from django.contrib import admin
from .models import ResumeCandidate


@admin.register(ResumeCandidate)
class ResumeCandidateAdmin(admin.ModelAdmin):
    list_display = (
        'number',
        'date',
        'full_name',
        'position',
        'contacts',
        'stage',
        'medical_commission',
        'ticket',
    )
    list_filter = ('stage', 'medical_commission', 'date')
    search_fields = ('full_name', 'hh_vacancy', 'position', 'contacts', 'ticket')
    ordering = ('stage', 'sort_order', '-date', '-id')