from django.core.management.base import BaseCommand

from Services.hh_import import import_hh_rows
from Services.parse_hh_candidates import collect_hh_rows


class Command(BaseCommand):
    help = 'Импорт откликов HH в ResumeCandidate'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Запуск импорта откликов HH...'))

        rows = collect_hh_rows()
        self.stdout.write(f'Получено строк из HH: {len(rows)}')

        created_count, updated_count = import_hh_rows(rows)

        self.stdout.write(
            self.style.SUCCESS(
                f'Готово. Создано: {created_count}, обновлено: {updated_count}'
            )
        )