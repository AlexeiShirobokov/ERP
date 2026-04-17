from django import forms
from .models import ResumeCandidate


class ResumeCandidateForm(forms.ModelForm):
    class Meta:
        model = ResumeCandidate
        fields = [
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
            #'medical_referral',
            'otipb',
            'refusal_reason',

            'ticket',
            'stage',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'comment': forms.Textarea(attrs={'rows': 2}),
            'qualification': forms.Textarea(attrs={'rows': 2}),
            'note': forms.Textarea(attrs={'rows': 2}),
            'refusal_reason': forms.Textarea(attrs={'rows': 2}),
            'hz': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for _, field in self.fields.items():
            css_class = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            current = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{current} {css_class}'.strip()