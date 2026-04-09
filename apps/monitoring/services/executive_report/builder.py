from collections import defaultdict

from django.db.models import Count, Max, Min
from django.utils import timezone

from apps.monitoring.models import (
    DatasetSnapshot,
    ExperimentRun,
    ExperimentSeries,
    ForecastEvaluation,
    ForecastRun,
    ModelVersion,
    Observation,
)

from ..model_selection import build_model_leaderboard
from .formatters import (
    format_datetime,
    format_metric_list,
    format_metric_source,
    format_number,
    format_source_name,
    format_status,
    to_float,
)


def _resolve_active_model() -> tuple[ModelVersion | None, dict | None]:
    active_model = ModelVersion.objects.filter(is_active=True).select_related("dataset").first()
    leaderboard = build_model_leaderboard(metric="overall_rmse")
    if active_model is not None:
        linked_entry = next((item for item in leaderboard if item["model_version_id"] == str(active_model.id)), None)
        return active_model, linked_entry
    if not leaderboard:
        return None, None
    best_entry = leaderboard[0]
    best_model = ModelVersion.objects.filter(id=best_entry["model_version_id"]).select_related("dataset").first()
    return best_model, best_entry


def _collect_source_summary() -> list[dict]:
    source_rows = (
        Observation.objects.values("source")
        .annotate(
            observation_count=Count("id"),
            station_count=Count("station_id", distinct=True),
            first_timestamp=Min("observed_at_utc"),
            latest_timestamp=Max("observed_at_utc"),
        )
        .order_by("source")
    )
    metrics_by_source: dict[str, list[str]] = defaultdict(list)
    for row in (
        Observation.objects.values("source", "metric")
        .distinct()
        .order_by("source", "metric")
    ):
        source = row["source"] or ""
        metric = row["metric"]
        if metric:
            metrics_by_source[source].append(metric)

    summaries = []
    for row in source_rows:
        summaries.append(
            {
                "source": row["source"],
                "label": format_source_name(row["source"]),
                "observation_count": row["observation_count"],
                "station_count": row["station_count"],
                "first_timestamp": row["first_timestamp"],
                "latest_timestamp": row["latest_timestamp"],
                "metrics": metrics_by_source.get(row["source"] or "", []),
            }
        )
    return summaries


def _extract_forecast_snapshot(run: ForecastRun | None) -> dict | None:
    if run is None:
        return None
    records = list(run.records.all())
    if not records:
        return {
            "id": str(run.id),
            "created_at": run.created_at,
            "generated_from_timestamp_utc": run.generated_from_timestamp_utc,
            "forecast_horizon_hours": run.forecast_horizon_hours,
            "record_count": 0,
            "aqi_start": None,
            "aqi_end": None,
            "aqi_delta": None,
            "target_metrics": [],
            "model_name": run.model_version.name if run.model_version else None,
            "aqi_series": [],
        }

    aqi_values = [
        to_float(record.values.get("mycityair_aqi_mean"))
        for record in records
        if to_float(record.values.get("mycityair_aqi_mean")) is not None
    ]
    first_aqi = aqi_values[0] if aqi_values else None
    last_aqi = aqi_values[-1] if aqi_values else None
    target_metrics = sorted({key for record in records for key in record.values.keys()})
    aqi_series = []
    for record in records:
        value = to_float(record.values.get("mycityair_aqi_mean"))
        if value is None:
            continue
        aqi_series.append({"label": format_datetime(record.timestamp_utc, ""), "value": value})
    return {
        "id": str(run.id),
        "created_at": run.created_at,
        "generated_from_timestamp_utc": run.generated_from_timestamp_utc,
        "forecast_horizon_hours": run.forecast_horizon_hours,
        "record_count": len(records),
        "aqi_start": first_aqi,
        "aqi_end": last_aqi,
        "aqi_delta": (last_aqi - first_aqi) if first_aqi is not None and last_aqi is not None else None,
        "target_metrics": target_metrics,
        "model_name": run.model_version.name if run.model_version else None,
        "aqi_series": aqi_series,
    }


