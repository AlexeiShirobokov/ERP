# -*- coding: utf-8 -*-
"""
Серверное универсальное распознавание паспорта буровзрывных работ (БВР).

Читает PDF-паспорт любого макета и извлекает:
  * матрицу проектных глубин скважин (зарядную карту) — глубина каждой скважины;
  * 15 технологических показателей блока;
  * сведения штампа (месторождение, блок, горизонт и т.п.).

Движок — vision-модель Claude через OpenRouter (OpenAI-совместимый API).
Архитектура провайдеро-независима: используется SDK ``openai`` с ``base_url``,
поэтому позже можно переключиться на прямой Anthropic или иной шлюз без
переписывания логики.

Принципы (см. ``План_распознавания_паспорта.md`` и ``Анализ_паспортов_БВР.md``):
  1. Привязка к смысловым якорям (заголовкам таблиц), а не к координатам листа.
  2. Чтение настоящих цифр в каждой ячейке, без подстановки единой глубины.
  3. Двухпроходная схема: дешёвая модель ищет области таблиц → сильная модель
     точно читает цифры. Запасной режим — одностраничное чтение целиком.
  4. Кросс-проверки и обязательная ручная правка результата на стороне формы.
  5. Экономия: текстовый слой не вызывает API; кэш по хешу файла; кадрирование
     таблиц; невысокое разрешение; дешёвая модель для поиска областей.

Модуль не импортирует Django на верхнем уровне, поэтому пригоден и для
автономного использования в Telegram-боте.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("bvr.passport_ocr")

# Версия структуры результата — пишется в кэш, чтобы при изменении формата
# старые записи кэша игнорировались.
RESULT_VERSION = 2

# Фиксированный перечень 15 технологических показателей (ключ → описание).
# Используется и в промпте, и при валидации ответа модели.
TECH_KEYS = [
    "kategoriya_porod",            # 1. Категория пород (римская цифра / текст)
    "napravlenie_grad",            # 2. Направление скважины, градус
    "diametr_mm",                  # 3. Диаметр скважины, мм
    "ploshad_bloka_tm2",           # 4. Площадь блока, тыс. м²
    "srednyaya_glubina_m",         # 5. Средняя/средневзвешенная глубина, м
    "perebur_m",                   # 6. Перебур, м
    "rasst_mezhdu_ryadami_m",      # 7. Расстояние между рядами, м
    "rasst_mezhdu_skvazhinami_m",  # 8. Расстояние между скважинами, м
    "kis",                         # 9. КИС
    "vyhod_gornoy_massy_tm3",      # 10. Выход горной массы, тыс. м³
    "smennaya_proizvoditelnost_pm",# 11. Сменная производительность, п.м
    "obyom_burovyh_rabot_pm",      # 12. Объём буровых работ, п.м
    "kolichestvo_skvazhin_sht",    # 13. Количество скважин, шт
    "raspredelenie_po_blokam",     # 14. Распределение по геол. блокам (строка)
    "vremya_bureniya_bloka_sut",   # 15. Время бурения блока, сутки
    "stanok",                      # доп.: марка станка
    "setka_bureniya",              # доп.: сетка бурения (например, "5,5x5,0")
]

STAMP_KEYS = [
    "mestorozhdenie", "burovoy_blok", "geol_blok", "gorizont", "masshtab",
]

# Числовые показатели (для приведения "9,5" → 9.5). Остальные — строки.
_TECH_NUMERIC = {
    "napravlenie_grad", "diametr_mm", "ploshad_bloka_tm2", "srednyaya_glubina_m",
    "perebur_m", "rasst_mezhdu_ryadami_m", "rasst_mezhdu_skvazhinami_m", "kis",
    "vyhod_gornoy_massy_tm3", "smennaya_proizvoditelnost_pm",
    "obyom_burovyh_rabot_pm", "kolichestvo_skvazhin_sht",
    "vremya_bureniya_bloka_sut",
}


# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------
@dataclass
class VisionConfig:
    """Настройки распознавания. Значения читаются из переменных окружения."""

    enabled: bool = True
    api_key: str = ""
    base_url: str = "https://openrouter.ai/api/v1"
    # Основная модель точного чтения цифр.
    model_read: str = "anthropic/claude-sonnet-4.6"
    # Дешёвая модель для поиска областей таблиц (проход 1).
    model_locate: str = "anthropic/claude-haiku-4.5"
    # Модель авто-эскалации при несошедшихся кросс-проверках.
    model_escalate: str = "anthropic/claude-opus-4.7"
    two_pass: bool = True
    escalate: bool = True
    proxy: str = ""
    provider: str = "Anthropic"        # пин провайдера в OpenRouter (приватность)
    max_pdf_mb: float = 20.0
    dpi: int = 220                      # DPI рендера всей страницы
    max_image_side: int = 2000         # макс. сторона изображения, отправляемого в модель
    cache_dir: Optional[Path] = None
    referer: str = "https://github.com/AlexeiShirobokov/ERP"
    title: str = "BVR passport OCR"
    request_timeout: float = 120.0

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.api_key)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "да")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip())
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, "").strip()))
    except (TypeError, ValueError):
        return default


def load_config(cache_dir: Optional[str | Path] = None) -> VisionConfig:
    """Собирает конфигурацию из переменных окружения ``BVR_VISION_*``."""
    cfg = VisionConfig()
    cfg.enabled = _env_bool("BVR_VISION_ENABLED", True)
    cfg.api_key = os.environ.get("BVR_VISION_API_KEY", "").strip()
    cfg.base_url = os.environ.get(
        "BVR_VISION_BASE_URL", cfg.base_url).strip() or cfg.base_url
    cfg.model_read = os.environ.get(
        "BVR_VISION_MODEL", cfg.model_read).strip() or cfg.model_read
    cfg.model_locate = os.environ.get(
        "BVR_VISION_MODEL_LOCATE", cfg.model_locate).strip() or cfg.model_locate
    cfg.model_escalate = os.environ.get(
        "BVR_VISION_MODEL_ESCALATE", cfg.model_escalate).strip() or cfg.model_escalate
    cfg.two_pass = _env_bool("BVR_VISION_TWO_PASS", True)
    cfg.escalate = _env_bool("BVR_VISION_ESCALATE", True)
    cfg.proxy = os.environ.get("BVR_VISION_PROXY", "").strip()
    cfg.provider = os.environ.get("BVR_VISION_PROVIDER", cfg.provider).strip()
    cfg.max_pdf_mb = _env_float("BVR_VISION_MAX_PDF_MB", cfg.max_pdf_mb)
    cfg.dpi = _env_int("BVR_VISION_DPI", cfg.dpi)
    cfg.max_image_side = _env_int("BVR_VISION_MAX_IMAGE_SIDE", cfg.max_image_side)

    cache = cache_dir or os.environ.get("BVR_VISION_CACHE_DIR", "").strip()
    if cache:
        cfg.cache_dir = Path(cache)
    else:
        cfg.cache_dir = Path(tempfile.gettempdir()) / "bvr_ocr_cache"
    return cfg


# ---------------------------------------------------------------------------
# Рендер PDF в изображение
# ---------------------------------------------------------------------------
def render_pdf_page(pdf_path: str | Path, dpi: int = 220, page_index: int = 0):
    """Рендерит страницу PDF в ``PIL.Image``.

    Сначала пытается PyMuPDF (чистый wheel, без системных зависимостей),
    при его отсутствии — poppler (``pdftoppm``). Бросает RuntimeError, если
    недоступны оба движка.
    """
    from PIL import Image  # Pillow обязателен в любом случае

    pdf_path = str(pdf_path)

    # 1) PyMuPDF
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        try:
            page = doc[page_index]
            zoom = dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            mode = "RGB" if pix.n < 4 else "RGBA"
            img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
            return img.convert("RGB")
        finally:
            doc.close()
    except ImportError:
        logger.info("PyMuPDF недоступен, пробую poppler (pdftoppm).")
    except Exception:
        logger.exception("PyMuPDF не смог отрендерить PDF, пробую poppler.")

    # 2) poppler / pdftoppm
    with tempfile.TemporaryDirectory() as tmp:
        prefix = os.path.join(tmp, "page")
        page_no = page_index + 1
        try:
            subprocess.run(
                ["pdftoppm", "-png", "-r", str(dpi),
                 "-f", str(page_no), "-l", str(page_no),
                 "-singlefile", pdf_path, prefix],
                check=True, capture_output=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Не найден движок рендера PDF. Установите PyMuPDF "
                "(pip install pymupdf) или poppler-utils (pdftoppm)."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"pdftoppm не смог отрендерить PDF: {exc.stderr.decode(errors='ignore')}"
            ) from exc
        out = prefix + ".png"
        return Image.open(out).convert("RGB")


# ---------------------------------------------------------------------------
# Работа с изображениями
# ---------------------------------------------------------------------------
def _fit_to_side(img, max_side: int):
    """Масштабирует изображение так, чтобы длинная сторона ≤ max_side."""
    w, h = img.size
    longest = max(w, h)
    if longest <= max_side:
        return img
    scale = max_side / float(longest)
    from PIL import Image
    return img.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                      Image.LANCZOS)


def _crop_fraction(img, box: dict, pad: float = 0.03):
    """Вырезает область по относительным координатам {x0,y0,x1,y1} в долях 0..1.

    Добавляет поле ``pad`` (доля размера) со всех сторон — на случай неточного
    определения границ моделью.
    """
    w, h = img.size
    x0 = max(0.0, float(box.get("x0", 0)) - pad)
    y0 = max(0.0, float(box.get("y0", 0)) - pad)
    x1 = min(1.0, float(box.get("x1", 1)) + pad)
    y1 = min(1.0, float(box.get("y1", 1)) + pad)
    if x1 <= x0 or y1 <= y0:
        return None
    return img.crop((int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h)))


def _valid_box(box: Any) -> bool:
    if not isinstance(box, dict):
        return False
    try:
        x0, y0, x1, y1 = (float(box["x0"]), float(box["y0"]),
                          float(box["x1"]), float(box["y1"]))
    except (KeyError, TypeError, ValueError):
        return False
    if not (0 <= x0 < x1 <= 1.0 and 0 <= y0 < y1 <= 1.0):
        return False
    # слишком крошечная область — скорее всего ошибка распознавания
    return (x1 - x0) > 0.02 and (y1 - y0) > 0.02


def _data_url(img) -> str:
    """PIL.Image → data-URL (PNG, base64) для image_url в OpenAI-формате."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ---------------------------------------------------------------------------
