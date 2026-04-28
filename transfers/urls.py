from django.urls import path

from .views import (
    TransferImportView,
    TransferOrderDetailView,
    TransferOrderKanbanView,
    TransferOrderListView,
    TransferOrderStatusUpdateView,
)

app_name = "transfers"

urlpatterns = [
    path("", TransferOrderListView.as_view(), name="order_list"),
    path("kanban/", TransferOrderKanbanView.as_view(), name="order_kanban"),
    path("import/", TransferImportView.as_view(), name="import"),
    path("<int:pk>/", TransferOrderDetailView.as_view(), name="order_detail"),
    path("<int:pk>/status/", TransferOrderStatusUpdateView.as_view(), name="order_status_update"),
]