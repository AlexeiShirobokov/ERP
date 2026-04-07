"""Утилиты для анализа 'Сводного наблюдателя оперативной информации'.

Этот модуль собран из Jupyter-ноутбука и подготовлен к дальнейшей
интеграции в Django. В отличие от ноутбука, здесь логика вынесена в функции,
которые возвращают DataFrame и Plotly Figure, а не печатают всё подряд.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


TODAY = pd.Timestamp.today().normalize()
TORFY_LABEL = "Торфы (объединено)"
DEFAULT_EXCLUDED_PEREDELS = ("Бурение взрывных скважин, м3", "МВ")


class OpiProcessor:
    """Загрузка, подготовка, фильтрация и сводные таблицы по ОПИ."""

    def __init__(self, df_path: str, sheet_name: str = "Реестр") -> None:
        self.file_path = Path(df_path)
        self.sheet_name = sheet_name
        self.df: Optional[pd.DataFrame] = None
        self.df_ready: Optional[pd.DataFrame] = None
        self.df_filtered: Optional[pd.DataFrame] = None

    def load_data(self, force: bool = False, usecols: Optional[Sequence[str]] = None) -> "OpiProcessor":
        """Читает Excel один раз и сохраняет в self.df."""
        if self.df is not None and not force:
            return self

        engine = "pyxlsb" if self.file_path.suffix.lower() == ".xlsb" else None
        self.df = pd.read_excel(
            self.file_path,
            sheet_name=self.sheet_name,
            engine=engine,
            usecols=usecols,
        )
        self._convert_date("Дата")
        return self

    def _convert_date(self, date_col: str = "Дата") -> None:
        """Робастная конвертация дат (Excel serial / UNIX / строки)."""
        if self.df is None or date_col not in self.df.columns:
            return

        s = self.df[date_col]
        if pd.api.types.is_datetime64_any_dtype(s):
            return

        if pd.api.types.is_numeric_dtype(s):
            x = pd.to_numeric(s, errors="coerce")
            x_valid = x[np.isfinite(x)]
            if not x_valid.empty:
                xmin, xmax = float(x_valid.min()), float(x_valid.max())
                if ((1e4 <= xmin <= 1e5) and (1e4 <= xmax <= 1e5)) or xmax < 1e6:
                    self.df[date_col] = pd.to_datetime("1899-12-30") + pd.to_timedelta(x, unit="D")
                    return
                if 1e9 <= xmin <= 2e10:
                    self.df[date_col] = pd.to_datetime(x, unit="s", errors="coerce")
                    return
                if 1e12 <= xmin <= 2e13:
                    self.df[date_col] = pd.to_datetime(x, unit="ms", errors="coerce")
                    return
                if 1e15 <= xmin <= 2e16:
                    self.df[date_col] = pd.to_datetime(x, unit="us", errors="coerce")
                    return
                if 1e18 <= xmin <= 2e19:
                    self.df[date_col] = pd.to_datetime(x, unit="ns", errors="coerce")
                    return

        self.df[date_col] = pd.to_datetime(s, errors="coerce", dayfirst=True)

    def prepare(
        self,
        numeric_columns: Optional[dict[str, float]] = None,
        volume_col: str = "Объём работ",
        coeff_col: str = "k, маркзамера",
        result_col: str = "Объем работ, скорректированный",
        add_month: bool = True,
    ) -> "OpiProcessor":
        """Чистит числовые поля и считает скорректированный объём."""
        if self.df is None:
            raise RuntimeError("Сначала вызовите load_data().")

        d = self.df.copy()

        if numeric_columns:
            for col, default in numeric_columns.items():
                if col in d.columns:
                    d[col] = (
                        d[col]
                        .astype(str)
                        .str.replace(",", ".", regex=False)
                        .str.replace(r"[^\d\.\-eE]", "", regex=True)
                        .replace("", pd.NA)
                        .apply(pd.to_numeric, errors="coerce")
                        .fillna(default)
                    )

        if volume_col in d.columns and coeff_col in d.columns:
            d[result_col] = d[volume_col] * d[coeff_col]

        if add_month and "Дата" in d.columns:
            months = {
                1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь",
                7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
            }
            d["Дата"] = pd.to_datetime(d["Дата"], errors="coerce")
            d["Месяц"] = d["Дата"].dt.month.map(months)

        self.df_ready = d
        return self

    @staticmethod
    def _norm_object_name(x: Any) -> str:
        return str(x).replace("—", "-").replace("–", "-").replace("\u00A0", " ").strip()

    def filter_by_conditions(
        self,
        field_conditions: dict[str, Any],
        positive_col: Optional[str] = "Объем работ, скорректированный",
    ) -> "OpiProcessor":
        """Фильтрация по набору условий без повторного чтения файла."""
        src = self.df_ready.copy() if self.df_ready is not None else self.df.copy()
        if src is None:
            raise RuntimeError("Нет данных. Сначала вызовите load_data().")

        df_filtered = src

        for col, value in field_conditions.items():
            if col not in df_filtered.columns:
                continue

            col_for_filter = col
            norm_val = value

            if pd.api.types.is_string_dtype(df_filtered[col].dtype):
                df_filtered[col] = df_filtered[col].astype(str).str.strip()

            if col == "Месторождение, объект":
                tmp = "__obj_norm__"
                df_filtered[tmp] = df_filtered[col].map(self._norm_object_name)
                col_for_filter = tmp
                if isinstance(value, (list, set, tuple)):
                    norm_val = [self._norm_object_name(v) for v in value]
                else:
                    norm_val = self._norm_object_name(value)

            is_range = isinstance(norm_val, (list, tuple)) and len(norm_val) == 2
            is_date_range = is_range and all(isinstance(x, (pd.Timestamp, datetime, np.datetime64)) for x in norm_val)
            is_num_range = is_range and all(isinstance(x, (int, float, np.number)) for x in norm_val)

            if is_date_range or is_num_range:
                a, b = norm_val
                if is_date_range:
                    df_filtered[col_for_filter] = pd.to_datetime(df_filtered[col_for_filter], errors="coerce")
                    a, b = pd.to_datetime(a), pd.to_datetime(b)
                df_filtered = df_filtered[(df_filtered[col_for_filter] >= a) & (df_filtered[col_for_filter] <= b)]
            elif isinstance(norm_val, (list, set, tuple)):
                df_filtered = df_filtered[df_filtered[col_for_filter].isin(list(norm_val))]
            else:
                df_filtered = df_filtered[df_filtered[col_for_filter] == norm_val]

            if col_for_filter == "__obj_norm__" and "__obj_norm__" in df_filtered.columns:
                df_filtered = df_filtered.drop(columns="__obj_norm__")

        if positive_col and positive_col in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[positive_col] > 0]

        self.df_filtered = df_filtered
        return self

    def get_pivot_table(
        self,
        index: Sequence[str],
        columns: str,
        values: str = "Объем работ, скорректированный",
    ) -> pd.DataFrame:
        if self.df_filtered is None:
            raise RuntimeError("Сначала вызовите filter_by_conditions(...).")
        return (
            self.df_filtered
            .pivot_table(index=index, columns=columns, values=values, aggfunc="sum", fill_value=0)
            .reset_index()
        )

    def pivot_for(
        self,
        conditions: dict[str, Any],
        index: Sequence[str],
        columns: str,
        values: str = "Объем работ, скорректированный",
    ) -> pd.DataFrame:
        return self.filter_by_conditions(conditions).get_pivot_table(index=index, columns=columns, values=values)

    def export_to_excel(self, df: pd.DataFrame, file_name: str) -> None:
        Path(file_name).parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(file_name, index=False)


# -----------------------------
# Общие вспомогательные функции
# -----------------------------

def combine_torf_peredel(value: Any) -> Optional[str]:
    s = str(value).strip().lower()
    if (("вскрыша торфов" in s and "экскаватор" in s) or
        ("вскрыша торфов" in s and "бульдозер" in s) or
        ("погрузка торфов" in s)):
        return TORFY_LABEL
    return None


def cut_to_today_each_year(
    df: pd.DataFrame,
    date_col: str = "Дата",
    ref_date: pd.Timestamp = TODAY,
) -> pd.DataFrame:
    m = ref_date.month
    d = ref_date.day
    return df[
        (df[date_col].dt.month < m) |
        ((df[date_col].dt.month == m) & (df[date_col].dt.day <= d))
    ].copy()


def add_inyear_axis(
    df: pd.DataFrame,
    date_col: str = "Дата",
    new_col: str = "Дата_внутри_года",
) -> pd.DataFrame:
    mmdd = df[date_col].dt.strftime("%m-%d")
    df[new_col] = pd.to_datetime("2000-" + mmdd, format="%Y-%m-%d", errors="coerce")
    return df


def detect_inventory_column(columns: Iterable[str]) -> str:
    candidates = ["Инв. №", "Инв№", "Инв.№", "Инв №"]
    for col in candidates:
        if col in columns:
            return col
    raise KeyError(f"Не найдена колонка инвентарного номера. Доступные колонки: {list(columns)}")


def prepare_base_df(processor: OpiProcessor) -> pd.DataFrame:
    if processor.df_ready is None:
        raise RuntimeError("Сначала вызовите processor.prepare(...).")
    df = processor.df_ready.copy()
    if "Дата" in df.columns:
        df["Дата"] = pd.to_datetime(df["Дата"], errors="coerce")
    if "Объем работ, скорректированный" in df.columns:
        df["Объем работ, скорректированный"] = pd.to_numeric(df["Объем работ, скорректированный"], errors="coerce")
    return df


# -----------------------------
# Графики торфов по подразделениям
# -----------------------------

def build_torf_charts_for_subdivision(processor: OpiProcessor, subdivision_name: str) -> tuple[go.Figure, go.Figure]:
    df = prepare_base_df(processor)
    df = df.dropna(subset=["Дата", "Объем работ, скорректированный"]).copy()
    df["Передел_для_графика"] = df["Передел"].apply(combine_torf_peredel)
    df["ПланФакт_norm"] = df["План / Факт"].astype(str).str.strip().str.lower()
    df["Год_даты"] = df["Дата"].dt.year
    df["Подразделение"] = df["Подразделение"].astype(str).str.strip()

    sub_df = df[
        (df["Подразделение"] == subdivision_name) &
        (df["Передел_для_графика"].notna())
    ].copy()

    if sub_df.empty:
        raise ValueError(f"Нет данных для подразделения: {subdivision_name}")

    fact = cut_to_today_each_year(sub_df[sub_df["ПланФакт_norm"] == "факт"].copy())
    fact_daily = fact.groupby(["Год_даты", "Дата"], as_index=False)["Объем работ, скорректированный"].sum()
    fact_daily = add_inyear_axis(fact_daily).dropna(subset=["Дата_внутри_года"]).copy()
    fact_daily = fact_daily.sort_values(["Год_даты", "Дата_внутри_года"])
    fact_daily["Накопленный объём"] = fact_daily.groupby("Год_даты")["Объем работ, скорректированный"].cumsum()

    fig1 = px.line(
        fact_daily,
        x="Дата_внутри_года",
        y="Накопленный объём",
        color="Год_даты",
        title=f"{subdivision_name}: торфы, накопленный факт по годам на текущую дату",
        markers=True,
    )
    fig1.update_layout(xaxis_title="Дата", yaxis_title="Накопленный объём", legend_title_text="Год")
    fig1.update_xaxes(tickformat="%d.%m")

    plan_fact_2026 = cut_to_today_each_year(
        sub_df[(sub_df["Год_даты"] == 2026) & (sub_df["ПланФакт_norm"].isin(["факт", "план"]))].copy()
    )
    plan_fact_2026["Сценарий"] = plan_fact_2026["ПланФакт_norm"].map({"факт": "Факт 2026", "план": "План 2026"})
    pf_daily = plan_fact_2026.groupby(["Сценарий", "Дата"], as_index=False)["Объем работ, скорректированный"].sum()
    pf_daily = pf_daily.sort_values(["Сценарий", "Дата"])
    pf_daily["Накопленный объём"] = pf_daily.groupby("Сценарий")["Объем работ, скорректированный"].cumsum()

    fig2 = px.line(
        pf_daily,
        x="Дата",
        y="Накопленный объём",
        color="Сценарий",
        line_dash="Сценарий",
        title=f"{subdivision_name}: торфы, факт 2026 vs план 2026",
        markers=True,
    )
    fig2.update_layout(xaxis_title="Дата", yaxis_title="Накопленный объём", legend_title_text="Сценарий")
    fig2.update_xaxes(tickformat="%d.%m")

    return fig1, fig2


def build_torf_charts_for_subdivisions(
    processor: OpiProcessor,
    subdivisions: Sequence[str],
) -> dict[str, tuple[go.Figure, go.Figure]]:
    return {sub: build_torf_charts_for_subdivision(processor, sub) for sub in subdivisions}


# -----------------------------
# Таблицы среднесменной производительности
# -----------------------------

def aggregate_shift_productivity(data: pd.DataFrame, group_cols: Sequence[str]) -> pd.DataFrame:
    agg = data.groupby(list(group_cols), as_index=False).agg(
        Объем_итого=("Объем работ, скорректированный", "sum"),
        Смен=("Объем работ, скорректированный", "size"),
    )
    agg["Среднесменная производительность"] = agg["Объем_итого"] / agg["Смен"]
    return agg


def build_shift_productivity_table_for_subdivision(
    data_sub: pd.DataFrame,
    col_field: str,
    col_order: Sequence[Any],
    inv_col: str,
) -> pd.DataFrame:
    """Промежуточный итог по марке = сумма среднесменных по инвентарным номерам.

    Итог по подразделению = сумма всех среднесменных по инвентарным номерам.
    """
    detail = aggregate_shift_productivity(data_sub, ["Марка машины", inv_col, col_field])
    detail_pivot = detail.pivot(
        index=["Марка машины", inv_col],
        columns=col_field,
        values="Среднесменная производительность",
    )

    existing_cols = [c for c in col_order if c in detail_pivot.columns]
    detail_pivot = detail_pivot.reindex(columns=existing_cols)

    brand_pivot = detail_pivot.groupby(level=0).sum(min_count=1)
    total_row = detail_pivot.sum(axis=0, min_count=1)

    rows: list[dict[str, Any]] = []
    for brand in sorted(brand_pivot.index):
        brand_vals = brand_pivot.loc[brand]
        row = {"Марка / Инв. №": brand}
        for c in existing_cols:
            row[c] = brand_vals.get(c, pd.NA)
        rows.append(row)

        inv_rows = sorted((idx for idx in detail_pivot.index if idx[0] == brand), key=lambda x: str(x[1]))
        for _, inv_num in inv_rows:
            vals = detail_pivot.loc[(brand, inv_num)]
            row = {"Марка / Инв. №": f"    {inv_num}"}
            for c in existing_cols:
                row[c] = vals.get(c, pd.NA)
            rows.append(row)

    total_dict = {"Марка / Инв. №": "Всего"}
    for c in existing_cols:
        total_dict[c] = total_row.get(c, pd.NA)
    rows.append(total_dict)
    return pd.DataFrame(rows)


def build_shift_productivity_tables_by_subdivision(processor: OpiProcessor) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    df = prepare_base_df(processor)
    inv_col = detect_inventory_column(df.columns)

    df["Подразделение"] = df["Подразделение"].astype(str).str.strip()
    df["Марка машины"] = df["Марка машины"].astype(str).str.strip()
    df[inv_col] = df[inv_col].astype(str).str.strip()
    df["ПланФакт_norm"] = df["План / Факт"].astype(str).str.strip().str.lower()
    df["Год_даты"] = df["Дата"].dt.year
    df["Передел_для_анализа"] = df["Передел"].apply(combine_torf_peredel)

    df = df[
        df["Передел_для_анализа"].notna() &
        df["Дата"].notna() &
        df["Объем работ, скорректированный"].notna() &
        (df["Марка машины"] != "") &
        (df["Марка машины"].str.lower() != "nan") &
        (df[inv_col] != "") &
        (df[inv_col].str.lower() != "nan")
    ].copy()

    subdivisions = sorted(df["Подразделение"].dropna().unique())
    tables_by_year: dict[str, pd.DataFrame] = {}
    tables_plan_fact_2026: dict[str, pd.DataFrame] = {}

    for sub in subdivisions:
        sub_df = df[df["Подразделение"] == sub].copy()
        if sub_df.empty:
            continue

        fact_years = cut_to_today_each_year(sub_df[sub_df["ПланФакт_norm"] == "факт"].copy())
        year_order = sorted(fact_years["Год_даты"].dropna().unique())
        if year_order:
            tables_by_year[sub] = build_shift_productivity_table_for_subdivision(
                fact_years,
                col_field="Год_даты",
                col_order=year_order,
                inv_col=inv_col,
            )

        pf_2026 = cut_to_today_each_year(
            sub_df[(sub_df["Год_даты"] == 2026) & (sub_df["ПланФакт_norm"].isin(["план", "факт"]))].copy()
        )
        if not pf_2026.empty:
            pf_2026["Сценарий"] = pf_2026["ПланФакт_norm"].map({"план": "План 2026", "факт": "Факт 2026"})
            tables_plan_fact_2026[sub] = build_shift_productivity_table_for_subdivision(
                pf_2026,
                col_field="Сценарий",
                col_order=["План 2026", "Факт 2026"],
                inv_col=inv_col,
            )

    return tables_by_year, tables_plan_fact_2026


# -----------------------------
# План / факт по блокам и переделам
# -----------------------------

def build_plan_fact_table_for_subdivision(data_sub: pd.DataFrame) -> pd.DataFrame:
    detail = data_sub.groupby(["Блок", "Передел", "Сценарий"], as_index=False)["Объем работ, скорректированный"].sum()
    detail_pivot = detail.pivot(index=["Блок", "Передел"], columns="Сценарий", values="Объем работ, скорректированный")
    block_pivot = detail_pivot.groupby(level=0).sum(min_count=1)
    total_row = detail_pivot.sum(axis=0, min_count=1)

    col_order = ["План 2026", "Факт 2026"]
    existing_cols = [c for c in col_order if c in detail_pivot.columns]
    detail_pivot = detail_pivot.reindex(columns=existing_cols)
    block_pivot = block_pivot.reindex(columns=existing_cols)
    total_row = total_row.reindex(existing_cols)

    rows: list[dict[str, Any]] = []
    for block in sorted(block_pivot.index):
        block_vals = block_pivot.loc[block]
        row = {"Блок / Передел": block}
        for c in existing_cols:
            row[c] = block_vals.get(c, pd.NA)
        rows.append(row)

        peredel_rows = sorted((idx for idx in detail_pivot.index if idx[0] == block), key=lambda x: str(x[1]))
        for _, peredel in peredel_rows:
            vals = detail_pivot.loc[(block, peredel)]
            row = {"Блок / Передел": f"    {peredel}"}
            for c in existing_cols:
                row[c] = vals.get(c, pd.NA)
            rows.append(row)

    total_dict = {"Блок / Передел": "Всего"}
    for c in existing_cols:
        total_dict[c] = total_row.get(c, pd.NA)
    rows.append(total_dict)
    return pd.DataFrame(rows)


def build_plan_fact_block_tables_by_subdivision(
    processor: OpiProcessor,
    excluded_peredels: Sequence[str] = DEFAULT_EXCLUDED_PEREDELS,
) -> dict[str, pd.DataFrame]:
    df = prepare_base_df(processor)
    df["Подразделение"] = df["Подразделение"].astype(str).str.strip()
    df["Блок"] = df["Блок"].astype(str).str.strip()
    df["Передел"] = df["Передел"].astype(str).str.strip()
    df["ПланФакт_norm"] = df["План / Факт"].astype(str).str.strip().str.lower()
    df["Год_даты"] = df["Дата"].dt.year

    df = df[~df["Передел"].isin(list(excluded_peredels))].copy()
    df = df[
        df["Дата"].notna() &
        df["Объем работ, скорректированный"].notna() &
        (df["Подразделение"] != "") &
        (df["Блок"] != "") &
        (df["Передел"] != "")
    ].copy()

    df_2026 = cut_to_today_each_year(
        df[(df["Год_даты"] == 2026) & (df["ПланФакт_norm"].isin(["план", "факт"]))].copy()
    )
    df_2026["Сценарий"] = df_2026["ПланФакт_norm"].map({"план": "План 2026", "факт": "Факт 2026"})

    subdivisions = sorted(df_2026["Подразделение"].dropna().unique())
    return {
        sub: build_plan_fact_table_for_subdivision(df_2026[df_2026["Подразделение"] == sub].copy())
        for sub in subdivisions
    }


# -----------------------------
# Пример запуска из консоли
# -----------------------------

def build_default_processor(df_path: str, sheet_name: str = "Реестр") -> OpiProcessor:
    return OpiProcessor(df_path=df_path, sheet_name=sheet_name).load_data().prepare(
        numeric_columns={"Объём работ": 0, "k, маркзамера": 1}
    )


if __name__ == "__main__":
    example_path = r"C:\Users\poisk-12\Documents\$Мониторинг\Сводный наблюдатель оперативной информации (PowerQuery).xlsb"
    processor = build_default_processor(example_path)


