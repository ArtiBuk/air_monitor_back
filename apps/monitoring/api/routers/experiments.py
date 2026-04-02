from datetime import UTC

from ninja import Query, Router
from ninja.responses import Status

from apps.authentication.security.jwt import JWTAuth
from apps.monitoring.services.experiments import ExperimentService
from apps.monitoring.services.series import (
    build_experiment_series_report,
)
from apps.monitoring.services.series import (
    create_experiment_series as create_experiment_series_service,
)
from apps.monitoring.services.task_queue import MonitoringTaskQueueService

from ...selectors import (
    get_experiment_run,
    get_experiment_runs_by_ids,
    get_experiment_series,
    get_experiment_series_by_ids,
    list_experiment_runs,
    list_experiment_runs_by_series,
    list_experiment_series,
)
from ..schemas import (
    AsyncTaskLaunchSchema,
    CreateExperimentSeriesPayload,
    ExperimentRunSchema,
    ExperimentSeriesReportSchema,
    ExperimentSeriesSchema,
    MessageSchema,
    RunExperimentPayload,
)
from ..utils import accepted_task_response, error_response, not_found_response

router = Router(tags=["Мониторинг: эксперименты"])


def _build_experiment_run_kwargs(payload: RunExperimentPayload) -> dict:
    """Преобразует API payload эксперимента в аргументы сервиса."""
    return {
        "name": payload.name,
        "input_len_hours": payload.dataset.input_len_hours,
        "forecast_horizon_hours": payload.dataset.forecast_horizon_hours,
        "feature_columns": payload.dataset.feature_columns,
        "target_columns": payload.dataset.target_columns,
        "training_config": {
            "epochs": payload.training.epochs,
            "batch_size": payload.training.batch_size,
            "lr": payload.training.lr,
            "weight_decay": payload.training.weight_decay,
            "patience": payload.training.patience,
            "seed": payload.training.seed,
        },
        "generated_from_timestamp_utc": (
            payload.backtest.generated_from_timestamp_utc if payload.backtest is not None else None
        ),
    }


def _serialize_series_configuration(payload: CreateExperimentSeriesPayload) -> dict | None:
    """Преобразует typed-конфиг серии в JSON для хранения."""
    if payload.configuration is None:
        return None
    return payload.configuration.model_dump(exclude_none=True)


@router.get("/experiments", response=list[ExperimentRunSchema])
def experiments(request, limit: int = Query(10, ge=1, le=50), series_id: str | None = None):
    """Возвращает последние запуски экспериментов."""
    if series_id is not None:
        if get_experiment_series(series_id) is None:
            return Status(200, [])
        return list_experiment_runs_by_series(series_id=series_id, limit=limit)
    return list_experiment_runs(limit=limit)


@router.get("/experiments/compare", response={200: list[ExperimentRunSchema], 400: MessageSchema, 404: MessageSchema})
def compare_experiments(request, ids: list[str] = Query(...)):
    """Возвращает несколько запусков экспериментов для сравнения."""
    if not ids:
        return error_response(ValueError("At least one experiment run id is required."))

    experiments_list = get_experiment_runs_by_ids(ids)
    if len(experiments_list) != len(ids):
        return not_found_response("One or more experiment runs were not found.")
    return Status(200, experiments_list)


@router.post("/experiments/run", response={200: ExperimentRunSchema, 400: MessageSchema}, auth=JWTAuth())
def run_experiment(request, payload: RunExperimentPayload):
    """Запускает полный эксперимент: датасет, обучение и при необходимости backtest."""
    series = None
    if payload.series_id is not None:
        series = get_experiment_series(payload.series_id)
        if series is None:
            return not_found_response("Experiment series not found.")

    try:
        result = ExperimentService().run(
            requested_by=request.auth,
            series=series,
            **_build_experiment_run_kwargs(payload),
        )
    except Exception as exc:
        return error_response(exc)

    experiment_run = get_experiment_run(result.experiment_run_id)
    return Status(200, experiment_run)


