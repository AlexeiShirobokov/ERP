import re
import warnings

import numpy as np
import pandas as pd

from maintenance.models import AggregateJournalRow
from Services.planto_rules import get_maintenance_dicts


pd.set_option("display.max_rows", 10)
pd.set_option("display.max_columns", 10)
pd.set_option("display.precision", 100)


RULE_STEP = 20
PLAN_DAYS = 30
PLAN_END_DATE = pd.Timestamp("2026-10-01")


def load_aggregate_journal_from_db():
    qs = AggregateJournalRow.objects.all().values(
        "department",
        "machine_brand",
        "modification",
        "inventory_number",
        "maintenance_start_date",
        "maintenance_end_date",
        "actual_hours_at_maintenance",
        "machine_hours",
        "maintenance_type",
    )

    rows = list(qs)
    if not rows:
        return pd.DataFrame(
            columns=[
                "Подразделение",
                "Марка",
                "Модификация",
                "Инвентарный номер",
                "Дата начала обслуживания",
                "Дата окончания обслуживания",
                "Фактическая наработка в момент проведения ТО",
                "Наработка машины",
                "Вид ТО",
            ]
        )

    df = pd.DataFrame(rows).rename(
        columns={
            "department": "Подразделение",
            "machine_brand": "Марка",
            "modification": "Модификация",
            "inventory_number": "Инвентарный номер",
            "maintenance_start_date": "Дата начала обслуживания",
            "maintenance_end_date": "Дата окончания обслуживания",
            "actual_hours_at_maintenance": "Фактическая наработка в момент проведения ТО",
            "machine_hours": "Наработка машины",
            "maintenance_type": "Вид ТО",
        }
    )

    for col in ["Дата начала обслуживания", "Дата окончания обслуживания"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    for col in ["Подразделение", "Марка", "Модификация", "Инвентарный номер", "Вид ТО"]:
        df[col] = df[col].fillna("").astype(str).str.strip()

    return df


def _inventory_mask(series: pd.Series, targets) -> pd.Series:
    targets = [str(x) for x in targets]
    pattern = rf"(?<!\d)(?:{'|'.join(map(re.escape, targets))})(?!\d)"
    return series.astype(str).str.contains(pattern, na=False, regex=True)


def _normalize_inventory_number(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace("\xa0", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
        .str.replace(r"\D+", "", regex=True)
        .replace("", pd.NA)
    )
    return pd.to_numeric(cleaned, errors="coerce").astype("Int64")


def _prepare_source_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()
    df["Дата начала обслуживания"] = pd.to_datetime(df["Дата начала обслуживания"], errors="coerce")
    df["Месяц_ном"] = df["Дата начала обслуживания"].dt.month
    df["Год"] = df["Дата начала обслуживания"].dt.year
    df = df.loc[df["Год"] >= 2025].copy()

    inventory_brand_rules = [
        (["1288", "1289", "1290", "1310"], "CLG975F"),
        (["1251", "1252"], "CLG942EHD"),
        (["1247", "1249"], "CLG877H"),
        (["1199"], "D55"),
        (["1183"], "SG21A_3"),
        (["1185", "1304"], "SD22"),
        (["702", "703", "704"], "TM10.11 ГСТ10"),
        (["652", "653"], "TM10.11 ГСТ12"),
    ]

    for targets, brand in inventory_brand_rules:
        mask = _inventory_mask(df["Инвентарный номер"], targets)
        df.loc[mask, "Марка"] = brand

    mask = df["Марка"].astype(str).isin(["SHANTUI SG21A-3", "Shantui "])
    df.loc[mask, "Марка"] = "SG21A_3"

    mask = df["Марка"].astype(str).isin(["Shantui SD22", "Shantui SD23"])
    df.loc[mask, "Марка"] = "SD22"

    df["Инвентарный номер"] = _normalize_inventory_number(df["Инвентарный номер"])
    return df


def _get_latest_state(df: pd.DataFrame, start_date: pd.Timestamp) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "Подразделение",
                "Марка",
                "Модификация",
                "Инвентарный номер",
                "Наработка машины",
                "Дата начала обслуживания",
                "Фактическая наработка в момент проведения ТО",
            ]
        )

    idx = df.groupby("Инвентарный номер")["Дата начала обслуживания"].idxmax()
    last_per_inv = df.loc[idx].copy()
    last_per_inv["Модификация"] = last_per_inv["Модификация"].replace("", pd.NA).fillna("1")

    pivot_table = (
        pd.pivot_table(
            last_per_inv,
            values=[
                "Наработка машины",
                "Дата начала обслуживания",
                "Фактическая наработка в момент проведения ТО",
            ],
            index=["Подразделение", "Марка", "Модификация", "Инвентарный номер"],
            aggfunc="first",
        )
        .reset_index()
        .round(2)
        .fillna(0)
    )

    pivot_table["Дата начала обслуживания"] = pd.to_datetime(start_date, errors="coerce")
    return pivot_table