# Разбор чисел и матрицы
# ---------------------------------------------------------------------------
def _num(value: Any) -> Optional[float]:
    """'9,5'/'9.5'/9.5 → 9.5; пусто/мусор → None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(" ", " ")
    if not s or s in ("-", "—", "–"):
        return None
    s = s.replace(",", ".")
    s = re.sub(r"[^\d.\-]", "", s)
    if not s or s in (".", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fmt_depth(value: Optional[float]) -> str:
    """Глубина → строка для зарядной карты. None/0 → '0'."""
    if value is None:
        return "0"
    if abs(value) < 1e-9:
        return "0"
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return ("%.2f" % value).rstrip("0").rstrip(".").replace(".", ",")


def matrix_to_card_text(matrix: list[list[Any]]) -> str:
    """Матрица глубин → текст зарядной карты (совместим с parse_charge_card).

    Пустая ячейка → '0'. Каждая строка матрицы — ряд скважин.
    """
    lines = []
    for row in matrix or []:
        if not isinstance(row, list):
            continue
        cells = [_fmt_depth(_num(c)) for c in row]
        # отбросить полностью пустые хвостовые '0', чтобы карта была компактнее
        while cells and cells[-1] == "0":
            cells.pop()
        if cells:
            lines.append(" ".join(cells))
    return "\n".join(lines)


def _count_wells(matrix: list[list[Any]]) -> int:
    n = 0
    for row in matrix or []:
        if not isinstance(row, list):
            continue
        for c in row:
            v = _num(c)
            if v is not None and v > 0:
                n += 1
    return n


def _depth_stats(matrix: list[list[Any]]):
    vals = []
    for row in matrix or []:
        if not isinstance(row, list):
            continue
        for c in row:
            v = _num(c)
            if v is not None and v > 0:
                vals.append(v)
    if not vals:
        return 0, None, None, None
    return len(vals), sum(vals) / len(vals), min(vals), max(vals)


# ---------------------------------------------------------------------------
# Промпты
# ---------------------------------------------------------------------------
_LOCATE_PROMPT = """Ты анализируешь инженерный чертёж — паспорт буровых работ.
На листе есть две таблицы:
1) "Проектная глубина скважин" — матрица проектных глубин (строки = ряды,
   столбцы = номера скважин, в ячейках — числа глубин в метрах);
