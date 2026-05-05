import json
import logging
import mimetypes
import os
import threading
from collections import defaultdict
from itertools import zip_longest
from types import SimpleNamespace

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db.models import Max, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
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

from .forms import (
    POSITION_OPTIONS,
    ResumeCandidateDocumentForm,
    ResumeCandidateForm,
    ResumeStageForm,
)
from .models import (
    DEFAULT_STAGE_DEFINITIONS,
    CandidateSourceRecord,
    ResumeCandidate,
    ResumeCandidateDocument,
    ResumeStage,
    normalize_full_name,
)

logger = logging.getLogger(__name__)

KANBAN_URL = '/personnel/resume/kanban/'
CANDIDATE_LIST_URL = '/personnel/resume/'
STAGES_URL = '/personnel/stages/'

DEPARTMENT_APPROVAL_STAGES = {
    'mechanic_approval',
    'geology_approval',
    'surveyor_approval',
    'transport_approval',
}


def candidate_detail_url(pk):
    return f'/personnel/resume/{pk}/'


def candidate_edit_url(pk):
    return f'/personnel/resume/{pk}/?edit=1'


def get_user_display_name(user):
    if not user:
        return 'Система'
    return (user.get_full_name() or '').strip() or getattr(user, 'username', '') or 'Система'


def get_stage_items(include_codes=None):
    include_codes = set(filter(None, include_codes or []))

    stage_map = {}

    for item in DEFAULT_STAGE_DEFINITIONS:
        stage_map[item['code']] = {
            'code': item['code'],
            'name': item['label'],
            'sort_order': item.get('sort_order', 100),
            'is_active': True,
            'notify_email': (
                (item.get('emails') or [''])[0]
                if item.get('emails')
                else ''
            ),
            'responsible_user': None,
        }

    db_stages = (
        ResumeStage.objects
        .select_related('responsible_user')
        .all()
        .order_by('sort_order', 'id')
    )

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
    return [
        (item.code, item.name)
        for item in get_stage_items(include_codes=include_codes)
    ]


def send_stage_notification(candidate, stage_code, moved_by, request=None):
    recipients = ResumeCandidate.get_stage_notification_emails(stage_code)
    if not recipients:
        return

    stage_name = ResumeCandidate.get_stage_label(stage_code)
    moved_by_name = get_user_display_name(moved_by)

    relative_url = candidate_detail_url(candidate.pk)
    site_url = getattr(settings, 'SITE_URL', '').rstrip('/')

    if site_url:
        candidate_url = f'{site_url}{relative_url}'
    elif request is not None:
        candidate_url = request.build_absolute_uri(relative_url)
    else:
        candidate_url = relative_url

    subject = f'Кандидат переведен на этап: {stage_name}'
    message = (
        f'Кандидат: {candidate.full_name}\n'
        f'Должность: {candidate.position or "-"}\n'
        f'Новый этап: {stage_name}\n'
        f'Переместил: {moved_by_name}\n'
        f'ID кандидата: {candidate.pk}\n'
        f'Ссылка на карточку: {candidate_url}\n'
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


def send_stage_notification_async(candidate, stage_code, moved_by, request=None):
    """
    Отправляем уведомление в отдельном потоке,
    чтобы сохранение карточки не ждало SMTP.
    """
    thread = threading.Thread(
        target=send_stage_notification,
        args=(candidate, stage_code, moved_by, request),
        daemon=True,
    )
    thread.start()


def get_next_stage_after_card_save(candidate, old_stage):
    """
    Автоматический маршрут кандидата при сохранении карточки.

    Правила:
    1. HR создает/сохраняет карточку -> Служба безопасности.
    2. Служба безопасности:
       - если "Не согласовано" -> Отказ;
       - иначе -> ОТИПБ.
    3. ОТИПБ:
       - если "Не согласовано" -> Отказ;
       - если выбран отдел согласования -> в этот отдел;
       - если отдел не выбран -> Направление на медосмотр.
    4. ОГМ / Геологический отдел / Отдел маркшейдера / Транспортный цех:
       - если "Не согласован к вызову" -> Отказ;
       - если "Согласован к вызову" -> Направление на медосмотр;
       - иначе остаётся на текущем этапе.
    """

    if old_stage == 'phone_interview':
        return 'security_service'

    if old_stage == 'security_service':
        if candidate.security_approval == 'rejected':
            return 'refusal'
        return 'otipb'

    if old_stage == 'otipb':
        if candidate.otipb_approval == 'rejected':
            return 'refusal'

        approval_department = (candidate.approval_department or '').strip()

        if approval_department in DEPARTMENT_APPROVAL_STAGES:
            return approval_department

        return 'medical_direction'

    if old_stage in DEPARTMENT_APPROVAL_STAGES:
        if candidate.department_call_approval == 'rejected':
            return 'refusal'

        if candidate.department_call_approval == 'approved':
            return 'medical_direction'

        return old_stage

    return old_stage


def move_candidate_to_stage(candidate, new_stage):
    """
    Переносит кандидата в конец нужной колонки канбана.
    Возвращает True, если этап реально изменился.
    """
    if not new_stage or candidate.stage == new_stage:
        return False

    last_sort = (
        ResumeCandidate.objects
        .filter(stage=new_stage)
        .aggregate(max_sort=Max('sort_order'))['max_sort'] or 0
    )

    candidate.stage = new_stage
    candidate.sort_order = last_sort + 1

    return True


def get_resume_candidates_queryset(request):
    queryset = (
        ResumeCandidate.objects
        .select_related('created_by', 'updated_by')
        .prefetch_related('documents')
        .order_by('-date', '-id')
    )

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
            | Q(note__icontains=q)
            | Q(refusal_reason__icontains=q)
            | Q(security_comment__icontains=q)
            | Q(security_refusal_reason__icontains=q)
            | Q(otipb_comment__icontains=q)
            | Q(otipb_refusal_reason__icontains=q)
            | Q(department_call_comment__icontains=q)
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
        return (
            ResumeStage.objects
            .select_related('responsible_user')
            .order_by('sort_order', 'id')
        )


class ResumeStageCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = ResumeStage
    form_class = ResumeStageForm
    template_name = 'personnel/resume_stage_form.html'
    success_url = STAGES_URL
    permission_required = 'personnel.add_resumestage'
    raise_exception = True


class ResumeStageUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = ResumeStage
    form_class = ResumeStageForm
    template_name = 'personnel/resume_stage_form.html'
    success_url = STAGES_URL
    permission_required = 'personnel.change_resumestage'
    raise_exception = True


class ResumeStageDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = ResumeStage
    template_name = 'personnel/resume_stage_confirm_delete.html'
    success_url = STAGES_URL
    permission_required = 'personnel.delete_resumestage'
    raise_exception = True

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        if ResumeCandidate.objects.filter(stage=self.object.code).exists():
            messages.error(
                request,
                'Нельзя удалить этап процесса, который используется в карточках кандидатов.',
            )
            return redirect(STAGES_URL)

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
            'Опыт работы',
            'Контакты',
            'Мед комиссия',
            'Комментарий',
            'Год рождения',
            'Квалификация',
            'Примечание',
            'ОТИПБ: статус',
            'ОТИПБ: комментарий',
            'ОТИПБ: причина отказа',
            'Отдел',
            'Служба безопасности',
            'Комментарий службы безопасности',
            'Причина отказа службы безопасности',
            'Согласование к вызову',
            'Комментарий отдела',
            'Причина отказа',
            'Билет',
            'Расчетная дата приезда',
            'Этап процесса',
            'Создал',
            'Последний редактор',
            'Документы',
        ]
        sheet.append(headers)

        for item in queryset:
            sheet.append(
                [
                    item.number or item.id,
                    item.date.strftime('%d.%m.%Y') if item.date else '',
                    item.full_name or '',
                    item.hh_vacancy or '',
                    item.position or '',
                    item.work_experience or '',
                    item.contacts or '',
                    item.get_medical_commission_display() if item.medical_commission else '',
                    item.comment or '',
                    item.birth_year or '',
                    item.qualification or '',
                    item.note or '',
                    item.get_otipb_approval_display() if item.otipb_approval else '',
                    item.otipb_comment or '',
                    item.otipb_refusal_reason or '',
                    item.current_department_name or '',
                    item.get_security_approval_display() if item.security_approval else '',
                    item.security_comment or '',
                    item.security_refusal_reason or '',
                    item.get_department_call_approval_display() if item.department_call_approval else '',
                    item.department_call_comment or '',
                    item.refusal_reason or '',
                    item.ticket or '',
                    item.estimated_arrival_date.strftime('%d.%m.%Y') if item.estimated_arrival_date else '',
                    item.stage_name,
                    get_user_display_name(item.created_by) if item.created_by else '',
                    get_user_display_name(item.updated_by) if item.updated_by else '',
                    item.documents.count(),
                ]
            )

        for column_cells in sheet.columns:
            max_length = 0
            column_letter = column_cells[0].column_letter

            for cell in column_cells:
                value = '' if cell.value is None else str(cell.value)
                if len(value) > max_length:
                    max_length = len(value)

            sheet.column_dimensions[column_letter].width = min(max_length + 2, 40)

        response = HttpResponse(
            content_type=(
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
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

        selected_created_by = self.request.GET.get('created_by', '').strip()
        selected_q = self.request.GET.get('q', '').strip()
        stages = get_stage_items()

        base_queryset = (
            ResumeCandidate.objects
            .select_related('created_by')
            .only(
                'id',
                'number',
                'date',
                'full_name',
                'position',
                'contacts',
                'medical_commission',
                'security_approval',
                'otipb_approval',
                'birth_year',
                'ticket',
                'estimated_arrival_date',
                'comment',
                'stage',
                'sort_order',
                'created_by__id',
                'created_by__username',
                'created_by__first_name',
                'created_by__last_name',
            )
            .order_by('stage', 'sort_order', '-date', '-id')
        )

        if selected_created_by:
            base_queryset = base_queryset.filter(created_by_id=selected_created_by)

        if selected_q:
            base_queryset = base_queryset.filter(
                Q(full_name__icontains=selected_q)
                | Q(position__icontains=selected_q)
                | Q(contacts__icontains=selected_q)
                | Q(ticket__icontains=selected_q)
                | Q(comment__icontains=selected_q)
                | Q(note__icontains=selected_q)
                | Q(refusal_reason__icontains=selected_q)
                | Q(security_comment__icontains=selected_q)
                | Q(otipb_comment__icontains=selected_q)
                | Q(department_call_comment__icontains=selected_q)
            )

        items_by_stage = defaultdict(list)

        for candidate in base_queryset:
            items_by_stage[candidate.stage].append(candidate)

        columns = []

        for stage_item in stages:
            stage_items = items_by_stage.get(stage_item.code, [])

            columns.append(
                {
                    'code': stage_item.code,
                    'name': stage_item.name,
                    'items': stage_items,
                    'count': len(stage_items),
                }
            )

        User = get_user_model()

        creator_ids = (
            ResumeCandidate.objects
            .exclude(created_by__isnull=True)
            .values_list('created_by_id', flat=True)
            .distinct()
        )

        creators = (
            User.objects
            .filter(id__in=creator_ids)
            .only('id', 'username', 'first_name', 'last_name')
            .order_by('last_name', 'first_name', 'username')
        )

        context['columns'] = columns
        context['creators'] = creators
        context['selected_created_by'] = selected_created_by
        context['selected_q'] = selected_q
        return context

class ResumeCandidateKanbanDataView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'personnel.view_resumecandidate'
    raise_exception = True

    def get(self, request, *args, **kwargs):
        selected_created_by = request.GET.get('created_by', '').strip()
        selected_q = request.GET.get('q', '').strip()
        stages = get_stage_items()

        queryset = (
            ResumeCandidate.objects
            .select_related('created_by')
            .only(
                'id',
                'number',
                'date',
                'full_name',
                'position',
                'contacts',
                'medical_commission',
                'security_approval',
                'otipb_approval',
                'birth_year',
                'ticket',
                'estimated_arrival_date',
                'comment',
                'stage',
                'sort_order',
                'created_by__id',
                'created_by__username',
                'created_by__first_name',
                'created_by__last_name',
            )
            .order_by('stage', 'sort_order', '-date', '-id')
        )

        if selected_created_by:
            queryset = queryset.filter(created_by_id=selected_created_by)

        if selected_q:
            queryset = queryset.filter(
                Q(full_name__icontains=selected_q)
                | Q(position__icontains=selected_q)
                | Q(contacts__icontains=selected_q)
                | Q(ticket__icontains=selected_q)
                | Q(comment__icontains=selected_q)
                | Q(note__icontains=selected_q)
                | Q(refusal_reason__icontains=selected_q)
                | Q(security_comment__icontains=selected_q)
                | Q(otipb_comment__icontains=selected_q)
                | Q(department_call_comment__icontains=selected_q)
            )

        items_by_stage = defaultdict(list)

        for candidate in queryset:
            created_by_name = ''

            if candidate.created_by_id:
                created_by_name = (
                    candidate.created_by.get_full_name()
                    or candidate.created_by.username
                )

            items_by_stage[candidate.stage].append(
                {
                    'id': candidate.id,
                    'stage': candidate.stage or '',
                    'full_name': candidate.full_name or '',
                    'position': candidate.position or 'Без должности',
                    'contacts': candidate.contacts or 'Нет контактов',
                    'medical_commission': candidate.get_medical_commission_display(),
                    'security_approval': candidate.security_approval or '',
                    'otipb_approval': candidate.otipb_approval or '',
                    'birth_year': candidate.birth_year or '',
                    'ticket': candidate.ticket or '',
                    'estimated_arrival_date': (
                        candidate.estimated_arrival_date.strftime('%d.%m.%Y')
                        if candidate.estimated_arrival_date
                        else ''
                    ),
                    'comment': candidate.comment or '',
                    'created_by': created_by_name,
                    'detail_url': reverse(
                        'personnel:resume_candidate_detail',
                        kwargs={'pk': candidate.pk},
                    ),
                }
            )

        columns = []

        for stage_item in stages:
            items = items_by_stage.get(stage_item.code, [])

            columns.append(
                {
                    'code': stage_item.code,
                    'name': stage_item.name,
                    'count': len(items),
                    'items': items,
                }
            )

        return JsonResponse(
            {
                'status': 'ok',
                'columns': columns,
            }
        )

class ResumeCandidateDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """
    Карточка кандидата.
    GET /personnel/resume/<pk>/ — просмотр карточки.
    GET /personnel/resume/<pk>/?edit=1 — редактирование в этой же карточке.
    POST /personnel/resume/<pk>/ — сохранение изменений из карточки.
    """
    model = ResumeCandidate
    template_name = 'personnel/resume_candidate_detail.html'
    context_object_name = 'record'
    permission_required = 'personnel.view_resumecandidate'
    raise_exception = True

    def get_queryset(self):
        return (
            ResumeCandidate.objects
            .select_related('created_by', 'updated_by')
            .prefetch_related('documents')
        )

    def get_candidate_form(self, data=None, files=None):
        form = ResumeCandidateForm(
            data=data,
            files=files,
            instance=self.object,
        )

        if 'stage' in form.fields:
            current_stage = getattr(self.object, 'stage', '')
            choices = get_stage_choices(
                include_codes=[current_stage] if current_stage else None
            )

            if current_stage and current_stage not in {code for code, _ in choices}:
                choices.append(
                    (
                        current_stage,
                        ResumeCandidate.get_stage_label(current_stage),
                    )
                )

            form.fields['stage'].widget = forms.Select(choices=choices)
            form.fields['stage'].choices = choices

        return form

    def get_context_data(self, **kwargs):
        form = kwargs.pop('form', None)
        edit_mode = kwargs.pop('edit_mode', False)

        context = super().get_context_data(**kwargs)
        context['documents'] = self.object.documents.all()
        context['document_form'] = ResumeCandidateDocumentForm()
        context['edit_mode'] = edit_mode or self.request.GET.get('edit') == '1'
        context['position_options'] = POSITION_OPTIONS

        if form is None:
            form = self.get_candidate_form()

        context['form'] = form
        return context

    def post(self, request, *args, **kwargs):
        if not request.user.has_perm('personnel.change_resumecandidate'):
            raise PermissionDenied

        self.object = self.get_object()

        form = self.get_candidate_form(
            data=request.POST,
            files=request.FILES,
        )

        if form.is_valid():
            old_stage = self.object.stage

            candidate = form.save(commit=False)

            if request.user.is_authenticated:
                candidate.updated_by = request.user

            next_stage = get_next_stage_after_card_save(candidate, old_stage)
            stage_changed = move_candidate_to_stage(candidate, next_stage)

            candidate.save()
            form.save_m2m()

            if stage_changed:
                send_stage_notification_async(candidate, candidate.stage, request.user, request)

            return redirect(KANBAN_URL)

        messages.error(request, 'Карточка не сохранена. Проверьте ошибки в форме.')

        return self.render_to_response(
            self.get_context_data(
                form=form,
                edit_mode=True,
            )
        )


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
            form.fields['stage'].required = False
            form.fields['stage'].initial = 'phone_interview'

        if 'security_approval' in form.fields:
            form.fields['security_approval'].required = False
            form.fields['security_approval'].initial = 'pending'

        if 'otipb_approval' in form.fields:
            form.fields['otipb_approval'].required = False
            form.fields['otipb_approval'].initial = 'pending'

        if 'department_call_approval' in form.fields:
            form.fields['department_call_approval'].required = False
            form.fields['department_call_approval'].initial = 'pending'

        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['documents'] = []
        context['document_form'] = None
        context['is_create'] = True
        context['position_options'] = POSITION_OPTIONS
        return context

    def form_invalid(self, form):
        messages.error(
            self.request,
            'Карточка не сохранена. Проверьте обязательные поля.',
        )
        logger.error('Ошибки создания карточки кандидата: %s', form.errors.as_json())
        return super().form_invalid(form)

    def form_valid(self, form):
        self.object = form.save(commit=False)

        self.object.stage = 'security_service'
        self.object.sort_order = 0

        if not self.object.security_approval:
            self.object.security_approval = 'pending'

        if not self.object.otipb_approval:
            self.object.otipb_approval = 'pending'

        if not self.object.department_call_approval:
            self.object.department_call_approval = 'pending'

        if self.request.user.is_authenticated:
            self.object.created_by = self.request.user
            self.object.updated_by = self.request.user

        self.object.save()
        form.save_m2m()

        titles = self.request.POST.getlist('create_document_titles')
        comments = self.request.POST.getlist('create_document_comments')
        files = self.request.FILES.getlist('create_document_files')

        for title, comment, uploaded_file in zip_longest(
            titles,
            comments,
            files,
            fillvalue=None,
        ):
            if not uploaded_file:
                continue

            ResumeCandidateDocument.objects.create(
                record=self.object,
                title=(title or '').strip() or uploaded_file.name,
                file=uploaded_file,
                comment=(comment or '').strip(),
                uploaded_by=(
                    self.request.user
                    if self.request.user.is_authenticated
                    else None
                ),
            )

        send_stage_notification_async(
            self.object,
            self.object.stage,
            self.request.user,
            self.request,
        )

        return redirect(KANBAN_URL)

    def get_success_url(self):
        return KANBAN_URL


class ResumeCandidateUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """
    Старый адрес /personnel/resume/<pk>/edit/ оставлен для совместимости.
    Чтобы окно не менялось, при открытии этого URL переводим пользователя
    в карточку кандидата в режим редактирования.
    """
    model = ResumeCandidate
    form_class = ResumeCandidateForm
    template_name = 'personnel/resume_candidate_form.html'
    permission_required = 'personnel.change_resumecandidate'
    raise_exception = True

    def get(self, request, *args, **kwargs):
        candidate = self.get_object()
        return redirect(candidate_edit_url(candidate.pk))

    def get_form(self, form_class=None):
        form = super().get_form(form_class)

        if 'stage' in form.fields:
            current_stage = getattr(self.object, 'stage', '')
            choices = get_stage_choices(
                include_codes=[current_stage] if current_stage else None
            )

            if current_stage and current_stage not in {code for code, _ in choices}:
                choices.append(
                    (
                        current_stage,
                        ResumeCandidate.get_stage_label(current_stage),
                    )
                )

            form.fields['stage'].widget = forms.Select(choices=choices)
            form.fields['stage'].choices = choices

        return form

    def form_valid(self, form):
        old_stage = self.object.stage

        self.object = form.save(commit=False)
        self.object.updated_by = self.request.user

        next_stage = get_next_stage_after_card_save(self.object, old_stage)
        stage_changed = move_candidate_to_stage(self.object, next_stage)

        self.object.save()
        form.save_m2m()

        if stage_changed:
            send_stage_notification_async(
                self.object,
                self.object.stage,
                self.request.user,
                self.request,
            )

        return redirect(self.get_success_url())

    def get_success_url(self):
        return KANBAN_URL


class ResumeCandidateDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = ResumeCandidate
    template_name = 'personnel/resume_candidate_confirm_delete.html'
    success_url = KANBAN_URL
    permission_required = 'personnel.delete_resumecandidate'
    raise_exception = True


class ResumeCandidateStageUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'personnel.change_resumecandidate'
    raise_exception = True

    def post(self, request, pk, stage):
        candidate = get_object_or_404(ResumeCandidate, pk=pk)
        valid_stages = {
            item.code
            for item in get_stage_items(include_codes=[candidate.stage])
        }

        if stage not in valid_stages:
            return JsonResponse(
                {
                    'status': 'error',
                    'message': 'Некорректный этап процесса',
                },
                status=400,
            )

        old_stage = candidate.stage
        candidate.stage = stage
        candidate.updated_by = request.user

        last_sort = (
            ResumeCandidate.objects
            .filter(stage=stage)
            .aggregate(max_sort=Max('sort_order'))['max_sort'] or 0
        )
        candidate.sort_order = last_sort + 1
        candidate.save()

        if old_stage != stage:
            send_stage_notification_async(candidate, stage, request.user, request)

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'ok'})

        return redirect(KANBAN_URL)


class ResumeCandidateKanbanReorderView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'personnel.change_resumecandidate'
    raise_exception = True

    def post(self, request):
        try:
            data = json.loads(request.body)
            candidate_id = data.get('candidate_id')
            new_stage = data.get('new_stage')
            ordered_ids = data.get('ordered_ids', [])

            if not candidate_id or not new_stage:
                return JsonResponse(
                    {
                        'status': 'error',
                        'message': 'Некорректные данные',
                    },
                    status=400,
                )

            valid_stages = {item.code for item in get_stage_items()}

            if new_stage not in valid_stages:
                return JsonResponse(
                    {
                        'status': 'error',
                        'message': 'Некорректный этап процесса',
                    },
                    status=400,
                )

            candidate = get_object_or_404(ResumeCandidate, pk=candidate_id)
            old_stage = candidate.stage

            if old_stage != new_stage:
                last_sort = (
                    ResumeCandidate.objects
                    .filter(stage=new_stage)
                    .aggregate(max_sort=Max('sort_order'))['max_sort'] or 0
                )

                candidate.stage = new_stage
                candidate.sort_order = last_sort + 1
                candidate.updated_by = request.user
                candidate.save()

                send_stage_notification_async(candidate, new_stage, request.user, request)
            else:
                candidate.updated_by = request.user
                candidate.save(update_fields=['updated_by', 'updated_at'])

            if isinstance(ordered_ids, list) and len(ordered_ids) > 1:
                for index, item_id in enumerate(ordered_ids, start=1):
                    ResumeCandidate.objects.filter(pk=item_id).update(
                        stage=new_stage,
                        sort_order=index,
                    )

            return JsonResponse({'status': 'ok'})

        except Exception as e:
            logger.exception('Ошибка изменения порядка канбана')
            return JsonResponse(
                {
                    'status': 'error',
                    'message': str(e),
                },
                status=500,
            )

