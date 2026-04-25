from django.conf import settings
from django.db import models
from django.db.models import Max
from django.utils import timezone


DEFAULT_STAGE_DEFINITIONS = [
    {
        'code': 'response',
        'label': 'Отклик',
        'emails': [],
        'sort_order': 10,
    },
    {
        'code': 'phone_interview',
        'label': 'Тел. интервью',
        'emails': [],
        'sort_order': 20,
    },
    {
        'code': 'otipb',
        'label': 'ОТИПБ',
        'emails': ['shirobokov@pskgold.ru'],
        'sort_order': 30,
    },
    {
        'code': 'hr_department',
        'label': 'Отдел кадров',
        'emails': ['shirobokov@pskgold.ru'],
        'sort_order': 40,
    },
    {
        'code': 'ticket',
        'label': 'Требуется покупка билетов',
        'emails': [],
        'sort_order': 50,
    },
    {
        'code': 'hired',
        'label': 'Трудоустроен',
        'emails': [],
        'sort_order': 60,
    },
]


def normalize_fio(value):
    """
    Нормализация ФИО для поиска:
    - убираем лишние пробелы;
    - приводим к нижнему регистру.
    """
    if not value:
        return ''

    return ' '.join(str(value).strip().lower().split())


class ResumeStage(models.Model):
    name = models.CharField('Название этапа', max_length=255)

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
        verbose_name = 'Этап подбора'
        verbose_name_plural = 'Этапы подбора'
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
    MEDICAL_CHOICES = [
        ('pending', 'Ожидает'),
        ('passed', 'Пройдена'),
        ('failed', 'Не пройдена'),
    ]

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

    comment = models.TextField(
        'Комментарий',
        blank=True,
    )

    birth_year = models.PositiveIntegerField(
        'Год рождения',
        null=True,
        blank=True,
    )

    qualification = models.TextField(
        'Квалификация, наличие удостоверения на сайте',
        blank=True,
    )

    work_experience = models.TextField(
        'Опыт работы',
        blank=True,
    )

    note = models.TextField(
        'Примечание',
        blank=True,
    )

    otipb = models.CharField(
        'ОТИПБ',
        max_length=255,
        blank=True,
    )

    refusal_reason = models.TextField(
        'Примечание или причина отказа',
        blank=True,
    )

    ticket = models.CharField(
        'Билет',
        max_length=255,
        blank=True,
    )

    stage = models.CharField(
        'Этап',
        max_length=100,
        default=DEFAULT_STAGE_DEFINITIONS[0]['code'],
        db_index=True,
    )

    sort_order = models.PositiveIntegerField(
        'Порядок',
        default=0,
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

    def get_stage_display(self):
        return self.stage_name

    def save(self, *args, **kwargs):
        if not self.number:
            max_number = (
                ResumeCandidate.objects.aggregate(max_num=Max('number'))['max_num']
                or 0
            )
            self.number = max_number + 1

        if not self.sort_order:
            max_sort = (
                ResumeCandidate.objects
                .filter(stage=self.stage)
                .aggregate(max_sort=models.Max('sort_order'))['max_sort']
                or 0
            )
            self.sort_order = max_sort + 1

        super().save(*args, **kwargs)

        OtipbHistory.create_from_candidate(self)

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse('personnel:resume_candidate_edit', kwargs={'pk': self.pk})


class ResumeCandidateDocument(models.Model):
    record = models.ForeignKey(
        'ResumeCandidate',
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name='Кандидат',
    )

    title = models.CharField(
        'Название',
        max_length=255,
    )

    file = models.FileField(
        'Файл',
        upload_to='personnel/candidate_documents/%Y/%m/',
    )

    comment = models.TextField(
        'Комментарий',
        blank=True,
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Загрузил',
    )

    uploaded_at = models.DateTimeField(
        'Дата загрузки',
        auto_now_add=True,
    )

    class Meta:
        verbose_name = 'Документ кандидата'
        verbose_name_plural = 'Документы кандидатов'
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.title


class OtipbHistory(models.Model):
    """
    История актуальных данных по кандидатам.

    Используется для проверки ФИО:
    - если кандидат найден, берём самую последнюю запись;
    - если не найден, очищаем поле ОТИПБ на форме.
    """

    source_candidate = models.ForeignKey(
        ResumeCandidate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='otipb_history_items',
        verbose_name='Карточка кандидата',
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
        blank=True,
    )

    comment = models.TextField(
        'Комментарий',
        blank=True,
    )

    birth_year = models.PositiveIntegerField(
        'Год рождения',
        null=True,
        blank=True,
    )

    qualification = models.TextField(
        'Квалификация, наличие удостоверения на сайте',
        blank=True,
    )

    work_experience = models.TextField(
        'Опыт работы',
        blank=True,
    )

    note = models.TextField(
        'Примечание',
        blank=True,
    )

    otipb = models.CharField(
        'ОТИПБ',
        max_length=255,
        blank=True,
    )

    refusal_reason = models.TextField(
        'Примечание или причина отказа',
        blank=True,
    )

    ticket = models.CharField(
        'Билет',
        max_length=255,
        blank=True,
    )

    stage = models.CharField(
        'Этап',
        max_length=100,
        blank=True,
    )

    source = models.CharField(
        'Источник',
        max_length=255,
        blank=True,
        default='Карточка кандидата',
    )

    source_date = models.DateTimeField(
        'Дата актуальности данных',
        default=timezone.now,
        db_index=True,
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
        verbose_name = 'История ОТИПБ'
        verbose_name_plural = 'История ОТИПБ'
        ordering = ['-source_date', '-id']

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        self.full_name_normalized = normalize_fio(self.full_name)
        super().save(*args, **kwargs)

    @classmethod
    def get_latest_by_full_name(cls, full_name):
        full_name_normalized = normalize_fio(full_name)

        if not full_name_normalized:
            return None

        return (
            cls.objects
            .filter(full_name_normalized=full_name_normalized)
            .order_by('-source_date', '-id')
            .first()
        )

    @classmethod
    def create_from_candidate(cls, candidate):
        if not candidate.full_name:
            return None

        latest = cls.get_latest_by_full_name(candidate.full_name)

        current_data = {
            'full_name': candidate.full_name,
            'hh_vacancy': candidate.hh_vacancy or '',
            'position': candidate.position or '',
            'contacts': candidate.contacts or '',
            'medical_commission': candidate.medical_commission or '',
            'comment': candidate.comment or '',
            'birth_year': candidate.birth_year,
            'qualification': candidate.qualification or '',
            'work_experience': candidate.work_experience or '',
            'note': candidate.note or '',
            'otipb': candidate.otipb or '',
            'refusal_reason': candidate.refusal_reason or '',
            'ticket': candidate.ticket or '',
            'stage': candidate.stage or '',
        }

        if latest:
            is_same = True

            for field_name, field_value in current_data.items():
                if getattr(latest, field_name) != field_value:
                    is_same = False
                    break

            if is_same:
                return latest

        return cls.objects.create(
            source_candidate=candidate,
            source='Карточка кандидата',
            source_date=timezone.now(),
            **current_data,
        )

    def as_form_data(self):
        return {
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
            'otipb': self.otipb or '',
            'refusal_reason': self.refusal_reason or '',
            'ticket': self.ticket or '',
            'stage': self.stage or '',
            'source': self.source or '',
            'source_date': (
                self.source_date.strftime('%d.%m.%Y %H:%M')
                if self.source_date
                else ''
            ),
        }