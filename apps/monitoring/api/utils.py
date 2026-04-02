from ninja.responses import Status

from apps.monitoring.services.task_queue import MonitoringTaskLaunchResult, MonitoringTaskStatusResult


def error_response(exc: Exception, *, status_code: int = 400):
    return Status(status_code, {"detail": str(exc)})


def not_found_response(detail: str):
    return Status(404, {"detail": detail})


def accepted_task_response(result: MonitoringTaskLaunchResult):
    return Status(
        202,
        {
            "task_id": result.task_id,
            "status": result.status,
            "operation": result.operation,
            "scheduled_task_id": result.scheduled_task_id,
            "scheduled_for": result.scheduled_for,
            "is_scheduled": result.is_scheduled,
        },
    )


def task_status_response(result: MonitoringTaskStatusResult):
    return Status(
        200,
        {
            "task_id": result.task_id,
            "status": result.status,
            "ready": result.ready,
            "successful": result.successful,
            "result": result.result,
            "error": result.error,
        },
    )
