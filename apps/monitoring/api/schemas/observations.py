from datetime import datetime
from typing import Any

from ninja import Schema
from ninja.orm import ModelSchema

from apps.monitoring.models import Observation


class ObservationSchema(ModelSchema):
    class Meta:
        model = Observation
        fields = [
            "id",
            "source",
            "source_kind",
            "station_id",
            "station_name",
            "lat",
            "lon",
            "observed_at_utc",
            "time_bucket_utc",
            "time_window_utc",
            "metric",
            "value",
            "unit",
            "extra",
        ]


class CollectObservationsPayload(Schema):
    start: datetime
    finish: datetime
    interval: str = "Interval1H"
    window_hours: int = 1
    scheduled_for: datetime | None = None


class ObservationSyncSchema(Schema):
    raw_count: int
    cleaned_count: int
    db_created_count: int
    db_updated_count: int


class AirMapBoundsSchema(Schema):
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    center_lat: float
    center_lon: float


class AirMapStationPointSchema(Schema):
    station_id: str
    station_name: str
    lat: float
    lon: float
    observed_at_utc: datetime
    value: float | None = None
    unit: str = ""
    source: str
    source_kind: str = ""
    extra: dict[str, Any] = {}


class AirMapMetricSnapshotSchema(Schema):
    metric: str
    value: float | None = None
    unit: str = ""
    observed_at_utc: datetime
    source: str
    station_name: str = ""
    extra: dict[str, Any] = {}


class AirMapSummarySchema(Schema):
    latest_station_timestamp: datetime | None = None
    latest_city_timestamp: datetime | None = None
    station_count: int = 0
    city_metric_count: int = 0
    sources: list[str]


class AirMapSnapshotSchema(Schema):
    summary: AirMapSummarySchema
    bounds: AirMapBoundsSchema | None = None
    station_points: list[AirMapStationPointSchema]
    city_metrics: list[AirMapMetricSnapshotSchema]
