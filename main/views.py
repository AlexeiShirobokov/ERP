from io import BytesIO

import pandas as pd
from django.http import FileResponse
from django.shortcuts import render, redirect

from .models import DebitorComment
from Services.debitor import Upload


def index(request):
    return render(request, "main/index.html")


def about(request):
    return render(request, "main/about.html")


def debitor_report(request):
    df = Upload().open().transform()

    df = df.fillna("")
    df = df.loc[~(df.astype(str).apply(lambda col: col.str.strip()).eq("").all(axis=1))]

    records = df.to_dict(orient="records")

    if request.method == "POST":
        row_index = request.POST.get("row_index")
        comment_text = request.POST.get("comment", "").strip()

        if row_index is not None and row_index.isdigit():
            row = records[int(row_index)]

            DebitorComment.objects.update_or_create(
                account=str(row.get("account", "")),
                subkonto1=str(row.get("subkonto1", "")),
                subkonto2=str(row.get("subkonto2", "")),
                subkonto3=str(row.get("subkonto3", "")),
                report_date=str(row.get("report_date", "")),
                defaults={
                    "comment": comment_text,
                }
            )

        return redirect("debitor_report")

    for i, row in enumerate(records):
        comment_obj = DebitorComment.objects.filter(
            account=str(row.get("account", "")),
            subkonto1=str(row.get("subkonto1", "")),
            subkonto2=str(row.get("subkonto2", "")),
            subkonto3=str(row.get("subkonto3", "")),
            report_date=str(row.get("report_date", "")),
        ).first()

        row["saved_comment"] = comment_obj.comment if comment_obj else ""
        row["row_index"] = i

    context = {
        "records": records,
        "rows_total": len(records),
    }
    return render(request, "main/debitor_report.html", context)


def export_debitor_excel(request):
    df = Upload().open().transform()
    df = df.fillna("")

    df = df.loc[~(df.astype(str).apply(lambda col: col.str.strip()).eq("").all(axis=1))]

    comments = DebitorComment.objects.all()

    comments_map = {}
    for obj in comments:
        key = (
            str(obj.account or ""),
            str(obj.subkonto1 or ""),
            str(obj.subkonto2 or ""),
            str(obj.subkonto3 or ""),
            str(obj.report_date or ""),
        )
        comments_map[key] = obj.comment or ""

    df["solution_comment"] = df.apply(
        lambda row: comments_map.get(
            (
                str(row.get("account", "")),
                str(row.get("subkonto1", "")),
                str(row.get("subkonto2", "")),
                str(row.get("subkonto3", "")),
                str(row.get("report_date", "")),
            ),
            str(row.get("solution_comment", "")),
        ),
        axis=1
    )

    export_df = df.rename(columns={
        "account": "Счет",
        "subkonto1": "Субконто 1",
        "subkonto2": "Субконто 2",
        "subkonto3": "Субконто 3",
        "date": "Дата",
        "sum_dt": "Сумма остаток Дт",
        "sum_kt": "Сумма остаток Кт",
        "records_count": "Количество записей",
        "debt_date": "Дата образования задолженности",
        "debt_term": "срок дебиторской задолженности",
        "debt_period": "Период задолженности",
        "report_date": "Дата отчета",
        "debt_reason": "Причина образования ДЗ",
        "responsible_department": "Ответственный отдел по урегулированию ДЗ",
        "solution_comment": "Комментарий решения",
    })

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Отчет")

    output.seek(0)

    return FileResponse(
        output,
        as_attachment=True,
        filename="debitor_updated.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )