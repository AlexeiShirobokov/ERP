import os

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class PersonnelRecord(models.Model):
    date = models.DateField("Дата", default=timezone.now)
    full_name = models.CharField("ФИО", max_length=255)
    hh_candidate = models.CharField(
        "Соискатель по вакансии на hh.ru",
        max_length=255,
        blank=True,
    )
    position_name = models.CharField(
        "Должность (название в Поиск золото)",
        max_length=255,
    )
    contacts = models.TextField("Контакты", blank=True)
    medical_commission = models.CharField("Мед комиссия", max_length=255, blank=True)
    comment = models.TextField("Комментарий", blank=True)
    birth_year = models.PositiveSmallIntegerField("Год рождения", null=True, blank=True)
    qualification = models.TextField(
        "Квалификация, наличие удостоверения на сайте",
        blank=True,
    )
    note = models.TextField("Примечание", blank=True)
    referral_to_mo = models.CharField("Направление на МО", max_length=255, blank=True)
    refusal_reason = models.TextField("Примечание или причина отказа", blank=True)
    ticket = models.CharField("Билет", max_length=255, blank=True)
    estimated_arrival_date = models.DateField(
        "Расчетная дата приезда",
        null=True,
        blank=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="personnel_records_created",
        verbose_name="Создал",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="personnel_records_updated",
        verbose_name="Последний редактор",
    )
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Изменено", auto_now=True)

    class Meta:
        verbose_name = "Кадровая карточка"
        verbose_name_plural = "Кадровые карточки"
        ordering = ["-date", "full_name", "-id"]

    def __str__(self):
        return f"{self.full_name} — {self.position_name}"

    def get_absolute_url(self):
        return reverse("personnel:record_detail", kwargs={"pk": self.pk})


class PersonnelDocument(models.Model):
    record = models.ForeignKey(
        PersonnelRecord,
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="Кадровая карточка",
    )
    title = models.CharField("Название документа", max_length=255)
    file = models.FileField("Файл", upload_to="personnel/%Y/%m/%d/")
    comment = models.TextField("Комментарий", blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="personnel_documents_uploaded",
        verbose_name="Загрузил",
    )
    uploaded_at = models.DateTimeField("Загружено", auto_now_add=True)

    class Meta:
        verbose_name = "Документ кадровой карточки"
        verbose_name_plural = "Документы кадровых карточек"
        ordering = ["-uploaded_at", "-id"]

    def __str__(self):
        return self.title

    @property
    def filename(self):
        return os.path.basename(self.file.name)