# Django models

## CharField
name = models.CharField("Название", max_length=255)

## Необязательная строка
comment = models.TextField("Комментарий", blank=True, default="")

## Необязательная дата
order_date = models.DateTimeField("Дата", null=True, blank=True)

## Служебные даты
created_at = models.DateTimeField(auto_now_add=True)
updated_at = models.DateTimeField(auto_now=True)

## choices
class Status(models.TextChoices):
    NEW = "new", "Новый"
    DONE = "done", "Завершен"

status = models.CharField(
    max_length=20,
    choices=Status.choices,
    default=Status.NEW,
)

from django.db import models


# 1. Models
``` python
class TransferOrder(models.Model):
    number = models.CharField("Номер", max_length=50, unique=True, db_index=True)
    order_date = models.DateTimeField("Дата", null=True, blank=True, db_index=True)
    organization = models.CharField("Организация", max_length=255, blank=True, default="")
    comment = models.TextField("Комментарий", blank=True, default="")
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Заказ на перемещение"
        verbose_name_plural = "Заказы на перемещение"
        ordering = ["-order_date", "-id"]

    def __str__(self):
        return self.number
```
## Частые параметры полей 
```python
models.CharField(max_length=255)              # короткий текст
models.TextField()                            # длинный текст
models.DateField()                            # только дата
models.DateTimeField()                        # дата и время
models.IntegerField()                         # целое число
models.DecimalField(max_digits=12, decimal_places=2)   # число с дробной частью
models.BooleanField(default=False)            # True / False
models.JSONField(null=True, blank=True)       # JSON
models.ForeignKey("app.Model", on_delete=models.CASCADE)  # связь
```
Важное различие
- blank=True — влияет на формы и admin
- null=True — влияет на базу данных

Для строк обычно так

```python
name = models.CharField(max_length=255, blank=True, default="")
comment = models.TextField(blank=True, default="")
```
Для дат и чисел часто так

```python
order_date = models.DateTimeField(null=True, blank=True)
amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
```
# 2. Choices / статусы
Когда использовать

Подходит для:
- статуса
- приоритета
- роли
- типа документа
```python
class TransferOrder(models.Model):
    class Status(models.TextChoices):
        TO_SUPPLY = "to_supply", "К обеспечению"
        TO_EXECUTE = "to_execute", "К выполнению"
        CLOSED = "closed", "Закрыт"
        UNKNOWN = "unknown", "Не определен"

    status = models.CharField(
        "Статус",
        max_length=30,
        choices=Status.choices,
        default=Status.UNKNOWN,
        db_index=True,
    )
```
```python
TO_SUPPLY = "to_supply", "К обеспечению"
```
- TO_SUPPLY — имя константы в Python
- "to_supply" — хранится в базе
- "К обеспечению" — показывается пользователю

Как использовать

```python
order.status = TransferOrder.Status.TO_SUPPLY
```
Красивый вывод
```python
order.get_status_display()
```
# 3. ForeignKey 
Когда нужен

Когда есть отдельная сущность:

-пользователь
-склад
-подразделение
-категория

Пример
```python
class Warehouse(models.Model):
    name = models.CharField("Название", max_length=255)

    def __str__(self):
        return self.name


class TransferOrder(models.Model):
    sender_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_orders",
        verbose_name="Склад-отправитель",
    )
```

Частые on_delete
- models.CASCADE — удалить вместе со связанной записью
- models.SET_NULL — поставить NULL
- models.PROTECT — запретить удаление

# 4. Миграции

```python
   python manage.py makemigrations
   python manage.py migrate
```

```python
   python manage.py sqlmigrate logistics 0001
```
# 5. Admin

Регистрация модели
```python
from django.contrib import admin
from .models import TransferOrder


@admin.register(TransferOrder)
class TransferOrderAdmin(admin.ModelAdmin):
    list_display = ("number", "order_date", "organization", "status")
    list_filter = ("status", "organization")
    search_fields = ("number", "organization", "comment")
    ordering = ("-order_date",)
```
Что значит
- list_display — какие колонки показывать
- list_filter — фильтры справа
- search_fields — поиск
- ordering — сортировка

# 6. Views

Простая функция-представление

```python
from django.shortcuts import render


def order_list(request):
    return render(request, "logistics/order_list.html")
```
Передача данных в шаблон

```python
from django.shortcuts import render
from .models import TransferOrder


def order_list(request):
    orders = TransferOrder.objects.all()
    return render(request, "logistics/order_list.html", {"orders": orders})
```
Получить один объект

```python
from django.shortcuts import get_object_or_404

def order_detail(request, pk):
    order = get_object_or_404(TransferOrder, pk=pk)
    return render(request, "logistics/order_detail.html", {"order": order})
```

Редирект

```python
from django.shortcuts import redirect

return redirect("logistics:order_list")
```
Защита входом

```python
from django.contrib.auth.decorators import login_required

@login_required
def order_list(request):
```
# 7.URLs

В приложении logistics/urls.py

```python
from django.urls import path
from . import views

app_name = "logistics"

urlpatterns = [
    path("", views.order_list, name="order_list"),
    path("<int:pk>/", views.order_detail, name="order_detail"),
]
```
В корневом urls.py

```python
from django.urls import path, include

urlpatterns = [
    path("logistics/", include("logistics.urls")),
]
```
