from typing import Any

from ninja import Schema


class AsyncTaskLaunchSchema(Schema):
    task_id: str
    status: str
    operation: str


class AsyncTaskStatusSchema(Schema):
    task_id: str
    status: str
    ready: bool
    successful: bool
    result: Any | None = None
    error: str | None = None


class MessageSchema(Schema):
    detail: str
