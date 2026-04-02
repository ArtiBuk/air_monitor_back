from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from celery.result import AsyncResult
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.monitoring.models import ScheduledMonitoringTask
from apps.monitoring.tasks import (
    build_dataset_snapshot,
    collect_observations_window,
    execute_scheduled_monitoring_task,
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
    scheduled_task_id: str | None = None
    scheduled_for: datetime | None = None
    is_scheduled: bool = False


@dataclass
class MonitoringTaskStatusResult:
    task_id: str
    status: str
    ready: bool
    successful: bool
    result: Any | None
    error: str | None


@dataclass
class MonitoringScheduledTaskResult:
    id: str
    operation: str
    status: str
    scheduled_for: datetime
    celery_task_id: str
    payload: dict[str, Any]
    result: Any | None
    error: str
    requested_by_id: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class MonitoringTaskQueueService:
    def _get_requested_by(self, requested_by_id: str | None):
        if not requested_by_id:
            return None
        return get_user_model().objects.filter(id=requested_by_id).first()

    def _normalize_scheduled_for(self, scheduled_for: datetime) -> datetime:
        normalized = scheduled_for.astimezone(UTC)
        if normalized <= timezone.now().astimezone(UTC):
            raise ValueError("scheduled_for must be in the future.")
        return normalized

    def _serialize_scheduled_task(self, scheduled_task: ScheduledMonitoringTask) -> MonitoringScheduledTaskResult:
        return MonitoringScheduledTaskResult(
            id=str(scheduled_task.id),
            operation=scheduled_task.operation,
            status=scheduled_task.status,
            scheduled_for=scheduled_task.scheduled_for,
            celery_task_id=scheduled_task.celery_task_id,
            payload=scheduled_task.payload,
            result=scheduled_task.result,
            error=scheduled_task.error,
            requested_by_id=str(scheduled_task.requested_by_id) if scheduled_task.requested_by_id else None,
            started_at=scheduled_task.started_at,
            finished_at=scheduled_task.finished_at,
            created_at=scheduled_task.created_at,
        )

    def _schedule_task(
        self,
        *,
        operation: str,
        payload: dict[str, Any],
        requested_by_id: str | None,
        scheduled_for: datetime,
    ) -> MonitoringTaskLaunchResult:
        normalized_scheduled_for = self._normalize_scheduled_for(scheduled_for)
        scheduled_task = ScheduledMonitoringTask.objects.create(
            requested_by=self._get_requested_by(requested_by_id),
            operation=operation,
            status=ScheduledMonitoringTask.Status.SCHEDULED,
            scheduled_for=normalized_scheduled_for,
            payload=_normalize_task_payload(payload),
        )
        task = execute_scheduled_monitoring_task.apply_async(
            kwargs={"scheduled_task_id": str(scheduled_task.id)},
            eta=normalized_scheduled_for,
        )
        scheduled_task.celery_task_id = str(task.id)
        scheduled_task.save(update_fields=["celery_task_id", "updated_at"])
        return MonitoringTaskLaunchResult(
            task_id=str(task.id),
            status=scheduled_task.status,
            operation=operation,
            scheduled_task_id=str(scheduled_task.id),
            scheduled_for=normalized_scheduled_for,
            is_scheduled=True,
        )

    def enqueue_collect_observations(
        self,
        *,
        start: str,
        finish: str,
        interval: str,
        window_hours: int,
        requested_by_id: str | None = None,
        scheduled_for: datetime | None = None,
    ) -> MonitoringTaskLaunchResult:
        if scheduled_for is not None:
            return self._schedule_task(
                operation=ScheduledMonitoringTask.Operation.COLLECT_OBSERVATIONS,
                payload={
                    "start": start,
                    "finish": finish,
                    "interval": interval,
                    "window_hours": window_hours,
                },
                requested_by_id=requested_by_id,
                scheduled_for=scheduled_for,
            )
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
        requested_by_id: str | None = None,
        scheduled_for: datetime | None = None,
    ) -> MonitoringTaskLaunchResult:
        if scheduled_for is not None:
            return self._schedule_task(
                operation=ScheduledMonitoringTask.Operation.BUILD_DATASET,
                payload={
                    "input_len_hours": input_len_hours,
                    "forecast_horizon_hours": forecast_horizon_hours,
                    "feature_columns": feature_columns,
                    "target_columns": target_columns,
                },
                requested_by_id=requested_by_id,
                scheduled_for=scheduled_for,
            )
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
        scheduled_for: datetime | None = None,
    ) -> MonitoringTaskLaunchResult:
        if scheduled_for is not None:
            return self._schedule_task(
                operation=ScheduledMonitoringTask.Operation.TRAIN_MODEL,
                payload={
                    "dataset_snapshot_id": dataset_snapshot_id,
                    "requested_by_id": requested_by_id,
                    "epochs": epochs,
                    "batch_size": batch_size,
                    "lr": lr,
                    "weight_decay": weight_decay,
                    "patience": patience,
                    "seed": seed,
                },
                requested_by_id=requested_by_id,
                scheduled_for=scheduled_for,
            )
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
        scheduled_for: datetime | None = None,
    ) -> MonitoringTaskLaunchResult:
        if scheduled_for is not None:
            return self._schedule_task(
                operation=ScheduledMonitoringTask.Operation.GENERATE_FORECAST,
                payload={
                    "model_version_id": model_version_id,
                    "requested_by_id": requested_by_id,
                    "input_len_hours": input_len_hours,
                    "forecast_horizon_hours": forecast_horizon_hours,
                    "generated_from_timestamp_utc": generated_from_timestamp_utc,
                },
                requested_by_id=requested_by_id,
                scheduled_for=scheduled_for,
            )
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
        scheduled_for: datetime | None = None,
    ) -> MonitoringTaskLaunchResult:
        if scheduled_for is not None:
            return self._schedule_task(
                operation=ScheduledMonitoringTask.Operation.RUN_EXPERIMENT,
                payload={
                    "requested_by_id": requested_by_id,
                    "series_id": series_id,
                    "name": name,
                    "input_len_hours": input_len_hours,
                    "forecast_horizon_hours": forecast_horizon_hours,
                    "feature_columns": feature_columns,
                    "target_columns": target_columns,
                    "generated_from_timestamp_utc": generated_from_timestamp_utc,
                    "training_config": training_config,
                },
                requested_by_id=requested_by_id,
                scheduled_for=scheduled_for,
            )
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

    def list_scheduled_tasks(
        self,
        *,
        requested_by_id: str | None = None,
        limit: int = 20,
        status: str | None = None,
    ) -> list[MonitoringScheduledTaskResult]:
        queryset = ScheduledMonitoringTask.objects.all()
        if requested_by_id is not None:
            queryset = queryset.filter(requested_by_id=requested_by_id)
        if status is not None:
            queryset = queryset.filter(status=status)
        return [self._serialize_scheduled_task(item) for item in queryset[:limit]]

    def get_scheduled_task(
        self,
        *,
        scheduled_task_id: str,
        requested_by_id: str | None = None,
    ) -> MonitoringScheduledTaskResult | None:
        queryset = ScheduledMonitoringTask.objects.filter(id=scheduled_task_id)
        if requested_by_id is not None:
            queryset = queryset.filter(requested_by_id=requested_by_id)
        scheduled_task = queryset.first()
        if scheduled_task is None:
            return None
        return self._serialize_scheduled_task(scheduled_task)

    def cancel_scheduled_task(
        self,
        *,
        scheduled_task_id: str,
        requested_by_id: str | None = None,
    ) -> MonitoringScheduledTaskResult:
        queryset = ScheduledMonitoringTask.objects.filter(id=scheduled_task_id)
        if requested_by_id is not None:
            queryset = queryset.filter(requested_by_id=requested_by_id)
        scheduled_task = queryset.first()
        if scheduled_task is None:
            raise ValueError("Scheduled task not found.")
        if scheduled_task.status != ScheduledMonitoringTask.Status.SCHEDULED:
            raise ValueError("Only scheduled tasks can be cancelled.")

        if scheduled_task.celery_task_id:
            celery_app.control.revoke(scheduled_task.celery_task_id)

        scheduled_task.status = ScheduledMonitoringTask.Status.CANCELLED
        scheduled_task.finished_at = timezone.now()
        scheduled_task.error = ""
        scheduled_task.save(update_fields=["status", "finished_at", "error", "updated_at"])
        return self._serialize_scheduled_task(scheduled_task)
