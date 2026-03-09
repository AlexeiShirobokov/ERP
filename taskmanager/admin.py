from django.contrib import admin
from .models import (
    Task,
    TaskParticipant,
    TaskMessage,
    TaskFile,
    Project,
    ProjectMember,
    ProjectItem,
    ProjectItemAssignee,
    ProjectMessage,
    ProjectFile,
    BusinessProcess,
    BusinessProcessMember,
    PurchaseRequest,
    BPMessage,
    BPFile,
    PRComment,
    PRFile,
)


class TaskParticipantInline(admin.TabularInline):
    model = TaskParticipant
    extra = 0


class TaskMessageInline(admin.TabularInline):
    model = TaskMessage
    extra = 0
    readonly_fields = ("sender", "content", "timestamp")


class TaskFileInline(admin.TabularInline):
    model = TaskFile
    extra = 0
    readonly_fields = ("uploaded_at", "uploaded_by")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "creator",
        "responsible",
        "deadline",
        "is_completed",
        "is_delegated",
        "created_at",
    )
    list_filter = ("is_completed", "is_delegated", "deadline", "created_at")
    search_fields = ("title", "description", "creator__username", "responsible__username")
    inlines = [TaskParticipantInline, TaskMessageInline, TaskFileInline]


@admin.register(TaskParticipant)
class TaskParticipantAdmin(admin.ModelAdmin):
    list_display = ("task", "user", "role")
    list_filter = ("role",)
    search_fields = ("task__title", "user__username", "user__first_name", "user__last_name")


@admin.register(TaskMessage)
class TaskMessageAdmin(admin.ModelAdmin):
    list_display = ("task", "sender", "timestamp")
    search_fields = ("task__title", "sender__username", "content")


@admin.register(TaskFile)
class TaskFileAdmin(admin.ModelAdmin):
    list_display = ("task", "filename", "uploaded_at", "uploaded_by")
    search_fields = ("task__title", "file")


class ProjectMemberInline(admin.TabularInline):
    model = ProjectMember
    extra = 0


class ProjectItemInline(admin.TabularInline):
    model = ProjectItem
    extra = 0


class ProjectMessageInline(admin.TabularInline):
    model = ProjectMessage
    extra = 0
    readonly_fields = ("sender", "content", "timestamp")


class ProjectFileInline(admin.TabularInline):
    model = ProjectFile
    extra = 0
    readonly_fields = ("uploaded_at", "uploaded_by")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "creator", "manager", "deadline", "created_at")
    search_fields = ("title", "description", "creator__username", "manager__username")
    list_filter = ("deadline", "created_at")
    inlines = [ProjectMemberInline, ProjectItemInline, ProjectMessageInline, ProjectFileInline]


@admin.register(ProjectItem)
class ProjectItemAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "deadline", "is_completed", "order")
    list_filter = ("is_completed",)
    search_fields = ("title", "project__title")


@admin.register(ProjectItemAssignee)
class ProjectItemAssigneeAdmin(admin.ModelAdmin):
    list_display = ("item", "user")
    search_fields = ("item__title", "user__username")


@admin.register(BusinessProcess)
class BusinessProcessAdmin(admin.ModelAdmin):
    list_display = ("title", "creator", "manager", "deadline", "created_at")
    search_fields = ("title", "description", "creator__username", "manager__username")
    list_filter = ("deadline", "created_at")


@admin.register(BusinessProcessMember)
class BusinessProcessMemberAdmin(admin.ModelAdmin):
    list_display = ("process", "user", "role")
    list_filter = ("role",)
    search_fields = ("process__title", "user__username")


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = ("title", "process", "stage", "order", "amount", "supplier", "deadline", "created_at")
    list_filter = ("stage", "deadline", "created_at")
    search_fields = ("title", "description", "supplier", "process__title")


@admin.register(BPMessage)
class BPMessageAdmin(admin.ModelAdmin):
    list_display = ("process", "sender", "timestamp")
    search_fields = ("process__title", "sender__username", "content")


@admin.register(BPFile)
class BPFileAdmin(admin.ModelAdmin):
    list_display = ("process", "filename", "uploaded_at", "uploaded_by")
    search_fields = ("process__title", "file")


@admin.register(PRComment)
class PRCommentAdmin(admin.ModelAdmin):
    list_display = ("item", "author", "created_at")
    search_fields = ("item__title", "author__username", "text")


@admin.register(PRFile)
class PRFileAdmin(admin.ModelAdmin):
    list_display = ("item", "filename", "uploaded_at", "uploaded_by")
    search_fields = ("item__title", "file")