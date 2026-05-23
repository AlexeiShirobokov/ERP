import datetime
import json
import logging
import os
import tempfile
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .bvr_calc import DEFAULTS, calculate, make_params, parse_charge_card
from .bvr_document import build_excel, build_pdf
from . import passport_ocr

logger = logging.getLogger("bvr.views")


NUMERIC_FIELDS = {
    "plotvv", "diam", "kis", "krab", "plotpor", "ktresh", "prev", "a",
    "zaboi", "ryad", "ploshad", "boevik", "doldt", "iskra42", "iskraV",
    "zoob", "zoso",
}
INT_FIELDS = {"ryad", "iskra42", "iskraV", "zoob", "zoso"}

TEXT_FIELDS = [
    "pred", "mest", "blok", "prisk", "np", "zar1", "zar2", "vz1", "vz2",
    "prikaz", "raspol", "viddt", "obj", "meri", "gendir", "gling",
    "nachbvr", "glgeo", "glmark", "nachuch", "vzryvnik",
]

DEFAULT_CARD = "\n".join([" ".join(["8"] * 14) for _ in range(14)])


def _defaults_for_form():
    values = dict(DEFAULTS)
    values["data"] = datetime.date.today().isoformat()
    return values


def _parse_date(value):
    if not value:
        return datetime.date.today()
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Дата взрыва должна быть в формате ГГГГ-ММ-ДД") from exc


def _parse_number(key, value):
    try:
        number = float(str(value).replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"Поле «{key}» должно быть числом") from exc
    return int(number) if key in INT_FIELDS else number


def _collect_params(post):
    overrides = {}
    for key in TEXT_FIELDS:
        value = post.get(key, "").strip()
        if value:
            overrides[key] = value

    overrides["data"] = _parse_date(post.get("data", "").strip())

    for key in NUMERIC_FIELDS:
        raw = post.get(key, "").strip()
        if raw:
            overrides[key] = _parse_number(key, raw)

    return make_params(overrides)


def _project_dir(project_id):
    return Path(settings.MEDIA_ROOT) / "bvr_projects" / project_id


def _remember_project(request, project_id):
    projects = request.session.get("bvr_project_ids", [])
    if project_id not in projects:
        projects.append(project_id)
        request.session["bvr_project_ids"] = projects[-20:]


def _can_download(request, project_id):
    return project_id in request.session.get("bvr_project_ids", [])


@login_required
def index(request):
    values = _defaults_for_form()
    card_text = DEFAULT_CARD
    result = None

    if request.method == "POST":
        values.update({key: request.POST.get(key, values.get(key, "")) for key in values})
        card_text = request.POST.get("charge_card", "").strip()

        try:
            params = _collect_params(request.POST)
            wells = parse_charge_card(card_text)
            if not wells:
                raise ValueError("Зарядная карта не содержит скважин")

            project_id = uuid.uuid4().hex
            out_dir = _project_dir(project_id)
            out_dir.mkdir(parents=True, exist_ok=True)

            # JSON распознавания паспорта (если форма уже его получила) —
            # сохраняем рядом с проектом для аудита, без повторного вызова API.
            ocr_json = request.POST.get("ocr_json", "").strip()
            if ocr_json:
                try:
                    (out_dir / "recognition.json").write_text(ocr_json, "utf-8")
                except OSError:
                    logger.warning("Не удалось сохранить recognition.json")

            passport_file = request.FILES.get("passport")
            passport_path = None
            if passport_file:
                if not passport_file.name.lower().endswith(".pdf"):
                    raise ValueError("Паспорт БВР нужно загрузить в формате PDF")
                passport_path = out_dir / "passport.pdf"
                with passport_path.open("wb") as fh:
                    for chunk in passport_file.chunks():
                        fh.write(chunk)

            calc = calculate(params, wells)
            xlsx_path = out_dir / "project.xlsx"
            pdf_path = out_dir / "project.pdf"
            build_excel(calc, str(xlsx_path))
            build_pdf(calc, str(pdf_path), passport_path=str(passport_path) if passport_path else None)
            _remember_project(request, project_id)

            result = {
                "project_id": project_id,
                "wells_count": calc["n"],
                "drilling": round(calc["sumD"], 2),
                "volume": round(calc["objem_massiva"], 2),
                "explosive_mass": round(calc["obsh_massa"], 2),
                "people_zone": calc["zona_ludi"],
                "equipment_zone": calc["zona_obor"],
            }
            messages.success(request, "Проект БВР сформирован. Файлы готовы к скачиванию.")
        except Exception as exc:
            messages.error(request, f"Не удалось сформировать проект: {exc}")

    return render(request, "bvr/index.html", {
        "values": values,
        "charge_card": card_text,
        "result": result,
    })


