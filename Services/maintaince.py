from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from django.db import transaction
from django.utils import timezone

from .models import (
    Department,
    MaintenancePlanRow,
    MaintenancePlanUpload,
)


# =========================================================
# ОБЩИЕ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================================================

def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _to_float_or_none(value: Any) -> float | None:
    if value in ("", None):
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    text = str(value).strip()
    text = text.replace("\xa0", "").replace(" ", "").replace(",", ".")

    if not text or text.lower() in {"none", "nan", "nat"}:
        return None

    try:
        return float(text)
    except Exception:
        return None


def _to_int_or_none(value: Any) -> int | None:
    number = _to_float_or_none(value)
    if number is None:
        return None
    try:
        return int(number)
    except Exception:
        return None


def _to_date_or_none(value: Any) -> date | None:
    if value in ("", None):
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "nat"}:
        return None

    # сначала пробуем популярные форматы явно
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except Exception:
            pass

    # fallback через pandas
    dt = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(dt):
        return None
    return dt.date()


def _month_start(value: date | None) -> date | None:
    if not value:
        return None
    return value.replace(day=1)


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _find_column(df: pd.DataFrame, aliases: list[str], required: bool = False) -> str | None:
    normalized = {str(col).strip().lower(): col for col in df.columns}

    for alias in aliases:
        key = alias.strip().lower()
        if key in normalized:
            return normalized[key]

    if required:
        raise ValueError(f"Не найдена обязательная колонка. Ожидались варианты: {aliases}")

    return None


# =========================================================
# 1. СТАРЫЙ СЕРВИС ДЛЯ ФАКТА ТО
#    НУЖЕН ДЛЯ ТВОЕГО ТЕКУЩЕГО create_record
# =========================================================

class MaintenanceExcelService:
    """
    Читает шаблон/справочник работ ТО из Services/maintenance.xlsx
    и отдает:
    - список марок техники
    - список видов ТО
    - список работ по выбранной марке и виду ТО
    """

    MACHINE_BRAND_ALIASES = ["Марка техники", "Марка", "Модель", "machine_brand"]
    MAINTENANCE_TYPE_ALIASES = ["Вид ТО", "Тип ТО", "maintenance_type", "Номер проведения ТО"]

    TASK_COLUMN_ALIASES = {
        "work_name": ["Работа", "Наименование работы", "work_name"],
        "detail_group": ["Группа деталей", "Узел", "detail_group"],
        "item_name": ["Наименование", "Материал", "Запчасть", "item_name"],
        "catalog_number": ["Кат. №", "Каталожный номер", "catalog_number"],
        "unit": ["Ед. изм.", "Ед.", "unit"],
        "qty_plan": ["Количество план", "Кол-во", "qty_plan"],
    }

    def __init__(self, file_path: str | Path | None = None, sheet_name: str | int = 0):
        base_dir = Path(__file__).resolve().parent.parent
        self.file_path = Path(file_path) if file_path else base_dir / "Services" / "maintenance.xlsx"
        self.sheet_name = sheet_name
        self._df: pd.DataFrame | None = None

    def _read(self) -> pd.DataFrame:
        if self._df is not None:
            return self._df

        df = pd.read_excel(self.file_path, sheet_name=self.sheet_name)
        df.columns = [str(c).strip() for c in df.columns]

        machine_brand_col = _find_column(df, self.MACHINE_BRAND_ALIASES, required=True)
        maintenance_type_col = _find_column(df, self.MAINTENANCE_TYPE_ALIASES, required=True)

        rename_map = {
            machine_brand_col: "machine_brand",
            maintenance_type_col: "maintenance_type",
        }

        for target, aliases in self.TASK_COLUMN_ALIASES.items():
            col = _find_column(df, aliases, required=False)
            if col:
                rename_map[col] = target

        df = df.rename(columns=rename_map)

        # гарантируем нужные колонки
        for col in ["machine_brand", "maintenance_type", *self.TASK_COLUMN_ALIASES.keys()]:
            if col not in df.columns:
                df[col] = ""

        text_cols = ["machine_brand", "maintenance_type", "work_name", "detail_group", "item_name", "catalog_number", "unit"]
        for col in text_cols:
            df[col] = df[col].apply(_clean_text)

        df["qty_plan"] = df["qty_plan"].apply(_to_float_or_none)

        self._df = df
        return self._df

    def get_machine_brands(self) -> list[str]:
        df = self._read()
        values = [x for x in df["machine_brand"].dropna().unique().tolist() if _clean_text(x)]
        return sorted({_clean_text(x) for x in values})

    def get_maintenance_types(self) -> list[str]:
        df = self._read()
        values = [x for x in df["maintenance_type"].dropna().unique().tolist() if _clean_text(x)]
        return sorted({_clean_text(x) for x in values})

    def get_tasks(self, machine_brand: str, maintenance_type: str) -> list[dict[str, Any]]:
        df = self._read()

        machine_brand = _clean_text(machine_brand)
        maintenance_type = _clean_text(maintenance_type)

        filtered = df[
            (df["machine_brand"] == machine_brand) &
            (df["maintenance_type"] == maintenance_type)
        ]

        result = []
        for _, row in filtered.iterrows():
            work_name = _clean_text(row.get("work_name"))
            if not work_name:
                continue

            result.append({
                "work_name": work_name,
                "detail_group": _clean_text(row.get("detail_group")),
                "item_name": _clean_text(row.get("item_name")),
                "catalog_number": _clean_text(row.get("catalog_number")),
                "unit": _clean_text(row.get("unit")),
                "qty_plan": row.get("qty_plan"),
            })

        return result


