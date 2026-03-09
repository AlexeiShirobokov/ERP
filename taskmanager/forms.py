from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory

from .models import (
    Task,
    Project,
    ProjectItem,
    BusinessProcess,
    PurchaseRequest,
)

User = get_user_model()


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "description", "deadline"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
        }


class DelegateTaskForm(forms.ModelForm):
    new_responsible = forms.ModelChoiceField(
        queryset=User.objects.all(),
        label="Новый ответственный",
        required=True,
        widget=forms.Select(attrs={"class": "form-select"})
    )

    class Meta:
        model = Task
        fields = ["new_responsible"]


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["title", "description", "deadline", "manager"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "manager": forms.Select(attrs={"class": "form-select"}),
        }


class ProjectItemForm(forms.ModelForm):
    assignees = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 4}),
        label="Исполнители",
    )

    class Meta:
        model = ProjectItem
        fields = ["title", "deadline", "is_completed", "order"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "order": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
        }

    def __init__(self, *args, **kwargs):
        qs = kwargs.pop("assignees_qs", None)
        super().__init__(*args, **kwargs)
        self.fields["assignees"].queryset = qs if qs is not None else User.objects.all()


ProjectItemFormSet = inlineformset_factory(
    Project,
    ProjectItem,
    form=ProjectItemForm,
    fields=["title", "deadline", "is_completed", "order"],
    extra=1,
    can_delete=True,
)


class BusinessProcessForm(forms.ModelForm):
    class Meta:
        model = BusinessProcess
        fields = ["title", "manager", "deadline", "description"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "required": True}),
            "manager": forms.Select(attrs={"class": "form-select"}),
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }


class PurchaseRequestForm(forms.ModelForm):
    assignees = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 4}),
        label="Исполнители",
    )

    class Meta:
        model = PurchaseRequest
        fields = [
            "title",
            "description",
            "amount",
            "supplier",
            "deadline",
            "assignees",
            "stage",
            "order",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "required": True}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "supplier": forms.TextInput(attrs={"class": "form-control"}),
            "deadline": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "stage": forms.Select(attrs={"class": "form-select"}),
            "order": forms.NumberInput(attrs={"class": "form-control"}),
        }


PurchaseFormSet = inlineformset_factory(
    BusinessProcess,
    PurchaseRequest,
    form=PurchaseRequestForm,
    extra=1,
    can_delete=True,
)