class ResumeCandidateCheckOtipbView(LoginRequiredMixin, View):
    """
    AJAX-проверка кандидата по ФИО.
    Сначала ищем в импортированной базе CandidateSourceRecord.
    Если там нет — ищем среди уже заведённых карточек ResumeCandidate.
    """

    def get(self, request, *args, **kwargs):
        full_name = request.GET.get('full_name', '').strip()

        if not full_name:
            return JsonResponse(
                {
                    'success': False,
                    'found': False,
                    'message': 'ФИО не заполнено.',
                    'data': {},
                },
                status=400,
            )

        source_record = CandidateSourceRecord.get_latest_by_full_name(full_name)

        if source_record:
            data = source_record.as_autofill_data()
            data['source_type'] = 'candidate_source'
            data['source_label'] = 'Импортированная база кандидатов'

            return JsonResponse(
                {
                    'success': True,
                    'found': True,
                    'message': 'Кандидат найден в импортированной базе.',
                    'data': data,
                }
            )

        target_name = normalize_full_name(full_name)
        candidate = (
            ResumeCandidate.objects
            .filter(full_name__iexact=full_name)
            .order_by('-updated_at', '-id')
            .first()
        )

        if not candidate and target_name:
            for item in ResumeCandidate.objects.only('id', 'full_name').order_by('-updated_at', '-id')[:2000]:
                if normalize_full_name(item.full_name) == target_name:
                    candidate = item
                    break

        if candidate:
            data = candidate.as_autofill_data()
            data['source_type'] = 'resume_candidate'
            data['source_label'] = 'Ранее заведённая карточка'

            return JsonResponse(
                {
                    'success': True,
                    'found': True,
                    'message': 'Кандидат найден среди ранее заведённых карточек.',
                    'data': data,
                }
            )

        return JsonResponse(
            {
                'success': True,
                'found': False,
                'message': 'Совпадений не найдено.',
                'data': {},
            }
        )


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

            record.updated_by = request.user
            record.save(update_fields=['updated_by', 'updated_at'])

            messages.success(request, 'Документ загружен.')
        else:
            messages.error(request, 'Не удалось загрузить документ.')

        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)

        return redirect(candidate_detail_url(record.pk))


