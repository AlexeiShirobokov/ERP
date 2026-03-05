from django.db import models

# Create your models here.

class DebitorUpload(models.Model): # создадим модель в базе данных, добавляет id, save, objects

    file=models.FileField(upload_to='uploads/debitorka/')
    uploaded_at=models.DateTimeField(auto_now_add=True) #upload_to=... задаёт папку внутри MEDIA_ROOT.

    def __str__(self):
        return self.file.name