def _extract_evaluation_summary(evaluation: ForecastEvaluation | None) -> dict | None:
    if evaluation is None:
        return None
    summary = evaluation.metrics.get("summary", {})
    return {
        "status": evaluation.status,
        "evaluated_at_utc": evaluation.evaluated_at_utc,
        "coverage_ratio": to_float(evaluation.coverage_ratio),
        "overall_rmse": to_float(summary.get("overall_rmse")),
        "overall_mae": to_float(summary.get("overall_mae")),
        "macro_mape": to_float(summary.get("macro_mape")),
        "matched_record_count": evaluation.matched_record_count,
        "expected_record_count": evaluation.expected_record_count,
    }


def _build_dataset_summary(dataset: DatasetSnapshot | None) -> dict | None:
    if dataset is None:
        return None
    summary = {
        "id": str(dataset.id),
        "created_at": dataset.created_at,
        "input_len_hours": dataset.input_len_hours,
        "forecast_horizon_hours": dataset.forecast_horizon_hours,
        "sample_count": dataset.sample_count,
        "master_row_count": dataset.master_row_count,
        "feature_count": len(dataset.feature_columns or []),
        "target_count": len(dataset.target_columns or []),
        "feature_preview": list(dataset.feature_columns or [])[:6],
        "target_preview": list(dataset.target_columns or [])[:6],
    }
    summary["feature_preview_label"] = format_metric_list(summary["feature_preview"])
    summary["target_preview_label"] = format_metric_list(summary["target_preview"])
    return summary


def _build_active_model_summary(model: ModelVersion | None, leaderboard_entry: dict | None) -> dict | None:
    if model is None:
        return None
    model_summary = (model.metrics or {}).get("summary", {})
    summary = {
        "id": str(model.id),
        "name": model.name,
        "created_at": model.created_at,
        "forecast_horizon_hours": model.forecast_horizon_hours,
        "input_len_hours": model.input_len_hours,
        "feature_count": len(model.feature_names or []),
        "target_count": len(model.target_names or []),
        "target_preview": list(model.target_names or [])[:6],
        "dataset_sample_count": model.dataset.sample_count if model.dataset else 0,
        "avg_overall_rmse": (
            to_float(leaderboard_entry.get("avg_overall_rmse"))
            if leaderboard_entry
            else to_float(model_summary.get("overall_rmse"))
        ),
        "avg_overall_mae": (
            to_float(leaderboard_entry.get("avg_overall_mae"))
            if leaderboard_entry
            else to_float(model_summary.get("overall_mae"))
        ),
        "avg_macro_mape": (
            to_float(leaderboard_entry.get("avg_macro_mape"))
            if leaderboard_entry
            else to_float(model_summary.get("macro_mape"))
        ),
        "metric_source": leaderboard_entry.get("metric_source") if leaderboard_entry else "training",
        "evaluation_count": leaderboard_entry.get("evaluation_count", 0) if leaderboard_entry else 0,
    }
    summary["avg_overall_rmse_label"] = format_number(summary["avg_overall_rmse"])
    summary["avg_overall_mae_label"] = format_number(summary["avg_overall_mae"])
    summary["avg_macro_mape_label"] = format_number(summary["avg_macro_mape"])
    summary["metric_source_label"] = format_metric_source(summary["metric_source"])
    summary["target_preview_label"] = format_metric_list(summary["target_preview"])
    return summary


def _build_experiment_run_summary(run: ExperimentRun | None) -> dict | None:
    if run is None:
        return None
    return {
        "id": str(run.id),
        "name": run.name,
        "status": run.status,
        "status_label": format_status(run.status),
        "created_at": run.created_at,
        "series_name": run.series.name if run.series else None,
        "model_name": run.model_version.name if run.model_version else None,
    }


