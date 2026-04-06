from django.urls import path
from . import views

urlpatterns = [
    path("debitor-report/", views.debitor_report, name="debitor_report"),
    path("debitor-report/sync/", views.debitor_sync, name="debitor_sync"),
    path("debitor-report/case/", views.debitor_case, name="debitor_case"),
    path("debitor-report/export/", views.export_debitor_excel, name="export_debitor_excel"),
    path("debitor-board/", views.debitor_board, name="debitor_board"),
    path("debitor-board/move/", views.move_debitor_case, name="move_debitor_case"),
    path("debitor-aging/", views.debitor_aging, name="debitor_aging"),
]