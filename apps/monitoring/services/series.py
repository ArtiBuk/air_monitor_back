from apps.monitoring.models import ExperimentRun, ExperimentSeries

from .validation import validate_series_name


def create_experiment_series(*, requested_by, name: str, description: str = "", configuration: dict | None = None):
    """Создаёт новую серию экспериментов с базовой сводкой."""
    normalized_name = validate_series_name(name)
    return ExperimentSeries.objects.create(
        requested_by=requested_by,
        name=normalized_name,
        description=description.strip(),
        configuration=configuration or {},
        summary={
            "run_count": 0,
            "completed_run_count": 0,
            "failed_run_count": 0,
            "latest_experiment_run_id": None,
            "best_experiment_run_id": None,
            "best_backtest_overall_rmse": None,
        },
    )


def build_experiment_series_summary(*, series: ExperimentSeries) -> dict:
    """Собирает сводку по серии экспериментов."""
    runs = list(series.runs.select_related("forecast_evaluation").all())
    completed_runs = [run for run in runs if run.status == ExperimentRun.Status.COMPLETED]
    failed_runs = [run for run in runs if run.status == ExperimentRun.Status.FAILED]

    best_run = None
    best_rmse = None
    for run in completed_runs:
        evaluation = run.forecast_evaluation
        if evaluation is None or evaluation.status != evaluation.Status.COMPLETED:
            continue
        overall_rmse = evaluation.metrics.get("summary", {}).get("overall_rmse")
        if overall_rmse is None:
            continue
        if best_rmse is None or overall_rmse < best_rmse:
            best_rmse = float(overall_rmse)
            best_run = run

    latest_run = completed_runs[0] if completed_runs else (runs[0] if runs else None)
    return {
        "run_count": len(runs),
        "completed_run_count": len(completed_runs),
        "failed_run_count": len(failed_runs),
        "latest_experiment_run_id": str(latest_run.id) if latest_run else None,
        "best_experiment_run_id": str(best_run.id) if best_run else None,
        "best_backtest_overall_rmse": best_rmse,
    }


def sync_experiment_series_summary(*, series: ExperimentSeries) -> ExperimentSeries:
    """Пересчитывает и сохраняет сводку серии экспериментов."""
    series.summary = build_experiment_series_summary(series=series)
    series.save(update_fields=["summary", "updated_at"])
    return series


def build_experiment_series_report(*, series: ExperimentSeries, runs: list[ExperimentRun]) -> dict:
    """Собирает детальный отчёт по серии экспериментов."""
    training_rmse_values = []
    backtest_rmse_values = []
    backtest_mae_values = []
    backtest_mape_values = []

    for run in runs:
        training_summary = (run.model_version.metrics if run.model_version else {}).get("summary", {})
        if "overall_rmse" in training_summary:
            training_rmse_values.append(float(training_summary["overall_rmse"]))

        backtest_summary = (run.forecast_evaluation.metrics if run.forecast_evaluation else {}).get("summary", {})
        if "overall_rmse" in backtest_summary:
            backtest_rmse_values.append(float(backtest_summary["overall_rmse"]))
        if "overall_mae" in backtest_summary:
            backtest_mae_values.append(float(backtest_summary["overall_mae"]))
        if "macro_mape" in backtest_summary:
            backtest_mape_values.append(float(backtest_summary["macro_mape"]))

    aggregates = {
        **series.summary,
        "avg_training_overall_rmse": (
            sum(training_rmse_values) / len(training_rmse_values) if training_rmse_values else None
        ),
        "avg_backtest_overall_rmse": (
            sum(backtest_rmse_values) / len(backtest_rmse_values) if backtest_rmse_values else None
        ),
        "avg_backtest_overall_mae": sum(backtest_mae_values) / len(backtest_mae_values)
        if backtest_mae_values
        else None,
        "avg_backtest_macro_mape": (
            sum(backtest_mape_values) / len(backtest_mape_values) if backtest_mape_values else None
        ),
    }
    return {
        "series": series,
        "runs": runs,
        "aggregates": aggregates,
    }
