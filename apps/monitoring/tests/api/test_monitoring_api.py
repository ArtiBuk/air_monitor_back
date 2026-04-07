from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from apps.monitoring.ml.dataset import DEFAULT_FEATURE_COLUMNS, DEFAULT_TARGET_COLUMNS
from apps.monitoring.models import ForecastRun, ModelVersion
from apps.monitoring.models import Observation as ObservationModel
from apps.monitoring.services.experiments import ExperimentRunResult
from apps.monitoring.services.forecasts import ForecastGenerationResult

pytestmark = pytest.mark.django_db


@patch("apps.monitoring.services.observations.PlumeCollector.collect")
@patch("apps.monitoring.services.observations.MyCityAirCollector.collect")
def test_collect_observations_persists_records_and_exposes_them(
    mycityair_collect,
    plume_collect,
    authenticated_client,
    json_post,
    mycityair_observation_factory,
    plume_observation_factory,
):
    mycityair_collect.return_value = [mycityair_observation_factory()]
    plume_collect.return_value = [plume_observation_factory()]

    collect_response = json_post(
        "/api/monitoring/observations/collect",
        {
            "start": "2026-03-31T09:00:00Z",
            "finish": "2026-03-31T11:00:00Z",
            "interval": "Interval1H",
            "window_hours": 1,
        },
    )

    assert collect_response.status_code == 200
    assert collect_response.json()["db_created_count"] == 2
    assert ObservationModel.objects.count() == 2

    list_response = authenticated_client.get("/api/monitoring/observations?limit=10")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 2