class ResumeCandidateDocumentDownloadView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'personnel.view_resumecandidate'
    raise_exception = True

    def get(self, request, pk):
        document = get_object_or_404(ResumeCandidateDocument, pk=pk)

        if not document.file:
            raise Http404('Файл не найден')

        file_handle = document.file.open('rb')
        filename = os.path.basename(document.file.name)

        return FileResponse(
            file_handle,
            as_attachment=True,
            filename=filename,
        )


class ResumeCandidateDocumentPreviewView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'personnel.view_resumecandidate'
    raise_exception = True

    def get(self, request, pk):
        document = get_object_or_404(ResumeCandidateDocument, pk=pk)

        if not document.file:
            raise Http404('Файл не найден')

        file_handle = document.file.open('rb')
        filename = os.path.basename(document.file.name)

        extension = ''
        if '.' in filename:
            extension = filename.rsplit('.', 1)[-1].lower()

        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

        if extension in {'jpg', 'jpeg', 'jpe', 'jfif'}:
            content_type = 'image/jpeg'

        return FileResponse(
            file_handle,
            as_attachment=False,
            filename=filename,
            content_type=content_type,
        )


class ResumeCandidateDocumentDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'personnel.change_resumecandidate'
    raise_exception = True

    def post(self, request, pk):
        document = get_object_or_404(ResumeCandidateDocument, pk=pk)
        record = document.record
        record_pk = record.pk

        if document.file:
            document.file.delete(save=False)

        document.delete()

        record.updated_by = request.user
        record.save(update_fields=['updated_by', 'updated_at'])

        messages.success(request, 'Документ удалён.')

        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)

        return redirect(candidate_detail_url(record_pk))
