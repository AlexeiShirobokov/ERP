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

    stage = models.CharField(
        max_length=30,
        choices=STAGE_CHOICES,
        default="accounting",
        verbose_name="Этап",
    )
    debt_reason = models.TextField(blank=True, null=True, verbose_name="Причина образования ДЗ")
    responsible_person = models.CharField(max_length=255, blank=True, null=True, verbose_name="Ответственный")
    comment = models.TextField(blank=True, null=True, verbose_name="Комментарий")

    last_report_date = models.DateField(blank=True, null=True, verbose_name="Последняя дата отчета")
    current_date = models.DateField(blank=True, null=True, verbose_name="Дата операции")
    current_sum_dt = models.FloatField(blank=True, null=True, verbose_name="Текущая сумма остаток Дт")
    current_sum_kt = models.FloatField(blank=True, null=True, verbose_name="Текущая сумма остаток Кт")
    current_records_count = models.CharField(max_length=50, blank=True, null=True, verbose_name="Количество записей")
    current_debt_date = models.DateField(blank=True, null=True, verbose_name="Дата образования задолженности")
    current_debt_term = models.CharField(max_length=50, blank=True, null=True, verbose_name="Срок дебиторской задолженности")
    current_debt_period = models.CharField(max_length=50, blank=True, null=True, verbose_name="Период задолженности")
    current_debt_reason_excel = models.TextField(blank=True, null=True, verbose_name="Причина ДЗ из Excel")
    current_responsible_department_excel = models.CharField(max_length=255, blank=True, null=True, verbose_name="Отдел из Excel")

    is_active = models.BooleanField(default=True, verbose_name="Активна")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Карточка дебиторской задолженности"
        verbose_name_plural = "Карточки дебиторской задолженности"
        unique_together = ("account", "subkonto1", "subkonto2", "subkonto3")

    def __str__(self):
        return f"{self.account} | {self.subkonto1} | {self.get_stage_display()}"


class DebitorSnapshot(models.Model):
    case = models.ForeignKey(
        DebitorCase,
        on_delete=models.CASCADE,
        related_name="snapshots",
        verbose_name="Карточка"
    )

    report_date = models.DateField(verbose_name="Дата отчета")
    date = models.DateField(blank=True, null=True, verbose_name="Дата")
    sum_dt = models.FloatField(blank=True, null=True, verbose_name="Сумма остаток Дт")
    sum_kt = models.FloatField(blank=True, null=True, verbose_name="Сумма остаток Кт")
    records_count = models.CharField(max_length=50, blank=True, null=True, verbose_name="Количество записей")
    debt_date = models.DateField(blank=True, null=True, verbose_name="Дата образования задолженности")
    debt_term = models.CharField(max_length=50, blank=True, null=True, verbose_name="Срок дебиторской задолженности")
    debt_period = models.CharField(max_length=50, blank=True, null=True, verbose_name="Период задолженности")
    debt_reason_excel = models.TextField(blank=True, null=True, verbose_name="Причина образования ДЗ из Excel")
    responsible_department_excel = models.CharField(max_length=255, blank=True, null=True, verbose_name="Ответственный отдел из Excel")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")

    class Meta:
        verbose_name = "Снимок дебиторской задолженности"
        verbose_name_plural = "Снимки дебиторской задолженности"
        unique_together = ("case", "report_date")
        ordering = ["-report_date", "-id"]

    def __str__(self):
        return f"{self.case} | {self.report_date}"