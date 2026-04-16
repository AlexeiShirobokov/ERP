import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

import pandas as pd
from playwright.sync_api import Page, sync_playwright

# =========================
# НАСТРОЙКИ
# =========================
PROFILE_DIR = "hh_profile"
VACANCIES_URL = "https://hh.ru/employer/vacancies?hhtmFrom=vacancy"
RESPONSES_URL_TEMPLATE = "https://hh.ru/employer/vacancyresponses?vacancyId={vacancy_id}"

# ТЕСТОВЫЙ РЕЖИМ:
# берем максимум 2 вакансии и максимум 5 резюме на вакансию
MAX_VACANCIES = 2
MAX_RESUMES_PER_VACANCY = 5

# Если True, скрипт будет нажимать "Показать телефон" на странице резюме
CLICK_SHOW_PHONE_ON_RESUME = True

DEBUG_DIR = Path("debug")
OUT_RESPONSES_XLSX = "hh_real_responses.xlsx"
OUT_RESPONSES_JSON = "hh_real_responses.json"
OUT_VACANCIES_XLSX = "hh_vacancies_summary.xlsx"
OUT_VACANCIES_JSON = "hh_vacancies_summary.json"


# =========================
# ОБЩИЕ УТИЛИТЫ
# =========================

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def safe_filename(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|]+", "_", value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value[:120] or "item"


def text_or_empty(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    if isinstance(value, bool):
        return "True" if value else "False"
    return ""


def text_from_value(
    value: Any,
    preferred_keys: Iterable[str] = ("string", "trl", "formatted", "text", "name", "value", "label")
) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, list):
        parts = [text_from_value(x, preferred_keys) for x in value]
        return ", ".join([x for x in parts if x])
    if isinstance(value, dict):
        for key in preferred_keys:
            if key in value:
                result = text_from_value(value.get(key), preferred_keys)
                if result:
                    return result
    return ""


def normalize_bool_like(value: Any) -> str:
    if value in (True, "true", "True", 1, "1"):
        return "True"
    if value in (False, "false", "False", 0, "0"):
        return "False"
    return text_from_value(value)


def normalize_resume_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    raw_url = raw_url.strip()
    if raw_url.startswith("/"):
        raw_url = urljoin("https://hh.ru", raw_url)
    parsed = urlparse(raw_url)
    path = parsed.path

    if "/resume/advanced" in path:
        return ""

    if "/resume/" in path:
        m = re.search(r"/resume/([^/?#]+)", path)
        if m:
            return f"https://hh.ru/resume/{m.group(1)}"

    if "resume" in parse_qs(parsed.query):
        resume_value = parse_qs(parsed.query).get("resume", [""])[0]
        if resume_value:
            return f"https://hh.ru/resume/{resume_value}"

    return raw_url


def resume_id_from_url(url: str) -> str:
    m = re.search(r"/resume/([^/?#]+)", url or "")
    return m.group(1) if m else ""


def is_excluded_resume_url(url: str) -> bool:
    lowered = (url or "").lower()
    excluded_tokens = [
        "suitable_resumes",
        "gifted",
        "related_resumes",
        "visitor",
        "viewer",
        "recommended",
        "recommendation",
        "similar_vacancies",
        "resume/advanced",
    ]
    return any(token in lowered for token in excluded_tokens)


def is_excluded_source(text: str) -> bool:
    lowered = (text or "").lower()
    excluded_tokens = [
        "gifted",
        "related_resumes",
        "suitable_resumes",
        "visitorcollection",
        "visitor_collection",
        "viewers",
        "viewer",
        "recommended",
        "recommendation",
        "similar_resumes",
        "rawenrichingdata",
    ]
    return any(token in lowered for token in excluded_tokens)


def save_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def body_text(page: Page) -> str:
    try:
        return page.locator("body").inner_text(timeout=3000)
    except Exception:
        return ""


# =========================
# PLAYWRIGHT УТИЛИТЫ
# =========================

