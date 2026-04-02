from datetime import datetime
from typing import Any

from ninja import Schema


class AsyncTaskLaunchSchema(Schema):
    task_id: str
    status: str
    operation: str
    scheduled_task_id: str | None = None
    scheduled_for: datetime | None = None
    is_scheduled: bool = False


class AsyncTaskStatusSchema(Schema):
    task_id: str
    status: str
    ready: bool
    successful: bool
    result: Any | None = None
    error: str | None = None


class MessageSchema(Schema):
    detail: str


class ScheduledTaskSchema(Schema):
    id: str
    operation: str
    status: str
    scheduled_for: datetime
    celery_task_id: str
    payload: dict[str, Any]
    result: Any | None = None
    error: str = ""
    requested_by_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
