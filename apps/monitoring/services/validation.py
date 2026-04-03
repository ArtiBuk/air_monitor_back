import hashlib
import json
from datetime import UTC

import pandas as pd

from apps.monitoring.ml.dataset import DEFAULT_FEATURE_COLUMNS, DEFAULT_TARGET_COLUMNS
from apps.monitoring.models import ExperimentRun, ExperimentSeries


def normalize_feature_columns(feature_columns: list[str] | None) -> list[str]:
    """Нормализует список признаков для датасета и эксперимента."""
    return _normalize_columns(
        columns=feature_columns,
        default_columns=DEFAULT_FEATURE_COLUMNS,
        field_name="feature_columns",
    )


def normalize_target_columns(target_columns: list[str] | None) -> list[str]:
    """Нормализует список целевых признаков для датасета и эксперимента."""
    return _normalize_columns(
        columns=target_columns,
        default_columns=DEFAULT_TARGET_COLUMNS,
        field_name="target_columns",
    )


def validate_dataset_request(
    *,
    master_columns: list[str],
    master_row_count: int,
    input_len_hours: int,
    forecast_horizon_hours: int,
    feature_columns: list[str],
    target_columns: list[str],
) -> None:
    """Проверяет, что датасет можно собрать из текущего master dataset."""
    if input_len_hours <= 0:
        raise ValueError("input_len_hours должен быть больше 0.")
    if forecast_horizon_hours <= 0:
        raise ValueError("forecast_horizon_hours должен быть больше 0.")

    if not feature_columns:
        raise ValueError("feature_columns не может быть пустым.")
    if not target_columns:
        raise ValueError("target_columns не может быть пустым.")

    available_columns = set(master_columns)
    missing_features = sorted(set(feature_columns) - available_columns)
    missing_targets = sorted(set(target_columns) - available_columns)

    if missing_features:
        raise ValueError(f"В master dataset отсутствуют признаки: {missing_features}.")
    if missing_targets:
        raise ValueError(f"В master dataset отсутствуют таргеты: {missing_targets}.")

    minimum_row_count = input_len_hours + forecast_horizon_hours + 2
    if master_row_count < minimum_row_count:
        max_input_len_hours = max(master_row_count - forecast_horizon_hours - 2, 0)
        raise ValueError(
            "Недостаточно наблюдений для построения датасета: "
            f"нужно минимум {minimum_row_count} часовых точек, доступно {master_row_count}. "
            f"При текущем горизонте {forecast_horizon_hours} ч максимально допустимое input_len_hours = {max_input_len_hours}. "
            "Для конфигурации 72/24 обычно нужно собрать хотя бы 98-120 часовых точек истории."
        )


def normalize_training_config(training_config: dict) -> dict:
    """Проверяет и приводит конфигурацию обучения к стабильному виду."""
    normalized = {
        "epochs": int(training_config["epochs"]),
        "batch_size": int(training_config["batch_size"]),
        "lr": float(training_config["lr"]),
        "weight_decay": float(training_config["weight_decay"]),
        "patience": int(training_config["patience"]),
        "seed": int(training_config["seed"]),
    }

    for key in ("epochs", "batch_size", "patience"):
        if normalized[key] <= 0:
            raise ValueError(f"{key} должен быть больше 0.")
    for key in ("lr", "weight_decay"):
        if normalized[key] < 0:
            raise ValueError(f"{key} не может быть отрицательным.")

    return normalized


def validate_series_name(name: str) -> str:
    """Проверяет имя серии экспериментов."""
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Название серии экспериментов не может быть пустым.")
    if ExperimentSeries.objects.filter(name__iexact=normalized_name).exists():
        raise ValueError("Серия экспериментов с таким названием уже существует.")
    return normalized_name


def ensure_series_accepts_runs(series: ExperimentSeries) -> None:
    """Проверяет, что в серию можно добавлять новые запуски."""
    if series.status != ExperimentSeries.Status.ACTIVE:
        raise ValueError("Новые запуски можно добавлять только в активную серию экспериментов.")


