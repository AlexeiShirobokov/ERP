from django.contrib import admin, messages

from .models import TransferDepartment, TransferImportBatch, TransferItem, TransferOrder
from .services import import_transfer_batch


@admin.register(TransferDepartment)
class TransferDepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name", "code", "warehouse_aliases")
    filter_horizontal = ("users",)
    prepopulated_fields = {"code": ("name",)}


@admin.register(TransferImportBatch)
class TransferImportBatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "original_name",
        "period_text",
        "rows_count",
        "orders_count",
        "items_count",
        "imported_by",
        "created_at",
        "has_error",
    )
    list_filter = ("created_at", "imported_by")
    search_fields = ("original_name", "period_text", "error")
    readonly_fields = (
        "created_at",
        "imported_by",
        "original_name",
        "period_text",
        "rows_count",
        "orders_count",
        "items_count",
        "error",
    )
    fields = (
        "file",
        "original_name",
        "imported_by",
        "created_at",
        "period_text",
        "rows_count",
        "orders_count",
        "items_count",
        "error",
    )
    actions = ("run_import_again",)

    def has_error(self, obj):
        return bool(obj.error)

    has_error.boolean = True
    has_error.short_description = "Ошибка"

    def save_model(self, request, obj, form, change):
        is_new = obj.pk is None
        file_changed = "file" in form.changed_data

        if obj.file and not obj.original_name:
            obj.original_name = obj.file.name.split("/")[-1]

        if not obj.imported_by_id:
            obj.imported_by = request.user

        super().save_model(request, obj, form, change)

        if is_new or file_changed:
            try:
                import_transfer_batch(obj.pk)
                obj.refresh_from_db()

                self.message_user(
                    request,
                    (
                        f"Файл импортирован. "
                        f"Строк: {obj.rows_count}. "
                        f"Заказов: {obj.orders_count}. "
                        f"Позиций: {obj.items_count}."
                    ),
                    level=messages.SUCCESS,
                )

            except Exception as exc:
                obj.error = str(exc)
                obj.save(update_fields=["error"])

                self.message_user(
                    request,
                    f"Ошибка импорта: {exc}",
                    level=messages.ERROR,
                )

    @admin.action(description="Повторно обработать выбранные загрузки")
    def run_import_again(self, request, queryset):
        success_count = 0
        error_count = 0

        for batch in queryset:
            try:
                import_transfer_batch(batch.pk)
                success_count += 1
            except Exception as exc:
                batch.error = str(exc)
                batch.save(update_fields=["error"])
                error_count += 1

        if success_count:
            self.message_user(
                request,
                f"Успешно обработано загрузок: {success_count}",
                level=messages.SUCCESS,
            )

        if error_count:
            self.message_user(
                request,
                f"Загрузок с ошибками: {error_count}",
                level=messages.ERROR,
            )


class TransferItemInline(admin.TabularInline):
    model = TransferItem
    extra = 0
    readonly_fields = (
        "item_name",
        "quantity_requested",
        "quantity_moved",
        "remaining_quantity",
        "movement_numbers",
        "source_rows",
        "updated_at",
    )
    fields = (
        "item_name",
        "quantity_requested",
        "quantity_moved",
        "remaining_quantity",
        "movement_numbers",
        "source_rows",
        "updated_at",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def remaining_quantity(self, obj):
        return obj.remaining_quantity

    remaining_quantity.short_description = "Остаток"


@admin.register(TransferOrder)
class TransferOrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "order_date",
        "status",
        "department",
        "sender_warehouse",
        "receiver_warehouse",
        "last_movement_date",
        "updated_at",
    )
    list_filter = (
        "status",
        "department",
        "sender_warehouse",
        "receiver_warehouse",
    )
    search_fields = (
        "order_number",
        "order_title",
        "movement_numbers",
        "responsible_name",
        "sender_warehouse",
        "receiver_warehouse",
        "items__item_name",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "order_number",
        "order_title",
        "order_date",
        "movement_numbers",
        "last_movement_date",
        "responsible_name",
        "sender_warehouse",
        "receiver_warehouse",
        "last_import_batch",
    )
    inlines = [TransferItemInline]