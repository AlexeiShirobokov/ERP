import json
import logging
import os
from itertools import zip_longest
from types import SimpleNamespace

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.mail import send_mail
from django.db.models import Max, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)
from openpyxl import Workbook

from .forms import ResumeCandidateDocumentForm, ResumeCandidateForm, ResumeStageForm
from .models import (
    DEFAULT_STAGE_DEFINITIONS,
    ResumeCandidate,
    ResumeCandidateDocument,
    ResumeStage,
)


logger = logging.getLogger(__name__)


def get_stage_items(include_codes=None):
    include_codes = set(filter(None, include_codes or []))

    stage_map = {}
    for item in DEFAULT_STAGE_DEFINITIONS:
        stage_map[item['code']] = {
            'code': item['code'],
            'name': item['label'],
            'sort_order': item.get('sort_order', 100),
            'is_active': True,
            'notify_email': (item.get('emails') or [''])[0] if item.get('emails') else '',
            'responsible_user': None,
        }

    db_stages = ResumeStage.objects.select_related('responsible_user').all().order_by('sort_order', 'id')
    for stage in db_stages:
        stage_map[stage.code] = {
            'code': stage.code,
            'name': stage.name,
            'sort_order': stage.sort_order,
            'is_active': stage.is_active,
            'notify_email': stage.notify_email,
            'responsible_user': stage.responsible_user,
        }

    stages = [
        SimpleNamespace(**data)
        for data in stage_map.values()
        if data['is_active'] or data['code'] in include_codes
    ]
    stages.sort(key=lambda item: (item.sort_order, item.name.lower()))
    return stages


def get_stage_choices(include_codes=None):
    return [(item.code, item.name) for item in get_stage_items(include_codes=include_codes)]


def send_stage_notification(candidate, stage_code, moved_by):
    recipients = ResumeCandidate.get_stage_notification_emails(stage_code)
    if not recipients:
        return

    stage_name = ResumeCandidate.get_stage_label(stage_code)

    moved_by_name = ''
    if moved_by:
        moved_by_name = (moved_by.get_full_name() or '').strip() or getattr(moved_by, 'username', '')
    if not moved_by_name:
        moved_by_name = 'Система'

    subject = f'Кандидат переведен на этап: {stage_name}'
    message = (
        f'Кандидат: {candidate.full_name}\n'
        f'Должность: {candidate.position or "-"}\n'
        f'Новый этап: {stage_name}\n'
        f'Переместил: {moved_by_name}\n'
        f'ID кандидата: {candidate.pk}\n'
    )

    from_email = (
        getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        or getattr(settings, 'EMAIL_HOST_USER', None)
        or 'noreply@localhost'
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            'Ошибка отправки уведомления по кандидату %s на этап %s',
            candidate.pk,
            stage_code,
        )


