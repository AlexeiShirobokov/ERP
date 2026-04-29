from django.conf import settings
from django.db import models
from django.db.models import Max
from django.urls import reverse
from django.utils import timezone


DEFAULT_STAGE_DEFINITIONS = [
    {
        'code': 'phone_interview',
        'label': 'HR',
        'emails': ['maslova@pskgold.ru'],
        'sort_order': 10,
    },
    {
        'code': 'security_service',
        'label': 'Служба безопасности',
        'emails': ['platonov@pskgold.ru', 'marchenkov@pskgold.ru'],
        'sort_order': 15,
    },
    {
        'code': 'otipb',
        'label': 'ОТИПБ',
        'emails': ['sorokin@pskgold.ru'],
        'sort_order': 20,
    },
    {
        'code': 'mechanic_approval',
        'label': 'ОГМ',
        'emails': ['kruglov@pskgold.ru'],
        'sort_order': 30,
    },
    {
        'code': 'geology_approval',
        'label': 'Геологический отдел',
        'emails': ['pomalejko@pskgold.ru'],
        'sort_order': 40,
    },
    {
        'code': 'surveyor_approval',
        'label': 'Отдел маркшейдера',
        'emails': ['efimov@pskgold.ru'],
        'sort_order': 45,
    },
    {
        'code': 'transport_approval',
        'label': 'Транспортный цех',
        'emails': ['pokashevskii@pskgold.ru'],
        'sort_order': 50,
    },
    {
        'code': 'medical_direction',
        'label': 'Направление на медосмотр',
        'emails': ['kalashnikova@pskgold.ru'],
        'sort_order': 53,
    },
    {
        'code': 'ticket',
        'label': 'Требуется покупка билетов',
        'emails': ['maslovataia@pskgold.ru','kalashnikova@pskgold.ru'],
        'sort_order': 55,
    },
    {
        'code': 'hr_department',
        'label': 'Отдел кадров',
        'emails': ['pivovarova@pskgold.ru', 'kalashnikova@pskgold.ru'],
        'sort_order': 60,
    },
    {
        'code': 'hired',
        'label': 'Трудоустроен',
        'emails': [],
        'sort_order': 80,
    },
    {
        'code': 'refusal',
        'label': 'Отказ',
        'emails': [],
        'sort_order': 90,
    },
]


APPROVAL_CHOICES = [
    ('', 'Не требуется'),
    ('mechanic_approval', 'ОГМ'),
    ('geology_approval', 'Геологический отдел'),
    ('surveyor_approval', 'Отдел маркшейдера'),
    ('transport_approval', 'Транспортный цех'),
]


DEPARTMENT_STAGE_LABELS = {
    'mechanic_approval': 'ОГМ',
    'geology_approval': 'Геологический отдел',
    'surveyor_approval': 'Отдел маркшейдера',
    'transport_approval': 'Транспортный цех',
}


SECURITY_APPROVAL_CHOICES = [
    ('pending', 'Не рассмотрено'),
    ('approved', 'Согласовано'),
    ('rejected', 'Не согласовано'),
]


DEPARTMENT_CALL_APPROVAL_CHOICES = [
    ('pending', 'Не рассмотрено'),
    ('approved', 'Согласован к вызову'),
    ('rejected', 'Не согласован к вызову'),
]


def normalize_full_name(value):
    if not value:
        return ''
    return ' '.join(str(value).strip().lower().split())


class ResumeStage(models.Model):
    name = models.CharField('Название этапа процесса', max_length=255)
    code = models.SlugField('Код', max_length=100, unique=True)
    sort_order = models.PositiveIntegerField('Порядок', default=100)
    is_active = models.BooleanField('Активен', default=True)

    responsible_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Ответственный',
        related_name='resume_stages',
    )
    notify_email = models.EmailField(
        'Дополнительный email для уведомлений',
        blank=True,
    )

    class Meta:
        verbose_name = 'Этап процесса'
        verbose_name_plural = 'Этапы процесса'
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.name

    def get_notification_emails(self):
        emails = []

        if self.notify_email:
            emails.append(self.notify_email.strip())

        if self.responsible_user and self.responsible_user.email:
            emails.append(self.responsible_user.email.strip())

        result = []

        for email in emails:
            if email and email not in result:
                result.append(email)

        return result


