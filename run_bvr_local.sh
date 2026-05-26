#!/usr/bin/env bash
# Локальный запуск БВР для проверки в браузере.
#   bash run_bvr_local.sh
# Ключ OpenRouter возьмётся из .env.local (см. .env.local.example) или из
# уже экспортированной переменной BVR_VISION_API_KEY. Без ключа форма всё равно
# запустится — распознавание просто будет недоступно, карту вводят вручную.
set -e
cd "$(dirname "$0")"

PY=../.venv/bin/python
PIP=../.venv/bin/pip
if [ ! -x "$PY" ]; then
    echo "Не найден ../.venv/bin/python. Создайте venv: python3 -m venv ../.venv"
    exit 1
fi

# 1) Зависимости распознавания и генерации проекта (идемпотентно)
echo "→ Проверяю зависимости…"
$PIP install -q pymupdf pillow openai httpx lxml openpyxl reportlab

# 2) Переменные окружения (ключ OpenRouter и т.п.) из ERP/.env
#    Этот же .env автоматически читает settings.py — один файл и локально, и на сервере.
if [ -f .env ]; then
    echo "→ Загружаю .env"
    set -a; . ./.env; set +a
fi
export DJANGO_DEBUG=1

if [ -z "${BVR_VISION_API_KEY:-}" ]; then
    echo "⚠️  BVR_VISION_API_KEY не задан — распознавание паспорта будет отключено."
    echo "   Скопируйте .env.example в .env и впишите ключ OpenRouter."
fi

# 3) Миграции (создаст таблицу аудита PassportRecognition)
echo "→ Применяю миграции…"
$PY manage.py migrate --noinput

# 4) Тестовый пользователь для локального входа
$PY manage.py shell -c "from django.contrib.auth import get_user_model as g; U=g(); (U.objects.filter(username='codex').exists() or U.objects.create_superuser('codex','','codex12345')) and print('Пользователь codex готов (codex / codex12345)')"

# 5) Запуск сервера
echo ""
echo "==================================================================="
echo "  Откройте:  http://127.0.0.1:8001/bvr/"
echo "  Логин:     codex   Пароль: codex12345"
echo "  Остановить сервер: Ctrl+C"
echo "==================================================================="
exec $PY manage.py runserver 127.0.0.1:8001
