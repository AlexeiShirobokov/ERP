from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from transfers.models import TransferDepartment, TransferImportBatch, TransferOrder


class Command(BaseCommand):
    help = 'Создает базовые подразделения и группу диспетчеров для приложения transfers.'

    def handle(self, *args, **options):
        departments = [
            ('ОГМ', 'ogm', 10),
            ('ОГЭ', 'oge', 20),
            ('Строительный отдел', 'construction', 30),
            ('Отдел главного диспетчера', 'dispatcher', 40),
            ('Склад', 'warehouse', 50),
        ]
        for name, code, sort_order in departments:
            TransferDepartment.objects.get_or_create(
                code=code,
                defaults={'name': name, 'sort_order': sort_order},
            )

        group, _ = Group.objects.get_or_create(name='transfers_dispatchers')
        order_ct = ContentType.objects.get_for_model(TransferOrder)
        batch_ct = ContentType.objects.get_for_model(TransferImportBatch)
        permission_codenames = [
            (order_ct, 'view_transferorder'),
            (order_ct, 'change_transferorder'),
            (order_ct, 'view_all_transferorder'),
            (order_ct, 'manage_transfer_delivery'),
            (batch_ct, 'add_transferimportbatch'),
            (batch_ct, 'view_transferimportbatch'),
        ]
        for content_type, codename in permission_codenames:
            permission = Permission.objects.filter(content_type=content_type, codename=codename).first()
            if permission:
                group.permissions.add(permission)

        self.stdout.write(self.style.SUCCESS('Приложение transfers подготовлено.'))
