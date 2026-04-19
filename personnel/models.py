from django.conf import settings
from django.db import models
from django.db.models import Max
from django.utils import timezone


DEFAULT_STAGE_DEFINITIONS = [
    {'code': 'response', 'label': 'Отклик', 'emails': [], 'sort_order': 10},
    {'code': 'phone_interview', 'label': 'Тел. интервью', 'emails': [], 'sort_order': 20},
    {'code': 'otipb', 'label': 'ОТИПБ', 'emails': ['shirobokov@pskgold.ru'], 'sort_order': 30},
    {'code': 'hr_department', 'label': 'Отдел кадров', 'emails': ['alexeimvc@gmail.com'], 'sort_order': 40},
    {'code': 'ticket', 'label': 'Требуется покупка билетов', 'emails': [], 'sort_order': 50},
    {'code': 'hired', 'label': 'Трудоустроен', 'emails': [], 'sort_order': 60},
]


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
    notify_email = models.EmailField('Дополнительный email для уведомлений', blank=True)

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

    hh_resume_id = models.CharField('HH resume id', max_length=100, blank=True, db_index=True)
    hh_resume_link = models.URLField('Ссылка на резюме HH', blank=True)
    hh_vacancy_id = models.CharField('HH vacancy id', max_length=100, blank=True, db_index=True)
    hh_source = models.CharField('Источник HH', max_length=100, blank=True)
    hh_last_sync_at = models.DateTimeField('Последняя синхронизация HH', null=True, blank=True)

    number = models.PositiveIntegerField('№', unique=True, blank=True, null=True)
    date = models.DateField('Дата', default=timezone.localdate)
    full_name = models.CharField('ФИО', max_length=255)
    hh_vacancy = models.CharField('Соискатель по вакансии на hh.ru', max_length=255, blank=True)
    position = models.CharField('Должность', max_length=255, blank=True)
    contacts = models.CharField('Контакты', max_length=255, blank=True)

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
    note = models.TextField('Примечание', blank=True)
    otipb = models.CharField('ОТИПБ', max_length=255, blank=True)
    refusal_reason = models.TextField('Примечание или причина отказа', blank=True)
    ticket = models.CharField('Билет', max_length=255, blank=True)

    stage = models.CharField(
        'Этап',
        max_length=100,
        default=DEFAULT_STAGE_DEFINITIONS[0]['code'],
        db_index=True,
    )
    sort_order = models.PositiveIntegerField('Порядок', default=0)

    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

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
        return ResumeStage.objects.select_related('responsible_user').filter(code=stage_code).first()

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
            max_number = ResumeCandidate.objects.aggregate(max_num=Max('number'))['max_num'] or 0
            self.number = max_number + 1

        if not self.sort_order:
            max_sort = ResumeCandidate.objects.filter(stage=self.stage).aggregate(
                max_sort=models.Max('sort_order')
            )['max_sort'] or 0
            self.sort_order = max_sort + 1

        super().save(*args, **kwargs)


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