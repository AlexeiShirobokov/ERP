from django.db import models
from django.db.models import Max
from django.utils import timezone


class ResumeCandidate(models.Model):
    MEDICAL_CHOICES = [
        ('pending', 'Ожидает'),
        ('passed', 'Пройдена'),
        ('failed', 'Не пройдена'),
    ]

    STAGE_CHOICES = [
        ('cold_search', 'Холодный поиск'),
        ('response', 'Отклик'),
        ('phone_interview', 'Тел. интервью'),
        ('interview', 'Собеседование'),
        ('medical', 'Медкомиссия'),
        ('ticket', 'Билет'),
        ('hired', 'Трудоустроен'),
        ('rejected', 'Отказ'),
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
        blank=True
    )
    comment = models.TextField('Комментарий', blank=True)
    birth_year = models.PositiveIntegerField('Год рождения', null=True, blank=True)
    qualification = models.TextField('Квалификация, наличие удостоверения на сайте', blank=True)
    note = models.TextField('Примечание', blank=True)
    medical_referral = models.CharField('Направление на МО', max_length=255, blank=True)
    refusal_reason = models.TextField('Примечание или причина отказа', blank=True)
    ticket = models.CharField('Билет', max_length=255, blank=True)

    stage = models.CharField(
        'Этап',
        max_length=30,
        choices=STAGE_CHOICES,
        default='cold_search'
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