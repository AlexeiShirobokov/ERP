from django.contrib import admin
from .models import DebitorComment


@admin.register(DebitorComment)
class DebitorCommentAdmin(admin.ModelAdmin):
    list_display = (
        "account",
        "subkonto1",
        "subkonto2",
        "subkonto3",
        "report_date",
        "updated_at",
    )
    search_fields = (
        "account",
        "subkonto1",
        "subkonto2",
        "subkonto3",
        "report_date",
        "comment",
    )
    list_filter = ("report_date", "updated_at")