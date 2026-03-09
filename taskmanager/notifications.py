# 'это обычно файл для уведомлений.'
# 'То есть туда выносят функции, которые срабатывают, когда что-то произошло в системе. Например:
#
# создали задачу
#
# изменили задачу
#
# делегировали задачу
#
# завершили задачу
#
# сдвинули карточку бизнес-процесса
#
# пришло новое сообщение
#
# Зачем его выносят в отдельный файл
#
# Чтобы не держать всю логику уведомлений прямо во views.py.
#
# То есть views.py отвечает за:
#
# принять запрос
#
# сохранить данные
#
# вернуть страницу/redirect
#
# А notifications.py отвечает за:
#
# отправить уведомление
#
# записать событие
#
# потом, возможно, отправить email / Telegram / WebSocket


def notify_task_updated(*args, **kwargs):
    return None


def notify_task_completed(*args, **kwargs):
    return None


def notify_task_delegated(*args, **kwargs):
    return None


def notify_project_updated(*args, **kwargs):
    return None


def notify_bp_item_moved(*args, **kwargs):
    return None


def notify_bp_message(*args, **kwargs):
    return None