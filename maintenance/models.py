import os

from django.db import models


class Department(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Подразделение")

    class Meta:
        verbose_name = "Подразделение"
        verbose_name_plural = "Подразделения"
        ordering = ["name"]

    def __str__(self):
        return self.name


class MaintenanceRecord(models.Model):
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        verbose_name="Подразделение",
    )
    machine_brand = models.CharField(max_length=255, verbose_name="Марка техники")
    inventory_number = models.CharField(max_length=100, verbose_name="Инв. номер")
    maintenance_date = models.DateField(verbose_name="Дата проведения ТО")
    responsible_fio = models.CharField(max_length=255, verbose_name="ФИО ответственного")
    machine_hours = models.PositiveIntegerField(verbose_name="Машиночасы")
    maintenance_number = models.CharField(max_length=100, verbose_name="Номер проведения ТО")
    maintenance_type = models.CharField(max_length=100, verbose_name="Вид ТО")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Техническое обслуживание"
        verbose_name_plural = "Техническое обслуживание"
        ordering = ["-maintenance_date", "-id"]

    def __str__(self):
        return f"{self.machine_brand} {self.inventory_number} {self.maintenance_type}"


class MaintenanceTaskFact(models.Model):
    record = models.ForeignKey(
        MaintenanceRecord,
        on_delete=models.CASCADE,
        related_name="tasks",
        verbose_name="Документ ТО",
    )
    work_name = models.TextField(verbose_name="Работа")
    detail_group = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Группа деталей",
    )
    item_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Наименование",
    )
    catalog_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="Кат. №",
    )
    unit = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Ед. изм.",
    )
    qty_plan = models.FloatField(blank=True, null=True, verbose_name="Количество план")
    qty_fact = models.FloatField(blank=True, null=True, verbose_name="Количество факт")

    class Meta:
        verbose_name = "Строка ТО"
        verbose_name_plural = "Строки ТО"
        ordering = ["id"]

    def __str__(self):
        return self.work_name[:80]


class AggregateJournalUpload(models.Model):
    STATUS_NEW = "new"
    STATUS_IMPORTING = "importing"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"

    STATUS_CHOICES = [
        (STATUS_NEW, "Новый"),
        (STATUS_IMPORTING, "Импортируется"),
        (STATUS_DONE, "Импортирован"),
        (STATUS_ERROR, "Ошибка"),
    ]

    title = models.CharField(max_length=255, blank=True, verbose_name="Название")
    file = models.FileField(
        upload_to="aggregate_journal/%Y/%m/",
        verbose_name="Файл Excel",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
        db_index=True,
        verbose_name="Статус",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Загружен")
    imported_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Импортирован",
    )
    rows_count = models.PositiveIntegerField(default=0, verbose_name="Количество строк")
    error_text = models.TextField(blank=True, verbose_name="Текст ошибки")

    class Meta:
        verbose_name = "Загрузка агрегатного журнала"
        verbose_name_plural = "Загрузки агрегатного журнала"
        ordering = ["-uploaded_at"]

    def save(self, *args, **kwargs):
        if not self.title and self.file:
            self.title = os.path.basename(self.file.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title or f"Файл #{self.pk}"


class AggregateJournalRow(models.Model):
    upload = models.ForeignKey(
        AggregateJournalUpload,
        on_delete=models.CASCADE,
        related_name="rows",
        verbose_name="Загрузка",
    )
    source_row_number = models.PositiveIntegerField(
        default=0,
        verbose_name="Номер строки в Excel",
    )

    department = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        verbose_name="Подразделение",
    )
    machine_brand = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        verbose_name="Марка",
    )
    modification = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Модификация",
    )
    inventory_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        verbose_name="Инвентарный номер",
    )

    maintenance_start_date = models.DateTimeField(
        blank=True,
        null=True,
        db_index=True,
        verbose_name="Дата начала обслуживания",
    )
    maintenance_end_date = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Дата окончания обслуживания",
    )

    actual_hours_at_maintenance = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Фактическая наработка в момент проведения ТО",
    )
    machine_hours = models.FloatField(
        blank=True,
        null=True,
        verbose_name="Наработка машины",
    )
    maintenance_type = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Вид ТО",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Строка агрегатного журнала"
        verbose_name_plural = "Строки агрегатного журнала"
        ordering = ["-maintenance_start_date", "-id"]
        indexes = [
            models.Index(fields=["maintenance_start_date"]),
            models.Index(fields=["machine_brand", "inventory_number"]),
            models.Index(fields=["department", "machine_brand"]),
        ]

    def __str__(self):
        return f"{self.machine_brand} {self.inventory_number} {self.maintenance_start_date}"