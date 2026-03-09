import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import F

User = get_user_model()


class TaskFile(models.Model):
    task = models.ForeignKey("Task", on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to="task_files/%Y/%m/%d/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.file.name

    @property
    def filename(self):
        return os.path.basename(self.file.name)


class Task(models.Model):
    title = models.CharField("Тема", max_length=255)
    description = models.TextField("Описание задачи")
    deadline = models.DateTimeField("Срок выполнения")
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    creator = models.ForeignKey(
        User,
        related_name="created_tasks",
        on_delete=models.CASCADE,
        verbose_name="Автор",
    )
    responsible = models.ForeignKey(
        User,
        related_name="responsible_tasks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Ответственный",
    )
    is_delegated = models.BooleanField("Делегировано", default=False)
    is_completed = models.BooleanField(default=False)
    delegated_from = models.ForeignKey(
        User,
        related_name="delegated_tasks",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Делегировано от",
    )
    delegated_at = models.DateTimeField("Дата делегирования", null=True, blank=True)

    def __str__(self):
        return f"{self.title} (до {self.deadline.strftime('%d.%m.%Y')})"


class TaskParticipant(models.Model):
    ROLE_CHOICES = [
        ("executor", "Исполнитель"),
        ("responsible", "Ответственный"),
        ("observer", "Наблюдатель"),
    ]

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="participants", verbose_name="Задача")
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Пользователь")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, verbose_name="Роль")

    class Meta:
        unique_together = ("task", "user")
        verbose_name = "Участник задачи"
        verbose_name_plural = "Участники задачи"

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} — {self.get_role_display()}"


class TaskMessage(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="messages", verbose_name="Задача")
    sender = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Отправитель")
    content = models.TextField("Сообщение")
    timestamp = models.DateTimeField("Дата и время", auto_now_add=True)

    def __str__(self):
        return f"Сообщение от {self.sender.get_full_name() or self.sender.username} — {self.timestamp.strftime('%d.%m.%Y %H:%M')}"


