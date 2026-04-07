from io import BytesIO

import pandas as pd
from django.forms import formset_factory
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import MaintenanceCreateForm, MaintenanceTaskFactInputForm
from .models import Department, MaintenanceRecord, MaintenanceTaskFact
from .services import MaintenanceExcelService
from Services.PlanTO_2025 import build_result_pv


def _prepare_dataframe(df):
    if hasattr(df.columns, "to_flat_index"):
        normalized_columns = []

        for col in df.columns.to_flat_index():
            if isinstance(col, tuple):
                left = col[0]
                right = col[1] if len(col) > 1 else None

                left_str = "" if pd.isna(left) else str(left).strip()

                if pd.isna(right):
                    normalized_columns.append(left_str)
                else:
                    right_ts = pd.to_datetime(right, errors="coerce")
                    if pd.notna(right_ts):
                        normalized_columns.append(right_ts.strftime("%d.%m.%Y"))
                    else:
                        normalized_columns.append(left_str)
            else:
                normalized_columns.append(str(col).strip())

        df.columns = normalized_columns

    return df.reset_index(drop=True).fillna("")


def _to_float_or_none(value):
    if value in ("", None):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _get_calendar_data(request):
    df = build_result_pv()
    df = _prepare_dataframe(df)

    selected_department = request.GET.get("department", "").strip()
    selected_machine_brand = request.GET.get("machine_brand", "").strip()

    department_choices = []
    machine_brand_choices = []

    if "Подразделение" in df.columns:
        department_choices = sorted(
            df["Подразделение"]
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .unique()
            .tolist()
        )

    if "Марка" in df.columns:
        machine_brand_choices = sorted(
            df["Марка"]
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .unique()
            .tolist()
        )

    filtered_df = df.copy()

    if selected_department and "Подразделение" in filtered_df.columns:
        filtered_df = filtered_df[
            filtered_df["Подразделение"].astype(str).str.strip() == selected_department
        ]

    if selected_machine_brand and "Марка" in filtered_df.columns:
        filtered_df = filtered_df[
            filtered_df["Марка"].astype(str).str.strip() == selected_machine_brand
        ]

    return {
        "df": filtered_df,
        "department_choices": department_choices,
        "machine_brand_choices": machine_brand_choices,
        "selected_department": selected_department,
        "selected_machine_brand": selected_machine_brand,
    }


def index(request):
    df = build_result_pv()
    df = _prepare_dataframe(df)

    table_html = df.to_html(
        index=False,
        classes="table table-bordered table-sm table-striped",
        escape=False,
    )

    return render(
        request,
        "maintenance/operate_index.html",
        {
            "table_html": table_html,
            "rows_total": len(df),
        },
    )


def create_record(request):
    service = MaintenanceExcelService()

    brand_choices = [(x, x) for x in service.get_machine_brands()]
    maintenance_number_choices = [(x, x) for x in service.get_maintenance_types()]

    if request.method == "POST":
        form = MaintenanceCreateForm(
            request.POST,
            machine_brand_choices=brand_choices,
            maintenance_number_choices=maintenance_number_choices,
        )
        if form.is_valid():
            machine_brand = form.cleaned_data["machine_brand"]
            maintenance_type = form.cleaned_data["maintenance_number"]

            tasks = service.get_tasks(machine_brand, maintenance_type)

            if not tasks:
                form.add_error(
                    None,
                    f"Для марки '{machine_brand}' и вида ТО '{maintenance_type}' работы не найдены."
                )
            else:
                request.session["maintenance_header"] = {
                    "department_id": form.cleaned_data["department"].id,
                    "machine_brand": machine_brand,
                    "inventory_number": form.cleaned_data["inventory_number"],
                    "maintenance_date": form.cleaned_data["maintenance_date"].isoformat(),
                    "responsible_fio": form.cleaned_data["responsible_fio"],
                    "machine_hours": form.cleaned_data["machine_hours"],
                    "maintenance_number": form.cleaned_data["maintenance_number"],
                    "maintenance_type": maintenance_type,
                }
                request.session["maintenance_tasks"] = tasks
                return redirect("maintenance:fill_tasks")
    else:
        form = MaintenanceCreateForm(
            machine_brand_choices=brand_choices,
            maintenance_number_choices=maintenance_number_choices,
        )

    return render(request, "maintenance/create_record.html", {"form": form})


