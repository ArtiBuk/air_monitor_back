from __future__ import annotations

from collections import defaultdict

from django.db import transaction

from apps.monitoring.models import ForecastEvaluation, ModelVersion


def _to_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _summary_metrics(summary: dict | None) -> dict[str, float | None]:
    summary = summary or {}
    return {
        "overall_rmse": _to_float(summary.get("overall_rmse")),
        "overall_mae": _to_float(summary.get("overall_mae")),
        "macro_mape": _to_float(summary.get("macro_mape")),
    }


def _metric_sort_value(value: float | None) -> float:
    return value if value is not None else float("inf")


def _list_ready_models() -> list[ModelVersion]:
    return list(
        ModelVersion.objects.filter(status=ModelVersion.Status.READY).select_related("dataset").order_by("-created_at")
    )


def _build_evaluation_aggregates(model_ids: list[str]) -> dict[str, dict]:
    evaluations = ForecastEvaluation.objects.select_related("forecast_run", "forecast_run__model_version").filter(
        status=ForecastEvaluation.Status.COMPLETED,
        forecast_run__model_version_id__in=model_ids,
    )
    grouped: dict[str, list[ForecastEvaluation]] = defaultdict(list)
    for evaluation in evaluations:
        grouped[str(evaluation.forecast_run.model_version_id)].append(evaluation)

    aggregates: dict[str, dict] = {}
    for model_id, model_evaluations in grouped.items():
        rmse_values = []
        mae_values = []
        mape_values = []
        coverage_values = []
        latest_evaluated_at = None

        for evaluation in model_evaluations:
            summary = evaluation.metrics.get("summary", {})
            rmse = _to_float(summary.get("overall_rmse"))
            mae = _to_float(summary.get("overall_mae"))
            mape = _to_float(summary.get("macro_mape"))
            coverage = _to_float(evaluation.coverage_ratio)

            if rmse is not None:
                rmse_values.append(rmse)
            if mae is not None:
                mae_values.append(mae)
            if mape is not None:
                mape_values.append(mape)
            if coverage is not None:
                coverage_values.append(coverage)
            if latest_evaluated_at is None or (
                evaluation.evaluated_at_utc and evaluation.evaluated_at_utc > latest_evaluated_at
            ):
                latest_evaluated_at = evaluation.evaluated_at_utc

        aggregates[model_id] = {
            "evaluation_count": len(model_evaluations),
            "avg_overall_rmse": (sum(rmse_values) / len(rmse_values)) if rmse_values else None,
            "avg_overall_mae": (sum(mae_values) / len(mae_values)) if mae_values else None,
            "avg_macro_mape": (sum(mape_values) / len(mape_values)) if mape_values else None,
            "avg_coverage_ratio": (sum(coverage_values) / len(coverage_values)) if coverage_values else None,
            "latest_evaluated_at_utc": latest_evaluated_at,
        }

    return aggregates


def _build_ranking_entry(model_version: ModelVersion, evaluation_aggregate: dict | None) -> dict:
    training_metrics = _summary_metrics(model_version.metrics.get("summary", {}))
    evaluation_aggregate = evaluation_aggregate or {}
    has_backtest_metrics = all(
        evaluation_aggregate.get(metric_name) is not None
        for metric_name in ("avg_overall_rmse", "avg_overall_mae", "avg_macro_mape")
    )

    metric_source = "backtest" if has_backtest_metrics else "training"
    metrics = (
        {
            "avg_overall_rmse": evaluation_aggregate.get("avg_overall_rmse"),
            "avg_overall_mae": evaluation_aggregate.get("avg_overall_mae"),
            "avg_macro_mape": evaluation_aggregate.get("avg_macro_mape"),
        }
        if has_backtest_metrics
        else {
            "avg_overall_rmse": training_metrics["overall_rmse"],
            "avg_overall_mae": training_metrics["overall_mae"],
            "avg_macro_mape": training_metrics["macro_mape"],
        }
    )

    dataset = model_version.dataset
    return {
        "model_version_id": str(model_version.id),
        "model_name": model_version.name,
        "evaluation_count": evaluation_aggregate.get("evaluation_count", 0),
        "avg_overall_rmse": metrics["avg_overall_rmse"],
        "avg_overall_mae": metrics["avg_overall_mae"],
        "avg_macro_mape": metrics["avg_macro_mape"],
        "avg_coverage_ratio": evaluation_aggregate.get("avg_coverage_ratio"),
        "forecast_horizon_hours": model_version.forecast_horizon_hours,
        "input_len_hours": model_version.input_len_hours,
        "is_active": model_version.is_active,
        "latest_evaluated_at_utc": evaluation_aggregate.get("latest_evaluated_at_utc"),
        "dataset_sample_count": dataset.sample_count if dataset else 0,
        "dataset_master_row_count": dataset.master_row_count if dataset else 0,
        "metric_source": metric_source,
        "created_at": model_version.created_at,
        "model_version": model_version,
    }


def _leaderboard_sort_key(metric: str, item: dict):
    metric_priority_map = {
        "overall_rmse": ("avg_overall_rmse", "avg_overall_mae", "avg_macro_mape"),
        "overall_mae": ("avg_overall_mae", "avg_overall_rmse", "avg_macro_mape"),
        "macro_mape": ("avg_macro_mape", "avg_overall_rmse", "avg_overall_mae"),
    }
    metric_order = metric_priority_map[metric]
    has_complete_metrics = 0 if all(item.get(metric_name) is not None for metric_name in metric_order) else 1
    metric_source_priority = 0 if item["metric_source"] == "backtest" else 1
    created_at = item.get("created_at")
    created_timestamp = created_at.timestamp() if created_at is not None else 0.0
    return (
        has_complete_metrics,
        metric_source_priority,
        *(_metric_sort_value(item.get(metric_name)) for metric_name in metric_order),
        -item["dataset_sample_count"],
        -item["dataset_master_row_count"],
        -item["evaluation_count"],
        -created_timestamp,
    )


def build_model_leaderboard(*, metric: str = "overall_rmse") -> list[dict]:
    models = [model for model in _list_ready_models() if model.checkpoint_blob]
    if not models:
        return []

    model_ids = [str(model.id) for model in models]
    evaluation_aggregates = _build_evaluation_aggregates(model_ids)
    leaderboard = [
        _build_ranking_entry(model, evaluation_aggregate=evaluation_aggregates.get(str(model.id))) for model in models
    ]
    leaderboard.sort(key=lambda item: _leaderboard_sort_key(metric, item))

    for index, item in enumerate(leaderboard, start=1):
        item["rank"] = index
        item["is_active"] = index == 1
        item.pop("created_at", None)
        item.pop("model_version", None)

    return leaderboard


class ModelSelectionService:
    def pick_best_model(self) -> ModelVersion | None:
        leaderboard = build_model_leaderboard(metric="overall_rmse")
        if not leaderboard:
            return None
        return ModelVersion.objects.filter(id=leaderboard[0]["model_version_id"]).first()

    @transaction.atomic
    def ensure_best_model_is_active(self) -> ModelVersion | None:
        best_model = self.pick_best_model()
        if best_model is None:
            ModelVersion.objects.filter(is_active=True).update(is_active=False)
            return None

        ModelVersion.objects.filter(is_active=True).exclude(id=best_model.id).update(is_active=False)
        if not best_model.is_active:
            ModelVersion.objects.filter(id=best_model.id).update(is_active=True)
            best_model.is_active = True

        return best_model
