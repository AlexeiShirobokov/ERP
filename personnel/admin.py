from django.contrib import admin

from .models import (
    CandidateSourceRecord,
    ResumeCandidate,
    ResumeCandidateDocument,
    ResumeStage,
)


class ResumeCandidateDocumentInline(admin.TabularInline):
    model = ResumeCandidateDocument
    extra = 0
    fields = (
        'title',
        'file',
        'comment',
        'uploaded_by',
        'uploaded_at',
    )
    readonly_fields = (
        'uploaded_at',
    )


@admin.register(ResumeStage)
class ResumeStageAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'code',
        'sort_order',
        'is_active',
        'responsible_user',
        'notify_email',
    )

    list_editable = (
        'sort_order',
        'is_active',
    )

    search_fields = (
        'name',
        'code',
        'responsible_user__username',
        'responsible_user__first_name',
        'responsible_user__last_name',
        'notify_email',
    )

    ordering = (
        'sort_order',
        'id',
    )


@admin.register(ResumeCandidate)
class ResumeCandidateAdmin(admin.ModelAdmin):
    list_display = (
        'number',
        'date',
        'full_name',
        'position',
        'contacts',
        'medical_commission',

        'stage_name_display',
        'created_at',
        'updated_at',
    )

    search_fields = (
        'full_name',
        'position',
        'contacts',
        'number',
        'otipb',
    )

    list_filter = (
        'date',
        'medical_commission',
        'stage',
    )

    readonly_fields = (
        'created_at',
        'updated_at',
    )

    inlines = [
        ResumeCandidateDocumentInline,
    ]

    @admin.display(description='Этап')
    def stage_name_display(self, obj):
        return obj.stage_name


@admin.register(CandidateSourceRecord)
class CandidateSourceRecordAdmin(admin.ModelAdmin):
    list_display = (
        'source_number',
        'source_date',
        'full_name',
        'birth_year',
        'vacancy',
        'phone',
        'medical_direction',
        'accepted_date',
        'imported_at',
    )

    search_fields = (
        'full_name',
        'full_name_normalized',
        'vacancy',
        'phone',
        'qualification',
        'note',
        'medical_direction',
        'refusal_reason',
    )

    list_filter = (
        'source_date',
        'vacancy',
        'medical_direction',
        'accepted_date',
        'import_file_name',
    )

    readonly_fields = (
        'full_name_normalized',
        'imported_at',
        'updated_at',
    )

    ordering = (
        '-source_date',
        '-id',
    )
