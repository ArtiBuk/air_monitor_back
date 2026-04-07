import pytest

from apps.monitoring.services.model_selection import ModelSelectionService
from apps.monitoring.services.reporting import build_model_leaderboard

pytestmark = pytest.mark.django_db


def test_model_leaderboard_ranks_ready_models_with_backtest_metrics(
    dataset_snapshot_factory,
    model_version_factory,
    forecast_run_factory,
    forecast_evaluation_factory,
):
    weaker_dataset = dataset_snapshot_factory(sample_count=120, master_row_count=240)
    stronger_dataset = dataset_snapshot_factory(sample_count=180, master_row_count=300)
    training_only_dataset = dataset_snapshot_factory(sample_count=140, master_row_count=260)

    weaker_model = model_version_factory(
        dataset=weaker_dataset,
        name="weaker-model",
        is_active=True,
        metrics={"summary": {"overall_rmse": 1.8, "overall_mae": 1.1, "macro_mape": 0.32}},
    )
    stronger_model = model_version_factory(
        dataset=stronger_dataset,
        name="stronger-model",
        is_active=False,
        metrics={"summary": {"overall_rmse": 1.5, "overall_mae": 0.9, "macro_mape": 0.24}},
    )
    model_version_factory(
        dataset=training_only_dataset,
        name="training-only-model",
        is_active=False,
        metrics={"summary": {"overall_rmse": 1.6, "overall_mae": 0.95, "macro_mape": 0.27}},
    )

    weaker_run = forecast_run_factory(model_version=weaker_model)
    stronger_run = forecast_run_factory(model_version=stronger_model)
    forecast_evaluation_factory(
        forecast_run=weaker_run,
        metrics={"summary": {"overall_rmse": 1.7, "overall_mae": 1.0, "macro_mape": 0.3}},
    )
    forecast_evaluation_factory(
        forecast_run=stronger_run,
        metrics={"summary": {"overall_rmse": 1.1, "overall_mae": 0.72, "macro_mape": 0.18}},
    )

    leaderboard = build_model_leaderboard(metric="overall_rmse")

    assert [item["model_name"] for item in leaderboard[:3]] == [
        "stronger-model",
        "weaker-model",
        "training-only-model",
    ]
    assert leaderboard[0]["metric_source"] == "backtest"
    assert leaderboard[0]["dataset_sample_count"] == 180
    assert leaderboard[2]["metric_source"] == "training"
    assert leaderboard[0]["rank"] == 1


def test_ensure_best_model_is_active_switches_flags_to_best_candidate(
    dataset_snapshot_factory,
    model_version_factory,
    forecast_run_factory,
    forecast_evaluation_factory,
):
    old_model = model_version_factory(
        dataset=dataset_snapshot_factory(sample_count=128, master_row_count=220),
        name="old-active",
        is_active=True,
        metrics={"summary": {"overall_rmse": 2.1, "overall_mae": 1.4, "macro_mape": 0.38}},
    )
    best_model = model_version_factory(
        dataset=dataset_snapshot_factory(sample_count=192, master_row_count=320),
        name="best-model",
        is_active=False,
        metrics={"summary": {"overall_rmse": 1.4, "overall_mae": 0.88, "macro_mape": 0.22}},
    )

    forecast_evaluation_factory(
        forecast_run=forecast_run_factory(model_version=old_model),
        metrics={"summary": {"overall_rmse": 2.0, "overall_mae": 1.3, "macro_mape": 0.35}},
    )
    forecast_evaluation_factory(
        forecast_run=forecast_run_factory(model_version=best_model),
        metrics={"summary": {"overall_rmse": 1.0, "overall_mae": 0.63, "macro_mape": 0.17}},
    )

    selected_model = ModelSelectionService().ensure_best_model_is_active()

    old_model.refresh_from_db()
    best_model.refresh_from_db()

    assert selected_model is not None
    assert selected_model.id == best_model.id
    assert best_model.is_active is True
    assert old_model.is_active is False
