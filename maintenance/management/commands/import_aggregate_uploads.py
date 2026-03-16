from django.core.management.base import BaseCommand

from maintenance.aggregate_import import import_aggregate_upload
from maintenance.models import AggregateJournalUpload


class Command(BaseCommand):
    help = "Импортирует в БД все неимпортированные или ошибочные файлы агрегатного журнала"

    def handle(self, *args, **options):
        queryset = AggregateJournalUpload.objects.filter(
            status__in=[
                AggregateJournalUpload.STATUS_NEW,
                AggregateJournalUpload.STATUS_ERROR,
            ]
        ).order_by("uploaded_at")

        total = queryset.count()
        self.stdout.write(f"Найдено файлов для импорта: {total}")

        success = 0
        for upload in queryset:
            try:
                rows = import_aggregate_upload(upload, replace_existing_rows=True)
                success += 1
                self.stdout.write(
                    self.style.SUCCESS(f"[OK] {upload} -> импортировано строк: {rows}")
                )
            except Exception as exc:
                self.stdout.write(
                    self.style.ERROR(f"[ERROR] {upload} -> {exc}")
                )

        self.stdout.write(self.style.SUCCESS(f"Готово. Успешно: {success}"))