# =========================================================
# 2. НОВЫЙ СЕРВИС ДЛЯ КАЛЕНДАРНОГО ПЛАНА ТО
#    ГРЯЗНЫЙ EXCEL -> ОЧИСТКА -> БД
# =========================================================

@dataclass
class PlanImportResult:
    upload_id: int
    rows_total: int
    rows_loaded: int
    status: str
    error_text: str = ""


class MaintenancePlanImportService:
    """
    Обрабатывает загруженный Excel календарного плана ТО
    и сохраняет его строки в MaintenancePlanRow.
    """

    COLUMN_ALIASES = {
        "department": ["Подразделение", "department", "Цех", "Участок"],
        "machine_brand": ["Марка техники", "Марка", "machine_brand"],
        "machine_name": ["Наименование техники", "Техника", "machine_name"],
        "inventory_number": ["Инв. номер", "Инвентарный номер", "inventory_number"],
        "maintenance_type": ["Вид ТО", "Тип ТО", "maintenance_type"],
        "maintenance_number": ["Номер проведения ТО", "Номер ТО", "maintenance_number"],
        "plan_date": ["Плановая дата ТО", "Дата ТО", "Дата", "plan_date"],
        "responsible_fio": ["ФИО ответственного", "Ответственный", "responsible_fio"],
        "machine_hours_plan": ["Плановые машиночасы", "Машиночасы", "machine_hours_plan"],
        "status": ["Статус", "status"],
        "comment": ["Комментарий", "Примечание", "comment"],
    }

    REQUIRED_CANONICAL_COLUMNS = ["machine_brand", "maintenance_type", "plan_date"]

    def __init__(self, sheet_name: str | int = 0):
        self.sheet_name = sheet_name

    def process_upload(self, upload_id: int) -> PlanImportResult:
        upload = MaintenancePlanUpload.objects.get(pk=upload_id)

        upload.status = MaintenancePlanUpload.STATUS_PROCESSING
        upload.started_at = timezone.now()
        upload.finished_at = None
        upload.error_text = ""
        upload.rows_total = 0
        upload.rows_loaded = 0
        upload.save(update_fields=["status", "started_at", "finished_at", "error_text", "rows_total", "rows_loaded"])

        try:
            df = self._read_upload(upload)
            df = self._normalize_plan_df(df)

            with transaction.atomic():
                upload.rows.all().delete()

                rows_to_create = self._build_plan_rows(upload, df)

                if rows_to_create:
                    MaintenancePlanRow.objects.bulk_create(rows_to_create, batch_size=1000)

                upload.rows_total = len(df)
                upload.rows_loaded = len(rows_to_create)
                upload.status = MaintenancePlanUpload.STATUS_DONE
                upload.finished_at = timezone.now()

                # делаем этот план активным
                MaintenancePlanUpload.objects.exclude(pk=upload.pk).update(is_active=False)
                upload.is_active = True

                # если report_date еще не заполнили — берем максимальную plan_date
                if not upload.report_date:
                    valid_dates = [x for x in df["plan_date"].tolist() if x]
                    if valid_dates:
                        upload.report_date = max(valid_dates)

                upload.save(
                    update_fields=[
                        "rows_total",
                        "rows_loaded",
                        "status",
                        "finished_at",
                        "is_active",
                        "report_date",
                    ]
                )

            return PlanImportResult(
                upload_id=upload.pk,
                rows_total=upload.rows_total,
                rows_loaded=upload.rows_loaded,
                status=upload.status,
            )

        except Exception as exc:
            upload.status = MaintenancePlanUpload.STATUS_FAILED
            upload.finished_at = timezone.now()
            upload.error_text = str(exc)
            upload.save(update_fields=["status", "finished_at", "error_text"])

            return PlanImportResult(
                upload_id=upload.pk,
                rows_total=upload.rows_total,
                rows_loaded=upload.rows_loaded,
                status=upload.status,
                error_text=str(exc),
            )

    def process_pending_uploads(self) -> list[PlanImportResult]:
        results: list[PlanImportResult] = []

        pending_ids = list(
            MaintenancePlanUpload.objects
            .filter(status=MaintenancePlanUpload.STATUS_PENDING)
            .values_list("id", flat=True)
            .order_by("uploaded_at", "id")
        )

        for upload_id in pending_ids:
            results.append(self.process_upload(upload_id))

        return results

    def _read_upload(self, upload: MaintenancePlanUpload) -> pd.DataFrame:
        path = upload.file.path
        df = pd.read_excel(path, sheet_name=self.sheet_name)
        df.columns = [str(c).strip() for c in df.columns]
        return df

    def _normalize_plan_df(self, df: pd.DataFrame) -> pd.DataFrame:
        rename_map: dict[str, str] = {}

        for canonical_name, aliases in self.COLUMN_ALIASES.items():
            found_col = _find_column(df, aliases, required=False)
            if found_col:
                rename_map[found_col] = canonical_name

        df = df.rename(columns=rename_map)

        # создаем недостающие колонки
        for canonical_name in self.COLUMN_ALIASES.keys():
            if canonical_name not in df.columns:
                df[canonical_name] = None

        # очистка текстов
        text_cols = [
            "department",
            "machine_brand",
            "machine_name",
            "inventory_number",
            "maintenance_type",
            "maintenance_number",
            "responsible_fio",
            "status",
            "comment",
        ]
        for col in text_cols:
            df[col] = df[col].apply(_clean_text)

        # числа
        df["machine_hours_plan"] = df["machine_hours_plan"].apply(_to_int_or_none)

        # даты
        df["plan_date"] = df["plan_date"].apply(_to_date_or_none)

        # убираем полностью пустые строки
        df = df.loc[
            ~(
                df[["machine_brand", "maintenance_type"]]
                .astype(str)
                .apply(lambda col: col.str.strip())
                .eq("")
                .all(axis=1)
            )
        ].copy()

        # проверяем обязательные поля
        missing_required = []
        for col in self.REQUIRED_CANONICAL_COLUMNS:
            if col not in df.columns:
                missing_required.append(col)

        if missing_required:
            raise ValueError(f"В файле не найдены обязательные колонки: {', '.join(missing_required)}")

        return df

    def _build_plan_rows(self, upload: MaintenancePlanUpload, df: pd.DataFrame) -> list[MaintenancePlanRow]:
        rows: list[MaintenancePlanRow] = []
        department_cache: dict[str, Department] = {}

        for excel_row_number, (_, row) in enumerate(df.iterrows(), start=2):
            machine_brand = _clean_text(row.get("machine_brand"))
            maintenance_type = _clean_text(row.get("maintenance_type"))
            plan_date = row.get("plan_date")

            # пропускаем мусорные строки
            if not machine_brand and not maintenance_type and not plan_date:
                continue

            department_name = _clean_text(row.get("department"))
            department_obj = None
            if department_name:
                department_obj = department_cache.get(department_name)
                if department_obj is None:
                    department_obj, _ = Department.objects.get_or_create(name=department_name)
                    department_cache[department_name] = department_obj

            raw_data = {}
            for key, value in row.to_dict().items():
                raw_data[str(key)] = _json_safe(value)

            rows.append(
                MaintenancePlanRow(
                    upload=upload,
                    department=department_obj,
                    machine_brand=machine_brand,
                    machine_name=_clean_text(row.get("machine_name")),
                    inventory_number=_clean_text(row.get("inventory_number")),
                    maintenance_type=maintenance_type,
                    maintenance_number=_clean_text(row.get("maintenance_number")),
                    plan_date=plan_date,
                    plan_month=_month_start(plan_date),
                    responsible_fio=_clean_text(row.get("responsible_fio")),
                    machine_hours_plan=_to_int_or_none(row.get("machine_hours_plan")),
                    status=_clean_text(row.get("status")),
                    comment=_clean_text(row.get("comment")),
                    source_row_number=excel_row_number,
                    raw_data=raw_data,
                )
            )

        return rows