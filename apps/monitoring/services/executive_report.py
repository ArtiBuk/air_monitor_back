from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path

from django.db.models import Count, Max, Min
from django.utils import timezone
from reportlab.graphics.shapes import Circle, Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.monitoring.models import (
    DatasetSnapshot,
    ExperimentRun,
    ExperimentSeries,
    ForecastEvaluation,
    ForecastRun,
    ModelVersion,
    Observation,
)

from .model_selection import build_model_leaderboard

PDF_ACCENT = colors.HexColor("#0F766E")
PDF_ACCENT_SOFT = colors.HexColor("#D7F2EF")
PDF_WARM = colors.HexColor("#F59E0B")
PDF_DANGER = colors.HexColor("#DC2626")
PDF_TEXT = colors.HexColor("#12212A")
PDF_MUTED = colors.HexColor("#54636D")
PDF_BORDER = colors.HexColor("#D9E1E7")
PDF_PANEL = colors.HexColor("#F6F9FB")
CONTENT_WIDTH = A4[0] - 32 * mm

METRIC_LABELS = {
    "mycityair_aqi_mean": "Индекс качества воздуха AQI",
    "mycityair_aqi_max": "Максимальный индекс AQI",
    "mycityair_aqi_min": "Минимальный индекс AQI",
    "aqi": "Индекс качества воздуха AQI",
    "plume_index": "Сводный индекс загрязнения",
    "pm25": "Мелкие частицы PM2.5",
    "plume_pm25": "Мелкие частицы PM2.5",
    "pm10": "Взвешенные частицы PM10",
    "plume_pm10": "Взвешенные частицы PM10",
    "no2": "Диоксид азота",
    "plume_no2": "Диоксид азота",
    "so2": "Диоксид серы",
    "plume_so2": "Диоксид серы",
    "o3": "Озон",
    "plume_o3": "Озон",
    "co": "Монооксид углерода",
    "plume_co": "Монооксид углерода",
}

SOURCE_LABELS = {
    "mycityair": "Посты MyCityAir",
    "plumelabs": "Городской фон Plume Labs",
}

STATUS_LABELS = {
    "completed": "завершён",
    "success": "успешно выполнен",
    "failed": "завершился с ошибкой",
    "pending": "ожидает выполнения",
    "started": "выполняется",
    "active": "активна",
    "ready": "готова к использованию",
}


def _to_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_number(value, digits: int = 2, fallback: str = "—") -> str:
    numeric = _to_float(value)
    if numeric is None:
        return fallback
    text = f"{numeric:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _fmt_int(value, fallback: str = "—") -> str:
    numeric = _to_float(value)
    if numeric is None:
        return fallback
    return str(int(round(numeric)))


def _fmt_dt(value, fallback: str = "—") -> str:
    if value is None:
        return fallback
    localized = timezone.localtime(value)
    return localized.strftime("%d.%m.%Y %H:%M")


def _format_metric_name(value: str | None) -> str:
    if not value:
        return "—"
    return METRIC_LABELS.get(value, value.replace("_", " "))


def _format_metric_list(values: list[str], limit: int = 4) -> str:
    if not values:
        return "—"
    labels = [_format_metric_name(item) for item in values[:limit]]
    if len(values) > limit:
        labels.append("и др.")
    return ", ".join(labels)


def _format_source_name(value: str | None) -> str:
    if not value:
        return "—"
    return SOURCE_LABELS.get(value, value)


def _format_status(value: str | None) -> str:
    if not value:
        return "—"
    return STATUS_LABELS.get(value, value)


def _format_metric_source(value: str | None) -> str:
    if value == "backtest":
        return "проверка на исторических данных"
    if value == "training":
        return "оценка на этапе обучения"
    return "—"


