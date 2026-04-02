from datetime import UTC

from ninja import Query, Router
from ninja.responses import Status

from apps.authentication.security.jwt import JWTAuth
from apps.monitoring.services.observations import ObservationSyncService

from ...selectors import list_observations
from ...services.task_queue import MonitoringTaskQueueService
from ..schemas import (
    AsyncTaskLaunchSchema,
    CollectObservationsPayload,
    MessageSchema,
    ObservationSchema,
    ObservationSyncSchema,
)
from ..utils import accepted_task_response, error_response

router = Router(tags=["Мониторинг: наблюдения"])


@router.get("/observations", response=list[ObservationSchema])
def observations(request, metric: str | None = None, source: str | None = None, limit: int = Query(100, ge=1, le=500)):
    """Возвращает последние наблюдения с необязательной фильтрацией."""
    return list_observations(metric=metric, source=source, limit=limit)


@router.post("/observations/collect", response={200: ObservationSyncSchema, 400: MessageSchema}, auth=JWTAuth())
def collect_observations(request, payload: CollectObservationsPayload):
    """Собирает наблюдения и синхронно сохраняет их в БД."""
    try:
        result = ObservationSyncService().collect(
            start=payload.start.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            finish=payload.finish.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            interval=payload.interval,
            window_hours=payload.window_hours,
        )
    except Exception as exc:
        return error_response(exc)

    return Status(
        200,
        {
            "raw_count": result.raw_count,
            "cleaned_count": result.cleaned_count,
            "db_created_count": result.db_created_count,
            "db_updated_count": result.db_updated_count,
        },
    )


@router.post("/observations/collect/async", response={202: AsyncTaskLaunchSchema, 400: MessageSchema}, auth=JWTAuth())
def collect_observations_async(request, payload: CollectObservationsPayload):
    """Ставит сбор наблюдений в очередь Celery."""
    try:
        result = MonitoringTaskQueueService().enqueue_collect_observations(
            start=payload.start.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            finish=payload.finish.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            interval=payload.interval,
            window_hours=payload.window_hours,
            requested_by_id=str(request.auth.id),
            scheduled_for=payload.scheduled_for,
        )
    except Exception as exc:
        return error_response(exc)

    return accepted_task_response(result)
