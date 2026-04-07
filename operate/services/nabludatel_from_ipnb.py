#%%
# Быстрый запуск без повторной загрузки при смене условий.
# Требуется: pip install pyxlsb  (для .xlsb)

import pandas as pd
from pathlib import Path
from datetime import datetime
import glob
import numpy as np

class OpiProcessor:
    def __init__(self, df_path: str, sheet_name: str = "Реестр"):
        self.file_path = Path(df_path)
        self.sheet_name = sheet_name
        self.df: pd.DataFrame | None = None        # сырой DataFrame (читаетcя 1 раз)
        self.df_ready: pd.DataFrame | None = None  # подготовленный (после prepare)
        self.df_filtered: pd.DataFrame | None = None

    # ── 1) Загрузка: читаем только один раз ────────────────────────────
    def load_data(self, force: bool = False, usecols=None):
        if self.df is not None and not force:
            return self
        engine = "pyxlsb" if self.file_path.suffix.lower() == ".xlsb" else None
        self.df = pd.read_excel(self.file_path, sheet_name=self.sheet_name,
                                engine=engine, usecols=usecols)
        self._convert_date("Дата")
        return self

    # Робастная конвертация дат (Excel serial / UNIX / строки)
    def _convert_date(self, date_col: str = "Дата"):
        if date_col not in (self.df.columns if self.df is not None else []):
            return
        s = self.df[date_col]
        if pd.api.types.is_datetime64_any_dtype(s):
            return
        if pd.api.types.is_numeric_dtype(s):
            x = pd.to_numeric(s, errors="coerce")
            x_valid = x[np.isfinite(x)]
            if not x_valid.empty:
                xmin, xmax = float(x_valid.min()), float(x_valid.max())
                # Excel serial дни
                if (1e4 <= xmin <= 1e5) and (1e4 <= xmax <= 1e5) or xmax < 1e6:
                    self.df[date_col] = pd.to_datetime("1899-12-30") + pd.to_timedelta(x, unit="D"); return
                # UNIX эпоха
                if 1e9 <= xmin <= 2e10:
                    self.df[date_col] = pd.to_datetime(x, unit="s", errors="coerce"); return
                if 1e12 <= xmin <= 2e13:
                    self.df[date_col] = pd.to_datetime(x, unit="ms", errors="coerce"); return
                if 1e15 <= xmin <= 2e16:
                    self.df[date_col] = pd.to_datetime(x, unit="us", errors="coerce"); return
                if 1e18 <= xmin <= 2e19:
                    self.df[date_col] = pd.to_datetime(x, unit="ns", errors="coerce"); return
        # как строки
        self.df[date_col] = pd.to_datetime(s, errors="coerce", dayfirst=True, infer_datetime_format=True)

    # ── 2) Подготовка: делаем один раз, далее переиспользуем ───────────
    def prepare(self,
                numeric_columns: dict | None = None,
                volume_col="Объём работ",
                coeff_col="k, маркзамера",
                result_col="Объем работ, скорректированный",
                add_month: bool = True):
        if self.df is None:
            raise RuntimeError("Сначала вызовите load_data().")
        d = self.df.copy()

        # числовая чистка
        if numeric_columns:
            for col, default in numeric_columns.items():
                if col in d.columns:
                    d[col] = (
                        d[col].astype(str)
                        .str.replace(",", ".", regex=False)
                        .str.replace(r"[^\d\.\-eE]", "", regex=True)
                        .replace("", pd.NA)
                        .apply(pd.to_numeric, errors="coerce")
                        .fillna(default)
                    )

        # расчёт скорректированного объёма
        if volume_col in d.columns and coeff_col in d.columns:
            d[result_col] = d[volume_col] * d[coeff_col]

        # колонка «Месяц» по-русски
        if add_month and "Дата" in d.columns:
            months = {1:"Январь",2:"Февраль",3:"Март",4:"Апрель",5:"Май",6:"Июнь",
                      7:"Июль",8:"Август",9:"Сентябрь",10:"Октябрь",11:"Ноябрь",12:"Декабрь"}
            d["Дата"] = pd.to_datetime(d["Дата"], errors="coerce")
            d["Месяц"] = d["Дата"].dt.month.map(months)

        self.df_ready = d
        return self

    # ── 3) Фильтрация: много раз, не трогая df/df_ready ────────────────
    @staticmethod
    def _norm_text(x) -> str:
        return str(x).strip()

    @staticmethod
    def _norm_object_name(x) -> str:
        # разные дефисы и неразрывные пробелы → обычные
        return str(x).replace("—","-").replace("–","-").replace("\u00A0"," ").strip()

    def filter_by_conditions(self, field_conditions: dict, positive_col: str | None = "Объем работ, скорректированный"):
        if self.df_ready is None:
            # если забыли вызвать prepare(), используем сырой df
            src = self.df.copy()
        else:
            src = self.df_ready.copy()

        df_filtered = src

        for col, value in field_conditions.items():
            if col not in df_filtered.columns:
                continue

            col_for_filter = col
            norm_val = value

            # нормализация текстовых полей
            if pd.api.types.is_string_dtype(df_filtered[col].dtype):
                df_filtered[col] = df_filtered[col].astype(str).str.strip()

            # специальная нормализация для "Месторождение, объект"
            if col == "Месторождение, объект":
                tmp = "__obj_norm__"
                df_filtered[tmp] = df_filtered[col].map(self._norm_object_name)
                col_for_filter = tmp
                if isinstance(value, (list, set, tuple)):
                    norm_val = [self._norm_object_name(v) for v in value]
                else:
                    norm_val = self._norm_object_name(value)

            # диапазон (2 значения дат или чисел)
            if isinstance(norm_val, (list, tuple)) and len(norm_val) == 2 and (
                all(isinstance(x, (pd.Timestamp, datetime, np.datetime64)) for x in norm_val) or
                all(isinstance(x, (int, float, np.number)) for x in norm_val)
            ):
                a, b = norm_val
                if any(isinstance(x, (pd.Timestamp, datetime, np.datetime64)) for x in (a, b)):
                    df_filtered[col_for_filter] = pd.to_datetime(df_filtered[col_for_filter], errors="coerce")
                    a = pd.to_datetime(a); b = pd.to_datetime(b)
                df_filtered = df_filtered[(df_filtered[col_for_filter] >= a) & (df_filtered[col_for_filter] <= b)]
            # IN-список
            elif isinstance(norm_val, (list, set, tuple)):
                df_filtered = df_filtered[df_filtered[col_for_filter].isin(list(norm_val))]
            # точное равенство
            else:
                df_filtered = df_filtered[df_filtered[col_for_filter] == norm_val]

            if col_for_filter == "__obj_norm__" and "__obj_norm__" in df_filtered.columns:
                df_filtered = df_filtered.drop(columns="__obj_norm__")

        if positive_col and positive_col in df_filtered.columns:
            df_filtered = df_filtered[df_filtered[positive_col] > 0]

        self.df_filtered = df_filtered
        return self

    # ── 4) Сводная + быстрый интерфейс pivot_for ──────────────────────
    def get_pivot_table(self, index, columns, values="Объем работ, скорректированный"):
        if self.df_filtered is None:
            raise RuntimeError("Сначала вызовите filter_by_conditions(...).")
        return self.df_filtered.pivot_table(index=index, columns=columns, values=values,
                                            aggfunc="sum", fill_value=0).reset_index()

    def pivot_for(self, conditions, index, columns, values="Объем работ, скорректированный"):
        # удобный метод: фильтр → свод
        return (self.filter_by_conditions(conditions)
                    .get_pivot_table(index=index, columns=columns, values=values))

    # ── экспорт ────────────────────────────────────────────────────────
    def export_to_excel(self, df, file_name: str):
        Path(file_name).parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(file_name, index=False)