@lru_cache(maxsize=1)
def _register_report_font() -> tuple[str, str]:
    font_dir = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    regular_candidates = [
        font_dir / "Arial.ttf",
        font_dir / "ArialUnicode.ttf",
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
    ]
    bold_candidates = [
        font_dir / "ArialBold.ttf",
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
    ]

    regular_path = next((candidate for candidate in regular_candidates if candidate.exists()), None)
    if regular_path is None:
        return "Helvetica", "Helvetica-Bold"

    bold_path = next((candidate for candidate in bold_candidates if candidate.exists()), None) or regular_path

    regular_name = "AirReportUnicode"
    bold_name = "AirReportUnicodeBold"
    if regular_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
    if bold_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
    pdfmetrics.registerFontFamily(
        "AirReportFamily",
        normal=regular_name,
        bold=bold_name,
        italic=regular_name,
        boldItalic=bold_name,
    )
    return regular_name, bold_name


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
    summaries = []
    for row in source_rows:
        metrics = sorted(Observation.objects.filter(source=row["source"]).values_list("metric", flat=True).distinct())
        summaries.append(
            {
                "source": row["source"],
                "label": _format_source_name(row["source"]),
                "observation_count": row["observation_count"],
                "station_count": row["station_count"],
                "first_timestamp": row["first_timestamp"],
                "latest_timestamp": row["latest_timestamp"],
                "metrics": metrics,
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
        }

    aqi_values = [
        _to_float(record.values.get("mycityair_aqi_mean"))
        for record in records
        if _to_float(record.values.get("mycityair_aqi_mean")) is not None
    ]
    first_aqi = aqi_values[0] if aqi_values else None
    last_aqi = aqi_values[-1] if aqi_values else None
    target_metrics = sorted({key for record in records for key in record.values.keys()})
    aqi_series = []
    for record in records:
        value = _to_float(record.values.get("mycityair_aqi_mean"))
        if value is None:
            continue
        aqi_series.append(
            {
                "label": _fmt_dt(record.timestamp_utc, ""),
                "value": value,
            }
        )
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
        "coverage_ratio": _to_float(evaluation.coverage_ratio),
        "overall_rmse": _to_float(summary.get("overall_rmse")),
        "overall_mae": _to_float(summary.get("overall_mae")),
        "macro_mape": _to_float(summary.get("macro_mape")),
        "matched_record_count": evaluation.matched_record_count,
        "expected_record_count": evaluation.expected_record_count,
    }


