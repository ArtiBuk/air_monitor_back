from datetime import datetime

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


class ObservationSyncSchema(Schema):
    raw_count: int
    cleaned_count: int
    db_created_count: int
    db_updated_count: int