def test_monitoring_overview_exposes_real_counts_and_collection_config(
    authenticated_client,
    dataset_snapshot_factory,
    model_version_factory,
    forecast_run_factory,
    experiment_series_factory,
    experiment_run_factory,
    reference_observations_factory,
):
    reference_observations_factory(hours=24)
    dataset = dataset_snapshot_factory()
    model = model_version_factory(dataset=dataset)
    forecast = forecast_run_factory(model_version=model)
    series = experiment_series_factory()
    experiment_run_factory(series=series, dataset_snapshot=dataset, model_version=model, forecast_run=forecast)

    response = authenticated_client.get("/api/monitoring/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["counts"]["observations"] > 0
    assert payload["counts"]["datasets"] == 1
    assert payload["counts"]["models"] == 1
    assert payload["counts"]["forecasts"] == 1
    assert payload["counts"]["experiments"] == 1
    assert payload["counts"]["series"] == 1
    assert payload["counts"]["scheduled_tasks"] == 0
    assert payload["automatic_collection"]["lookback_hours"] == 48
    assert payload["automatic_collection"]["interval"] == "Interval1H"
    assert payload["automatic_collection"]["window_hours"] == 1
    assert payload["automatic_collection"]["schedule_minute"] == 5
    assert payload["automatic_collection"]["enabled_sources"] == ["mycityair", "plumelabs"]


@patch("apps.monitoring.services.observations.PlumeCollector.collect")
@patch("apps.monitoring.services.observations.MyCityAirCollector.collect")
def test_collect_observations_async_exposes_task_status(
    mycityair_collect,
    plume_collect,
    authenticated_client,
    json_post,
    mycityair_observation_factory,
    plume_observation_factory,
):
    mycityair_collect.return_value = [mycityair_observation_factory()]
    plume_collect.return_value = [plume_observation_factory()]

    response = json_post(
        "/api/monitoring/observations/collect/async",
        {
            "start": "2026-03-31T09:00:00Z",
            "finish": "2026-03-31T11:00:00Z",
            "interval": "Interval1H",
            "window_hours": 1,
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["operation"] == "collect_observations"

    status_response = authenticated_client.get(f"/api/monitoring/tasks/{payload['task_id']}")
    assert status_response.status_code == 200
    assert status_response.json()["successful"] is True
    assert status_response.json()["result"]["db_created_count"] == 2


@patch("apps.monitoring.tasks.ModelLifecycleService.build_dataset")
def test_build_dataset_async_exposes_task_status(
    build_dataset, authenticated_client, json_post, dataset_snapshot_factory
):
    snapshot = dataset_snapshot_factory(sample_count=32)
    build_dataset.return_value = snapshot

    response = json_post(
        "/api/monitoring/datasets/build/async",
        {
            "input_len_hours": 72,
            "forecast_horizon_hours": 24,
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["operation"] == "build_dataset"

    status_response = authenticated_client.get(f"/api/monitoring/tasks/{payload['task_id']}")
    assert status_response.status_code == 200
    assert status_response.json()["successful"] is True
    assert status_response.json()["result"]["dataset_id"] == str(snapshot.id)


@patch("apps.monitoring.tasks.ModelLifecycleService.train")
def test_train_model_async_exposes_task_status(train_model, authenticated_client, json_post, model_version_factory):
    model_version = model_version_factory()
    train_model.return_value = model_version

    response = json_post(
        "/api/monitoring/models/train/async",
        {
            "epochs": 5,
            "batch_size": 8,
            "lr": 0.001,
            "weight_decay": 0.0001,
            "patience": 2,
            "seed": 42,
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["operation"] == "train_model"

    status_response = authenticated_client.get(f"/api/monitoring/tasks/{payload['task_id']}")
    assert status_response.status_code == 200
    assert status_response.json()["successful"] is True
    assert status_response.json()["result"]["model_version_id"] == str(model_version.id)


@patch("apps.monitoring.tasks.ForecastService.generate")
def test_generate_forecast_async_exposes_task_status(generate_forecast, authenticated_client, json_post):
    generate_forecast.return_value = ForecastGenerationResult(
        run_id="forecast-run-1",
        generated_from_timestamp_utc="2026-03-31T12:00:00Z",
        forecast_horizon_hours=24,
        records=[{"timestamp_utc": "2026-03-31T13:00:00Z", "pm25": 12.5}],
    )

    response = json_post(
        "/api/monitoring/forecasts/generate/async",
        {
            "input_len_hours": 72,
            "forecast_horizon_hours": 24,
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["operation"] == "generate_forecast"

    status_response = authenticated_client.get(f"/api/monitoring/tasks/{payload['task_id']}")
    assert status_response.status_code == 200
    assert status_response.json()["successful"] is True
    assert status_response.json()["result"]["forecast_run_id"] == "forecast-run-1"


@patch("apps.monitoring.tasks.ExperimentService.run")
def test_run_experiment_async_exposes_task_status(run_experiment, authenticated_client, json_post):
    run_experiment.return_value = ExperimentRunResult(
        experiment_run_id="experiment-run-1",
        status="completed",
        dataset_snapshot_id="dataset-1",
        model_version_id="model-1",
        forecast_run_id="forecast-1",
        forecast_evaluation_id="evaluation-1",
        summary={"model_version": {"overall_rmse": 1.2}},
    )

    response = json_post(
        "/api/monitoring/experiments/run/async",
        {
            "name": "exp-async",
            "dataset": {
                "input_len_hours": 72,
                "forecast_horizon_hours": 24,
            },
            "training": {
                "epochs": 2,
                "batch_size": 8,
                "lr": 0.001,
                "weight_decay": 0.0001,
                "patience": 2,
                "seed": 42,
            },
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["operation"] == "run_experiment"

    status_response = authenticated_client.get(f"/api/monitoring/tasks/{payload['task_id']}")
    assert status_response.status_code == 200
    assert status_response.json()["successful"] is True
    assert status_response.json()["result"]["experiment_run_id"] == "experiment-run-1"


@patch("apps.monitoring.services.task_queue.execute_scheduled_monitoring_task.apply_async")
def test_collect_observations_async_can_schedule_for_later(
    apply_async,
    authenticated_client,
    json_post,
):
    apply_async.return_value.id = "scheduled-celery-task-1"
    apply_async.return_value.status = "PENDING"
    scheduled_for = (datetime.now(UTC) + timedelta(hours=2)).replace(microsecond=0)

    response = json_post(
        "/api/monitoring/observations/collect/async",
        {
            "start": "2026-03-31T09:00:00Z",
            "finish": "2026-03-31T11:00:00Z",
            "interval": "Interval1H",
            "window_hours": 1,
            "scheduled_for": scheduled_for.isoformat().replace("+00:00", "Z"),
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["operation"] == "collect_observations"
    assert payload["is_scheduled"] is True
    assert payload["scheduled_task_id"]
    assert payload["scheduled_for"] == scheduled_for.isoformat().replace("+00:00", "Z")

    detail_response = authenticated_client.get(f"/api/monitoring/scheduled-tasks/{payload['scheduled_task_id']}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["status"] == "scheduled"
    assert detail_payload["celery_task_id"] == "scheduled-celery-task-1"


@patch("apps.monitoring.services.task_queue.celery_app.control.revoke")
@patch("apps.monitoring.services.task_queue.execute_scheduled_monitoring_task.apply_async")
def test_scheduled_task_can_be_cancelled(apply_async, revoke, authenticated_client, json_post):
    apply_async.return_value.id = "scheduled-celery-task-2"
    apply_async.return_value.status = "PENDING"
    scheduled_for = (datetime.now(UTC) + timedelta(hours=3)).replace(microsecond=0)

    response = json_post(
        "/api/monitoring/datasets/build/async",
        {
            "input_len_hours": 72,
            "forecast_horizon_hours": 24,
            "scheduled_for": scheduled_for.isoformat().replace("+00:00", "Z"),
        },
    )

    assert response.status_code == 202
    scheduled_task_id = response.json()["scheduled_task_id"]

    cancel_response = json_post(
        f"/api/monitoring/scheduled-tasks/{scheduled_task_id}/cancel",
        {},
    )
    assert cancel_response.status_code == 200
    cancel_payload = cancel_response.json()
    assert cancel_payload["status"] == "cancelled"
    revoke.assert_called_once_with("scheduled-celery-task-2")


def test_monitoring_read_endpoints_expose_datasets_and_models(
    authenticated_client, dataset_snapshot_factory, model_version_factory
):
    dataset_snapshot_factory()
    model_version_factory()

    datasets_response = authenticated_client.get("/api/monitoring/datasets?limit=10")
    assert datasets_response.status_code == 200
    assert len(datasets_response.json()) == 2

    models_response = authenticated_client.get("/api/monitoring/models?limit=10")
    assert models_response.status_code == 200
    assert len(models_response.json()) == 1

    active_model_response = authenticated_client.get("/api/monitoring/models/active")
    assert active_model_response.status_code == 200
    assert active_model_response.json()["is_active"] is True


def test_active_model_endpoint_returns_best_ready_model(
    authenticated_client,
    dataset_snapshot_factory,
    model_version_factory,
    forecast_run_factory,
    forecast_evaluation_factory,
):
    weaker_model = model_version_factory(
        dataset=dataset_snapshot_factory(sample_count=120, master_row_count=220),
        name="older-model",
        is_active=True,
        metrics={"summary": {"overall_rmse": 1.9, "overall_mae": 1.15, "macro_mape": 0.31}},
    )
    better_model = model_version_factory(
        dataset=dataset_snapshot_factory(sample_count=180, master_row_count=300),
        name="best-model",
        is_active=False,
        metrics={"summary": {"overall_rmse": 1.4, "overall_mae": 0.86, "macro_mape": 0.24}},
    )
    forecast_evaluation_factory(
        forecast_run=forecast_run_factory(model_version=weaker_model),
        metrics={"summary": {"overall_rmse": 1.8, "overall_mae": 1.0, "macro_mape": 0.29}},
    )
    forecast_evaluation_factory(
        forecast_run=forecast_run_factory(model_version=better_model),
        metrics={"summary": {"overall_rmse": 1.05, "overall_mae": 0.67, "macro_mape": 0.18}},
    )

    response = authenticated_client.get("/api/monitoring/models/active")

    weaker_model.refresh_from_db()
    better_model.refresh_from_db()

    assert response.status_code == 200
    assert response.json()["id"] == str(better_model.id)
    assert response.json()["is_active"] is True
    assert weaker_model.is_active is False
    assert better_model.is_active is True


def test_monitoring_detail_endpoints_return_specific_entities(
    authenticated_client, dataset_snapshot_factory, model_version_factory
):
    dataset_snapshot = dataset_snapshot_factory()
    model_version = model_version_factory(dataset=dataset_snapshot)
    forecast_run = ForecastRun.objects.create(
        model_version=model_version,
        status=ForecastRun.Status.SUCCESS,
        forecast_horizon_hours=24,
        metadata={"record_count": 0},
    )

    dataset_response = authenticated_client.get(f"/api/monitoring/datasets/{dataset_snapshot.id}")
    assert dataset_response.status_code == 200
    assert dataset_response.json()["id"] == str(dataset_snapshot.id)

    model_response = authenticated_client.get(f"/api/monitoring/models/{model_version.id}")
    assert model_response.status_code == 200
    assert model_response.json()["id"] == str(model_version.id)
    assert model_response.json()["dataset"] == str(dataset_snapshot.id)

    forecast_response = authenticated_client.get(f"/api/monitoring/forecasts/{forecast_run.id}")
    assert forecast_response.status_code == 200
    assert forecast_response.json()["id"] == str(forecast_run.id)
    assert forecast_response.json()["model_version"] == str(model_version.id)

    compare_models_response = authenticated_client.get(f"/api/monitoring/models/compare?ids={model_version.id}")
    assert compare_models_response.status_code == 200
    assert compare_models_response.json()[0]["id"] == str(model_version.id)

    compare_forecasts_response = authenticated_client.get(f"/api/monitoring/forecasts/compare?ids={forecast_run.id}")
    assert compare_forecasts_response.status_code == 200
    assert compare_forecasts_response.json()[0]["id"] == str(forecast_run.id)


def test_monitoring_pipeline_e2e_on_reference_observations(
    authenticated_client,
    json_post,
    reference_observations_factory,
):
    reference_observations_factory(hours=144)

    dataset_response = json_post(
        "/api/monitoring/datasets/build",
        {
            "input_len_hours": 72,
            "forecast_horizon_hours": 24,
        },
    )
    assert dataset_response.status_code == 200
    dataset_payload = dataset_response.json()
    assert dataset_payload["sample_count"] > 0

    train_response = json_post(
        "/api/monitoring/models/train",
        {
            "dataset_snapshot_id": dataset_payload["id"],
            "epochs": 2,
            "batch_size": 8,
            "lr": 0.001,
            "weight_decay": 0.0001,
            "patience": 2,
            "seed": 42,
        },
    )
    assert train_response.status_code == 200
    model_payload = train_response.json()
    assert model_payload["status"] == ModelVersion.Status.READY
    assert model_payload["dataset"] == dataset_payload["id"]
    assert model_payload["is_active"] is True
    assert model_payload["training_config"]["epochs"] == 2
    assert model_payload["metrics"]["summary"]["overall_rmse"] >= 0
    assert "mycityair_aqi_mean" in model_payload["metrics"]["per_target"]

    forecast_response = json_post(
        "/api/monitoring/forecasts/generate",
        {
            "model_version_id": model_payload["id"],
            "input_len_hours": 72,
            "forecast_horizon_hours": 24,
        },
    )
    assert forecast_response.status_code == 200
    forecast_payload = forecast_response.json()
    assert forecast_payload["status"] == ForecastRun.Status.SUCCESS
    assert forecast_payload["model_version"] == model_payload["id"]
    assert len(forecast_payload["records"]) == 24

    dataset_detail_response = authenticated_client.get(f"/api/monitoring/datasets/{dataset_payload['id']}")
    assert dataset_detail_response.status_code == 200
    assert dataset_detail_response.json()["id"] == dataset_payload["id"]

    model_detail_response = authenticated_client.get(f"/api/monitoring/models/{model_payload['id']}")
    assert model_detail_response.status_code == 200
    assert model_detail_response.json()["id"] == model_payload["id"]

    forecast_detail_response = authenticated_client.get(f"/api/monitoring/forecasts/{forecast_payload['id']}")
    assert forecast_detail_response.status_code == 200
    assert forecast_detail_response.json()["id"] == forecast_payload["id"]
    assert len(forecast_detail_response.json()["records"]) == 24


def test_monitoring_backtest_and_evaluation_flow(
    authenticated_client,
    json_post,
    reference_observations_factory,
):
    reference_observations_factory(hours=168)

    dataset_response = json_post(
        "/api/monitoring/datasets/build",
        {
            "input_len_hours": 72,
            "forecast_horizon_hours": 24,
        },
    )
    assert dataset_response.status_code == 200
    dataset_payload = dataset_response.json()

    train_response = json_post(
        "/api/monitoring/models/train",
        {
            "dataset_snapshot_id": dataset_payload["id"],
            "epochs": 2,
            "batch_size": 8,
            "lr": 0.001,
            "weight_decay": 0.0001,
            "patience": 2,
            "seed": 42,
        },
    )
    assert train_response.status_code == 200
    model_payload = train_response.json()

    first_backtest_response = json_post(
        "/api/monitoring/forecasts/backtest",
        {
            "model_version_id": model_payload["id"],
            "input_len_hours": 72,
            "forecast_horizon_hours": 24,
            "generated_from_timestamp_utc": "2026-03-05T23:00:00Z",
        },
    )
    assert first_backtest_response.status_code == 200
    first_backtest_payload = first_backtest_response.json()
    assert first_backtest_payload["status"] == ForecastRun.Status.SUCCESS
    assert first_backtest_payload["generated_from_timestamp_utc"] == "2026-03-05T23:00:00Z"

    backtest_response = json_post(
        "/api/monitoring/forecasts/backtest",
        {
            "model_version_id": model_payload["id"],
            "input_len_hours": 72,
            "forecast_horizon_hours": 24,
            "generated_from_timestamp_utc": "2026-03-06T23:00:00Z",
        },
    )
    assert backtest_response.status_code == 200
    backtest_payload = backtest_response.json()
    assert backtest_payload["status"] == ForecastRun.Status.SUCCESS
    assert backtest_payload["generated_from_timestamp_utc"] == "2026-03-06T23:00:00Z"

    first_evaluation_response = authenticated_client.post(
        f"/api/monitoring/forecasts/{first_backtest_payload['id']}/evaluate"
    )
    assert first_evaluation_response.status_code == 200

    evaluation_response = authenticated_client.post(f"/api/monitoring/forecasts/{backtest_payload['id']}/evaluate")
    assert evaluation_response.status_code == 200
    evaluation_payload = evaluation_response.json()
    assert evaluation_payload["status"] == "completed"
    assert evaluation_payload["expected_record_count"] == 24
    assert evaluation_payload["matched_record_count"] == 24
    assert evaluation_payload["coverage_ratio"] == 1.0
    assert evaluation_payload["metrics"]["summary"]["overall_rmse"] >= 0
    assert "mycityair_aqi_mean" in evaluation_payload["metrics"]["per_target"]

    evaluation_detail_response = authenticated_client.get(
        f"/api/monitoring/forecasts/{backtest_payload['id']}/evaluation"
    )
    assert evaluation_detail_response.status_code == 200
    assert evaluation_detail_response.json()["forecast_run"] == backtest_payload["id"]

    evaluations_response = authenticated_client.get("/api/monitoring/forecasts/evaluations?limit=10")
    assert evaluations_response.status_code == 200
    assert len(evaluations_response.json()) == 2

    compare_evaluations_response = authenticated_client.get(
        "/api/monitoring/forecasts/evaluations/compare"
        f"?forecast_run_ids={first_backtest_payload['id']}"
        f"&forecast_run_ids={backtest_payload['id']}"
    )
    assert compare_evaluations_response.status_code == 200
    assert len(compare_evaluations_response.json()) == 2

    leaderboard_response = authenticated_client.get("/api/monitoring/models/leaderboard?metric=overall_rmse&limit=10")
    assert leaderboard_response.status_code == 200
    leaderboard_payload = leaderboard_response.json()
    assert len(leaderboard_payload) == 1
    assert leaderboard_payload[0]["model_version_id"] == model_payload["id"]
    assert leaderboard_payload[0]["evaluation_count"] == 2
    assert leaderboard_payload[0]["avg_overall_rmse"] >= 0


def test_monitoring_experiment_run_flow(authenticated_client, json_post, reference_observations_factory):
    reference_observations_factory(hours=168)
    feature_columns = list(DEFAULT_FEATURE_COLUMNS[:12])
    target_columns = list(DEFAULT_TARGET_COLUMNS[:3])

    series_response = json_post(
        "/api/monitoring/experiment-series",
        {
            "name": "series-thesis-baseline",
            "description": "Базовая серия экспериментов",
            "configuration": {
                "goal": "baseline comparison",
                "dataset": {
                    "input_len_hours": 72,
                    "forecast_horizon_hours": 24,
                },
            },
        },
    )
    assert series_response.status_code == 201
    series_payload = series_response.json()
    assert series_payload["name"] == "series-thesis-baseline"
    assert series_payload["summary"]["run_count"] == 0

    first_response = json_post(
        "/api/monitoring/experiments/run",
        {
            "name": "exp-short-window",
            "series_id": series_payload["id"],
            "dataset": {
                "input_len_hours": 72,
                "forecast_horizon_hours": 24,
                "feature_columns": feature_columns,
                "target_columns": target_columns,
            },
            "training": {
                "epochs": 2,
                "batch_size": 8,
                "lr": 0.001,
                "weight_decay": 0.0001,
                "patience": 2,
                "seed": 42,
            },
            "backtest": {
                "generated_from_timestamp_utc": "2026-03-05T23:00:00Z",
            },
        },
    )
    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert first_payload["status"] == "completed"
    assert first_payload["name"] == "exp-short-window"
    assert first_payload["series"] == series_payload["id"]
    assert first_payload["forecast_evaluation"] is not None
    assert first_payload["feature_columns"] == feature_columns
    assert first_payload["target_columns"] == target_columns
    assert first_payload["summary"]["dataset"]["sample_count"] > 0
    assert first_payload["summary"]["model_version"]["overall_rmse"] >= 0
    assert first_payload["summary"]["forecast_evaluation"]["overall_rmse"] >= 0

    second_response = json_post(
        "/api/monitoring/experiments/run",
        {
            "name": "exp-alt-seed",
            "series_id": series_payload["id"],
            "dataset": {
                "input_len_hours": 72,
                "forecast_horizon_hours": 24,
                "feature_columns": feature_columns,
                "target_columns": target_columns,
            },
            "training": {
                "epochs": 2,
                "batch_size": 8,
                "lr": 0.001,
                "weight_decay": 0.0001,
                "patience": 2,
                "seed": 7,
            },
            "backtest": {
                "generated_from_timestamp_utc": "2026-03-06T23:00:00Z",
            },
        },
    )
    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["status"] == "completed"
    assert second_payload["series"] == series_payload["id"]

    list_response = authenticated_client.get("/api/monitoring/experiments?limit=10")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 2

    filtered_list_response = authenticated_client.get(
        f"/api/monitoring/experiments?series_id={series_payload['id']}&limit=10"
    )
    assert filtered_list_response.status_code == 200
    assert len(filtered_list_response.json()) == 2

    detail_response = authenticated_client.get(f"/api/monitoring/experiments/{first_payload['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == first_payload["id"]

    compare_response = authenticated_client.get(
        f"/api/monitoring/experiments/compare?ids={first_payload['id']}&ids={second_payload['id']}"
    )
    assert compare_response.status_code == 200
    assert len(compare_response.json()) == 2

    series_list_response = authenticated_client.get("/api/monitoring/experiment-series?limit=10")
    assert series_list_response.status_code == 200
    assert len(series_list_response.json()) == 1

    series_detail_response = authenticated_client.get(f"/api/monitoring/experiment-series/{series_payload['id']}")
    assert series_detail_response.status_code == 200
    series_detail_payload = series_detail_response.json()
    assert series_detail_payload["id"] == series_payload["id"]
    assert series_detail_payload["summary"]["run_count"] == 2
    assert series_detail_payload["summary"]["completed_run_count"] == 2
    assert series_detail_payload["summary"]["best_experiment_run_id"] in {first_payload["id"], second_payload["id"]}

    series_runs_response = authenticated_client.get(
        f"/api/monitoring/experiment-series/{series_payload['id']}/runs?limit=10"
    )
    assert series_runs_response.status_code == 200
    assert len(series_runs_response.json()) == 2

    series_report_response = authenticated_client.get(
        f"/api/monitoring/experiment-series/{series_payload['id']}/report"
    )
    assert series_report_response.status_code == 200
    series_report_payload = series_report_response.json()
    assert series_report_payload["series"]["id"] == series_payload["id"]
    assert len(series_report_payload["runs"]) == 2
    assert series_report_payload["aggregates"]["run_count"] == 2
    assert series_report_payload["aggregates"]["avg_training_overall_rmse"] >= 0
    assert series_report_payload["aggregates"]["avg_backtest_overall_rmse"] >= 0

    compare_series_response = authenticated_client.get(
        f"/api/monitoring/experiment-series/compare?ids={series_payload['id']}"
    )
    assert compare_series_response.status_code == 200
    assert len(compare_series_response.json()) == 1

    compare_series_reports_response = authenticated_client.get(
        f"/api/monitoring/experiment-series/reports/compare?ids={series_payload['id']}"
    )
    assert compare_series_reports_response.status_code == 200
    assert len(compare_series_reports_response.json()) == 1
    assert compare_series_reports_response.json()[0]["series"]["id"] == series_payload["id"]