def fill_tasks(request):
    header = request.session.get("maintenance_header")
    tasks = request.session.get("maintenance_tasks")

    if not header or not tasks:
        return redirect("maintenance:create_record")

    department_name = ""
    department_id = header.get("department_id")
    if department_id:
        department = Department.objects.filter(pk=department_id).first()
        if department:
            department_name = department.name

    TaskFormSet = formset_factory(MaintenanceTaskFactInputForm, extra=0)

    initial_data = []
    for task in tasks:
        initial_data.append(
            {
                "work_name": task.get("work_name", ""),
                "detail_group": task.get("detail_group", ""),
                "item_name": task.get("item_name", ""),
                "catalog_number": task.get("catalog_number", ""),
                "unit": task.get("unit", ""),
                "qty_plan": task.get("qty_plan", ""),
                "qty_fact": task.get("qty_plan", "") if task.get("qty_plan", "") != "" else None,
            }
        )

    if request.method == "POST":
        formset = TaskFormSet(request.POST)
        if formset.is_valid():
            department = get_object_or_404(Department, pk=header["department_id"])

            record = MaintenanceRecord.objects.create(
                department=department,
                machine_brand=header["machine_brand"],
                inventory_number=header["inventory_number"],
                maintenance_date=header["maintenance_date"],
                responsible_fio=header["responsible_fio"],
                machine_hours=header["machine_hours"],
                maintenance_number=header["maintenance_number"],
                maintenance_type=header["maintenance_type"],
            )

            for form in formset:
                MaintenanceTaskFact.objects.create(
                    record=record,
                    work_name=form.cleaned_data.get("work_name", ""),
                    detail_group=form.cleaned_data.get("detail_group", ""),
                    item_name=form.cleaned_data.get("item_name", ""),
                    catalog_number=form.cleaned_data.get("catalog_number", ""),
                    unit=form.cleaned_data.get("unit", ""),
                    qty_plan=_to_float_or_none(form.cleaned_data.get("qty_plan")),
                    qty_fact=form.cleaned_data.get("qty_fact"),
                )

            request.session.pop("maintenance_header", None)
            request.session.pop("maintenance_tasks", None)

            return redirect("maintenance:detail", pk=record.pk)
    else:
        formset = TaskFormSet(initial=initial_data)

    context = {
        "header": header,
        "department_name": department_name,
        "formset": formset,
        "tasks_count": len(tasks),
    }
    return render(request, "maintenance/fill_tasks.html", context)


def detail(request, pk):
    record = get_object_or_404(
        MaintenanceRecord.objects.select_related("department").prefetch_related("tasks"),
        pk=pk,
    )
    return render(request, "maintenance/detail.html", {"record": record})


def calendar_view(request):
    data = _get_calendar_data(request)
    filtered_df = data["df"]

    table_html = filtered_df.to_html(
        index=False,
        classes="calendar-table",
        escape=False,
    )

    return render(
        request,
        "maintenance/calendar.html",
        {
            "table_html": table_html,
            "rows_total": len(filtered_df),
            "department_choices": data["department_choices"],
            "machine_brand_choices": data["machine_brand_choices"],
            "selected_department": data["selected_department"],
            "selected_machine_brand": data["selected_machine_brand"],
        },
    )


def calendar_export_excel(request):
    data = _get_calendar_data(request)
    df = data["df"].copy()

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Календарь ТО", index=False)

    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="calendar_to.xlsx"'
    return response