from django import forms
from .models import Department


class MaintenanceCreateForm(forms.Form):
    department = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        label="Подразделение"
    )
    machine_brand = forms.ChoiceField(
        choices=[],
        label="Марка техники"
    )
    inventory_number = forms.CharField(
        max_length=100,
        label="Инв. номер"
    )
    maintenance_date = forms.DateField(
        label="Дата проведения ТО",
        widget=forms.DateInput(attrs={"type": "date"})
    )
    responsible_fio = forms.CharField(
        max_length=255,
        label="ФИО ответственного"
    )
    machine_hours = forms.IntegerField(
        min_value=0,
        label="Машиночасы"
    )
    maintenance_number = forms.ChoiceField(
        choices=[],
        label="Вид ТО"
    )

    def __init__(self, *args, machine_brand_choices=None, maintenance_number_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["machine_brand"].choices = machine_brand_choices or []
        self.fields["maintenance_number"].choices = maintenance_number_choices or []


class MaintenanceTaskFactInputForm(forms.Form):
    work_name = forms.CharField(label="Работа", required=False)
    detail_group = forms.CharField(label="Группа деталей", required=False)
    item_name = forms.CharField(label="Наименование", required=False)
    catalog_number = forms.CharField(label="Кат. №", required=False)
    unit = forms.CharField(label="Ед. изм.", required=False)
    qty_plan = forms.CharField(label="Количество план", required=False)
    qty_fact = forms.FloatField(label="Количество факт", required=False)