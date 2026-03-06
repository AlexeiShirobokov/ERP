from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("about/", views.about, name="about"),
    path("debitor-report/", views.debitor_report, name="debitor_report"),
    path("debitor-report/export/", views.export_debitor_excel, name="export_debitor_excel"),
]