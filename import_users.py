import json
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ERP.settings")
os.environ["USE_POSTGRES"] = "True"
os.environ["DJANGO_DEBUG"] = "False"

django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

User = get_user_model()

with open("users_export.json", "r", encoding="utf-8") as f:
    data = json.load(f)

count_created = 0
count_updated = 0

for item in data:
    user, created = User.objects.update_or_create(
        username=item["username"],
        defaults={
            "email": item["email"],
            "first_name": item["first_name"],
            "last_name": item["last_name"],
            "is_active": item["is_active"],
            "is_staff": item["is_staff"],
            "is_superuser": item["is_superuser"],
            "password": item["password"],  # сохраняем готовый хеш
        }
    )

    groups = []
    for group_name in item.get("groups", []):
        group, _ = Group.objects.get_or_create(name=group_name)
        groups.append(group)

    user.groups.set(groups)

    if created:
        count_created += 1
    else:
        count_updated += 1

print(f"Created: {count_created}, Updated: {count_updated}")