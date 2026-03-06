from django.urls import path
from . import views

app_name = "maintenance"

urlpatterns = [
    path("", views.index, name="index"),
    path("create/", views.create_record, name="create_record"),
    path("fill-tasks/", views.fill_tasks, name="fill_tasks"),
    path("<int:pk>/", views.detail, name="detail"),
]