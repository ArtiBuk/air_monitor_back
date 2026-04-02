from ninja import Query, Router
from ninja.responses import Status

from apps.authentication.security.jwt import JWTAuth

from ...selectors import get_dataset_snapshot, list_dataset_snapshots
from ...services.task_queue import MonitoringTaskQueueService
from ...services.training import ModelLifecycleService
from ..schemas import AsyncTaskLaunchSchema, BuildDatasetPayload, DatasetSnapshotSchema, MessageSchema
from ..utils import accepted_task_response, error_response, not_found_response

router = Router(tags=["Мониторинг: датасеты"])


@router.get("/datasets", response=list[DatasetSnapshotSchema])
def datasets(request, limit: int = Query(10, ge=1, le=50)):
    """Возвращает последние срезы датасетов."""
    return list_dataset_snapshots(limit=limit)


@router.post("/datasets/build", response={200: DatasetSnapshotSchema, 400: MessageSchema}, auth=JWTAuth())
def build_dataset(request, payload: BuildDatasetPayload):
    """Синхронно собирает срез датасета."""
    try:
        result = ModelLifecycleService().build_dataset(
            input_len_hours=payload.input_len_hours,
            forecast_horizon_hours=payload.forecast_horizon_hours,
            feature_columns=payload.feature_columns,
            target_columns=payload.target_columns,
        )
    except Exception as exc:
        return error_response(exc)

    return Status(200, result)


@router.post("/datasets/build/async", response={202: AsyncTaskLaunchSchema, 400: MessageSchema}, auth=JWTAuth())
def build_dataset_async(request, payload: BuildDatasetPayload):
    """Ставит сборку среза датасета в очередь Celery."""
    try:
        result = MonitoringTaskQueueService().enqueue_build_dataset(
            input_len_hours=payload.input_len_hours,
            forecast_horizon_hours=payload.forecast_horizon_hours,
            feature_columns=payload.feature_columns,
            target_columns=payload.target_columns,
            requested_by_id=str(request.auth.id),
            scheduled_for=payload.scheduled_for,
        )
    except Exception as exc:
        return error_response(exc)

    return accepted_task_response(result)


@router.get("/datasets/{dataset_snapshot_id}", response={200: DatasetSnapshotSchema, 404: MessageSchema})
def dataset_detail(request, dataset_snapshot_id: str):
    """Возвращает один срез датасета."""
    snapshot = get_dataset_snapshot(dataset_snapshot_id)
    if snapshot is None:
        return not_found_response("Dataset snapshot not found.")
    return Status(200, snapshot)
