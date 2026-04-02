import math
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from apps.monitoring.ingestion.types import Observation
from apps.monitoring.models import (
    DatasetSnapshot,
    ExperimentRun,
    ExperimentSeries,
    ForecastEvaluation,
    ForecastRun,
    ModelVersion,
)
from apps.monitoring.models import Observation as ObservationModel
from apps.monitoring.services.utils import build_observation_fingerprint


def build_monitoring_auth_payload(**overrides) -> dict:
    payload = {
        "email": "monitor@example.com",
        "password": "pass12345",
        "first_name": "Monitor",
        "last_name": "User",
    }
    payload.update(overrides)
    return payload


def build_mycityair_observation(**overrides) -> Observation:
    payload = {
        "source": "mycityair",
        "source_kind": "api",
        "station_id": "station-1",
        "station_name": "Station 1",
        "lat": 69.3558,
        "lon": 88.1893,
        "observed_at_utc": "2026-03-31T10:30:00Z",
        "time_bucket_utc": "2026-03-31T10:00:00Z",
        "time_window_utc": "2026-03-31T10:00:00Z",
        "metric": "aqi",
        "value": 75,
        "unit": "index",
        "extra": {"provider": "mycityair"},
    }
    payload.update(overrides)
    return Observation(**payload)


def build_plume_observation(**overrides) -> Observation:
    payload = {
        "source": "plumelabs",
        "source_kind": "embedded_js",
        "station_id": None,
        "station_name": "Norilsk",
        "lat": None,
        "lon": None,
        "observed_at_utc": "2026-03-31T10:30:00Z",
        "time_bucket_utc": "2026-03-31T10:00:00Z",
        "time_window_utc": "2026-03-31T10:00:00Z",
        "metric": "pm25",
        "value": 18.5,
        "unit": "µg/m3",
        "extra": {"provider": "plume"},
    }
    payload.update(overrides)
    return Observation(**payload)


def create_dataset_snapshot(**overrides) -> DatasetSnapshot:
    payload = {
        "input_len_hours": 72,
        "forecast_horizon_hours": 24,
        "master_row_count": 100,
        "sample_count": 10,
        "feature_columns": ["feature_1"],
        "target_columns": ["target_1"],
        "metadata": {"source": "test"},
        "payload_npz": b"dataset",
    }
    payload.update(overrides)
    return DatasetSnapshot.objects.create(**payload)


def create_model_version(**overrides) -> ModelVersion:
    dataset = overrides.pop("dataset", None) or create_dataset_snapshot()
    payload = {
        "dataset": dataset,
        "name": "model-test",
        "status": ModelVersion.Status.READY,
        "input_len_hours": dataset.input_len_hours,
        "forecast_horizon_hours": dataset.forecast_horizon_hours,
        "feature_names": ["feature_1"],
        "target_names": ["target_1"],
        "training_config": {},
        "metrics": {},
        "history": {},
        "checkpoint_blob": b"checkpoint",
        "is_active": True,
    }
    payload.update(overrides)
    return ModelVersion.objects.create(**payload)


def create_experiment_series(**overrides) -> ExperimentSeries:
    payload = {
        "name": f"series-{uuid4()}",
        "description": "Тестовая серия",
        "configuration": {"goal": "tests"},
        "summary": {
            "run_count": 0,
            "completed_run_count": 0,
            "failed_run_count": 0,
            "latest_experiment_run_id": None,
            "best_experiment_run_id": None,
            "best_backtest_overall_rmse": None,
        },
    }
    payload.update(overrides)
    return ExperimentSeries.objects.create(**payload)


def create_forecast_run(**overrides) -> ForecastRun:
    model_version = overrides.pop("model_version", None) or create_model_version()
    payload = {
        "model_version": model_version,
        "status": ForecastRun.Status.SUCCESS,
        "forecast_horizon_hours": model_version.forecast_horizon_hours,
        "metadata": {"record_count": 24},
    }
    payload.update(overrides)
    return ForecastRun.objects.create(**payload)


def create_forecast_evaluation(**overrides) -> ForecastEvaluation:
    forecast_run = overrides.pop("forecast_run", None) or create_forecast_run()
    payload = {
        "forecast_run": forecast_run,
        "status": ForecastEvaluation.Status.COMPLETED,
        "expected_record_count": 24,
        "matched_record_count": 24,
        "coverage_ratio": 1.0,
        "metrics": {
            "summary": {
                "overall_rmse": 1.0,
                "overall_mae": 0.8,
                "macro_mape": 0.1,
            }
        },
    }
    payload.update(overrides)
    return ForecastEvaluation.objects.create(**payload)