def _build_best_series_summary(series: ExperimentSeries | None) -> dict | None:
    if series is None:
        return None
    summary = series.summary or {}
    result = {
        "id": str(series.id),
        "name": series.name,
        "description": series.description,
        "run_count": int(summary.get("run_count") or 0),
        "completed_run_count": int(summary.get("completed_run_count") or 0),
        "failed_run_count": int(summary.get("failed_run_count") or 0),
        "best_backtest_overall_rmse": to_float(summary.get("best_backtest_overall_rmse")),
        "created_at": series.created_at,
    }
    result["best_backtest_overall_rmse_label"] = format_number(result["best_backtest_overall_rmse"])
    return result


def _select_best_series() -> ExperimentSeries | None:
    best_series = None
    best_rmse = None
    for series in ExperimentSeries.objects.all():
        rmse = to_float((series.summary or {}).get("best_backtest_overall_rmse"))
        if rmse is None:
            continue
        if best_rmse is None or rmse < best_rmse:
            best_rmse = rmse
            best_series = series
    return best_series or ExperimentSeries.objects.first()


def _build_conclusions(report: dict) -> list[str]:
    observations = report["observations"]
    latest_dataset = report["latest_dataset"]
    active_model = report["active_model"]
    latest_forecast = report["latest_forecast"]
    latest_evaluation = report["latest_evaluation"]
    latest_run = report["latest_experiment_run"]
    best_series = report["best_series"]

    conclusions = [
        (
            f"На {report['generated_at_label']} в системе накоплено {observations['total_count']} наблюдений "
            f"из {observations['source_count']} источников; последние данные поступили {observations['latest_label']}."
        )
    ]
    if latest_dataset:
        conclusions.append(
            f"Последняя обучающая выборка содержит {latest_dataset['sample_count']} временных фрагментов и "
            f"{latest_dataset['feature_count']} признаков; прогноз строится на {latest_dataset['forecast_horizon_hours']} часов вперёд."
        )
    if active_model:
        conclusions.append(
            f"Текущая рабочая модель «{active_model['name']}» прогнозирует {active_model['target_count']} ключевых показателей; "
            f"её основная ошибка составляет {active_model['avg_overall_rmse_label']} по данным типа "
            f"«{format_metric_source(active_model['metric_source'])}»."
        )
    if latest_forecast:
        trend = latest_forecast["aqi_delta"]
        if trend is None:
            trend_note = "без расчёта динамики AQI"
        elif trend > 0:
            trend_note = f"ожидается ухудшение AQI на {abs(trend):.1f} пункта"
        elif trend < 0:
            trend_note = f"ожидается улучшение AQI на {abs(trend):.1f} пункта"
        else:
            trend_note = "ожидается стабильный AQI"
        conclusions.append(
            f"Последний прогноз построен на {latest_forecast['forecast_horizon_hours']} ч вперёд; "
            f"{trend_note}, рассчитано {latest_forecast['record_count']} временных точек."
        )
    if latest_evaluation:
        conclusions.append(
            f"Последняя проверка прогноза показала среднюю абсолютную ошибку {latest_evaluation['overall_mae_label']} "
            f"и покрытие {latest_evaluation['coverage_ratio_label']}% от ожидаемых точек."
        )
    if latest_run or best_series:
        run_count = best_series["run_count"] if best_series else 0
        series_name = best_series["name"] if best_series else "без серии"
        conclusions.append(
            f"Экспериментальный контур уже включает {report['counts']['experiments']} запусков; "
            f"наиболее содержательная серия сейчас — «{series_name}» ({run_count} запусков)."
        )
    return conclusions[:5]


