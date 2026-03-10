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
        verbose_name="Подразделение"
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
        verbose_name="Документ ТО"
    )
    work_name = models.TextField(verbose_name="Работа")
    detail_group = models.CharField(max_length=255, blank=True, null=True, verbose_name="Группа деталей")
    item_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Наименование")
    catalog_number = models.CharField(max_length=100, blank=True, null=True, verbose_name="Кат. №")
    unit = models.CharField(max_length=50, blank=True, null=True, verbose_name="Ед. изм.")
    qty_plan = models.FloatField(blank=True, null=True, verbose_name="Количество план")
    qty_fact = models.FloatField(blank=True, null=True, verbose_name="Количество факт")

    class Meta:
        verbose_name = "Строка ТО"
        verbose_name_plural = "Строки ТО"
        ordering = ["id"]

    def __str__(self):
        return self.work_name[:80]

