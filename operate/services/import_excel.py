from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from django.db import transaction

from operate.models import OperateDataFile, OperateRow


COLUMN_ALIASES = {
    "Дата": "date",
    "Год операции": "year",
    "Месяц": "month",
    "Подразделение": "subdivision",
    "Блок": "block",
    "Передел": "process_name",
    "Марка техники": "machine_brand",
    "Марка машины": "machine_name",
    "Инв. №": "machine_inventory",
    "Объём работ": "work_volume",
    "Объем работ": "work_volume",
    "Объем работ, скорректированный": "corrected_work_volume",
    "Объём работ, скорректированный": "corrected_work_volume",
    "Время работы, час/см": "work_time",
    "Время простоя, час/см": "downtime",
    "Откатка, м": "transportation_distance",
    "Ф.И.О. Горного мастера": "shift_master",
    "Ф.И.О. Машиниста": "operator_name",
    "Ф.И.О. Помощника": "assistant_name",
    "Описание причины простоя (примечание)": "downtime_reason",
}


def clean_str(value: Any) -> str:
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    return str(value).strip()


def clean_float(value: Any):
    if value is None:
        return None
    if pd.isna(value):
        return None

    text = str(value).strip()
    if not text:
        return None

    text = text.replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except Exception:
        return None


def clean_int(value: Any):
    val = clean_float(value)
    if val is None:
        return None
    try:
        return int(val)
    except Exception:
        return None


def clean_date(value: Any):
    if value is None:
        return None
    if pd.isna(value):
        return None

    try:
        dt = pd.to_datetime(value, errors="coerce", dayfirst=True)
        if pd.isna(dt):
            return None
        return dt.date()
    except Exception:
        return None


def detect_engine(file_path: str):
    ext = Path(file_path).suffix.lower()
    if ext == ".xlsb":
        return "pyxlsb"
    return None


def read_dataframe(file_path: str, sheet_name="Реестр") -> pd.DataFrame:
    engine = detect_engine(file_path)
    kwargs = {"sheet_name": sheet_name}
    if engine:
        kwargs["engine"] = engine
    return pd.read_excel(file_path, **kwargs)


def import_excel_to_db(data_file: OperateDataFile, sheet_name="Реестр", batch_size: int = 1000):
    file_path = data_file.file.path
    df = read_dataframe(file_path, sheet_name=sheet_name)

    if df.empty:
        OperateRow.objects.filter(data_file=data_file).delete()
        data_file.is_processed = True
        data_file.processing_error = ""
        data_file.save(update_fields=["is_processed", "processing_error"])
        return

    df = df.copy()

    with transaction.atomic():
        OperateRow.objects.filter(data_file=data_file).delete()

        rows_to_create = []

        for idx, row in df.iterrows():
            row_dict = row.to_dict()

            rows_to_create.append(
                OperateRow(
                    data_file=data_file,
                    source_row_number=idx + 2,
                    date=clean_date(row.get("Дата")),
                    year=clean_int(row.get("Год операции")),
                    month=clean_int(row.get("Месяц")),
                    subdivision=clean_str(row.get("Подразделение")),
                    block=clean_str(row.get("Блок")),
                    process_name=clean_str(row.get("Передел")),
                    machine_brand=clean_str(row.get("Марка техники")),
                    machine_name=clean_str(row.get("Марка машины")),
                    machine_inventory=clean_str(row.get("Инв. №")),
                    work_volume=clean_float(row.get("Объём работ") if "Объём работ" in row else row.get("Объем работ")),
                    corrected_work_volume=clean_float(
                        row.get("Объем работ, скорректированный")
                        if "Объем работ, скорректированный" in row
                        else row.get("Объём работ, скорректированный")
                    ),
                    work_time=clean_float(row.get("Время работы, час/см")),
                    downtime=clean_float(row.get("Время простоя, час/см")),
                    transportation_distance=clean_float(row.get("Откатка, м")),
                    shift_master=clean_str(row.get("Ф.И.О. Горного мастера")),
                    operator_name=clean_str(row.get("Ф.И.О. Машиниста")),
                    assistant_name=clean_str(row.get("Ф.И.О. Помощника")),
                    downtime_reason=clean_str(row.get("Описание причины простоя (примечание)")),
                    raw_data={k: ("" if pd.isna(v) else str(v)) for k, v in row_dict.items()},
                )
            )

            if len(rows_to_create) >= batch_size:
                OperateRow.objects.bulk_create(rows_to_create, batch_size=batch_size)
                rows_to_create = []

        if rows_to_create:
            OperateRow.objects.bulk_create(rows_to_create, batch_size=batch_size)

        data_file.is_processed = True
        data_file.processing_error = ""
        data_file.save(update_fields=["is_processed", "processing_error"])