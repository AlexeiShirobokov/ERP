from django.urls import path
from . import views

app_name = "logistics"

urlpatterns = [
    path("logistiks/", views.logistics_view, name="logistics"),


]