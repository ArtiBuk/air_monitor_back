from datetime import datetime
from uuid import UUID

from ninja import Schema
from ninja.orm import ModelSchema

from apps.monitoring.models import ModelVersion


class TrainModelPayload(Schema):
    dataset_snapshot_id: UUID | None = None
    epochs: int = 250
    batch_size: int = 32
    lr: float = 1e-3
    weight_decay: float = 1e-4
    patience: int = 25
    seed: int = 42
    scheduled_for: datetime | None = None


class ModelVersionSchema(ModelSchema):
    class Meta:
        model = ModelVersion
        fields = [
            "id",
            "dataset",
            "name",
            "status",
            "input_len_hours",
            "forecast_horizon_hours",
            "feature_names",
            "target_names",
            "training_config",
            "metrics",
            "history",
            "error_message",
            "is_active",
            "created_at",
        ]


class ModelLeaderboardEntrySchema(Schema):
    model_version_id: UUID
    model_name: str
    evaluation_count: int
    avg_overall_rmse: float
    avg_overall_mae: float
    avg_macro_mape: float
    avg_coverage_ratio: float
    forecast_horizon_hours: int
    input_len_hours: int
    is_active: bool
    latest_evaluated_at_utc: datetime | None = None
