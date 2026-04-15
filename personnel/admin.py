from django.contrib import admin

from .models import PersonnelDocument, PersonnelRecord


class PersonnelDocumentInline(admin.TabularInline):
    model = PersonnelDocument
    extra = 0
    readonly_fields = ("uploaded_at", "uploaded_by")
    fields = ("title", "file", "comment", "uploaded_by", "uploaded_at")


@admin.register(PersonnelRecord)
class PersonnelRecordAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "date",
        "full_name",
        "position_name",
        "medical_commission",
        "estimated_arrival_date",
        "created_by",
        "updated_by",
    )
    search_fields = (
        "full_name",
        "hh_candidate",
        "position_name",
        "contacts",
        "medical_commission",
        "ticket",
    )
    list_filter = ("date", "estimated_arrival_date", "medical_commission")
    readonly_fields = ("created_at", "updated_at", "created_by", "updated_by")
    inlines = [PersonnelDocumentInline]


@admin.register(PersonnelDocument)
class PersonnelDocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "record", "uploaded_by", "uploaded_at")
    search_fields = ("title", "record__full_name", "record__position_name")
    readonly_fields = ("uploaded_at", "uploaded_by")