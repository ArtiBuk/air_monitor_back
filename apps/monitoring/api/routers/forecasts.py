from datetime import UTC

from ninja import Query, Router
from ninja.responses import Status

from apps.authentication.security.jwt import JWTAuth
from apps.monitoring.models import ForecastRun

from ...selectors import (
    get_forecast_evaluation,
    get_forecast_evaluations_by_run_ids,
    get_forecast_run,
    get_forecast_runs_by_ids,
    get_latest_forecast_run,
    get_model_version,
    list_forecast_evaluations,
    list_forecast_runs,
)
from ...services.forecasts import ForecastService
from ...services.task_queue import MonitoringTaskQueueService
from ..schemas import (
    AsyncTaskLaunchSchema,
    ForecastEvaluationSchema,
    ForecastGeneratePayload,
    ForecastRunSchema,
    MessageSchema,
)
from ..utils import accepted_task_response, error_response, not_found_response

router = Router(tags=["Мониторинг: прогнозы"])


@router.get("/forecasts/latest", response={200: ForecastRunSchema, 404: MessageSchema})
def latest_forecast(request):
    """Возвращает последний успешный прогноз."""
    run = get_latest_forecast_run()
    if run is None:
        return not_found_response("Forecast not found.")
    return Status(200, run)


@router.get("/forecasts", response=list[ForecastRunSchema])
def forecasts(request, limit: int = Query(10, ge=1, le=50)):
    """Возвращает последние запуски прогноза."""
    return list_forecast_runs(limit=limit)


@router.get("/forecasts/compare", response={200: list[ForecastRunSchema], 400: MessageSchema, 404: MessageSchema})
def compare_forecasts(request, ids: list[str] = Query(...)):
    """Возвращает несколько запусков прогноза для сравнения."""
    if not ids:
        return error_response(ValueError("At least one forecast id is required."))

    runs = get_forecast_runs_by_ids(ids)
    if len(runs) != len(ids):
        return not_found_response("One or more forecast runs were not found.")
    return Status(200, runs)


@router.get("/forecasts/evaluations", response=list[ForecastEvaluationSchema])
def forecast_evaluations(request, limit: int = Query(10, ge=1, le=50), model_version_id: str | None = None):
    """Возвращает оценки прогнозов, при необходимости с фильтром по модели."""
    return list_forecast_evaluations(limit=limit, model_version_id=model_version_id)


@router.get(
    "/forecasts/evaluations/compare",
    response={200: list[ForecastEvaluationSchema], 400: MessageSchema, 404: MessageSchema},
)
def compare_forecast_evaluations(request, forecast_run_ids: list[str] = Query(...)):
    """Возвращает несколько оценок прогнозов для сравнения."""
    if not forecast_run_ids:
        return error_response(ValueError("At least one forecast run id is required."))

    evaluations = get_forecast_evaluations_by_run_ids(forecast_run_ids)
    if len(evaluations) != len(forecast_run_ids):
        return not_found_response("One or more forecast evaluations were not found.")
    return Status(200, evaluations)


@router.post("/forecasts/generate", response={200: ForecastRunSchema, 400: MessageSchema}, auth=JWTAuth())
def generate_forecast(request, payload: ForecastGeneratePayload):
    """Синхронно запускает генерацию прогноза."""
    model_version = None
    if payload.model_version_id:
        model_version = get_model_version(payload.model_version_id)
        if model_version is None:
            return not_found_response("Model version not found.")

    try:
        result = ForecastService().generate(
            model_version=model_version,
            requested_by=request.auth,
            input_len_hours=payload.input_len_hours,
            forecast_horizon_hours=payload.forecast_horizon_hours,
            generated_from_timestamp_utc=payload.generated_from_timestamp_utc,
        )
    except Exception as exc:
        return error_response(exc)

    return Status(200, ForecastRun.objects.prefetch_related("records").get(id=result.run_id))


@router.post("/forecasts/generate/async", response={202: AsyncTaskLaunchSchema, 400: MessageSchema}, auth=JWTAuth())
def generate_forecast_async(request, payload: ForecastGeneratePayload):
    """Ставит генерацию прогноза в очередь Celery."""
    if payload.model_version_id and get_model_version(payload.model_version_id) is None:
        return not_found_response("Model version not found.")

    try:
        result = MonitoringTaskQueueService().enqueue_generate_forecast(
            model_version_id=str(payload.model_version_id) if payload.model_version_id else None,
            requested_by_id=str(request.auth.id),
            input_len_hours=payload.input_len_hours,
            forecast_horizon_hours=payload.forecast_horizon_hours,
            generated_from_timestamp_utc=(
                payload.generated_from_timestamp_utc.astimezone(UTC).isoformat().replace("+00:00", "Z")
                if payload.generated_from_timestamp_utc is not None
                else None
            ),
            scheduled_for=payload.scheduled_for,
        )
    except Exception as exc:
        return error_response(exc)

    return accepted_task_response(result)


@router.post("/forecasts/backtest", response={200: ForecastRunSchema, 400: MessageSchema}, auth=JWTAuth())
def backtest_forecast(request, payload: ForecastGeneratePayload):
    """Строит исторический прогноз от фиксированного времени отсечения."""
    if payload.generated_from_timestamp_utc is None:
        return error_response(ValueError("generated_from_timestamp_utc is required for backtesting."))
    return generate_forecast(request, payload)


@router.get("/forecasts/{forecast_run_id}/evaluation", response={200: ForecastEvaluationSchema, 404: MessageSchema})
def forecast_evaluation_detail(request, forecast_run_id: str):
    """Возвращает оценку качества конкретного прогноза."""
    evaluation = get_forecast_evaluation(forecast_run_id)
    if evaluation is None:
        return not_found_response("Forecast evaluation not found.")
    return Status(200, evaluation)


@router.post(
    "/forecasts/{forecast_run_id}/evaluate",
    response={200: ForecastEvaluationSchema, 400: MessageSchema, 404: MessageSchema},
    auth=JWTAuth(),
)
def evaluate_forecast(request, forecast_run_id: str):
    """Оценивает прогноз по фактическим наблюдениям."""
    from apps.monitoring.services.evaluation import ForecastEvaluationService

    forecast_run = get_forecast_run(forecast_run_id)
    if forecast_run is None:
        return not_found_response("Forecast not found.")

    try:
        ForecastEvaluationService().evaluate(forecast_run=forecast_run)
    except Exception as exc:
        return error_response(exc)

    evaluation = get_forecast_evaluation(forecast_run_id)
    return Status(200, evaluation)


@router.get("/forecasts/{forecast_run_id}", response={200: ForecastRunSchema, 404: MessageSchema})
def forecast_detail(request, forecast_run_id: str):
    """Возвращает один запуск прогноза вместе с его записями."""
    run = get_forecast_run(forecast_run_id)
    if run is None:
        return not_found_response("Forecast not found.")
    return Status(200, run)
