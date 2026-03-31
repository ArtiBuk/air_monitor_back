from dataclasses import dataclass
from typing import Any

from celery.result import AsyncResult

from apps.monitoring.tasks import (
    build_dataset_snapshot,
    collect_observations_window,
    generate_forecast_run,
    run_experiment_pipeline,
    train_model_version,
)
from config.celery import app as celery_app


def _normalize_task_payload(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _normalize_task_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_task_payload(item) for item in value]
    return str(value)


@dataclass
class MonitoringTaskLaunchResult:
    task_id: str
    status: str
    operation: str


@dataclass
class MonitoringTaskStatusResult:
    task_id: str
    status: str
    ready: bool
    successful: bool
    result: Any | None
    error: str | None


class MonitoringTaskQueueService:
    def enqueue_collect_observations(
        self, *, start: str, finish: str, interval: str, window_hours: int
    ) -> MonitoringTaskLaunchResult:
        task = collect_observations_window.delay(
            start=start,
            finish=finish,
            interval=interval,
            window_hours=window_hours,
        )
        return MonitoringTaskLaunchResult(
            task_id=str(task.id), status=str(task.status), operation="collect_observations"
        )

    def enqueue_build_dataset(
        self,
        *,
        input_len_hours: int,
        forecast_horizon_hours: int,
        feature_columns: list[str] | None = None,
        target_columns: list[str] | None = None,
    ) -> MonitoringTaskLaunchResult:
        task = build_dataset_snapshot.delay(
            input_len_hours=input_len_hours,
            forecast_horizon_hours=forecast_horizon_hours,
            feature_columns=feature_columns,
            target_columns=target_columns,
        )
        return MonitoringTaskLaunchResult(task_id=str(task.id), status=str(task.status), operation="build_dataset")

    def enqueue_train_model(
        self,
        *,
        dataset_snapshot_id: str | None,
        requested_by_id: str | None,
        epochs: int,
        batch_size: int,
        lr: float,
        weight_decay: float,
        patience: int,
        seed: int,
    ) -> MonitoringTaskLaunchResult:
        task = train_model_version.delay(
            dataset_snapshot_id=dataset_snapshot_id,
            requested_by_id=requested_by_id,
            epochs=epochs,
            batch_size=batch_size,
            lr=lr,
            weight_decay=weight_decay,
            patience=patience,
            seed=seed,
        )
        return MonitoringTaskLaunchResult(task_id=str(task.id), status=str(task.status), operation="train_model")

    def enqueue_generate_forecast(
        self,
        *,
        model_version_id: str | None,
        requested_by_id: str | None,
        input_len_hours: int,
        forecast_horizon_hours: int,
        generated_from_timestamp_utc: str | None = None,
    ) -> MonitoringTaskLaunchResult:
        task = generate_forecast_run.delay(
            model_version_id=model_version_id,
            requested_by_id=requested_by_id,
            input_len_hours=input_len_hours,
            forecast_horizon_hours=forecast_horizon_hours,
            generated_from_timestamp_utc=generated_from_timestamp_utc,
        )
        return MonitoringTaskLaunchResult(task_id=str(task.id), status=str(task.status), operation="generate_forecast")

    def enqueue_run_experiment(
        self,
        *,
        requested_by_id: str | None,
        series_id: str | None,
        name: str,
        input_len_hours: int,
        forecast_horizon_hours: int,
        feature_columns: list[str] | None = None,
        target_columns: list[str] | None = None,
        generated_from_timestamp_utc: str | None = None,
        training_config: dict,
    ) -> MonitoringTaskLaunchResult:
        task = run_experiment_pipeline.delay(
            requested_by_id=requested_by_id,
            series_id=series_id,
            name=name,
            input_len_hours=input_len_hours,
            forecast_horizon_hours=forecast_horizon_hours,
            feature_columns=feature_columns,
            target_columns=target_columns,
            generated_from_timestamp_utc=generated_from_timestamp_utc,
            training_config=training_config,
        )
        return MonitoringTaskLaunchResult(task_id=str(task.id), status=str(task.status), operation="run_experiment")

    def get_status(self, *, task_id: str) -> MonitoringTaskStatusResult:
        task = AsyncResult(task_id, app=celery_app)
        raw_payload = task.result if task.ready() else task.info

        if task.failed():
            return MonitoringTaskStatusResult(
                task_id=task.id,
                status=str(task.status),
                ready=task.ready(),
                successful=False,
                result=None,
                error=str(raw_payload),
            )

        return MonitoringTaskStatusResult(
            task_id=str(task.id),
            status=str(task.status),
            ready=task.ready(),
            successful=task.successful(),
            result=_normalize_task_payload(raw_payload),
            error=None,
        )
