from django.contrib import admin

from .models import (
    OtipbHistory,
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
        'medical_commission',
        'otipb',
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


@admin.register(OtipbHistory)
class OtipbHistoryAdmin(admin.ModelAdmin):
    list_display = (
        'full_name',
        'position',
        'contacts',
        'otipb',
        'source',
        'source_date',
        'created_at',
    )

    search_fields = (
        'full_name',
        'full_name_normalized',
        'position',
        'contacts',
        'otipb',
        'comment',
    )

    list_filter = (
        'source',
        'source_date',
        'created_at',
    )

    readonly_fields = (
        'full_name_normalized',
        'created_at',
        'updated_at',
    )

    ordering = (
        '-source_date',
        '-id',
    )