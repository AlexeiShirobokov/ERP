from django.urls import path
from . import views

app_name = "operate"

urlpatterns = [
    path("", views.index, name="operate_index"),
]