#%%
# ====== ПРИМЕР ИСПОЛЬЗОВАНИЯ ======
#df_path = '/Users/alexei/Documents/Мониторинг/Сводный наблюдатель оперативной информации (PowerQuery).xlsb'
df_path = r'C:\Users\poisk-12\Documents\$Мониторинг\Сводный наблюдатель оперативной информации (PowerQuery).xlsb'
#создание объекта
processor = (OpiProcessor(df_path)
             .load_data()  # читаем один раз
             .prepare(numeric_columns={"Объём работ": 0, "k, маркзамера": 1}))

#%%
processor.df.loc[
    (processor.df['План / Факт']=='Факт') &
    (processor.df["Год"]==2026),
    "Подразделение"].unique()
#%%
# Меняйте условия — файл больше не перечитывается:
pivot = processor.pivot_for(
    conditions={
        "Подразделение": 'Дражный',        # ← было «Подраздление» (опечатка)
        "Год": 2026,
        "Год операции": 2026,
        "План / Факт": "Факт",
        "Дата": (datetime(2025, 9, 28 ), datetime(2025, 9, 29)),   # диапазон
    },
    index=["Подразделение", "Блок", "Передел"],
    columns="Дата"   # можно заменить на "Месяц"
)

# processor.export_to_excel(pivot, "pivot_hch.xlsx")


