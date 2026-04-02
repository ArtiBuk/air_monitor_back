from ninja import Query, Router
from ninja.responses import Status

from apps.authentication.security.jwt import JWTAuth

from ...selectors import (
    get_active_model_version,
    get_dataset_snapshot,
    get_model_version,
    get_model_versions_by_ids,
    list_forecast_evaluations,
    list_model_versions,
)
from ...services.reporting import build_model_leaderboard
from ...services.task_queue import MonitoringTaskQueueService
from ...services.training import ModelLifecycleService
from ..schemas import (
    AsyncTaskLaunchSchema,
    MessageSchema,
    ModelLeaderboardEntrySchema,
    ModelVersionSchema,
    TrainModelPayload,
)
from ..utils import accepted_task_response, error_response, not_found_response

router = Router(tags=["Мониторинг: модели"])


@router.get("/models", response=list[ModelVersionSchema])
def model_versions(request, limit: int = Query(10, ge=1, le=50)):
    """Возвращает последние версии моделей."""
    return list_model_versions(limit=limit)


@router.get("/models/compare", response={200: list[ModelVersionSchema], 400: MessageSchema, 404: MessageSchema})
def compare_model_versions(request, ids: list[str] = Query(...)):
    """Возвращает несколько версий моделей для сравнения."""
    if not ids:
        return error_response(ValueError("At least one model version id is required."))

    model_versions_list = get_model_versions_by_ids(ids)
    if len(model_versions_list) != len(ids):
        return not_found_response("One or more model versions were not found.")
    return Status(200, model_versions_list)


@router.get("/models/leaderboard", response={200: list[ModelLeaderboardEntrySchema], 400: MessageSchema})
def model_leaderboard(request, metric: str = Query("overall_rmse"), limit: int = Query(10, ge=1, le=50)):
    """Возвращает лидерборд моделей по метрикам backtest."""
    if metric not in {"overall_rmse", "overall_mae", "macro_mape"}:
        return error_response(ValueError("metric must be one of: overall_rmse, overall_mae, macro_mape."))

    evaluations = list_forecast_evaluations(limit=500)
    leaderboard = build_model_leaderboard(evaluations=evaluations, metric=metric)
    return Status(200, leaderboard[:limit])


@router.get("/models/active", response={200: ModelVersionSchema, 404: MessageSchema})
def active_model(request):
    """Возвращает активную готовую к использованию модель."""
    model_version = get_active_model_version()
    if model_version is None:
        return not_found_response("Active model not found.")
    return Status(200, model_version)


@router.post("/models/train", response={200: ModelVersionSchema, 400: MessageSchema}, auth=JWTAuth())
def train_model(request, payload: TrainModelPayload):
    """Синхронно обучает новую версию модели."""
    dataset_snapshot = None
    if payload.dataset_snapshot_id:
        dataset_snapshot = get_dataset_snapshot(payload.dataset_snapshot_id)
        if dataset_snapshot is None:
            return not_found_response("Dataset snapshot not found.")

    try:
        result = ModelLifecycleService().train(
            dataset_snapshot=dataset_snapshot,
            requested_by=request.auth,
            epochs=payload.epochs,
            batch_size=payload.batch_size,
            lr=payload.lr,
            weight_decay=payload.weight_decay,
            patience=payload.patience,
            seed=payload.seed,
        )
    except Exception as exc:
        return error_response(exc)

    return Status(200, result)


@router.post("/models/train/async", response={202: AsyncTaskLaunchSchema, 400: MessageSchema}, auth=JWTAuth())
def train_model_async(request, payload: TrainModelPayload):
    """Ставит обучение модели в очередь Celery."""
    if payload.dataset_snapshot_id and get_dataset_snapshot(payload.dataset_snapshot_id) is None:
        return not_found_response("Dataset snapshot not found.")

    try:
        result = MonitoringTaskQueueService().enqueue_train_model(
            dataset_snapshot_id=str(payload.dataset_snapshot_id) if payload.dataset_snapshot_id else None,
            requested_by_id=str(request.auth.id),
            epochs=payload.epochs,
            batch_size=payload.batch_size,
            lr=payload.lr,
            weight_decay=payload.weight_decay,
            patience=payload.patience,
            seed=payload.seed,
            scheduled_for=payload.scheduled_for,
        )
    except Exception as exc:
        return error_response(exc)

    return accepted_task_response(result)


@router.get("/models/{model_version_id}", response={200: ModelVersionSchema, 404: MessageSchema})
def model_version_detail(request, model_version_id: str):
    """Возвращает одну версию модели."""
    model_version = get_model_version(model_version_id)
    if model_version is None:
        return not_found_response("Model version not found.")
    return Status(200, model_version)
