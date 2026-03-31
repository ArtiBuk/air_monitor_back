from collections import defaultdict

from apps.monitoring.models import ForecastEvaluation


def build_model_leaderboard(*, evaluations, metric: str) -> list[dict]:
    """Строит лидерборд моделей по завершенным оценкам прогноза."""
    grouped = defaultdict(list)
    for evaluation in evaluations:
        if evaluation.status != ForecastEvaluation.Status.COMPLETED:
            continue
        grouped[str(evaluation.forecast_run.model_version_id)].append(evaluation)

    leaderboard = []
    for model_version_id, model_evaluations in grouped.items():
        model_version = model_evaluations[0].forecast_run.model_version
        if model_version is None:
            continue
        rmse_values = []
        mae_values = []
        mape_values = []
        coverage_values = []
        latest_evaluated_at = None

        for evaluation in model_evaluations:
            summary = evaluation.metrics.get("summary", {})
            rmse_values.append(float(summary.get("overall_rmse", 0.0)))
            mae_values.append(float(summary.get("overall_mae", 0.0)))
            mape_values.append(float(summary.get("macro_mape", 0.0)))
            coverage_values.append(float(evaluation.coverage_ratio))
            if latest_evaluated_at is None or (
                evaluation.evaluated_at_utc and evaluation.evaluated_at_utc > latest_evaluated_at
            ):
                latest_evaluated_at = evaluation.evaluated_at_utc

        leaderboard.append(
            {
                "model_version_id": model_version_id,
                "model_name": model_version.name,
                "evaluation_count": len(model_evaluations),
                "avg_overall_rmse": sum(rmse_values) / len(rmse_values),
                "avg_overall_mae": sum(mae_values) / len(mae_values),
                "avg_macro_mape": sum(mape_values) / len(mape_values),
                "avg_coverage_ratio": sum(coverage_values) / len(coverage_values),
                "forecast_horizon_hours": model_version.forecast_horizon_hours,
                "input_len_hours": model_version.input_len_hours,
                "is_active": model_version.is_active,
                "latest_evaluated_at_utc": latest_evaluated_at,
            }
        )

    sort_field_map = {
        "overall_rmse": "avg_overall_rmse",
        "overall_mae": "avg_overall_mae",
        "macro_mape": "avg_macro_mape",
    }
    sort_field = sort_field_map[metric]
    return sorted(leaderboard, key=lambda item: (item[sort_field], -item["evaluation_count"]))
