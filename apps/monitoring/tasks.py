import logging
from dataclasses import asdict
from datetime import UTC, timedelta

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import DatasetSnapshot, ExperimentSeries, ModelVersion
from .services.experiments import ExperimentService
from .services.forecasts import ForecastService
from .services.observations import ObservationSyncService
from .services.training import ModelLifecycleService

logger = logging.getLogger(__name__)


def _get_requested_by(requested_by_id: str | None):
    if not requested_by_id:
        return None
    return get_user_model().objects.filter(id=requested_by_id).first()


def _get_dataset_snapshot(dataset_snapshot_id: str | None):
    if not dataset_snapshot_id:
        return None
    return DatasetSnapshot.objects.filter(id=dataset_snapshot_id).first()


def _get_model_version(model_version_id: str | None):
    if not model_version_id:
        return None
    return ModelVersion.objects.filter(id=model_version_id).first()


def _get_experiment_series(series_id: str | None):
    if not series_id:
        return None
    return ExperimentSeries.objects.filter(id=series_id).first()


@shared_task(name="apps.monitoring.tasks.collect_recent_observations")
def collect_recent_observations():
    logger.info("celery task started task=collect_recent_observations")
    finish = timezone.now().astimezone(UTC)
    start = finish - timedelta(hours=settings.MONITORING_COLLECTION_LOOKBACK_HOURS)
    service = ObservationSyncService()
    result = service.collect(
        start=start.isoformat().replace("+00:00", "Z"),
        finish=finish.isoformat().replace("+00:00", "Z"),
        interval=settings.MONITORING_INTERVAL,
        window_hours=settings.MONITORING_WINDOW_HOURS,
    )
    logger.info("celery task completed task=collect_recent_observations")
    return asdict(result)


@shared_task(name="apps.monitoring.tasks.collect_observations_window")
def collect_observations_window(*, start: str, finish: str, interval: str, window_hours: int):
    logger.info(
        "celery task started task=collect_observations_window start=%s finish=%s interval=%s window_hours=%s",
        start,
        finish,
        interval,
        window_hours,
    )
    result = ObservationSyncService().collect(
        start=start,
        finish=finish,
        interval=interval,
        window_hours=window_hours,
    )
    logger.info("celery task completed task=collect_observations_window")
    return asdict(result)


@shared_task(name="apps.monitoring.tasks.build_dataset_snapshot")
def build_dataset_snapshot(
    *,
    input_len_hours: int,
    forecast_horizon_hours: int,
    feature_columns: list[str] | None = None,
    target_columns: list[str] | None = None,
):
    logger.info(
        "celery task started task=build_dataset_snapshot input_len_hours=%s forecast_horizon_hours=%s",
        input_len_hours,
        forecast_horizon_hours,
    )
    snapshot = ModelLifecycleService().build_dataset(
        input_len_hours=input_len_hours,
        forecast_horizon_hours=forecast_horizon_hours,
        feature_columns=feature_columns,
        target_columns=target_columns,
    )
    logger.info("celery task completed task=build_dataset_snapshot dataset_id=%s", snapshot.id)
    return {
        "dataset_id": str(snapshot.id),
        "input_len_hours": snapshot.input_len_hours,
        "forecast_horizon_hours": snapshot.forecast_horizon_hours,
        "sample_count": snapshot.sample_count,
    }


@shared_task(name="apps.monitoring.tasks.train_model_version")
def train_model_version(
    *,
    dataset_snapshot_id: str | None,
    requested_by_id: str | None,
    epochs: int,
    batch_size: int,
    lr: float,
    weight_decay: float,
    patience: int,
    seed: int,
):
    logger.info(
        "celery task started task=train_model_version dataset_snapshot_id=%s requested_by=%s epochs=%s batch_size=%s",
        dataset_snapshot_id,
        requested_by_id,
        epochs,
        batch_size,
    )
    model_version = ModelLifecycleService().train(
        dataset_snapshot=_get_dataset_snapshot(dataset_snapshot_id),
        requested_by=_get_requested_by(requested_by_id),
        epochs=epochs,
        batch_size=batch_size,
        lr=lr,
        weight_decay=weight_decay,
        patience=patience,
        seed=seed,
    )
    logger.info("celery task completed task=train_model_version model_version_id=%s", model_version.id)
    return {
        "model_version_id": str(model_version.id),
        "status": model_version.status,
        "is_active": model_version.is_active,
    }


@shared_task(name="apps.monitoring.tasks.generate_hourly_forecast")
def generate_hourly_forecast():
    logger.info("celery task started task=generate_hourly_forecast")
    result = ForecastService().generate()
    logger.info("celery task completed task=generate_hourly_forecast run_id=%s", result.run_id)
    return {
        "run_id": result.run_id,
        "generated_from_timestamp_utc": result.generated_from_timestamp_utc,
        "forecast_horizon_hours": result.forecast_horizon_hours,
        "record_count": len(result.records),
    }


@shared_task(name="apps.monitoring.tasks.generate_forecast_run")
def generate_forecast_run(
    *,
    model_version_id: str | None,
    requested_by_id: str | None,
    input_len_hours: int,
    forecast_horizon_hours: int,
    generated_from_timestamp_utc: str | None = None,
):
    logger.info(
        "celery task started task=generate_forecast_run model_version_id=%s requested_by=%s input_len_hours=%s forecast_horizon_hours=%s",
        model_version_id,
        requested_by_id,
        input_len_hours,
        forecast_horizon_hours,
    )
    result = ForecastService().generate(
        model_version=_get_model_version(model_version_id),
        requested_by=_get_requested_by(requested_by_id),
        input_len_hours=input_len_hours,
        forecast_horizon_hours=forecast_horizon_hours,
        generated_from_timestamp_utc=generated_from_timestamp_utc,
    )
    logger.info("celery task completed task=generate_forecast_run run_id=%s", result.run_id)
    return {
        "forecast_run_id": result.run_id,
        "generated_from_timestamp_utc": result.generated_from_timestamp_utc,
        "forecast_horizon_hours": result.forecast_horizon_hours,
        "record_count": len(result.records),
    }


@shared_task(name="apps.monitoring.tasks.run_experiment_pipeline")
def run_experiment_pipeline(
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
):
    logger.info(
        "celery task started task=run_experiment_pipeline series_id=%s requested_by=%s name=%s",
        series_id,
        requested_by_id,
        name,
    )
    result = ExperimentService().run(
        requested_by=_get_requested_by(requested_by_id),
        series=_get_experiment_series(series_id),
        name=name,
        input_len_hours=input_len_hours,
        forecast_horizon_hours=forecast_horizon_hours,
        feature_columns=feature_columns,
        target_columns=target_columns,
        generated_from_timestamp_utc=generated_from_timestamp_utc,
        training_config=training_config,
    )
    logger.info(
        "celery task completed task=run_experiment_pipeline experiment_run_id=%s",
        result.experiment_run_id,
    )
    return asdict(result)
