import os

from django.db import models

class TransferOrder(models.Model):
    class Status(models.TextChoices):
        TO_SUPPLY="to_supply", "К обеспечению"
        TO_EXECUTE="to_execute", "К выполнению"
        CLOSED="closed", "Закрыт"
        UNKNOWN="unknow", "Не определен"

    class Source(models.TextChoices):
        EXCEL="excel", "EXCEL"
        API="api", "API 1C"

    number=models.CharField("Номер", max_length=10, unique=True, db_index=True)
    order_date=models.DateField("Дата", null=True, blank=True, db_index=True )
    sender_warehouse=models.CharField("Склад-отправитель", max_length=100, blank=True, default="", db_index=True)
    receiver_warehouse = models.CharField("Склад-получатель", max_length=100, blank=True, default="", db_index=True)

    status=models.CharField("Нормализованный статус", max_length=100, )

