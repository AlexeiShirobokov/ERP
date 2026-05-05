from django import forms
from django.utils.text import slugify

from .models import ResumeCandidate, ResumeCandidateDocument, ResumeStage


POSITION_OPTIONS = [
    'Автоэлектрик',
    'Аналитик',
    'Архивариус',
    'Бухгалтер по налоговому учету',
    'Бухгалтер-кассир',
    'Бухгалтер-материалист',
    'Ведущий инженер по охране окружающей среды',
    'Взрывник',
    'Водитель автомобиля АТЗ',
    'Водитель автомобиля КМУ',
    'Водитель вахтового автобуса',
    'Водитель водовоза',
    'Водитель карьерного самосвала',
    'Водитель погрузчика',
    'Водитель тяжелого карьерного самосвала',
    'Водитель-экспедитор',
    'Генеральный директор',
    'Геолог',
    'Главный бухгалтер',
    'Главный геолог',
    'Главный диспетчер',
    'Главный инженер',
    'Главный маркшейдер',
    'Главный механик',
    'Главный специалист',
    'Главный специалист службы безопасности',
    'Главный энергетик',
    'Горнорабочий',
    'Горный мастер',
    'Грузчик',
    'Директор по развитию минерально-сырьевой базы',
    'Диспетчер прииска',
    'Доводчик',
    'Заведующий отделом',
    'Заведующий складом',
    'Заведующий складом ГСМ',
    'Заместитель генерального директора по безопасности',
    'Заместитель генерального директора по ОТиПБ',
    'Заместитель генерального директора по производству',
    'Заместитель главного бухгалтера',
    'Заместитель главного инженера по кадрам',
    'Заместитель главного маркшейдера',
    'Заместитель главного механика',
    'Заместитель начальника БВР',
    'Инженер',
    'Инженер по охране труда и промышленной безопасности',
    'Инженер-проектировщик',
    'Казначей',
    'Кассир по приему драгоценных металлов',
    'Кладовщик',
    'Кладовщик ГСМ',
    'Комендант общежития',
    'Кочегар',
    'Кухонный рабочий',
    'Маркшейдер',
    'Мастер горный',
    'Машинист автогрейдера',
    'Машинист бульдозера МЗТ',
    'Машинист Бульдозера ТЗТ',
    'Машинист буровой установки D55',
    'Машинист буровой установки DM-45',
    'Машинист буровой установки JD2000',
    'Машинист буровой установки POC',
    'Машинист буровой установки Беркут',
    'Машинист буровой установки БУ-20',
    'Машинист буровой установки СБШ-250',
    'Машинист колесного бульдозера',
    'Машинист крана автомобильного',
    'Машинист погрузчика',
    'Машинист экскаватора гидравлического',
    'Менеджер по персоналу',
    'Менеджер по снабжению',
    'Механик',
    'Моторист промывочного прибора',
    'Начальник горного участка',
    'Начальник отдела',
    'Начальник склада',
    'Начальник строительного участка',
    'Начальник строительной бригады',
    'Начальник транспортного цеха',
    'Начальник участка БВР',
    'Начальник участка геологоразведки',
    'Оператор БПЛА',
    'Оператор СЗМ',
    'Оператор систем видеонаблюдения',
    'Плотник',
    'Повар',
    'Помощник бурильщика Беркут',
    'Помощник бурильщика Бу-20',
    'Помощник бурильщика СБШ-250',
    'Прачка',
    'Представитель',
    'Промывальщик геологических проб',
    'Секретарь-делопроизводитель',
    'Системный администратор',
    'Слесарь',
    'Слесарь по ремонту агрегатов',
    'Слесарь по техническому обслуживанию',
    'Старший бухгалтер-материалист',
    'Старший Бухгалтер-расчётчик',
    'Старший доводчик',
    'Старший кладовщик',
    'Старший маркшейдер',
    'Старший механик',
    'Старший специалист по безопасности',
    'Старший энергетик',
    'Сторож производственных объектов',
    'Стропальщик',
    'Судоводитель',
    'Судоводитель(капитан)',
    'Съемщик-доводчик',
    'Токарь',
    'Уборщик помещений',
    'Фельдшер',
    'Финансовый аналитик',
    'Электрогазосварщик',
    'Электрослесарь дежурный по ремонту оборудования',
    'Юрисконсульт',
]


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
    'security_approval',
    'security_comment',
    'security_refusal_reason',
    'otipb_approval',
    'otipb_comment',
    'otipb_refusal_reason',
    'department_call_approval',
    'department_call_comment',
    'chief_engineer_approval',
    'chief_engineer_comment',
    'refusal_reason',
    'ticket',
    'estimated_arrival_date',
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
    fields = existing_candidate_fields()

    if 'date' in fields:
        widgets['date'] = forms.DateInput(
            format='%Y-%m-%d',
            attrs={'type': 'date'},
        )

    if 'estimated_arrival_date' in fields:
        widgets['estimated_arrival_date'] = forms.DateInput(
            format='%Y-%m-%d',
            attrs={'type': 'date'},
        )

    if 'position' in fields:
        widgets['position'] = forms.TextInput(
            attrs={
                'list': 'position-options',
                'autocomplete': 'off',
                'placeholder': 'Начните вводить должность',
            }
        )

    textarea_fields = [
        'comment',
        'qualification',
        'work_experience',
        'note',
        'refusal_reason',
        'security_comment',
        'security_refusal_reason',
        'otipb_comment',
        'otipb_refusal_reason',
        'department_call_comment',
        'chief_engineer_comment',
    ]

    for field_name in textarea_fields:
        if field_name in fields:
            rows = 4 if field_name == 'work_experience' else 2
            widgets[field_name] = forms.Textarea(attrs={'rows': rows})

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

        if 'estimated_arrival_date' in self.fields:
            self.fields['estimated_arrival_date'].input_formats = [
                '%Y-%m-%d',
                '%d.%m.%Y',
            ]


        
        if 'position' in self.fields:
            self.fields['position'].widget.attrs.update({
                'list': 'position-options',
                'autocomplete': 'off',
                'placeholder': 'Начните вводить должность',
            })

        allowed_medical_choices = [
            ('pending', 'Ожидает направления'),
            ('issued', 'Выдано направление'),
            ('passed', 'Пройдена медкомиссия'),
        ]

        if 'medical_commission' in self.fields:
            current_value = None
            if self.instance and self.instance.pk:
                current_value = self.instance.medical_commission

            self.fields['medical_commission'].choices = allowed_medical_choices.copy()

            if current_value and current_value not in dict(allowed_medical_choices):
                self.fields['medical_commission'].choices.append(
                    (current_value, self.instance.get_medical_commission_display())
                )

        if 'security_approval' in self.fields:
            self.fields['security_approval'].required = False
            self.fields['security_approval'].initial = 'pending'

        if 'otipb_approval' in self.fields:
            self.fields['otipb_approval'].required = False
            self.fields['otipb_approval'].initial = 'pending'

        if 'department_call_approval' in self.fields:
            self.fields['department_call_approval'].required = False
            self.fields['department_call_approval'].initial = 'pending'

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
            'Если оставить пустым, код этапа процесса будет создан автоматически.'
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
