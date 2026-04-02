from datetime import datetime

from ninja import Schema
from ninja.orm import ModelSchema

from apps.monitoring.models import DatasetSnapshot


class BuildDatasetPayload(Schema):
    input_len_hours: int = 72
    forecast_horizon_hours: int = 24
    feature_columns: list[str] | None = None
    target_columns: list[str] | None = None
    scheduled_for: datetime | None = None


class DatasetSnapshotSchema(ModelSchema):
    class Meta:
        model = DatasetSnapshot
        fields = [
            "id",
            "input_len_hours",
            "forecast_horizon_hours",
            "master_row_count",
            "sample_count",
            "feature_columns",
            "target_columns",
            "metadata",
            "created_at",
        ]
