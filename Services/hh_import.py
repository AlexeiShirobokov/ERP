from django.utils import timezone

from personnel.models import ResumeCandidate


def row_to_birth_year(row: dict):
    age = str(row.get('age') or '').strip()
    if not age.isdigit():
        return None

    age_int = int(age)
    current_year = timezone.now().year

    if 14 <= age_int <= 90:
        return current_year - age_int

    return None


def row_to_contacts(row: dict) -> str:
    parts = [
        str(row.get('phone') or '').strip(),
        str(row.get('email') or '').strip(),
    ]
    parts = [p for p in parts if p]
    return ', '.join(parts)


def row_to_comment(row: dict) -> str:
    parts = [
        f"Город: {row.get('city')}" if row.get('city') else '',
        f"Опыт: {row.get('experience_total')}" if row.get('experience_total') else '',
        f"Последнее место работы: {row.get('last_company')}" if row.get('last_company') else '',
        f"Последняя должность: {row.get('last_position')}" if row.get('last_position') else '',
        f"Период: {row.get('last_period')}" if row.get('last_period') else '',
        f"Командировки: {row.get('business_trip_readiness')}" if row.get('business_trip_readiness') else '',
        f"Переезд: {row.get('relocation')}" if row.get('relocation') else '',
        f"Другие контакты: {row.get('other_contacts')}" if row.get('other_contacts') else '',
    ]
    return '\n'.join([p for p in parts if p])


def row_to_qualification(row: dict) -> str:
    parts = [
        f"Специализация: {row.get('specializations')}" if row.get('specializations') else '',
        f"Водительские права: {row.get('driver_licenses')}" if row.get('driver_licenses') else '',
        f"Наличие авто: {row.get('has_vehicle')}" if row.get('has_vehicle') else '',
        f"Название резюме: {row.get('resume_title')}" if row.get('resume_title') else '',
    ]
    return '\n'.join([p for p in parts if p])


def build_note(row: dict) -> str:
    parts = [
        "Импортировано из HH",
        f"Источник: {row.get('source')}" if row.get('source') else '',
        f"Путь: {row.get('source_path')}" if row.get('source_path') else '',
        f"Ссылка на резюме: {row.get('resume_link')}" if row.get('resume_link') else '',
        f"Вакансия HH ID: {row.get('vacancy_id')}" if row.get('vacancy_id') else '',
    ]
    return '\n'.join([p for p in parts if p])


def set_if_value(obj, field_name: str, value):
    if value not in (None, ''):
        setattr(obj, field_name, value)


def import_hh_rows(rows: list[dict]) -> tuple[int, int]:
    created_count = 0
    updated_count = 0

    for row in rows:
        hh_resume_id = str(row.get('resume_id') or '').strip()
        hh_resume_link = str(row.get('resume_link') or '').strip()

        candidate = None

        if hh_resume_id:
            candidate = ResumeCandidate.objects.filter(hh_resume_id=hh_resume_id).first()

        if candidate is None and hh_resume_link:
            candidate = ResumeCandidate.objects.filter(hh_resume_link=hh_resume_link).first()

        full_name = str(row.get('fio') or row.get('resume_title') or 'Без имени').strip()
        hh_vacancy = str(row.get('vacancy_title') or '').strip()
        position = str(row.get('resume_title') or '').strip()
        contacts = row_to_contacts(row)
        comment = row_to_comment(row)
        qualification = row_to_qualification(row)
        birth_year = row_to_birth_year(row)
        note = build_note(row)
        hh_vacancy_id = str(row.get('vacancy_id') or '').strip()
        hh_source = str(row.get('source') or '').strip()

        if candidate is None:
            ResumeCandidate.objects.create(
                full_name=full_name,
                hh_vacancy=hh_vacancy,
                position=position,
                contacts=contacts,
                comment=comment,
                birth_year=birth_year,
                qualification=qualification,
                note=note,
                stage='response',
                hh_resume_id=hh_resume_id,
                hh_resume_link=hh_resume_link,
                hh_vacancy_id=hh_vacancy_id,
                hh_source=hh_source,
                hh_last_sync_at=timezone.now(),
            )
            created_count += 1
            continue

        set_if_value(candidate, 'full_name', full_name)
        set_if_value(candidate, 'hh_vacancy', hh_vacancy)
        set_if_value(candidate, 'position', position)
        set_if_value(candidate, 'contacts', contacts)
        set_if_value(candidate, 'comment', comment)
        set_if_value(candidate, 'birth_year', birth_year)
        set_if_value(candidate, 'qualification', qualification)

        if not candidate.note and note:
            candidate.note = note

        set_if_value(candidate, 'hh_resume_id', hh_resume_id)
        set_if_value(candidate, 'hh_resume_link', hh_resume_link)
        set_if_value(candidate, 'hh_vacancy_id', hh_vacancy_id)
        set_if_value(candidate, 'hh_source', hh_source)

        candidate.hh_last_sync_at = timezone.now()
        candidate.save()
        updated_count += 1

    return created_count, updated_count