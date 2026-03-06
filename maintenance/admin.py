from django.contrib import admin
from .models import Department, MaintenanceRecord, MaintenanceTaskFact


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


class MaintenanceTaskFactInline(admin.TabularInline):
    model = MaintenanceTaskFact
    extra = 0


@admin.register(MaintenanceRecord)
class MaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "maintenance_date",
        "department",
        "machine_brand",
        "inventory_number",
        "maintenance_type",
        "machine_hours",
        "responsible_fio",
    )
    search_fields = (
        "machine_brand",
        "inventory_number",
        "responsible_fio",
        "maintenance_type",
        "maintenance_number",
    )
    list_filter = ("department", "maintenance_date", "maintenance_type")
    inlines = [MaintenanceTaskFactInline]