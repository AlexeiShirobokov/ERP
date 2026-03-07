from io import BytesIO

import pandas as pd
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import DebitorCase
from Services.debitor import Upload


def index(request):
    return render(request, "main/index.html")


def about(request):
    return render(request, "main/about.html")


def _get_debitor_df():
    df = Upload().open().transform()
    df = df.fillna("")
    df = df.loc[~(df.astype(str).apply(lambda col: col.str.strip()).eq("").all(axis=1))]
    return df


def _get_case_key_from_row(row):
    return {
        "account": str(row.get("account", "")),
        "subkonto1": str(row.get("subkonto1", "")),
        "subkonto2": str(row.get("subkonto2", "")),
        "subkonto3": str(row.get("subkonto3", "")),
        "report_date": str(row.get("report_date", "")),
    }


def _sync_cases_from_excel():
    """
    Создает карточки DebitorCase для всех строк Excel, если их еще нет.
    Все новые карточки по умолчанию попадают в Бухгалтерию.
    """
    df = _get_debitor_df()
    records = df.to_dict(orient="records")

    existing_keys = set(
        DebitorCase.objects.values_list(
            "account", "subkonto1", "subkonto2", "subkonto3", "report_date"
        )
    )

    to_create = []
    for row in records:
        key = (
            str(row.get("account", "")),
            str(row.get("subkonto1", "")),
            str(row.get("subkonto2", "")),
            str(row.get("subkonto3", "")),
            str(row.get("report_date", "")),
        )

        if key in existing_keys:
            continue

        to_create.append(
            DebitorCase(
                account=key[0],
                subkonto1=key[1],
                subkonto2=key[2],
                subkonto3=key[3],
                report_date=key[4],
                stage="accounting",
                debt_reason=str(row.get("debt_reason", "")),
            )
        )

    if to_create:
        DebitorCase.objects.bulk_create(to_create, ignore_conflicts=True)

    return df


def debitor_report(request):
    df = _sync_cases_from_excel()
    records = df.to_dict(orient="records")

    existing_cases = DebitorCase.objects.all()
    cases_map = {}
    for obj in existing_cases:
        key = (
            str(obj.account or ""),
            str(obj.subkonto1 or ""),
            str(obj.subkonto2 or ""),
            str(obj.subkonto3 or ""),
            str(obj.report_date or ""),
        )
        cases_map[key] = obj

    for row in records:
        key = (
            str(row.get("account", "")),
            str(row.get("subkonto1", "")),
            str(row.get("subkonto2", "")),
            str(row.get("subkonto3", "")),
            str(row.get("report_date", "")),
        )

        case_obj = cases_map.get(key)
        row["case_exists"] = case_obj is not None
        row["case_stage"] = case_obj.get_stage_display() if case_obj else "Бухгалтерия"

    context = {
        "records": records,
        "rows_total": len(records),
    }
    return render(request, "main/debitor_report.html", context)