def _build_forecast_interpretation(report: dict) -> str:
    latest_forecast = report["latest_forecast"]
    latest_evaluation = report["latest_evaluation"]
    if not latest_forecast:
        return (
            "Прогнозный слой пока не сформирован, поэтому система ещё не может показать ожидаемую динамику "
            "качества воздуха на ближайшие часы."
        )

    start_value = latest_forecast["aqi_start"]
    end_value = latest_forecast["aqi_end"]
    if start_value is None or end_value is None:
        trend_text = "Динамика AQI пока не читается однозначно, так как данных для начала и конца горизонта недостаточно."
    elif end_value > start_value:
        trend_text = (
            f"По последнему прогнозу AQI растёт с {latest_forecast['aqi_start_label']} до {latest_forecast['aqi_end_label']}, "
            "что указывает на вероятное ухудшение фоновой ситуации к концу горизонта."
        )
    elif end_value < start_value:
        trend_text = (
            f"По последнему прогнозу AQI снижается с {latest_forecast['aqi_start_label']} до {latest_forecast['aqi_end_label']}, "
            "что указывает на вероятное ослабление загрязнения к концу горизонта."
        )
    else:
        trend_text = (
            f"По последнему прогнозу AQI остаётся около значения {latest_forecast['aqi_start_label']}, "
            "поэтому резкой смены фоновой ситуации на горизонте не ожидается."
        )

    if latest_evaluation and latest_evaluation["overall_mae"] is not None:
        trust_text = (
            f"Доверие к этому сценарию поддерживается последней проверкой прогноза: "
            f"средняя абсолютная ошибка составила {latest_evaluation['overall_mae_label']}, "
            f"а покрытие фактическими данными достигло {latest_evaluation['coverage_ratio_label']}%."
        )
    else:
        trust_text = (
            "Полная оценка по фактическим данным пока недоступна, поэтому текущий прогноз следует трактовать как "
            "оперативный ориентир, а не как окончательное подтверждённое значение."
        )

    return f"{trend_text} {trust_text}"


def _build_practical_value(report: dict) -> list[str]:
    observations = report["observations"]
    latest_forecast = report["latest_forecast"]
    latest_evaluation = report["latest_evaluation"]
    values = [
        (
            "Система собирает разрозненные наблюдения из нескольких источников и сводит их в единый временной контур, "
            "что особенно важно для Норильского промышленного района с неоднородной экологической обстановкой."
        ),
        (
            "На основе этих данных формируется воспроизводимый датасет и обучается рабочая модель, "
            "поэтому прогноз строится не вручную, а как результат формализованного исследовательского pipeline."
        ),
        (
            "Итог прогноза сразу интерпретируется в прикладной форме: городской фон и station-level точки выводятся на карте, "
            "что делает результат понятным не только разработчику, но и конечному пользователю."
        ),
    ]
    if latest_forecast:
        values.append(
            f"Сейчас система уже умеет строить прогноз на {latest_forecast['forecast_horizon_hours']} часов вперёд, "
            "то есть может использоваться как инструмент краткосрочного предупреждения о смене качества воздуха."
        )
    if latest_evaluation:
        values.append(
            f"Наличие блока проверки по фактическим данным позволяет не ограничиваться визуализацией: "
            f"прогноз дополнительно контролируется метриками точности и покрытием ({latest_evaluation['coverage_ratio_label']}%)."
        )
    if observations["station_count"]:
        values.append(
            f"В текущем контуре учтены данные как минимум по {observations['station_count']} станциям, "
            "что даёт возможность сопоставлять локальные горячие точки и общий городской фон."
        )
    return values[:5]


