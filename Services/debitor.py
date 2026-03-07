import pandas as pd
from pathlib import Path


class Upload:
    def open(self):
        base_dir = Path(__file__).resolve().parent
        self.path = base_dir / "debitor.xlsx"
        return self

    def transform(self):
        df = pd.read_excel(self.path)

        df = df.fillna("")

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

        return df

