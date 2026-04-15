from django.urls import path

from . import views

app_name = "personnel"

urlpatterns = [
    path("", views.record_list, name="record_list"),
    path("create/", views.record_create, name="record_create"),
    path("<int:pk>/", views.record_detail, name="record_detail"),
    path("<int:pk>/edit/", views.record_update, name="record_update"),
    path("<int:pk>/delete/", views.record_delete, name="record_delete"),

    path("<int:record_id>/documents/upload/", views.document_upload, name="document_upload"),
    path("documents/<int:pk>/download/", views.document_download, name="document_download"),
    path("documents/<int:pk>/delete/", views.document_delete, name="document_delete"),
]