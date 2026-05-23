#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Живой прогон распознавания паспортов БВР через OpenRouter.

Использует НАСТОЯЩИЙ API (тратит токены OpenRouter). Запускать у себя,
задав ключ в переменной окружения.

Пример (из папки ERP):

    export BVR_VISION_API_KEY="sk-or-..."          # ключ OpenRouter
    # опционально:
    export BVR_VISION_MODEL="anthropic/claude-sonnet-4.6"
    export BVR_VISION_MODEL_LOCATE="anthropic/claude-haiku-4.5"

    ../.venv/bin/python bvr/tests/run_ocr.py                 # все фикстуры
    ../.venv/bin/python bvr/tests/run_ocr.py путь/к/Паспорт.pdf
    ../.venv/bin/python bvr/tests/run_ocr.py --save out_json/ bvr/tests/fixtures/*.pdf

Зависимости на сервере: pip install pymupdf pillow openai httpx
"""
import argparse
import json
import sys
import time
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parent.parent))  # .../bvr

import passport_ocr as po  # noqa: E402

FIXTURES = _THIS.parent / "fixtures"


def main():
    ap = argparse.ArgumentParser(description="Живой прогон распознавания паспортов БВР")
    ap.add_argument("files", nargs="*", help="PDF-файлы (по умолчанию — все фикстуры)")
    ap.add_argument("--save", metavar="DIR", help="папка для сохранения JSON результатов")
    ap.add_argument("--no-cache", action="store_true", help="игнорировать кэш")
    args = ap.parse_args()

    cfg = po.load_config()
    if not cfg.configured:
        print("ОШИБКА: распознавание не настроено. Задайте BVR_VISION_API_KEY "
              "(ключ OpenRouter) и при необходимости BVR_VISION_ENABLED=1.")
        return 2

    files = [Path(f) for f in args.files] if args.files else sorted(FIXTURES.glob("*.pdf"))
    if not files:
        print("Нет файлов для распознавания.")
        return 1

    print(f"Модель чтения: {cfg.model_read}")
    print(f"Модель поиска областей: {cfg.model_locate} (two_pass={cfg.two_pass})")
    print(f"База API: {cfg.base_url}")
    print("=" * 92)
    header = (f"{'файл':<16}{'статус':<9}{'ряд×макс':<10}{'скв.':>6}"
             f"{'ср.гл.':>8}{'деклар.':>9}{'предупр.':>10}  источник")
    print(header)
    print("-" * 92)

    save_dir = Path(args.save) if args.save else None
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)

    ok_count = 0
    t0 = time.time()
    for f in files:
        try:
            res = po.recognize_passport(f, cfg=cfg, use_cache=not args.no_cache)
        except Exception as exc:  # noqa: BLE001
            print(f"{f.name:<16}ИСКЛ.   {exc}")
            continue

        cc = res.get("charge_card") or {}
        tp = res.get("tech_params") or {}
        status = "OK" if res.get("ok") else "FAIL"
        if res.get("ok"):
            ok_count += 1
        size = f"{cc.get('rows', 0)}x{cc.get('max_cols', 0)}"
        declared = tp.get("kolichestvo_skvazhin_sht")
        declared_s = str(int(declared)) if declared else "—"
        avg = cc.get("avg_depth")
        avg_s = f"{avg}" if avg else "—"
        nwarn = len(res.get("warnings") or [])
        src = res.get("source", "")
        print(f"{f.name:<16}{status:<9}{size:<10}{cc.get('wells_count', 0):>6}"
              f"{avg_s:>8}{declared_s:>9}{nwarn:>10}  {src}")
        if not res.get("ok") and res.get("error"):
            print(f"    ↳ {res['error']}")

        if save_dir:
            (save_dir / f"{f.stem}.json").write_text(
                json.dumps(res, ensure_ascii=False, indent=2), "utf-8")

    print("-" * 92)
    dt = time.time() - t0
    print(f"Готово: {ok_count}/{len(files)} успешно за {dt:.1f} c.")
    if save_dir:
        print(f"JSON сохранены в {save_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
