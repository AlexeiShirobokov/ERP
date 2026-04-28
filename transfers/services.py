import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zipfile import BadZipFile, ZipFile

from django.db import transaction

from .models import TransferDepartment, TransferImportBatch, TransferItem, TransferOrder


ORDER_RE = re.compile(
    r"Заказ\s+на\s+перемещение\s+(?P<number>[^\s]+)\s+от\s+"
    r"(?P<date>\d{2}\.\d{2}\.\d{4})(?:\s+(?P<time>\d{1,2}:\d{2}:\d{2}))?",
    re.IGNORECASE,
)

MOVEMENT_RE = re.compile(
    r"Перемещение\s+товаров\s+(?P<number>[^\s]+)\s+от\s+"
    r"(?P<date>\d{2}\.\d{2}\.\d{4})(?:\s+(?P<time>\d{1,2}:\d{2}:\d{2}))?",
    re.IGNORECASE,
)

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def clean_text(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def parse_decimal(value):
    value = clean_text(value)

    if not value:
        return Decimal("0")

    try:
        return Decimal(value.replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def parse_datetime_from_match(match):
    if not match:
        return None

    date_text = match.group("date")
    time_text = match.group("time") or "00:00:00"

    try:
        return datetime.strptime(f"{date_text} {time_text}", "%d.%m.%Y %H:%M:%S")
    except ValueError:
        return None


def parse_responsible(document_text):
    document_text = clean_text(document_text)

    if "," not in document_text:
        return ""

    return document_text.split(",", 1)[1].strip()


def col_letters_to_number(cell_ref):
    letters = ""

    for char in cell_ref:
        if char.isalpha():
            letters += char
        else:
            break

    number = 0

    for char in letters:
        number = number * 26 + (ord(char.upper()) - ord("A") + 1)

    return number


def read_shared_strings(zip_file):
    """
    1С иногда создаёт xl/SharedStrings.xml вместо xl/sharedStrings.xml.
    Поэтому читаем оба варианта.
    """
    names = set(zip_file.namelist())

    shared_path = None

    if "xl/sharedStrings.xml" in names:
        shared_path = "xl/sharedStrings.xml"
    elif "xl/SharedStrings.xml" in names:
        shared_path = "xl/SharedStrings.xml"

    if not shared_path:
        return []

    root = ET.fromstring(zip_file.read(shared_path))
    result = []

    for si in root.findall(f"{NS_MAIN}si"):
        parts = []

        direct_t = si.find(f"{NS_MAIN}t")
        if direct_t is not None and direct_t.text:
            parts.append(direct_t.text)

        for rich_text in si.findall(f"{NS_MAIN}r"):
            t = rich_text.find(f"{NS_MAIN}t")
            if t is not None and t.text:
                parts.append(t.text)

        result.append("".join(parts))

    return result


def get_first_sheet_path(zip_file):
    """
    Для нашей выгрузки достаточно первого листа.
    Обычно это xl/worksheets/sheet1.xml.
    """
    names = zip_file.namelist()

    if "xl/worksheets/sheet1.xml" in names:
        return "xl/worksheets/sheet1.xml"

    for name in names:
        if name.startswith("xl/worksheets/") and name.endswith(".xml"):
            return name

    raise ValueError("В xlsx не найден лист Excel.")


def read_xlsx_rows(file_path):
    try:
        with ZipFile(file_path, "r") as zip_file:
            shared_strings = read_shared_strings(zip_file)
            sheet_path = get_first_sheet_path(zip_file)

            root = ET.fromstring(zip_file.read(sheet_path))

            rows = []

            for row in root.findall(f".//{NS_MAIN}sheetData/{NS_MAIN}row"):
                row_values = {}

                for cell in row.findall(f"{NS_MAIN}c"):
                    cell_ref = cell.attrib.get("r", "")
                    column_number = col_letters_to_number(cell_ref)

                    cell_type = cell.attrib.get("t")
                    value_element = cell.find(f"{NS_MAIN}v")
                    inline_string = cell.find(f"{NS_MAIN}is/{NS_MAIN}t")

                    value = ""

                    if cell_type == "s" and value_element is not None:
                        index = int(value_element.text)
                        if 0 <= index < len(shared_strings):
                            value = shared_strings[index]

                    elif cell_type == "inlineStr" and inline_string is not None:
                        value = inline_string.text or ""

                    elif value_element is not None:
                        value = value_element.text or ""

                    row_values[column_number] = clean_text(value)

                if row_values:
                    max_column = max(row_values.keys())
                    rows.append([row_values.get(i, "") for i in range(1, max_column + 1)])
                else:
                    rows.append([])

            return rows

    except BadZipFile:
        raise ValueError(
            "Файл не является корректным .xlsx. "
            "Откройте его в Excel и сохраните заново как 'Книга Excel (*.xlsx)'."
        )


def find_header_row(rows):
    for index, row in enumerate(rows):
        values = [clean_text(value) for value in row]

        if "Заказ на перемещение" in values and "Номенклатура" in values:
            return index, values

    raise ValueError(
        "Не найдена строка заголовков. "
        "Проверьте, что это выгрузка перемещений из 1С."
    )


def get_column_map(headers):
    required = {
        "Заказ на перемещение": "order",
        "Документ, Ответственный": "document",
        "Склад отправитель": "sender",
        "Склад получатель": "receiver",
        "Номенклатура": "item",
        "К оформлению Приход": "qty_in",
        "К оформлению Расход": "qty_out",
    }

    result = {}

    for column_index, title in enumerate(headers):
        normalized = clean_text(title)

        if normalized in required:
            result[required[normalized]] = column_index

    missing = [title for title, key in required.items() if key not in result]

    if missing:
        raise ValueError(f"В файле не найдены колонки: {', '.join(missing)}")

    return result


def get_cell(row, index):
    if index >= len(row):
        return ""
    return clean_text(row[index])


def read_period_text(rows):
    for row in rows[:10]:
        for value in row[:10]:
            value = clean_text(value)
            if value.startswith("Период:"):
                return value
    return ""


def get_latest_datetime(first_value, second_value):
    if first_value and second_value:
        return max(first_value, second_value)

    return first_value or second_value


def parse_transfer_workbook(file_path):
    rows = read_xlsx_rows(file_path)

    header_index, headers = find_header_row(rows)
    column_map = get_column_map(headers)
    period_text = read_period_text(rows)

    grouped = defaultdict(
        lambda: {
            "order_title": "",
            "order_date": None,
            "sender_warehouse": "",
            "receiver_warehouse": "",
            "responsible_name": "",
            "movement_numbers": set(),
            "last_movement_date": None,
            "items": defaultdict(
                lambda: {
                    "quantity_requested": Decimal("0"),
                    "quantity_moved": Decimal("0"),
                    "movement_numbers": set(),
                    "source_rows": [],
                }
            ),
        }
    )

    rows_count = 0

    for excel_row_number, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        order_text = get_cell(row, column_map["order"])

        if not order_text or order_text.lower() == "итого":
            continue

        item_name = get_cell(row, column_map["item"])

        if not item_name:
            continue

        order_match = ORDER_RE.search(order_text)

        if not order_match:
            continue

        order_number = order_match.group("number")

        document_text = get_cell(row, column_map["document"])
        movement_match = MOVEMENT_RE.search(document_text)

        movement_number = movement_match.group("number") if movement_match else ""
        movement_date = parse_datetime_from_match(movement_match)

        order_data = grouped[order_number]
        order_data["order_title"] = order_text
        order_data["order_date"] = order_data["order_date"] or parse_datetime_from_match(order_match)
        order_data["sender_warehouse"] = get_cell(row, column_map["sender"])
        order_data["receiver_warehouse"] = get_cell(row, column_map["receiver"])

        responsible_name = parse_responsible(document_text)
        if responsible_name:
            order_data["responsible_name"] = responsible_name

        if movement_number:
            order_data["movement_numbers"].add(movement_number)
            order_data["last_movement_date"] = get_latest_datetime(
                order_data["last_movement_date"],
                movement_date,
            )

        item_data = order_data["items"][item_name]

        qty_requested = parse_decimal(get_cell(row, column_map["qty_in"]))
        qty_moved = parse_decimal(get_cell(row, column_map["qty_out"]))

        item_data["quantity_requested"] += qty_requested
        item_data["quantity_moved"] += qty_moved

        if movement_number:
            item_data["movement_numbers"].add(movement_number)

        item_data["source_rows"].append(str(excel_row_number))
        rows_count += 1

    return {
        "period_text": period_text,
        "rows_count": rows_count,
        "orders": grouped,
    }


@transaction.atomic
def import_transfer_batch(batch_id):
    batch = TransferImportBatch.objects.select_for_update().get(pk=batch_id)

    parsed = parse_transfer_workbook(batch.file.path)

    orders_count = 0
    items_count = 0

    for order_number, order_data in parsed["orders"].items():
        department = TransferDepartment.find_by_receiver(order_data["receiver_warehouse"])

        order, _ = TransferOrder.objects.get_or_create(order_number=order_number)

        order.order_title = order_data["order_title"]
        order.order_date = order_data["order_date"]
        order.sender_warehouse = order_data["sender_warehouse"]
        order.receiver_warehouse = order_data["receiver_warehouse"]
        order.responsible_name = order_data["responsible_name"]

        if department:
            order.department = department

        for movement_number in sorted(order_data["movement_numbers"]):
            order.set_movement_number(movement_number)

        order.last_movement_date = get_latest_datetime(
            order.last_movement_date,
            order_data["last_movement_date"],
        )
        order.last_import_batch = batch
        order.save()

        for item_name, item_data in order_data["items"].items():
            item, _ = TransferItem.objects.get_or_create(
                order=order,
                item_name=item_name,
            )

            item.quantity_requested = item_data["quantity_requested"]
            item.quantity_moved = item_data["quantity_moved"]
            item.movement_numbers = "\n".join(sorted(item_data["movement_numbers"]))
            item.source_rows = ", ".join(item_data["source_rows"])
            item.save()

            items_count += 1

        order.recalculate_status_from_items(save=True)
        orders_count += 1

    batch.period_text = parsed["period_text"]
    batch.rows_count = parsed["rows_count"]
    batch.orders_count = orders_count
    batch.items_count = items_count
    batch.error = ""
    batch.save(
        update_fields=[
            "period_text",
            "rows_count",
            "orders_count",
            "items_count",
            "error",
        ]
    )

    return batch