@router.post(
    "/experiments/run/async",
    response={202: AsyncTaskLaunchSchema, 400: MessageSchema, 404: MessageSchema},
    auth=JWTAuth(),
)
def run_experiment_async(request, payload: RunExperimentPayload):
    """Ставит полный experiment run в очередь Celery."""
    if payload.series_id is not None and get_experiment_series(payload.series_id) is None:
        return not_found_response("Experiment series not found.")

    try:
        result = MonitoringTaskQueueService().enqueue_run_experiment(
            requested_by_id=str(request.auth.id),
            series_id=str(payload.series_id) if payload.series_id is not None else None,
            name=payload.name,
            input_len_hours=payload.dataset.input_len_hours,
            forecast_horizon_hours=payload.dataset.forecast_horizon_hours,
            feature_columns=payload.dataset.feature_columns,
            target_columns=payload.dataset.target_columns,
            generated_from_timestamp_utc=(
                payload.backtest.generated_from_timestamp_utc.astimezone(UTC).isoformat().replace("+00:00", "Z")
                if payload.backtest is not None and payload.backtest.generated_from_timestamp_utc is not None
                else None
            ),
            training_config={
                "epochs": payload.training.epochs,
                "batch_size": payload.training.batch_size,
                "lr": payload.training.lr,
                "weight_decay": payload.training.weight_decay,
                "patience": payload.training.patience,
                "seed": payload.training.seed,
            },
            scheduled_for=payload.scheduled_for,
        )
    except Exception as exc:
        return error_response(exc)

    return accepted_task_response(result)


@router.get("/experiments/{experiment_run_id}", response={200: ExperimentRunSchema, 404: MessageSchema})
def experiment_detail(request, experiment_run_id: str):
    """Возвращает один запуск эксперимента."""
    experiment_run = get_experiment_run(experiment_run_id)
    if experiment_run is None:
        return not_found_response("Experiment run not found.")
    return Status(200, experiment_run)


@router.get("/experiment-series", response=list[ExperimentSeriesSchema])
def experiment_series(request, limit: int = Query(10, ge=1, le=50)):
    """Возвращает последние серии экспериментов."""
    return list_experiment_series(limit=limit)


@router.get(
    "/experiment-series/compare",
    response={200: list[ExperimentSeriesSchema], 400: MessageSchema, 404: MessageSchema},
)
def compare_experiment_series(request, ids: list[str] = Query(...)):
    """Возвращает несколько серий экспериментов для сравнения."""
    if not ids:
        return error_response(ValueError("At least one experiment series id is required."))

    series_list = get_experiment_series_by_ids(ids)
    if len(series_list) != len(ids):
        return not_found_response("One or more experiment series were not found.")
    return Status(200, series_list)


@router.get(
    "/experiment-series/reports/compare",
    response={200: list[ExperimentSeriesReportSchema], 400: MessageSchema, 404: MessageSchema},
)
def compare_experiment_series_reports(request, ids: list[str] = Query(...)):
    """Возвращает несколько отчётов по сериям экспериментов."""
    if not ids:
        return error_response(ValueError("At least one experiment series id is required."))

    series_list = get_experiment_series_by_ids(ids)
    if len(series_list) != len(ids):
        return not_found_response("One or more experiment series were not found.")

    reports = []
    for series in series_list:
        runs = list_experiment_runs_by_series(series_id=series.id, limit=100)
        reports.append(build_experiment_series_report(series=series, runs=list(runs)))
    return Status(200, reports)


@router.post("/experiment-series", response={201: ExperimentSeriesSchema, 400: MessageSchema}, auth=JWTAuth())
def create_experiment_series(request, payload: CreateExperimentSeriesPayload):
    """Создает новую серию экспериментов."""
    try:
        series = create_experiment_series_service(
            requested_by=request.auth,
            name=payload.name,
            description=payload.description,
            configuration=_serialize_series_configuration(payload),
        )
    except Exception as exc:
        return error_response(exc)

    return Status(201, series)


@router.get("/experiment-series/{series_id}/runs", response={200: list[ExperimentRunSchema], 404: MessageSchema})
def experiment_series_runs(request, series_id: str, limit: int = Query(20, ge=1, le=100)):
    """Возвращает запуски, входящие в серию экспериментов."""
    if get_experiment_series(series_id) is None:
        return not_found_response("Experiment series not found.")
    return Status(200, list_experiment_runs_by_series(series_id=series_id, limit=limit))


@router.get("/experiment-series/{series_id}/report", response={200: ExperimentSeriesReportSchema, 404: MessageSchema})
def experiment_series_report(request, series_id: str):
    """Возвращает сводный отчёт по серии экспериментов."""
    series = get_experiment_series(series_id)
    if series is None:
        return not_found_response("Experiment series not found.")
    runs = list_experiment_runs_by_series(series_id=series_id, limit=100)
    return Status(200, build_experiment_series_report(series=series, runs=list(runs)))


@router.get("/experiment-series/{series_id}", response={200: ExperimentSeriesSchema, 404: MessageSchema})
def experiment_series_detail(request, series_id: str):
    """Возвращает одну серию экспериментов."""
    series = get_experiment_series(series_id)
    if series is None:
        return not_found_response("Experiment series not found.")
    return Status(200, series)