# Экспорт результата
#processor.export_to_excel(pivot, "pivot_hch.xlsx")
#%%
pivot_teh = processor.pivot_for(
    conditions={
        "Подразделение": 'Дражный',        # ← было «Подраздление» (опечатка)
        "Год": 2026,
        #"Год операции": 2026,
        "План / Факт": "Факт",
        "Дата": (datetime(2026, 3, 1), datetime(2026, 4, 7)),   # диапазон
    },
    index=["Подразделение",  "Передел","Марка машины", "Блок", "Инв. №"],
    columns="Дата"   # можно заменить на "Месяц"
)
#%%

pivot_teh
#%%

#%%
#!pip install plotly

#%%
import plotly.express as px


value_vars = [col for col in pivot_teh.columns if col not in ["Блок", "Передел", "Марка машины", "Инв. №"]]

# Преобразуем pivot в формат long для Plotly
pivot_long = pivot_teh.melt(
    id_vars=["Блок", "Передел","Марка машины", "Инв. №"],
    value_vars=value_vars,
    var_name="Дата",
    value_name="Объём"
)

# Построим stacked bar chart
fig = px.bar(
    pivot_long,
    x="Блок",
    y="Объём",
    color="Передел",  # можно сменить на "Блок" или "Месторождение, объект"
    hover_data=["Передел", "Марка машины", "Инв. №"],
    title="Объём работ по месяцам (интерактивный график)",
    barmode="stack"
)

fig.update_layout(xaxis={'categoryorder':'category ascending'})
fig.show()

#%%
# Те колонки, которые реально есть в pivot_teh
id_cols = ["Подразделение", "Передел", "Марка машины"]

# Берём только дата-колонки
value_vars = [col for col in pivot_teh.columns if col not in id_cols]

pivot_long = pivot_teh.melt(
    id_vars=id_cols,
    value_vars=value_vars,
    var_name="Дата",
    value_name="Объём"
)

pivot_long["Дата"] = pd.to_datetime(pivot_long["Дата"], errors="coerce")
pivot_long["Объём"] = pd.to_numeric(pivot_long["Объём"], errors="coerce")
pivot_long = pivot_long.dropna(subset=["Дата", "Объём"])

# Сумма по датам и переделам
plot_df = (
    pivot_long
    .groupby(["Дата", "Передел"], as_index=False)["Объём"]
    .sum()
)

fig = px.bar(
    plot_df,
    x="Дата",
    y="Объём",
    color="Передел",
    title="Объём работ по датам",
    barmode="stack"
)

fig.update_layout(
    xaxis_title="Дата",
    yaxis_title="Объём",
    xaxis_tickformat="%d.%m.%Y"
)

fig.show()
#%%
import pandas as pd
import plotly.express as px

SUBDIVISION = "Дражный"
TODAY = pd.Timestamp.today().normalize()

# -----------------------------
# Объединяем нужные переделы в один
# -----------------------------
def combine_peredel(x):
    s = str(x).strip().lower()

    if (
        ("вскрыша торфов" in s and "экскаватор" in s) or
        ("вскрыша торфов" in s and "бульдозер" in s) or
        ("погрузка торфов" in s)
    ):
        return "Торфы (объединено)"

    return None

