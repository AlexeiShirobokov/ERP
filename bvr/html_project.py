# -*- coding: utf-8 -*-
"""
Проект массового взрыва в виде печатной HTML-страницы.

Зачем: HTML/CSS даёт точную, не «съезжающую» вёрстку; страницу можно
редактировать прямо в браузере (contenteditable), печатать и сохранять в PDF
средствами браузера. Серверные PDF-библиотеки и LibreOffice не нужны.

Вёрстка повторяет Excel-эталон: A4, отдельная страница на каждый лист,
альбомная «Таблица параметров», шапка приказа (логотип + реквизиты —
встроенное изображение), типографские формулы (дроби/корни) средствами CSS.
"""
from __future__ import annotations

import base64
import datetime
import html
from pathlib import Path

from .bvr_calc import depth_groups
from .bvr_document import (fmt, fmt0, date_parts, date_str, _boevik_name,
                           _participants, _summary_values)

RESOURCES = Path(__file__).resolve().parent / "resources"


def _letterhead_data_uri() -> str:
    path = RESOURCES / "letterhead.png"
    if not path.exists():
        return ""
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return "data:image/png;base64," + b64


def e(x) -> str:
    return html.escape(str(x), quote=True)


# Типографика формул -------------------------------------------------------
def frac(num: str, den: str) -> str:
    return ('<span class="frac"><span class="fn">%s</span>'
            '<span class="fd">%s</span></span>' % (num, den))


def sqrt(inner: str) -> str:
    return '<span class="sqrt"><span class="sqrt-in">%s</span></span>' % inner


CSS = """
:root{ --ink:#000; --line:#000; --muted:#555; --soft:#eef3f9; }
*{ box-sizing:border-box; }
body{ margin:0; background:#e9edf3; color:var(--ink);
  font-family:"Times New Roman",Georgia,serif; font-size:12pt; }
.toolbar{ position:sticky; top:0; z-index:50; background:#fff; border-bottom:1px solid #d6deea;
  padding:10px 16px; display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
.toolbar .sp{ flex:1; }
.toolbar .hint{ color:#667085; font-family:system-ui,sans-serif; font-size:12px; }
.btn{ font-family:system-ui,sans-serif; font-size:13px; padding:7px 14px; border-radius:7px;
  border:1px solid #b9c7da; background:#fff; color:#1d4e89; cursor:pointer; text-decoration:none; }
.btn.primary{ background:#1d4e89; color:#fff; border-color:#1d4e89; }
.doc{ margin:16px auto; }
.sheet{ background:#fff; width:210mm; min-height:297mm; margin:0 auto 14px; padding:14mm 16mm;
  box-shadow:0 8px 24px rgba(20,32,50,.10); page-break-after:always; position:relative; }
.sheet.land{ width:297mm; min-height:210mm; }
.sheet:last-child{ page-break-after:auto; }
h1,h2,h3{ font-family:"Times New Roman",serif; }
.center{ text-align:center; } .right{ text-align:right; } .muted{ color:var(--muted); }
.title{ font-weight:bold; text-align:center; letter-spacing:3px; font-size:15pt; margin:4px 0; }
.sub{ text-align:center; margin:2px 0 10px; }
.cover-co{ text-align:center; font-weight:bold; }
.cover{ display:flex; flex-direction:column; justify-content:space-between; min-height:252mm; text-align:center; }
.cover-big{ text-align:center; font-weight:bold; font-size:34pt; letter-spacing:8px; margin:0 0 4mm; }
.cover-sub{ text-align:center; font-weight:bold; font-size:16pt; letter-spacing:4px; }
.cover-foot{ text-align:center; }
ol.items{ margin:6px 0; padding-left:0; list-style:none; counter-reset:it; }
ol.items>li{ counter-increment:it; margin:3px 0; text-align:justify; }
ol.items>li::before{ content:counter(it)". "; font-weight:bold; }
p{ margin:5px 0; text-align:justify; }
table{ border-collapse:collapse; width:100%; margin:8px 0; }
th,td{ border:1px solid var(--line); padding:3px 5px; vertical-align:middle; font-size:11pt; }
th{ background:var(--soft); font-family:"Times New Roman",serif; }
.num{ text-align:center; }
.nob td,.nob th{ border:0; }
.akt-val{ display:inline-block; min-width:150px; border-bottom:1px solid #000; text-align:center; font-weight:bold; }
.sig-box{ border:1px solid #2f7d4f; padding:10px 12px; margin-top:18px; }
.sigline{ display:inline-block; min-width:200px; border-bottom:1px solid #000; }
.lh{ width:100%; margin-bottom:6px; }
.lh img{ width:100%; height:auto; display:block; }
.formula{ text-align:center; margin:8px 0; font-size:12.5pt; }
.frac{ display:inline-block; vertical-align:middle; text-align:center; }
.frac .fn{ display:block; padding:0 4px; border-bottom:1px solid #000; }
.frac .fd{ display:block; padding:0 4px; }
.sqrt{ display:inline-block; }
.sqrt::before{ content:"\\221A"; }
.sqrt .sqrt-in{ display:inline-block; border-top:1px solid #000; padding:0 3px; }
.grid td,.grid th{ text-align:center; min-width:22px; font-family:ui-monospace,Consolas,monospace; font-size:9.5pt; padding:2px 3px; }
.grid td.rh,.grid th.rh{ background:var(--soft); font-family:system-ui,sans-serif; }
[contenteditable="true"]:focus{ outline:1px dashed #6aa3d8; }
@media print{
  @page{ size:A4 portrait; margin:12mm 14mm; }
  @page land{ size:A4 landscape; margin:10mm 12mm; }
  body{ background:#fff; }
  .toolbar{ display:none; }
  .doc{ margin:0; }
  .sheet{ box-shadow:none; margin:0; width:auto; min-height:auto; padding:0; }
  .sheet.land{ page:land; width:auto; }
  th{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }
}
"""

