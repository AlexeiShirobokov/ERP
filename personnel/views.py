from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import PersonnelDocumentForm, PersonnelRecordForm
from .models import PersonnelDocument, PersonnelRecord


@login_required
def record_list(request: HttpRequest) -> HttpResponse:
    query = request.GET.get("q", "").strip()

    records = PersonnelRecord.objects.all()
    if query:
        records = records.filter(
            Q(full_name__icontains=query)
            | Q(hh_candidate__icontains=query)
            | Q(position_name__icontains=query)
            | Q(contacts__icontains=query)
            | Q(medical_commission__icontains=query)
            | Q(qualification__icontains=query)
            | Q(ticket__icontains=query)
        )

    paginator = Paginator(records, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "personnel/record_list.html",
        {
            "page_obj": page_obj,
            "records": page_obj.object_list,
            "q": query,
        },
    )


@login_required
def record_detail(request: HttpRequest, pk: int) -> HttpResponse:
    record = get_object_or_404(
        PersonnelRecord.objects.select_related("created_by", "updated_by"),
        pk=pk,
    )

    return render(
        request,
        "personnel/record_detail.html",
        {
            "record": record,
            "document_form": PersonnelDocumentForm(),
            "documents": record.documents.select_related("uploaded_by").all(),
        },
    )


@login_required
def record_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = PersonnelRecordForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.created_by = request.user
            record.updated_by = request.user
            record.save()
            messages.success(request, "Кадровая карточка создана.")
            return redirect(record.get_absolute_url())
    else:
        form = PersonnelRecordForm()

    return render(
        request,
        "personnel/record_form.html",
        {
            "form": form,
            "page_title": "Новая кадровая карточка",
            "submit_text": "Сохранить",
        },
    )


@login_required
def record_update(request: HttpRequest, pk: int) -> HttpResponse:
    record = get_object_or_404(PersonnelRecord, pk=pk)

    if request.method == "POST":
        form = PersonnelRecordForm(request.POST, instance=record)
        if form.is_valid():
            record = form.save(commit=False)
            record.updated_by = request.user
            record.save()
            messages.success(request, "Кадровая карточка обновлена.")
            return redirect(record.get_absolute_url())
    else:
        form = PersonnelRecordForm(instance=record)

    return render(
        request,
        "personnel/record_form.html",
        {
            "form": form,
            "record": record,
            "page_title": "Редактирование кадровой карточки",
            "submit_text": "Сохранить изменения",
        },
    )


@login_required
def record_delete(request: HttpRequest, pk: int) -> HttpResponse:
    record = get_object_or_404(PersonnelRecord, pk=pk)

    if request.method == "POST":
        record.delete()
        messages.success(request, "Кадровая карточка удалена.")
        return redirect("personnel:record_list")

    return render(
        request,
        "personnel/record_confirm_delete.html",
        {"record": record},
    )


@login_required
@require_POST
def document_upload(request: HttpRequest, record_id: int) -> HttpResponse:
    record = get_object_or_404(PersonnelRecord, pk=record_id)
    form = PersonnelDocumentForm(request.POST, request.FILES)

    if form.is_valid():
        document = form.save(commit=False)
        document.record = record
        document.uploaded_by = request.user
        document.save()
        messages.success(request, "Документ загружен.")
    else:
        messages.error(request, "Не удалось загрузить документ. Проверь заполнение формы.")

    return redirect("personnel:record_detail", pk=record.pk)


@login_required
def document_download(request: HttpRequest, pk: int) -> FileResponse:
    document = get_object_or_404(PersonnelDocument, pk=pk)

    if not document.file:
        raise Http404("Файл не найден.")

    if not default_storage.exists(document.file.name):
        raise Http404("Файл не найден в хранилище.")

    return FileResponse(
        document.file.open("rb"),
        as_attachment=True,
        filename=document.filename,
    )


@login_required
@require_POST
def document_delete(request: HttpRequest, pk: int) -> HttpResponse:
    document = get_object_or_404(PersonnelDocument, pk=pk)
    record_pk = document.record_id
    document.delete()
    messages.success(request, "Документ удален.")
    return redirect("personnel:record_detail", pk=record_pk)