def cut_to_today_each_year(df, date_col="Дата", ref_date=TODAY):
    m = ref_date.month
    d = ref_date.day
    return df[
        (df[date_col].dt.month < m) |
        ((df[date_col].dt.month == m) & (df[date_col].dt.day <= d))
    ].copy()

def add_inyear_axis(df, date_col="Дата", new_col="Дата_внутри_года"):
    mmdd = df[date_col].dt.strftime("%m-%d")
    df[new_col] = pd.to_datetime("2000-" + mmdd, format="%Y-%m-%d", errors="coerce")
    return df

# -----------------------------
# База
# -----------------------------
df = processor.df_ready.copy()

df["Дата"] = pd.to_datetime(df["Дата"], errors="coerce")
df["Объем работ, скорректированный"] = pd.to_numeric(
    df["Объем работ, скорректированный"], errors="coerce"
)

df = df.dropna(subset=["Дата", "Объем работ, скорректированный"]).copy()

df["Передел_для_графика"] = df["Передел"].apply(combine_peredel)
df["ПланФакт_norm"] = df["План / Факт"].astype(str).str.strip().str.lower()
df["Год_даты"] = df["Дата"].dt.year

df = df[
    (df["Подразделение"].astype(str).str.strip() == SUBDIVISION) &
    (df["Передел_для_графика"].notna())
].copy()

# =========================================================
# 1. Факт по годам на текущую дату
# =========================================================
fact = df[df["ПланФакт_norm"] == "факт"].copy()
fact = cut_to_today_each_year(fact)

fact_daily = (
    fact.groupby(["Год_даты", "Дата"], as_index=False)["Объем работ, скорректированный"]
    .sum()
)

fact_daily = add_inyear_axis(fact_daily)
fact_daily = fact_daily.dropna(subset=["Дата_внутри_года"]).copy()
fact_daily = fact_daily.sort_values(["Год_даты", "Дата_внутри_года"])

fact_daily["Накопленный объём"] = (
    fact_daily.groupby("Год_даты")["Объем работ, скорректированный"]
    .cumsum()
)

fig1 = px.line(
    fact_daily,
    x="Дата_внутри_года",
    y="Накопленный объём",
    color="Год_даты",
    title="Торфы: накопленный факт по годам на текущую дату"
)

fig1.update_layout(
    xaxis_title="Дата",
    yaxis_title="Накопленный объём",
    legend_title_text="Год"
)

fig1.update_xaxes(tickformat="%d.%m")
fig1.show()

# =========================================================
# 2. Сравнение факт 2026 vs план 2026
# =========================================================
plan_fact_2026 = df[
    (df["Год_даты"] == 2026) &
    (df["ПланФакт_norm"].isin(["факт", "план"]))
].copy()

plan_fact_2026 = cut_to_today_each_year(plan_fact_2026)

plan_fact_2026["Сценарий"] = plan_fact_2026["ПланФакт_norm"].map({
    "факт": "Факт 2026",
    "план": "План 2026"
})

pf_daily = (
    plan_fact_2026.groupby(["Сценарий", "Дата"], as_index=False)["Объем работ, скорректированный"]
    .sum()
)

pf_daily = pf_daily.sort_values(["Сценарий", "Дата"])

pf_daily["Накопленный объём"] = (
    pf_daily.groupby("Сценарий")["Объем работ, скорректированный"]
    .cumsum()
)

fig2 = px.line(
    pf_daily,
    x="Дата",
    y="Накопленный объём",
    color="Сценарий",
    line_dash="Сценарий",
    title="Торфы: факт 2026 vs план 2026"
)

fig2.update_layout(
    xaxis_title="Дата",
    yaxis_title="Накопленный объём",
    legend_title_text="Сценарий"
)

fig2.update_xaxes(tickformat="%d.%m")
fig2.show()
#%%
from IPython.display import display, Markdown

TODAY = pd.Timestamp.today().normalize()

# -------------------------------------------------
# Объединяем нужные переделы в один
# -------------------------------------------------
def combine_peredel(x):
    s = str(x).strip().lower()

    if (
        ("вскрыша торфов" in s and "экскаватор" in s) or
        ("вскрыша торфов" in s and "бульдозер" in s) or
        ("погрузка торфов" in s)
    ):
        return "Торфы (объединено)"

    return None


