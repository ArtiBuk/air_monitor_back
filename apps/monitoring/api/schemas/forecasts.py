from datetime import datetime
from uuid import UUID

from ninja import Schema
from ninja.orm import ModelSchema

from apps.monitoring.models import ForecastEvaluation, ForecastRecord, ForecastRun


class ForecastRecordSchema(ModelSchema):
    class Meta:
        model = ForecastRecord
        fields = ["id", "timestamp_utc", "values"]


class ForecastRunSchema(ModelSchema):
    records: list[ForecastRecordSchema]

    class Meta:
        model = ForecastRun
        fields = [
            "id",
            "model_version",
            "status",
            "generated_from_timestamp_utc",
            "forecast_horizon_hours",
            "created_at",
            "error_message",
            "metadata",
        ]


class ForecastGeneratePayload(Schema):
    input_len_hours: int = 72
    forecast_horizon_hours: int = 24
    model_version_id: UUID | None = None
    generated_from_timestamp_utc: datetime | None = None


class ForecastEvaluationSchema(ModelSchema):
    class Meta:
        model = ForecastEvaluation
        fields = [
            "id",
            "forecast_run",
            "status",
            "expected_record_count",
            "matched_record_count",
            "coverage_ratio",
            "evaluated_at_utc",
            "metrics",
            "error_message",
            "created_at",
        ]
