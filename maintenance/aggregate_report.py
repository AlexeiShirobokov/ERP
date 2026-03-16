import pandas as pd

from .models import AggregateJournalRow


def build_result_pv_from_db():
    qs = AggregateJournalRow.objects.all().values(
        "department",
        "machine_brand",
        "modification",
        "inventory_number",
        "maintenance_start_date",
        "actual_hours_at_maintenance",
        "machine_hours",
        "maintenance_type",
    )

    rows = list(qs)

    result_columns = [
        "Подразделение",
        "Марка",
        "Модификация",
        "Инвентарный номер",
        "Дата начала обслуживания",
        "Фактическая наработка в момент проведения ТО",
        "Наработка машины",
        "Вид ТО",
    ]

    if not rows:
        return pd.DataFrame(columns=result_columns)

    df = pd.DataFrame(rows)

    df["maintenance_start_date"] = pd.to_datetime(df["maintenance_start_date"], errors="coerce")

    keys = [
        "department",
        "machine_brand",
        "modification",
        "inventory_number",
    ]

    df = df.sort_values(
        by=keys + ["maintenance_start_date"],
        ascending=[True, True, True, True, False],
        na_position="last",
    )

    # берём последнюю запись по каждой единице техники
    df = df.drop_duplicates(subset=keys, keep="first").copy()

    df = df.rename(
        columns={
            "department": "Подразделение",
            "machine_brand": "Марка",
            "modification": "Модификация",
            "inventory_number": "Инвентарный номер",
            "maintenance_start_date": "Дата начала обслуживания",
            "actual_hours_at_maintenance": "Фактическая наработка в момент проведения ТО",
            "machine_hours": "Наработка машины",
            "maintenance_type": "Вид ТО",
        }
    )

    for col in result_columns:
        if col not in df.columns:
            df[col] = ""

    df = df[result_columns].reset_index(drop=True)

    if not df.empty:
        df["Дата начала обслуживания"] = pd.to_datetime(
            df["Дата начала обслуживания"], errors="coerce"
        ).dt.strftime("%d.%m.%Y")

    return df