def get_resume_candidates_queryset(request):
    queryset = ResumeCandidate.objects.all().prefetch_related('documents').order_by('-date', '-id')

    q = request.GET.get('q', '').strip()
    stage = request.GET.get('stage', '').strip()
    medical = request.GET.get('medical', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if q:
        queryset = queryset.filter(
            Q(full_name__icontains=q)
            | Q(hh_vacancy__icontains=q)
            | Q(position__icontains=q)
            | Q(contacts__icontains=q)
            | Q(ticket__icontains=q)
        )

    if stage:
        queryset = queryset.filter(stage=stage)

    if medical:
        queryset = queryset.filter(medical_commission=medical)

    if date_from:
        queryset = queryset.filter(date__gte=date_from)

    if date_to:
        queryset = queryset.filter(date__lte=date_to)

    return queryset


class ResumeStageListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ResumeStage
    template_name = 'personnel/resume_stage_list.html'
    context_object_name = 'stages'
    permission_required = 'personnel.view_resumestage'
    raise_exception = True

    def get_queryset(self):
        return ResumeStage.objects.select_related('responsible_user').order_by('sort_order', 'id')


class ResumeStageCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = ResumeStage
    form_class = ResumeStageForm
    template_name = 'personnel/resume_stage_form.html'
    success_url = reverse_lazy('personnel:resume_stage_list')
    permission_required = 'personnel.add_resumestage'
    raise_exception = True


class ResumeStageUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = ResumeStage
    form_class = ResumeStageForm
    template_name = 'personnel/resume_stage_form.html'
    success_url = reverse_lazy('personnel:resume_stage_list')
    permission_required = 'personnel.change_resumestage'
    raise_exception = True


class ResumeStageDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = ResumeStage
    template_name = 'personnel/resume_stage_confirm_delete.html'
    success_url = reverse_lazy('personnel:resume_stage_list')
    permission_required = 'personnel.delete_resumestage'
    raise_exception = True

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        if ResumeCandidate.objects.filter(stage=self.object.code).exists():
            messages.error(
                request,
                'Нельзя удалить этап, который используется в карточках кандидатов.',
            )
            return redirect('personnel:resume_stage_list')

        return super().post(request, *args, **kwargs)


class ResumeCandidateListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ResumeCandidate
    template_name = 'personnel/resume_candidate_list.html'
    context_object_name = 'candidates'
    paginate_by = 50
    permission_required = 'personnel.view_resumecandidate'
    raise_exception = True

    def get_queryset(self):
        return get_resume_candidates_queryset(self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        context['stage'] = self.request.GET.get('stage', '')
        context['medical'] = self.request.GET.get('medical', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        context['stages'] = get_stage_items()
        context['medical_choices'] = ResumeCandidate.MEDICAL_CHOICES
        return context


class ResumeCandidateExportExcelView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'personnel.view_resumecandidate'
    raise_exception = True

    def get(self, request, *args, **kwargs):
        queryset = get_resume_candidates_queryset(request)

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Кандидаты'

        headers = [
            '№',
            'Дата',
            'ФИО',
            'Соискатель по вакансии на hh.ru',
            'Должность',
            'Контакты',
            'Мед комиссия',
            'Комментарий',
            'Год рождения',
            'Квалификация',
            'Примечание',
            'ОТИПБ',
            'Причина отказа',
            'Билет',
            'Этап',
            'Документы',
        ]
        sheet.append(headers)

        for item in queryset:
            sheet.append([
                item.number or item.id,
                item.date.strftime('%d.%m.%Y') if item.date else '',
                item.full_name or '',
                item.hh_vacancy or '',
                item.position or '',
                item.contacts or '',
                item.get_medical_commission_display() if item.medical_commission else '',
                item.comment or '',
                item.birth_year or '',
                item.qualification or '',
                item.note or '',
                item.otipb or '',
                item.refusal_reason or '',
                item.ticket or '',
                item.stage_name,
                item.documents.count(),
            ])

        for column_cells in sheet.columns:
            max_length = 0
            column_letter = column_cells[0].column_letter
            for cell in column_cells:
                value = '' if cell.value is None else str(cell.value)
                if len(value) > max_length:
                    max_length = len(value)
            sheet.column_dimensions[column_letter].width = min(max_length + 2, 40)

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="resume_candidates.xlsx"'
        workbook.save(response)
        return response


class ResumeCandidateKanbanView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'personnel/resume_candidate_kanban.html'
    permission_required = 'personnel.view_resumecandidate'
    raise_exception = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        columns = []
        for stage_item in get_stage_items():
            items = ResumeCandidate.objects.filter(stage=stage_item.code).order_by('sort_order', '-date', '-id')
            columns.append({
                'code': stage_item.code,
                'name': stage_item.name,
                'items': items,
                'count': items.count(),
            })

        context['columns'] = columns
        return context


class ResumeCandidateDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = ResumeCandidate
    template_name = 'personnel/resume_candidate_detail.html'
    context_object_name = 'record'
    permission_required = 'personnel.view_resumecandidate'
    raise_exception = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['documents'] = self.object.documents.all()
        context['document_form'] = ResumeCandidateDocumentForm()
        return context


class ResumeCandidateCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = ResumeCandidate
    form_class = ResumeCandidateForm
    template_name = 'personnel/resume_candidate_form.html'
    permission_required = 'personnel.add_resumecandidate'
    raise_exception = True

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if 'stage' in form.fields:
            choices = get_stage_choices()
            form.fields['stage'].widget = forms.Select(choices=choices)
            form.fields['stage'].choices = choices
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['documents'] = []
        context['document_form'] = None
        context['is_create'] = True
        return context

    def form_valid(self, form):
        response = super().form_valid(form)

        titles = self.request.POST.getlist('create_document_titles')
        comments = self.request.POST.getlist('create_document_comments')
        files = self.request.FILES.getlist('create_document_files')

        for title, comment, uploaded_file in zip_longest(titles, comments, files, fillvalue=None):
            if not uploaded_file:
                continue

            ResumeCandidateDocument.objects.create(
                record=self.object,
                title=(title or '').strip() or uploaded_file.name,
                file=uploaded_file,
                comment=(comment or '').strip(),
                uploaded_by=self.request.user if self.request.user.is_authenticated else None,
            )

        return response

    def get_success_url(self):
        return reverse_lazy('personnel:resume_candidate_edit', kwargs={'pk': self.object.pk})


class ResumeCandidateUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = ResumeCandidate
    form_class = ResumeCandidateForm
    template_name = 'personnel/resume_candidate_form.html'
    success_url = reverse_lazy('personnel:resume_candidate_list')
    permission_required = 'personnel.change_resumecandidate'
    raise_exception = True

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if 'stage' in form.fields:
            current_stage = getattr(self.object, 'stage', '')
            choices = get_stage_choices(include_codes=[current_stage] if current_stage else None)
            if current_stage and current_stage not in {code for code, _ in choices}:
                choices.append((current_stage, ResumeCandidate.get_stage_label(current_stage)))

            form.fields['stage'].widget = forms.Select(choices=choices)
            form.fields['stage'].choices = choices
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['documents'] = self.object.documents.all()
        context['document_form'] = ResumeCandidateDocumentForm()
        context['is_create'] = False
        return context


class ResumeCandidateDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = ResumeCandidate
    template_name = 'personnel/resume_candidate_confirm_delete.html'
    success_url = reverse_lazy('personnel:resume_candidate_list')
    permission_required = 'personnel.delete_resumecandidate'
    raise_exception = True


class ResumeCandidateStageUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'personnel.change_resumecandidate'
    raise_exception = True

    def post(self, request, pk, stage):
        candidate = get_object_or_404(ResumeCandidate, pk=pk)
        valid_stages = {item.code for item in get_stage_items(include_codes=[candidate.stage])}

        if stage not in valid_stages:
            return JsonResponse({'status': 'error', 'message': 'Некорректный этап'}, status=400)

        old_stage = candidate.stage
        candidate.stage = stage
        last_sort = ResumeCandidate.objects.filter(stage=stage).aggregate(
            max_sort=Max('sort_order')
        )['max_sort'] or 0
        candidate.sort_order = last_sort + 1
        candidate.save()

        if old_stage != stage:
            send_stage_notification(candidate, stage, request.user)

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'ok'})

        return redirect('personnel:resume_candidate_kanban')


class ResumeCandidateKanbanReorderView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'personnel.change_resumecandidate'
    raise_exception = True

    def post(self, request):
        try:
            data = json.loads(request.body)
            candidate_id = data.get('candidate_id')
            new_stage = data.get('new_stage')
            ordered_ids = data.get('ordered_ids', [])

            if not candidate_id or not new_stage or not isinstance(ordered_ids, list):
                return JsonResponse({'status': 'error', 'message': 'Некорректные данные'}, status=400)

            valid_stages = {item.code for item in get_stage_items()}
            if new_stage not in valid_stages:
                return JsonResponse({'status': 'error', 'message': 'Некорректный этап'}, status=400)

            candidate = get_object_or_404(ResumeCandidate, pk=candidate_id)
            old_stage = candidate.stage

            candidate.stage = new_stage
            candidate.save()

            for index, item_id in enumerate(ordered_ids, start=1):
                ResumeCandidate.objects.filter(pk=item_id).update(
                    stage=new_stage,
                    sort_order=index,
                )

            if old_stage != new_stage:
                send_stage_notification(candidate, new_stage, request.user)

            return JsonResponse({'status': 'ok'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


class ResumeCandidateDocumentUploadView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'personnel.change_resumecandidate'
    raise_exception = True

    def post(self, request, pk):
        record = get_object_or_404(ResumeCandidate, pk=pk)
        form = ResumeCandidateDocumentForm(request.POST, request.FILES)

        if form.is_valid():
            document = form.save(commit=False)
            document.record = record
            document.uploaded_by = request.user
            document.save()

        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)

        return redirect('personnel:resume_candidate_edit', pk=record.pk)


class ResumeCandidateDocumentDownloadView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'personnel.view_resumecandidate'
    raise_exception = True

    def get(self, request, pk):
        document = get_object_or_404(ResumeCandidateDocument, pk=pk)

        if not document.file:
            raise Http404('Файл не найден')

        file_handle = document.file.open('rb')
        filename = os.path.basename(document.file.name)
        return FileResponse(file_handle, as_attachment=True, filename=filename)


class ResumeCandidateDocumentDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'personnel.change_resumecandidate'
    raise_exception = True

    def post(self, request, pk):
        document = get_object_or_404(ResumeCandidateDocument, pk=pk)
        record_pk = document.record.pk

        if document.file:
            document.file.delete(save=False)

        document.delete()

        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)

        return redirect('personnel:resume_candidate_edit', pk=record_pk)