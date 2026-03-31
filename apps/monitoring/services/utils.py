import hashlib
import json
from datetime import datetime


def parse_utc_datetime(value: str | None):
    if not value:
        return None

    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def build_observation_fingerprint(parts: tuple) -> str:
    payload = json.dumps(parts, default=str, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
