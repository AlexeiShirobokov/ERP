from django.contrib import admin, messages
from .models import OperateDataFile, OperateRow
from .services.import_excel import import_excel_to_db


class OperateRowInline(admin.TabularInline):
    model = OperateRow
    extra = 0
    can_delete = False
    show_change_link = True
    fields = (
        "date",
        "subdivision",
        "block",
        "process_name",
        "machine_brand",
        "work_volume",
        "corrected_work_volume",
        "work_time",
        "downtime",
    )
    readonly_fields = fields
    max_num = 20


@admin.register(OperateDataFile)
class OperateDataFileAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "file", "is_active", "is_processed", "uploaded_at")
    list_filter = ("is_active", "is_processed", "uploaded_at")
    search_fields = ("title", "comment", "file")
    ordering = ("-uploaded_at", "-id")
    readonly_fields = ("uploaded_at", "is_processed", "processing_error")
    inlines = [OperateRowInline]
    actions = ["reimport_selected"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        try:
            import_excel_to_db(obj)
            self.message_user(request, "Файл успешно загружен и импортирован в базу.", level=messages.SUCCESS)
        except Exception as exc:
            obj.is_processed = False
            obj.processing_error = str(exc)
            obj.save(update_fields=["is_processed", "processing_error"])
            self.message_user(request, f"Ошибка импорта: {exc}", level=messages.ERROR)

    @admin.action(description="Переимпортировать выбранные файлы")
    def reimport_selected(self, request, queryset):
        ok_count = 0
        err_count = 0

        for obj in queryset:
            try:
                import_excel_to_db(obj)
                ok_count += 1
            except Exception as exc:
                err_count += 1
                obj.is_processed = False
                obj.processing_error = str(exc)
                obj.save(update_fields=["is_processed", "processing_error"])

        if ok_count:
            self.message_user(request, f"Успешно переимпортировано: {ok_count}", level=messages.SUCCESS)
        if err_count:
            self.message_user(request, f"С ошибкой: {err_count}", level=messages.WARNING)


@admin.register(OperateRow)
class OperateRowAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "data_file",
        "date",
        "subdivision",
        "block",
        "process_name",
        "machine_brand",
        "work_volume",
        "corrected_work_volume",
        "work_time",
        "downtime",
    )
    list_filter = ("data_file", "subdivision", "process_name", "year", "month")
    search_fields = (
        "subdivision",
        "block",
        "process_name",
        "machine_brand",
        "machine_name",
        "machine_inventory",
        "shift_master",
        "operator_name",
        "assistant_name",
        "downtime_reason",
    )
    ordering = ("-date", "-id")