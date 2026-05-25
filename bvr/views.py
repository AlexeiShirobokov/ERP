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
from .bvr_document import build_excel, build_pdf, build_html_context
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
    "shema", "avtoVM", "voditel", "injot", "dispet", "participants",
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


def _to_float(value):
    """Безопасно приводит строку формы к float (поддержка запятой). None при пустом/мусоре."""
    if value is None:
        return None
    raw = str(value).strip().replace(",", ".")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _collect_declared(post):
    """Паспортные (декларированные) значения из скрытых полей формы.

    Заполняются JS после распознавания паспорта из техпоказателей:
    количество скважин, объём буровых работ (п.м), средняя глубина (м).
    Это «авторитетные» цифры — грид используется для рисунка/поскважинного расчёта.
    """
    wells = _to_float(post.get("decl_wells"))
    meters = _to_float(post.get("decl_meters"))
    avg = _to_float(post.get("decl_avg"))
    return {
        "wells": int(round(wells)) if wells and wells > 0 else None,
        "meters": meters if meters and meters > 0 else None,
        "avg": avg if avg and avg > 0 else None,
    }


def resolve_summary(calc, declared):
    """Сводные цифры проекта: при наличии паспортных значений берём их,
    иначе — посчитанные по зарядной карте (гриду)."""
    declared = declared or {}
    w = declared.get("wells")
    m = declared.get("meters")
    a = declared.get("avg")
    wells_v = int(w) if w else calc["n"]
    meters_v = float(m) if m else float(calc["sumD"])
    if a:
        avg_v = float(a)
    elif (w or m):
        avg_v = (meters_v / wells_v) if wells_v else 0.0
    else:
        avg_v = float(calc["sr_glub"])
    return {
        "wells": wells_v,
        "meters": meters_v,
        "avg": avg_v,
        "from_passport": bool(w or m or a),
        # «сеточные» значения для подсветки расхождения
        "grid_wells": calc["n"],
        "grid_meters": float(calc["sumD"]),
        "grid_avg": float(calc["sr_glub"]),
    }


def _project_dir(project_id):
    return Path(settings.MEDIA_ROOT) / "bvr_projects" / project_id


def _save_inputs(out_dir, params, card_text, declared):
    """Сохраняет входные данные проекта для последующего HTML-рендера."""
    data = dict(params)
    if isinstance(data.get("data"), datetime.date):
        data["data"] = data["data"].isoformat()
    payload = {"params": data, "charge_card": card_text, "declared": declared}
    try:
        (out_dir / "inputs.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    except OSError:
        logger.warning("Не удалось сохранить inputs.json")


def _load_inputs(project_id):
    """Восстанавливает params/wells/declared из inputs.json для HTML-проекта."""
    path = _project_dir(project_id) / "inputs.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text("utf-8"))
    params = make_params(data.get("params") or {})
    raw_date = params.get("data")
    if isinstance(raw_date, str):
        try:
            params["data"] = datetime.date.fromisoformat(raw_date)
        except ValueError:
            params["data"] = datetime.date.today()
    wells = parse_charge_card(data.get("charge_card") or "")
    declared = data.get("declared") or {}
    return params, wells, declared


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
            declared = _collect_declared(request.POST)
            summary = resolve_summary(calc, declared)
            _save_inputs(out_dir, params, card_text, declared)

            xlsx_path = out_dir / "project.xlsx"
            pdf_path = out_dir / "project.pdf"
            build_excel(calc, str(xlsx_path), summary=summary)
            build_pdf(calc, str(pdf_path), summary=summary,
                      passport_path=str(passport_path) if passport_path else None)
            _remember_project(request, project_id)

            result = {
                "project_id": project_id,
                "wells_count": summary["wells"],
                "drilling": round(summary["meters"], 2),
                "avg_depth": round(summary["avg"], 2),
                "from_passport": summary["from_passport"],
                "grid_wells": summary["grid_wells"],
                "grid_drilling": round(summary["grid_meters"], 2),
                "mismatch": summary["from_passport"] and (
                    summary["wells"] != summary["grid_wells"]
                    or abs(summary["meters"] - summary["grid_meters"]) > 0.5),
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


@login_required
def project_html(request, project_id):
    """Печатная HTML-версия проекта массового взрыва.

    Восстанавливает входные данные из inputs.json, пересчитывает проект и
    рендерит полную веб-страницу (акт, распорядок, таблицы, расчёты, зоны,
    зарядная карта с нумерацией). Удобно для просмотра и печати в браузере.
    """
    if not _can_download(request, project_id):
        raise Http404("Проект не найден")

    loaded = _load_inputs(project_id)
    if not loaded:
        raise Http404("Проект не найден")

    params, wells, declared = loaded
    if not wells:
        raise Http404("В проекте нет скважин")

    calc = calculate(params, wells)
    summary = resolve_summary(calc, declared)
    context = build_html_context(calc, summary=summary)
    context["project_id"] = project_id
    context["has_passport"] = (_project_dir(project_id) / "passport.pdf").exists()
    return render(request, "bvr/project.html", context)


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
