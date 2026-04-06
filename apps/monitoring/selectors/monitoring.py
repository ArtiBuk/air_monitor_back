from django.conf import settings

from apps.monitoring.models import (
    DatasetSnapshot,
    ExperimentRun,
    ExperimentSeries,
    ForecastEvaluation,
    ForecastRun,
    ModelVersion,
    Observation,
    ScheduledMonitoringTask,
)


def list_observations(*, metric=None, source=None, start=None, finish=None, limit=100):
    queryset = Observation.objects.all().recent().between(start=start, finish=finish)
    if metric:
        queryset = queryset.for_metric(metric)
    if source:
        queryset = queryset.from_source(source)
    return queryset[:limit]


def list_forecast_runs(limit=10):
    return ForecastRun.objects.prefetch_related("records").select_related("evaluation").all()[:limit]


def get_latest_forecast_run():
    return (
        ForecastRun.objects.filter(status=ForecastRun.Status.SUCCESS)
        .prefetch_related("records")
        .select_related("evaluation")
        .first()
    )


def get_forecast_run(run_id):
    return ForecastRun.objects.prefetch_related("records").select_related("evaluation").filter(id=run_id).first()


def get_forecast_runs_by_ids(run_ids):
    runs = ForecastRun.objects.prefetch_related("records").select_related("evaluation").filter(id__in=run_ids)
    runs_by_id = {str(run.id): run for run in runs}
    return [runs_by_id[run_id] for run_id in run_ids if run_id in runs_by_id]


def get_forecast_evaluation(run_id):
    return ForecastEvaluation.objects.select_related("forecast_run").filter(forecast_run_id=run_id).first()


def list_forecast_evaluations(*, limit=10, model_version_id=None):
    queryset = ForecastEvaluation.objects.select_related("forecast_run", "forecast_run__model_version")
    if model_version_id:
        queryset = queryset.filter(forecast_run__model_version_id=model_version_id)
    return queryset[:limit]


def get_forecast_evaluations_by_run_ids(run_ids):
    evaluations = ForecastEvaluation.objects.select_related("forecast_run", "forecast_run__model_version").filter(
        forecast_run_id__in=run_ids
    )
    evaluations_by_run_id = {str(evaluation.forecast_run_id): evaluation for evaluation in evaluations}
    return [evaluations_by_run_id[run_id] for run_id in run_ids if run_id in evaluations_by_run_id]


def list_dataset_snapshots(limit=10):
    return DatasetSnapshot.objects.all()[:limit]


def get_dataset_snapshot(snapshot_id):
    return DatasetSnapshot.objects.filter(id=snapshot_id).first()


def list_model_versions(limit=10):
    return ModelVersion.objects.all()[:limit]


def get_active_model_version():
    return ModelVersion.objects.filter(is_active=True, status=ModelVersion.Status.READY).first()


def get_model_version(model_version_id):
    return ModelVersion.objects.filter(id=model_version_id).first()


def get_model_versions_by_ids(model_version_ids):
    models = ModelVersion.objects.filter(id__in=model_version_ids)
    models_by_id = {str(model.id): model for model in models}
    return [
        models_by_id[model_version_id] for model_version_id in model_version_ids if model_version_id in models_by_id
    ]


def list_experiment_runs(limit=10):
    return ExperimentRun.objects.select_related(
        "series",
        "dataset_snapshot",
        "model_version",
        "forecast_run",
        "forecast_evaluation",
    )[:limit]


def list_experiment_runs_by_series(*, series_id, limit=10):
    return ExperimentRun.objects.select_related(
        "series",
        "dataset_snapshot",
        "model_version",
        "forecast_run",
        "forecast_evaluation",
    ).filter(series_id=series_id)[:limit]


def get_experiment_run(experiment_run_id):
    return (
        ExperimentRun.objects.select_related(
            "series",
            "dataset_snapshot",
            "model_version",
            "forecast_run",
            "forecast_evaluation",
        )
        .filter(id=experiment_run_id)
        .first()
    )


def get_experiment_runs_by_ids(experiment_run_ids):
    experiments = ExperimentRun.objects.select_related(
        "series",
        "dataset_snapshot",
        "model_version",
        "forecast_run",
        "forecast_evaluation",
    ).filter(id__in=experiment_run_ids)
    experiments_by_id = {str(experiment.id): experiment for experiment in experiments}
    return [
        experiments_by_id[experiment_run_id]
        for experiment_run_id in experiment_run_ids
        if experiment_run_id in experiments_by_id
    ]


def list_experiment_series(limit=10):
    return ExperimentSeries.objects.all()[:limit]


def get_experiment_series(series_id):
    return ExperimentSeries.objects.filter(id=series_id).first()


def get_experiment_series_by_ids(series_ids):
    series_queryset = ExperimentSeries.objects.filter(id__in=series_ids)
    series_by_id = {str(series.id): series for series in series_queryset}
    return [series_by_id[series_id] for series_id in series_ids if series_id in series_by_id]


def list_scheduled_monitoring_tasks(*, limit=20, requested_by_id=None):
    queryset = ScheduledMonitoringTask.objects.all()
    if requested_by_id is not None:
        queryset = queryset.filter(requested_by_id=requested_by_id)
    return queryset[:limit]


def get_scheduled_monitoring_task(task_id, *, requested_by_id=None):
    queryset = ScheduledMonitoringTask.objects.filter(id=task_id)
    if requested_by_id is not None:
        queryset = queryset.filter(requested_by_id=requested_by_id)
    return queryset.first()


def get_monitoring_overview():
    return {
        "counts": {
            "observations": Observation.objects.count(),
            "datasets": DatasetSnapshot.objects.count(),
            "models": ModelVersion.objects.count(),
            "forecasts": ForecastRun.objects.count(),
            "experiments": ExperimentRun.objects.count(),
            "series": ExperimentSeries.objects.count(),
            "scheduled_tasks": ScheduledMonitoringTask.objects.count(),
        },
        "automatic_collection": {
            "lookback_hours": settings.MONITORING_COLLECTION_LOOKBACK_HOURS,
            "interval": settings.MONITORING_INTERVAL,
            "window_hours": settings.MONITORING_WINDOW_HOURS,
            "schedule_minute": 5,
            "enabled_sources": ["mycityair", "plumelabs"],
        },
    }
