import logging
import time
import uuid

request_logger = logging.getLogger("api.requests")


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        started_at = time.perf_counter()

        request.request_id = request_id
        response = self.get_response(request)

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        response["X-Request-ID"] = request_id

        request_logger.info(
            "%s %s status=%s duration_ms=%s request_id=%s",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response
