from django import forms

from .models import PersonnelDocument, PersonnelRecord


class BootstrapMixin:
    def apply_bootstrap(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-check-input"
            else:
                current = widget.attrs.get("class", "")
                widget.attrs["class"] = f"{current} form-control".strip()


class PersonnelRecordForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = PersonnelRecord
        fields = [
            "date",
            "full_name",
            "hh_candidate",
            "position_name",
            "contacts",
            "medical_commission",
            "comment",
            "birth_year",
            "qualification",
            "note",
            "referral_to_mo",
            "refusal_reason",
            "ticket",
            "estimated_arrival_date",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "estimated_arrival_date": forms.DateInput(attrs={"type": "date"}),
            "contacts": forms.Textarea(attrs={"rows": 2}),
            "comment": forms.Textarea(attrs={"rows": 2}),
            "qualification": forms.Textarea(attrs={"rows": 2}),
            "note": forms.Textarea(attrs={"rows": 2}),
            "refusal_reason": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()


class PersonnelDocumentForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = PersonnelDocument
        fields = ["title", "file", "comment"]
        widgets = {
            "comment": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap()