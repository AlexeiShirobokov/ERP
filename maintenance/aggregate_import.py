from __future__ import annotations

import pandas as pd
from django.db import transaction
from django.utils import timezone

from .models import AggregateJournalRow, AggregateJournalUpload


COLUMN_ALIASES = {
    "department": ["Подразделение"],
    "machine_brand": ["Марка или обозначение техники", "Марка"],
    "modification": ["Модификация"],
    "inventory_number": ["Инвентарный номер"],
    "maintenance_start_date": ["Дата начала обслуживания"],
    "maintenance_end_date": ["Дата окончания обслуживания"],
    "actual_hours_at_maintenance": [
        "Фактическая наработка в момент проведения ТО",
        "Показания прибора учета",
    ],
    "machine_hours": ["Наработка машины"],
    "maintenance_type": ["Вид ТО", "Тип ТО"],
}


def _find_column(df: pd.DataFrame, variants: list[str]) -> str | None:
    for name in variants:
        if name in df.columns:
            return name
    return None


def _normalize_inventory(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _to_float(value):
    if pd.isna(value) or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


@transaction.atomic
def import_aggregate_upload(upload: AggregateJournalUpload, replace_existing_rows: bool = True) -> int:
    upload.status = AggregateJournalUpload.STATUS_IMPORTING
    upload.error_text = ""
    upload.save(update_fields=["status", "error_text"])

    try:
        df = pd.read_excel(upload.file.path, sheet_name="Агрегатный журнал")
        df = df.copy()
        df.columns = [str(col).strip() for col in df.columns]

        normalized = pd.DataFrame()

        for target_field, variants in COLUMN_ALIASES.items():
            source_col = _find_column(df, variants)
            if source_col:
                normalized[target_field] = df[source_col]
            else:
                normalized[target_field] = None

        if normalized["maintenance_start_date"].isna().all():
            raise ValueError("В файле не найдена колонка 'Дата начала обслуживания'.")

        normalized["maintenance_start_date"] = pd.to_datetime(
            normalized["maintenance_start_date"],
            errors="coerce",
        )
        normalized["maintenance_end_date"] = pd.to_datetime(
            normalized["maintenance_end_date"],
            errors="coerce",
        )

        normalized["inventory_number"] = normalized["inventory_number"].apply(_normalize_inventory)
        normalized["department"] = normalized["department"].fillna("").astype(str).str.strip()
        normalized["machine_brand"] = normalized["machine_brand"].fillna("").astype(str).str.strip()
        normalized["modification"] = normalized["modification"].fillna("").astype(str).str.strip()
        normalized["maintenance_type"] = normalized["maintenance_type"].fillna("").astype(str).str.strip()

        normalized["actual_hours_at_maintenance"] = normalized["actual_hours_at_maintenance"].apply(_to_float)
        normalized["machine_hours"] = normalized["machine_hours"].apply(_to_float)

        # убираем полностью пустые строки
        normalized = normalized[
            ~(
                normalized[["department", "machine_brand", "inventory_number"]]
                .fillna("")
                .astype(str)
                .apply(lambda col: col.str.strip())
                .eq("")
                .all(axis=1)
            )
        ].copy()

        if replace_existing_rows:
            upload.rows.all().delete()

        objects = []
        for excel_row_number, row in enumerate(normalized.to_dict("records"), start=2):
            objects.append(
                AggregateJournalRow(
                    upload=upload,
                    source_row_number=excel_row_number,
                    department=row.get("department", "") or "",
                    machine_brand=row.get("machine_brand", "") or "",
                    modification=row.get("modification", "") or "",
                    inventory_number=row.get("inventory_number", "") or "",
                    maintenance_start_date=row.get("maintenance_start_date"),
                    maintenance_end_date=row.get("maintenance_end_date"),
                    actual_hours_at_maintenance=row.get("actual_hours_at_maintenance"),
                    machine_hours=row.get("machine_hours"),
                    maintenance_type=row.get("maintenance_type", "") or "",
                )
            )

        AggregateJournalRow.objects.bulk_create(objects, batch_size=1000)

        upload.status = AggregateJournalUpload.STATUS_DONE
        upload.imported_at = timezone.now()
        upload.rows_count = len(objects)
        upload.error_text = ""
        upload.save(update_fields=["status", "imported_at", "rows_count", "error_text"])

        return len(objects)

    except Exception as exc:
        upload.status = AggregateJournalUpload.STATUS_ERROR
        upload.error_text = str(exc)
        upload.save(update_fields=["status", "error_text"])
        raise