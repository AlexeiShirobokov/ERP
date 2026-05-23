from django.urls import path

from . import views

app_name = "bvr"

urlpatterns = [
    path("", views.index, name="index"),
    path("recognize-passport/", views.recognize_passport, name="recognize_passport"),
    path("download/<str:project_id>/<str:file_kind>/", views.download_project_file, name="download"),
]
