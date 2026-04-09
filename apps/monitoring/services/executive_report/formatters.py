from django.utils import timezone

from .constants import METRIC_LABELS, SOURCE_LABELS, STATUS_LABELS


def to_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def format_number(value, digits: int = 2, fallback: str = "—") -> str:
    numeric = to_float(value)
    if numeric is None:
        return fallback
    text = f"{numeric:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def format_int(value, fallback: str = "—") -> str:
    numeric = to_float(value)
    if numeric is None:
        return fallback
    return str(int(round(numeric)))


def format_datetime(value, fallback: str = "—") -> str:
    if value is None:
        return fallback
    localized = timezone.localtime(value)
    return localized.strftime("%d.%m.%Y %H:%M")


def format_metric_name(value: str | None) -> str:
    if not value:
        return "—"
    return METRIC_LABELS.get(value, value.replace("_", " "))


def format_metric_list(values: list[str], limit: int = 4) -> str:
    if not values:
        return "—"
    labels = [format_metric_name(item) for item in values[:limit]]
    if len(values) > limit:
        labels.append("и др.")
    return ", ".join(labels)


def format_source_name(value: str | None) -> str:
    if not value:
        return "—"
    return SOURCE_LABELS.get(value, value)


def format_status(value: str | None) -> str:
    if not value:
        return "—"
    return STATUS_LABELS.get(value, value)


def format_metric_source(value: str | None) -> str:
    if value == "backtest":
        return "проверка на исторических данных"
    if value == "training":
        return "оценка на этапе обучения"
    return "—"
