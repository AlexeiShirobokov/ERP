# views.py
from datetime import timedelta, datetime
from io import BytesIO

import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q, Prefetch
from django.http import (
    FileResponse,
    HttpResponseForbidden,
    HttpResponseBadRequest,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.timezone import make_aware
from django.views.decorators.http import require_POST

from .forms import (
    ProjectForm,
    ProjectItemFormSet,
    TaskForm,
    BusinessProcessForm,
    PurchaseFormSet,
)
from .models import (
    Project,
    ProjectMember,
    ProjectItem,
    ProjectItemAssignee,
    ProjectMessage,
    ProjectFile,
    Task,
    TaskParticipant,
    TaskMessage,
    TaskFile,
    BusinessProcess,
    BusinessProcessMember,
    BPMessage,
    BPFile,
    PurchaseRequest,
    Notification,
    BP_ROLES,
    BP_STAGES,
)
from .notifications import (
    notify_task_created,
    notify_task_updated,
    notify_task_completed,
    notify_task_delegated,
    notify_project_updated,
    notify_bp_item_moved,
    notify_bp_message,
)
# =========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================

def get_user_role(user, task):
    if task.creator_id == user.id:
        return "Создатель"
    if task.responsible_id == user.id:
        return "Ответственный"
    p = TaskParticipant.objects.filter(task=task, user=user).first()
    return p.get_role_display() if p else "-"

def user_can_access_task(user, task):
    return (
        task.creator_id == user.id
        or task.responsible_id == user.id
        or task.participants.filter(user=user).exists()
    )

def user_can_upload_files(user, task):
    return user_can_access_task(user, task)

def user_can_complete_task(user, task):
    return (
        task.creator_id == user.id
        or task.responsible_id == user.id
        or task.participants.filter(user=user, role__in=["executor", "responsible"]).exists()
    )

# (1) Редактировать: Создатель или Наблюдатель
def user_can_edit_task(user, task):
    return (
        task.creator_id == user.id
        or TaskParticipant.objects.filter(task=task, user=user, role="observer").exists()
    )

# (2) Делегировать: Создатель, Ответственный, Исполнитель, Наблюдатель
def user_can_delegate_task(user, task):
    return (
        task.creator_id == user.id
        or task.responsible_id == user.id
        or TaskParticipant.objects.filter(task=task, user=user, role__in=["executor", "observer"]).exists()
    )

# Подсветка дедлайна
def calc_deadline_status(task):
    """
    Возвращает один из статусов:
    done / overdue / soon / ok / no_deadline
    """
    if not task.deadline:
        return "no_deadline"
    if task.is_completed:
        return "done"
    now = timezone.now()
    if task.deadline < now:
        return "overdue"
    if task.deadline <= now + timedelta(days=1):
        return "soon"
    return "ok"


# ============
# TASK VIEWS
# ============

@login_required
def task_list(request):
    query = request.GET.get("q", "").strip()
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    active_tab = request.GET.get("tab", "creator")

    # Базы
    qs_creator = Task.objects.filter(creator=request.user)
    qs_responsible = Task.objects.filter(responsible=request.user)
    qs_participant = Task.objects.filter(participants__user=request.user)
    qs_completed = Task.objects.filter(
        Q(creator=request.user) | Q(responsible=request.user) | Q(participants__user=request.user),
        is_completed=True,
    )

    # Поиск
    if query:
        f = (
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(responsible__first_name__icontains=query)
            | Q(responsible__last_name__icontains=query)
        )
        qs_creator = qs_creator.filter(f)
        qs_responsible = qs_responsible.filter(f)
        qs_participant = qs_participant.filter(f)
        qs_completed = qs_completed.filter(f)

    # Даты
    if date_from:
        dtf = make_aware(datetime.strptime(date_from, "%Y-%m-%d"))
        qs_creator = qs_creator.filter(deadline__gte=dtf)
        qs_responsible = qs_responsible.filter(deadline__gte=dtf)
        qs_participant = qs_participant.filter(deadline__gte=dtf)
        qs_completed = qs_completed.filter(deadline__gte=dtf)

    if date_to:
        dtt = make_aware(datetime.strptime(date_to, "%Y-%m-%d"))
        qs_creator = qs_creator.filter(deadline__lte=dtt)
        qs_responsible = qs_responsible.filter(deadline__lte=dtt)
        qs_participant = qs_participant.filter(deadline__lte=dtt)
        qs_completed = qs_completed.filter(deadline__lte=dtt)

    # Экспорт
    if "export" in request.GET:
        all_tasks = qs_creator.union(qs_responsible, qs_participant, qs_completed)
        data = [
            {
                "Тема": t.title,
                "Описание": t.description,
                "Срок": t.deadline.strftime("%Y-%m-%d %H:%M") if t.deadline else "",
                "Постановщик": t.creator.get_full_name() or t.creator.username,
                "Ответственный": t.responsible.get_full_name() if t.responsible else "",
                "Роль": get_user_role(request.user, t),
                "Статус": "Завершена" if t.is_completed else "В работе",
            }
            for t in all_tasks
        ]
        output = BytesIO()
        pd.DataFrame(data).to_excel(output, index=False)
        output.seek(0)
        return FileResponse(output, as_attachment=True, filename="tasks.xlsx")

    tabs = {
        "creator": qs_creator.filter(is_completed=False),
        "responsible": qs_responsible.filter(is_completed=False).exclude(creator=request.user),
        "participant": qs_participant.filter(is_completed=False)
        .exclude(creator=request.user)
        .exclude(responsible=request.user),
        "completed": qs_completed,
    }
    current_qs = (
        tabs.get(active_tab, tabs["creator"]).select_related("responsible").prefetch_related("files").distinct()
    )

    # Подготовка объектов для шаблона
    current_tasks = []
    for t in current_qs.order_by("-created_at"):
        t.my_role = get_user_role(request.user, t)
        t.files_count = t.files.count()
        t.deadline_status = calc_deadline_status(t)
        current_tasks.append(t)

    return render(
        request,
        "taskmanager/tasks/task_list.html",
        {
            "query": query,
            "date_from": date_from,
            "date_to": date_to,
            "active_tab": active_tab,
            "current_tasks": current_tasks,
        },
    )


@login_required
def task_create(request):
    users = User.objects.exclude(id=request.user.id).order_by("first_name", "last_name", "username")
    if request.method == "POST":
        form = TaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.creator = request.user
            responsible_id = request.POST.get("responsible")
            if responsible_id:
                task.responsible_id = responsible_id
            task.save()

            # участники
            for user_id, role in zip(request.POST.getlist("participants"), request.POST.getlist("roles")):
                if user_id:
                    TaskParticipant.objects.create(task=task, user_id=user_id, role=role)

            notify_task_created(task, changed_by=request.user)

            return redirect("taskmanager:task_detail", pk=task.pk)
    else:
        form = TaskForm()
    return render(request, "taskmanager/tasks/task_form.html", {"form": form, "users": users})


@login_required
def task_detail(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not user_can_access_task(request.user, task):
        return HttpResponseForbidden("У вас нет доступа к этой задаче")

    # права
    can_complete = user_can_complete_task(request.user, task)
    can_upload_files = user_can_upload_files(request.user, task)
    can_edit = user_can_edit_task(request.user, task)
    can_delegate = user_can_delegate_task(request.user, task)

    # подсветка срока
    task.deadline_status = calc_deadline_status(task)

    # POST
    if request.method == "POST":
        # файлы
        if "files" in request.FILES:
            if not can_upload_files:
                return HttpResponseForbidden("У вас нет прав для загрузки файлов")
            for f in request.FILES.getlist("files"):
                TaskFile.objects.create(task=task, file=f, uploaded_by=request.user)
            messages.success(request, "Файлы загружены")
            return redirect("taskmanager:task_detail", pk=pk)

        # сообщение
        content = request.POST.get("content")
        if content:
            TaskMessage.objects.create(task=task, sender=request.user, content=content)
            return redirect("taskmanager:task_detail", pk=pk)

    participants = TaskParticipant.objects.filter(task=task)
    task_messages = task.messages.all().order_by("timestamp")

    return render(
        request,
        "taskmanager/tasks/task_detail.html",
        {
            "task": task,
            "participants": participants,
            "task_messages": task_messages,
            "can_complete": can_complete,
            "can_upload_files": can_upload_files,
            "can_edit": can_edit,
            "can_delegate": can_delegate,
        },
    )


@login_required
def edit_task(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not user_can_edit_task(request.user, task):
        return HttpResponseForbidden("У вас нет прав для редактирования этой задачи")

    users = User.objects.exclude(id=request.user.id).order_by("first_name", "last_name", "username")
    if request.method == "POST":
        form = TaskForm(request.POST, instance=task)
        if form.is_valid():
            task = form.save()

            # участники
            TaskParticipant.objects.filter(task=task).delete()
            for user_id, role in zip(request.POST.getlist("participants"), request.POST.getlist("roles")):
                if user_id:
                    TaskParticipant.objects.create(task=task, user_id=user_id, role=role)

            # файлы
            for f in request.FILES.getlist("files"):
                TaskFile.objects.create(task=task, file=f, uploaded_by=request.user)

            # уведомление (после всех изменений)
            notify_task_updated(task, changed_by=request.user)

            messages.success(request, "Задача успешно обновлена")
            return redirect("taskmanager:task_detail", pk=task.pk)
    else:
        form = TaskForm(instance=task)

    current_participants = TaskParticipant.objects.filter(task=task)
    return render(
        request,
        "taskmanager/tasks/task_form.html",
        {"form": form, "users": users, "task": task, "is_edit": True, "current_participants": current_participants},
    )


@login_required
def delegate_task(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not user_can_delegate_task(request.user, task):
        return HttpResponseForbidden("У вас нет прав для делегирования этой задачи")

    users = User.objects.exclude(id=request.user.id).order_by("first_name", "last_name", "username")
    if request.method == "POST":
        new_responsible_id = request.POST.get("new_responsible")
        if new_responsible_id:
            new_resp = get_object_or_404(User, id=new_responsible_id)
            old_resp = task.responsible  # фиксируем старого до изменения

            if old_resp and old_resp != new_resp:
                TaskParticipant.objects.get_or_create(task=task, user=old_resp, defaults={"role": "observer"})

            task.responsible = new_resp
            task.is_delegated = True
            task.save()

            # уведомление с корректным old_resp/new_resp
            notify_task_delegated(task, old_resp=old_resp, new_resp=new_resp, changed_by=request.user)

            TaskParticipant.objects.get_or_create(task=task, user=new_resp, defaults={"role": "responsible"})
            TaskMessage.objects.create(
                task=task,
                sender=request.user,
                content=f"Задача делегирована от {old_resp.get_full_name() if old_resp else request.user.get_full_name()} к {new_resp.get_full_name()}",
            )
            messages.success(request, f"Задача успешно делегирована {new_resp.get_full_name()}")
            return redirect("taskmanager:task_detail", pk=task.pk)

    return render(request, "taskmanager/tasks/delegate_task.html", {"task": task, "users": users})


@login_required
def complete_task(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not user_can_complete_task(request.user, task):
        return HttpResponseForbidden("У вас нет прав для завершения этой задачи")
    if not task.is_completed:
        task.is_completed = True
        task.save()
        notify_task_completed(task, changed_by=request.user)
        messages.success(request, "Задача отмечена как завершенная")
    return redirect("taskmanager:task_list")


@login_required
def upload_files(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not user_can_upload_files(request.user, task):
        return HttpResponseForbidden("У вас нет прав для загрузки файлов в эту задачу")
    if request.method == "POST":
        for f in request.FILES.getlist("files"):
            TaskFile.objects.create(task=task, file=f, uploaded_by=request.user)
        messages.success(request, "Файлы загружены")
    return redirect("taskmanager:task_detail", pk=task.pk)


@login_required
def dashboard(request):
    user_tasks = Task.objects.filter(
        Q(creator=request.user) | Q(responsible=request.user) | Q(participants__user=request.user)
    ).distinct()

    total_tasks = user_tasks.count()
    completed_tasks = user_tasks.filter(is_completed=True).count()
    overdue_tasks = user_tasks.filter(is_completed=False, deadline__lt=timezone.now()).count()

    context = {
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "overdue_tasks": overdue_tasks,
    }
    return render(request, "taskmanager/tasks/dashboard.html", context)


# ==============
# PROJECT VIEWS
# ==============

def user_can_access_project(user, project):
    return (
        project.creator_id == user.id
        or (project.manager_id == user.id if project.manager_id else False)
        or project.members.filter(user=user).exists()
    )

def user_can_edit_project(user, project):
    return project.creator_id == user.id or project.manager_id == user.id

def user_can_upload_project_files(user, project):
    return user_can_access_project(user, project)


@login_required
def project_create(request):
    users = User.objects.order_by("first_name", "last_name", "username")
    if request.method == "POST":
        form = ProjectForm(request.POST)
        formset = ProjectItemFormSet(request.POST, instance=Project())
        for f in formset.forms:
            f.fields["assignees"].queryset = users

        if form.is_valid() and formset.is_valid():
            project = form.save(commit=False)
            project.creator = request.user
            project.save()

            formset.instance = project
            formset.save()

            # привяжем исполнителей
            for f in formset.forms:
                if not f.cleaned_data or f.cleaned_data.get("DELETE"):
                    continue
                item = f.instance
                assignees = f.cleaned_data.get("assignees")
                if assignees:
                    ProjectItemAssignee.objects.bulk_create(
                        [ProjectItemAssignee(item=item, user=u) for u in assignees], ignore_conflicts=True
                    )

            if project.manager_id:
                ProjectMember.objects.get_or_create(
                    project=project, user_id=project.manager_id, defaults={"role": "manager"}
                )

            # уведомление о создании/обновлении проекта
            notify_project_updated(project, changed_by=request.user)

            messages.success(request, "Проект создан")
            return redirect("taskmanager:project_detail", pk=project.pk)
    else:
        form = ProjectForm()
        formset = ProjectItemFormSet(instance=Project())
        for f in formset.forms:
            f.fields["assignees"].queryset = users

    return render(request, "taskmanager/tasks/project_form.html", {"form": form, "formset": formset, "users": users})


@login_required
def project_edit(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if not user_can_edit_project(request.user, project):
        return HttpResponseForbidden("Нет прав")

    users = User.objects.order_by("first_name", "last_name", "username")
    if request.method == "POST":
        form = ProjectForm(request.POST, instance=project)
        formset = ProjectItemFormSet(request.POST, instance=project)
        for f in formset.forms:
            f.fields["assignees"].queryset = users

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()

            # пересобираем исполнителей
            ProjectItemAssignee.objects.filter(item__project=project).delete()
            for f in formset.forms:
                if not f.cleaned_data or f.cleaned_data.get("DELETE"):
                    continue
                item = f.instance
                assignees = f.cleaned_data.get("assignees")
                if assignees:
                    ProjectItemAssignee.objects.bulk_create(
                        [ProjectItemAssignee(item=item, user=u) for u in assignees], ignore_conflicts=True
                    )

            if project.manager_id:
                ProjectMember.objects.get_or_create(
                    project=project, user_id=project.manager_id, defaults={"role": "manager"}
                )

            # уведомление после всех изменений
            notify_project_updated(project, changed_by=request.user)

            messages.success(request, "Проект обновлён")
            return redirect("taskmanager:project_detail", pk=project.pk)
    else:
        form = ProjectForm(instance=project)
        formset = ProjectItemFormSet(instance=project)
        for f in formset.forms:
            f.fields["assignees"].queryset = users
            if f.instance.pk:
                f.initial["assignees"] = f.instance.assignees.values_list("pk", flat=True)

    return render(
        request,
        "taskmanager/tasks/project_form.html",
        {"form": form, "formset": formset, "project": project, "is_edit": True, "users": users},
    )


@login_required
def project_detail(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if not user_can_access_project(request.user, project):
        return HttpResponseForbidden("Нет доступа к проекту")

    # отправка сообщения
    if request.method == "POST" and "pmsg" in request.POST:
        text = request.POST.get("pmsg", "").strip()
        if text:
            msg = ProjectMessage.objects.create(project=project, sender=request.user, content=text)
            # уведомим участников проекта о новом сообщении/изменении
            notify_project_updated(project, changed_by=request.user)
            return redirect("taskmanager:project_detail", pk=pk)

    items = project.items.prefetch_related("assignees")
    members = project.members.select_related("user")
    messages_qs = project.messages.select_related("sender").order_by("timestamp")

    can_edit = user_can_edit_project(request.user, project)
    can_upload = user_can_upload_project_files(request.user, project)

    return render(
        request,
        "taskmanager/tasks/project_detail.html",
        {
            "project": project,
            "items": items,
            "members": members,
            "messages": messages_qs,
            "can_edit": can_edit,
            "can_upload_files": can_upload,
        },
    )


@login_required
def project_upload_files(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if not user_can_upload_project_files(request.user, project):
        return HttpResponseForbidden("Нет прав для загрузки файлов")
    if request.method == "POST":
        for f in request.FILES.getlist("files"):
            ProjectFile.objects.create(project=project, file=f, uploaded_by=request.user)
        # можно тоже оповещать об изменении файла проекта:
        notify_project_updated(project, changed_by=request.user)
        messages.success(request, "Файлы загружены")
    return redirect("taskmanager:project_detail", pk=pk)


@login_required
def project_list(request):
    projects = Project.objects.all().select_related("manager").order_by("-created_at")
    return render(request, "taskmanager/tasks/project_list.html", {"projects": projects})


# ===========================
# BUSINESS PROCESS (BP) VIEWS
# ===========================

@login_required
def bp_list(request):
    """Список бизнес-процессов с поиском."""
    q = request.GET.get("q", "").strip()
    processes = BusinessProcess.objects.select_related("manager", "creator").order_by("-created_at")

    if q:
        processes = processes.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(manager__first_name__icontains=q)
            | Q(manager__last_name__icontains=q)
        )

    return render(request, "taskmanager/bp/bp_list.html", {"processes": processes, "q": q})


@login_required
def bp_create(request):
    """
    Создание бизнес-процесса + первичный чек-лист «Покупка»
    (formset позволяет добавить сразу несколько карточек).
    """
    users = User.objects.order_by("first_name", "last_name", "username")

    if request.method == "POST":
        form = BusinessProcessForm(request.POST)
        formset = PurchaseFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                bp = form.save(commit=False)
                bp.creator = request.user
                bp.save()

                # создаём стартовые карточки из формсета
                formset.instance = bp
                formset.save()

                # по умолчанию делаем автора инициатором заявки (если ещё не добавлен)
                BusinessProcessMember.objects.get_or_create(
                    process=bp, user=request.user, defaults={"role": "initiator"}
                )

            messages.success(request, "Бизнес-процесс создан")
            return redirect("taskmanager:bp_detail", pk=bp.pk)
        else:
            messages.error(request, "Проверьте форму — есть ошибки.")
    else:
        form = BusinessProcessForm()
        formset = PurchaseFormSet()

    return render(request, "taskmanager/bp/bp_form.html", {"form": form, "formset": formset, "users": users})


@login_required
def bp_detail(request, pk):
    """
    Карточка бизнес-процесса: инфо, участники, карточки, чат, файлы.
    """
    bp = get_object_or_404(BusinessProcess, pk=pk)

    if request.method == "POST":
        # Сообщение в чат процесса
        msg = request.POST.get("bpmsg", "").strip()
        if msg:
            message = BPMessage.objects.create(process=bp, sender=request.user, content=msg)
            notify_bp_message(bp, message)
            return redirect("taskmanager:bp_detail", pk=pk)

        # Загрузка файлов на процесс
        if request.FILES.getlist("files"):
            uploaded = 0
            for f in request.FILES.getlist("files"):
                BPFile.objects.create(process=bp, file=f, uploaded_by=request.user)
                uploaded += 1
            # оповещение об изменении процесса при загрузке файлов — опционально:
            notify_bp_message(bp, BPMessage(process=bp, sender=request.user, content="Загружены файлы"))
            messages.success(request, f"Загружено файлов: {uploaded}")
            return redirect("taskmanager:bp_detail", pk=pk)

    members = bp.members.select_related("user").all().order_by("role", "user__first_name", "user__last_name")
    items = bp.purchases.prefetch_related("assignees").order_by("stage", "order", "id")
    messages_qs = bp.messages.select_related("sender").order_by("timestamp")

    return render(
        request,
        "taskmanager/bp/bp_detail.html",
        {"bp": bp, "members": members, "items": items, "messages": messages_qs, "roles": BP_ROLES, "stages": BP_STAGES},
    )


@login_required
def bp_board(request, pk):
    bp = get_object_or_404(BusinessProcess, pk=pk)
    items = bp.purchases.prefetch_related("assignees").all()

    cols = [
        ("initiator", "Инициатор заявки"),
        ("procurement", "Снабжение"),
        ("finance", "Финансовый отдел"),
        ("treasury", "Казначейство"),
        ("warehouse", "Склад"),
        ("done", "Готово"),
    ]
    columns = {key: [] for key, _ in cols}
    for it in items:
        columns[it.stage].append(it)

    return render(
        request,
        "taskmanager/bp/bp_board.html",
        {
            "bp": bp,
            "stages": [
                type(
                    "S",
                    (),
                    {
                        "id": key,
                        "title": title,
                        "items": type(
                            "Q", (), {"all": (lambda self, k=key: columns[k]), "count": len(columns[key])}
                        )(),
                    },
                )
                for key, title in cols
            ],
        },
    )


@login_required
@require_POST
def bp_move(request, pk):
    """
    AJAX: перетаскивание карточки.
    Принимает:
      - id:        id карточки
      - stage:     новая стадия (колонка)
      - ordered[]: массив id карточек в колонке после dnd (слева направо, сверху вниз)
    """
    bp = get_object_or_404(BusinessProcess, pk=pk)

    item_id = request.POST.get("id")
    new_stage = request.POST.get("stage")
    ordered = request.POST.getlist("ordered[]")

    if not item_id or not new_stage or not ordered:
        return HttpResponseBadRequest("Missing params")

    item = get_object_or_404(PurchaseRequest, pk=item_id, process=bp)

    with transaction.atomic():
        # старая стадия до перемещения — для уведомления
        old_stage = item.stage

        # позиция карточки в новом порядке
        try:
            new_pos = ordered.index(str(item.id))
        except ValueError:
            return HttpResponseBadRequest("Item id not in ordered[]")

        # перемещаем и нормализуем порядок
        item.move_to(new_stage, new_pos)
        item.resequence_stage()

    # уведомление участникам процесса и исполнителям карточки
    notify_bp_item_moved(bp, item, old_stage=old_stage, new_stage=new_stage, changed_by=request.user)

    return JsonResponse({"ok": True})


@login_required
@require_POST
def bp_add_comment(request, item_id):
    # Заглушка — если будете делать отдельные комментарии по карточке
    return JsonResponse({"ok": True, "msg": "Комментарий добавлен (заглушка)"})


@login_required
@require_POST
def bp_upload_file(request, item_id):
    # Заглушка — если будете грузить файлы на карточку отдельно
    return JsonResponse({"ok": True, "msg": "Файл загружен (заглушка)"})

@login_required
def notification_list(request):
    notifications = request.user.task_notifications.all()
    return render(
        request,
        "taskmanager/notifications/list.html",
        {"notifications": notifications},
    )


@login_required
@require_POST
def notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save(update_fields=["is_read"])

    if notification.url:
        return redirect(notification.url)
    return redirect("taskmanager:notification_list")

@login_required
def director_dashboard(request):
    now = timezone.now()
    tasks = list(
        Task.objects.select_related("creator", "responsible").all().order_by("-created_at")
    )

    def display_name(user):
        if not user:
            return "Не назначен"
        full_name = (user.get_full_name() or "").strip()
        return full_name or user.username

    total_tasks = len(tasks)
    completed_tasks = sum(1 for t in tasks if t.is_completed)
    active_tasks = total_tasks - completed_tasks

    overdue_tasks = sum(
        1 for t in tasks
        if not t.is_completed and t.deadline and t.deadline < now
    )

    due_soon_tasks = sum(
        1 for t in tasks
        if not t.is_completed and t.deadline and now <= t.deadline <= now + timedelta(days=3)
    )

    no_deadline_tasks = sum(
        1 for t in tasks
        if not t.is_completed and not t.deadline
    )

    in_work_tasks = sum(
        1 for t in tasks
        if not t.is_completed and t.deadline and t.deadline > now + timedelta(days=3)
    )

    delegated_tasks = sum(1 for t in tasks if t.is_delegated and not t.is_completed)

    execution_rate = round((completed_tasks / total_tasks) * 100, 1) if total_tasks else 0

    # 1. Структура задач
    status_labels = ["Завершено", "Просрочено", "Срок до 3 дней", "В работе", "Без срока"]
    status_values = [
        completed_tasks,
        overdue_tasks,
        due_soon_tasks,
        in_work_tasks,
        no_deadline_tasks,
    ]

    # 2. По постановщикам
    creator_map = {}
    for t in tasks:
        name = display_name(t.creator)
        creator_map.setdefault(name, {"name": name, "total": 0, "overdue": 0})
        creator_map[name]["total"] += 1
        if not t.is_completed and t.deadline and t.deadline < now:
            creator_map[name]["overdue"] += 1

    creator_rows = sorted(
        creator_map.values(),
        key=lambda x: (-x["total"], -x["overdue"], x["name"])
    )[:10]

    creator_labels = [row["name"] for row in creator_rows]
    creator_total = [row["total"] for row in creator_rows]
    creator_overdue = [row["overdue"] for row in creator_rows]

    # 3. По ответственным
    responsible_map = {}
    for t in tasks:
        name = display_name(t.responsible)
        responsible_map.setdefault(
            name,
            {"name": name, "total": 0, "overdue": 0, "completed": 0}
        )
        responsible_map[name]["total"] += 1
        if t.is_completed:
            responsible_map[name]["completed"] += 1
        if not t.is_completed and t.deadline and t.deadline < now:
            responsible_map[name]["overdue"] += 1

    responsible_rows = sorted(
        responsible_map.values(),
        key=lambda x: (-x["total"], -x["overdue"], x["name"])
    )[:10]

    responsible_labels = [row["name"] for row in responsible_rows]
    responsible_total = [row["total"] for row in responsible_rows]
    responsible_overdue = [row["overdue"] for row in responsible_rows]
    responsible_completed = [row["completed"] for row in responsible_rows]

    # 4. Возраст просрочки
    aging_map = {
        "1–3 дня": 0,
        "4–7 дней": 0,
        "8–14 дней": 0,
        "15+ дней": 0,
    }

    red_tasks = []

    for t in tasks:
        if not t.is_completed and t.deadline and t.deadline < now:
            overdue_days = (now.date() - t.deadline.date()).days
            overdue_days = max(overdue_days, 1)

            if overdue_days <= 3:
                aging_map["1–3 дня"] += 1
            elif overdue_days <= 7:
                aging_map["4–7 дней"] += 1
            elif overdue_days <= 14:
                aging_map["8–14 дней"] += 1
            else:
                aging_map["15+ дней"] += 1

            red_tasks.append({
                "id": t.id,
                "title": t.title,
                "creator_name": display_name(t.creator),
                "responsible_name": display_name(t.responsible),
                "deadline": t.deadline,
                "overdue_days": overdue_days,
            })

    red_tasks = sorted(
        red_tasks,
        key=lambda x: (-x["overdue_days"], x["deadline"])
    )[:15]

    aging_labels = list(aging_map.keys())
    aging_values = list(aging_map.values())

    # 5. Создано задач за последние 30 дней
    start_date = (now - timedelta(days=29)).date()
    date_axis = [start_date + timedelta(days=i) for i in range(30)]
    created_map = {d: 0 for d in date_axis}

    for t in tasks:
        created_date = t.created_at.date()
        if created_date in created_map:
            created_map[created_date] += 1

    created_labels = [d.strftime("%d.%m") for d in date_axis]
    created_values = [created_map[d] for d in date_axis]

    context = {
        "total_tasks": total_tasks,
        "active_tasks": active_tasks,
        "completed_tasks": completed_tasks,
        "overdue_tasks": overdue_tasks,
        "due_soon_tasks": due_soon_tasks,
        "delegated_tasks": delegated_tasks,
        "execution_rate": execution_rate,

        "status_labels": status_labels,
        "status_values": status_values,

        "creator_labels": creator_labels,
        "creator_total": creator_total,
        "creator_overdue": creator_overdue,

        "responsible_labels": responsible_labels,
        "responsible_total": responsible_total,
        "responsible_overdue": responsible_overdue,
        "responsible_completed": responsible_completed,

        "aging_labels": aging_labels,
        "aging_values": aging_values,

        "created_labels": created_labels,
        "created_values": created_values,

        "red_tasks": red_tasks,
    }
    return render(request, "taskmanager/tasks/director_dashboard.html", context)