from collections import OrderedDict

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from .forms import TransferImportForm, TransferOrderStatusForm
from .models import TransferDepartment, TransferImportBatch, TransferItem, TransferOrder
from .services import import_transfer_batch


def can_view_all_transfers(user):
    if not user or not user.is_authenticated:
        return False
    return (
        user.is_superuser
        or user.has_perm('transfers.view_all_transferorder')
        or user.groups.filter(name='transfers_dispatchers').exists()
    )


def can_manage_delivery(user):
    if not user or not user.is_authenticated:
        return False
    return (
        user.is_superuser
        or user.has_perm('transfers.manage_transfer_delivery')
        or user.groups.filter(name='transfers_dispatchers').exists()
    )


def get_visible_orders_queryset(user):
    queryset = (
        TransferOrder.objects
        .select_related('department', 'delivered_by', 'last_import_batch')
        .prefetch_related('items')
    )
    if can_view_all_transfers(user):
        return queryset
    departments = TransferDepartment.objects.filter(users=user, is_active=True)
    return queryset.filter(department__in=departments)


def filter_orders_queryset(queryset, request):
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    department = request.GET.get('department', '').strip()
    receiver = request.GET.get('receiver', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if q:
        queryset = queryset.filter(
            Q(order_number__icontains=q)
            | Q(order_title__icontains=q)
            | Q(movement_numbers__icontains=q)
            | Q(responsible_name__icontains=q)
            | Q(sender_warehouse__icontains=q)
            | Q(receiver_warehouse__icontains=q)
            | Q(items__item_name__icontains=q)
        ).distinct()
    if status:
        queryset = queryset.filter(status=status)
    if department:
        queryset = queryset.filter(department_id=department)
    if receiver:
        queryset = queryset.filter(receiver_warehouse__icontains=receiver)
    if date_from:
        queryset = queryset.filter(order_date__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(order_date__date__lte=date_to)
    return queryset


class TransferOrderListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = TransferOrder
    template_name = 'transfers/order_list.html'
    context_object_name = 'orders'
    paginate_by = 50
    permission_required = 'transfers.view_transferorder'
    raise_exception = True

    def get_queryset(self):
        queryset = get_visible_orders_queryset(self.request.user).order_by('-updated_at', '-order_date')
        return filter_orders_queryset(queryset, self.request)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visible_orders = filter_orders_queryset(get_visible_orders_queryset(self.request.user), self.request)
        context['q'] = self.request.GET.get('q', '')
        context['selected_status'] = self.request.GET.get('status', '')
        context['selected_department'] = self.request.GET.get('department', '')
        context['receiver'] = self.request.GET.get('receiver', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        context['status_choices'] = TransferOrder.Status.choices
        context['departments'] = TransferDepartment.objects.filter(is_active=True).order_by('sort_order', 'name')
        context['can_view_all'] = can_view_all_transfers(self.request.user)
        context['can_manage_delivery'] = can_manage_delivery(self.request.user)
        context['total_orders'] = visible_orders.count()
        context['total_requested'] = visible_orders.aggregate(total=Sum('items__quantity_requested'))['total'] or 0
        context['total_moved'] = visible_orders.aggregate(total=Sum('items__quantity_moved'))['total'] or 0
        context['last_batch'] = TransferImportBatch.objects.order_by('-created_at').first()
        return context


class TransferOrderKanbanView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    template_name = 'transfers/order_kanban.html'
    permission_required = 'transfers.view_transferorder'
    raise_exception = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = filter_orders_queryset(
            get_visible_orders_queryset(self.request.user).order_by('-updated_at', '-order_date'),
            self.request,
        )
        columns = OrderedDict((code, {'code': code, 'name': label, 'items': [], 'count': 0}) for code, label in TransferOrder.Status.choices)
        for order in queryset:
            columns[order.status]['items'].append(order)
            columns[order.status]['count'] += 1
        context['columns'] = columns.values()
        context['status_choices'] = TransferOrder.Status.choices
        context['departments'] = TransferDepartment.objects.filter(is_active=True).order_by('sort_order', 'name')
        context['selected_status'] = self.request.GET.get('status', '')
        context['selected_department'] = self.request.GET.get('department', '')
        context['q'] = self.request.GET.get('q', '')
        context['can_manage_delivery'] = can_manage_delivery(self.request.user)
        return context


class TransferOrderDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = TransferOrder
    template_name = "transfers/order_detail.html"
    context_object_name = "order"
    permission_required = "transfers.view_transferorder"
    raise_exception = True

    def get_queryset(self):
        return (
            get_visible_orders_queryset(self.request.user)
            .prefetch_related(None)
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=TransferItem.objects.order_by("item_name"),
                )
            )
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_form"] = TransferOrderStatusForm(instance=self.object)
        context["can_manage_delivery"] = can_manage_delivery(self.request.user)
        return context


class TransferOrderStatusUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'transfers.manage_transfer_delivery'
    raise_exception = True

    def post(self, request, pk):
        order = get_object_or_404(get_visible_orders_queryset(request.user), pk=pk)
        form = TransferOrderStatusForm(request.POST, instance=order)
        if form.is_valid():
            order = form.save(commit=False)
            if order.status == TransferOrder.Status.DELIVERED and not order.delivered_at:
                order.delivered_at = timezone.now()
            if order.status == TransferOrder.Status.DELIVERED and request.user.is_authenticated:
                order.delivered_by = request.user
            order.save()
            messages.success(request, 'Статус перемещения обновлен.')
        else:
            messages.error(request, 'Статус не обновлен. Проверьте заполнение формы.')
        return redirect('transfers:order_detail', pk=pk)


class TransferImportView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    template_name = 'transfers/import.html'
    form_class = TransferImportForm
    success_url = reverse_lazy('transfers:order_list')
    permission_required = 'transfers.add_transferimportbatch'
    raise_exception = True

    def form_valid(self, form):
        batch = form.save(commit=False)
        batch.imported_by = self.request.user
        batch.original_name = form.cleaned_data['file'].name
        batch.save()
        try:
            import_transfer_batch(batch.pk)
            messages.success(
                self.request,
                f'Файл загружен. Обработано строк: {batch.rows_count}, заказов: {batch.orders_count}, позиций: {batch.items_count}.',
            )
        except Exception as exc:
            batch.error = str(exc)
            batch.save(update_fields=['error'])
            messages.error(self.request, f'Ошибка импорта: {exc}')
        return super().form_valid(form)
