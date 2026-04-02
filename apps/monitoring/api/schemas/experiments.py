from datetime import datetime
from typing import Any
from uuid import UUID

from ninja import Schema
from ninja.orm import ModelSchema
from pydantic import Field

from apps.monitoring.models import ExperimentRun, ExperimentSeries


class ExperimentDatasetConfigPayload(Schema):
    input_len_hours: int = 72
    forecast_horizon_hours: int = 24
    feature_columns: list[str] | None = None
    target_columns: list[str] | None = None


class ExperimentTrainingConfigPayload(Schema):
    epochs: int = 250
    batch_size: int = 32
    lr: float = 1e-3
    weight_decay: float = 1e-4
    patience: int = 25
    seed: int = 42


class ExperimentBacktestConfigPayload(Schema):
    generated_from_timestamp_utc: datetime | None = None


class RunExperimentPayload(Schema):
    name: str = "experiment"
    series_id: UUID | None = None
    dataset: ExperimentDatasetConfigPayload = Field(default_factory=ExperimentDatasetConfigPayload)
    training: ExperimentTrainingConfigPayload = Field(default_factory=ExperimentTrainingConfigPayload)
    backtest: ExperimentBacktestConfigPayload | None = None
    scheduled_for: datetime | None = None


class ExperimentRunSchema(ModelSchema):
    class Meta:
        model = ExperimentRun
        fields = [
            "id",
            "series",
            "name",
            "status",
            "dataset_snapshot",
            "model_version",
            "forecast_run",
            "forecast_evaluation",
            "input_len_hours",
            "forecast_horizon_hours",
            "feature_columns",
            "target_columns",
            "training_config",
            "backtest_config",
            "summary",
            "error_message",
            "created_at",
        ]


class ExperimentSeriesConfigurationPayload(Schema):
    goal: str = ""
    dataset: ExperimentDatasetConfigPayload | None = None
    training: ExperimentTrainingConfigPayload | None = None
    backtest: ExperimentBacktestConfigPayload | None = None
    metadata: dict[str, Any] | None = None


class CreateExperimentSeriesPayload(Schema):
    name: str
    description: str = ""
    configuration: ExperimentSeriesConfigurationPayload | None = None


class ExperimentSeriesSchema(ModelSchema):
    class Meta:
        model = ExperimentSeries
        fields = [
            "id",
            "name",
            "description",
            "status",
            "configuration",
            "summary",
            "created_at",
        ]


class ExperimentSeriesReportAggregatesSchema(Schema):
    run_count: int
    completed_run_count: int
    failed_run_count: int
    latest_experiment_run_id: UUID | None = None
    best_experiment_run_id: UUID | None = None
    best_backtest_overall_rmse: float | None = None
    avg_training_overall_rmse: float | None = None
    avg_backtest_overall_rmse: float | None = None
    avg_backtest_overall_mae: float | None = None
    avg_backtest_macro_mape: float | None = None


class ExperimentSeriesReportSchema(Schema):
    series: ExperimentSeriesSchema
    runs: list[ExperimentRunSchema]
    aggregates: ExperimentSeriesReportAggregatesSchema
