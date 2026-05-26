# -*- coding: utf-8 -*-
"""
Формирование проекта массового взрыва 1:1 с Excel-эталоном.

Идея: берём заранее оформленный шаблон ``resources/project_template.xlsm``
(все листы, формулы, шапка приказа с логотипом, типографика формул сделаны
в Excel), вписываем в него данные формы (штамп, параметры, зарядную карту,
участников), помечаем книгу на полный пересчёт при открытии и экспортируем
печатные листы в PDF через LibreOffice headless.

Так оформление полностью совпадает с Excel. Если LibreOffice на сервере
недоступен, вызывающий код откатывается на генератор ``bvr_document.build_pdf``.

Правка делается на уровне XML внутри .xlsm (zip), чтобы НЕ потерять изображения
(логотип приказа), массивные формулы каталога и структурные таблицы —
openpyxl при пересохранении это портит.
"""
from __future__ import annotations

import datetime
import os
import shutil
import base64
import logging
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from lxml import etree

logger = logging.getLogger("bvr.excel_project")

RESOURCES = Path(__file__).resolve().parent / "resources"
TEMPLATE = RESOURCES / "project_template.xlsm"

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
M = "{%s}" % NS["m"]

# Листы-данные, которые НЕ печатаем (скрываем). Остальные — печатные.
HIDE_SHEETS = {"Зарядная карта", "Каталог скважин", "Параметры", "Справочник",
               "<", ">", "не печатать!!!"}

# Зарядная карта: сетка глубин. Ряд 1 -> строка 5, Скв 1 -> столбец C(3).
GRID_SHEET = "Зарядная карта"
GRID_ROW0 = 4      # строка = GRID_ROW0 + ряд
GRID_COL0 = 2      # столбец = GRID_COL0 + скважина
GRID_ROWS = 40     # ряды 1..40  -> строки 5..44
GRID_COLS = 60     # скв 1..60   -> столбцы C..BJ

# Лист ознакомления.
PARTIC_SHEET = "2"
PARTIC_ROW0 = 4    # первая строка ФИО
PARTIC_MAX = 19


# --------------------------------------------------------------------------
# Утилиты
# --------------------------------------------------------------------------
def libreoffice_bin() -> Optional[str]:
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    for cand in (
        # Linux (сервер)
        "/usr/bin/soffice", "/usr/bin/libreoffice",
        "/opt/libreoffice/program/soffice",
        # macOS (локально, VS Code)
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        # Windows
        r"C:\Program Files\LibreOffice\program\soffice.exe",
    ):
        if os.path.exists(cand):
            return cand
    return None


def available() -> bool:
    return TEMPLATE.exists() and libreoffice_bin() is not None


def col_letter(idx: int) -> str:
    s = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


def col_index(letter: str) -> int:
    n = 0
    for ch in letter:
        n = n * 26 + (ord(ch) - 64)
    return n


def excel_serial(d: datetime.date) -> int:
    """Дата -> серийный номер Excel (база 1899-12-30)."""
    if isinstance(d, datetime.datetime):
        d = d.date()
    return (d - datetime.date(1899, 12, 30)).days


