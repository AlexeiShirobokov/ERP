from django import forms

from .models import ResumeCandidate, ResumeCandidateDocument


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
    'note',
    'otipb',
    'medical_referral',
    'referral_to_mo',
    'estimated_arrival_date',
    'refusal_reason',
    'ticket',
    'stage',
]


def existing_candidate_fields():
    model_field_names = {field.name for field in ResumeCandidate._meta.get_fields()}
    return [name for name in CANDIDATE_FIELD_ORDER if name in model_field_names]


def candidate_widgets():
    widgets = {}

    if 'date' in existing_candidate_fields():
        widgets['date'] = forms.DateInput(attrs={'type': 'date'})

    if 'estimated_arrival_date' in existing_candidate_fields():
        widgets['estimated_arrival_date'] = forms.DateInput(attrs={'type': 'date'})

    for field_name in ['comment', 'qualification', 'note', 'refusal_reason']:
        if field_name in existing_candidate_fields():
            widgets[field_name] = forms.Textarea(attrs={'rows': 2})

    return widgets


class ResumeCandidateForm(forms.ModelForm):
    document_title = forms.CharField(
        label='Название документа',
        max_length=255,
        required=False
    )
    document_file = forms.FileField(
        label='Файл',
        required=False
    )
    document_comment = forms.CharField(
        label='Комментарий к документу',
        required=False,
        widget=forms.Textarea(attrs={'rows': 2})
    )

    class Meta:
        model = ResumeCandidate
        fields = existing_candidate_fields()
        widgets = candidate_widgets()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for _, field in self.fields.items():
            css_class = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
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
            'comment': forms.TextInput(attrs={'placeholder': 'Комментаррий'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for _, field in self.fields.items():
            css_class = 'form-control'
            current = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{current} {css_class}'.strip()