def _select_best_series() -> ExperimentSeries | None:
    best_series = None
    best_rmse = None
    for series in ExperimentSeries.objects.all():
        rmse = _to_float((series.summary or {}).get("best_backtest_overall_rmse"))
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
        rmse = active_model["avg_overall_rmse_label"]
        source = _format_metric_source(active_model["metric_source"])
        conclusions.append(
            f"Текущая рабочая модель «{active_model['name']}» прогнозирует {active_model['target_count']} ключевых показателей; "
            f"её основная ошибка составляет {rmse} по данным типа «{source}»."
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
        .first()
    )
    latest_evaluation_obj = None
    if latest_forecast_obj and hasattr(latest_forecast_obj, "evaluation"):
        latest_evaluation_obj = latest_forecast_obj.evaluation
    if latest_evaluation_obj is None:
        latest_evaluation_obj = (
            ForecastEvaluation.objects.filter(status=ForecastEvaluation.Status.COMPLETED)
            .select_related("forecast_run", "forecast_run__model_version")
            .first()
        )
    latest_experiment_run_obj = (
        ExperimentRun.objects.select_related("series", "dataset_snapshot", "model_version", "forecast_evaluation")
        .order_by("-created_at")
        .first()
    )
    best_series_obj = _select_best_series()

    latest_dataset = None
    if latest_dataset_obj is not None:
        latest_dataset = {
            "id": str(latest_dataset_obj.id),
            "created_at": latest_dataset_obj.created_at,
            "input_len_hours": latest_dataset_obj.input_len_hours,
            "forecast_horizon_hours": latest_dataset_obj.forecast_horizon_hours,
            "sample_count": latest_dataset_obj.sample_count,
            "master_row_count": latest_dataset_obj.master_row_count,
            "feature_count": len(latest_dataset_obj.feature_columns or []),
            "target_count": len(latest_dataset_obj.target_columns or []),
            "feature_preview": list(latest_dataset_obj.feature_columns or [])[:6],
            "target_preview": list(latest_dataset_obj.target_columns or [])[:6],
        }
        latest_dataset["feature_preview_label"] = _format_metric_list(latest_dataset["feature_preview"])
        latest_dataset["target_preview_label"] = _format_metric_list(latest_dataset["target_preview"])

    active_model = None
    if active_model_obj is not None:
        model_summary = (active_model_obj.metrics or {}).get("summary", {})
        active_model = {
            "id": str(active_model_obj.id),
            "name": active_model_obj.name,
            "created_at": active_model_obj.created_at,
            "forecast_horizon_hours": active_model_obj.forecast_horizon_hours,
            "input_len_hours": active_model_obj.input_len_hours,
            "feature_count": len(active_model_obj.feature_names or []),
            "target_count": len(active_model_obj.target_names or []),
            "target_preview": list(active_model_obj.target_names or [])[:6],
            "dataset_sample_count": active_model_obj.dataset.sample_count if active_model_obj.dataset else 0,
            "avg_overall_rmse": (
                _to_float(leaderboard_entry.get("avg_overall_rmse"))
                if leaderboard_entry
                else _to_float(model_summary.get("overall_rmse"))
            ),
            "avg_overall_mae": (
                _to_float(leaderboard_entry.get("avg_overall_mae"))
                if leaderboard_entry
                else _to_float(model_summary.get("overall_mae"))
            ),
            "avg_macro_mape": (
                _to_float(leaderboard_entry.get("avg_macro_mape"))
                if leaderboard_entry
                else _to_float(model_summary.get("macro_mape"))
            ),
            "metric_source": leaderboard_entry.get("metric_source") if leaderboard_entry else "training",
            "evaluation_count": leaderboard_entry.get("evaluation_count", 0) if leaderboard_entry else 0,
        }
        active_model["avg_overall_rmse_label"] = _fmt_number(active_model["avg_overall_rmse"])
        active_model["avg_overall_mae_label"] = _fmt_number(active_model["avg_overall_mae"])
        active_model["avg_macro_mape_label"] = _fmt_number(active_model["avg_macro_mape"])
        active_model["metric_source_label"] = _format_metric_source(active_model["metric_source"])
        active_model["target_preview_label"] = _format_metric_list(active_model["target_preview"])

    latest_forecast = _extract_forecast_snapshot(latest_forecast_obj)
    if latest_forecast:
        latest_forecast["aqi_start_label"] = _fmt_number(latest_forecast["aqi_start"])
        latest_forecast["aqi_end_label"] = _fmt_number(latest_forecast["aqi_end"])
        latest_forecast["aqi_delta_label"] = _fmt_number(latest_forecast["aqi_delta"])
        latest_forecast["target_metrics_label"] = _format_metric_list(latest_forecast["target_metrics"], limit=5)

    latest_evaluation = _extract_evaluation_summary(latest_evaluation_obj)
    if latest_evaluation:
        latest_evaluation["coverage_ratio_label"] = _fmt_number(
            (latest_evaluation["coverage_ratio"] or 0) * 100, digits=1
        )
        latest_evaluation["overall_rmse_label"] = _fmt_number(latest_evaluation["overall_rmse"])
        latest_evaluation["overall_mae_label"] = _fmt_number(latest_evaluation["overall_mae"])
        latest_evaluation["macro_mape_label"] = _fmt_number((latest_evaluation["macro_mape"] or 0) * 100, digits=1)

    latest_experiment_run = None
    if latest_experiment_run_obj is not None:
        latest_experiment_run = {
            "id": str(latest_experiment_run_obj.id),
            "name": latest_experiment_run_obj.name,
            "status": latest_experiment_run_obj.status,
            "status_label": _format_status(latest_experiment_run_obj.status),
            "created_at": latest_experiment_run_obj.created_at,
            "series_name": latest_experiment_run_obj.series.name if latest_experiment_run_obj.series else None,
            "model_name": latest_experiment_run_obj.model_version.name
            if latest_experiment_run_obj.model_version
            else None,
        }

    best_series = None
    if best_series_obj is not None:
        summary = best_series_obj.summary or {}
        best_series = {
            "id": str(best_series_obj.id),
            "name": best_series_obj.name,
            "description": best_series_obj.description,
            "run_count": int(summary.get("run_count") or 0),
            "completed_run_count": int(summary.get("completed_run_count") or 0),
            "failed_run_count": int(summary.get("failed_run_count") or 0),
            "best_backtest_overall_rmse": _to_float(summary.get("best_backtest_overall_rmse")),
            "created_at": best_series_obj.created_at,
        }
        best_series["best_backtest_overall_rmse_label"] = _fmt_number(best_series["best_backtest_overall_rmse"])

    report = {
        "generated_at": now,
        "generated_at_label": _fmt_dt(now),
        "report_date_label": now.strftime("%d.%m.%Y"),
        "title": "Итоговый отчёт по мониторингу качества воздуха в НПР",
        "subtitle": "Краткая сводка по наблюдениям, датасетам, моделям, прогнозам и экспериментальному контуру.",
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
            "first_label": _fmt_dt(observation_range["first_timestamp"]),
            "latest_label": _fmt_dt(observation_range["latest_timestamp"]),
            "sources": source_summary,
        },
        "latest_dataset": latest_dataset,
        "active_model": active_model,
        "latest_forecast": latest_forecast,
        "latest_evaluation": latest_evaluation,
        "latest_experiment_run": latest_experiment_run,
        "best_series": best_series,
    }
    report["conclusions"] = _build_conclusions(report)
    return report


