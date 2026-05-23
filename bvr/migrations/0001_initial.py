# -*- coding: utf-8 -*-
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PassportRecognition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True,
                                                    verbose_name="Создано")),
                ("user", models.CharField(blank=True, default="", max_length=150,
                                          verbose_name="Пользователь")),
                ("file_hash", models.CharField(blank=True, db_index=True, default="",
                                               max_length=64,
                                               verbose_name="SHA-256 файла")),
                ("file_name", models.CharField(blank=True, default="", max_length=255,
                                               verbose_name="Имя файла")),
                ("ok", models.BooleanField(default=False, verbose_name="Успех")),
                ("source", models.CharField(blank=True, default="", max_length=32,
                                            verbose_name="Источник")),
                ("model_used", models.CharField(blank=True, default="", max_length=64,
                                                verbose_name="Модель")),
                ("wells_count", models.IntegerField(blank=True, null=True,
                                                    verbose_name="Скважин распознано")),
                ("avg_depth", models.FloatField(blank=True, null=True,
                                                verbose_name="Средняя глубина, м")),
                ("warnings", models.JSONField(blank=True, default=list,
                                              verbose_name="Предупреждения")),
                ("payload", models.JSONField(blank=True, default=dict,
                                             verbose_name="Результат распознавания")),
                ("error", models.CharField(blank=True, default="", max_length=500,
                                           verbose_name="Ошибка")),
            ],
            options={
                "verbose_name": "Распознавание паспорта БВР",
                "verbose_name_plural": "Распознавания паспортов БВР",
                "ordering": ("-created_at",),
            },
        ),
    ]
