from django import forms
from django.utils.text import slugify

from .models import ResumeCandidate, ResumeCandidateDocument, ResumeStage


CANDIDATE_FIELD_ORDER = [
    'date',
    'full_name',
    'hh_vacancy',
    'position',
    'contacts',
    'medical_commission',
    'comment',
    'birth_year',
    'qualification',
    'work_experience',
    'note',
    'otipb',
    'approval_department',
    'refusal_reason',
    'ticket',
    'stage',
]


def existing_candidate_fields():
    model_field_names = {field.name for field in ResumeCandidate._meta.get_fields()}

    return [
        name
        for name in CANDIDATE_FIELD_ORDER
        if name in model_field_names
    ]


def candidate_widgets():
    widgets = {}

    if 'date' in existing_candidate_fields():
        widgets['date'] = forms.DateInput(
            format='%Y-%m-%d',
            attrs={'type': 'date'},
        )

    for field_name in ['comment', 'qualification', 'note', 'refusal_reason']:
        if field_name in existing_candidate_fields():
            widgets[field_name] = forms.Textarea(attrs={'rows': 2})

    return widgets


class ResumeCandidateForm(forms.ModelForm):
    document_title = forms.CharField(
        label='Название документа',
        max_length=255,
        required=False,
    )

    document_file = forms.FileField(
        label='Файл',
        required=False,
    )

    document_comment = forms.CharField(
        label='Комментарий к документу',
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
    )

    class Meta:
        model = ResumeCandidate
        fields = existing_candidate_fields()
        widgets = candidate_widgets()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'date' in self.fields:
            self.fields['date'].input_formats = [
                '%Y-%m-%d',
                '%d.%m.%Y',
            ]

        for _, field in self.fields.items():
            css_class = (
                'form-select'
                if isinstance(field.widget, forms.Select)
                else 'form-control'
            )

            current = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{current} {css_class}'.strip()

    def clean(self):
        cleaned_data = super().clean()

        document_title = cleaned_data.get('document_title')
        document_file = cleaned_data.get('document_file')

        if document_title and not document_file:
            self.add_error('document_file', 'Выберите файл для документа.')

        return cleaned_data


class ResumeCandidateDocumentForm(forms.ModelForm):
    class Meta:
        model = ResumeCandidateDocument
        fields = ['title', 'file', 'comment']
        widgets = {
            'comment': forms.TextInput(
                attrs={
                    'placeholder': 'Комментарий',
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for _, field in self.fields.items():
            current = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{current} form-control'.strip()


class ResumeStageForm(forms.ModelForm):
    class Meta:
        model = ResumeStage
        fields = [
            'name',
            'code',
            'sort_order',
            'is_active',
            'responsible_user',
            'notify_email',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['code'].required = False
        self.fields['code'].help_text = (
            'Если оставить пустым, код будет создан автоматически.'
        )

        self.fields['notify_email'].required = False
        self.fields['responsible_user'].required = False

        for _, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                continue

            css_class = (
                'form-select'
                if isinstance(field.widget, forms.Select)
                else 'form-control'
            )

            current = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{current} {css_class}'.strip()

        current = self.fields['is_active'].widget.attrs.get('class', '')
        self.fields['is_active'].widget.attrs['class'] = (
            f'{current} form-check-input'.strip()
        )

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip()
        name = (self.cleaned_data.get('name') or '').strip()

        if not code:
            code = slugify(name)

        if not code:
            raise forms.ValidationError('Не удалось сформировать код этапа процесса.')

        qs = ResumeStage.objects.filter(code=code)

        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise forms.ValidationError('Этап процесса с таким кодом уже существует.')

        return code
