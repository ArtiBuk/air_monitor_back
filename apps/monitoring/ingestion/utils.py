from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from ..config import DEFAULT_HEADERS, REQUEST_TIMEOUT, USE_FAKE_USER_AGENT
from .types import Observation

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

try:
    from fake_useragent import UserAgent
except ImportError:
    UserAgent = None


_SESSION: requests.Session | None = None


def get_http_session() -> requests.Session:
    if requests is None:
        raise RuntimeError("requests is not installed.")

    global _SESSION

    if _SESSION is not None:
        return _SESSION

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    user_agent = None
    if USE_FAKE_USER_AGENT and UserAgent is not None:
        try:
            user_agent = UserAgent().chrome
        except Exception:
            user_agent = None

    if not user_agent:
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/133.0.0.0 Safari/537.36"
        )

    session.headers["User-Agent"] = user_agent
    _SESSION = session
    return _SESSION


def safe_float(value: Any):
    try:
        if value is None or value == "":
            return None
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def http_get_json(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> dict:
    session = get_http_session()
    resp = session.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def http_get_text(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> str:
    session = get_http_session()
    resp = session.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def normalize_metric(metric: str | None) -> str | None:
    if metric is None:
        return None

    metric = metric.strip().lower()

    aliases = {
        "pm2.5": "pm25",
        "pm2,5": "pm25",
        "pm_25": "pm25",
        "pm25": "pm25",
        "pm10": "pm10",
        "no2": "no2",
        "so2": "so2",
        "o3": "o3",
        "co": "co",
        "aqi": "aqi",
        "plume_index": "plume_index",
    }
    return aliases.get(metric, metric)


def normalize_unit(metric: str | None, unit: str | None) -> str | None:
    metric = normalize_metric(metric)

    if metric in {"aqi", "plume_index"}:
        return "index"

    if unit is None:
        if metric in {"pm25", "pm10", "no2", "so2", "o3", "co"}:
            return "µg/m3"
        return None

    cleaned = unit.strip()
    replacements = {
        "µg/m³": "µg/m3",
        "ug/m3": "µg/m3",
        "мкг/м3": "µg/m3",
        "мкг/м³": "µg/m3",
    }
    return replacements.get(cleaned, cleaned)


def normalize_timestamp_to_utc_str(value: str | None) -> str | None:
    if not value:
        return None

    raw = value.strip()

    if raw.endswith("Z"):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except ValueError:
            return raw

    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except ValueError:
        return raw


def floor_timestamp_to_hour(value: str | None) -> str | None:
    normalized = normalize_timestamp_to_utc_str(value)
    if not normalized:
        return None

    raw = normalized.replace("Z", "+00:00")
    dt = datetime.fromisoformat(raw)
    dt = dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def floor_timestamp_to_window(value: str | None, window_hours: int = 3) -> str | None:
    normalized = normalize_timestamp_to_utc_str(value)
    if not normalized:
        return None

    if window_hours <= 0:
        raise ValueError("window_hours must be > 0")

    raw = normalized.replace("Z", "+00:00")
    dt = datetime.fromisoformat(raw).astimezone(timezone.utc)

    floored_hour = (dt.hour // window_hours) * window_hours
    dt = dt.replace(hour=floored_hour, minute=0, second=0, microsecond=0)

    return dt.isoformat().replace("+00:00", "Z")


def round_value(metric: str | None, value: float | None) -> float | None:
    if value is None:
        return None

    metric = normalize_metric(metric)
    if metric in {"aqi", "plume_index"}:
        return round(value, 0)
    return round(value, 3)


def is_reasonable_value(metric: str | None, value: float | None) -> bool:
    metric = normalize_metric(metric)

    if value is None:
        return False

    ranges = {
        "aqi": (0, 500),
        "plume_index": (0, 500),
        "pm25": (0, 1000),
        "pm10": (0, 1000),
        "no2": (0, 2000),
        "so2": (0, 2000),
        "o3": (0, 2000),
        "co": (0, 50000),
    }

    if metric not in ranges:
        return True

    low, high = ranges[metric]
    return low <= value <= high


def has_required_fields(obs: Observation) -> bool:
    return bool(
        obs.source
        and obs.metric
        and obs.observed_at_utc
        and obs.time_bucket_utc
        and obs.time_window_utc
        and obs.value is not None
    )


def normalize_observation(
    obs: Observation,
    *,
    window_hours: int = 3,
) -> Observation:
    normalized_metric = normalize_metric(obs.metric)
    normalized_value = safe_float(obs.value)
    normalized_unit = normalize_unit(normalized_metric, obs.unit)
    normalized_ts = normalize_timestamp_to_utc_str(obs.observed_at_utc)
    normalized_bucket = floor_timestamp_to_hour(normalized_ts)
    normalized_window = floor_timestamp_to_window(normalized_ts, window_hours=window_hours)

    lat = safe_float(obs.lat)
    lon = safe_float(obs.lon)

    if lat is not None:
        lat = round(lat, 6)
    if lon is not None:
        lon = round(lon, 6)

    return Observation(
        source=(obs.source or "").strip().lower(),
        source_kind=(obs.source_kind or None),
        station_id=(obs.station_id or None),
        station_name=(obs.station_name or None),
        lat=lat,
        lon=lon,
        observed_at_utc=normalized_ts or "",
        time_bucket_utc=normalized_bucket,
        time_window_utc=normalized_window,
        metric=normalized_metric or "",
        value=round_value(normalized_metric, normalized_value),
        unit=normalized_unit,
        extra=obs.extra or {},
    )


def observation_dedup_key(obs: Observation) -> tuple:
    return (
        obs.source,
        obs.station_id or "",
        obs.station_name or "",
        obs.lat,
        obs.lon,
        obs.observed_at_utc,
        obs.time_bucket_utc,
        obs.time_window_utc,
        obs.metric,
        obs.value,
        obs.unit,
    )


def explain_observation_rejection(obs: Observation) -> str | None:
    if not obs.source:
        return "missing_source"
    if not obs.metric:
        return "missing_metric"
    if not obs.observed_at_utc:
        return "missing_timestamp"
    if not obs.time_bucket_utc:
        return "missing_time_bucket"
    if not obs.time_window_utc:
        return "missing_time_window"
    if obs.value is None:
        return "missing_value"
    if not is_reasonable_value(obs.metric, obs.value):
        return "unreasonable_value"
    return None


def normalize_and_filter_observations(
    observations: list[Observation],
    *,
    window_hours: int = 3,
    debug: bool = False,
) -> list[Observation]:
    cleaned: list[Observation] = []
    seen: set[tuple] = set()

    rejection_counter = Counter()
    rejection_by_source = defaultdict(Counter)

    for obs in observations:
        normalized = normalize_observation(obs, window_hours=window_hours)
        reason = explain_observation_rejection(normalized)

        if reason is not None:
            rejection_counter[reason] += 1
            rejection_by_source[normalized.source][reason] += 1
            continue

        key = observation_dedup_key(normalized)
        if key in seen:
            rejection_counter["duplicate"] += 1
            rejection_by_source[normalized.source]["duplicate"] += 1
            continue

        seen.add(key)
        cleaned.append(normalized)

    if debug:
        print("\nFILTER DEBUG")
        print("Accepted:", len(cleaned))
        print("Rejected summary:", dict(rejection_counter))
        print("Rejected by source:")
        for source, stats in rejection_by_source.items():
            print(f"  {source}: {dict(stats)}")

    return cleaned
