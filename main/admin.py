from django.contrib import admin
from .models import DebitorCase


@admin.register(DebitorCase)
class DebitorCaseAdmin(admin.ModelAdmin):
    list_display = (
        "account",
        "subkonto1",
        "subkonto2",
        "report_date",
        "stage",
        "responsible_person",
        "updated_at",
    )
    search_fields = (
        "account",
        "subkonto1",
        "subkonto2",
        "subkonto3",
        "report_date",
        "debt_reason",
        "responsible_person",
        "comment",
    )
    list_filter = ("stage", "report_date", "updated_at")