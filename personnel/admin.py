from django.contrib import admin
from .models import ResumeCandidate

@admin.register(ResumeCandidate)
class ResumeCandidateAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "date",
        "full_name",
        "position",
        "medical_commission",
        "otipb",
        "stage",
    )
    search_fields = ("full_name", "position", "contacts", "number")
    list_filter = ("date", "medical_commission", "otipb", "stage")