class Project(models.Model):
    title = models.CharField("Название проекта", max_length=255)
    description = models.TextField("Описание", blank=True)
    deadline = models.DateTimeField("Срок", null=True, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    creator = models.ForeignKey(User, related_name="created_projects", on_delete=models.CASCADE, verbose_name="Автор")
    manager = models.ForeignKey(
        User,
        related_name="managed_projects",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Руководитель проекта",
    )

    def __str__(self):
        return self.title


class ProjectMember(models.Model):
    ROLE_CHOICES = [
        ("manager", "Руководитель проекта"),
        ("member", "Участник"),
        ("observer", "Наблюдатель"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="member")

    class Meta:
        unique_together = ("project", "user")

    def __str__(self):
        return f"{self.user} — {self.get_role_display()}"


class ProjectItem(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="items")
    title = models.CharField("Пункт", max_length=255)
    deadline = models.DateTimeField("Срок", null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    assignees = models.ManyToManyField(
        User,
        through="ProjectItemAssignee",
        related_name="project_items",
        verbose_name="Исполнители",
    )

    class Meta:
        ordering = ("order", "id")

    def __str__(self):
        return self.title


class ProjectItemAssignee(models.Model):
    item = models.ForeignKey(ProjectItem, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("item", "user")


class ProjectMessage(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="messages", verbose_name="Проект")
    sender = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Отправитель")
    content = models.TextField("Сообщение")
    timestamp = models.DateTimeField("Дата и время", auto_now_add=True)

    class Meta:
        ordering = ("timestamp",)

    def __str__(self):
        return f"{self.project_id} / {self.sender} / {self.timestamp:%Y-%m-%d %H:%M}"


class ProjectFile(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to="project_files/%Y/%m/%d/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.file.name

    @property
    def filename(self):
        return os.path.basename(self.file.name)


BP_ROLES = (
    ("initiator", "Инициатор заявки"),
    ("procurement", "Снабжение"),
    ("finance", "Финансовый отдел"),
    ("treasury", "Казначейство"),
    ("warehouse", "Склад"),
)

BP_STAGES = (
    ("initiator", "Инициатор заявки"),
    ("procurement", "Снабжение"),
    ("finance", "Финансовый отдел"),
    ("treasury", "Казначейство"),
    ("warehouse", "Склад"),
    ("done", "Готово"),
)


class BusinessProcess(models.Model):
    title = models.CharField("Название", max_length=255)
    description = models.TextField("Описание", blank=True)
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bp_created", verbose_name="Автор")
    manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bp_managed",
        verbose_name="Руководитель процесса",
    )
    deadline = models.DateTimeField("Срок", null=True, blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "id")

    def __str__(self):
        return self.title


class BusinessProcessMember(models.Model):
    process = models.ForeignKey(BusinessProcess, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=32, choices=BP_ROLES)

    class Meta:
        unique_together = ("process", "user")
        indexes = [models.Index(fields=["process", "role"])]

    def __str__(self):
        return f"{self.process} — {self.user} ({self.get_role_display()})"


class PurchaseRequest(models.Model):
    process = models.ForeignKey(BusinessProcess, on_delete=models.CASCADE, related_name="purchases")
    title = models.CharField("Наименование/заказ", max_length=255)
    description = models.TextField("Комментарий", blank=True)
    amount = models.DecimalField("Сумма", max_digits=12, decimal_places=2, null=True, blank=True)
    supplier = models.CharField("Поставщик", max_length=255, blank=True)
    deadline = models.DateTimeField("Срок", null=True, blank=True)

    stage = models.CharField(max_length=32, choices=BP_STAGES, default="initiator")
    order = models.PositiveIntegerField(default=0)

    assignees = models.ManyToManyField(User, blank=True, related_name="purchase_assignees")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("stage", "order", "id")
        indexes = [
            models.Index(fields=["process", "stage", "order"]),
            models.Index(fields=["deadline"]),
        ]

    def __str__(self):
        return f"{self.title} • {self.get_stage_display()}"

    def resequence_stage(self):
        siblings = (
            PurchaseRequest.objects.filter(process=self.process, stage=self.stage)
            .order_by("order", "id")
            .values_list("id", flat=True)
        )
        for i, pk in enumerate(siblings):
            if pk == self.id and self.order == i:
                continue
            PurchaseRequest.objects.filter(pk=pk).update(order=i)

    def move_to(self, new_stage: str, new_order: int):
        if new_order < 0:
            new_order = 0

        with transaction.atomic():
            if self.stage != new_stage:
                PurchaseRequest.objects.filter(
                    process=self.process,
                    stage=self.stage,
                    order__gt=self.order,
                ).update(order=F("order") - 1)

                PurchaseRequest.objects.filter(
                    process=self.process,
                    stage=new_stage,
                    order__gte=new_order,
                ).update(order=F("order") + 1)

                self.stage = new_stage
                self.order = new_order
                self.save(update_fields=["stage", "order"])
            else:
                if new_order == self.order:
                    return

                if new_order > self.order:
                    PurchaseRequest.objects.filter(
                        process=self.process,
                        stage=self.stage,
                        order__gt=self.order,
                        order__lte=new_order,
                    ).update(order=F("order") - 1)
                else:
                    PurchaseRequest.objects.filter(
                        process=self.process,
                        stage=self.stage,
                        order__gte=new_order,
                        order__lt=self.order,
                    ).update(order=F("order") + 1)

                self.order = new_order
                self.save(update_fields=["order"])


class BPMessage(models.Model):
    process = models.ForeignKey(BusinessProcess, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField("Сообщение")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]


class BPFile(models.Model):
    process = models.ForeignKey(BusinessProcess, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to="bp_files/%Y/%m/%d/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    @property
    def filename(self):
        return os.path.basename(self.file.name)


class PRComment(models.Model):
    item = models.ForeignKey(PurchaseRequest, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField("Сообщение")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class PRFile(models.Model):
    item = models.ForeignKey(PurchaseRequest, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to="bp_item_files/%Y/%m/%d/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    @property
    def filename(self):
        return os.path.basename(self.file.name)