class ResumeCandidate(models.Model):
    APPROVAL_CHOICES = APPROVAL_CHOICES

    MEDICAL_CHOICES = [
        ('pending', 'Ожидает направления'),
        ('issued', 'Выдано направление'),
        ('passed', 'Пройдена медкомиссия'),
        # Старое значение оставлено для совместимости со старыми карточками.

    ]

    SECURITY_APPROVAL_CHOICES = SECURITY_APPROVAL_CHOICES
    DEPARTMENT_CALL_APPROVAL_CHOICES = DEPARTMENT_CALL_APPROVAL_CHOICES

    hh_resume_id = models.CharField(
        'HH resume id',
        max_length=100,
        blank=True,
        db_index=True,
    )
    hh_resume_link = models.URLField(
        'Ссылка на резюме HH',
        blank=True,
    )
    hh_vacancy_id = models.CharField(
        'HH vacancy id',
        max_length=100,
        blank=True,
        db_index=True,
    )
    hh_source = models.CharField(
        'Источник HH',
        max_length=100,
        blank=True,
    )
    hh_last_sync_at = models.DateTimeField(
        'Последняя синхронизация HH',
        null=True,
        blank=True,
    )

    number = models.PositiveIntegerField(
        '№',
        unique=True,
        blank=True,
        null=True,
    )
    date = models.DateField(
        'Дата',
        default=timezone.localdate,
    )
    full_name = models.CharField(
        'ФИО',
        max_length=255,
    )
    hh_vacancy = models.CharField(
        'Соискатель по вакансии на hh.ru',
        max_length=255,
        blank=True,
    )
    position = models.CharField(
        'Должность',
        max_length=255,
        blank=True,
    )
    contacts = models.CharField(
        'Контакты',
        max_length=255,
        blank=True,
    )
    medical_commission = models.CharField(
        'Мед комиссия',
        max_length=20,
        choices=MEDICAL_CHOICES,
        default='pending',
        blank=True,
    )

    comment = models.TextField('Комментарий', blank=True)
    birth_year = models.PositiveIntegerField('Год рождения', null=True, blank=True)
    qualification = models.TextField('Квалификация, наличие удостоверения на сайте', blank=True)
    work_experience = models.TextField('Опыт работы', blank=True)
    note = models.TextField('Примечание', blank=True)


    approval_department = models.CharField(
        'Какой отдел отвечает',
        max_length=100,
        choices=APPROVAL_CHOICES,
        blank=True,
        default='',
        db_index=True,
    )

    security_approval = models.CharField(
        'Служба безопасности',
        max_length=20,
        choices=SECURITY_APPROVAL_CHOICES,
        default='pending',
        blank=True,
        db_index=True,
    )
    security_comment = models.TextField(
        'Комментарий службы безопасности',
        blank=True,
    )
    security_refusal_reason = models.TextField(
        'Причина отказа службы безопасности',
        blank=True,
    )

    otipb_approval = models.CharField(
        'ОТИПБ',
        max_length=20,
        choices=SECURITY_APPROVAL_CHOICES,
        default='pending',
        blank=True,
        db_index=True,
    )

    otipb_comment = models.TextField(
        'Комментарий ОТИПБ',
        blank=True,
    )

    otipb_refusal_reason = models.TextField(
        'Причина отказа ОТИПБ',
        blank=True,
    )

    department_call_approval = models.CharField(
        'Согласование к вызову',
        max_length=20,
        choices=DEPARTMENT_CALL_APPROVAL_CHOICES,
        default='pending',
        blank=True,
        db_index=True,
    )
    department_call_comment = models.TextField(
        'Комментарий отдела',
        blank=True,
    )

    refusal_reason = models.TextField('Примечание или причина отказа', blank=True)
    ticket = models.CharField('Билет', max_length=255, blank=True)
    estimated_arrival_date = models.DateField(
        'Расчетная дата приезда',
        null=True,
        blank=True,
    )

    stage = models.CharField(
        'Этап процесса',
        max_length=100,
        default='phone_interview',
        blank=True,
        db_index=True,
    )
    sort_order = models.PositiveIntegerField(
        'Порядок',
        default=0,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Создал',
        related_name='created_resume_candidates',
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Последний редактор',
        related_name='updated_resume_candidates',
    )

    created_at = models.DateTimeField(
        'Создано',
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        'Обновлено',
        auto_now=True,
    )

    class Meta:
        verbose_name = 'Кандидат'
        verbose_name_plural = 'Кандидаты'
        ordering = ['stage', 'sort_order', '-date', '-id']

    def __str__(self):
        return f'{self.full_name} ({self.position})'

    @classmethod
    def get_default_stage_map(cls):
        return {item['code']: item for item in DEFAULT_STAGE_DEFINITIONS}

    @classmethod
    def get_stage_object(cls, stage_code):
        if not stage_code:
            return None
        return (
            ResumeStage.objects
            .select_related('responsible_user')
            .filter(code=stage_code)
            .first()
        )

    @classmethod
    def get_stage_label(cls, stage_code):
        if not stage_code:
            return '—'

        stage_obj = cls.get_stage_object(stage_code)
        if stage_obj:
            return stage_obj.name

        default_item = cls.get_default_stage_map().get(stage_code)
        if default_item:
            return default_item['label']

        return stage_code

    @classmethod
    def get_stage_notification_emails(cls, stage_code):
        if not stage_code:
            return []

        stage_obj = cls.get_stage_object(stage_code)
        if stage_obj:
            return stage_obj.get_notification_emails()

        default_item = cls.get_default_stage_map().get(stage_code)
        if default_item:
            return default_item.get('emails', [])

        return []

    @property
    def stage_name(self):
        return self.get_stage_label(self.stage)

    @property
    def current_department_name(self):
        # Берём отдел именно по текущему этапу канбана.
        # Если карточка стоит в колонке Транспортного цеха, здесь будет
        # 'Транспортный цех'. Если в ОГМ — 'ОГМ' и так далее.
        if self.stage in DEPARTMENT_STAGE_LABELS:
            return DEPARTMENT_STAGE_LABELS[self.stage]

        approval_map = {code: label for code, label in APPROVAL_CHOICES if code}
        return approval_map.get(self.approval_department, '')

    def get_stage_display(self):
        return self.stage_name

    def save(self, *args, **kwargs):
        # Старый этап response оставлен только для обратной совместимости.
        if not self.stage or self.stage == 'response':
            self.stage = 'phone_interview'

        if not self.security_approval:
            self.security_approval = 'pending'

        if not self.department_call_approval:
            self.department_call_approval = 'pending'

        if not self.number:
            max_number = (
                ResumeCandidate.objects.aggregate(max_num=Max('number'))['max_num'] or 0
            )
            self.number = max_number + 1

        if not self.sort_order:
            max_sort = (
                ResumeCandidate.objects
                .filter(stage=self.stage)
                .aggregate(max_sort=models.Max('sort_order'))['max_sort'] or 0
            )
            self.sort_order = max_sort + 1

        super().save(*args, **kwargs)

        # Актуализируем справочную базу только после прохождения этапа ОТИПБ.
        # Пока кандидат находится на этапе ОТИПБ, запись ещё не обновляем.
        CandidateSourceRecord.create_or_update_from_candidate_if_otipb_stage_passed(self)

    def get_absolute_url(self):
        return reverse('personnel:resume_candidate_edit', kwargs={'pk': self.pk})

    def as_autofill_data(self):
        return {
            'date': self.date.isoformat() if self.date else '',
            'full_name': self.full_name or '',
            'hh_vacancy': self.hh_vacancy or '',
            'position': self.position or '',
            'contacts': self.contacts or '',
            'medical_commission': self.medical_commission or '',
            'comment': self.comment or '',
            'birth_year': self.birth_year or '',
            'qualification': self.qualification or '',
            'work_experience': self.work_experience or '',
            'note': self.note or '',

            'approval_department': self.approval_department or '',
            'security_approval': self.security_approval or 'pending',
            'security_comment': self.security_comment or '',
            'security_refusal_reason': self.security_refusal_reason or '',
            'otipb_approval': self.otipb_approval or 'pending',
            'otipb_comment': self.otipb_comment or '',
            'otipb_refusal_reason': self.otipb_refusal_reason or '',
            'department_call_approval': self.department_call_approval or 'pending',
            'department_call_comment': self.department_call_comment or '',
            'refusal_reason': self.refusal_reason or '',
            'ticket': self.ticket or '',
            'estimated_arrival_date': self.estimated_arrival_date.isoformat() if self.estimated_arrival_date else '',
            'stage': self.stage or '',
        }


