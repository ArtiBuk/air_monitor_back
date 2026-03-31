from ninja import Router

from ...services.task_queue import MonitoringTaskQueueService
from ..schemas import AsyncTaskStatusSchema
from ..utils import task_status_response

router = Router(tags=["Мониторинг: задачи"])


@router.get("/tasks/{task_id}", response=AsyncTaskStatusSchema)
def monitoring_task_status(request, task_id: str):
    """Возвращает текущий статус фоновой задачи мониторинга."""
    result = MonitoringTaskQueueService().get_status(task_id=task_id)
    return task_status_response(result)