2) "Технологические показатели" — список из ~15 параметров блока
   (категория пород, диаметр, КИС, площадь блока, количество скважин и т.д.).

Найди обе таблицы по их заголовкам и верни ТОЛЬКО JSON без пояснений:
{
  "depth_table": {"x0":0.0,"y0":0.0,"x1":0.0,"y1":0.0} | null,
  "tech_table":  {"x0":0.0,"y0":0.0,"x1":0.0,"y1":0.0} | null
}
Координаты — доли от ширины/высоты листа (0..1), прямоугольник, охватывающий
ВСЮ таблицу вместе с заголовком и подписями строк/столбцов. Если таблицы нет —
верни null для неё."""

_DEPTH_PROMPT = """На изображении — таблица "Проектная глубина скважин" из паспорта
буровых работ. Строки таблицы = ряды скважин (левый столбец — номер ряда),
столбцы = номера скважин в ряду. В ячейках — проектная глубина скважины в метрах
(например 5; 9,5; 7,3). Пустая ячейка означает, что скважины нет.

Прочитай таблицу и верни ТОЛЬКО JSON без пояснений и без markdown:
{
  "matrix": [[<глубина|null>, ...], ...],
  "rows": <число рядов>,
  "max_cols": <макс. число столбцов>
}
Правила:
- одна строка массива = один ряд таблицы слева направо;
- число — глубина в метрах, десятичный разделитель приведи к точке (9,5 → 9.5);
- пустая ячейка → null (НЕ 0, не пропускай позицию — сохраняй выравнивание столбцов);
- НЕ включай в matrix столбец/строку с номерами рядов и скважин — только глубины;
- не придумывай значения, читай ровно то, что видно."""

_TECH_PROMPT = """На изображении — таблица технологических показателей из паспорта
буровых работ (и, возможно, штамп с месторождением/блоком/горизонтом).
Верни ТОЛЬКО JSON без пояснений и без markdown, с такими ключами (значение
null, если показатель не читается):
{
  "kategoriya_porod": <строка, напр. "V">,
  "napravlenie_grad": <число>,
  "diametr_mm": <число, мм>,
  "ploshad_bloka_tm2": <число, тыс. м²>,
  "srednyaya_glubina_m": <число, м>,
  "perebur_m": <число, м>,
  "rasst_mezhdu_ryadami_m": <число, м>,
  "rasst_mezhdu_skvazhinami_m": <число, м>,
  "kis": <число>,
  "vyhod_gornoy_massy_tm3": <число, тыс. м³>,
  "smennaya_proizvoditelnost_pm": <число, п.м>,
  "obyom_burovyh_rabot_pm": <число, п.м>,
  "kolichestvo_skvazhin_sht": <число, шт>,
  "raspredelenie_po_blokam": <строка или null>,
  "vremya_bureniya_bloka_sut": <число, сутки>,
  "stanok": <строка, напр. "DM-45">,
  "setka_bureniya": <строка, напр. "5,5x5,0">,
  "mestorozhdenie": <строка или null>,
  "burovoy_blok": <строка, напр. "П-15">,
  "geol_blok": <строка или null>,
  "gorizont": <строка, напр. "+525.0">,
  "masshtab": <строка, напр. "1:1000">
}
Десятичный разделитель приведи к точке. Не придумывай значения."""

_FULL_PROMPT = """На изображении — паспорт буровых работ (инженерный чертёж).
Извлеки две таблицы и сведения штампа. Верни ТОЛЬКО JSON без пояснений и markdown:
{
  "matrix": [[<глубина|null>, ...], ...],   // таблица "Проектная глубина скважин":
                                            // строки = ряды, ячейки = глубина в метрах,
                                            // пустая ячейка = null, без столбца номеров
  "rows": <число рядов>,
  "max_cols": <макс. столбцов>,
  "tech": {
     "kategoriya_porod": <строка>, "napravlenie_grad": <число>,
     "diametr_mm": <число>, "ploshad_bloka_tm2": <число>,
     "srednyaya_glubina_m": <число>, "perebur_m": <число>,
     "rasst_mezhdu_ryadami_m": <число>, "rasst_mezhdu_skvazhinami_m": <число>,
     "kis": <число>, "vyhod_gornoy_massy_tm3": <число>,
     "smennaya_proizvoditelnost_pm": <число>, "obyom_burovyh_rabot_pm": <число>,
     "kolichestvo_skvazhin_sht": <число>, "raspredelenie_po_blokam": <строка|null>,
     "vremya_bureniya_bloka_sut": <число>, "stanok": <строка>,
     "setka_bureniya": <строка>, "mestorozhdenie": <строка|null>,
     "burovoy_blok": <строка>, "geol_blok": <строка|null>,
     "gorizont": <строка>, "masshtab": <строка>
  }
}
Десятичный разделитель приведи к точке. Не придумывай значения, читай как есть."""


# ---------------------------------------------------------------------------
# Вызов vision-модели
# ---------------------------------------------------------------------------
def build_client(cfg: VisionConfig):
    """Создаёт OpenAI-совместимый клиент (OpenRouter). Ленивая зависимость."""
    from openai import OpenAI

    kwargs = dict(base_url=cfg.base_url, api_key=cfg.api_key,
                  timeout=cfg.request_timeout)
    if cfg.proxy:
        import httpx
        kwargs["http_client"] = httpx.Client(proxy=cfg.proxy,
                                              timeout=cfg.request_timeout)
    return OpenAI(**kwargs)


def _extract_json(text: str) -> Any:
    """Достаёт JSON из ответа модели (снимает markdown-ограждение и мусор)."""
    if not text:
        raise ValueError("пустой ответ модели")
    s = text.strip()
    # снять ```json ... ``` / ``` ... ```
    fence = re.match(r"^```(?:json)?\s*(.+?)\s*```$", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # вытащить первый сбалансированный объект { ... }
    start = s.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(s[start:i + 1])
    raise ValueError("в ответе модели не найден JSON")


def _vision_json(client, cfg: VisionConfig, model: str, prompt: str,
                 images: list, max_tokens: int = 6000) -> Any:
    """Один vision-вызов: текст + изображения → распарсенный JSON."""
    content: list[dict] = [{"type": "text", "text": prompt}]
    for img in images:
        content.append({"type": "image_url",
                        "image_url": {"url": _data_url(img)}})

    extra_headers = {"HTTP-Referer": cfg.referer, "X-Title": cfg.title}
    extra_body: dict = {}
    if cfg.provider:
        # Пин провайдера (приватность/стабильность). На не-OpenRouter шлюзах
        # поле просто игнорируется.
        extra_body["provider"] = {"order": [cfg.provider],
                                  "allow_fallbacks": False}

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        max_tokens=max_tokens,
        temperature=0,
        extra_headers=extra_headers,
        extra_body=extra_body or None,
    )
    text = resp.choices[0].message.content or ""
    return _extract_json(text)


# ---------------------------------------------------------------------------
# Нормализация ответов модели
# ---------------------------------------------------------------------------
def _normalize_tech(raw: dict) -> dict:
    out: dict[str, Any] = {}
    raw = raw or {}
    for key in TECH_KEYS + STAMP_KEYS:
        val = raw.get(key)
        if key in _TECH_NUMERIC:
            out[key] = _num(val)
        else:
            out[key] = (str(val).strip() if val not in (None, "") else None)
    return out


def _normalize_matrix(raw: Any) -> list[list[Any]]:
    matrix = []
    if not isinstance(raw, list):
        return matrix
    for row in raw:
        if isinstance(row, list):
            matrix.append([_num(c) for c in row])
    return matrix


# ---------------------------------------------------------------------------
# Кросс-проверки
# ---------------------------------------------------------------------------
def cross_checks(matrix: list[list[Any]], tech: dict) -> list[str]:
    warnings: list[str] = []
    count, avg, dmin, dmax = _depth_stats(matrix)

    declared = tech.get("kolichestvo_skvazhin_sht") if tech else None
    if declared and count:
        if abs(declared - count) > max(2, 0.03 * declared):
            warnings.append(
                f"Количество скважин в матрице ({count}) расходится с "
                f"показателем «Количество скважин» ({int(declared)}). "
                f"Проверьте карту вручную.")

    declared_avg = tech.get("srednyaya_glubina_m") if tech else None
    if declared_avg and avg:
        if abs(declared_avg - avg) > max(0.5, 0.1 * declared_avg):
            warnings.append(
                f"Средняя глубина по матрице ({avg:.2f} м) расходится со "
                f"средней глубиной из таблицы ({declared_avg} м).")

    if dmin is not None and dmin < 2:
        warnings.append(f"Есть подозрительно малые глубины (минимум {dmin} м).")
    if dmax is not None and dmax > 30:
        warnings.append(f"Есть подозрительно большие глубины (максимум {dmax} м).")

    if not count:
        warnings.append("Зарядная карта пуста — глубины не распознаны.")
    return warnings


def _checks_passed(matrix, tech) -> bool:
    """True, если кросс-проверки сошлись (можно не эскалировать на Opus)."""
    count, avg, _, _ = _depth_stats(matrix)
    if not count:
        return False
    declared = (tech or {}).get("kolichestvo_skvazhin_sht")
    if declared and abs(declared - count) > max(2, 0.03 * declared):
        return False
    declared_avg = (tech or {}).get("srednyaya_glubina_m")
    if declared_avg and avg and abs(declared_avg - avg) > max(0.5, 0.1 * declared_avg):
        return False
    return True


# ---------------------------------------------------------------------------
# Кэш по хешу файла
# ---------------------------------------------------------------------------
def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_path(cfg: VisionConfig, digest: str) -> Optional[Path]:
    if not cfg.cache_dir:
        return None
    return Path(cfg.cache_dir) / f"{digest}.json"


def _load_cache(cfg: VisionConfig, digest: str) -> Optional[dict]:
    path = _cache_path(cfg, digest)
    if path and path.exists():
        try:
            data = json.loads(path.read_text("utf-8"))
            if data.get("_version") == RESULT_VERSION:
                data["cached"] = True
                return data
        except Exception:
            logger.warning("Повреждённый кэш распознавания: %s", path)
    return None


def _save_cache(cfg: VisionConfig, digest: str, result: dict) -> None:
    path = _cache_path(cfg, digest)
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    except Exception:
        logger.exception("Не удалось записать кэш распознавания.")


# ---------------------------------------------------------------------------
# Сборка результата
# ---------------------------------------------------------------------------
def _assemble(matrix: list[list[Any]], tech: dict, source: str) -> dict:
    count, avg, dmin, dmax = _depth_stats(matrix)
    card_text = matrix_to_card_text(matrix)
    tech = tech or {}
    stamp = {k: tech.get(k) for k in STAMP_KEYS}
    tech_only = {k: tech.get(k) for k in TECH_KEYS}
    return {
        "ok": bool(count) or any(v is not None for v in tech_only.values()),
        "_version": RESULT_VERSION,
        "source": source,
        "charge_card": {
            "rows": len(matrix),
            "max_cols": max((len(r) for r in matrix), default=0),
            "matrix": matrix,
            "wells_count": count,
            "avg_depth": round(avg, 2) if avg else None,
            "min_depth": dmin,
            "max_depth": dmax,
            "text": card_text,
        },
        "tech_params": tech_only,
        "stamp": stamp,
        "warnings": cross_checks(matrix, tech),
    }


# ---------------------------------------------------------------------------
# Главная функция
# ---------------------------------------------------------------------------
def recognize_passport(pdf_path: str | Path,
                       cfg: Optional[VisionConfig] = None,
                       client: Any = None,
                       use_cache: bool = True) -> dict:
    """Распознаёт паспорт БВР и возвращает структуру result.

    Параметры:
      pdf_path  — путь к PDF-паспорту;
      cfg       — VisionConfig (по умолчанию читается из окружения);
      client    — заранее созданный OpenAI-клиент (для тестов/мока);
      use_cache — использовать кэш по хешу файла.

    Возврат: dict со структурой result. При выключенном/ненастроенном
    распознавании или ошибке — {"ok": False, "error": ...}.
    """
    cfg = cfg or load_config()
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        return {"ok": False, "source": "none", "error": "Файл не найден",
                "warnings": []}

    size_mb = pdf_path.stat().st_size / (1024 * 1024)
    if size_mb > cfg.max_pdf_mb:
        return {"ok": False, "source": "none",
                "error": f"PDF больше лимита {cfg.max_pdf_mb:.0f} МБ "
                         f"({size_mb:.1f} МБ)", "warnings": []}

    digest = file_sha256(pdf_path)
    if use_cache:
        cached = _load_cache(cfg, digest)
        if cached:
            logger.info("Распознавание взято из кэша: %s", digest[:12])
            return cached

    if not cfg.configured:
        return {"ok": False, "source": "disabled", "file_hash": digest,
                "error": "Распознавание выключено или не задан BVR_VISION_API_KEY",
                "warnings": []}

    try:
        page = render_pdf_page(pdf_path, dpi=cfg.dpi)
    except Exception as exc:
        logger.exception("Ошибка рендера PDF.")
        return {"ok": False, "source": "render", "file_hash": digest,
                "error": f"Не удалось отрендерить PDF: {exc}", "warnings": []}

    if client is None:
        try:
            client = build_client(cfg)
        except Exception as exc:
            logger.exception("Не удалось создать клиент модели.")
            return {"ok": False, "source": "client", "file_hash": digest,
                    "error": f"Нет клиента модели: {exc}", "warnings": []}

    try:
        result = _run_pipeline(page, client, cfg)
    except Exception as exc:
        logger.exception("Ошибка распознавания.")
        return {"ok": False, "source": "vision", "file_hash": digest,
                "error": f"Сбой распознавания: {exc}", "warnings": []}

    result["file_hash"] = digest
    if use_cache and result.get("ok"):
        _save_cache(cfg, digest, result)
    return result


def _run_pipeline(page, client, cfg: VisionConfig) -> dict:
    """Конвейер распознавания: двухпроходный с запасным одностраничным режимом."""
    matrix: list[list[Any]] = []
    tech: dict = {}
    source = "vision"

    if cfg.two_pass:
        try:
            small = _fit_to_side(page, 1400)
            boxes = _vision_json(client, cfg, cfg.model_locate,
                                 _LOCATE_PROMPT, [small], max_tokens=400)
        except Exception:
            logger.exception("Проход 1 (поиск областей) не удался.")
            boxes = {}

        depth_box = boxes.get("depth_table") if isinstance(boxes, dict) else None
        tech_box = boxes.get("tech_table") if isinstance(boxes, dict) else None

        if _valid_box(depth_box):
            crop = _crop_fraction(page, depth_box)
            if crop is not None:
                crop = _fit_to_side(crop, cfg.max_image_side)
                try:
                    data = _vision_json(client, cfg, cfg.model_read,
                                        _DEPTH_PROMPT, [crop])
                    matrix = _normalize_matrix(data.get("matrix"))
                except Exception:
                    logger.exception("Чтение матрицы глубин не удалось.")

        if _valid_box(tech_box):
            crop = _crop_fraction(page, tech_box)
            if crop is not None:
                crop = _fit_to_side(crop, cfg.max_image_side)
                try:
                    data = _vision_json(client, cfg, cfg.model_read,
                                        _TECH_PROMPT, [crop])
                    tech = _normalize_tech(data)
                except Exception:
                    logger.exception("Чтение техпоказателей не удалось.")

    # Запасной одностраничный режим, если двухпроходный не дал карты.
    if not matrix:
        source = "vision_full"
        full = _fit_to_side(page, cfg.max_image_side)
        data = _vision_json(client, cfg, cfg.model_read, _FULL_PROMPT, [full])
        matrix = _normalize_matrix(data.get("matrix"))
        if not tech:
            tech = _normalize_tech(data.get("tech") or {})

    # Авто-эскалация на сильную модель, если кросс-проверки не сошлись.
    if (cfg.escalate and cfg.model_escalate
            and cfg.model_escalate != cfg.model_read
            and matrix and not _checks_passed(matrix, tech)):
        try:
            full = _fit_to_side(page, cfg.max_image_side)
            data = _vision_json(client, cfg, cfg.model_escalate,
                                _FULL_PROMPT, [full])
            esc_matrix = _normalize_matrix(data.get("matrix"))
            esc_tech = _normalize_tech(data.get("tech") or {})
            if esc_matrix and _checks_passed(esc_matrix, esc_tech or tech):
                matrix = esc_matrix
                tech = esc_tech or tech
                source = "vision_escalated"
        except Exception:
            logger.exception("Эскалация на сильную модель не удалась.")

    return _assemble(matrix, tech, source)
