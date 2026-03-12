1. Данный проект будет открывать
 - титульная страница содержит:
    - ссылку на дебиторскую задолженность
    - горные работы
    - динамику золото подтягиваем с мфд
    - остатки важных позиций на складе
    - таск менеджер
    - аналитику


2. При нажатии должна открываться отдельная страница по тематике

    Дебиторская задолженность

Сервер

    cd /home/django/ERP
    source /home/django/django_venv/bin/activate
    python3 manage.py shell

Перезапустить сервер
    под root
    systemctl restart erp
    systemctl restart nginx
Проверка:
    systemctl status erp
    systemctl status nginx

conda deactivate
venv\Scripts\activate

внести пользователей:
from django.contrib.auth.models import User, Group

user = User.objects.create_user(
    username="afanasiev",
    email="afanasiev@pskgold.ru",
    password="YnMRTe3j",
)

user.is_staff = True
user.save()

groups = Group.objects.filter(name__in=["Геологи", "Снабжение", "Прочие"])
user.groups.add(*groups)

from django.contrib.auth.models import User, Group

group = Group.objects.get(name="Геологи")

user = User.objects.create_user(
    username="afanasiev",
    email="afanasiev@pskgold.ru",
    password="YnMRTe3j",
)

user.is_staff = True
user.first_name = "Алексей"
user.last_name = "Афанасьев"
user.save()

user.groups.add(group)





что еще сделать:


2. внести пользователей
3. разграничить права
4. внести энергетика (его данные)
5. убрать кнопку обновить из excel
6. сделать более юзабильный интерфейс, вывести онлайн расчеты, добавить строки к примеру журнал ТО, для суперпользователя и директора вывести все задачи

