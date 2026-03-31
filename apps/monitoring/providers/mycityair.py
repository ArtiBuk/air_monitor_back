from typing import Any

from ..config import MYCITYAIR_TOKEN
from ..ingestion.types import Observation
from ..ingestion.utils import floor_timestamp_to_hour, floor_timestamp_to_window, http_get_json
from .base import BaseCollector


class MyCityAirCollector(BaseCollector):
    source_name = "mycityair"

    URL = "https://eco-sources.mycityair.ru/api/basic/v1/group/66/timeline/widget"

    def __init__(self, token: str | None = None, window_hours: int = 3):
        self.token = token or MYCITYAIR_TOKEN
        self.window_hours = window_hours

    def _headers(self) -> dict:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://norilsk.mycityair.ru",
            "Referer": "https://norilsk.mycityair.ru/",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def fetch_raw(self, start: str, finish: str, interval: str = "Interval1H") -> dict[str, Any]:
        params = {
            "start": start,
            "finish": finish,
            "interval": interval,
        }
        return http_get_json(self.URL, params=params, headers=self._headers())

    def collect(self, *, start: str, finish: str, interval: str = "Interval1H") -> list[Observation]:
        payload = self.fetch_raw(start=start, finish=finish, interval=interval)
        observations: list[Observation] = []

        for feature in payload.get("features", []):
            props = feature.get("properties", {})
            geom = feature.get("geometry", {})
            coords = geom.get("coordinates", [None, None])

            if props.get("obj") != "source":
                continue

            dates = props.get("timeseries", {}).get("date", [])
            aqi_values = props.get("timeseries", {}).get("aqi", [])

            for dt_value, aqi_value in zip(dates, aqi_values):
                if aqi_value is None:
                    continue

                observations.append(
                    Observation(
                        source=self.source_name,
                        source_kind="api",
                        station_id=props.get("uuid"),
                        station_name=props.get("name_ru") or props.get("name"),
                        lat=coords[1] if len(coords) > 1 else None,
                        lon=coords[0] if len(coords) > 0 else None,
                        observed_at_utc=dt_value,
                        time_bucket_utc=floor_timestamp_to_hour(dt_value),
                        time_window_utc=floor_timestamp_to_window(
                            dt_value,
                            window_hours=self.window_hours,
                        ),
                        metric="aqi",
                        value=float(aqi_value),
                        unit="index",
                        extra={
                            "name": props.get("name"),
                            "object_type": props.get("obj"),
                        },
                    )
                )

        return observations