# -------------------------------------------------
# Обрезка каждого года по текущую дату
# -------------------------------------------------
def cut_to_today_each_year(df, date_col="Дата", ref_date=TODAY):
    m = ref_date.month
    d = ref_date.day

    return df[
        (df[date_col].dt.month < m) |
        ((df[date_col].dt.month == m) & (df[date_col].dt.day <= d))
    ].copy()


# -------------------------------------------------
# Поиск колонки инвентарного номера
# -------------------------------------------------
def detect_inventory_column(columns):
    candidates = ["Инв. №", "Инв№", "Инв.№", "Инв №"]
    for c in candidates:
        if c in columns:
            return c
    raise KeyError(
        f"Не найдена колонка инвентарного номера. Доступные колонки: {list(columns)}"
    )


# -------------------------------------------------
# Подготовка базы
# -------------------------------------------------
df = processor.df_ready.copy()

INV_COL = detect_inventory_column(df.columns)

df["Дата"] = pd.to_datetime(df["Дата"], errors="coerce")
df["Объем работ, скорректированный"] = pd.to_numeric(
    df["Объем работ, скорректированный"], errors="coerce"
)

df["Подразделение"] = df["Подразделение"].astype(str).str.strip()
df["Марка машины"] = df["Марка машины"].astype(str).str.strip()
df[INV_COL] = df[INV_COL].astype(str).str.strip()
df["ПланФакт_norm"] = df["План / Факт"].astype(str).str.strip().str.lower()
df["Год_даты"] = df["Дата"].dt.year
df["Передел_для_анализа"] = df["Передел"].apply(combine_peredel)

df = df[
    df["Передел_для_анализа"].notna() &
    df["Дата"].notna() &
    df["Объем работ, скорректированный"].notna() &
    (df["Марка машины"] != "") &
    (df["Марка машины"].str.lower() != "nan") &
    (df[INV_COL] != "") &
    (df[INV_COL].str.lower() != "nan")
].copy()


# -------------------------------------------------
# Среднесменная производительность
# Логика:
# 1 строка = 1 смена
# -------------------------------------------------
def aggregate_shift_productivity(data, group_cols):
    agg = (
        data.groupby(group_cols, as_index=False)
        .agg(
            Объем_итого=("Объем работ, скорректированный", "sum"),
            Смен=("Объем работ, скорректированный", "size")
        )
    )

    agg["Среднесменная производительность"] = agg["Объем_итого"] / agg["Смен"]
    return agg


# -------------------------------------------------
# Таблица по одному подразделению:
# строки = Марка машины -> Инв. №
# колонки = годы или сценарии
# + строка "Всего"
# -------------------------------------------------
def build_table_for_subdivision(data_sub, col_field, col_order, inv_col):
    # 1. Считаем ТОЛЬКО детально по инвентарным номерам
    detail = aggregate_shift_productivity(data_sub, ["Марка машины", inv_col, col_field])

    detail_pivot = detail.pivot(
        index=["Марка машины", inv_col],
        columns=col_field,
        values="Среднесменная производительность"
    )

    existing_cols = [c for c in col_order if c in detail_pivot.columns]
    detail_pivot = detail_pivot.reindex(columns=existing_cols)

    # 2. Промежуточный итог по марке =
    # сумма среднесменных по инвентарным номерам этой марки
    brand_pivot = detail_pivot.groupby(level=0).sum(min_count=1)

    # 3. Итог по подразделению =
    # сумма всех среднесменных по всем инвентарным номерам
    total_row = detail_pivot.sum(axis=0, min_count=1)

    rows = []

    for brand in sorted(brand_pivot.index):
        # строка марки
        brand_vals = brand_pivot.loc[brand]
        row = {"Марка / Инв. №": brand}
        for c in existing_cols:
            row[c] = brand_vals.get(c, pd.NA)
        rows.append(row)

        # строки инвентарных номеров этой марки
        inv_rows = [idx for idx in detail_pivot.index if idx[0] == brand]
        inv_rows = sorted(inv_rows, key=lambda x: str(x[1]))

        for _, inv_num in inv_rows:
            vals = detail_pivot.loc[(brand, inv_num)]
            row = {"Марка / Инв. №": f"    {inv_num}"}
            for c in existing_cols:
                row[c] = vals.get(c, pd.NA)
            rows.append(row)

    # строка "Всего" по подразделению
    total_dict = {"Марка / Инв. №": "Всего"}
    for c in existing_cols:
        total_dict[c] = total_row.get(c, pd.NA)
    rows.append(total_dict)

    result = pd.DataFrame(rows)
    return result