def close_popups(page: Page) -> None:
    selectors = [
        'button[aria-label="Закрыть"]',
        'button[aria-label="Close"]',
        '[data-qa="bloko-modal-close"]',
        '[data-qa="close-popup"]',
        'button:has-text("Закрыть")',
        'button:has-text("Понятно")',
        'button:has-text("Хорошо")',
        'button:has-text("Не сейчас")',
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            count = min(loc.count(), 5)
            for i in range(count):
                try:
                    loc.nth(i).click(timeout=700)
                    page.wait_for_timeout(200)
                except Exception:
                    pass
        except Exception:
            pass


def wait_network(page: Page, timeout_ms: int = 6000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass


def auto_scroll(page: Page, rounds: int = 18, pause_ms: int = 1000) -> None:
    last_height = -1
    stable = 0
    for _ in range(rounds):
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            break
        page.wait_for_timeout(pause_ms)
        wait_network(page, 2500)
        try:
            new_height = page.evaluate("document.body.scrollHeight")
        except Exception:
            break
        if new_height == last_height:
            stable += 1
        else:
            stable = 0
            last_height = new_height
        if stable >= 2:
            break


def click_show_more(page: Page, max_clicks: int = 30) -> None:
    selectors = [
        'button:has-text("Показать ещё")',
        'button:has-text("Показать еще")',
        'a:has-text("Показать ещё")',
        'a:has-text("Показать еще")',
        'button:has-text("Ещё")',
        'button:has-text("Еще")',
        'button:has-text("Загрузить ещё")',
        'button:has-text("Загрузить еще")',
    ]
    for _ in range(max_clicks):
        clicked = False
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if loc.count() > 0:
                    loc.first.click(timeout=1200)
                    page.wait_for_timeout(900)
                    wait_network(page, 2500)
                    clicked = True
                    break
            except Exception:
                pass
        if not clicked:
            break


def click_show_phone(page: Page) -> None:
    selectors = [
        'button:has-text("Показать телефон")',
        'a:has-text("Показать телефон")',
        'span:has-text("Показать телефон")',
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            for i in range(min(loc.count(), 3)):
                try:
                    loc.nth(i).click(timeout=1200)
                    page.wait_for_timeout(500)
                except Exception:
                    pass
        except Exception:
            pass


def attach_payload_collector(page: Page) -> List[Dict[str, Any]]:
    payloads: List[Dict[str, Any]] = []

    def handle_response(response):
        try:
            content_type = (response.headers.get("content-type") or "").lower()
            if "application/json" not in content_type:
                return
            payloads.append({
                "url": response.url,
                "data": response.json(),
            })
        except Exception:
            pass

    page.on("response", handle_response)
    return payloads


# =========================
# СБОР ВАКАНСИЙ
# =========================

def extract_vacancies_from_page(page: Page) -> List[Dict[str, str]]:
    js = r'''
    () => {
        const result = [];
        const anchors = Array.from(document.querySelectorAll('a[href*="/employer/vacancyresponses?vacancyId="]'));

        function pickTitle(anchor) {
            const direct = (anchor.innerText || '').trim();
            if (direct && direct.length > 1 && !direct.includes('Отклики')) {
                return direct;
            }

            const row = anchor.closest('tr, article, section, li, div');
            if (!row) return direct;

            const candidates = Array.from(row.querySelectorAll('a, [title]'))
                .map(el => ((el.innerText || el.getAttribute('title') || '').trim()))
                .filter(Boolean)
                .filter(text => !text.includes('Отклики') && !text.includes('Просмотры') && !text.includes('Показы'));

            candidates.sort((a, b) => b.length - a.length);
            return candidates[0] || direct;
        }

        for (const a of anchors) {
            const href = a.href || '';
            const match = href.match(/vacancyId=(\d+)/);
            if (!match) continue;
            result.push({
                vacancy_id: match[1],
                vacancy_title: pickTitle(a),
                responses_url: href,
            });
        }

        const uniq = {};
        for (const item of result) {
            const prev = uniq[item.vacancy_id];
            if (!prev || ((item.vacancy_title || '').length > (prev.vacancy_title || '').length)) {
                uniq[item.vacancy_id] = item;
            }
        }
        return Object.values(uniq);
    }
    '''
    try:
        items = page.evaluate(js)
    except Exception:
        items = []

    clean: List[Dict[str, str]] = []
    seen = set()
    for item in items:
        vacancy_id = text_or_empty(item.get("vacancy_id"))
        if not vacancy_id or vacancy_id in seen:
            continue
        seen.add(vacancy_id)
        clean.append({
            "vacancy_id": vacancy_id,
            "vacancy_title": text_or_empty(item.get("vacancy_title")),
            "responses_url": text_or_empty(item.get("responses_url")) or RESPONSES_URL_TEMPLATE.format(vacancy_id=vacancy_id),
        })
    return clean


# =========================
# ПОИСК РЕАЛЬНЫХ ОТКЛИКОВ НА СТРАНИЦЕ ВАКАНСИИ
# =========================

def parse_response_count(page_text: str) -> int:
    patterns = [
        r'"id":"response".*?"collectionItemCount":\{(?:"newOrUpdated":\d+,)?"total":(\d+)',
        r'"name":"response".*?"total":(\d+)',
    ]
    for pat in patterns:
        m = re.search(pat, page_text, flags=re.S)
        if m:
            return int(m.group(1))
    return 0


def looks_like_resume_object(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False

    attrs = obj.get("_attributes") or {}
    has_resume_id = bool(attrs.get("id") or obj.get("id") or obj.get("resumeId"))
    has_resume_hash = bool(attrs.get("hash") or obj.get("hash"))
    has_title = bool(obj.get("title"))
    has_name = bool(obj.get("firstName") or obj.get("lastName") or obj.get("fullName") or obj.get("fio"))
    has_contacts = bool(obj.get("phone") or obj.get("email"))
    has_geo = bool(obj.get("area") or obj.get("relocation") or obj.get("businessTripReadiness"))

    return (has_resume_id or has_resume_hash) and (has_title or has_name or has_contacts or has_geo)


def score_resume_object(obj: Dict[str, Any]) -> int:
    score = 0
    attrs = obj.get("_attributes") or {}
    if attrs.get("id") or obj.get("id") or obj.get("resumeId"):
        score += 3
    if attrs.get("hash") or obj.get("hash"):
        score += 3
    if obj.get("title"):
        score += 2
    if obj.get("firstName") or obj.get("lastName") or obj.get("fullName"):
        score += 3
    if obj.get("phone"):
        score += 2
    if obj.get("email"):
        score += 1
    if obj.get("area"):
        score += 1
    if obj.get("professionExperience"):
        score += 3
    if obj.get("driverLicenseTypes"):
        score += 1
    return score


def walk_objects(value: Any, path: str = "root") -> Iterable[Tuple[str, Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk_objects(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from walk_objects(item, f"{path}[{index}]")


def build_resume_link_from_object(obj: Dict[str, Any]) -> str:
    attrs = obj.get("_attributes") or {}
    hash_value = attrs.get("hash") or obj.get("hash")
    resume_id = attrs.get("id") or obj.get("id") or obj.get("resumeId")
    if hash_value:
        return f"https://hh.ru/resume/{hash_value}"
    if resume_id:
        return f"https://hh.ru/resume/{resume_id}"
    return ""


def extract_resume_entries_from_payloads(payloads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    seen = set()

    for payload in payloads:
        url = text_or_empty(payload.get("url"))
        data = payload.get("data")
        if data is None:
            continue
        if is_excluded_source(url):
            continue

        for path, obj in walk_objects(data, path=url):
            if not looks_like_resume_object(obj):
                continue
            if is_excluded_source(path):
                continue

            resume_link = normalize_resume_url(build_resume_link_from_object(obj))
            if not resume_link:
                continue
            if is_excluded_resume_url(resume_link):
                continue

            key = (resume_link, path)
            if key in seen:
                continue
            seen.add(key)

            found.append({
                "resume_link": resume_link,
                "resume_id": text_or_empty((obj.get("_attributes") or {}).get("id") or obj.get("id") or obj.get("resumeId")),
                "fio": " ".join(filter(None, [
                    text_from_value(obj.get("lastName")),
                    text_from_value(obj.get("firstName")),
                    text_from_value(obj.get("middleName")),
                ])).strip() or text_from_value(obj.get("fullName")) or text_from_value(obj.get("fio")),
                "age": text_from_value(obj.get("age")),
                "resume_title": text_from_value(obj.get("title")),
                "source": "response_payload",
                "source_path": path,
                "score": score_resume_object(obj),
            })

    found.sort(key=lambda x: x.get("score", 0), reverse=True)
    return found


def extract_resume_entries_from_page_links(page: Page) -> List[Dict[str, Any]]:
    js = r'''
    () => {
        const out = [];
        const anchors = Array.from(document.querySelectorAll('a[href*="/resume/"], a[href*="/applicant/resumes/view?resume="]'));

        function blockText(a) {
            const row = a.closest('tr, article, section, li, div');
            if (!row) return '';
            return (row.innerText || '').replace(/\u00a0/g, ' ').trim();
        }

        for (const a of anchors) {
            const href = a.href || '';
            if (!href) continue;
            const text = (a.innerText || '').trim();
            out.push({
                href,
                text,
                block_text: blockText(a),
            });
        }
        return out;
    }
    '''
    try:
        rows = page.evaluate(js)
    except Exception:
        rows = []

    items: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        href = normalize_resume_url(text_or_empty(row.get("href")))
        if not href or href in seen:
            continue
        seen.add(href)
        if is_excluded_resume_url(href):
            continue

        text = text_or_empty(row.get("text"))
        block_text = text_or_empty(row.get("block_text"))
        name_match = re.search(r"([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)", block_text)
        age_match = re.search(r",\s*(\d{1,2})\s*(?:год|года|лет)", block_text)

        items.append({
            "resume_link": href,
            "resume_id": resume_id_from_url(href),
            "fio": name_match.group(1).strip() if name_match else "",
            "age": age_match.group(1) if age_match else "",
            "resume_title": text,
            "source": "page_link",
            "source_path": "page_link",
            "score": 1,
        })
    return items


def dedupe_resume_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        resume_link = entry.get("resume_link") or ""
        if not resume_link:
            continue
        prev = best.get(resume_link)
        if not prev or entry.get("score", 0) > prev.get("score", 0):
            best[resume_link] = entry
        else:
            for key, value in entry.items():
                if not prev.get(key) and value:
                    prev[key] = value
    return list(best.values())


def collect_responses_for_vacancy(page: Page, vacancy: Dict[str, str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    vacancy_id = vacancy["vacancy_id"]
    vacancy_title = vacancy.get("vacancy_title", "")
    responses_url = vacancy.get("responses_url") or RESPONSES_URL_TEMPLATE.format(vacancy_id=vacancy_id)

    payloads = attach_payload_collector(page)
    page.goto(responses_url, wait_until="domcontentloaded")
    wait_network(page)
    close_popups(page)
    auto_scroll(page)
    click_show_more(page)
    auto_scroll(page, rounds=8, pause_ms=700)
    close_popups(page)
    wait_network(page)

    html = page.content()
    text = body_text(page)
    response_count = parse_response_count(html)

    page_entries = extract_resume_entries_from_page_links(page)
    payload_entries = extract_resume_entries_from_payloads(payloads)
    entries = dedupe_resume_entries(page_entries + payload_entries)

    if MAX_RESUMES_PER_VACANCY is not None:
        entries = entries[:MAX_RESUMES_PER_VACANCY]

    vacancy_debug_dir = DEBUG_DIR / f"vacancy_{vacancy_id}_{safe_filename(vacancy_title)}"
    ensure_dir(vacancy_debug_dir)
    save_text(vacancy_debug_dir / "page.html", html)
    save_text(vacancy_debug_dir / "page.txt", text)
    save_json(vacancy_debug_dir / "payloads.json", payloads)
    save_json(vacancy_debug_dir / "resume_entries.json", entries)
    try:
        page.screenshot(path=str(vacancy_debug_dir / "page.png"), full_page=True)
    except Exception:
        pass

    summary = {
        "vacancy_id": vacancy_id,
        "vacancy_title": vacancy_title,
        "responses_url": responses_url,
        "responses_count_on_page": response_count,
        "resume_links_found": len(entries),
        "error": "",
    }
    return entries, summary


# =========================
# ПАРСИНГ СТРАНИЦЫ РЕЗЮМЕ
# =========================

def phone_from_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        phones = []
        for item in value:
            p = phone_from_value(item)
            if p:
                phones.append(p)
        return ", ".join(dict.fromkeys(phones))
    if isinstance(value, dict):
        for key in ("formatted", "raw", "value", "string"):
            if key in value and value[key]:
                return text_or_empty(value[key])
        return ""
    text = text_or_empty(value)
    return text


def email_from_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        emails = []
        for item in value:
            e = email_from_value(item)
            if e:
                emails.append(e)
        return ", ".join(dict.fromkeys(emails))
    if isinstance(value, dict):
        for key in ("value", "email", "string"):
            if key in value and value[key]:
                return text_or_empty(value[key])
        return ""
    return text_or_empty(value)


def list_to_text(values: Any, key_hints: Iterable[str] = ("string", "trl", "formatted", "text", "name", "value")) -> str:
    if not values:
        return ""
    if not isinstance(values, list):
        return text_from_value(values, key_hints)
    result = []
    for item in values:
        val = text_from_value(item, key_hints)
        if val:
            result.append(val)
    return ", ".join(dict.fromkeys(result))


def format_total_experience(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, list) and value:
        value = value[0]
    if isinstance(value, dict):
        years = value.get("years")
        months = value.get("months")
        if years is not None or months is not None:
            return f"{years or 0} г {months or 0} мес"
        if value.get("string"):
            return text_or_empty(value.get("string"))
    text = text_from_value(value)
    if text.isdigit():
        total = int(text)
        return f"{total // 12} г {total % 12} мес"
    return text


def get_last_experience(resume_obj: Dict[str, Any]) -> Tuple[str, str, str]:
    sections = resume_obj.get("professionExperience") or resume_obj.get("professionalExperience") or []
    if not isinstance(sections, list):
        return "", "", ""
    for section in sections:
        experiences = section.get("experience") or section.get("items") or []
        if not isinstance(experiences, list):
            continue
        for item in experiences:
            company = text_from_value(item.get("company"))
            position = text_from_value(item.get("position"))
            period = ""
            if item.get("start") or item.get("end"):
                period = f"{text_from_value(item.get('start'))} — {text_from_value(item.get('end'))}".strip(" —")
            elif item.get("dateRange"):
                period = text_from_value(item.get("dateRange"))
            if company or position or period:
                return company, position, period
    return "", "", ""


def extract_other_contacts(resume_obj: Dict[str, Any], page_text: str) -> str:
    raw_json = json.dumps(resume_obj.get("otherCommunicationMethods") or [], ensure_ascii=False).lower()
    raw_text = (page_text or "").lower()
    found = []
    for name in ["whatsapp", "telegram", "viber"]:
        if name in raw_json or name in raw_text:
            found.append(name)
    return ", ".join(found)


def fio_from_resume_obj(resume_obj: Dict[str, Any]) -> str:
    parts = [
        text_from_value(resume_obj.get("lastName")),
        text_from_value(resume_obj.get("firstName")),
        text_from_value(resume_obj.get("middleName")),
    ]
    full = " ".join([p for p in parts if p]).strip()
    if full:
        return full
    return text_from_value(resume_obj.get("fullName")) or text_from_value(resume_obj.get("fio"))


def score_full_resume_obj(obj: Dict[str, Any]) -> int:
    score = score_resume_object(obj)
    if obj.get("professionExperience"):
        score += 4
    if obj.get("driverLicenseTypes"):
        score += 2
    if obj.get("otherCommunicationMethods"):
        score += 2
    if obj.get("businessTripReadiness"):
        score += 1
    if obj.get("relocation"):
        score += 1
    return score


def choose_best_resume_object(payloads: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], str]:
    best_obj = None
    best_path = ""
    best_score = -1

    for payload in payloads:
        url = text_or_empty(payload.get("url"))
        data = payload.get("data")
        if data is None:
            continue
        for path, obj in walk_objects(data, path=url):
            if not looks_like_resume_object(obj):
                continue
            score = score_full_resume_obj(obj)
            if score > best_score:
                best_obj = obj
                best_path = path
                best_score = score
    return best_obj, best_path


def parse_resume_from_payloads(resume_obj: Dict[str, Any], page_text: str) -> Dict[str, Any]:
    company, position, period = get_last_experience(resume_obj)
    attrs = resume_obj.get("_attributes") or {}
    resume_link = normalize_resume_url(build_resume_link_from_object(resume_obj))

    return {
        "resume_id": text_or_empty(attrs.get("id") or resume_obj.get("id") or resume_obj.get("resumeId")) or resume_id_from_url(resume_link),
        "fio": fio_from_resume_obj(resume_obj),
        "age": text_from_value(resume_obj.get("age")),
        "resume_title": text_from_value(resume_obj.get("title")),
        "city": text_from_value(resume_obj.get("area"), ("trl", "name", "text", "string", "value")),
        "phone": phone_from_value(resume_obj.get("phone")),
        "email": email_from_value(resume_obj.get("email")),
        "experience_total": format_total_experience(resume_obj.get("totalExperience")),
        "specializations": list_to_text(resume_obj.get("specialization") or resume_obj.get("professionalRoles") or resume_obj.get("specializations")),
        "last_company": company,
        "last_position": position,
        "last_period": period,
        "driver_licenses": list_to_text(resume_obj.get("driverLicenseTypes")),
        "has_vehicle": normalize_bool_like(resume_obj.get("hasVehicle")),
        "business_trip_readiness": text_from_value(resume_obj.get("businessTripReadiness")),
        "relocation": text_from_value(resume_obj.get("relocation")),
        "other_contacts": extract_other_contacts(resume_obj, page_text),
        "resume_link": resume_link,
    }


def parse_resume_from_text(page_text: str, resume_url: str) -> Dict[str, Any]:
    lines = [line.strip() for line in page_text.splitlines() if line.strip()]
    joined = "\n".join(lines)

    fio = ""
    age = ""
    for line in lines[:20]:
        m = re.match(r"^([А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?),\s*(\d{1,2})\s*(?:год|года|лет)", line)
        if m:
            fio = m.group(1).strip()
            age = m.group(2)
            break

    if not fio:
        for line in lines[:20]:
            if re.match(r"^[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?$", line):
                fio = line
                break

    city = ""
    city_patterns = [
        r"(?:Город проживания|Проживает|Место жительства)\s*:?\s*([^\n]+)",
        r"Где жив[её]т\s*\n([^\n]+)",
    ]
    for pat in city_patterns:
        m = re.search(pat, joined, flags=re.I)
        if m:
            city = m.group(1).replace("На карте", "").strip()
            break

    phone_match = re.search(r"\+7[\d\s\-()]{9,}", joined)
    email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", joined)

    exp_total = ""
    m = re.search(r"(?:Общий опыт|Опыт работы)\s*\n([^\n]+)", joined, flags=re.I)
    if m:
        exp_total = m.group(1).strip()

    last_company = ""
    last_position = ""
    m = re.search(r"Последнее место работы\s*\n([^\n]+)\n([^\n]+)", joined, flags=re.I)
    if m:
        last_company = m.group(1).strip()
        last_position = m.group(2).strip()

    driver_licenses = ""
    m = re.search(r"(?:Права категории|Водительские права|Опыт вождения)\s*\n([^\n]+)", joined, flags=re.I)
    if m:
        driver_licenses = m.group(1).strip()

    other_contacts = []
    lower = joined.lower()
    for name in ["telegram", "whatsapp", "viber"]:
        if name in lower:
            other_contacts.append(name)

    resume_title = ""
    for line in lines[:30]:
        if line == fio or line.startswith(fio + ","):
            continue
        if 2 <= len(line) <= 120 and not re.search(r"\+7|@", line):
            resume_title = line
            break

    return {
        "resume_id": resume_id_from_url(resume_url),
        "fio": fio,
        "age": age,
        "resume_title": resume_title,
        "city": city,
        "phone": phone_match.group(0).strip() if phone_match else "",
        "email": email_match.group(0).strip() if email_match else "",
        "experience_total": exp_total,
        "specializations": "",
        "last_company": last_company,
        "last_position": last_position,
        "last_period": "",
        "driver_licenses": driver_licenses,
        "has_vehicle": "",
        "business_trip_readiness": "",
        "relocation": "",
        "other_contacts": ", ".join(other_contacts),
        "resume_link": normalize_resume_url(resume_url),
    }


def merge_dicts(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in extra.items():
        if value not in (None, "") and not result.get(key):
            result[key] = value
    return result


def open_and_parse_resume(context, vacancy: Dict[str, str], list_entry: Dict[str, Any], index_in_vacancy: int) -> Dict[str, Any]:
    vacancy_id = vacancy["vacancy_id"]
    vacancy_title = vacancy.get("vacancy_title", "")
    resume_url = normalize_resume_url(text_or_empty(list_entry.get("resume_link")))

    result: Dict[str, Any] = {
        "vacancy_id": vacancy_id,
        "vacancy_title": vacancy_title,
        "page_url": vacancy.get("responses_url") or RESPONSES_URL_TEMPLATE.format(vacancy_id=vacancy_id),
        "resume_id": text_or_empty(list_entry.get("resume_id")) or resume_id_from_url(resume_url),
        "fio": text_or_empty(list_entry.get("fio")),
        "age": text_or_empty(list_entry.get("age")),
        "resume_title": text_or_empty(list_entry.get("resume_title")),
        "city": "",
        "phone": "",
        "email": "",
        "experience_total": "",
        "specializations": "",
        "last_company": "",
        "last_position": "",
        "last_period": "",
        "driver_licenses": "",
        "has_vehicle": "",
        "business_trip_readiness": "",
        "relocation": "",
        "other_contacts": "",
        "resume_link": resume_url,
        "source": text_or_empty(list_entry.get("source")) or "response_page",
        "source_path": text_or_empty(list_entry.get("source_path")) or "response_page",
    }

    if not resume_url:
        result["source"] = "error"
        result["source_path"] = "no_resume_url"
        return result

    page = context.new_page()
    payloads = attach_payload_collector(page)
    try:
        page.goto(resume_url, wait_until="domcontentloaded")
        wait_network(page, 7000)
        close_popups(page)
        if CLICK_SHOW_PHONE_ON_RESUME:
            click_show_phone(page)
        wait_network(page, 3000)

        html = page.content()
        text = body_text(page)
        best_resume_obj, best_path = choose_best_resume_object(payloads)

        if best_resume_obj is not None:
            payload_data = parse_resume_from_payloads(best_resume_obj, text)
            result = merge_dicts(result, payload_data)
            result["source"] = "resume_page_payload"
            result["source_path"] = best_path

        text_data = parse_resume_from_text(text, resume_url)
        result = merge_dicts(result, text_data)

        if not result.get("resume_link"):
            result["resume_link"] = normalize_resume_url(page.url)
        if not result.get("resume_id"):
            result["resume_id"] = resume_id_from_url(result.get("resume_link", "") or page.url)

        resume_debug_dir = DEBUG_DIR / f"vacancy_{vacancy_id}_{safe_filename(vacancy_title)}" / f"resume_{index_in_vacancy:04d}_{safe_filename(result.get('resume_id') or result.get('fio') or 'resume')}"
        ensure_dir(resume_debug_dir)
        save_text(resume_debug_dir / "resume.html", html)
        save_text(resume_debug_dir / "resume.txt", text)
        save_json(resume_debug_dir / "resume_payloads.json", payloads)
        save_json(resume_debug_dir / "parsed_row.json", result)
        try:
            page.screenshot(path=str(resume_debug_dir / "resume.png"), full_page=True)
        except Exception:
            pass

    except Exception as e:
        result["source"] = "error"
        result["source_path"] = f"resume_open_error: {e}"
    finally:
        try:
            page.close()
        except Exception:
            pass

    return result


# =========================
# СБОР ИТОГОВЫХ СТРОК
# =========================

def build_final_rows(vacancies: List[Dict[str, str]], page, context) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    all_rows: List[Dict[str, Any]] = []
    vacancies_summary: List[Dict[str, Any]] = []

    for vacancy_index, vacancy in enumerate(vacancies, start=1):
        vacancy_id = vacancy["vacancy_id"]
        vacancy_title = vacancy.get("vacancy_title", "")
        print(f"\n[{vacancy_index}/{len(vacancies)}] Вакансия {vacancy_id}: {vacancy_title}")

        try:
            entries, summary = collect_responses_for_vacancy(page, vacancy)
        except Exception as e:
            summary = {
                "vacancy_id": vacancy_id,
                "vacancy_title": vacancy_title,
                "responses_url": vacancy.get("responses_url", ""),
                "responses_count_on_page": 0,
                "resume_links_found": 0,
                "error": str(e),
            }
            vacancies_summary.append(summary)
            print(f"  Ошибка на странице откликов: {e}")
            continue

        print(f"  Найдено ссылок на резюме: {len(entries)}")

        vacancy_rows: List[Dict[str, Any]] = []
        for idx, entry in enumerate(entries, start=1):
            row = open_and_parse_resume(context, vacancy, entry, idx)
            vacancy_rows.append(row)
            print(f"    [{idx}/{len(entries)}] {row.get('fio') or row.get('resume_title') or row.get('resume_id')}")

        all_rows.extend(vacancy_rows)
        summary["resumes_opened"] = len(vacancy_rows)
        vacancies_summary.append(summary)

        save_json(
            DEBUG_DIR / f"vacancy_{vacancy_id}_{safe_filename(vacancy_title)}" / "parsed_rows.json",
            vacancy_rows,
        )

    best_rows: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in all_rows:
        key = (
            text_or_empty(row.get("vacancy_id")),
            text_or_empty(row.get("resume_link")) or text_or_empty(row.get("resume_id")) or text_or_empty(row.get("fio")),
        )
        prev = best_rows.get(key)
        current_score = sum(bool(row.get(col)) for col in [
            "fio", "age", "resume_title", "city", "phone", "email", "experience_total",
            "last_company", "last_position", "driver_licenses", "resume_link"
        ])
        if prev is None:
            best_rows[key] = row
        else:
            prev_score = sum(bool(prev.get(col)) for col in [
                "fio", "age", "resume_title", "city", "phone", "email", "experience_total",
                "last_company", "last_position", "driver_licenses", "resume_link"
            ])
            if current_score > prev_score:
                best_rows[key] = row

    final_rows = list(best_rows.values())
    final_rows.sort(
        key=lambda x: (
            text_or_empty(x.get("vacancy_title")),
            text_or_empty(x.get("fio")),
            text_or_empty(x.get("resume_title")),
        )
    )

    return final_rows, vacancies_summary


def collect_hh_rows() -> List[Dict[str, Any]]:
    ensure_dir(DEBUG_DIR)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            viewport={"width": 1500, "height": 980},
            locale="ru-RU",
        )

        try:
            page = context.new_page()
            page.goto(VACANCIES_URL, wait_until="domcontentloaded")

            print("\nОткрыл HH.")
            print("Сейчас вручную:")
            print("1. войдите в аккаунт")
            print("2. введите код из почты")
            print("3. дождитесь страницы 'Мои вакансии'")
            print("4. потом вернитесь в консоль")
            input("\nНажмите Enter, когда страница вакансий уже открыта... ")

            wait_network(page)
            close_popups(page)
            auto_scroll(page)
            click_show_more(page)
            auto_scroll(page, rounds=10, pause_ms=700)
            close_popups(page)

            vacancies = extract_vacancies_from_page(page)
            if not vacancies:
                raise RuntimeError("Не удалось найти вакансии на странице 'Мои вакансии'.")

            if MAX_VACANCIES is not None:
                vacancies = vacancies[:MAX_VACANCIES]

            print(f"Найдено вакансий: {len(vacancies)}")
            save_json(DEBUG_DIR / "vacancies.json", vacancies)

            final_rows, vacancies_summary = build_final_rows(vacancies, page, context)

            # Сохраняем отладочные/промежуточные результаты тоже
            save_json(Path(OUT_RESPONSES_JSON), final_rows)
            save_json(Path(OUT_VACANCIES_JSON), vacancies_summary)

            print("\nСбор строк завершен.")
            print(f"Всего строк откликов: {len(final_rows)}")

            return final_rows

        finally:
            try:
                context.close()
            except Exception:
                pass


def save_results_to_files(rows: List[Dict[str, Any]], vacancies_summary: List[Dict[str, Any]]) -> None:
    df_rows = pd.DataFrame(rows)
    df_vacancies = pd.DataFrame(vacancies_summary)

    df_rows.to_excel(OUT_RESPONSES_XLSX, index=False)
    df_vacancies.to_excel(OUT_VACANCIES_XLSX, index=False)
    save_json(Path(OUT_RESPONSES_JSON), rows)
    save_json(Path(OUT_VACANCIES_JSON), vacancies_summary)

    print("\nГотово.")
    print(f"Файл с откликами: {OUT_RESPONSES_XLSX}")
    print(f"Сводка по вакансиям: {OUT_VACANCIES_XLSX}")
    print(f"Всего строк откликов: {len(df_rows)}")


def main() -> None:
    ensure_dir(DEBUG_DIR)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            viewport={"width": 1500, "height": 980},
            locale="ru-RU",
        )

        try:
            page = context.new_page()
            page.goto(VACANCIES_URL, wait_until="domcontentloaded")

            print("\nОткрыл HH.")
            print("Сейчас вручную:")
            print("1. войдите в аккаунт")
            print("2. введите код из почты")
            print("3. дождитесь страницы 'Мои вакансии'")
            print("4. потом вернитесь в консоль")
            input("\nНажмите Enter, когда страница вакансий уже открыта... ")

            wait_network(page)
            close_popups(page)
            auto_scroll(page)
            click_show_more(page)
            auto_scroll(page, rounds=10, pause_ms=700)
            close_popups(page)

            vacancies = extract_vacancies_from_page(page)
            if not vacancies:
                raise RuntimeError("Не удалось найти вакансии на странице 'Мои вакансии'.")

            if MAX_VACANCIES is not None:
                vacancies = vacancies[:MAX_VACANCIES]

            print(f"Найдено вакансий: {len(vacancies)}")
            save_json(DEBUG_DIR / "vacancies.json", vacancies)

            final_rows, vacancies_summary = build_final_rows(vacancies, page, context)
            save_results_to_files(final_rows, vacancies_summary)

            input("\nНажмите Enter для закрытия браузера... ")

        finally:
            try:
                context.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()