def _build_styles(font_name: str, bold_font_name: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "AirTitle",
            parent=base["Title"],
            fontName=bold_font_name,
            fontSize=20,
            leading=24,
            textColor=PDF_TEXT,
            spaceAfter=4,
            alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "AirSubtitle",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=9.5,
            leading=13,
            textColor=PDF_MUTED,
        ),
        "section": ParagraphStyle(
            "AirSection",
            parent=base["Heading2"],
            fontName=bold_font_name,
            fontSize=12.5,
            leading=16,
            textColor=PDF_TEXT,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "AirBody",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=9.5,
            leading=13,
            textColor=PDF_TEXT,
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
        "muted": ParagraphStyle(
            "AirMuted",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=8.4,
            leading=11.5,
            textColor=PDF_MUTED,
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
        "card_value": ParagraphStyle(
            "AirCardValue",
            parent=base["BodyText"],
            fontName=bold_font_name,
            fontSize=16,
            leading=19,
            textColor=PDF_TEXT,
        ),
        "card_label": ParagraphStyle(
            "AirCardLabel",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=8,
            leading=10,
            textColor=PDF_MUTED,
        ),
        "label": ParagraphStyle(
            "AirLabel",
            parent=base["BodyText"],
            fontName=bold_font_name,
            fontSize=9.5,
            leading=13,
            textColor=PDF_TEXT,
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
        "table_head": ParagraphStyle(
            "AirTableHead",
            parent=base["BodyText"],
            fontName=bold_font_name,
            fontSize=8.3,
            leading=10.5,
            textColor=PDF_TEXT,
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
        "table_cell": ParagraphStyle(
            "AirTableCell",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=8.2,
            leading=10.4,
            textColor=PDF_TEXT,
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
    }


def _logo_flowable(font_name: str) -> Drawing:
    drawing = Drawing(150, 36)
    drawing.add(Rect(0, 7, 22, 22, rx=5, ry=5, fillColor=PDF_ACCENT, strokeColor=PDF_ACCENT))
    drawing.add(Circle(11, 18, 5, fillColor=colors.white, strokeColor=colors.white))
    drawing.add(Rect(30, 18, 54, 5, fillColor=PDF_TEXT, strokeColor=PDF_TEXT))
    drawing.add(Rect(30, 9, 41, 5, fillColor=PDF_WARM, strokeColor=PDF_WARM))
    drawing.add(String(92, 14, "AIR NPR", fontName=font_name, fontSize=12, fillColor=PDF_TEXT))
    return drawing


def _summary_cards(report: dict, styles: dict[str, ParagraphStyle]):
    cards = [
        ("Наблюдения", _fmt_int(report["counts"]["observations"]), "всего записей"),
        ("Источники", _fmt_int(report["observations"]["source_count"]), "каналы данных"),
        ("Датасеты", _fmt_int(report["counts"]["datasets"]), "собранные срезы"),
        ("Модели", _fmt_int(report["counts"]["models"]), "версии прогноза"),
        ("Прогнозы", _fmt_int(report["counts"]["forecasts"]), "успешные и архивные"),
        ("Эксперименты", _fmt_int(report["counts"]["experiments"]), "запуски серии"),
    ]
    rows = []
    row = []
    for index, (label, value, helper) in enumerate(cards, start=1):
        row.append(
            Table(
                [
                    [Paragraph(label, styles["card_label"])],
                    [Paragraph(value, styles["card_value"])],
                    [Paragraph(helper, styles["muted"])],
                ],
                colWidths=[56 * mm],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), PDF_PANEL),
                        ("BOX", (0, 0), (-1, -1), 0.7, PDF_BORDER),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ]
                ),
            )
        )
        if index % 3 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return Table(
        rows,
        colWidths=[58 * mm, 58 * mm, 58 * mm],
        hAlign="LEFT",
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )


def _simple_detail_table(
    rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle], col_widths=(50 * mm, CONTENT_WIDTH - 50 * mm)
):
    table_rows = [[Paragraph(label, styles["label"]), Paragraph(value, styles["body"])] for label, value in rows]
    return Table(
        table_rows,
        colWidths=list(col_widths),
        hAlign="LEFT",
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.7, PDF_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, PDF_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        ),
    )


def _source_chart(report: dict, font_name: str) -> Drawing:
    drawing = Drawing(CONTENT_WIDTH, 42 * mm)
    sources = report["observations"]["sources"][:4]
    if not sources:
        drawing.add(String(0, 10, "Нет данных для диаграммы.", fontName=font_name, fontSize=9, fillColor=PDF_MUTED))
        return drawing

    chart_x = 0
    chart_y = 8
    chart_w = CONTENT_WIDTH - 12 * mm
    chart_h = 24 * mm
    max_value = max(item["observation_count"] for item in sources) or 1
    bar_gap = 10
    bar_w = max(28, (chart_w - bar_gap * (len(sources) - 1)) / len(sources))

    drawing.add(Rect(chart_x, chart_y, chart_w, chart_h, strokeColor=PDF_BORDER, fillColor=colors.white))
    for idx, source in enumerate(sources):
        bar_height = chart_h * (source["observation_count"] / max_value)
        x = chart_x + idx * (bar_w + bar_gap) + 4
        drawing.add(Rect(x, chart_y, bar_w, bar_height, fillColor=PDF_ACCENT, strokeColor=PDF_ACCENT))
        drawing.add(
            String(
                x + bar_w / 2,
                chart_y + bar_height + 4,
                _fmt_int(source["observation_count"]),
                fontName=font_name,
                fontSize=7.5,
                textAnchor="middle",
                fillColor=PDF_TEXT,
            )
        )
        drawing.add(
            String(
                x + bar_w / 2,
                chart_y - 8,
                source["label"],
                fontName=font_name,
                fontSize=7,
                textAnchor="middle",
                fillColor=PDF_MUTED,
            )
        )
    return drawing


