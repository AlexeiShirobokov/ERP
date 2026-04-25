from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import OtipbHistory

# Замени CandidateCard на реальное название твоей модели карточки
from .models import CandidateCard


@receiver(post_save, sender=CandidateCard)
def update_otipb_history_from_card(sender, instance, created, **kwargs):
    """
    После сохранения карточки актуализируем базу ОТИПБ.

    Если кандидат новый — появится новая запись в истории.
    Если кандидат уже был — мы всё равно создаём новую запись,
    потому что это история изменений, а не одна строка на человека.
    """

    fio = getattr(instance, "fio", None)

    if not fio:
        return

    OtipbHistory.objects.create(
        fio=fio,
        otipb=getattr(instance, "otipb", "") or "",
        position=getattr(instance, "position", "") or "",
        department=getattr(instance, "department", "") or "",
        phone=getattr(instance, "phone", "") or "",
        comment="Актуализировано из карточки кандидата",
        source="Карточка кандидата",
        source_date=timezone.now(),
    )