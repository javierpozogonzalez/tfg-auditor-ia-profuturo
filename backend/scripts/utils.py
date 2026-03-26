import re
from collections import defaultdict
from datetime import date
MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]
def add_months(base: date, months: int) -> date:
    month_index = base.month - 1 + months
    year = base.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)
def format_month_year_es(value: date) -> str:
    return f"{MONTHS_ES[value.month - 1].capitalize()} {value.year}"
def get_reporting_periods() -> tuple[str, str, str]:
    today = date.today()
    report_month = add_months(today, 1)
    next_review_month = add_months(report_month, 1)
    return (
        format_month_year_es(report_month),
        format_month_year_es(today),
        format_month_year_es(next_review_month),
    )
def is_noise_record(topic: str, content: str) -> bool:
    joined = f"{topic} {content}".strip().lower()
    if not joined:
        return False
    return bool(re.search(r"\b(prueba|test|testing|demo|hilo de prueba|qa|sandbox)\b", joined))
def to_date_key(raw_date) -> str:
    if raw_date is None:
        return "sin-fecha"
    try:
        year = getattr(raw_date, "year", None)
        month = getattr(raw_date, "month", None)
        if year and month:
            return f"{int(year):04d}-{int(month):02d}"
    except Exception:
        pass
    value = str(raw_date)
    if len(value) >= 7 and value[4] == "-":
        return value[:7]
    return "sin-fecha"
def apply_current_report_dates(text: str) -> str:
    if not text:
        return text
    period_label, generation_label, next_review_label = get_reporting_periods()
    normalized = text
    replacements = {
        r"(?im)^\s*(Mes\s+de\s+referencia\s*:\s*).*$": rf"\1{period_label}",
        r"(?im)^\s*(Per[ií]odo\s+de\s+an[aá]lisis\s*:\s*).*$": rf"\1{period_label}",
        r"(?im)^\s*(Per[ií]odo\s*:\s*).*$": rf"\1{period_label}",
        r"(?im)^\s*(Fecha\s+de\s+generaci[oó]n\s*:\s*).*$": rf"\1{generation_label}",
        r"(?im)^\s*(Pr[oó]xima\s+revisi[oó]n\s*:\s*).*$": rf"\1{next_review_label}",
    }
    for pattern, replacement in replacements.items():
        normalized = re.sub(pattern, replacement, normalized)
    return normalized
