import pandas as pd
from pathlib import Path


def parse_float(value):
    if value is None or value == "":
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


def parse_date(value):
    if value is None or value == "":
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if hasattr(value, "date") and not isinstance(value, str):
        try:
            return value.date()
        except Exception:
            pass

    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "nat"}:
        return None

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
            return pd.to_datetime(text, format=fmt, errors="raise").date()
        except Exception:
            pass

    dt = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(dt):
        return None

    return dt.date()


class Upload:
    def open(self):
        base_dir = Path(__file__).resolve().parent
        self.path = base_dir / "debitor.xlsx"
        return self

    def transform(self):
        df = pd.read_excel(self.path)

        df.columns = [
            "account",
            "subkonto1",
            "subkonto2",
            "subkonto3",
            "date",
            "sum_dt",
            "sum_kt",
            "records_count",
            "debt_date",
            "debt_term",
            "debt_period",
            "report_date",
            "debt_reason",
            "responsible_department",
            "solution_comment",
        ]

        text_cols = [
            "account",
            "subkonto1",
            "subkonto2",
            "subkonto3",
            "records_count",
            "debt_term",
            "debt_period",
            "debt_reason",
            "responsible_department",
            "solution_comment",
        ]

        for col in text_cols:
            df[col] = df[col].fillna("").astype(str).str.strip()

        df["sum_dt"] = df["sum_dt"].apply(parse_float)
        df["sum_kt"] = df["sum_kt"].apply(parse_float)

        df["date"] = df["date"].apply(parse_date)
        df["debt_date"] = df["debt_date"].apply(parse_date)
        df["report_date"] = df["report_date"].apply(parse_date)

        df = df.loc[
            ~(
                df[["account", "subkonto1", "subkonto2", "subkonto3", "report_date"]]
                .astype(str)
                .apply(lambda col: col.str.strip())
                .eq("")
                .all(axis=1)
            )
        ]

        return df