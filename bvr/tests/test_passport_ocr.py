# -*- coding: utf-8 -*-
"""Юнит-тесты модуля распознавания паспорта БВР (passport_ocr).

Сеть не используется: vision-вызовы заменяются фейковым клиентом, рендер PDF
подменяется заглушкой. Запуск:

    # standalone (без Django):
    python -m unittest bvr.tests.test_passport_ocr   # из папки ERP
    # либо через Django:
    ../.venv/bin/python manage.py test bvr.tests.test_passport_ocr
"""
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

# Позволяем запускать как из ERP (Django), так и напрямую.
_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parent.parent))  # .../bvr

import passport_ocr as po  # noqa: E402

FIXTURES = _THIS.parent / "fixtures"


# --------------------------------------------------------------------------
# Фейковый OpenAI-совместимый клиент
# --------------------------------------------------------------------------
class _Resp:
    def __init__(self, content):
        self.choices = [types.SimpleNamespace(
            message=types.SimpleNamespace(content=content))]


class FakeClient:
    """Возвращает заранее заданный JSON в зависимости от типа промпта."""

    def __init__(self, depth_matrix, tech, locate=True, escalate_matrix=None):
        self.depth_matrix = depth_matrix
        self.tech = tech
        self.locate = locate
        self.escalate_matrix = escalate_matrix
        self.calls = []
        self._escalated = False

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    def create(self, model, messages, **kw):
        text = messages[0]["content"][0]["text"]
        self.calls.append(model)
        if "depth_table" in text and "tech_table" in text:
            if not self.locate:
                return _Resp(json.dumps({"depth_table": None, "tech_table": None}))
            return _Resp(json.dumps({
                "depth_table": {"x0": 0.01, "y0": 0.66, "x1": 0.34, "y1": 0.98},
                "tech_table": {"x0": 0.40, "y0": 0.09, "x1": 0.62, "y1": 0.34},
            }))
        if "Проектная глубина скважин" in text and '"tech"' not in text:
            return _Resp(json.dumps({"matrix": self.depth_matrix,
                                     "rows": len(self.depth_matrix), "max_cols": 3}))
        if "технологических показателей" in text:
            return _Resp(json.dumps(self.tech))
        # _FULL_PROMPT (запасной / эскалация)
        matrix = self.depth_matrix
        if self.escalate_matrix is not None and model == po.VisionConfig().model_escalate:
            matrix = self.escalate_matrix
            self._escalated = True
        return _Resp(json.dumps({"matrix": matrix, "rows": len(matrix),
                                 "max_cols": 3, "tech": self.tech}))


def _cfg(**kw):
    base = dict(enabled=True, api_key="test", two_pass=True, escalate=True,
                cache_dir=tempfile.mkdtemp())
    base.update(kw)
    return po.VisionConfig(**base)


# --------------------------------------------------------------------------
# Тесты разбора
# --------------------------------------------------------------------------
class ParsingTests(unittest.TestCase):
    def test_num(self):
        self.assertEqual(po._num("9,5"), 9.5)
        self.assertEqual(po._num("203"), 203.0)
        self.assertEqual(po._num(7), 7.0)
        self.assertIsNone(po._num(""))
        self.assertIsNone(po._num("—"))
        self.assertIsNone(po._num(None))

    def test_fmt_depth(self):
        self.assertEqual(po._fmt_depth(9.5), "9,5")
        self.assertEqual(po._fmt_depth(5.0), "5")
        self.assertEqual(po._fmt_depth(None), "0")
        self.assertEqual(po._fmt_depth(0), "0")

    def test_matrix_to_card_text(self):
        m = [[None, 5, 9.5, 9.5], [5, 9.3, 9.3, None], [None, None, 5.0, None]]
        txt = po.matrix_to_card_text(m)
        self.assertEqual(txt, "0 5 9,5 9,5\n5 9,3 9,3\n0 0 5")
        # round-trip через расчётный парсер
        from bvr_calc import parse_charge_card
        wells = parse_charge_card(txt)
        self.assertEqual(len(wells), 7)

    def test_count_and_stats(self):
        m = [[None, 5, 9.5], [5, 9.3, 9.3]]
        self.assertEqual(po._count_wells(m), 5)
        count, avg, dmin, dmax = po._depth_stats(m)
        self.assertEqual(count, 5)
        self.assertAlmostEqual(dmin, 5.0)
        self.assertAlmostEqual(dmax, 9.5)

    def test_extract_json(self):
        self.assertEqual(po._extract_json('```json\n{"a":1}\n```'), {"a": 1})
        self.assertEqual(po._extract_json('text {"a":2} tail'), {"a": 2})
        with self.assertRaises(ValueError):
            po._extract_json("нет json")

    def test_valid_box(self):
        self.assertTrue(po._valid_box({"x0": 0, "y0": 0, "x1": 0.5, "y1": 0.5}))
        self.assertFalse(po._valid_box({"x0": 0.5, "y0": 0, "x1": 0.4, "y1": 0.5}))
        self.assertFalse(po._valid_box(None))
        self.assertFalse(po._valid_box({"x0": 0, "y0": 0, "x1": 0.01, "y1": 0.01}))


class CrossCheckTests(unittest.TestCase):
    def setUp(self):
        self.m = [[None, 5, 9.5, 9.5], [5, 9.3, 9.3, None]]  # 6 скважин

    def test_match_no_warnings(self):
        tech = {"kolichestvo_skvazhin_sht": 6, "srednyaya_glubina_m": 7.7}
        self.assertEqual(po.cross_checks(self.m, tech), [])
        self.assertTrue(po._checks_passed(self.m, tech))

    def test_mismatch_warns(self):
        tech = {"kolichestvo_skvazhin_sht": 50, "srednyaya_glubina_m": 20}
        warns = po.cross_checks(self.m, tech)
        self.assertGreaterEqual(len(warns), 1)
        self.assertFalse(po._checks_passed(self.m, tech))

    def test_empty_matrix(self):
        warns = po.cross_checks([], {})
        self.assertTrue(any("пуст" in w for w in warns))


