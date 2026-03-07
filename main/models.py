from django.db import models


class DebitorCase(models.Model):
    STAGE_CHOICES = [
        ("accounting", "Бухгалтерия"),
        ("supply", "Снабжение"),
        ("legal", "Юридический отдел"),
        ("closed", "Закрыто"),
    ]

    account = models.CharField(max_length=100, verbose_name="Счет")
    subkonto1 = models.CharField(max_length=255, blank=True, null=True, verbose_name="Субконто 1")
    subkonto2 = models.CharField(max_length=255, blank=True, null=True, verbose_name="Субконто 2")
    subkonto3 = models.CharField(max_length=255, blank=True, null=True, verbose_name="Субконто 3")
    report_date = models.CharField(max_length=50, blank=True, null=True, verbose_name="Дата отчета")

    stage = models.CharField(
        max_length=30,
        choices=STAGE_CHOICES,
        default="accounting",
        verbose_name="Этап",
    )
    debt_reason = models.TextField(blank=True, null=True, verbose_name="Причина образования ДЗ")
    responsible_person = models.CharField(max_length=255, blank=True, null=True, verbose_name="Ответственный")
    comment = models.TextField(blank=True, null=True, verbose_name="Комментарий")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Карточка дебиторской задолженности"
        verbose_name_plural = "Карточки дебиторской задолженности"
        unique_together = ("account", "subkonto1", "subkonto2", "subkonto3", "report_date")

    def __str__(self):
        return f"{self.account} | {self.subkonto1} | {self.get_stage_display()}"