def build_monitoring_executive_report() -> dict:
    now = timezone.now()
    observation_range = Observation.objects.aggregate(
        total_count=Count("id"),
        first_timestamp=Min("observed_at_utc"),
        latest_timestamp=Max("observed_at_utc"),
        source_count=Count("source", distinct=True),
        station_count=Count("station_id", distinct=True),
    )
    source_summary = _collect_source_summary()

    latest_dataset_obj = DatasetSnapshot.objects.order_by("-created_at").first()
    active_model_obj, leaderboard_entry = _resolve_active_model()
    latest_forecast_obj = (
        ForecastRun.objects.filter(status=ForecastRun.Status.SUCCESS)
        .select_related("model_version", "evaluation")
        .prefetch_related("records")
        .order_by("-created_at")
        .first()
    )
    latest_evaluation_obj = getattr(latest_forecast_obj, "evaluation", None) if latest_forecast_obj else None
    if latest_evaluation_obj is None:
        latest_evaluation_obj = (
            ForecastEvaluation.objects.filter(status=ForecastEvaluation.Status.COMPLETED)
            .select_related("forecast_run", "forecast_run__model_version")
            .order_by("-evaluated_at_utc")
            .first()
        )
    latest_experiment_run_obj = (
        ExperimentRun.objects.select_related("series", "dataset_snapshot", "model_version", "forecast_evaluation")
        .order_by("-created_at")
        .first()
    )
    best_series_obj = _select_best_series()

    latest_dataset = _build_dataset_summary(latest_dataset_obj)
    active_model = _build_active_model_summary(active_model_obj, leaderboard_entry)

    latest_forecast = _extract_forecast_snapshot(latest_forecast_obj)
    if latest_forecast:
        latest_forecast["aqi_start_label"] = format_number(latest_forecast["aqi_start"])
        latest_forecast["aqi_end_label"] = format_number(latest_forecast["aqi_end"])
        latest_forecast["aqi_delta_label"] = format_number(latest_forecast["aqi_delta"])
        latest_forecast["target_metrics_label"] = format_metric_list(latest_forecast["target_metrics"], limit=5)

    latest_evaluation = _extract_evaluation_summary(latest_evaluation_obj)
    if latest_evaluation:
        latest_evaluation["coverage_ratio_label"] = format_number((latest_evaluation["coverage_ratio"] or 0) * 100, digits=1)
        latest_evaluation["overall_rmse_label"] = format_number(latest_evaluation["overall_rmse"])
        latest_evaluation["overall_mae_label"] = format_number(latest_evaluation["overall_mae"])
        latest_evaluation["macro_mape_label"] = format_number((latest_evaluation["macro_mape"] or 0) * 100, digits=1)

    latest_experiment_run = _build_experiment_run_summary(latest_experiment_run_obj)
    best_series = _build_best_series_summary(best_series_obj)

    report = {
        "generated_at": now,
        "generated_at_label": format_datetime(now),
        "report_date_label": now.strftime("%d.%m.%Y"),
        "title": "Итоговый аналитический отчёт о мониторинге и прогнозировании качества воздуха в Норильском промышленном районе",
        "subtitle": "Практический результат исследовательской системы: от наблюдений и моделей до карты загрязнения и финальных выводов.",
        "counts": {
            "observations": int(observation_range["total_count"] or 0),
            "datasets": DatasetSnapshot.objects.count(),
            "models": ModelVersion.objects.count(),
            "forecasts": ForecastRun.objects.count(),
            "experiments": ExperimentRun.objects.count(),
            "series": ExperimentSeries.objects.count(),
        },
        "observations": {
            "total_count": int(observation_range["total_count"] or 0),
            "source_count": int(observation_range["source_count"] or 0),
            "station_count": int(observation_range["station_count"] or 0),
            "first_timestamp": observation_range["first_timestamp"],
            "latest_timestamp": observation_range["latest_timestamp"],
            "first_label": format_datetime(observation_range["first_timestamp"]),
            "latest_label": format_datetime(observation_range["latest_timestamp"]),
            "sources": source_summary,
        },
        "latest_dataset": latest_dataset,
        "active_model": active_model,
        "latest_forecast": latest_forecast,
        "latest_evaluation": latest_evaluation,
        "latest_experiment_run": latest_experiment_run,
        "best_series": best_series,
        "study_context": (
            "Документ подводит итог практической части исследовательской работы по качеству воздуха в НПР. "
            "Он показывает, как собранные наблюдения, подготовленные датасеты, модели и прогнозы складываются "
            "в единый прикладной инструмент анализа экологической обстановки."
        ),
    }
    report["forecast_interpretation"] = _build_forecast_interpretation(report)
    report["practical_value"] = _build_practical_value(report)
    report["conclusions"] = _build_conclusions(report)
    return report
