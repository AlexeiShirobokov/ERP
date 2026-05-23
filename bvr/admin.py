# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import PassportRecognition


@admin.register(PassportRecognition)
class PassportRecognitionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "file_name", "ok", "source",
                    "wells_count", "avg_depth", "user")
    list_filter = ("ok", "source", "created_at")
    search_fields = ("file_name", "file_hash", "user")
    readonly_fields = ("created_at", "file_hash", "payload", "warnings")
    date_hierarchy = "created_at"
