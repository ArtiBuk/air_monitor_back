from dataclasses import dataclass

from apps.monitoring.models import ExperimentRun

from .evaluation import ForecastEvaluationService
from .forecasts import ForecastService
from .series import sync_experiment_series_summary
from .training import ModelLifecycleService
from .validation import (
    build_experiment_run_fingerprint,
    build_experiment_run_summary,
    ensure_no_conflicting_experiment_run,
    ensure_series_accepts_runs,
    normalize_feature_columns,
    normalize_target_columns,
    normalize_training_config,
    serialize_backtest_config,
)


@dataclass
class ExperimentRunResult:
    experiment_run_id: str
    status: str
    dataset_snapshot_id: str | None
    model_version_id: str | None
    forecast_run_id: str | None
    forecast_evaluation_id: str | None
    summary: dict


class ExperimentService:
    def run(
        self,
        *,
        requested_by=None,
        name: str,
        input_len_hours: int,
        forecast_horizon_hours: int,
        feature_columns: list[str] | None,
        target_columns: list[str] | None,
        training_config: dict,
        generated_from_timestamp_utc=None,
        series=None,
    ) -> ExperimentRunResult:
        """Запускает эксперимент обучения модели и при необходимости backtest."""
        normalized_name = name.strip() or "experiment"
        feature_columns = normalize_feature_columns(feature_columns)
        target_columns = normalize_target_columns(target_columns)
        training_config = normalize_training_config(training_config)
        if series is not None:
            ensure_series_accepts_runs(series)

        config_fingerprint = build_experiment_run_fingerprint(
            series_id=str(series.id) if series is not None else None,
            input_len_hours=input_len_hours,
            forecast_horizon_hours=forecast_horizon_hours,
            feature_columns=feature_columns,
            target_columns=target_columns,
            training_config=training_config,
            generated_from_timestamp_utc=generated_from_timestamp_utc,
        )
        ensure_no_conflicting_experiment_run(series=series, config_fingerprint=config_fingerprint)

        experiment_run = ExperimentRun.objects.create(
            requested_by=requested_by,
            series=series,
            name=normalized_name,
            status=ExperimentRun.Status.PENDING,
            input_len_hours=input_len_hours,
            forecast_horizon_hours=forecast_horizon_hours,
            feature_columns=feature_columns,
            target_columns=target_columns,
            training_config=training_config,
            backtest_config=serialize_backtest_config(generated_from_timestamp_utc=generated_from_timestamp_utc),
            config_fingerprint=config_fingerprint,
        )

        lifecycle_service = ModelLifecycleService()
        dataset_snapshot = None
        model_version = None
        forecast_run = None
        forecast_evaluation = None

        try:
            dataset_snapshot = lifecycle_service.build_dataset(
                input_len_hours=input_len_hours,
                forecast_horizon_hours=forecast_horizon_hours,
                feature_columns=feature_columns,
                target_columns=target_columns,
            )
            model_version = lifecycle_service.train(
                dataset_snapshot=dataset_snapshot,
                requested_by=requested_by,
                epochs=training_config["epochs"],
                batch_size=training_config["batch_size"],
                lr=training_config["lr"],
                weight_decay=training_config["weight_decay"],
                patience=training_config["patience"],
                seed=training_config["seed"],
            )

            if generated_from_timestamp_utc is not None:
                forecast_result = ForecastService().generate(
                    requested_by=requested_by,
                    input_len_hours=input_len_hours,
                    forecast_horizon_hours=forecast_horizon_hours,
                    model_version=model_version,
                    generated_from_timestamp_utc=generated_from_timestamp_utc,
                )
                forecast_run = model_version.forecast_runs.get(id=forecast_result.run_id)
                ForecastEvaluationService().evaluate(forecast_run=forecast_run)
                forecast_evaluation = forecast_run.evaluation

            experiment_run.status = ExperimentRun.Status.COMPLETED
            experiment_run.dataset_snapshot = dataset_snapshot
            experiment_run.model_version = model_version
            experiment_run.forecast_run = forecast_run
            experiment_run.forecast_evaluation = forecast_evaluation
            experiment_run.summary = build_experiment_run_summary(
                dataset_snapshot=dataset_snapshot,
                model_version=model_version,
                forecast_run=forecast_run,
                forecast_evaluation=forecast_evaluation,
            )
            experiment_run.error_message = ""
            experiment_run.save(
                update_fields=[
                    "series",
                    "status",
                    "dataset_snapshot",
                    "model_version",
                    "forecast_run",
                    "forecast_evaluation",
                    "config_fingerprint",
                    "summary",
                    "error_message",
                    "updated_at",
                ]
            )
            if series is not None:
                sync_experiment_series_summary(series=series)
        except Exception as exc:
            experiment_run.status = ExperimentRun.Status.FAILED
            experiment_run.dataset_snapshot = dataset_snapshot
            experiment_run.model_version = model_version
            experiment_run.forecast_run = forecast_run
            experiment_run.forecast_evaluation = forecast_evaluation
            experiment_run.error_message = str(exc)
            experiment_run.save(
                update_fields=[
                    "series",
                    "status",
                    "dataset_snapshot",
                    "model_version",
                    "forecast_run",
                    "forecast_evaluation",
                    "config_fingerprint",
                    "error_message",
                    "updated_at",
                ]
            )
            if series is not None:
                sync_experiment_series_summary(series=series)
            raise

        return ExperimentRunResult(
            experiment_run_id=str(experiment_run.id),
            status=experiment_run.status,
            dataset_snapshot_id=str(dataset_snapshot.id) if dataset_snapshot else None,
            model_version_id=str(model_version.id) if model_version else None,
            forecast_run_id=str(forecast_run.id) if forecast_run else None,
            forecast_evaluation_id=str(forecast_evaluation.id) if forecast_evaluation else None,
            summary=experiment_run.summary,
        )
