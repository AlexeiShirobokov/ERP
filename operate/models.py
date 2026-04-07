from django.db import models
from django.core.exceptions import ValidationError


class OperateDataFile(models.Model):
    title = models.CharField("Название", max_length=255, blank=True, default="")
    file = models.FileField("Файл", upload_to="operate/")
    uploaded_at = models.DateTimeField("Загружен", auto_now_add=True)
    is_active = models.BooleanField("Активный", default=True)
    is_processed = models.BooleanField("Обработан", default=False)
    processing_error = models.TextField("Ошибка обработки", blank=True, default="")
    comment = models.TextField("Комментарий", blank=True, default="")

    class Meta:
        verbose_name = "Файл аналитики"
        verbose_name_plural = "Файлы аналитики"
        ordering = ["-uploaded_at", "-id"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            OperateDataFile.objects.exclude(pk=self.pk).update(is_active=False)

    def __str__(self):
        return self.title or self.file.name


class OperateRow(models.Model):
    data_file = models.ForeignKey(
        OperateDataFile,
        on_delete=models.CASCADE,
        related_name="rows",
        verbose_name="Файл",
    )

    source_row_number = models.IntegerField("Номер строки в источнике", null=True, blank=True)

    date = models.DateField("Дата", null=True, blank=True)
    year = models.IntegerField("Год", null=True, blank=True)
    month = models.IntegerField("Месяц", null=True, blank=True)

    subdivision = models.CharField("Подразделение", max_length=255, blank=True, default="")
    block = models.CharField("Блок", max_length=255, blank=True, default="")
    process_name = models.CharField("Передел", max_length=255, blank=True, default="")
    machine_brand = models.CharField("Марка техники", max_length=255, blank=True, default="")
    machine_name = models.CharField("Марка машины", max_length=255, blank=True, default="")
    machine_inventory = models.CharField("Инв. №", max_length=255, blank=True, default="")

    work_volume = models.FloatField("Объем работ", null=True, blank=True)
    corrected_work_volume = models.FloatField("Объем работ скорректированный", null=True, blank=True)
    work_time = models.FloatField("Время работы", null=True, blank=True)
    downtime = models.FloatField("Время простоя", null=True, blank=True)
    transportation_distance = models.FloatField("Откатка, м", null=True, blank=True)

    shift_master = models.CharField("Горный мастер", max_length=255, blank=True, default="")
    operator_name = models.CharField("Машинист", max_length=255, blank=True, default="")
    assistant_name = models.CharField("Помощник", max_length=255, blank=True, default="")
    downtime_reason = models.TextField("Причина простоя", blank=True, default="")

    raw_data = models.JSONField("Сырые данные", null=True, blank=True)

    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Строка аналитики"
        verbose_name_plural = "Строки аналитики"
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["subdivision"]),
            models.Index(fields=["date"]),
            models.Index(fields=["year"]),
            models.Index(fields=["month"]),
            models.Index(fields=["subdivision", "year"]),
            models.Index(fields=["subdivision", "process_name"]),
        ]

    def __str__(self):
        return f"{self.subdivision} | {self.date} | {self.process_name}"