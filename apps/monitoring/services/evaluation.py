import logging
from dataclasses import dataclass

import numpy as np
from django.db import transaction
from django.utils import timezone

from apps.monitoring.models import ForecastEvaluation, ForecastRun

from .dataframes import build_master_dataset_from_db

logger = logging.getLogger(__name__)


@dataclass
class ForecastEvaluationResult:
    evaluation_id: str
    forecast_run_id: str
    status: str
    expected_record_count: int
    matched_record_count: int
    coverage_ratio: float
    metrics: dict


def _build_series_evaluation_metrics(y_true: np.ndarray, y_pred: np.ndarray, target_names: list[str]) -> dict:
    per_target = {}
    rmse_values = []
    mae_values = []
    mape_values = []
    max_abs_errors = []

    for index, target_name in enumerate(target_names):
        err = y_pred[:, index] - y_true[:, index]
        abs_err = np.abs(err)
        denom = np.where(np.abs(y_true[:, index]) < 1e-6, np.nan, np.abs(y_true[:, index]))
        rmse = float(np.sqrt(np.mean(err**2)))
        mae = float(np.mean(abs_err))
        mape = float(np.nan_to_num(np.nanmean(abs_err / denom) * 100.0, nan=0.0))
        max_abs_error = float(np.max(abs_err))

        rmse_values.append(rmse)
        mae_values.append(mae)
        mape_values.append(mape)
        max_abs_errors.append(max_abs_error)
        per_target[target_name] = {
            "rmse": rmse,
            "mae": mae,
            "mape": mape,
            "max_abs_error": max_abs_error,
        }

    overall_err = y_pred - y_true
    summary = {
        "overall_rmse": float(np.sqrt(np.mean(overall_err**2))),
        "overall_mae": float(np.mean(np.abs(overall_err))),
        "macro_rmse": float(np.mean(rmse_values)),
        "macro_mae": float(np.mean(mae_values)),
        "macro_mape": float(np.mean(mape_values)),
        "max_abs_error": float(np.max(max_abs_errors)),
    }

    return {
        "summary": summary,
        "per_target": per_target,
    }


class ForecastEvaluationService:
    @transaction.atomic
    def evaluate(self, *, forecast_run: ForecastRun) -> ForecastEvaluationResult:
        """Оценивает прогноз по фактически наблюдаемым целям."""
        if forecast_run.status != ForecastRun.Status.SUCCESS:
            raise ValueError("Only successful forecast runs can be evaluated.")
        if forecast_run.model_version_id is None:
            raise ValueError("Forecast run has no associated model version.")

        evaluation, _ = ForecastEvaluation.objects.get_or_create(forecast_run=forecast_run)
        target_names = list(forecast_run.model_version.target_names)
        expected_record_count = forecast_run.records.count()

        try:
            master_df = build_master_dataset_from_db()
            actual_frame = master_df[["timestamp_utc", *target_names]].copy()
            actual_frame["timestamp_utc"] = actual_frame["timestamp_utc"].dt.tz_convert("UTC")

            forecast_rows = []
            for record in forecast_run.records.all():
                row = {"timestamp_utc": record.timestamp_utc}
                row.update({target_name: record.values.get(target_name) for target_name in target_names})
                forecast_rows.append(row)

            if not forecast_rows:
                raise ValueError("Forecast run has no records to evaluate.")

            import pandas as pd

            predicted_frame = pd.DataFrame(forecast_rows)
            merged = predicted_frame.merge(
                actual_frame,
                on="timestamp_utc",
                how="left",
                suffixes=("_pred", "_actual"),
            )
            actual_columns = [f"{target_name}_actual" for target_name in target_names]
            matched = merged.dropna(subset=actual_columns)
            if matched.empty:
                raise ValueError("No actual observations found for forecast horizon.")

            y_pred = matched[[f"{target_name}_pred" for target_name in target_names]].to_numpy(dtype="float32")
            y_true = matched[actual_columns].to_numpy(dtype="float32")
            metrics = _build_series_evaluation_metrics(y_true, y_pred, target_names)
            matched_record_count = len(matched)
            coverage_ratio = matched_record_count / expected_record_count if expected_record_count else 0.0

            evaluation.status = ForecastEvaluation.Status.COMPLETED
            evaluation.expected_record_count = expected_record_count
            evaluation.matched_record_count = matched_record_count
            evaluation.coverage_ratio = coverage_ratio
            evaluation.evaluated_at_utc = timezone.now()
            evaluation.metrics = metrics
            evaluation.error_message = ""
            evaluation.save(
                update_fields=[
                    "status",
                    "expected_record_count",
                    "matched_record_count",
                    "coverage_ratio",
                    "evaluated_at_utc",
                    "metrics",
                    "error_message",
                    "updated_at",
                ]
            )
            logger.info(
                "forecast evaluation completed forecast_run_id=%s matched=%s expected=%s",
                forecast_run.id,
                matched_record_count,
                expected_record_count,
            )
        except Exception as exc:
            evaluation.status = ForecastEvaluation.Status.FAILED
            evaluation.expected_record_count = expected_record_count
            evaluation.matched_record_count = 0
            evaluation.coverage_ratio = 0.0
            evaluation.metrics = {}
            evaluation.error_message = str(exc)
            evaluation.evaluated_at_utc = timezone.now()
            evaluation.save(
                update_fields=[
                    "status",
                    "expected_record_count",
                    "matched_record_count",
                    "coverage_ratio",
                    "metrics",
                    "error_message",
                    "evaluated_at_utc",
                    "updated_at",
                ]
            )
            logger.exception("forecast evaluation failed forecast_run_id=%s", forecast_run.id)
            raise

        return ForecastEvaluationResult(
            evaluation_id=str(evaluation.id),
            forecast_run_id=str(forecast_run.id),
            status=evaluation.status,
            expected_record_count=evaluation.expected_record_count,
            matched_record_count=evaluation.matched_record_count,
            coverage_ratio=evaluation.coverage_ratio,
            metrics=evaluation.metrics,
        )