def _aqi_forecast_chart(report: dict, font_name: str) -> Drawing:
    drawing = Drawing(CONTENT_WIDTH, 48 * mm)
    series = (report.get("latest_forecast") or {}).get("aqi_series") or []
    if len(series) < 2:
        drawing.add(
            String(
                0, 10, "Для прогноза AQI пока недостаточно точек.", fontName=font_name, fontSize=9, fillColor=PDF_MUTED
            )
        )
        return drawing

    chart_x = 0
    chart_y = 10
    chart_w = CONTENT_WIDTH - 14 * mm
    chart_h = 28 * mm
    values = [item["value"] for item in series]
    min_value = min(values)
    max_value = max(values)
    spread = max(max_value - min_value, 1)

    drawing.add(Rect(chart_x, chart_y, chart_w, chart_h, strokeColor=PDF_BORDER, fillColor=colors.white))
    points: list[tuple[float, float]] = []
    for idx, item in enumerate(series):
        x = chart_x + (chart_w * idx / max(len(series) - 1, 1))
        y = chart_y + ((item["value"] - min_value) / spread) * chart_h
        points.append((x, y))

    for idx in range(1, len(points)):
        x1, y1 = points[idx - 1]
        x2, y2 = points[idx]
        drawing.add(Line(x1, y1, x2, y2, strokeColor=PDF_WARM, strokeWidth=2))

    step = max(1, len(series) // 5)
    for idx, (x, y) in enumerate(points):
        drawing.add(Circle(x, y, 1.8, fillColor=PDF_WARM, strokeColor=PDF_WARM))
        if idx % step == 0 or idx == len(points) - 1:
            drawing.add(
                String(
                    x,
                    chart_y - 8,
                    series[idx]["label"][11:16] if len(series[idx]["label"]) >= 16 else series[idx]["label"],
                    fontName=font_name,
                    fontSize=6.8,
                    textAnchor="middle",
                    fillColor=PDF_MUTED,
                )
            )

    drawing.add(
        String(
            chart_x + chart_w + 6,
            chart_y + chart_h - 2,
            _fmt_number(max_value),
            fontName=font_name,
            fontSize=7,
            fillColor=PDF_MUTED,
        )
    )
    drawing.add(
        String(
            chart_x + chart_w + 6,
            chart_y - 2,
            _fmt_number(min_value),
            fontName=font_name,
            fontSize=7,
            fillColor=PDF_MUTED,
        )
    )
    return drawing


def _build_source_observation_table(report: dict, styles: dict[str, ParagraphStyle]) -> Table:
    rows = [
        [
            Paragraph("Источник", styles["table_head"]),
            Paragraph("Наблюдения", styles["table_head"]),
            Paragraph("Станции", styles["table_head"]),
            Paragraph("Метрики", styles["table_head"]),
            Paragraph("Последняя точка", styles["table_head"]),
        ]
    ]
    for source in report["observations"]["sources"]:
        rows.append(
            [
                Paragraph(source["label"], styles["table_cell"]),
                Paragraph(_fmt_int(source["observation_count"]), styles["table_cell"]),
                Paragraph(_fmt_int(source["station_count"]), styles["table_cell"]),
                Paragraph(_format_metric_list(source["metrics"], limit=3), styles["table_cell"]),
                Paragraph(_fmt_dt(source["latest_timestamp"]), styles["table_cell"]),
            ]
        )

    return Table(
        rows,
        colWidths=[30 * mm, 22 * mm, 18 * mm, 70 * mm, CONTENT_WIDTH - 140 * mm],
        hAlign="LEFT",
        style=TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PDF_ACCENT_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.7, PDF_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, PDF_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        ),
    )


