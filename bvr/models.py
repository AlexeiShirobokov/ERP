# -*- coding: utf-8 -*-
"""Модели приложения БВР."""
from django.db import models


class PassportRecognition(models.Model):
    """Результат распознавания паспорта БВР — для аудита и отладки.

    Записывается при каждом вызове эндпоинта распознавания. Поле ``file_hash``
    (SHA-256 PDF) позволяет связывать загрузки одного и того же паспорта.
    """

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    user = models.CharField("Пользователь", max_length=150, blank=True, default="")
    file_hash = models.CharField("SHA-256 файла", max_length=64, db_index=True,
                                 blank=True, default="")
    file_name = models.CharField("Имя файла", max_length=255, blank=True, default="")
    ok = models.BooleanField("Успех", default=False)
    source = models.CharField("Источник", max_length=32, blank=True, default="")
    model_used = models.CharField("Модель", max_length=64, blank=True, default="")
    wells_count = models.IntegerField("Скважин распознано", null=True, blank=True)
    avg_depth = models.FloatField("Средняя глубина, м", null=True, blank=True)
    warnings = models.JSONField("Предупреждения", default=list, blank=True)
    payload = models.JSONField("Результат распознавания", default=dict, blank=True)
    error = models.CharField("Ошибка", max_length=500, blank=True, default="")

    class Meta:
        verbose_name = "Распознавание паспорта БВР"
        verbose_name_plural = "Распознавания паспортов БВР"
        ordering = ("-created_at",)

    def __str__(self):
        status = "ok" if self.ok else "fail"
        return f"Паспорт {self.file_name or self.file_hash[:8]} [{status}] {self.created_at:%Y-%m-%d %H:%M}"
