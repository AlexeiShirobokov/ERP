from io import BytesIO

import pandas as pd
from django.contrib import messages
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import DebitorCase, DebitorSnapshot
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


def _report_date_sort_key(value):
    if value in ("", None):
        return pd.Timestamp.min
    try:
        return pd.to_datetime(value, dayfirst=True, errors="coerce")
    except Exception:
        return pd.Timestamp.min


def _to_float_or_none(value):
    if value in ("", None):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _sync_cases_from_excel():
    """
    1. Создает/обновляет DebitorCase по ключу без report_date
    2. Создает/обновляет DebitorSnapshot по (case, report_date)
    3. Обновляет текущие поля кейса по самой свежей дате отчета
    """
    df = _get_debitor_df()
    records = df.to_dict(orient="records")

    existing_cases = {
        (
            str(obj.account or ""),
            str(obj.subkonto1 or ""),
            str(obj.subkonto2 or ""),
            str(obj.subkonto3 or ""),
        ): obj
        for obj in DebitorCase.objects.all()
    }

    touched_case_ids = set()

    for row in records:
        case_key = (
            str(row.get("account", "")),
            str(row.get("subkonto1", "")),
            str(row.get("subkonto2", "")),
            str(row.get("subkonto3", "")),
        )

        case_obj = existing_cases.get(case_key)
        if not case_obj:
            case_obj = DebitorCase.objects.create(
                account=case_key[0],
                subkonto1=case_key[1],
                subkonto2=case_key[2],
                subkonto3=case_key[3],
                stage="accounting",
                debt_reason="",
                is_active=True,
            )
            existing_cases[case_key] = case_obj

        touched_case_ids.add(case_obj.id)

        report_date = str(row.get("report_date", ""))

        DebitorSnapshot.objects.update_or_create(
            case=case_obj,
            report_date=report_date,
            defaults={
                "date": str(row.get("date", "")),
                "sum_dt": _to_float_or_none(row.get("sum_dt")),
                "sum_kt": _to_float_or_none(row.get("sum_kt")),
                "records_count": str(row.get("records_count", "")),
                "debt_date": str(row.get("debt_date", "")),
                "debt_term": str(row.get("debt_term", "")),
                "debt_period": str(row.get("debt_period", "")),
                "debt_reason_excel": str(row.get("debt_reason", "")),
                "responsible_department_excel": str(row.get("responsible_department", "")),
            },
        )

    DebitorCase.objects.exclude(id__in=touched_case_ids).update(is_active=False)
    DebitorCase.objects.filter(id__in=touched_case_ids).update(is_active=True)

    cases = DebitorCase.objects.prefetch_related("snapshots").all()
    for case_obj in cases:
        snapshots = list(case_obj.snapshots.all())
        if not snapshots:
            continue

        latest_snapshot = max(
            snapshots,
            key=lambda s: (_report_date_sort_key(s.report_date), s.id),
        )

        case_obj.last_report_date = latest_snapshot.report_date
        case_obj.current_date = latest_snapshot.date
        case_obj.current_sum_dt = latest_snapshot.sum_dt
        case_obj.current_sum_kt = latest_snapshot.sum_kt
        case_obj.current_records_count = latest_snapshot.records_count
        case_obj.current_debt_date = latest_snapshot.debt_date
        case_obj.current_debt_term = latest_snapshot.debt_term
        case_obj.current_debt_period = latest_snapshot.debt_period
        case_obj.current_debt_reason_excel = latest_snapshot.debt_reason_excel
        case_obj.current_responsible_department_excel = latest_snapshot.responsible_department_excel
        case_obj.save(
            update_fields=[
                "last_report_date",
                "current_date",
                "current_sum_dt",
                "current_sum_kt",
                "current_records_count",
                "current_debt_date",
                "current_debt_term",
                "current_debt_period",
                "current_debt_reason_excel",
                "current_responsible_department_excel",
                "is_active",
                "updated_at",
            ]
        )


def debitor_sync(request):
    _sync_cases_from_excel()
    messages.success(request, "Данные из Excel обновлены.")
    return redirect("debitor_report")


