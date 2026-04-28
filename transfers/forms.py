from django import forms

from .models import TransferImportBatch, TransferOrder


class TransferImportForm(forms.ModelForm):
    class Meta:
        model = TransferImportBatch
        fields = ['file']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['file'].widget.attrs.update({'class': 'form-control', 'accept': '.xlsx,.xlsm'})

    def clean_file(self):
        uploaded_file = self.cleaned_data['file']
        filename = uploaded_file.name.lower()
        if not filename.endswith(('.xlsx', '.xlsm')):
            raise forms.ValidationError('Загрузите Excel-файл .xlsx или .xlsm.')
        return uploaded_file


class TransferOrderStatusForm(forms.ModelForm):
    class Meta:
        model = TransferOrder
        fields = [
            'status',
            'planned_delivery_at',
            'delivered_at',
            'driver_name',
            'vehicle_number',
            'comment',
        ]
        widgets = {
            'planned_delivery_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'delivered_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'comment': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.update({'class': 'form-select'})
            else:
                field.widget.attrs.update({'class': 'form-control'})
        self.fields['planned_delivery_at'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S']
        self.fields['delivered_at'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S']
