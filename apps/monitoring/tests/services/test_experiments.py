import pytest

from apps.monitoring.models import ExperimentRun, ExperimentSeries
from apps.monitoring.services.experiments import ExperimentService
from apps.monitoring.services.series import build_experiment_series_report, create_experiment_series
from apps.monitoring.services.validation import build_experiment_run_fingerprint

pytestmark = pytest.mark.django_db


def test_create_experiment_series_rejects_case_insensitive_duplicates(experiment_series_factory):
    experiment_series_factory(name="Baseline-Series")

    with pytest.raises(ValueError, match="Серия экспериментов с таким названием уже существует"):
        create_experiment_series(
            requested_by=None,
            name="baseline-series",
            description="Дубликат",
            configuration={"goal": "duplicate"},
        )


def test_experiment_service_rejects_conflicting_pending_run(experiment_series_factory):
    series = experiment_series_factory(name="series-conflict")
    config_fingerprint = build_experiment_run_fingerprint(
        series_id=str(series.id),
        input_len_hours=72,
        forecast_horizon_hours=24,
        feature_columns=["plume_pm25", "plume_pm10"],
        target_columns=["plume_pm25"],
        training_config={
            "epochs": 2,
            "batch_size": 8,
            "lr": 0.001,
            "weight_decay": 0.0001,
            "patience": 2,
            "seed": 42,
        },
        generated_from_timestamp_utc=None,
    )
    ExperimentRun.objects.create(
        series=series,
        name="pending-run",
        status=ExperimentRun.Status.PENDING,
        input_len_hours=72,
        forecast_horizon_hours=24,
        feature_columns=["plume_pm25", "plume_pm10"],
        target_columns=["plume_pm25"],
        training_config={
            "epochs": 2,
            "batch_size": 8,
            "lr": 0.001,
            "weight_decay": 0.0001,
            "patience": 2,
            "seed": 42,
        },
        backtest_config={"generated_from_timestamp_utc": None},
        config_fingerprint=config_fingerprint,
    )

    with pytest.raises(ValueError, match="Уже есть незавершенный experiment run с такой конфигурацией"):
        ExperimentService().run(
            requested_by=None,
            name="duplicate-run",
            series=series,
            input_len_hours=72,
            forecast_horizon_hours=24,
            feature_columns=["plume_pm25", "plume_pm10"],
            target_columns=["plume_pm25"],
            training_config={
                "epochs": 2,
                "batch_size": 8,
                "lr": 0.001,
                "weight_decay": 0.0001,
                "patience": 2,
                "seed": 42,
            },
            generated_from_timestamp_utc=None,
        )


def test_experiment_service_rejects_non_active_series(experiment_series_factory):
    series = experiment_series_factory(
        name="series-archived",
        status=ExperimentSeries.Status.ARCHIVED,
    )

    with pytest.raises(ValueError, match="только в активную серию экспериментов"):
        ExperimentService().run(
            requested_by=None,
            name="archived-run",
            series=series,
            input_len_hours=72,
            forecast_horizon_hours=24,
            feature_columns=["plume_pm25", "plume_pm10"],
            target_columns=["plume_pm25"],
            training_config={
                "epochs": 2,
                "batch_size": 8,
                "lr": 0.001,
                "weight_decay": 0.0001,
                "patience": 2,
                "seed": 42,
            },
            generated_from_timestamp_utc=None,
        )


def test_series_report_uses_linked_metrics_instead_of_run_summary(
    experiment_series_factory,
    experiment_run_factory,
    dataset_snapshot_factory,
):
    series = experiment_series_factory(name="series-report")
    dataset_snapshot = dataset_snapshot_factory(
        feature_columns=["plume_pm25", "plume_pm10"],
        target_columns=["plume_pm25"],
    )
    run = experiment_run_factory(
        series=series,
        dataset_snapshot=dataset_snapshot,
        summary={},
    )
    run.model_version.metrics = {
        "summary": {
            "overall_rmse": 2.5,
        }
    }
    run.model_version.save(update_fields=["metrics", "updated_at"])
    run.forecast_evaluation.metrics = {
        "summary": {
            "overall_rmse": 1.5,
            "overall_mae": 1.0,
            "macro_mape": 0.2,
        }
    }
    run.forecast_evaluation.save(update_fields=["metrics", "updated_at"])

    report = build_experiment_series_report(series=series, runs=[run])

    assert report["aggregates"]["avg_training_overall_rmse"] == 2.5
    assert report["aggregates"]["avg_backtest_overall_rmse"] == 1.5
    assert report["aggregates"]["avg_backtest_overall_mae"] == 1.0
    assert report["aggregates"]["avg_backtest_macro_mape"] == 0.2