def build_experiment_run_fingerprint(
    *,
    series_id: str | None,
    input_len_hours: int,
    forecast_horizon_hours: int,
    feature_columns: list[str],
    target_columns: list[str],
    training_config: dict,
    generated_from_timestamp_utc=None,
) -> str:
    """Строит стабильный отпечаток конфигурации experiment run."""
    payload = {
        "series_id": str(series_id) if series_id is not None else None,
        "input_len_hours": int(input_len_hours),
        "forecast_horizon_hours": int(forecast_horizon_hours),
        "feature_columns": list(feature_columns),
        "target_columns": list(target_columns),
        "training_config": normalize_training_config(training_config),
        "generated_from_timestamp_utc": _serialize_timestamp(generated_from_timestamp_utc),
    }
    raw_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()


def ensure_no_conflicting_experiment_run(*, series: ExperimentSeries | None, config_fingerprint: str) -> None:
    """Не даёт запускать одинаковый experiment run параллельно."""
    queryset = ExperimentRun.objects.filter(
        status=ExperimentRun.Status.PENDING,
        config_fingerprint=config_fingerprint,
    )
    if series is None:
        queryset = queryset.filter(series__isnull=True)
    else:
        queryset = queryset.filter(series=series)

    if queryset.exists():
        raise ValueError("Уже есть незавершенный experiment run с такой конфигурацией.")


def serialize_backtest_config(*, generated_from_timestamp_utc) -> dict:
    """Собирает конфигурацию backtest для хранения в ExperimentRun."""
    return {"generated_from_timestamp_utc": _serialize_timestamp(generated_from_timestamp_utc)}


def build_experiment_run_summary(
    *,
    dataset_snapshot,
    model_version,
    forecast_run=None,
    forecast_evaluation=None,
) -> dict:
    """Собирает компактную сводку experiment run без дублирования полных метрик."""
    summary = {
        "dataset": {
            "id": str(dataset_snapshot.id),
            "sample_count": dataset_snapshot.sample_count,
            "master_row_count": dataset_snapshot.master_row_count,
        },
        "model_version": {
            "id": str(model_version.id),
            "status": model_version.status,
            "overall_rmse": model_version.metrics.get("summary", {}).get("overall_rmse"),
            "overall_mae": model_version.metrics.get("summary", {}).get("overall_mae"),
        },
    }

    if forecast_run is not None:
        summary["forecast_run"] = {
            "id": str(forecast_run.id),
            "status": forecast_run.status,
            "generated_from_timestamp_utc": (
                forecast_run.generated_from_timestamp_utc.astimezone(UTC).isoformat().replace("+00:00", "Z")
                if forecast_run.generated_from_timestamp_utc is not None
                else None
            ),
        }

    if forecast_evaluation is not None:
        summary["forecast_evaluation"] = {
            "id": str(forecast_evaluation.id),
            "status": forecast_evaluation.status,
            "coverage_ratio": forecast_evaluation.coverage_ratio,
            "overall_rmse": forecast_evaluation.metrics.get("summary", {}).get("overall_rmse"),
            "overall_mae": forecast_evaluation.metrics.get("summary", {}).get("overall_mae"),
            "macro_mape": forecast_evaluation.metrics.get("summary", {}).get("macro_mape"),
        }

    return summary


def _normalize_columns(*, columns: list[str] | None, default_columns: list[str], field_name: str) -> list[str]:
    if columns is None:
        return list(default_columns)

    normalized_columns = []
    for column in columns:
        normalized_column = str(column).strip()
        if normalized_column:
            normalized_columns.append(normalized_column)

    if not normalized_columns:
        raise ValueError(f"{field_name} не может быть пустым.")

    return list(dict.fromkeys(normalized_columns))


def _serialize_timestamp(value) -> str | None:
    if value is None:
        return None

    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(UTC)
    else:
        timestamp = timestamp.tz_convert(UTC)
    return timestamp.isoformat().replace("+00:00", "Z")