# --------------------------------------------------------------------------
# Работа с XML листа
# --------------------------------------------------------------------------
class _Sheet:
    def __init__(self, xml_bytes: bytes):
        self.tree = etree.fromstring(xml_bytes)
        self.data = self.tree.find("m:sheetData", NS)

    def _row(self, r: int):
        for row in self.data.findall("m:row", NS):
            if int(row.get("r")) == r:
                return row
        # вставить строку в правильном порядке
        new = etree.Element(M + "row"); new.set("r", str(r))
        inserted = False
        for row in self.data.findall("m:row", NS):
            if int(row.get("r")) > r:
                row.addprevious(new); inserted = True; break
        if not inserted:
            self.data.append(new)
        return new

    def _cell(self, ref: str, create=True):
        letter = "".join(c for c in ref if c.isalpha())
        r = int("".join(c for c in ref if c.isdigit()))
        row = self._row(r)
        ci = col_index(letter)
        for c in row.findall("m:c", NS):
            if c.get("r") == ref:
                return c
        if not create:
            return None
        cell = etree.Element(M + "c"); cell.set("r", ref)
        inserted = False
        for c in row.findall("m:c", NS):
            cl = "".join(ch for ch in c.get("r") if ch.isalpha())
            if col_index(cl) > ci:
                c.addprevious(cell); inserted = True; break
        if not inserted:
            row.append(cell)
        return cell

    def set_value(self, ref, value, is_num):
        cell = self._cell(ref)
        style = cell.get("s")
        for ch in list(cell):
            cell.remove(ch)
        for a in list(cell.attrib):
            if a not in ("r", "s"):
                del cell.attrib[a]
        if style is not None:
            cell.set("s", style)
        if is_num:
            v = etree.SubElement(cell, M + "v"); v.text = repr(value) if isinstance(value, float) else str(value)
        else:
            text = "" if value is None else str(value)
            cell.set("t", "inlineStr")
            is_ = etree.SubElement(cell, M + "is")
            t = etree.SubElement(is_, M + "t")
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            t.text = text

    def clear_region(self, r0, r1, c0, c1):
        """Очистить значения (но не стиль) в прямоугольнике строк/столбцов."""
        for row in self.data.findall("m:row", NS):
            rr = int(row.get("r"))
            if rr < r0 or rr > r1:
                continue
            for c in row.findall("m:c", NS):
                letter = "".join(ch for ch in c.get("r") if ch.isalpha())
                ci = col_index(letter)
                if c0 <= ci <= c1:
                    for ch in list(c):
                        c.remove(ch)
                    if c.get("t"):
                        del c.attrib["t"]

    def bytes(self) -> bytes:
        return etree.tostring(self.tree, xml_declaration=True,
                              encoding="UTF-8", standalone=True)


# --------------------------------------------------------------------------
# Заполнение шаблона
# --------------------------------------------------------------------------
def _param_ops(p, n_wells):
    def f(v):
        return float(v)
    return [
        ("Параметры", "C3", p.get("pred", ""), False),
        ("Параметры", "C5", p.get("mest", ""), False),
        ("Параметры", "C7", p.get("blok", ""), False),
        ("Параметры", "C9", excel_serial(p.get("data") or datetime.date.today()), True),
        ("Параметры", "C11", p.get("zar1", ""), False),
        ("Параметры", "C13", p.get("zar2", ""), False),
        ("Параметры", "C15", p.get("vz1", ""), False),
        ("Параметры", "C17", p.get("vz2", ""), False),
        ("Параметры", "D20", p.get("raspol", "Шахматное"), False),
        ("Параметры", "D22", f(p["plotvv"]), True),
        ("Параметры", "D23", p.get("viddt", "Зимнее"), False),
        ("Параметры", "D26", f(p["diam"]), True),
        ("Параметры", "D27", f(p["kis"]), True),
        ("Параметры", "D28", f(p["krab"]), True),
        ("Параметры", "D29", f(p["plotpor"]), True),
        ("Параметры", "D30", f(p["ktresh"]), True),
        ("Параметры", "D31", f(p["prev"]), True),
        ("Параметры", "D33", f(p["a"]), True),
        ("Параметры", "D39", int(p["ryad"]), True),
        ("Параметры", "D40", int(n_wells), True),
        ("Параметры", "D41", f(p["ploshad"]), True),
        ("Параметры", "D61", f(p["boevik"]), True),
        ("Параметры", "D67", int(p["iskra42"]), True),
        ("Параметры", "D68", int(p["iskraV"]), True),
    ]


def _parse_participants(raw):
    out = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        sep = ";" if ";" in line else ("\t" if "\t" in line else ",")
        fio, _, prof = line.partition(sep)
        out.append((fio.strip(), prof.strip()))
    return out


