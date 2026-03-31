from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class Observation:
    source: str
    source_kind: Optional[str]
    station_id: Optional[str]
    station_name: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    observed_at_utc: str
    time_bucket_utc: Optional[str]
    time_window_utc: Optional[str]
    metric: str
    value: Optional[float]
    unit: Optional[str]
    extra: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)