def debitor_case(request):
    account = request.GET.get("account", "")
    subkonto1 = request.GET.get("subkonto1", "")
    subkonto2 = request.GET.get("subkonto2", "")
    subkonto3 = request.GET.get("subkonto3", "")
    report_date = request.GET.get("report_date", "")

    df = _sync_cases_from_excel()
    records = df.to_dict(orient="records")

    selected_row = None
    for row in records:
        if (
            str(row.get("account", "")) == str(account)
            and str(row.get("subkonto1", "")) == str(subkonto1)
            and str(row.get("subkonto2", "")) == str(subkonto2)
            and str(row.get("subkonto3", "")) == str(subkonto3)
            and str(row.get("report_date", "")) == str(report_date)
        ):
            selected_row = row
            break

    if not selected_row:
        raise Http404("Карточка по данной строке Excel не найдена")

    key_data = _get_case_key_from_row(selected_row)

    case_obj, created = DebitorCase.objects.get_or_create(
        account=key_data["account"],
        subkonto1=key_data["subkonto1"],
        subkonto2=key_data["subkonto2"],
        subkonto3=key_data["subkonto3"],
        report_date=key_data["report_date"],
        defaults={
            "stage": "accounting",
            "debt_reason": str(selected_row.get("debt_reason", "")),
        },
    )

    if request.method == "POST":
        action = request.POST.get("action", "save")

        case_obj.debt_reason = request.POST.get("debt_reason", "").strip()
        case_obj.responsible_person = request.POST.get("responsible_person", "").strip()
        case_obj.comment = request.POST.get("comment", "").strip()

        if action == "to_accounting":
            case_obj.stage = "accounting"
        elif action == "to_supply":
            case_obj.stage = "supply"
        elif action == "to_legal":
            case_obj.stage = "legal"
        elif action == "to_closed":
            case_obj.stage = "closed"

        case_obj.save()

        query = (
            f"?account={case_obj.account}"
            f"&subkonto1={case_obj.subkonto1}"
            f"&subkonto2={case_obj.subkonto2}"
            f"&subkonto3={case_obj.subkonto3}"
            f"&report_date={case_obj.report_date}"
        )
        return redirect(f"{request.path}{query}")

    context = {
        "row": selected_row,
        "case_obj": case_obj,
    }
    return render(request, "main/debitor_case.html", context)


def export_debitor_excel(request):
    df = _sync_cases_from_excel()

    cases = DebitorCase.objects.all()

    cases_map = {}
    for obj in cases:
        key = (
            str(obj.account or ""),
            str(obj.subkonto1 or ""),
            str(obj.subkonto2 or ""),
            str(obj.subkonto3 or ""),
            str(obj.report_date or ""),
        )
        cases_map[key] = obj

    def get_case_value(row, attr_name, fallback=""):
        key = (
            str(row.get("account", "")),
            str(row.get("subkonto1", "")),
            str(row.get("subkonto2", "")),
            str(row.get("subkonto3", "")),
            str(row.get("report_date", "")),
        )
        obj = cases_map.get(key)
        if not obj:
            return fallback
        return getattr(obj, attr_name, fallback) or fallback

    df["debt_reason"] = df.apply(
        lambda row: get_case_value(row, "debt_reason", str(row.get("debt_reason", ""))),
        axis=1,
    )
    df["responsible_department"] = df.apply(
        lambda row: (
            cases_map.get(
                (
                    str(row.get("account", "")),
                    str(row.get("subkonto1", "")),
                    str(row.get("subkonto2", "")),
                    str(row.get("subkonto3", "")),
                    str(row.get("report_date", "")),
                )
            ).get_stage_display()
            if cases_map.get(
                (
                    str(row.get("account", "")),
                    str(row.get("subkonto1", "")),
                    str(row.get("subkonto2", "")),
                    str(row.get("subkonto3", "")),
                    str(row.get("report_date", "")),
                )
            )
            else "Бухгалтерия"
        ),
        axis=1,
    )
    df["solution_comment"] = df.apply(
        lambda row: get_case_value(row, "comment", ""),
        axis=1,
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


@require_POST
def move_debitor_case(request):
    case_id = request.POST.get("case_id")
    new_stage = request.POST.get("new_stage")

    allowed_stages = {"accounting", "supply", "legal", "closed"}

    if not case_id or new_stage not in allowed_stages:
        return JsonResponse({"ok": False, "error": "Неверные данные"}, status=400)

    case_obj = get_object_or_404(DebitorCase, pk=case_id)
    case_obj.stage = new_stage
    case_obj.save(update_fields=["stage", "updated_at"])

    return JsonResponse({
        "ok": True,
        "stage": case_obj.stage,
        "stage_display": case_obj.get_stage_display(),
    })


def debitor_board(request):
    _sync_cases_from_excel()
    cases = DebitorCase.objects.all().order_by("stage", "subkonto1")
    return render(request, "main/debitor_board.html", {"cases": cases})