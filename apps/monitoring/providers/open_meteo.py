from datetime import datetime, timezone
from typing import Any

import openmeteo_requests

from ..ingestion.types import Observation
from ..ingestion.utils import floor_timestamp_to_hour, floor_timestamp_to_window, safe_float
from .base import BaseCollector


class OpenMeteoCollector(BaseCollector):
    source_name = "open_meteo"
    provider_name = "open_meteo"

    URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
    DEFAULT_LATITUDE = 69.3558
    DEFAULT_LONGITUDE = 88.1893
    HOURLY_VARIABLES = (
        "european_aqi",
        "pm2_5",
        "pm10",
        "nitrogen_dioxide",
        "sulphur_dioxide",
        "ozone",
        "carbon_monoxide",
    )
    METRIC_MAP = {
        "european_aqi": "plume_index",
        "pm2_5": "pm25",
        "pm10": "pm10",
        "nitrogen_dioxide": "no2",
        "sulphur_dioxide": "so2",
        "ozone": "o3",
        "carbon_monoxide": "co",
    }

    def __init__(
        self,
        *,
        window_hours: int = 3,
        latitude: float = DEFAULT_LATITUDE,
        longitude: float = DEFAULT_LONGITUDE,
        station_name: str = "Норильск (городской фон)",
        client: openmeteo_requests.Client | None = None,
    ):
        self.window_hours = window_hours
        self.latitude = latitude
        self.longitude = longitude
        self.station_name = station_name
        self.client = client or openmeteo_requests.Client()

    @staticmethod
    def _parse_utc_datetime(value: str) -> datetime:
        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @classmethod
    def _to_api_hour(cls, value: str) -> str:
        return cls._parse_utc_datetime(value).strftime("%Y-%m-%dT%H:%M")

    @classmethod
    def _to_observed_at_utc(cls, value: str) -> str:
        return cls._parse_utc_datetime(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def fetch_raw(self, *, start: str, finish: str) -> dict[str, Any]:
        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "hourly": list(self.HOURLY_VARIABLES),
            "timezone": "UTC",
            "start_hour": self._to_api_hour(start),
            "end_hour": self._to_api_hour(finish),
        }
        responses = self.client.weather_api(self.URL, params=params)
        if not responses:
            return {"timezone": "UTC", "times": [], "values": {}}

        response = responses[0]
        hourly = response.Hourly()
        variables_count = hourly.VariablesLength()
        if variables_count < len(self.HOURLY_VARIABLES):
            raise RuntimeError(
                f"Open-Meteo вернул неполный ответ: переменных={variables_count}, ожидалось={len(self.HOURLY_VARIABLES)}"
            )

        values: dict[str, list[float]] = {}
        for index, variable in enumerate(self.HOURLY_VARIABLES):
            values[variable] = hourly.Variables(index).ValuesAsNumpy().tolist()

        times = list(range(hourly.Time(), hourly.TimeEnd(), hourly.Interval()))
        return {
            "timezone": response.Timezone(),
            "times": times,
            "values": values,
        }

    def collect(self, **kwargs: Any) -> list[Observation]:
        start = kwargs.get("start")
        finish = kwargs.get("finish")
        if not isinstance(start, str) or not isinstance(finish, str):
            raise ValueError("OpenMeteoCollector.collect requires string args: start, finish")

        payload = self.fetch_raw(start=start, finish=finish)
        timeline = payload.get("times") or []
        values_map = payload.get("values") or {}

        observations: list[Observation] = []
        for index, ts in enumerate(timeline):
            observed_at_utc = (
                datetime.fromtimestamp(ts, tz=timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace(
                    "+00:00",
                    "Z",
                )
            )
            time_bucket_utc = floor_timestamp_to_hour(observed_at_utc)
            time_window_utc = floor_timestamp_to_window(observed_at_utc, window_hours=self.window_hours)

            for variable, metric in self.METRIC_MAP.items():
                values = values_map.get(variable) or []
                raw_value = values[index] if index < len(values) else None
                value = safe_float(raw_value)
                if value is None:
                    continue

                unit = "index" if metric == "plume_index" else "µg/m3"

                observations.append(
                    Observation(
                        source=self.source_name,
                        source_kind="open_meteo_api",
                        station_id=None,
                        station_name=self.station_name,
                        lat=self.latitude,
                        lon=self.longitude,
                        observed_at_utc=observed_at_utc,
                        time_bucket_utc=time_bucket_utc,
                        time_window_utc=time_window_utc,
                        metric=metric,
                        value=value,
                        unit=unit,
                        extra={
                            "provider": self.provider_name,
                            "raw_metric": variable,
                            "timezone": payload.get("timezone"),
                        },
                    )
                )

        return observations
