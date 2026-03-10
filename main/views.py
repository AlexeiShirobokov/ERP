from io import BytesIO

import pandas as pd
from django.contrib import messages
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from collections import defaultdict
from django.db.models import Sum
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import DebitorCase, DebitorSnapshot
from Services.debitor import Upload

@login_required
def index(request):
    return render(request, "main/index.html")


def about(request):
    return render(request, "main/about.html")


def _get_debitor_df():
    df = Upload().open().transform()
    df = df.loc[~(df.astype(str).apply(lambda col: col.str.strip()).eq("").all(axis=1))]
    return df


def _report_date_sort_key(value):
    if value in ("", None):
        return pd.Timestamp.min
    try:
        ts = pd.to_datetime(value, dayfirst=True, errors="coerce")
        if pd.isna(ts):
            return pd.Timestamp.min
        return ts
    except Exception:
        return pd.Timestamp.min


def _to_date_or_none(value):
    if value in ("", None):
        return None
    try:
        ts = pd.to_datetime(value, dayfirst=True, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.date()
    except Exception:
        return None


def _to_float_or_none(value):
    if value in ("", None):
        return None

    text = str(value).strip()
    text = text.replace("\xa0", "").replace(" ", "").replace(",", ".")

    if not text:
        return None

    try:
        return float(text)
    except Exception:
        return None


def _sync_cases_from_excel():
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
            str(row.get("account", "") or ""),
            str(row.get("subkonto1", "") or ""),
            str(row.get("subkonto2", "") or ""),
            str(row.get("subkonto3", "") or ""),
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

        report_date = row.get("report_date")
        if not report_date:
            continue

        DebitorSnapshot.objects.update_or_create(
            case=case_obj,
            report_date=report_date,
            defaults={
                "date": row.get("date"),
                "sum_dt": row.get("sum_dt"),
                "sum_kt": row.get("sum_kt"),
                "records_count": str(row.get("records_count", "") or ""),
                "debt_date": row.get("debt_date"),
                "debt_term": str(row.get("debt_term", "") or ""),
                "debt_period": str(row.get("debt_period", "") or ""),
                "debt_reason_excel": str(row.get("debt_reason", "") or ""),
                "responsible_department_excel": str(row.get("responsible_department", "") or ""),
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

### === для debitor_aging ===

PERIOD_ORDER = [
    "0-30",
    "31-90",
    "91-120",
    "121-180",
    "181-270",
    "271-360",
    ">360",
]


def _normalize_period(value):
    value = str(value or "").strip()
    if value in PERIOD_ORDER:
        return value
    return value if value else "Без периода"


def _format_number(value):
    if value in (None, ""):
        return ""
    try:
        return f"{float(value):,.0f}".replace(",", " ")
    except Exception:
        return str(value)


def debitor_aging(request):
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()

    snapshots_qs = DebitorSnapshot.objects.select_related("case").all()

    all_report_dates = sorted(
        set(
            str(x).strip()
            for x in DebitorSnapshot.objects.exclude(report_date__isnull=True)
            .values_list("report_date", flat=True)
            if str(x).strip()
        ),
        key=_report_date_sort_key,
    )

    snapshots_qs = list(snapshots_qs)

    if date_from:
        snapshots_qs = [
            s for s in snapshots_qs
            if _report_date_sort_key(s.report_date) >= _report_date_sort_key(date_from)
        ]

    if date_to:
        snapshots_qs = [
            s for s in snapshots_qs
            if _report_date_sort_key(s.report_date) <= _report_date_sort_key(date_to)
        ]

    snapshots = list(snapshots_qs)

    report_dates = sorted(
        set(str(s.report_date).strip() for s in snapshots if str(s.report_date).strip()),
        key=_report_date_sort_key,
    )

    if not report_dates:
        context = {
            "date_from": date_from,
            "date_to": date_to,
            "all_report_dates": all_report_dates,
            "report_dates": [],
            "period_rows": [],
            "totals_by_date": [],
            "grand_total": 0,
            "over_90_total": 0,
            "over_360_total": 0,
            "change_total": None,
            "chart_labels": [],
            "chart_datasets": [],
            "top_counterparties": [],
            "growth_counterparties": [],
            "worsened_counterparties": [],
        }
        return render(request, "main/debitor_aging.html", context)

    # ---------- блок по периодам ----------
    from collections import defaultdict

    matrix = defaultdict(lambda: defaultdict(float))
    totals_by_date = defaultdict(float)

    for snap in snapshots:
        period = _normalize_period(snap.debt_period)
        report_date = str(snap.report_date).strip()
        amount = float(snap.sum_dt or 0)

        matrix[period][report_date] += amount
        totals_by_date[report_date] += amount

    present_periods = list(matrix.keys())
    ordered_periods = [p for p in PERIOD_ORDER if p in present_periods]
    other_periods = [p for p in present_periods if p not in PERIOD_ORDER]
    final_periods = ordered_periods + sorted(other_periods)

    period_rows = []
    for period in final_periods:
        values = []
        first_value = None
        last_value = None

        for i, dt in enumerate(report_dates):
            val = matrix[period].get(dt, 0)
            values.append({
                "raw": val,
                "formatted": _format_number(val),
            })
            if i == 0:
                first_value = val
            if i == len(report_dates) - 1:
                last_value = val

        delta = (last_value or 0) - (first_value or 0)

        period_rows.append({
            "period": period,
            "values": values,
            "delta_raw": delta,
            "delta_formatted": _format_number(delta),
        })

    totals_row = []
    for dt in report_dates:
        totals_row.append({
            "raw": totals_by_date.get(dt, 0),
            "formatted": _format_number(totals_by_date.get(dt, 0)),
        })

    grand_total = totals_by_date.get(report_dates[-1], 0)

    over_90_periods = {"91-120", "121-180", "181-270", "271-360", ">360"}
    over_90_total = sum(
        matrix[p].get(report_dates[-1], 0)
        for p in final_periods
        if p in over_90_periods
    )

    over_360_total = matrix.get(">360", {}).get(report_dates[-1], 0)

    change_total = None
    if len(report_dates) >= 2:
        change_total = totals_by_date.get(report_dates[-1], 0) - totals_by_date.get(report_dates[0], 0)

    chart_labels = report_dates
    chart_datasets = []
    for period in final_periods:
        chart_datasets.append({
            "label": period,
            "data": [round(matrix[period].get(dt, 0), 2) for dt in report_dates],
        })

    # ---------- блок по контрагентам ----------
    top_counterparties, growth_counterparties, worsened_counterparties = _build_counterparty_analytics(snapshots)

    context = {
        "date_from": date_from,
        "date_to": date_to,
        "all_report_dates": all_report_dates,
        "report_dates": report_dates,
        "period_rows": period_rows,
        "totals_by_date": totals_row,
        "grand_total": _format_number(grand_total),
        "over_90_total": _format_number(over_90_total),
        "over_360_total": _format_number(over_360_total),
        "change_total": _format_number(change_total) if change_total is not None else None,
        "chart_labels": chart_labels,
        "chart_datasets": chart_datasets,
        "top_counterparties": top_counterparties,
        "growth_counterparties": growth_counterparties,
        "worsened_counterparties": worsened_counterparties,
    }
    return render(request, "main/debitor_aging.html", context)

### === helper функции ===
def _period_rank(period):
    order_map = {
        "0-30": 1,
        "31-90": 2,
        "91-120": 3,
        "121-180": 4,
        "181-270": 5,
        "271-360": 6,
        ">360": 7,
        "Без периода": 999,
        "": 999,
    }
    return order_map.get(str(period).strip(), 999)


def _case_url(case_obj, report_date=""):
    return (
        f"/debitor-report/case/"
        f"?account={case_obj.account}"
        f"&subkonto1={case_obj.subkonto1 or ''}"
        f"&subkonto2={case_obj.subkonto2 or ''}"
        f"&subkonto3={case_obj.subkonto3 or ''}"
        f"&report_date={report_date or ''}"
    )


def _build_counterparty_analytics(snapshots):
    """
    Для каждого case берем:
    - первый snapshot в диапазоне
    - последний snapshot в диапазоне
    И строим:
    1. top_counterparties
    2. growth_counterparties
    3. worsened_counterparties
    """
    grouped = {}

    for snap in snapshots:
        case_id = snap.case.id
        grouped.setdefault(case_id, []).append(snap)

    top_counterparties = []
    growth_counterparties = []
    worsened_counterparties = []

    for case_id, snaps in grouped.items():
        snaps_sorted = sorted(
            snaps,
            key=lambda s: (_report_date_sort_key(s.report_date), s.id)
        )

        first_snap = snaps_sorted[0]
        last_snap = snaps_sorted[-1]
        case_obj = last_snap.case

        first_sum = float(first_snap.sum_dt or 0)
        last_sum = float(last_snap.sum_dt or 0)
        delta_sum = last_sum - first_sum

        first_period = _normalize_period(first_snap.debt_period)
        last_period = _normalize_period(last_snap.debt_period)

        item = {
            "case_id": case_obj.id,
            "counterparty": case_obj.subkonto1 or "Без названия",
            "account": case_obj.account,
            "subkonto2": case_obj.subkonto2 or "",
            "first_report_date": first_snap.report_date,
            "last_report_date": last_snap.report_date,
            "first_sum": first_sum,
            "last_sum": last_sum,
            "delta_sum": delta_sum,
            "first_sum_fmt": _format_number(first_sum),
            "last_sum_fmt": _format_number(last_sum),
            "delta_sum_fmt": _format_number(delta_sum),
            "first_period": first_period,
            "last_period": last_period,
            "stage": case_obj.get_stage_display(),
            "detail_url": _case_url(case_obj, last_snap.report_date),
        }

        top_counterparties.append(item)
        growth_counterparties.append(item)

        if _period_rank(last_period) > _period_rank(first_period):
            worsened_counterparties.append(item)

    top_counterparties = sorted(
        top_counterparties,
        key=lambda x: x["last_sum"],
        reverse=True
    )[:20]

    growth_counterparties = sorted(
        growth_counterparties,
        key=lambda x: x["delta_sum"],
        reverse=True
    )[:20]

    worsened_counterparties = sorted(
        worsened_counterparties,
        key=lambda x: (
            _period_rank(x["last_period"]) - _period_rank(x["first_period"]),
            x["last_sum"]
        ),
        reverse=True
    )[:20]

    return top_counterparties, growth_counterparties, worsened_counterparties