def render_monitoring_executive_report_pdf(report: dict) -> bytes:
    font_name, bold_font_name = _register_report_font()
    styles = _build_styles(font_name, bold_font_name)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=14 * mm,
        title=report["title"],
        author="Air Monitor Back",
    )

    story = [
        _logo_flowable(bold_font_name),
        Spacer(1, 6),
        Paragraph(report["title"], styles["title"]),
        Paragraph(report["subtitle"], styles["subtitle"]),
        Spacer(1, 8),
        _summary_cards(report, styles),
        Spacer(1, 10),
        HRFlowable(color=PDF_BORDER, thickness=0.8, width="100%"),
        Spacer(1, 8),
        Paragraph("1. Что показывает система сейчас", styles["section"]),
        Paragraph(
            (
                f"На момент формирования отчёта в приложении накоплено {_fmt_int(report['observations']['total_count'])} наблюдений. "
                f"Данные поступают из {_fmt_int(report['observations']['source_count'])} источников и покрывают период "
                f"с {report['observations']['first_label']} по {report['observations']['latest_label']}. "
                f"Это позволяет одновременно видеть ситуацию по отдельным постам MyCityAir и по городскому фону загрязнения."
            ),
            styles["body"],
        ),
        Spacer(1, 6),
        Paragraph("2. Источники наблюдений", styles["section"]),
        Paragraph(
            "Ниже показано, какой вклад в систему вносит каждый источник данных. Чем больше наблюдений и станций, тем устойчивее последующие датасеты и прогнозы.",
            styles["body"],
        ),
        Spacer(1, 4),
        _source_chart(report, font_name),
        Spacer(1, 6),
        _simple_detail_table(
            [
                (
                    "Период данных",
                    f"{report['observations']['first_label']} — {report['observations']['latest_label']}",
                ),
                ("Количество станций", _fmt_int(report["observations"]["station_count"])),
                ("Источники", ", ".join(item["label"] for item in report["observations"]["sources"]) or "—"),
            ],
            styles,
        ),
        Spacer(1, 6),
    ]

    story.append(_build_source_observation_table(report, styles))
    story.extend([Spacer(1, 10), Paragraph("3. Из чего обучалась модель", styles["section"])])

    dataset = report["latest_dataset"]
    if dataset:
        story.append(
            Paragraph(
                (
                    "Последняя обучающая выборка собрана из реальных наблюдений и временных признаков. "
                    "Она нужна для того, чтобы модель улавливала суточные и краткосрочные колебания загрязнения."
                ),
                styles["body"],
            )
        )
        story.extend([Spacer(1, 4)])
        story.append(
            _simple_detail_table(
                [
                    ("Когда собран датасет", f"{_fmt_dt(dataset['created_at'])}"),
                    ("Размер обучающей выборки", f"{_fmt_int(dataset['sample_count'])} временных фрагментов"),
                    ("Общий объём исходных строк", _fmt_int(dataset["master_row_count"])),
                    ("Окно входных данных", f"{dataset['input_len_hours']} часов истории на один прогноз"),
                    ("Горизонт прогноза", f"{dataset['forecast_horizon_hours']} часов вперёд"),
                    ("Основные прогнозируемые показатели", dataset["target_preview_label"]),
                ],
                styles,
            )
        )
    else:
        story.append(Paragraph("Датасеты ещё не собраны.", styles["body"]))

    active_model = report["active_model"]
    story.extend([Spacer(1, 6)])
    if active_model:
        story.append(
            Paragraph(
                "Ниже указана текущая рабочая модель. Именно её backend использует для формирования последних прогнозов по городу.",
                styles["body"],
            )
        )
        story.extend([Spacer(1, 4)])
        story.append(
            _simple_detail_table(
                [
                    ("Название модели", active_model["name"]),
                    ("На чём обучалась", f"выборка на {_fmt_int(active_model['dataset_sample_count'])} фрагментов"),
                    ("Какие показатели прогнозирует", active_model["target_preview_label"]),
                    ("Основная ошибка модели", f"RMSE {active_model['avg_overall_rmse_label']}"),
                    ("Средняя абсолютная ошибка", f"MAE {active_model['avg_overall_mae_label']}"),
                    ("Средняя относительная ошибка", f"MAPE {active_model['avg_macro_mape_label']}%"),
                    ("Откуда взята оценка качества", active_model["metric_source_label"]),
                ],
                styles,
            )
        )
        story.extend(
            [
                Spacer(1, 4),
                Paragraph(
                    "Пояснение к метрикам: RMSE показывает типичный масштаб ошибки с усилением крупных промахов; "
                    "MAE показывает среднюю абсолютную ошибку; MAPE отражает среднюю относительную ошибку в процентах.",
                    styles["muted"],
                ),
            ]
        )
    else:
        story.append(Paragraph("Готовая активная модель пока отсутствует.", styles["body"]))

    story.extend([Spacer(1, 10), Paragraph("4. Последний прогноз по городу", styles["section"])])
    latest_forecast = report["latest_forecast"]
    if latest_forecast:
        story.append(
            Paragraph(
                "График ниже показывает, как меняется прогнозный индекс качества воздуха AQI на горизонте последнего запуска модели.",
                styles["body"],
            )
        )
        story.extend([Spacer(1, 4), _aqi_forecast_chart(report, font_name), Spacer(1, 6)])
        story.append(
            _simple_detail_table(
                [
                    ("Когда построен прогноз", f"{_fmt_dt(latest_forecast['created_at'])}"),
                    ("На сколько часов вперёд", f"{latest_forecast['forecast_horizon_hours']} часов"),
                    ("Использованная модель", latest_forecast["model_name"] or "—"),
                    (
                        "Изменение прогнозного AQI",
                        f"{latest_forecast['aqi_start_label']} → {latest_forecast['aqi_end_label']} (изменение {latest_forecast['aqi_delta_label']})",
                    ),
                    ("Количество временных точек", _fmt_int(latest_forecast["record_count"])),
                    ("Какие показатели считает прогноз", latest_forecast["target_metrics_label"]),
                ],
                styles,
            )
        )
    else:
        story.append(Paragraph("Успешный прогноз пока отсутствует.", styles["body"]))

    latest_evaluation = report["latest_evaluation"]
    story.extend([Spacer(1, 10), Paragraph("5. Насколько прогнозу можно доверять", styles["section"])])
    if latest_evaluation:
        story.append(
            Paragraph(
                "После того как появляются фактические наблюдения, система сравнивает их с прогнозом. "
                "Это позволяет оценить точность модели на реальных данных, а не только на этапе обучения.",
                styles["body"],
            )
        )
        story.extend([Spacer(1, 4)])
        story.append(
            _simple_detail_table(
                [
                    ("Статус проверки", _format_status(latest_evaluation["status"])),
                    (
                        "Ошибка с усилением крупных отклонений",
                        f"RMSE {latest_evaluation['overall_rmse_label']}",
                    ),
                    ("Средняя абсолютная ошибка", f"MAE {latest_evaluation['overall_mae_label']}"),
                    ("Средняя относительная ошибка", f"MAPE {latest_evaluation['macro_mape_label']}%"),
                    (
                        "Покрытие проверкой",
                        f"{latest_evaluation['coverage_ratio_label']}% "
                        f"({latest_evaluation['matched_record_count']}/{latest_evaluation['expected_record_count']})",
                    ),
                    ("Когда выполнена проверка", _fmt_dt(latest_evaluation["evaluated_at_utc"])),
                ],
                styles,
            )
        )
    else:
        story.append(Paragraph("Оценка прогнозов ещё не проводилась.", styles["body"]))

    story.extend([Spacer(1, 10), Paragraph("6. Как развивался исследовательский контур", styles["section"])])
    best_series = report["best_series"]
    latest_run = report["latest_experiment_run"]
    experiment_rows = []
    if best_series:
        experiment_rows.append(("Основная серия экспериментов", best_series["name"]))
        experiment_rows.append(("Количество запусков в серии", _fmt_int(best_series["run_count"])))
        experiment_rows.append(
            ("Лучшая ошибка на исторической проверке", best_series["best_backtest_overall_rmse_label"])
        )
    if latest_run:
        experiment_rows.append(("Последний эксперимент", latest_run["name"]))
        experiment_rows.append(("Текущий статус эксперимента", latest_run["status_label"]))
        experiment_rows.append(("Связанная модель", latest_run["model_name"] or "—"))
    if experiment_rows:
        story.append(
            Paragraph(
                "Этот блок показывает, что исследование не ограничивается одной моделью: система сохраняет серии экспериментов и позволяет сравнивать разные запуски между собой.",
                styles["body"],
            )
        )
        story.extend([Spacer(1, 4)])
        story.append(_simple_detail_table(experiment_rows, styles))
    else:
        story.append(Paragraph("Экспериментальные серии и запуски пока не накоплены.", styles["body"]))

    story.extend([Spacer(1, 10), Paragraph("7. Итоговые выводы", styles["section"])])
    story.append(
        ListFlowable(
            [ListItem(Paragraph(item, styles["body"])) for item in report["conclusions"]],
            bulletType="bullet",
            leftPadding=12,
            bulletFontName=font_name,
            bulletColor=PDF_ACCENT,
        )
    )
    story.extend(
        [
            Spacer(1, 8),
            Paragraph(
                "Отчёт сформирован автоматически backend-сервисом проекта Air Monitor и предназначен для быстрого человеческого чтения, а не только для технической отладки.",
                styles["muted"],
            ),
        ]
    )

    def draw_page(canvas, document):
        canvas.saveState()
        canvas.setFillColor(PDF_ACCENT)
        canvas.rect(0, A4[1] - 8, A4[0], 8, fill=1, stroke=0)
        canvas.setFillColor(PDF_MUTED)
        canvas.setFont(font_name, 8)
        canvas.drawRightString(A4[0] - 16 * mm, 8 * mm, f"Страница {document.page}")
        canvas.drawString(16 * mm, 8 * mm, f"НПР Air Monitor · {report['report_date_label']}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return buffer.getvalue()


def build_monitoring_executive_report_pdf() -> bytes:
    return render_monitoring_executive_report_pdf(build_monitoring_executive_report())
