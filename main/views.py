import re
import requests
from django.http import JsonResponse
from django.core.cache import cache
from datetime import datetime

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from Services.debitor import Upload # берем из класса в дебиторе
from .models import DebitorUpload

def upload(request, pk:int):
    obj=get_object_or_404(DebitorUpload, pk=pk)
    df=Upload().open(obj.file.path).transform() ## путь берём из загруженного файла

    df_view=df

    table_html=df.to_html(index=False, escape=True)

    return render(request, "main/upload_view.html", {
            "obj": obj,
            "rows_total": len(df),
            "rows_shown": len(df_view),
            "table_html": table_html,
        })