SCRIPT = """
function ccToggle(b){var d=document.getElementById('doc');var on=d.getAttribute('contenteditable')==='true';
 d.setAttribute('contenteditable', on?'false':'true'); b.textContent= on?'Включить редактирование':'Выключить редактирование';}
"""


def _akt_row(num, label, value, unit):
    return ('<tr class="nob"><td style="width:55%%">%d. %s</td>'
            '<td class="num" style="width:30%%"><span class="akt-val">%s</span></td>'
            '<td style="width:15%%">%s</td></tr>' % (num, e(label), e(value), e(unit)))


def build_html(calc, summary=None, project_id=None, excel_url=None) -> str:
    p = calc["params"]
    n_disp, drill_disp, avg_disp = _summary_values(calc, summary)
    dd, mon, yy = date_parts(p)
    D = "« %s » %s %s г." % (dd, mon, yy)
    bname = _boevik_name(p)
    mest, blok, prisk, pred = p["mest"], p["blok"], p["prisk"], p["pred"]
    nu = 'Начальник участка "%s" %s' % (mest, p["nachuch"])
    gling, vzr, injot, dispet = p["gling"], p["vzryvnik"], p["injot"], p["dispet"]
    asn = calc["mas_as"] / calc["n"] if calc["n"] else 0
    dtn = calc["mas_dt_kg"] / calc["n"] if calc["n"] else 0
    lh = _letterhead_data_uri()
    S = []  # листы

    # --- Обложка ---
    S.append(
        '<section class="sheet"><div class="cover">'
        '<div><div class="cover-co">АКЦИОНЕРНОЕ ОБЩЕСТВО</div>'
        '<div class="cover-co">"%s"</div></div>'
        '<div><div class="cover-big">ПРОЕКТ</div>'
        '<div class="cover-sub">МАССОВОГО ВЗРЫВА</div>'
        '<div class="center" style="margin-top:14mm">месторождение: <b>%s</b><br>Блок: <b>%s</b></div></div>'
        '<div class="cover-foot">%s<br>%s г.</div>'
        '</div></section>'
        % (e(pred.replace("АО", "").replace('"', "").strip().upper()), e(mest), e(blok), e(p["np"]), e(yy)))

    # --- Акт ---
    akt = ['<section class="sheet"><div class="cover-co">%s</div>' % e(pred)]
    akt.append('<div class="title">А К Т</div><div class="sub">о готовности блока к заряжанию</div>')
    akt.append('<table class="nob"><tr><td style="width:35%%">Россыпное месторождение:</td>'
               '<td style="width:30%%"><b>%s</b></td><td style="width:12%%">блок:</td>'
               '<td><b>%s</b></td></tr></table>' % (e(mest), e(blok)))
    akt.append('<table class="nob"><tr><td>"______"&nbsp;&nbsp;%s&nbsp;&nbsp;%s г.</td>'
               '<td class="right">%s</td></tr></table>' % (e(mon), e(yy), e(prisk)))
    akt.append('<p>Мы, нижеподписавшиеся, ответственный руководитель ВР %s, маркшейдер '
               '________________, составили настоящий акт о том, что блок <b>%s</b> полностью '
               'забурен и подготовлен к заряжанию в следующих параметрах:</p>' % (e(p["nachuch"]), e(blok)))
    akt.append('<table class="nob" style="margin-left:18px">')
    akt.append(_akt_row(1, "Средняя глубина скважин", fmt(avg_disp), "м"))
    akt.append(_akt_row(2, "Площадь блока", fmt(p["ploshad"] / 1000, 3), "тыс.м2"))
    akt.append(_akt_row(3, "Количество скважин", str(n_disp), "шт."))
    akt.append(_akt_row(4, "Объем торфов на взрыв", fmt(calc["objem_massiva"] / 1000, 2), "тыс.м3"))
    akt.append('</table>')
    akt.append('<p>Скважины пробурены в соответствии с проектом и очищены. Блок очищен от '
               'посторонних предметов и металлолома.</p>')
    akt.append('<div class="sig-box"><table class="nob"><tr><td>Ответственный:</td><td></td></tr>'
               '<tr><td>руководитель ВР</td><td>%s</td></tr>'
               '<tr><td>Маркшейдер</td><td><span class="sigline">&nbsp;</span></td></tr></table></div>'
               % e(p["nachuch"]))
    akt.append('</section>')
    S.append("".join(akt))

    # --- Ознакомление ---
    parts = _participants(p)
    oz = ['<section class="sheet"><p><b>С проектом массового взрыва ознакомлены и проинструктированы:</b></p>']
    oz.append('<table><tr><th class="num" style="width:12%">№ п/п</th><th>Ф.И.О.</th>'
              '<th style="width:25%">Профессия</th><th style="width:20%">Роспись</th></tr>')
    total = max(19, len(parts) + 2)
    for i in range(1, total + 1):
        fio, prof = parts[i - 1] if i <= len(parts) else ("", "")
        oz.append('<tr><td class="num">%d</td><td>%s</td><td>%s</td><td></td></tr>'
                  % (i, e(fio), e(prof)))
    oz.append('</table></section>')
    S.append("".join(oz))

    # --- Распорядок ---
    rasp = ['<section class="sheet">']
    rasp.append('<p class="right">«УТВЕРЖДАЮ»<br>Главный инженер %s<br>________________ %s</p>'
                % (e(pred), e(gling)))
    rasp.append('<div class="title">Р А С П О Р Я Д О К</div><div class="sub">проведения массового взрыва</div>')
    rasp.append('<p>Россыпное месторождение: <b>%s</b>&nbsp;&nbsp; блок: <b>%s</b></p>' % (e(mest), e(blok)))
    items = [
        'Дата взрыва: %s' % D,
        'Место взрыва: месторождение %s, %s' % (mest, prisk),
        'Время взрыва: с %s до %s по местному времени' % (p["vz1"], p["vz2"]),
        'Зарядка производится: %s с %s до %s' % (D, p["zar1"], p["zar2"]),
        'Способы инициирования зарядов, взрывной сети: электрический',
        'Общее количество взрываемых скважин (шт.): %d' % n_disp,
        'Способ взрывания: инициирующий импульс от капсюля-детонатора Искра-В (Старт-600м) '
        'устройства Искра-С, с интервалом замедления: 500 мс',
        'Тип замедлителей: ИСКРА-П (42; 67) мс',
        'Схема взрывания с указанием величин интервалов замедлений: %s' % p["shema"],
        'Порядок монтажа взрывной сети: к источнику тока',
        'Место расположения взрывной станции: согласно схемы',
        'Опасная зона: для людей — %s м; для оборудования — %s м; для сооружений — %s м.'
        % (calc["zona_ludi"], calc["zona_obor"], p["zoso"]),
        'Объекты находящиеся в опасной зоне: %s' % p["obj"],
        'Мероприятия по предотвращению повреждений охраняемых объектов: %s' % p["meri"],
        'Оборудование отводится от ближайшей скважины: экскаваторы на %s м; буровые станки на %s м.'
        % (calc["zona_obor"], calc["zona_obor"]),
        'Схема расстановки постов охраны опасной зоны прилагается.',
        'Ответственным руководителем массового взрыва назначен: %s (должность, фамилия, инициалы).' % nu,
        'Подвозка взрывчатых материалов к месту взрыва производится специализированным '
        'автомобилем: %s, водитель: %s. Сопровождающее лицо: %s.'
        % (p["avtoVM"], p["voditel"] or "____________", nu),
        'Для очистки скважин перед заряжанием используется: СБШ-250. Обслуживаемая бригада: ____________.',
    ]
    rasp.append('<ol class="items">' + "".join('<li>%s</li>' % e(x) for x in items) + '</ol>')
    rasp.append('</section>')
    S.append("".join(rasp))

    # --- Таблица параметров (альбомная) ---
    diam_mm = str(round(p["diam"] * 1000))
    groups = depth_groups(calc)
    tb = ['<section class="sheet land">']
    tb.append('<div class="title">Т А Б Л И Ц А</div>'
              '<div class="sub">параметров взрывных работ</div>'
              '<p class="center muted">на россыпном месторождении золота %s, блок %s на взрыв %s</p>'
              % (e(mest), e(blok), e(D)))
    heads = ["Глубина скважин, м", "Количество скважин", "Расстояние между скважинами, м",
             "Расстояние между рядами, м", "Диаметр скважины, мм", "Масса заряда в скважине, кг",
             "Длина заряда, м", "Длина забойки, м"]
    th1 = '<th class="num" rowspan="2">№ п/п</th>' + "".join('<th class="num" colspan="2">%s</th>' % e(h) for h in heads) + '<th class="num" rowspan="2">Примечание</th>'
    th2 = "".join('<th class="num">Р</th><th class="num">Ф</th>' for _ in heads)
    tb.append('<table class="grid"><tr>%s</tr><tr>%s</tr>' % (th1, th2))
    def rowf(i, vals):
        cells = '<td class="num">%s</td>' % i
        for v in vals:
            cells += '<td class="num">%s</td><td></td>' % e(v)
        cells += '<td></td>'
        return '<tr>%s</tr>' % cells
    for i, g in enumerate(groups, 1):
        mass = (g["sK"] + g["sL"]) / g["n"] + p["boevik"]
        tb.append(rowf(i, [fmt(g["d"], 1), str(g["n"]), fmt(p["a"], 1), fmt(calc["b"], 1),
                           diam_mm, fmt(mass, 1), fmt(g["sN"] / g["n"], 1), fmt(g["sZ"] / g["n"], 1)]))
    for k in range(len(groups), len(groups) + 3):
        tb.append(rowf("", ["", "", "", "", "", "", "", ""]))
    tb.append('</table>')
    blk1 = ('<b>Расчетная формула усредненного веса заряда:</b><br>1. Боевик %s — %s кг<br>'
            '2. Селитра / скв. — %s кг<br>3. Дизельное топливо — %s кг<br><b>Итого: %s кг</b>'
            % (e(bname), fmt(p["boevik"]), fmt(asn), fmt(dtn), fmt(calc["sr_massa"])))
    blk2 = ('<b>Общая масса заряда:</b><br>1. Гранулит М (АС+ДТ) — %s кг<br>2. %s — %s кг<br>'
            '<b>Итого ВМ: %s кг</b>' % (fmt(calc["mas_as"] + calc["mas_dt_kg"], 1), e(bname),
                                        fmt(calc["mas_pt"], 1), fmt(calc["obsh_massa"], 1)))
    blk3 = ('<b>Потребляемое кол-во СИ:</b><br>1. ИСКРА-В-Старт — %s<br>2. ИСКРА-С (500мс) — %s<br>'
            '3. ИСКРА-П (42 мс) — %s<br>4. ИСКРА-П (67 мс) — %s'
            % (calc["iskraV"], calc["iskra_s"], calc["iskra42"], calc["iskra67"]))
    tb.append('<table class="nob" style="margin-top:6px"><tr style="vertical-align:top">'
              '<td style="width:34%%">%s</td><td style="width:33%%">%s</td><td>%s</td></tr></table>' % (blk1, blk2, blk3))
    tb.append('<table class="nob" style="margin-top:6px"><tr><td>Расчет составил: %s &nbsp; %s</td>'
              '<td class="right">Расчет проверил: Главный инженер %s &nbsp; %s</td></tr></table>'
              % (e(nu), e(D), e(gling), e(D)))
    tb.append('</section>')
    S.append("".join(tb))

    # --- Инструктаж (лист 5) ---
    i5 = ['<section class="sheet"><p>Инструктаж работников провёл: <b>%s</b></p>'
          '<p class="center muted">(кем, когда)</p>' % e(nu)]
    instr5 = [
        'Непосредственное руководство работой персонала при подготовке и проведении массового '
        'взрыва, учет и сохранность ВМ при заряжании скважин возложить на: %s.' % nu,
        'Ответственным за вывод людей с территории запретной и опасной зон назначен: %s.' % nu,
        'Ответственным за заряжание и монтаж взрывной (электровзрывной) сети назначен: Старший взрывник %s.' % vzr,
        'Ответственным за вывод внутрикарьерного транспорта из запретной и опасной зон назначен: %s.' % nu,
        'Ответственным за охрану запретной и опасной зон назначен: %s.' % nu,
        'Ответственным за отключение электроэнергии, удаление в безопасное место эл/оборудования '
        'перед взрывом, а также за проверку и подключение ее после взрыва назначен: %s.' % nu,
        'Ответственным за подачу звуковых и световых сигналов назначен: %s.' % nu,
        'Ответственным за оповещение соседних предприятий, подразделений назначен: %s.' % nu,
        'Подача сигналов проводится по распоряжению. Исполнитель: %s. Звуковая сирена, '
        'установленная на зарядно-смесительной машине МЗ-3Б.' % p["nachuch"],
        'После выставления постов подается предупредительный сигнал: один продолжительный звуковой, оператором МЗ-3Б.',
        'По указанию ответственного за вывод людей все люди, не занятые заряжанием, должны '
        'удалиться за пределы опасной зоны: место расположения — столовая вахтового посёлка, согласно схемы.',
        'Осуществляются перечисленные в распорядке проведения массового взрыва дополнительные меры '
        'безопасности, связанные с вводом запретной зоны: запрещается проход не задействованных на '
        'зарядке работников, запрещен проезд техники.',
        'Заряжание скважин осуществляет: Старший взрывник %s.' % vzr,
        'Место сбора лиц, выполняющих заряжание, перед выходом из запретной зоны: пост №1.',
        'По завершению заряжания выставляются посты охраны опасной зоны.',
    ]
    i5.append('<ol class="items">' + "".join('<li>%s</li>' % e(x) for x in instr5) + '</ol></section>')
    S.append("".join(i5))

    # --- Инструктаж (лист 7) ---
    i7 = ['<section class="sheet">']
    i7.append('<ol class="items">')
    i7.append('<li>Укладку в заряды боевиков с капсюлем, монтаж электровзрывной сети осуществляет: '
              'Старший взрывник %s, под руководством ответственного руководителя ВР %s.</li>' % (e(vzr), e(nu)))
    i7.append('<li>Боевой сигнал: два длинных звуковых, оператором МЗ-3Б.</li>')
    i7.append('<li>После подачи боевого сигнала производится взрыв: неэлектрический (способ взрывания).</li>')
    i7.append('<li>Сигнал отбой: три коротких после осмотра места взрыва, после получения указания '
              'от ответственного руководителя ВР %s.</li>' % e(nu))
    i7.append('<li>Время проветривания и допуска людей в карьер, к месту взрыва — 00 час 30 мин.</li>')
    i7.append('</ol>')
    i7.append('<p><b>С распорядком проведения массового взрыва ознакомлены:</b></p>')
    nuu = p["nachuch"]
    soglas = [("Ответственный руководитель взрывных работ", nuu),
              ("Ответственный за вывод людей из опасной и запретной зон", nuu),
              ("Ответственный руководитель ВР в смене", nuu),
              ("Ответственный за заряжание и монтаж взрывной сети", vzr),
              ("Ответственный за вывод внутрикарьерного транспорта", nuu),
              ("Ответственный за отключение электроэнергии", nuu),
              ("Ответственный за охрану запретной и опасной зон", nuu),
              ("Ответственный за подачу сигналов", nuu),
              ("Ответственный за оповещение соседних предприятий", injot)]
    i7.append('<table class="nob">')
    for role, fio in soglas:
        i7.append('<tr><td style="width:62%%">%s:</td><td>%s</td><td class="right">'
                  '<span class="sigline">&nbsp;</span></td></tr>' % (e(role), e(fio)))
    i7.append('</table>')
    i7.append('<p>Распорядок проведения массового взрыва составил: %s &nbsp; %s</p>' % (e(nu), e(D)))
    i7.append('<p>Распорядок проведения массового взрыва проверил: Главный инженер %s &nbsp; %s</p>'
              % (e(gling), e(D)))
    i7.append('</section>')
    S.append("".join(i7))

    # --- Приказ (шапка-логотип + 17 пунктов) ---
    pr = ['<section class="sheet">']
    if lh:
        pr.append('<div class="lh"><img src="%s" alt="реквизиты"></div>' % lh)
    pr.append('<div class="title">П Р И К А З   №   %s</div>' % e(p["prikaz"]))
    pr.append('<p class="center">от %s &nbsp;&nbsp; %s</p>' % (e(D), e(p["np"])))
    pr.append('<p class="center"><b>О производстве массового взрыва %s</b></p>' % e(D))
    pr.append('<p class="center">на месторождении %s, блок № %s.</p>' % (e(mest), e(blok)))
    pr.append('<p>Согласно графику производства массовых взрывов и проекта горных работ на участке '
              'россыпного золота месторождение %s, блок %s, %s, %s с %s до %s часов будет произведен '
              'массовый взрыв.</p>' % (e(mest), e(blok), e(prisk), e(D), e(p["vz1"]), e(p["vz2"])))
    pr.append('<p>В целях обеспечения безопасности работ и сохранности ВМ,</p>')
    pr.append('<p class="center"><b>ПРИКАЗЫВАЮ:</b></p>')
    pitems = [
        'Проект производства массового взрыва на %s, разработанный на основании типового проекта, утвердить.' % blok,
        'Ответственным руководителем массового взрыва %s назначить: %s.' % (blok, nu),
        'Ответственность за вывод людей за пределы опасной зоны взрывных работ (%s метров по проекту) возложить на: %s.' % (calc["zona_ludi"], nu),
        'Ответственность за вывод техники за пределы опасной зоны (%s метров по проекту) возложить на: %s.' % (calc["zona_obor"], nu),
        'Непосредственное руководство работой персонала при подготовке и проведении массового взрыва, '
        'учет и сохранность ВМ при заряжании скважин возложить на: %s.' % nu,
        'Взрывником назначить: Старший взрывник %s.' % vzr,
        'Директор прииска обязан обеспечить подготовку и проведение массового взрыва: автотранспортом, '
        'рабочим персоналом для забойки скважин и загрузки АС в СЗМ, а также для назначения на посты охраны опасной зоны.',
        'Ответственность за отключение электроэнергии возложить на: %s.' % nu,
        'Зарядку скважин произвести: %s с %s до %s (сырые скважины зарядить с использованием '
        'полиэтиленового рукава).' % (D, p["zar1"], p["zar2"]),
        'Взрыв произвести: %s с %s до %s.' % (D, p["vz1"], p["vz2"]),
        'Оповещение ответственного руководителя взрывных работ %s об окончании взрывных работ или '
        'изменениях даты и времени взрыва, с объяснением причин, возложить на: ответственного руководителя ВР %s.' % (pred, nu),
        'Оповещение диспетчерской службы Зонального центра и Якутского районного центра единой системы '
        'организации воздушного движения о сроках и времени проведения массового взрыва возложить на: Инженер ОТ и ПБ %s.' % injot,
        'Ответственность за проведение инструктажа персоналу, привлекаемому к работам по загрузке АС в '
        'СЗМ, забойке скважин и охране опасной зоны, возлагается на: %s.' % nu,
        'Ответственный руководитель ВР, %s, должен вести работы в соответствии с утвержденным распорядком '
        'проведения массового взрыва, требованиями ФНиП ПБ «Правила безопасности при взрывных работах» и инструкций.' % nu,
        'Оповещение диспетчера %s о времени проведения массового взрыва за 30 мин до начала МВ — %s.' % (pred, dispet),
        'Все назначенные настоящим приказом ответственные лица на период подготовки и производства '
        'взрывных работ подчиняются ответственному руководителю массового взрыва.',
        'Контроль за исполнением настоящего приказа оставляю за собой.',
    ]
    pr.append('<ol class="items">' + "".join('<li>%s</li>' % e(x) for x in pitems) + '</ol>')
    pr.append('<p style="margin-top:14px">Главный инженер %s &nbsp;&nbsp; ________________ %s</p>' % (e(pred), e(gling)))
    pr.append('</section>')
    S.append("".join(pr))

    # --- Распоряжение о постах ---
    rp = ['<section class="sheet">']
    rp.append('<div class="title">Р А С П О Р Я Ж Е Н И Е</div>'
              '<div class="sub">о расстановке постов оцепления по охране опасной зоны</div>'
              '<p class="center">ВР на месторождении %s, блок %s</p>' % (e(mest), e(blok)))
    rp.append('<p>Взрыв %s, время взрыва с %s до %s часов.</p>' % (e(D), e(p["vz1"]), e(p["vz2"])))
    rp.append('<p>%s, в целях обеспечения безопасности производства взрыва, производит расстановку '
              'постов оцепления на границах опасной зоны %s м, в местах, указанных на плане горных работ, '
              'в следующем порядке:</p>' % (e(nu), calc["zona_ludi"]))
    rp.append('<ol class="items">')
    for i in range(1, 6):
        rp.append('<li>Пост №%d — перекрывает подходы со стороны ____________________.<br>'
                  'Ответственный ____________________ (подпись) ____________________</li>' % i)
    rp.append('</ol>')
    rp.append('<p><b>ВСЕМ ПОСТОВЫМ!</b></p>')
    rp.append('<p>1. Бдительно наблюдать за местностью, самовольно не покидать пост и никого не пропускать в опасную зону.</p>')
    rp.append('<p>2. Внимательно следить за подаваемыми сигналами:</p>')
    rp.append('<p class="center">ОДИН ДЛИННЫЙ звуковой сигнал — предупредительный;<br>'
              'ДВА ДЛИННЫХ звуковых сигнала — боевой;<br>ТРИ КОРОТКИХ звуковых сигнала — отбой.</p>')
    rp.append('<p>Ответственный за выставление постов опасной зоны: %s _____________ %s</p>' % (e(nu), e(D)))
    rp.append('<p>%s %s _____________ %s</p>' % (e(nu), e(pred), e(D)))
    rp.append('</section>')
    S.append("".join(rp))

    # --- Расчёт параметров (лист 12) ---
    c12 = ['<section class="sheet"><p class="center"><b>Расчет параметров буровзрывных работ и потребности материалов</b></p>']
    c12.append('<p>Вместимость погонного метра скважины (Р) определяется по справочным таблицам исходя '
               'из диаметра скважины и плотности ВВ в заряде и составит: <b>%s</b> кг/пог.м.</p>' % fmt(calc["raskh_sel"]))
    c12.append('<p>Линия сопротивления по подошве уступа (ЛСПП) для вертикального заряда рассчитывается по формуле:</p>')
    c12.append('<div class="formula">Wп = 53 · k<sub>т</sub> · d<sub>зар</sub> · %s , м</div>'
               % sqrt(frac("ρ<sub>вв</sub>·1000 − l", "ρ<sub>пор</sub>")))
    c12.append('<p>где: k<sub>т</sub> — коэффициент местных геологических условий, k<sub>т</sub> = %s; '
               'd<sub>зар</sub> — диаметр заряда, d<sub>зар</sub> = %s м; ρ<sub>вв</sub> — плотность ВВ '
               'в заряде, ρ<sub>вв</sub> = %s г/см³; l — коэффициент работоспособности ВВ (игданит) по '
               'отношению к %s, l = %s; ρ<sub>пор</sub> — плотность породы, ρ<sub>пор</sub> = %s кг/м³.</p>'
               % (fmt(p["ktresh"], 1), fmt(p["diam"], 3), fmt(p["plotvv"]), e(bname), fmt(p["krab"]), fmt0(p["plotpor"])))
    c12.append('<div class="formula">Wп = 53 · %s · %s · %s = <b>%s</b> м.</div>'
               % (fmt(p["ktresh"], 1), fmt(p["diam"], 3),
                  sqrt(frac("%s − %s" % (fmt0(p["plotvv"] * 1000), fmt(p["krab"])), fmt0(p["plotpor"]))),
                  fmt(calc["lspp"], 1)))
    c12.append('<p>Расстояние между скважинами в ряду: a = Wп · m = %s · %s ≈ <b>%s</b> м; между рядами '
               'b ≈ <b>%s</b> м, где m — коэффициент сближения зарядов, m = %s.</p>'
               % (fmt(calc["lspp"], 1), fmt(calc["ksbl"]), fmt(p["a"], 1), fmt(calc["b"], 1), fmt(calc["ksbl"])))
    c12.append('<p>Для инициирования зарядов скважин используются неэлектрические системы ИСКРА С/П, '
               'поэтому расстояние между рядами и скважинами принято равным.</p>')
    c12.append('<p>Число рядов скважинных зарядов принято в соответствии с минимальной шириной рабочей '
               'площадки экскаватора. Количество рядов на полигоне %s составит <b>%s</b> шт.</p>' % (e(blok), p["ryad"]))
    c12.append('<p>Величина перебура: L<sub>пер</sub> = 14 · d<sub>зар</sub> · %s = %s м; принимается '
               'равной <b>%s</b> м.</p>' % (sqrt("ρ<sub>вв</sub> · 0,8"), fmt(calc["l_per_form"]), fmt(calc["sr_pereb"], 1)))
    c12.append('</section>')
    S.append("".join(c12))

    # --- Расчёт (лист 13) ---
    c13 = ['<section class="sheet"><p>Глубина скважины устанавливается по формуле:</p>']
    c13.append('<div class="formula">L<sub>с</sub> = H + L<sub>пер</sub> = %s + %s = <b>%s</b> м.</div>'
               % (fmt(calc["sr_hust"]), fmt(calc["sr_pereb"]), fmt(calc["sr_glub"])))
    c13.append('<p>Коэффициент использования скважины (Кис):</p>')
    c13.append('<div class="formula">Кис = %s = %s = <b>%s</b>.</div>'
               % (frac("H", "L<sub>с</sub>"), frac(fmt(calc["sr_hust"]), fmt(calc["sr_glub"])), fmt(p["kis"])))
    c13.append('<p>Вес заряда в скважине (Q<sub>скв</sub>) принимается по фактическим данным каталога скважин:</p>')
    c13.append('<div class="formula">Q<sub>скв</sub> = Q<sub>ас</sub> + Q<sub>дт</sub> + Q<sub>боевика</sub> = '
               '%s + %s + %s = <b>%s</b> кг.</div>' % (fmt(asn), fmt(dtn), fmt(p["boevik"]), fmt(calc["sr_massa"])))
    c13.append('<p>Длина заряда: L<sub>зар</sub> = ΣL<sub>зар</sub> / n<sub>скв</sub> = <b>%s</b> м.</p>' % fmt(calc["sr_zar"]))
    c13.append('<p>Длина забойки: L<sub>заб</sub> = ΣL<sub>заб</sub> / n<sub>скв</sub> = <b>%s</b> м.</p>' % fmt(calc["sr_zaboi"]))
    c13.append('<p>Площадь, приходящаяся на одну скважину: S<sub>скв</sub> = a · b = %s · %s = <b>%s</b> кв.м.</p>'
               % (fmt(p["a"], 1), fmt(calc["b"], 1), fmt(calc["s_per_skv"])))
    c13.append('<p>Выход горной массы по маркшейдерским данным: V<sub>гм</sub>/пог.м = V<sub>маркш</sub> / ΣL<sub>с</sub> '
               '= %s = <b>%s</b> м³/пог.м.</p>' % (frac(fmt0(calc["objem_massiva"]), fmt0(calc["sumD"])), fmt(calc["vyhod_gm"])))
    c13.append('<p>Объем взрываемой горной массы: V<sub>гм</sub> = <b>%s</b> м³.</p>' % fmt(calc["objem_massiva"], 1))
    c13.append('</section>')
    S.append("".join(c13))

    # --- Расчёт (лист 14) + основные параметры ---
    c14 = ['<section class="sheet"><p><b>Суммарный расход ВВ (игданита) на взрыв составит:</b></p>']
    c14.append('<p>Q<sub>селитры</sub> = N<sub>скв</sub> · Q<sub>скв</sub> = %d · %s = %s т;</p>' % (n_disp, fmt(asn), fmt(calc["mas_as"] / 1000)))
    c14.append('<p>Q<sub>дт</sub> = Q<sub>селитры</sub> · %s = %s т;</p>' % (fmt(p["doldt"], 3), fmt(calc["mas_dt_kg"] / 1000)))
    c14.append('<p>M<sub>гранулита</sub> = %s + %s = %s т.</p>' % (fmt(calc["mas_as"] / 1000), fmt(calc["mas_dt_kg"] / 1000), fmt((calc["mas_as"] + calc["mas_dt_kg"]) / 1000)))
    c14.append('<p>Расход СИ: Искра-С — %s шт; Искра-П (67 мс) — %s шт; Искра-П (42 мс) — %s шт; '
               'Искра-В (Старт-600м) — %s шт.</p>' % (calc["iskra_s"], calc["iskra67"], calc["iskra42"], calc["iskraV"]))
    c14.append('<p>Расход %s на боевики: M<sub>б</sub> · N<sub>скв</sub> = %s · %d = %s кг.</p>' % (e(bname), fmt(p["boevik"]), n_disp, fmt(calc["mas_pt"])))
    op = [
        ("1", "Площадь полигона", "тыс.кв.м", fmt(p["ploshad"] / 1000, 3)),
        ("2", "Высота уступа", "м", fmt(calc["sr_hust"])),
        ("3", "Объем взрыва", "тыс.куб.м", fmt(calc["objem_massiva"] / 1000)),
        ("4", "Средняя глубина скважин", "м", fmt(avg_disp)),
        ("5", "в т.ч. перебур", "м", fmt(calc["sr_pereb"])),
        ("6", "Диаметр скважины", "мм", diam_mm),
        ("7", "Коэффициент использования скважины", "", fmt(p["kis"])),
        ("8", "Линия сопротивления по подошве (ЛСПП)", "м", fmt(calc["lspp"], 1)),
        ("9", "Расстояние между скважинами", "м", fmt(p["a"], 1)),
        ("10", "Расстояние между рядами скважин", "м", fmt(calc["b"], 1)),
        ("11", "Расположение скважин", "", p["raspol"]),
        ("12", "Количество скважин", "шт", str(n_disp)),
        ("13", "Объем бурения скважин", "пог.м", fmt0(drill_disp)),
        ("14", "Удельный расход Гранулита М", "кг/пог.м", fmt(calc["ud_vv"], 3)),
        ("15", "Длина заряда", "м", fmt(calc["sr_zar"])),
        ("16", "Длина забойки", "м", fmt(calc["sr_zaboi"])),
        ("17", "Величина заряда в скважине", "кг", fmt(calc["sr_massa"])),
        ("18", "Выход горной массы на 1 пог.м скважины", "куб.м", fmt(calc["vyhod_gm"])),
        ("19", "Расход Гранулит М", "т", fmt((calc["mas_as"] + calc["mas_dt_kg"]) / 1000, 3)),
        ("20", "Удельный расход АС на 1 куб.м ГМ", "кг/куб.м", fmt(calc["ud_as"], 3)),
        ("21", bname, "кг", fmt(calc["mas_pt"])),
        ("22", "Расход ИСКРА-С", "шт", str(calc["iskra_s"])),
        ("23", "Расход Искра-П (67 мс)", "шт", str(calc["iskra67"])),
        ("24", "Расход Искра-П (42 мс)", "шт", str(calc["iskra42"])),
        ("25", "Расход Искра-В (Старт-600м)", "шт", str(calc["iskraV"])),
        ("26", "Расход аммиачной селитры на взрыв", "т", fmt(calc["mas_as"] / 1000, 3)),
        ("27", "Удельный расход аммиачной селитры", "кг/м3", fmt(calc["ud_as"], 3)),
    ]
    c14.append('<p class="center"><b>Основные параметры буровзрывных работ</b></p>')
    c14.append('<table><tr><th class="num">№ п/п</th><th>Параметр</th><th class="num">Ед. изм.</th><th class="num">Средний показатель</th></tr>')
    for i, name, unit, val in op:
        c14.append('<tr><td class="num">%s</td><td>%s</td><td class="num">%s</td><td class="num">%s</td></tr>'
                   % (i, e(name), e(unit), e(val)))
    c14.append('</table></section>')
    S.append("".join(c14))

    # --- Безопасные расстояния (лист 15) ---
    import math as _m
    s15 = ['<section class="sheet"><p class="center"><b>Расчет безопасных расстояний при взрывных работах</b></p>']
    s15.append('<p>Расчет производится согласно главе XII ФНП «Правила безопасности при производстве, '
               'хранении и применении взрывчатых материалов промышленного назначения».</p>')
    s15.append('<p><b>Определение зон, опасных по разлету отдельных кусков породы (грунта).</b></p>')
    s15.append('<p>Расстояние, безопасное для людей при взрывании скважинных зарядов, рассчитанных на '
               'дробящее действие, определяется по формуле:</p>')
    s15.append('<div class="formula">r<sub>раз</sub> = 1250 · n<sub>з</sub> · %s , м</div>'
               % sqrt(frac("4d", "(1+1)·b")))
    s15.append('<p>где: d — диаметр взрываемой скважины, d = %s м; b — расстояние между рядами, b = %s м; '
               'n<sub>з</sub> — коэффициент заполнения скважин ВВ.</p>' % (fmt(p["diam"], 3), fmt(calc["b"], 1)))
    s15.append('<div class="formula">n<sub>з</sub> = %s = %s = <b>%s</b>.</div>'
               % (frac("L<sub>з</sub>", "L<sub>с</sub>"), frac(fmt(calc["sr_zar"]), fmt(calc["sr_glub"])), fmt(calc["nz"], 3)))
    s15.append('<div class="formula">r<sub>раз</sub> = 1250 · %s · %s = <b>%s</b> м.</div>'
               % (fmt(calc["nz"], 3), fmt(calc["h9"]), fmt(calc["r_raz"], 1)))
    s15.append('<p>Коэффициент рельефа К<sub>р</sub> = <b>%s</b> (превышение H = %s м).</p>' % (fmt(calc["kr"]), fmt(p["prev"], 1)))
    s15.append('<div class="formula">R<sub>раз</sub> = r<sub>раз</sub> · К<sub>р</sub> = %s · %s = <b>%s</b> м.</div>'
               % (fmt(calc["r_raz"], 1), fmt(calc["kr"]), fmt(calc["R_raz"], 1)))
    s15.append('<p>Окончательное значение радиуса опасной зоны по разлету отдельных кусков породы '
               'принимается равным <b>%s</b> м.</p>' % max(1000, _m.ceil(calc["R_raz"] / 100) * 100))
    s15.append('</section>')
    S.append("".join(s15))

    # --- Безопасные (лист 16) ---
    s16 = ['<section class="sheet"><p><b>Определение расстояний, безопасных по действию ударной воздушной волны (УВВ) на здания и сооружения.</b></p>']
    s16.append('<p>R<sub>в</sub> = 10 · Q<sup>1/3</sup>, где Q — максимальная масса заряда ВВ взрываемого блока, Q = %s кг.</p>' % fmt0(calc["obsh_massa"]))
    s16.append('<div class="formula">R<sub>в</sub> = 10 · %s<sup>1/3</sup> = <b>%s</b> м.</div>' % (fmt0(calc["obsh_massa"]), fmt(calc["r_uvv"], 1)))
    s16.append('<p>Принимаем величину безопасного расстояния по действию УВВ для зданий и сооружений равной <b>%s</b> м.</p>' % calc["r_uvv_zd"])
    s16.append('<p><b>Расчет сейсмически безопасных расстояний.</b></p>')
    s16.append('<p>Q = 2 · %s · 0,9 + 1 = %s кг.</p>' % (fmt(calc["sr_massa"], 1), fmt0(calc["q_seism"])))
    s16.append('<div class="formula">r<sub>с</sub> = 15,14 · Q<sup>1/3</sup> = 15,14 · %s<sup>1/3</sup> = <b>%s</b> м.</div>' % (fmt0(calc["q_seism"]), fmt(calc["r_seism"], 1)))
    s16.append('<p>Безопасное расстояние по сейсмическому действию принимаем равным <b>%s</b> м.</p>' % (_m.ceil(calc["r_seism"] / 10) * 10))
    s16.append('<p><b>Расчет расстояний, безопасных по высоте разлета отдельных кусков породы.</b></p>')
    s16.append('<div class="formula">r<sub>разл.в</sub> = 1,4 · r<sub>раз</sub> = 1,4 · %s = <b>%s</b> м.</div>' % (fmt(calc["r_raz"], 1), fmt(calc["r_raz_v"], 1)))
    s16.append('<p>Расстояние, безопасное по высоте разлета отдельных кусков породы, принимаем равным <b>%s</b> м.</p>' % max(500, _m.ceil(calc["r_raz_v"] / 100) * 100))
    s16.append('</section>')
    S.append("".join(s16))

    # --- Безопасные (лист 17) ---
    s17 = ['<section class="sheet"><p><b>Расчет расстояния, исключающего передачу детонации при хранении ВМ, доставленных к месту работ.</b></p>']
    s17.append('<p>Расчет произведен в соответствии с требованиями п. 845 главы XII ФНиП ПБ «Правила '
               'безопасности при взрывных работах». Рассматриваются ВВ (гранулит М) и средства инициирования; К<sub>д</sub> = 0,8.</p>')
    s17.append('<p>Окончательное значение расстояния, исключающего передачу детонации при хранении ВМ, '
               'доставленных к месту работ, принимаем равным <b>15</b> м.</p>')
    s17.append('<p><b>По результатам расчетов радиус опасной зоны на участке производства взрывных работ принимаем:</b></p>')
    s17.append('<p>для людей — <b>%s</b> м;<br>для оборудования — <b>%s</b> м.</p>' % (calc["zona_ludi"], calc["zona_obor"]))
    s17.append('<p>Принятые расстояния должны быть не менее расчетных по разлету кусков, УВВ, сейсмическому '
               'воздействию и высоте разлета; при наличии более жестких требований проекта принимается большее значение.</p>')
    s17.append('<p style="margin-top:14px">Расчет составил: Начальник участка "%s" _____________ / %s /</p>' % (e(mest), e(p["nachuch"])))
    s17.append('<p class="muted">Проект массового взрыва со всеми графическими материалами хранится в делах '
               'взрывного участка (цеха) до полной отработки взорванного блока (ФНиП ПБ «Правила безопасности при взрывных работах»).</p>')
    s17.append('</section>')
    S.append("".join(s17))

    # --- Тулбар ---
    excel_btn = ('<a class="btn" href="%s">Скачать Excel</a>' % e(excel_url)) if excel_url else ""
    toolbar = (
        '<div class="toolbar">'
        '<button class="btn primary" onclick="window.print()">Печать / Сохранить в PDF</button>'
        '%s'
        '<button class="btn" onclick="ccToggle(this)">Выключить редактирование</button>'
        '<span class="sp"></span>'
        '<span class="hint">Любой текст можно править прямо здесь, затем «Печать / Сохранить в PDF». '
        'Правки в Excel не переносятся.</span>'
        '</div>' % excel_btn)

    return (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Проект массового взрыва — %s, блок %s</title><style>%s</style></head>'
        '<body>%s<div class="doc" id="doc" contenteditable="true">%s</div>'
        '<script>%s</script></body></html>'
        % (e(mest), e(blok), CSS, toolbar, "".join(S), SCRIPT))
