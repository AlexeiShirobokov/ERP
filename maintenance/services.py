from pathlib import Path
import pandas as pd


class MaintenanceExcelService:
    def __init__(self):
        self.path = Path(__file__).resolve().parent.parent / "Services" / "maintenance.xlsx"

    def _read_reglament(self):
        df = pd.read_excel(self.path, sheet_name="Регламент")
        df = df.fillna("")
        df.columns = [str(col).strip() for col in df.columns]

        rename_map = {
            "Марка техники": "machine_brand",
            "Тип техники": "machine_type",
            "Вид ТО": "maintenance_type",
            "Выполненые работы": "work_name",
            "Группа деталей": "detail_group",
            "Наименование": "item_name",
            "Кат. №": "catalog_number",
            "Ед. изм.": "unit",
            "Кол-во": "qty_plan",
        }
        df = df.rename(columns=rename_map)

        needed = [
            "machine_brand",
            "machine_type",
            "maintenance_type",
            "work_name",
            "detail_group",
            "item_name",
            "catalog_number",
            "unit",
            "qty_plan",
        ]

        for col in needed:
            if col not in df.columns:
                df[col] = ""

        df = df[needed]
        df["machine_brand"] = df["machine_brand"].astype(str).str.strip()
        df["maintenance_type"] = df["maintenance_type"].astype(str).str.strip()

        # убираем совсем пустые строки
        df = df[
            ~(
                df[["machine_brand", "maintenance_type", "work_name", "item_name"]]
                .astype(str)
                .apply(lambda col: col.str.strip())
                .eq("")
                .all(axis=1)
            )
        ]

        return df

    def get_machine_brands(self):
        df = self._read_reglament()
        brands = sorted(
            x for x in df["machine_brand"].dropna().astype(str).str.strip().unique()
            if x
        )
        return brands

    def get_maintenance_types(self):
        df = self._read_reglament()
        types_ = sorted(
            x for x in df["maintenance_type"].dropna().astype(str).str.strip().unique()
            if x
        )
        return types_

    def get_tasks(self, machine_brand: str, maintenance_type: str):
        df = self._read_reglament()

        machine_brand = str(machine_brand).strip()
        maintenance_type = str(maintenance_type).strip()

        result = df[
            (df["machine_brand"] == machine_brand) &
            (df["maintenance_type"] == maintenance_type)
        ].copy()

        # если точного совпадения нет — пробуем упрощенную нормализацию марки
        if result.empty:
            df["brand_simple"] = df["machine_brand"].astype(str).apply(self._simplify_brand)
            machine_brand_simple = self._simplify_brand(machine_brand)

            result = df[
                (df["brand_simple"] == machine_brand_simple) &
                (df["maintenance_type"] == maintenance_type)
            ].copy()

        result = result.fillna("")

        tasks = []
        for _, row in result.iterrows():
            tasks.append({
                "work_name": str(row.get("work_name", "")).strip(),
                "detail_group": str(row.get("detail_group", "")).strip(),
                "item_name": str(row.get("item_name", "")).strip(),
                "catalog_number": str(row.get("catalog_number", "")).strip(),
                "unit": str(row.get("unit", "")).strip(),
                "qty_plan": row.get("qty_plan", ""),
            })

        return tasks

    def _simplify_brand(self, brand: str):
        return str(brand).upper().replace(" ", "").replace("-", "").replace("/", "")