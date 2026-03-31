import json
import re
from datetime import datetime, timezone

from ..ingestion.types import Observation
from ..ingestion.utils import floor_timestamp_to_hour, floor_timestamp_to_window, http_get_text
from .base import BaseCollector


class PlumeCollector(BaseCollector):
    source_name = "plumelabs"

    def __init__(self, page_url: str, window_hours: int = 3):
        self.page_url = page_url
        self.window_hours = window_hours

    def fetch_html(self) -> str:
        return http_get_text(self.page_url)

    def _extract_current_data(self, html: str) -> dict:
        patterns = [
            r"window\.current_data\s*=\s*(\{.*?\});",
            r"window\.current_data\s*=\s*(\{.*?\})\s*\n",
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if not match:
                continue
            return json.loads(match.group(1))

        raise ValueError("Plume current_data not found")

    def _extract_timeline_data(self, html: str) -> list[dict]:
        named_patterns = [
            r"window\.forecast_data\s*=\s*(\[\{.*?\}\]);",
            r"window\.history_data\s*=\s*(\[\{.*?\}\]);",
            r"window\.timeline_data\s*=\s*(\[\{.*?\}\]);",
            r"window\.chart_data\s*=\s*(\[\{.*?\}\]);",
        ]

        for pattern in named_patterns:
            match = re.search(pattern, html, re.DOTALL)
            if not match:
                continue

            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

            if isinstance(data, list) and data:
                return data

        fallback_patterns = [
            r"(\[\s*\{.*?\"timestamp\".*?\}\s*\])\s*;\s*window\.current_data\s*=",
        ]

        for pattern in fallback_patterns:
            match = re.search(pattern, html, re.DOTALL)
            if not match:
                continue

            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

            if isinstance(data, list) and data:
                return data

        raise ValueError("Plume timeline data not found")

    @staticmethod
    def _ts_to_iso(ts: int | float | None) -> str:
        if ts is None:
            raise ValueError("Plume timestamp is missing")

        return datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _safe_float(value):
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_iso_to_dt(value: str | None) -> datetime | None:
        if not value:
            return None

        raw = value.strip()
        if raw.endswith("Z"):
            raw = raw.replace("Z", "+00:00")

        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    def _record_to_observations(self, item: dict) -> list[Observation]:
        observed_at = self._ts_to_iso(item.get("timestamp"))
        time_bucket_utc = floor_timestamp_to_hour(observed_at)
        time_window_utc = floor_timestamp_to_window(
            observed_at,
            window_hours=self.window_hours,
        )

        values = item.get("values", {}) or {}
        weather = item.get("weather")

        observations: list[Observation] = []

        plume_index = self._safe_float(item.get("plume_index"))
        if plume_index is not None:
            observations.append(
                Observation(
                    source=self.source_name,
                    source_kind="embedded_js",
                    station_id=None,
                    station_name="Norilsk",
                    lat=None,
                    lon=None,
                    observed_at_utc=observed_at,
                    time_bucket_utc=time_bucket_utc,
                    time_window_utc=time_window_utc,
                    metric="plume_index",
                    value=plume_index,
                    unit="index",
                    extra={
                        "page_url": self.page_url,
                        "raw_metric": "plume_index",
                        "plume_index_level": item.get("plume_index_level"),
                        "weather": weather,
                    },
                )
            )

        metric_map = {
            "PM25": "pm25",
            "PM10": "pm10",
            "NO2": "no2",
            "O3": "o3",
            "SO2": "so2",
            "CO": "co",
        }

        for src_key, metric in metric_map.items():
            metric_obj = values.get(src_key)
            if not isinstance(metric_obj, dict):
                continue

            value = self._safe_float(metric_obj.get("value_upm"))
            if value is None:
                continue

            observations.append(
                Observation(
                    source=self.source_name,
                    source_kind="embedded_js",
                    station_id=None,
                    station_name="Norilsk",
                    lat=None,
                    lon=None,
                    observed_at_utc=observed_at,
                    time_bucket_utc=time_bucket_utc,
                    time_window_utc=time_window_utc,
                    metric=metric,
                    value=value,
                    unit="µg/m3",
                    extra={
                        "page_url": self.page_url,
                        "raw_metric": src_key,
                        "pi": metric_obj.get("pi"),
                        "weather": weather,
                    },
                )
            )

        return observations

    def collect(
        self,
        *,
        start: str | None = None,
        finish: str | None = None,
        timeline: bool = True,
        **kwargs,
    ) -> list[Observation]:
        html = self.fetch_html()

        if not timeline:
            current = self._extract_current_data(html)
            return self._record_to_observations(current)

        items = self._extract_timeline_data(html)

        start_dt = self._parse_iso_to_dt(start)
        finish_dt = self._parse_iso_to_dt(finish)

        filtered_items: list[dict] = []
        for item in items:
            ts = item.get("timestamp")
            if ts is None:
                continue

            item_dt = datetime.fromtimestamp(ts, tz=timezone.utc)

            if start_dt and item_dt < start_dt:
                continue
            if finish_dt and item_dt > finish_dt:
                continue

            filtered_items.append(item)

        observations: list[Observation] = []
        for item in filtered_items:
            observations.extend(self._record_to_observations(item))

        return observations
