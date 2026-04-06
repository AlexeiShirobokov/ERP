from django.contrib import admin
from .models import DebitorCase, DebitorSnapshot


class DebitorSnapshotInline(admin.TabularInline):
    model = DebitorSnapshot
    extra = 0
    can_delete = False
    show_change_link = True
    readonly_fields = (
        "report_date",
        "date",
        "sum_dt",
        "sum_kt",
        "records_count",
        "debt_date",
        "debt_term",
        "debt_period",
        "debt_reason_excel",
        "responsible_department_excel",
        "created_at",
    )


@admin.register(DebitorCase)
class DebitorCaseAdmin(admin.ModelAdmin):
    list_display = (
        "account",
        "subkonto1",
        "subkonto2",
        "subkonto3",
        "last_report_date",
        "stage",
        "responsible_person",
        "is_active",
        "updated_at",
    )
    search_fields = (
        "account",
        "subkonto1",
        "subkonto2",
        "subkonto3",
        "debt_reason",
        "responsible_person",
        "comment",
    )
    list_filter = (
        "stage",
        "is_active",
        "last_report_date",
        "updated_at",
    )
    ordering = ("-updated_at", "-id")
    inlines = [DebitorSnapshotInline]


@admin.register(DebitorSnapshot)
class DebitorSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "case",
        "report_date",
        "date",
        "sum_dt",
        "sum_kt",
        "debt_term",
        "debt_period",
        "created_at",
    )
    search_fields = (
        "case__account",
        "case__subkonto1",
        "case__subkonto2",
        "case__subkonto3",
        "report_date",
    )
    list_filter = (
        "report_date",
        "debt_period",
        "created_at",
    )
    ordering = ("-report_date", "-id")
    list_select_related = ("case",)