def fill_template(params, wells, template: Path = TEMPLATE) -> bytes:
    """Возвращает байты .xlsm шаблона, заполненного данными формы."""
    zin = zipfile.ZipFile(template)
    parts = {n: zin.read(n) for n in zin.namelist()}
    zin.close()

    wb = etree.fromstring(parts["xl/workbook.xml"])
    rels = etree.fromstring(parts["xl/_rels/workbook.xml.rels"])
    rid2tgt = {r.get("Id"): r.get("Target") for r in rels}
    sheets_el = wb.find("m:sheets", NS)
    name2file = {}
    for sh in sheets_el.findall("m:sheet", NS):
        tgt = rid2tgt[sh.get("{%s}id" % NS["r"])]
        name2file[sh.get("name")] = tgt if tgt.startswith("xl/") else "xl/" + tgt

    # 1) скрыть данные-листы + полный пересчёт при открытии
    for sh in sheets_el.findall("m:sheet", NS):
        if sh.get("name") in HIDE_SHEETS:
            sh.set("state", "hidden")
    calc = wb.find("m:calcPr", NS)
    if calc is None:
        calc = etree.SubElement(wb, M + "calcPr")
    calc.set("fullCalcOnLoad", "1")

    # Поджать область печати «Зарядной карты» под фактический размер сетки,
    # чтобы не было пустых столбцов/разлёта на лишние страницы (localSheetId=0).
    if wells:
        maxskv = max(int(w["skv"]) for w in wells)
        maxryad = max(int(w["ryad"]) for w in wells)
        last_col = col_letter(GRID_COL0 + maxskv)
        last_row = GRID_ROW0 + maxryad + 1
        dn = wb.find("m:definedNames", NS)
        if dn is not None:
            for d in dn.findall("m:definedName", NS):
                if (d.get("name") == "_xlnm.Print_Area"
                        and d.get("localSheetId") == "0"):
                    d.text = "'%s'!$A$1:$%s$%d" % (GRID_SHEET, last_col, last_row)

    parts["xl/workbook.xml"] = etree.tostring(wb, xml_declaration=True,
                                              encoding="UTF-8", standalone=True)

    # загрузить нужные листы
    sheets = {}

    def sheet(name):
        if name not in sheets:
            sheets[name] = _Sheet(parts[name2file[name]])
        return sheets[name]

    n_wells = len(wells)

    # 2) параметры/штамп
    for sname, ref, val, is_num in _param_ops(params, n_wells):
        sheet(sname).set_value(ref, val, is_num)

    # 3) зарядная карта: очистить сетку и вписать глубины
    zk = sheet(GRID_SHEET)
    zk.clear_region(GRID_ROW0 + 1, GRID_ROW0 + GRID_ROWS,
                    GRID_COL0 + 1, GRID_COL0 + GRID_COLS)
    for w in wells:
        ryad = int(w["ryad"]); skv = int(w["skv"])
        if 1 <= ryad <= GRID_ROWS and 1 <= skv <= GRID_COLS:
            ref = "%s%d" % (col_letter(GRID_COL0 + skv), GRID_ROW0 + ryad)
            zk.set_value(ref, float(w["d"]), True)

    # 4) участники (лист ознакомления)
    parts_list = _parse_participants(params.get("participants"))
    sh2 = sheet(PARTIC_SHEET)
    for i in range(PARTIC_MAX):
        r = PARTIC_ROW0 + i
        fio, prof = parts_list[i] if i < len(parts_list) else ("", "")
        sh2.set_value("C%d" % r, fio, False)
        sh2.set_value("D%d" % r, prof, False)

    # собрать обратно
    for name, sh in sheets.items():
        parts[name2file[name]] = sh.bytes()

    buf = tempfile.SpooledTemporaryFile()
    zout = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)
    for n, data in parts.items():
        zout.writestr(n, data)
    zout.close()
    buf.seek(0)
    return buf.read()