# --------------------------------------------------------------------------
# Тесты конвейера (рендер замокан, клиент фейковый)
# --------------------------------------------------------------------------
class PipelineTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self._patch = mock.patch.object(
            po, "render_pdf_page", return_value=Image.new("RGB", (1200, 850), "white"))
        self._patch.start()
        # реальный путь к существующему PDF — для хеша и проверки размера
        self.pdf = str(FIXTURES / "P-15.pdf")
        self.assertTrue(os.path.exists(self.pdf), "нет фикстуры P-15.pdf")

    def tearDown(self):
        self._patch.stop()

    def test_two_pass_success(self):
        matrix = [[None, 5, 9.5, 9.5], [5, 9.3, 9.3, None]]
        tech = {"kolichestvo_skvazhin_sht": 6, "srednyaya_glubina_m": 7.7,
                "diametr_mm": 203, "kis": 0.9, "setka_bureniya": "5,5x5,0",
                "burovoy_blok": "П-15", "mestorozhdenie": "Урочище Сайлык"}
        client = FakeClient(matrix, tech)
        res = po.recognize_passport(self.pdf, cfg=_cfg(), client=client)
        self.assertTrue(res["ok"])
        self.assertEqual(res["source"], "vision")
        self.assertEqual(res["charge_card"]["wells_count"], 6)
        self.assertIn("9,5", res["charge_card"]["text"])
        self.assertEqual(res["tech_params"]["diametr_mm"], 203)
        self.assertEqual(res["stamp"]["burovoy_blok"], "П-15")
        # 3 вызова: locate + depth + tech
        self.assertEqual(len(client.calls), 3)

    def test_cache(self):
        matrix = [[5, 9.5]]
        tech = {"kolichestvo_skvazhin_sht": 2}
        cfg = _cfg()
        c1 = FakeClient(matrix, tech)
        po.recognize_passport(self.pdf, cfg=cfg, client=c1)
        c2 = FakeClient(matrix, tech)
        res2 = po.recognize_passport(self.pdf, cfg=cfg, client=c2)
        self.assertTrue(res2.get("cached"))
        self.assertEqual(len(c2.calls), 0)

    def test_fallback_full_page(self):
        # locate возвращает null → запасной одностраничный режим
        matrix = [[5, 9.5, 9.3]]
        tech = {"kolichestvo_skvazhin_sht": 3, "srednyaya_glubina_m": 7.9}
        client = FakeClient(matrix, tech, locate=False)
        res = po.recognize_passport(self.pdf, cfg=_cfg(), client=client)
        self.assertTrue(res["ok"])
        self.assertEqual(res["source"], "vision_full")
        self.assertEqual(res["charge_card"]["wells_count"], 3)

    def test_escalation(self):
        # Первый ответ не сходится по количеству, эскалация на Opus исправляет.
        bad = [[5]]                       # 1 скважина
        good = [[5, 9.5, 9.3, 9.4, 9.5]]  # 5 скважин
        tech = {"kolichestvo_skvazhin_sht": 5, "srednyaya_glubina_m": 8.5}
        client = FakeClient(bad, tech, locate=False, escalate_matrix=good)
        res = po.recognize_passport(self.pdf, cfg=_cfg(), client=client)
        self.assertEqual(res["source"], "vision_escalated")
        self.assertEqual(res["charge_card"]["wells_count"], 5)

    def test_disabled(self):
        cfg = _cfg(api_key="")  # не настроено
        res = po.recognize_passport(self.pdf, cfg=cfg, client=None, use_cache=False)
        self.assertFalse(res["ok"])
        self.assertEqual(res["source"], "disabled")

    def test_non_json_does_not_crash(self):
        """Регрессия P-17: модель вернула не-JSON — прогон не должен падать."""
        class BadClient:
            calls = 0

            @property
            def chat(self):
                return self

            @property
            def completions(self):
                return self

            def create(self, model, messages, **kw):
                BadClient.calls += 1
                return _Resp("Извините, не могу прочитать таблицу на чертеже.")

        res = po.recognize_passport(self.pdf, cfg=_cfg(), client=BadClient(),
                                    use_cache=False)
        self.assertFalse(res["ok"])          # не распознано, но без исключения
        self.assertIsInstance(res.get("warnings"), list)
        self.assertGreater(BadClient.calls, 1)  # были повторы

    def test_retry_recovers(self):
        """Невалидный JSON в первой попытке, валидный — во второй."""
        good = {"matrix": [[5, 9.5, 9.3]], "rows": 1, "max_cols": 3,
                "tech": {"kolichestvo_skvazhin_sht": 3, "srednyaya_glubina_m": 7.9}}

        class FlakyClient:
            def __init__(self):
                self.n = 0

            @property
            def chat(self):
                return self

            @property
            def completions(self):
                return self

            def create(self, model, messages, **kw):
                text = messages[0]["content"][0]["text"]
                if "depth_table" in text:           # locate → пусто, идём в full
                    return _Resp(json.dumps({"depth_table": None, "tech_table": None}))
                self.n += 1
                if self.n == 1:
                    return _Resp("не json, прости")  # первая попытка full — мусор
                return _Resp(json.dumps(good))       # повтор — валидный JSON

        res = po.recognize_passport(self.pdf, cfg=_cfg(), client=FlakyClient(),
                                    use_cache=False)
        self.assertTrue(res["ok"])
        self.assertEqual(res["charge_card"]["wells_count"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
