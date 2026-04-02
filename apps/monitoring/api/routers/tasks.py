from ninja import Query, Router
from ninja.responses import Status

from apps.authentication.security.jwt import JWTAuth

from ...services.task_queue import MonitoringTaskQueueService
from ..schemas import AsyncTaskStatusSchema, MessageSchema, ScheduledTaskSchema
from ..utils import error_response, not_found_response, task_status_response

router = Router(tags=["Мониторинг: задачи"])


@router.get("/tasks/{task_id}", response=AsyncTaskStatusSchema)
def monitoring_task_status(request, task_id: str):
    """Возвращает текущий статус фоновой задачи мониторинга."""
    result = MonitoringTaskQueueService().get_status(task_id=task_id)
    return task_status_response(result)


@router.get("/scheduled-tasks", response=list[ScheduledTaskSchema], auth=JWTAuth())
def scheduled_tasks(request, limit: int = Query(20, ge=1, le=100), status: str | None = None):
    """Возвращает запланированные задачи текущего пользователя."""
    return MonitoringTaskQueueService().list_scheduled_tasks(
        requested_by_id=str(request.auth.id),
        limit=limit,
        status=status,
    )


@router.get("/scheduled-tasks/{scheduled_task_id}", response={200: ScheduledTaskSchema, 404: MessageSchema}, auth=JWTAuth())
def scheduled_task_detail(request, scheduled_task_id: str):
    """Возвращает одну запланированную задачу текущего пользователя."""
    scheduled_task = MonitoringTaskQueueService().get_scheduled_task(
        scheduled_task_id=scheduled_task_id,
        requested_by_id=str(request.auth.id),
    )
    if scheduled_task is None:
        return not_found_response("Scheduled task not found.")
    return Status(200, scheduled_task)


@router.post(
    "/scheduled-tasks/{scheduled_task_id}/cancel",
    response={200: ScheduledTaskSchema, 400: MessageSchema, 404: MessageSchema},
    auth=JWTAuth(),
)
def cancel_scheduled_task(request, scheduled_task_id: str):
    """Отменяет задачу, которая ещё не начала выполняться."""
    service = MonitoringTaskQueueService()
    if service.get_scheduled_task(scheduled_task_id=scheduled_task_id, requested_by_id=str(request.auth.id)) is None:
        return not_found_response("Scheduled task not found.")

    try:
        scheduled_task = service.cancel_scheduled_task(
            scheduled_task_id=scheduled_task_id,
            requested_by_id=str(request.auth.id),
        )
    except Exception as exc:
        return error_response(exc)

    return Status(200, scheduled_task)