@login_required
def download_project_file(request, project_id, file_kind):
    if not _can_download(request, project_id):
        raise Http404("Проект не найден")

    files = {
        "xlsx": ("project.xlsx", "Проект_БВР.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        "pdf": ("project.pdf", "Проект_БВР.pdf", "application/pdf"),
        "passport": ("passport.pdf", "Паспорт_БВР.pdf", "application/pdf"),
    }
    if file_kind not in files:
        raise Http404("Файл не найден")

    stored_name, download_name, content_type = files[file_kind]
    path = _project_dir(project_id) / stored_name
    if not path.exists():
        raise Http404("Файл не найден")
    return FileResponse(path.open("rb"), as_attachment=True, filename=download_name, content_type=content_type)


def _ocr_cache_dir():
    return Path(settings.MEDIA_ROOT) / "bvr_ocr_cache"


@login_required
@require_POST
def recognize_passport(request):
    """Серверное распознавание паспорта БВР.

    Принимает multipart-поле ``passport`` (PDF), возвращает JSON со структурой
    result (см. ``passport_ocr.recognize_passport``): зарядную карту,
    техпоказатели, штамп и предупреждения. Ошибки распознавания не «роняют»
    форму — возвращается ``ok: false`` с понятным текстом.
    """
    upload = request.FILES.get("passport")
    if not upload:
        return JsonResponse({"ok": False, "error": "Файл паспорта не передан"},
                            status=400)
    if not upload.name.lower().endswith(".pdf"):
        return JsonResponse({"ok": False, "error": "Нужен файл PDF"}, status=400)

    cfg = passport_ocr.load_config(cache_dir=_ocr_cache_dir())

    max_bytes = cfg.max_pdf_mb * 1024 * 1024
    if upload.size and upload.size > max_bytes:
        return JsonResponse(
            {"ok": False,
             "error": f"PDF больше лимита {cfg.max_pdf_mb:.0f} МБ"}, status=400)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            for chunk in upload.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        result = passport_ocr.recognize_passport(tmp_path, cfg=cfg)
    except Exception as exc:  # защита: эндпоинт не должен падать 500
        logger.exception("Сбой распознавания паспорта.")
        result = {"ok": False, "source": "error", "warnings": [],
                  "error": f"Внутренняя ошибка распознавания: {exc}"}
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # Аудит в БД (best-effort, не мешает ответу).
    if result.get("source") not in (None, "disabled"):
        try:
            from .models import PassportRecognition
            card = result.get("charge_card") or {}
            PassportRecognition.objects.create(
                user=(getattr(request.user, "username", "") or "")[:150],
                file_hash=result.get("file_hash", "") or "",
                file_name=(upload.name or "")[:255],
                ok=bool(result.get("ok")),
                source=(result.get("source") or "")[:32],
                model_used=cfg.model_read[:64],
                wells_count=card.get("wells_count"),
                avg_depth=card.get("avg_depth"),
                warnings=result.get("warnings", []) or [],
                payload=result,
                error=(result.get("error") or "")[:500],
            )
        except Exception:
            logger.exception("Не удалось записать аудит распознавания.")

    return JsonResponse(result)