class ResumeCandidateDocument(models.Model):
    record = models.ForeignKey(
        'ResumeCandidate',
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name='Кандидат',
    )
    title = models.CharField('Название', max_length=255)
    file = models.FileField('Файл', upload_to='personnel/candidate_documents/%Y/%m/')
    comment = models.TextField('Комментарий', blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Загрузил',
    )
    uploaded_at = models.DateTimeField('Дата загрузки', auto_now_add=True)

    class Meta:
        verbose_name = 'Документ кандидата'
        verbose_name_plural = 'Документы кандидатов'
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.title


class CandidateSourceRecord(models.Model):
    source_row = models.PositiveIntegerField(
        'Строка Excel',
        null=True,
        blank=True,
        db_index=True,
    )
    source_number = models.PositiveIntegerField(
        '№ п/п из Excel',
        null=True,
        blank=True,
    )
    source_date = models.DateField(
        'Дата из Excel',
        null=True,
        blank=True,
        db_index=True,
    )
    full_name = models.CharField(
        'ФИО',
        max_length=255,
        db_index=True,
    )
    full_name_normalized = models.CharField(
        'ФИО для поиска',
        max_length=255,
        db_index=True,
        blank=True,
    )
    birth_date = models.DateField(
        'Дата рождения',
        null=True,
        blank=True,
    )
    birth_year = models.PositiveIntegerField(
        'Год рождения',
        null=True,
        blank=True,
    )
    vacancy = models.CharField(
        'Вакансия',
        max_length=255,
        blank=True,
    )
    phone = models.CharField(
        'Телефон',
        max_length=255,
        blank=True,
    )
    qualification = models.TextField(
        'Квалификация, наличие удостоверения на сайте',
        blank=True,
    )
    note = models.TextField(
        'Примечание',
        blank=True,
    )
    med_result = models.CharField(
        'Направление на МО',
        max_length=20,
        choices=ResumeCandidate.MEDICAL_CHOICES,
        default='pending',
        blank=True,
    )

    # medical_direction = models.TextField(
    #     'Направление на МО',
    #     blank=True,
    # )
    refusal_reason = models.TextField(
        'Примечание или причина отказа',
        blank=True,
    )
    accepted_date = models.DateField(
        'Принят дата',
        null=True,
        blank=True,
    )
    import_file_name = models.CharField(
        'Имя файла импорта',
        max_length=255,
        blank=True,
    )
    imported_at = models.DateTimeField(
        'Дата импорта',
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        'Обновлено',
        auto_now=True,
    )

    class Meta:
        verbose_name = 'Запись из файла кандидатов'
        verbose_name_plural = 'Записи из файла кандидатов'
        ordering = ['-source_date', '-id']
        indexes = [
            models.Index(fields=['full_name_normalized', '-source_date']),
        ]

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        self.full_name_normalized = normalize_full_name(self.full_name)
        super().save(*args, **kwargs)

    @classmethod
    def get_latest_by_full_name(cls, full_name):
        full_name_normalized = normalize_full_name(full_name)
        if not full_name_normalized:
            return None

        return (
            cls.objects
            .filter(full_name_normalized=full_name_normalized)
            .order_by('-source_date', '-accepted_date', '-id')
            .first()
        )

    def get_medical_commission_value(self):
        value = (self.med_result or '').strip()

        allowed_values = {
            code for code, label in ResumeCandidate.MEDICAL_CHOICES
        }

        if value in allowed_values:
            return value

        return 'pending'

    @classmethod
    def get_stage_sort_order(cls, stage_code):
        """
        Возвращает порядок этапа по его коду.
        Сначала смотрим пользовательские этапы из базы ResumeStage.
        Если этапа там нет, берём порядок из DEFAULT_STAGE_DEFINITIONS.
        """
        if not stage_code:
            return None

        stage = ResumeStage.objects.filter(code=stage_code).first()
        if stage:
            return stage.sort_order

        for item in DEFAULT_STAGE_DEFINITIONS:
            if item.get('code') == stage_code:
                return item.get('sort_order', 100)

        return None

    @classmethod
    def is_otipb_stage_passed(cls, stage_code):
        """
        ОТИПБ считается пройденным, когда текущий этап кандидата находится
        после этапа 'otipb'.
        """
        current_stage_order = cls.get_stage_sort_order(stage_code)
        otipb_stage_order = cls.get_stage_sort_order('otipb')

        if current_stage_order is None or otipb_stage_order is None:
            return False

        return current_stage_order > otipb_stage_order

    @classmethod
    def create_or_update_from_candidate_if_otipb_stage_passed(cls, candidate):
        """
        Актуализирует справочную базу кандидатов из карточки.
        Правило: запись создаётся или обновляется только тогда, когда кандидат
        уже прошёл этап ОТИПБ, то есть переведён на следующий этап после 'otipb'.
        """
        if not cls.is_otipb_stage_passed(candidate.stage):
            return None

        full_name = (getattr(candidate, 'full_name', '') or '').strip()
        if not full_name:
            return None

        source_record = cls.get_latest_by_full_name(full_name)

        data = {
            'source_date': candidate.date or timezone.localdate(),
            'full_name': full_name,
            'birth_year': candidate.birth_year,
            'vacancy': candidate.hh_vacancy or candidate.position or '',
            'phone': candidate.contacts or '',
            'qualification': candidate.qualification or '',
            'note': candidate.note or '',
            'med_result': candidate.medical_commission or 'pending',
            'refusal_reason': candidate.refusal_reason or '',
            'import_file_name': 'Карточка кандидата',
        }

        if source_record:
            for field_name, field_value in data.items():
                setattr(source_record, field_name, field_value)
            source_record.save()
            return source_record

        return cls.objects.create(**data)

    @classmethod
    def create_or_update_from_candidate_if_otipb_filled(cls, candidate):
        """
        Обратная совместимость со старым названием метода.
        Раньше база обновлялась по заполненному полю ОТИПБ.
        Теперь правильное условие — прохождение этапа ОТИПБ.
        """
        return cls.create_or_update_from_candidate_if_otipb_stage_passed(candidate)

    def as_autofill_data(self):
        comment = ''
        medical_text = (self.med_result or '').strip()

        if medical_text and medical_text.lower() != 'направлено':
            comment = medical_text

        return {
            'date': self.source_date.isoformat() if self.source_date else '',
            'full_name': self.full_name or '',
            'hh_vacancy': self.vacancy or '',
            'position': self.vacancy or '',
            'contacts': self.phone or '',
            'medical_commission': self.get_medical_commission_value(),
            'comment': comment,
            'birth_year': self.birth_year or '',
            'qualification': self.qualification or '',
            'work_experience': '',
            'note': self.note or '',
            'approval_department': '',
            'med_result': self.med_result or 'pending',
            'security_approval': 'pending',
            'security_comment': '',
            'security_refusal_reason': '',
            'department_call_approval': 'pending',
            'department_call_comment': '',
            'refusal_reason': self.refusal_reason or '',
            'ticket': '',
            'stage': '',
            'source_date': self.source_date.strftime('%d.%m.%Y') if self.source_date else '',
            'accepted_date': self.accepted_date.strftime('%d.%m.%Y') if self.accepted_date else '',
            'medical_direction': self.medical_direction or '',
        }