# -------------------------------------------------
# Формирование таблиц по всем подразделениям
# -------------------------------------------------
subdivisions = sorted(df["Подразделение"].dropna().unique())

tables_by_year = {}
tables_plan_fact_2026 = {}

for sub in subdivisions:
    sub_df = df[df["Подразделение"] == sub].copy()

    if sub_df.empty:
        continue

    # 1. Факт по годам на текущую дату
    fact_years = sub_df[sub_df["ПланФакт_norm"] == "факт"].copy()
    fact_years = cut_to_today_each_year(fact_years)

    year_order = sorted(fact_years["Год_даты"].dropna().unique())

    if len(year_order) > 0:
        table_years = build_table_for_subdivision(
            fact_years,
            col_field="Год_даты",
            col_order=year_order,
            inv_col=INV_COL
        )
        tables_by_year[sub] = table_years

    # 2. План 2026 vs Факт 2026
    pf_2026 = sub_df[
        (sub_df["Год_даты"] == 2026) &
        (sub_df["ПланФакт_norm"].isin(["план", "факт"]))
    ].copy()

    pf_2026 = cut_to_today_each_year(pf_2026)

    if not pf_2026.empty:
        pf_2026["Сценарий"] = pf_2026["ПланФакт_norm"].map({
            "план": "План 2026",
            "факт": "Факт 2026"
        })

        table_pf = build_table_for_subdivision(
            pf_2026,
            col_field="Сценарий",
            col_order=["План 2026", "Факт 2026"],
            inv_col=INV_COL
        )
        tables_plan_fact_2026[sub] = table_pf


# -------------------------------------------------
# Вывод таблиц
# -------------------------------------------------
for sub in subdivisions:
    display(Markdown(f"## Подразделение: {sub}"))

    if sub in tables_by_year:
        display(Markdown("### Среднесменная производительность — факт по годам на текущую дату"))
        display(
            tables_by_year[sub].style.format(
                {
                    col: "{:,.2f}".format
                    for col in tables_by_year[sub].columns
                    if col != "Марка / Инв. №"
                },
                na_rep="-"
            )
        )
    else:
        print("Нет данных для таблицы по годам.")

    if sub in tables_plan_fact_2026:
        display(Markdown("### Среднесменная производительность — План 2026 vs Факт 2026"))
        display(
            tables_plan_fact_2026[sub].style.format(
                {
                    col: "{:,.2f}".format
                    for col in tables_plan_fact_2026[sub].columns
                    if col != "Марка / Инв. №"
                },
                na_rep="-"
            )
        )
    else:
        print("Нет данных для таблицы План 2026 / Факт 2026.")
#%%


# -------------------------------------------------
# Обрезка каждого года по текущую дату
# -------------------------------------------------

TODAY = pd.Timestamp.today().normalize()

def cut_to_today_each_year(df, date_col="Дата", ref_date=TODAY):
    m = ref_date.month
    d = ref_date.day

    return df[
        (df[date_col].dt.month < m) |
        ((df[date_col].dt.month == m) & (df[date_col].dt.day <= d))
    ].copy()

# -------------------------------------------------
# Подготовка базы
# -------------------------------------------------
df = processor.df_ready.copy()

df["Дата"] = pd.to_datetime(df["Дата"], errors="coerce")
df["Объем работ, скорректированный"] = pd.to_numeric(
    df["Объем работ, скорректированный"], errors="coerce"
)

