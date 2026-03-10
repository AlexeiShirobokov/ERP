from django.urls import path
from . import views

app_name = "taskmanager"

urlpatterns = [
    path("", views.task_list, name="task_list"),
    path("dashboard/", views.dashboard, name="dashboard"),

    path("tasks/new/", views.task_create, name="task_create"),
    path("tasks/<int:pk>/", views.task_detail, name="task_detail"),
    path("tasks/<int:pk>/edit/", views.edit_task, name="edit_task"),
    path("tasks/<int:pk>/delegate/", views.delegate_task, name="delegate_task"),
    path("tasks/<int:pk>/complete/", views.complete_task, name="complete_task"),
    path("tasks/<int:pk>/upload/", views.upload_files, name="upload_files"),

    path("notifications/", views.notification_list, name="notification_list"),
    path("notifications/<int:pk>/read/", views.notification_read, name="notification_read"),

    path("projects/", views.project_list, name="project_list"),
    path("projects/new/", views.project_create, name="project_create"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path("projects/<int:pk>/edit/", views.project_edit, name="project_edit"),
    path("projects/<int:pk>/upload/", views.project_upload_files, name="project_upload_files"),

    path("processes/", views.bp_list, name="bp_list"),
    path("processes/new/", views.bp_create, name="bp_create"),
    path("processes/<int:pk>/", views.bp_detail, name="bp_detail"),
    path("processes/<int:pk>/board/", views.bp_board, name="bp_board"),
    path("processes/<int:pk>/move/", views.bp_move, name="bp_move"),
    path("processes/item/<int:item_id>/comment/", views.bp_add_comment, name="bp_add_comment"),
    path("processes/item/<int:item_id>/upload/", views.bp_upload_file, name="bp_upload_file"),
]