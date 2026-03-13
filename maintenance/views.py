from django.forms import formset_factory
from django.shortcuts import get_object_or_404, redirect, render

from .forms import MaintenanceCreateForm, MaintenanceTaskFactInputForm
from .models import MaintenanceRecord, MaintenanceTaskFact, Department
from .services import MaintenanceExcelService
from Services.PlanTO_2025 import build_result_pv

def index(request):
    df = build_result_pv()

    # если колонки MultiIndex после pivot_table
    if hasattr(df.columns, "to_flat_index"):
        flat_cols = []
        for col in df.columns.to_flat_index():
            if isinstance(col, tuple):
                parts = [str(x) for x in col if x not in ("", None)]
                flat_cols.append(" / ".join(parts))
            else:
                flat_cols.append(str(col))
        df.columns = flat_cols

    df = df.reset_index(drop=True).fillna("")

    table_html = df.to_html(
        index=False,
        classes="table table-bordered table-sm table-striped",
        escape=False,
    )

    return render(
        request,
        "maintenance/index.html",
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
                    "maintenance_number": form.cleaned_data["maintenance_number"],  # здесь у тебя выбранный вид ТО
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
        initial_data.append({
            "work_name": task.get("work_name", ""),
            "detail_group": task.get("detail_group", ""),
            "item_name": task.get("item_name", ""),
            "catalog_number": task.get("catalog_number", ""),
            "unit": task.get("unit", ""),
            "qty_plan": task.get("qty_plan", ""),
            "qty_fact": task.get("qty_plan", "") if task.get("qty_plan", "") != "" else None,
        })

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
        pk=pk
    )
    return render(request, "maintenance/detail.html", {"record": record})


def _to_float_or_none(value):
    if value in ("", None):
        return None
    try:
        return float(value)
    except Exception:
        return None