# --------------------------------------------------------------------------
# Конвертация в PDF через LibreOffice
# --------------------------------------------------------------------------
_RECALC_XCU = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
 <item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item>
 <item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="ODFRecalcMode" oor:op="fuse"><value>0</value></prop></item>
 <item oor:path="/org.openoffice.Setup/L10N"><prop oor:name="ooLocale" oor:op="fuse"><value>ru-RU</value></prop></item>
 <item oor:path="/org.openoffice.Office.Calc/Content/Update/Link"><prop oor:name="Mode" oor:op="fuse"><value>0</value></prop></item>
</oor:items>
"""


def _page_texts(pdf_path):
    """Список текстов страниц PDF (через pdftotext, разделитель — form feed)."""
    try:
        out = subprocess.run(["pdftotext", "-layout", pdf_path, "-"],
                             capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return None
    return out.split("\f")


def _trim_pdf(pdf_path: str) -> None:
    """Оставляет в PDF только печатные листы проекта.

    LibreOffice при конвертации печатает ВСЕ листы (включая скрытые
    листы-данные) и добавляет пустые страницы/обрывки из-за широких областей
    печати. Печатные листы идут подряд: от «Обложки» (АКЦИОНЕРНОЕ ОБЩЕСТВО +
    ПРОЕКТ) до листа 17 («исключающего передачу детонации»). Берём этот
    диапазон и выкидываем пустые/обрывочные страницы (мало текста).
    """
    try:
        import pypdf
    except Exception:
        return
    pages = _page_texts(pdf_path)
    if not pages:
        return
    flats = [" ".join(p.split()) for p in pages]
    n = len(flats)

    def is_cover(t):
        return "АКЦИОНЕРНОЕ" in t and "ПРОЕКТ" in t

    def is_last(t):
        return "передачу детонации" in t or "хранится в делах взрывного" in t

    start = next((i for i, t in enumerate(flats) if is_cover(t)), 0)
    end = next((i for i in range(n - 1, -1, -1) if is_last(flats[i])), n - 1)
    if end < start:
        end = n - 1

    # «Зарядная карта» печатается до обложки (лист-данные) — её надо ВЕРНУТЬ
    # в проект и поставить после «Таблицы».
    zk = [i for i in range(0, start)
          if "Проектная глубина скважин" in flats[i] and len(flats[i].strip()) >= 30]
    # печатные листы (обложка..17), без пустых/обрывочных страниц
    main = [i for i in range(start, end + 1) if len(flats[i].strip()) >= 45]
    tabl = next((i for i in main if "ТАБЛИЦА" in flats[i]), None)
    keep = []
    for i in main:
        keep.append(i)
        if i == tabl:
            keep.extend(zk)
    if tabl is None and zk:
        keep = zk + keep
    if not keep or len(keep) >= n:
        return  # нечего обрезать / не распознали структуру — не трогаем
    try:
        reader = pypdf.PdfReader(pdf_path)
        writer = pypdf.PdfWriter()
        for i in keep:
            if i < len(reader.pages):
                writer.add_page(reader.pages[i])
        with open(pdf_path, "wb") as fh:
            writer.write(fh)
    except Exception:
        logger.exception("Не удалось обрезать служебные страницы PDF")


def convert_to_pdf(xlsm_bytes: bytes, out_pdf: str, timeout: float = 90.0) -> bool:
    soffice = libreoffice_bin()
    if not soffice:
        return False
    work = tempfile.mkdtemp(prefix="bvr_lo_")
    try:
        profile = os.path.join(work, "profile")
        os.makedirs(os.path.join(profile, "user"), exist_ok=True)
        with open(os.path.join(profile, "user", "registrymodifications.xcu"),
                  "w", encoding="utf-8") as fh:
            fh.write(_RECALC_XCU)
        src = os.path.join(work, "project.xlsm")
        with open(src, "wb") as fh:
            fh.write(xlsm_bytes)
        env = dict(os.environ)
        env["HOME"] = work
        env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:" + env.get("PATH", "")
        # Русская локаль: десятичная запятая и корректные форматы TEXT(...)
        # (если локаль ru_RU.UTF-8 установлена в системе — сервер/Mac).
        env["LANG"] = "ru_RU.UTF-8"
        env["LC_ALL"] = "ru_RU.UTF-8"
        cmd = [soffice, "--headless", "--norestore", "--convert-to", "pdf",
               "--outdir", work, src,
               "-env:UserInstallation=file://%s" % profile]
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout, env=env)
        produced = os.path.join(work, "project.pdf")
        if not os.path.exists(produced):
            return False
        shutil.move(produced, out_pdf)
        _trim_pdf(out_pdf)  # убрать листы-данные и пустые страницы
        return True
    finally:
        shutil.rmtree(work, ignore_errors=True)


def build_project_pdf(params, wells, out_pdf: str) -> bool:
    """Главная точка: заполнить шаблон и сконвертировать в PDF.

    Возвращает True при успехе, False — если LibreOffice/шаблон недоступны
    (тогда вызывающий код использует резервный генератор).
    """
    if not available():
        return False
    xlsm = fill_template(params, wells)
    return convert_to_pdf(xlsm, out_pdf)


# --------------------------------------------------------------------------
# Экспорт заполненного шаблона в HTML (точное оформление Excel, редактируемое)
# --------------------------------------------------------------------------
_EDITOR_HEAD = """
<style id="bvr-editor-style">
 #bvr-toolbar{position:sticky;top:0;z-index:99999;background:#fff;border-bottom:1px solid #d6deea;
   padding:8px 14px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-family:system-ui,Arial,sans-serif;}
 .bvr-btn{font-size:13px;padding:7px 14px;border-radius:7px;border:1px solid #b9c7da;background:#fff;color:#1d4e89;cursor:pointer;text-decoration:none;}
 .bvr-btn.primary{background:#1d4e89;color:#fff;border-color:#1d4e89;}
 .bvr-hint{color:#667085;font-size:12px;}
 [contenteditable="true"]:focus{outline:1px dashed #6aa3d8;}
 .bvr-sheet{ page-break-after:always; }
 .bvr-sheet:last-child{ page-break-after:auto; }
 #bvr-doc{ max-width:980px; margin:0 auto; }
 @media print{ #bvr-toolbar{display:none!important;} #bvr-doc{max-width:none;margin:0;} }
</style>
<script>
function bvrToggle(b){var d=document.getElementById('bvr-doc');var on=d.getAttribute('contenteditable')==='true';
 d.setAttribute('contenteditable',on?'false':'true');b.textContent=on?'Включить редактирование':'Выключить редактирование';}
</script>
"""


def _toolbar_html(excel_url):
    excel = ('<a class="bvr-btn" href="%s">Скачать Excel</a>' % excel_url) if excel_url else ""
    return (
        '<div id="bvr-toolbar" contenteditable="false">'
        '<button class="bvr-btn primary" type="button" onclick="window.print()">Печать / Сохранить в PDF</button>'
        + excel +
        '<button class="bvr-btn" type="button" onclick="bvrToggle(this)">Выключить редактирование</button>'
        '<span class="bvr-hint">Точное оформление из Excel. Правьте текст прямо здесь, затем «Печать / Сохранить в PDF».</span>'
        '</div>')


def convert_to_html(xlsm_bytes: bytes, excel_url: Optional[str] = None,
                    timeout: float = 90.0) -> Optional[str]:
    """Заполненный .xlsm -> самодостаточная редактируемая HTML-страница.

    LibreOffice экспортирует книгу в HTML (точное оформление, формулы и шапка —
    картинками). Картинки встраиваются как data-uri, добавляется панель печати,
    содержимое делается редактируемым (contenteditable). Возвращает HTML-строку
    или None, если LibreOffice недоступен.
    """
    soffice = libreoffice_bin()
    if not soffice:
        return None
    work = tempfile.mkdtemp(prefix="bvr_lohtml_")
    try:
        profile = os.path.join(work, "profile")
        os.makedirs(os.path.join(profile, "user"), exist_ok=True)
        with open(os.path.join(profile, "user", "registrymodifications.xcu"),
                  "w", encoding="utf-8") as fh:
            fh.write(_RECALC_XCU)
        src = os.path.join(work, "project.xlsm")
        with open(src, "wb") as fh:
            fh.write(xlsm_bytes)
        env = dict(os.environ)
        env["HOME"] = work
        env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:" + env.get("PATH", "")
        # Русская локаль: десятичная запятая и корректные форматы TEXT(...)
        # (если локаль ru_RU.UTF-8 установлена в системе — сервер/Mac).
        env["LANG"] = "ru_RU.UTF-8"
        env["LC_ALL"] = "ru_RU.UTF-8"
        cmd = [soffice, "--headless", "--norestore", "--convert-to", "html",
               "--outdir", work, src,
               "-env:UserInstallation=file://%s" % profile]
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout, env=env)
        produced = os.path.join(work, "project.html")
        if not os.path.exists(produced):
            return None
        with open(produced, encoding="utf-8", errors="replace") as fh:
            doc = fh.read()

        # встроить картинки (формулы, логотип) как data-uri -> самодостаточный файл
        def _inline(m):
            fn = os.path.basename(m.group(1))
            path = os.path.join(work, fn)
            if os.path.exists(path):
                ext = fn.rsplit(".", 1)[-1].lower()
                mime = {"png": "image/png", "gif": "image/gif",
                        "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "image/png")
                b64 = base64.b64encode(open(path, "rb").read()).decode("ascii")
                return 'src="data:%s;base64,%s"' % (mime, b64)
            return m.group(0)
        doc = re.sub(r'src="([^"]+\.(?:png|gif|jpe?g))"', _inline, doc, flags=re.I)

        # стили из <head> LibreOffice (шрифты/цвета) сохраняем для точности
        head_m = re.search(r"<head[^>]*>(.*?)</head>", doc, re.S | re.I)
        head_inner = head_m.group(1) if head_m else '<meta charset="utf-8">'
        head_inner = re.sub(r"<title>.*?</title>", "", head_inner, flags=re.S | re.I)
        body_m = re.search(r"<body[^>]*>(.*)</body>", doc, re.S | re.I)
        body_inner = body_m.group(1) if body_m else doc

        # LibreOffice экспортирует ВСЕ листы (включая скрытые данные-листы) +
        # оглавление и заголовки «Sheet N: Имя». Оставляем только печатные листы.
        section = re.compile(
            r'<a\s+name="table\d+">\s*<h1>\s*Sheet[^:]*:\s*<em>(.*?)</em>\s*</h1>\s*</a>'
            r'(.*?)(?=<a\s+name="table\d+">\s*<h1>\s*Sheet|\Z)', re.S | re.I)
        keep = {"Обложка", "АКТ", "2", "Распорядок", "Таблица",
                "5", "7", "8", "11", "12", "13", "14", "15", "16", "17"}
        sheets = []
        for m in section.finditer(body_inner):
            name = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            content = m.group(2)
            content = re.sub(r"<!--.*?-->", "", content, flags=re.S)
            content = re.sub(r"<hr\s*/?>", "", content, flags=re.I).strip()
            if name in keep:
                sheets.append('<div class="bvr-sheet">%s</div>' % content)
        body_doc = "".join(sheets) if sheets else body_inner

        return (
            '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            + head_inner + _EDITOR_HEAD + '</head><body>'
            + _toolbar_html(excel_url)
            + '<div id="bvr-doc" contenteditable="true">' + body_doc + '</div>'
            '</body></html>')
    finally:
        shutil.rmtree(work, ignore_errors=True)