def _apply_launch_dates(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()

    launch_rules = [
        (
            [
                "701", "665", "1251", "1148", "1084", "1156", "661", "658", "1151", "1152",
                "903", "1252", "916", "789", "790", "1185", "597", "675", "603", "691",
                "960", "702", "711", "1288", "678", "688", "1187", "1082", "660", "664",
                "915", "697", "1158", "1157", "1159", "600", "1184",
            ],
            "2026-04-01",
        ),
        (
            ["676", "1078", "466", "965", "690", "1312", "1311", "1153", "1160", "1161", "720", "681", "1247"],
            "2026-05-01",
        ),
        (
            ["1024", "1249", "719", "693"],
            "2026-06-01",
        ),
    ]

    for targets, date_str in launch_rules:
        mask = _inventory_mask(df["Инвентарный номер"], targets)
        df.loc[mask, "Дата начала обслуживания"] = pd.to_datetime(date_str, errors="coerce")

    return df


def _expand_calendar(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()
    df["Дата планирования"] = df["Дата начала обслуживания"] + pd.DateOffset(days=PLAN_DAYS)

    for col in ["Дата начала обслуживания", "Дата планирования"]:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    df = df.dropna(subset=["Дата начала обслуживания", "Дата планирования"])
    df = df[df["Дата планирования"] >= df["Дата начала обслуживания"]].copy()

    n = (df["Дата планирования"] - df["Дата начала обслуживания"]).dt.days + 1
    out = df.loc[df.index.repeat(n)].copy()
    out["__i"] = out.groupby(level=0).cumcount()
    out["Дата"] = out["Дата начала обслуживания"] + pd.to_timedelta(out["__i"], unit="D")
    out = out.drop(columns="__i")
    return out


def _prepare_runtime_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    new_df = df.copy()

    new_df["Наработка машины"] = pd.to_numeric(new_df["Наработка машины"], errors="coerce")
    new_df = new_df.loc[~new_df["Марка"].eq("\xa0 LIUGONG ")].copy()

    new_df["Планируемая наработка в момент проведения ТО"] = new_df["Наработка машины"]
    new_df = new_df[
        ~new_df["Планируемая наработка в момент проведения ТО"].astype(str).isin(
            ["н/д", "Отсутствие показаний", "н/р", "отсутствие показаний", "Н/Р"]
        )
    ].copy()

    new_df["Планируемая наработка в момент проведения ТО"] = (
        pd.to_numeric(new_df["Планируемая наработка в момент проведения ТО"], errors="coerce")
        .fillna(0)
        .astype(int)
    )

    new_df = new_df.reset_index(drop=True)
    new_df["Дата"] = pd.to_datetime(new_df["Дата"], errors="coerce")

    group_cols = ["Подразделение", "Марка", "Модификация", "Инвентарный номер"]
    new_df = new_df.sort_values(group_cols + ["Дата"])

    start = new_df.groupby(group_cols)["Планируемая наработка в момент проведения ТО"].transform("first")
    day_idx = new_df.groupby(group_cols).cumcount()
    new_df["Планируемая наработка в момент проведения ТО"] = start + RULE_STEP * day_idx

    return new_df


def _get_rule(rules: dict, name: str) -> dict:
    rule_map = rules.get(name, {})
    if not isinstance(rule_map, dict):
        return {}
    normalized = {}
    for k, v in rule_map.items():
        try:
            normalized[int(k)] = v
        except Exception:
            continue
    return normalized


def _apply_rule_map(df: pd.DataFrame, base_mask: pd.Series, rule_map: dict) -> None:
    if not base_mask.any() or not rule_map:
        return

    values = pd.to_numeric(df["Планируемая наработка в момент проведения ТО"], errors="coerce")

    for i, label in sorted(rule_map.items()):
        if pd.isna(label) or str(label).strip() == "":
            continue
        mask = base_mask & (((values > i) & (values < i + RULE_STEP)) | (values == i))
        df.loc[mask, "Планируемое техобслуживание"] = label


def _apply_maintenance_rules(df: pd.DataFrame, rules: dict) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()

    rule_specs = [
        ("Марка", ["ДЭС-320", "DCA-500SPK"], "to_dict"),
        ("Модификация", ["320", "200", "220"], "to_dict"),
        ("Модификация", ["60"], "to_DEC60"),
        ("Модификация", ["400"], "to_dict"),
        ("Марка", ["АДД-4004"], "to_ADD_4004"),
        ("Модификация", ["ДНУ-630"], "to_DHU_630_70_GCP"),
        ("Модификация", ["ДНУ-1250/63-ГСП"], "to_DHU_1250_63_GCP"),
        ("Модификация", ["ДНУ-1250/63-ЛП"], "to_DHU_1250_63"),
        ("Марка", ["ДНС-СВ-300-20"], "to_DHC_CB_300_20"),
        ("Модификация", ["ДНС-СВ-32-22"], "to_DHC_CB_320_22"),
        (
            "Модификация",
            ["DNUDo-1600-75 ГСП (Doosan DP158LD) ", "DNUDo-1600-75 ГСП (Doosan DP158LD)", "DNUDO -1600/75"],
            "to_DNUDo_1600",
        ),
        ("Модификация", ["12НДС 1500ГК-01"], "to_12HDC"),
        ("Марка", ["D-375", "D-375A", "Компрессор"], "to_dict"),
        ("Марка", ["D-475"], "to_dict475"),
        ("Марка", ["PC-800", "PC-1250", "PC-750"], "to_dict_PC"),
        ("Марка", ["ZX-870"], "to_dict_ZX"),
        ("Марка", ["HD-465"], "to_dict_HD"),
        ("Марка", ["DM-45"], "to_dict_DM"),
        ("Марка", ["JD-2000"], "to_dict_JD"),
        ("Марка", ["WA-470"], "to_dict_WA470"),
        ("Марка", ["WD-600", "WA-600"], "to_dict_WD"),
        ("Марка", ["TM10.11 ГСТ10", "TM10.11 ГСТ12"], "to_dict_TM"),
        ("Марка", ["ECD50E"], "to_dict_ECD50E"),
        ("Марка", ["БелАЗ"], "to_dict_7547"),
        ("Модификация", ["7555B"], "to_dict_7555"),
        ("Марка", ["TD-16"], "to_dict_TD16"),
        ("Марка", ["D-65"], "to_dict_D65"),
        ("Марка", ["PC-400"], "to_dict_PC400"),
        ("Марка", ["CASE"], "to_dict_case"),
        ("Марка", ["SL50W"], "to_dict_sl"),
        ("Марка", ["Б-11"], "to_dict_b11"),
        ("Марка", ["СБШ-250"], "to_dict_sbh"),
        ("Марка", ["ДНУ-1250/63-ГСП", "ДНУ-630/70-ГСП"], "to_dict_DNU"),
        ("Марка", ["DNUDo-1600/75-ГСП"], "to_dict_DNU_1600"),
        ("Марка", ["DCA-220SPK3", "DCA-500SPK"], "to_dict_DCA"),
        ("Марка", ["АД200С"], "to_dict_DCA_AD200"),
        ("Марка", ["ЭД30Е"], "to_dict_DCA_ED30"),
        ("Марка", ["ЭД200С"], "to_dict_DCA_ED200"),
        ("Марка", ["D55"], "to_dict_D55"),
        ("Марка", ["SD22"], "to_dict_SD22"),
        ("Марка", ["SG21A_3"], "to_dict_SG21A_3"),
        ("Марка", ["CLG975F"], "to_CLG975F"),
        ("Марка", ["CLG877H"], "to_CLG877H"),
        ("Марка", ["CLG942EHD"], "to_CLG942EHD"),
    ]

    for column, values, rule_name in rule_specs:
        rule_map = _get_rule(rules, rule_name)
        if column not in df.columns:
            continue
        base_mask = df[column].isin(values)
        _apply_rule_map(df, base_mask, rule_map)

    return df


def _set_brand_mod(df: pd.DataFrame, mask: pd.Series, brand=None, modification=None) -> None:
    if brand is not None:
        df.loc[mask, "Марка"] = brand
    if modification is not None:
        df.loc[mask, "Модификация"] = modification


def _postprocess_brand_modifications(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()

    replacement_rules = [
        ((df["Марка"] == "Насосная станция") & (df["Модификация"] == "ДНС-СВ-32-22"), "ДНС-СВ", "320-22"),
        ((df["Марка"] == "TM10.11 ГСТ12") & (df["Модификация"] == "1"), "ТМ10.11", "ГСТ12"),
        (df["Марка"] == "АДД-4004", "АДД-4004", "Д-243"),
        (df["Марка"] == "PC-750", "РС 800 8E0", "8"),
        ((df["Марка"] == "ДЭС") & (df["Модификация"] == "320"), "Wilson 320", "2306CE14TAG3"),
        ((df["Марка"] == "ДЭС") & (df["Модификация"] == "400"), "ЭД400", "DC13 072A"),
        ((df["Марка"] == "Компрессор") & (df["Модификация"] == "LUY100-12"), "LUY100-12", "12"),
        ((df["Марка"] == "ДЭС") & (df["Модификация"] == "60"), "ДЭС-60", "NEF45SM3.S500"),
        ((df["Марка"] == "Насосная станция") & (df["Модификация"] == "ДНУ-630"), "ДНУ-630/70-ГСП", "ЯМЗ-238ДИ"),
        ((df["Марка"] == "Насосная станция") & (df["Модификация"] == "ДНУ-1250/63-ЛП"), "ДНУ-1250/63", "ЛП ЯМЗ-7514"),
        ((df["Марка"] == "Насосная станция") & (df["Модификация"] == "ДНУ-1250/63-ГСП"), "ДНУ-1250/63-ГСП", "ГСП ЯМЗ-7514"),
        (df["Марка"] == "WA-600", "WA 600-6", "6"),
        (df["Марка"] == "WD-600", "WD 600 6", "6"),
        (df["Марка"] == "TM10.11 ГСТ10", "ТМ10.11", "ГСТ10"),
        ((df["Марка"] == "ТМ10.10") & (df["Модификация"] == "ГСТ9"), "ТМ10.10", "ГСТ9"),
        (df["Марка"] == "CASE", "CASE CX-800B", "CX-800B"),
        (df["Марка"] == "D-475", "D 475 A-5", "A-5"),
        (
            (df["Марка"] == "Насосная станция") & (df["Модификация"].isin([
                "DNUDo-1600-75 ГСП (Doosan DP158LD)",
                "DNUDO -1600/75",
                "DNUDo-1600-75 ГСП (Doosan DP158LD) ",
            ])),
            "DNUDo-1600/75-ГСП",
            "DP158LD",
        ),
        (df["Марка"] == "HD-465", "HD 465-7R", "7R"),
        (df["Марка"] == "DM-45", "DM45 HP", None),
        (df["Марка"] == "CLG877H", None, "H"),
        (df["Марка"] == "CLG942EHD", None, "EHD"),
        (df["Марка"] == "CLG975F", None, "F"),
        (df["Марка"] == "PC-400", "РС 400-7", "7"),
        (df["Марка"].isin(["PC-800", "PC-800"]), "РС 800 8E0", "8"),
        (df["Марка"] == "WA-470", "WA 470-3", "3"),
        ((df["Марка"] == "ДЭС") & (df["Модификация"] == "220"), "DCA-220SPK3", "S6D125E-2"),
        ((df["Марка"] == "ДЭС") & (df["Модификация"].isin(["200", "1"])), "ДЭС-200", "DC09 072A"),
        ((df["Марка"] == "ДЭС") & (df["Модификация"] == "201"), "ДЭС-200", "DC09 072A"),
        ((df["Марка"] == "ДЭС") & (df["Модификация"] == "378"), "DPK-DC-378", "378"),
        ((df["Марка"] == "ECD50E") & (df["Модификация"] == "0"), "ECD50E", "1"),
        ((df["Марка"] == "FG Wilson P150-1") & (df["Модификация"] == "150"), "FG Wilson P150-1", "P150-1"),
        (df["Марка"] == "D-65", "D 65EX-16", "EX-16"),
        ((df["Марка"] == "Насосная станция") & (df["Модификация"] == "ДНС-СВ-300-20"), "ДНС-СВ", "300-20"),
        ((df["Марка"] == "Насосная станция") & (df["Модификация"] == "12НДС 1500ГК-01"), "1500ГК-01", "12НДС"),
        ((df["Марка"] == "ДНУ ПМС") & (df["Модификация"] == "ДНУ-1250/63-ЛП"), "ДНУ-1250/63", "ЛП ЯМЗ-7514"),
        ((df["Марка"] == "ДЭС") & (df["Модификация"] == "100"), "АД100С", "6BTAA5,9-G2"),
        ((df["Марка"] == "ДЭС") & (df["Модификация"] == "30"), "АД-30С", "Д-243"),
        (df["Марка"] == "D55", "PRD55", "1"),
        (df["Марка"] == "JD-2000", "JD-2000", "1"),
        (df["Марка"] == "PC-1250", "PC 1250-8", "8"),
    ]

    for mask, brand, mod in replacement_rules:
        _set_brand_mod(df, mask, brand, mod)

    inv_to_mod = {791: "791", 917: "917", 967: "967"}
    for inv, mod in inv_to_mod.items():
        mask = df["Инвентарный номер"].eq(inv)
        _set_brand_mod(df, mask, modification=mod)

    inv_brand_rules = [
        (
            [697, 721, 720, 677, 719, 717, 675, 678, 716],
            "D 375 А-5D",
            "5D",
        ),
        (
            [688, 818, 916, 915, 902, 603, 679, 1161, 602],
            "D 375 A-6",
            "6",
        ),
        (
            [1148, 1145, 1160],
            "D 375 А-6R",
            "6R",
        ),
        (
            [1371],
            "D 375 А-8",
            "8",
        ),
        (
            [661, 1080, 1081, 1083, 1084, 1156, 1186, 330, 1152, 658, 1151, 660, 1187, 573,
             659, 1150, 1153, 1154, 1155, 333, 574, 575, 600, 601, 1157, 1158, 1159],
            "БелАЗ 7547",
            "7547",
        ),
        (
            [1204, 1238, 1311, 1312, 789, 790],
            "БелАЗ 7555В",
            "7555В",
        ),
    ]

    for inv_list, brand, mod in inv_brand_rules:
        mask = df["Инвентарный номер"].isin(inv_list)
        _set_brand_mod(df, mask, brand, mod)

    return df


def _get_initial_runtime_df(df_source: pd.DataFrame) -> pd.DataFrame:
    if df_source.empty:
        return pd.DataFrame(
            columns=[
                "Марка",
                "Модификация",
                "Инвентарный номер",
                "Фактическая наработка в момент проведения ТО",
                "Наработка машины",
                "Дата начала обслуживания",
            ]
        )

    df = df_source.copy()
    df["Дата начала обслуживания"] = pd.to_datetime(df["Дата начала обслуживания"], errors="coerce")
    df["Наработка машины"] = pd.to_numeric(df["Наработка машины"], errors="coerce")
    df["Фактическая наработка в момент проведения ТО"] = pd.to_numeric(
        df["Фактическая наработка в момент проведения ТО"], errors="coerce"
    )

    cols_keep = [
        "Марка",
        "Модификация",
        "Инвентарный номер",
        "Фактическая наработка в момент проведения ТО",
        "Наработка машины",
        "Дата начала обслуживания",
    ]

    pivot_table = (
        df.sort_values(
            [
                "Инвентарный номер",
                "Дата начала обслуживания",
                "Фактическая наработка в момент проведения ТО",
                "Наработка машины",
            ]
        )
        .drop_duplicates(subset=["Инвентарный номер"], keep="first")[cols_keep]
        .reset_index(drop=True)
    )

    return pivot_table


def _to_float(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    s = s.replace({r"^\s*[–—−-]+\s*$": np.nan}, regex=True)
    s = (
        s.str.replace("\u2212", "-", regex=False)
        .str.replace("\u2013", "-", regex=False)
        .str.replace("\u2014", "-", regex=False)
        .str.replace("\xa0", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.replace(r"[^0-9\.\-]", "", regex=True)
    )
    return pd.to_numeric(s, errors="coerce")


def _apply_runtime_limits(result: pd.DataFrame) -> pd.DataFrame:
    if result.empty:
        return result

    limit_rules = [
        (2500, [1249, 967, 1024, 1199, 1202, 1094, 719, 791, 917, 1304, 1091]),
        (3600, [1251, 697, 1148]),
        (3000, [574, 575, 600, 601, 1157, 1158, 1159, 1204, 1238, 792, 793, 1086, 1087, 1088, 1089, 1090, 900, 903, 1160, 805, 901]),
        (2000, [1006, 1228, 680, 804, 1185, 1183, 711, 912, 1250, 1184, 1253, 476, 596]),
        (1000, [963, 1357, 919, 1127, 681, 126, 1005, 811, 1115, 1203, 595, 1067, 498, 810, 400, 652, 653, 819, 1007, 684, 918, 830]),
    ]

    for max_hours, inv_list in limit_rules:
        work = pd.to_numeric(result["Наработка 2026"], errors="coerce")
        fit = result["Инвентарный номер"].isin(inv_list)
        result = result.loc[~fit | (work < max_hours)].copy()

    return result


def build_result_pv():
    warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

    plan_start = pd.Timestamp.now().normalize() - pd.Timedelta(days=1)
    rules = get_maintenance_dicts()

    source_df = load_aggregate_journal_from_db()
    if source_df.empty:
        return pd.DataFrame()

    source_df = _prepare_source_df(source_df)
    df_narabotka = source_df.copy()

    latest_state = _get_latest_state(source_df, plan_start)
    latest_state = _apply_launch_dates(latest_state)

    expanded = _expand_calendar(latest_state)
    new_df = _prepare_runtime_df(expanded)
    new_df = _apply_maintenance_rules(new_df, rules)
    new_df = _postprocess_brand_modifications(new_df)

    initial_runtime = _get_initial_runtime_df(df_narabotka)
    to_join = (
        initial_runtime[["Инвентарный номер", "Дата начала обслуживания", "Наработка машины"]]
        .drop_duplicates("Инвентарный номер", keep="first")
        .rename(
            columns={
                "Дата начала обслуживания": "Дата ТО (мин)",
                "Наработка машины": "Первоначальная наработка",
            }
        )
    )

    new_df["Инвентарный номер"] = pd.to_numeric(new_df["Инвентарный номер"], errors="coerce")
    to_join["Инвентарный номер"] = pd.to_numeric(to_join["Инвентарный номер"], errors="coerce")

    result = new_df.merge(to_join, how="left", on="Инвентарный номер")
    result = result.loc[result["Дата"] <= PLAN_END_DATE].copy()

    for col in ["Планируемая наработка в момент проведения ТО", "Наработка машины"]:
        result[col + "_num"] = _to_float(result[col])

    result["Наработка 2026"] = (
        result["Планируемая наработка в момент проведения ТО_num"]
        - result["Наработка машины_num"]
    )

    result = _apply_runtime_limits(result)

    result_pv = pd.pivot_table(
        result,
        values=["Планируемое техобслуживание"],
        index=[
            "Подразделение",
            "Марка",
            "Инвентарный номер",
            "Фактическая наработка в момент проведения ТО",
        ],
        columns="Дата",
        aggfunc={"Планируемое техобслуживание": "last"},
    ).reset_index()

    return result_pv