# ВОТ СЮДА СТАВИШЬ СВОЙ БЛОК
df["Подразделение"] = df["Подразделение"].astype(str).str.strip()
df["Блок"] = df["Блок"].astype(str).str.strip()
df["Передел"] = df["Передел"].astype(str).str.strip()
df["ПланФакт_norm"] = df["План / Факт"].astype(str).str.strip().str.lower()
df["Год_даты"] = df["Дата"].dt.year

excluded_peredels = [
    "Бурение взрывных скважин, м3",
    "МВ"
]

df = df[~df["Передел"].isin(excluded_peredels)].copy()

df = df[
    df["Дата"].notna() &
    df["Объем работ, скорректированный"].notna() &
    (df["Подразделение"] != "") &
    (df["Блок"] != "") &
    (df["Передел"] != "")
].copy()

# -------------------------------------------------
# Только 2026 и только план / факт
# -------------------------------------------------
df_2026 = df[
    (df["Год_даты"] == 2026) &
    (df["ПланФакт_norm"].isin(["план", "факт"]))
].copy()

# накопительно на сегодняшнюю дату
df_2026 = cut_to_today_each_year(df_2026)

df_2026["Сценарий"] = df_2026["ПланФакт_norm"].map({
    "план": "План 2026",
    "факт": "Факт 2026"
})

# -------------------------------------------------
# Функция таблицы по одному подразделению
# блок -> передел
# -------------------------------------------------
def build_plan_fact_table_for_subdivision(data_sub):
    # детально по переделам
    detail = (
        data_sub.groupby(["Блок", "Передел", "Сценарий"], as_index=False)["Объем работ, скорректированный"]
        .sum()
    )

    detail_pivot = detail.pivot(
        index=["Блок", "Передел"],
        columns="Сценарий",
        values="Объем работ, скорректированный"
    )

    # итог по блоку = сумма переделов
    block_pivot = detail_pivot.groupby(level=0).sum(min_count=1)

    # итог по подразделению
    total_row = detail_pivot.sum(axis=0, min_count=1)

    col_order = ["План 2026", "Факт 2026"]
    existing_cols = [c for c in col_order if c in detail_pivot.columns]

    detail_pivot = detail_pivot.reindex(columns=existing_cols)
    block_pivot = block_pivot.reindex(columns=existing_cols)
    total_row = total_row.reindex(existing_cols)

    rows = []

    for block in sorted(block_pivot.index):
        # строка блока
        block_vals = block_pivot.loc[block]
        row = {"Блок / Передел": block}
        for c in existing_cols:
            row[c] = block_vals.get(c, pd.NA)
        rows.append(row)

        # строки переделов внутри блока
        peredel_rows = [idx for idx in detail_pivot.index if idx[0] == block]
        peredel_rows = sorted(peredel_rows, key=lambda x: str(x[1]))

        for _, peredel in peredel_rows:
            vals = detail_pivot.loc[(block, peredel)]
            row = {"Блок / Передел": f"    {peredel}"}
            for c in existing_cols:
                row[c] = vals.get(c, pd.NA)
            rows.append(row)

    # строка всего
    total_dict = {"Блок / Передел": "Всего"}
    for c in existing_cols:
        total_dict[c] = total_row.get(c, pd.NA)
    rows.append(total_dict)

    return pd.DataFrame(rows)


# -------------------------------------------------
# Формирование таблиц по подразделениям
# -------------------------------------------------
subdivisions = sorted(df_2026["Подразделение"].dropna().unique())

tables_plan_fact = {}

for sub in subdivisions:
    sub_df = df_2026[df_2026["Подразделение"] == sub].copy()
    if not sub_df.empty:
        tables_plan_fact[sub] = build_plan_fact_table_for_subdivision(sub_df)


# -------------------------------------------------
# Вывод
# -------------------------------------------------
for sub in subdivisions:
    display(Markdown(f"## Подразделение: {sub}"))

    if sub in tables_plan_fact:
        display(
            tables_plan_fact[sub].style.format(
                {
                    col: "{:,.2f}".format
                    for col in tables_plan_fact[sub].columns
                    if col != "Блок / Передел"
                },
                na_rep="-"
            )
        )
    else:
        print("Нет данных.")
#%%
