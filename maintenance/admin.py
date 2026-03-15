from django.contrib import admin, messages

from .aggregate_import import import_aggregate_upload
from .models import (
    AggregateJournalRow,
    AggregateJournalUpload,
    Department,
    MaintenanceRecord,
    MaintenanceTaskFact,
)


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


@admin.register(AggregateJournalUpload)
class AggregateJournalUploadAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "rows_count", "uploaded_at", "imported_at")
    list_filter = ("status", "uploaded_at", "imported_at")
    search_fields = ("title", "file")
    readonly_fields = ("status", "rows_count", "uploaded_at", "imported_at", "error_text")
    actions = ("import_selected_files",)

    @admin.action(description="Импортировать выбранные файлы в БД")
    def import_selected_files(self, request, queryset):
        success_count = 0

        for upload in queryset:
            try:
                imported_rows = import_aggregate_upload(upload, replace_existing_rows=True)
                success_count += 1
                self.message_user(
                    request,
                    f"Файл '{upload}' импортирован. Строк: {imported_rows}.",
                    level=messages.SUCCESS,
                )
            except Exception as exc:
                self.message_user(
                    request,
                    f"Ошибка при импорте '{upload}': {exc}",
                    level=messages.ERROR,
                )

        if success_count:
            self.message_user(
                request,
                f"Успешно обработано файлов: {success_count}.",
                level=messages.SUCCESS,
            )


@admin.register(AggregateJournalRow)
class AggregateJournalRowAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "upload",
        "department",
        "machine_brand",
        "inventory_number",
        "maintenance_start_date",
        "actual_hours_at_maintenance",
        "machine_hours",
        "maintenance_type",
    )
    list_filter = ("department", "machine_brand", "maintenance_type", "maintenance_start_date")
    search_fields = ("machine_brand", "inventory_number", "modification", "department")
    autocomplete_fields = ("upload",)