def debitor_report(request):
    report_date_filter = request.GET.get("report_date", "").strip()

    snapshots_qs = DebitorSnapshot.objects.select_related("case").all()

    if report_date_filter:
        snapshots_qs = snapshots_qs.filter(report_date=report_date_filter)

    snapshots = list(snapshots_qs.order_by("-report_date", "-id"))

    report_dates_qs = (
        DebitorSnapshot.objects.exclude(report_date__isnull=True)
        .exclude(report_date__exact="")
        .values_list("report_date", flat=True)
        .distinct()
    )
    report_dates = sorted(
        set(str(x).strip() for x in report_dates_qs if str(x).strip()),
        key=_report_date_sort_key,
        reverse=True,
    )

    records = []
    for snap in snapshots:
        records.append({
            "account": snap.case.account,
            "subkonto1": snap.case.subkonto1,
            "subkonto2": snap.case.subkonto2,
            "subkonto3": snap.case.subkonto3,
            "date": snap.date,
            "sum_dt": snap.sum_dt,
            "sum_kt": snap.sum_kt,
            "records_count": snap.records_count,
            "debt_date": snap.debt_date,
            "debt_term": snap.debt_term,
            "debt_period": snap.debt_period,
            "report_date": snap.report_date,
            "debt_reason": snap.debt_reason_excel,
            "case_stage": snap.case.get_stage_display(),
        })

    context = {
        "records": records,
        "rows_total": len(records),
        "report_dates": report_dates,
        "selected_report_date": report_date_filter,
    }
    return render(request, "main/debitor_report.html", context)


def debitor_case(request):
    account = request.GET.get("account", "")
    subkonto1 = request.GET.get("subkonto1", "")
    subkonto2 = request.GET.get("subkonto2", "")
    subkonto3 = request.GET.get("subkonto3", "")
    report_date = request.GET.get("report_date", "").strip()

    case_obj = get_object_or_404(
        DebitorCase,
        account=str(account),
        subkonto1=str(subkonto1),
        subkonto2=str(subkonto2),
        subkonto3=str(subkonto3),
    )

    snapshots = list(case_obj.snapshots.all().order_by("-report_date", "-id"))
    if not snapshots:
        raise Http404("История по данной карточке не найдена")

    selected_snapshot = None
    if report_date:
        for snap in snapshots:
            if str(snap.report_date) == str(report_date):
                selected_snapshot = snap
                break

    if not selected_snapshot:
        selected_snapshot = snapshots[0]

    row = {
        "account": case_obj.account,
        "subkonto1": case_obj.subkonto1,
        "subkonto2": case_obj.subkonto2,
        "subkonto3": case_obj.subkonto3,
        "date": selected_snapshot.date,
        "sum_dt": selected_snapshot.sum_dt,
        "sum_kt": selected_snapshot.sum_kt,
        "records_count": selected_snapshot.records_count,
        "debt_date": selected_snapshot.debt_date,
        "debt_term": selected_snapshot.debt_term,
        "debt_period": selected_snapshot.debt_period,
        "report_date": selected_snapshot.report_date,
    }

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
            f"&report_date={selected_snapshot.report_date}"
        )
        return redirect(f"{request.path}{query}")

    context = {
        "row": row,
        "case_obj": case_obj,
        "snapshots": snapshots,
        "selected_snapshot": selected_snapshot,
    }
    return render(request, "main/debitor_case.html", context)


def export_debitor_excel(request):
    snapshots = DebitorSnapshot.objects.select_related("case").all().order_by("-report_date", "id")

    export_rows = []
    for snap in snapshots:
        export_rows.append({
            "Счет": snap.case.account,
            "Субконто 1": snap.case.subkonto1,
            "Субконто 2": snap.case.subkonto2,
            "Субконто 3": snap.case.subkonto3,
            "Дата": snap.date,
            "Сумма остаток Дт": snap.sum_dt,
            "Сумма остаток Кт": snap.sum_kt,
            "Количество записей": snap.records_count,
            "Дата образования задолженности": snap.debt_date,
            "срок дебиторской задолженности": snap.debt_term,
            "Период задолженности": snap.debt_period,
            "Дата отчета": snap.report_date,
            "Причина образования ДЗ": snap.case.debt_reason or snap.debt_reason_excel,
            "Ответственный отдел по урегулированию ДЗ": snap.case.get_stage_display(),
            "Комментарий решения": snap.case.comment or "",
        })

    export_df = pd.DataFrame(export_rows)

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
    cases = DebitorCase.objects.filter(is_active=True).order_by("stage", "subkonto1")
    return render(request, "main/debitor_board.html", {"cases": cases})