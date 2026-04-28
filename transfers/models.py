from django.conf import settings
from django.db import models
from django.utils import timezone


class TransferDepartment(models.Model):
    name = models.CharField('Подразделение', max_length=255, unique=True)
    code = models.SlugField('Код', max_length=100, unique=True)
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name='Пользователи подразделения',
        related_name='transfer_departments',
        blank=True,
    )
    warehouse_aliases = models.TextField(
        'Склады/получатели из 1С',
        blank=True,
        help_text='Каждое название с новой строки. Например: Склад Дражный.',
    )
    is_active = models.BooleanField('Активно', default=True)
    sort_order = models.PositiveIntegerField('Порядок', default=100)

    class Meta:
        verbose_name = 'Подразделение по перемещениям'
        verbose_name_plural = 'Подразделения по перемещениям'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name

    def aliases_list(self):
        return [
            item.strip().lower()
            for item in (self.warehouse_aliases or '').splitlines()
            if item.strip()
        ]

    def matches_receiver(self, receiver_name):
        receiver = (receiver_name or '').strip().lower()
        if not receiver:
            return False
        return receiver in self.aliases_list()

    @classmethod
    def find_by_receiver(cls, receiver_name):
        receiver = (receiver_name or '').strip().lower()
        if not receiver:
            return None
        for department in cls.objects.filter(is_active=True).order_by('sort_order', 'name'):
            if department.matches_receiver(receiver):
                return department
        return None


class TransferImportBatch(models.Model):
    file = models.FileField('Файл Excel', upload_to='transfers/imports/%Y/%m/%d/')
    original_name = models.CharField('Исходное имя файла', max_length=255, blank=True)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Загрузил',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transfer_import_batches',
    )
    created_at = models.DateTimeField('Дата загрузки', auto_now_add=True)
    period_text = models.CharField('Период из файла', max_length=255, blank=True)
    rows_count = models.PositiveIntegerField('Строк обработано', default=0)
    orders_count = models.PositiveIntegerField('Заказов обновлено', default=0)
    items_count = models.PositiveIntegerField('Позиций обновлено', default=0)
    error = models.TextField('Ошибка импорта', blank=True)

    class Meta:
        verbose_name = 'Загрузка перемещений'
        verbose_name_plural = 'Загрузки перемещений'
        ordering = ['-created_at']

    def __str__(self):
        return self.original_name or f'Загрузка №{self.pk}'


class TransferOrder(models.Model):
    class Status(models.TextChoices):
        REQUESTED = 'requested', 'Ожидает оформления'
        ISSUED = 'issued', 'Отгружено со склада'
        IN_TRANSIT = 'in_transit', 'В пути'
        DELIVERED = 'delivered', 'Доставлено'
        CANCELED = 'canceled', 'Отменено'

    order_number = models.CharField('Номер заказа', max_length=50, unique=True, db_index=True)
    order_title = models.CharField('Заказ на перемещение', max_length=255, blank=True)
    order_date = models.DateTimeField('Дата заказа', null=True, blank=True, db_index=True)
    movement_numbers = models.TextField('Документы перемещения', blank=True)
    last_movement_date = models.DateTimeField('Последнее перемещение', null=True, blank=True, db_index=True)
    responsible_name = models.CharField('Ответственный 1С', max_length=255, blank=True)
    sender_warehouse = models.CharField('Склад отправитель', max_length=255, blank=True, db_index=True)
    receiver_warehouse = models.CharField('Склад получатель', max_length=255, blank=True, db_index=True)
    department = models.ForeignKey(
        TransferDepartment,
        verbose_name='Подразделение',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
    )
    status = models.CharField(
        'Статус',
        max_length=30,
        choices=Status.choices,
        default=Status.REQUESTED,
        db_index=True,
    )
    planned_delivery_at = models.DateTimeField('Плановая доставка', null=True, blank=True)
    delivered_at = models.DateTimeField('Фактическая доставка', null=True, blank=True)
    delivered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Отметил доставку',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='delivered_transfer_orders',
    )
    driver_name = models.CharField('Водитель/экспедитор', max_length=255, blank=True)
    vehicle_number = models.CharField('Транспорт', max_length=100, blank=True)
    comment = models.TextField('Комментарий', blank=True)
    last_import_batch = models.ForeignKey(
        TransferImportBatch,
        verbose_name='Последняя загрузка',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
    )
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Заказ на перемещение'
        verbose_name_plural = 'Заказы на перемещение'
        ordering = ['status', '-order_date', '-updated_at']
        permissions = [
            ('view_all_transferorder', 'Может видеть все перемещения'),
            ('manage_transfer_delivery', 'Может менять доставку перемещений'),
        ]

    def __str__(self):
        return self.order_number

    @property
    def department_name(self):
        return self.department.name if self.department else 'Не назначено'

    @property
    def total_requested(self):
        return sum(item.quantity_requested or 0 for item in self.items.all())

    @property
    def total_moved(self):
        return sum(item.quantity_moved or 0 for item in self.items.all())

    def movement_numbers_list(self):
        return [item.strip() for item in (self.movement_numbers or '').splitlines() if item.strip()]

    def set_movement_number(self, number):
        number = (number or '').strip()
        if not number:
            return
        existing = self.movement_numbers_list()
        if number not in existing:
            existing.append(number)
            self.movement_numbers = '\n'.join(existing)

    def recalculate_status_from_items(self, save=True):
        if self.status in {self.Status.DELIVERED, self.Status.IN_TRANSIT, self.Status.CANCELED}:
            if save:
                self.save(update_fields=['status', 'updated_at'])
            return self.status
        has_moved = self.items.filter(quantity_moved__gt=0).exists()
        self.status = self.Status.ISSUED if has_moved else self.Status.REQUESTED
        if save:
            self.save(update_fields=['status', 'updated_at'])
        return self.status

    def mark_delivered(self, user=None):
        self.status = self.Status.DELIVERED
        self.delivered_at = self.delivered_at or timezone.now()
        if user and user.is_authenticated:
            self.delivered_by = user
        self.save(update_fields=['status', 'delivered_at', 'delivered_by', 'updated_at'])


class TransferItem(models.Model):
    order = models.ForeignKey(
        TransferOrder,
        verbose_name='Заказ',
        on_delete=models.CASCADE,
        related_name='items',
    )
    item_name = models.CharField('Номенклатура', max_length=500, db_index=True)
    quantity_requested = models.DecimalField('К оформлению Приход', max_digits=14, decimal_places=3, default=0)
    quantity_moved = models.DecimalField('К оформлению Расход', max_digits=14, decimal_places=3, default=0)
    movement_numbers = models.TextField('Документы перемещения по позиции', blank=True)
    source_rows = models.TextField('Строки исходного файла', blank=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Позиция перемещения'
        verbose_name_plural = 'Позиции перемещений'
        ordering = ['item_name']
        unique_together = [('order', 'item_name')]

    def __str__(self):
        return self.item_name

    @property
    def remaining_quantity(self):
        remaining = (self.quantity_requested or 0) - (self.quantity_moved or 0)
        return remaining if remaining > 0 else 0
