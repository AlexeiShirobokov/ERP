from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Sum, Count
from django.shortcuts import render

from .models import OperateDataFile, OperateRow


@login_required
def index(request):
    data_file = OperateDataFile.objects.filter(is_active=True).order_by("-uploaded_at", "-id").first()

    if not data_file:
        return render(request, "operate/operate_index.html", {
            "error": "В админке не загружен активный файл аналитики.",
            "subdivisions": [],
            "selected_subdivision": "",
            "summary_rows": [],
            "detail_rows": [],
        })

    if not data_file.is_processed:
        return render(request, "operate/operate_index.html", {
            "error": data_file.processing_error or "Файл ещё не обработан.",
            "data_file": data_file,
            "subdivisions": [],
            "selected_subdivision": "",
            "summary_rows": [],
            "detail_rows": [],
        })

    base_qs = OperateRow.objects.filter(data_file=data_file)

    subdivisions = sorted(
        x for x in base_qs.exclude(subdivision="").values_list("subdivision", flat=True).distinct()
    )

    selected_subdivision = request.GET.get("subdivision", "").strip()
    if not selected_subdivision and subdivisions:
        selected_subdivision = subdivisions[0]

    filtered_qs = base_qs
    if selected_subdivision:
        filtered_qs = filtered_qs.filter(subdivision=selected_subdivision)

    summary = (
        filtered_qs
        .values("process_name")
        .annotate(
            rows_count=Count("id"),
            total_work_volume=Sum("work_volume"),
            total_corrected_work_volume=Sum("corrected_work_volume"),
            avg_work_time=Avg("work_time"),
            avg_downtime=Avg("downtime"),
        )
        .order_by("process_name")
    )

    detail_rows = (
        filtered_qs
        .values(
            "date",
            "subdivision",
            "block",
            "process_name",
            "machine_brand",
            "machine_name",
            "machine_inventory",
            "work_volume",
            "corrected_work_volume",
            "work_time",
            "downtime",
            "transportation_distance",
            "shift_master",
            "operator_name",
            "assistant_name",
            "downtime_reason",
        )
        .order_by("-date", "process_name")[:300]
    )

    context = {
        "data_file": data_file,
        "subdivisions": subdivisions,
        "selected_subdivision": selected_subdivision,
        "summary_rows": list(summary),
        "detail_rows": list(detail_rows),
        "error": "",
    }
    return render(request, "operate/operate_index.html", context)