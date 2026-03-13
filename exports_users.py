import json
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ERP.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

User = get_user_model()

data = []

for user in User.objects.all().prefetch_related("groups"):
    data.append({
        "username": user.username,
        "email": user.email or "",
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "password": user.password,   # хеш пароля
        "groups": [g.name for g in user.groups.all()],
    })

with open("users_export.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Exported {len(data)} users to users_export.json")