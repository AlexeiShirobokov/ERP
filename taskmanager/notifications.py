from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from .models import Notification


def _display_name(user):
    if not user:
        return "Система"
    return user.get_full_name() or user.username


def _task_participants_queryset(task):
    return task.participants.select_related("user")


def _task_recipient_users(task, exclude_user_id=None):
    users = []

    if task.creator_id:
        users.append(task.creator)

    if task.responsible_id:
        users.append(task.responsible)

    for participant in _task_participants_queryset(task):
        users.append(participant.user)

    unique = {}
    for user in users:
        if not user:
            continue
        if exclude_user_id and user.id == exclude_user_id:
            continue
        unique[user.id] = user

    return list(unique.values())


def _create_notifications(users, title, text, url=""):
    Notification.objects.bulk_create(
        [
            Notification(
                user=user,
                title=title,
                text=text,
                url=url,
            )
            for user in users
        ]
    )


def _send_email_notifications(users, subject, message):
    recipient_list = [u.email for u in users if getattr(u, "email", "")]

    if not recipient_list:
        return

    send_mail(
        subject=subject,
        message=message,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        recipient_list=recipient_list,
        fail_silently=False,
    )


def _notify_task_users(task, title, text, changed_by=None):
    users = _task_recipient_users(
        task,
        exclude_user_id=changed_by.id if changed_by else None,
    )

    if not users:
        return

    url = f"{settings.APP_BASE_URL}{reverse('taskmanager:task_detail', kwargs={'pk': task.pk})}"

    _create_notifications(users, title, text, url)

    full_message = (
        f"{text}\n\n"
        f"Задача: {task.title}\n"
        f"Срок: {task.deadline:%d.%m.%Y %H:%M}\n"
        f"Ссылка: {url}"
    )
    _send_email_notifications(users, title, full_message)


def notify_task_created(task, changed_by=None):
    actor = _display_name(changed_by)
    title = f"Новая задача: {task.title}"
    text = f"{actor} создал(а) задачу и добавил(а) вас в участники."
    _notify_task_users(task, title, text, changed_by=changed_by)


def notify_task_updated(task, changed_by=None):
    actor = _display_name(changed_by)
    title = f"Задача обновлена: {task.title}"
    text = f"{actor} изменил(а) задачу, в которой вы участвуете."
    _notify_task_users(task, title, text, changed_by=changed_by)


def notify_task_completed(task, changed_by=None):
    actor = _display_name(changed_by)
    title = f"Задача завершена: {task.title}"
    text = f"{actor} отметил(а) задачу как завершенную."
    _notify_task_users(task, title, text, changed_by=changed_by)


def notify_task_delegated(task, old_resp=None, new_resp=None, changed_by=None):
    actor = _display_name(changed_by)
    old_name = _display_name(old_resp)
    new_name = _display_name(new_resp)

    title = f"Задача делегирована: {task.title}"
    text = f"{actor} делегировал(а) задачу от {old_name} к {new_name}."
    _notify_task_users(task, title, text, changed_by=changed_by)


def notify_project_updated(*args, **kwargs):
    return None


def notify_bp_item_moved(*args, **kwargs):
    return None


def notify_bp_message(*args, **kwargs):
    return None