def create_experiment_run(**overrides) -> ExperimentRun:
    dataset_snapshot = overrides.pop("dataset_snapshot", None) or create_dataset_snapshot()
    model_version = overrides.pop("model_version", None) or create_model_version(dataset=dataset_snapshot)
    forecast_run = overrides.pop("forecast_run", None) or create_forecast_run(model_version=model_version)
    forecast_evaluation = overrides.pop("forecast_evaluation", None) or create_forecast_evaluation(
        forecast_run=forecast_run
    )
    payload = {
        "name": "experiment-default",
        "status": ExperimentRun.Status.COMPLETED,
        "dataset_snapshot": dataset_snapshot,
        "model_version": model_version,
        "forecast_run": forecast_run,
        "forecast_evaluation": forecast_evaluation,
        "input_len_hours": dataset_snapshot.input_len_hours,
        "forecast_horizon_hours": dataset_snapshot.forecast_horizon_hours,
        "feature_columns": list(dataset_snapshot.feature_columns),
        "target_columns": list(dataset_snapshot.target_columns),
        "training_config": {
            "epochs": 2,
            "batch_size": 8,
            "lr": 0.001,
            "weight_decay": 0.0001,
            "patience": 2,
            "seed": 42,
        },
        "backtest_config": {"generated_from_timestamp_utc": "2026-03-05T23:00:00Z"},
        "summary": {},
    }
    payload.update(overrides)
    return ExperimentRun.objects.create(**payload)


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_observation_record(
    *,
    source: str,
    source_kind: str,
    station_id: str,
    station_name: str,
    lat: float | None,
    lon: float | None,
    observed_at_utc: datetime,
    time_bucket_utc: datetime,
    time_window_utc: datetime,
    metric: str,
    value: float,
    unit: str,
    extra: dict,
) -> ObservationModel:
    observed_at_str = _isoformat_utc(observed_at_utc)
    time_bucket_str = _isoformat_utc(time_bucket_utc)
    time_window_str = _isoformat_utc(time_window_utc)
    fingerprint = build_observation_fingerprint(
        (
            source,
            station_id,
            station_name,
            lat,
            lon,
            observed_at_str,
            time_bucket_str,
            time_window_str,
            metric,
            float(value),
            unit,
        )
    )
    return ObservationModel(
        fingerprint=fingerprint,
        source=source,
        source_kind=source_kind,
        station_id=station_id,
        station_name=station_name,
        lat=lat,
        lon=lon,
        observed_at_utc=observed_at_utc,
        time_bucket_utc=time_bucket_utc,
        time_window_utc=time_window_utc,
        metric=metric,
        value=float(value),
        unit=unit,
        extra=extra,
    )


def create_reference_observations(
    *, start: datetime | None = None, hours: int = 168, station_count: int = 4
) -> list[ObservationModel]:
    start = start or datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    station_offsets = [-6.0, -2.0, 3.0, 6.0][:station_count]

    records: list[ObservationModel] = []

    for hour_idx in range(hours):
        bucket = start + timedelta(hours=hour_idx)
        observed = bucket + timedelta(minutes=30)

        base_daily = math.sin(2 * math.pi * hour_idx / 24.0)
        base_weekly = math.cos(2 * math.pi * hour_idx / 168.0)

        base_aqi = 82.0 + 18.0 * base_daily + 9.0 * base_weekly
        pm25 = max(6.0, 18.0 + 7.0 * base_daily + 3.0 * base_weekly)
        pm10 = max(pm25 + 4.0, 28.0 + 8.0 * base_daily + 4.0 * base_weekly)
        no2 = max(4.0, 14.0 + 5.0 * math.cos(2 * math.pi * hour_idx / 18.0))
        so2 = max(1.0, 6.0 + 2.2 * math.sin(2 * math.pi * hour_idx / 36.0))
        o3 = max(2.0, 11.0 + 4.5 * math.sin(2 * math.pi * (hour_idx + 4) / 30.0))
        co = max(25.0, 115.0 + 16.0 * math.cos(2 * math.pi * hour_idx / 20.0))
        plume_index = max(1.0, 0.35 * pm25 + 0.30 * pm10 + 0.20 * no2 + 0.15 * o3)

        for station_idx, station_offset in enumerate(station_offsets, start=1):
            station_value = max(
                15.0,
                base_aqi + station_offset + 1.5 * math.sin(2 * math.pi * (hour_idx + station_idx) / 12.0),
            )
            records.append(
                _build_observation_record(
                    source="mycityair",
                    source_kind="api",
                    station_id=f"station-{station_idx}",
                    station_name=f"Station {station_idx}",
                    lat=69.3558 + station_idx * 0.002,
                    lon=88.1893 + station_idx * 0.002,
                    observed_at_utc=observed,
                    time_bucket_utc=bucket,
                    time_window_utc=bucket,
                    metric="aqi",
                    value=station_value,
                    unit="index",
                    extra={"provider": "mycityair", "station_index": station_idx},
                )
            )

        plume_metrics = {
            "plume_index": plume_index,
            "pm25": pm25,
            "pm10": pm10,
            "no2": no2,
            "so2": so2,
            "o3": o3,
            "co": co,
        }
        plume_units = {
            "plume_index": "index",
            "pm25": "µg/m3",
            "pm10": "µg/m3",
            "no2": "µg/m3",
            "so2": "µg/m3",
            "o3": "µg/m3",
            "co": "µg/m3",
        }

        for metric, value in plume_metrics.items():
            records.append(
                _build_observation_record(
                    source="plumelabs",
                    source_kind="embedded_js",
                    station_id="",
                    station_name="Norilsk",
                    lat=None,
                    lon=None,
                    observed_at_utc=observed,
                    time_bucket_utc=bucket,
                    time_window_utc=bucket,
                    metric=metric,
                    value=value,
                    unit=plume_units[metric],
                    extra={"provider": "plume", "metric": metric},
                )
            )

    ObservationModel.objects.bulk_create(records)
    return records
