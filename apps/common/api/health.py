from django.db import connections
from django.http import JsonResponse


def liveness_probe(request):
    """Возвращает статус liveness-проверки."""
    return JsonResponse({"status": "ok"})


def readiness_probe(request):
    """Возвращает статус readiness-проверки."""
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # pragma: no cover
        return JsonResponse({"status": "error", "detail": str(exc)}, status=503)

    return JsonResponse({"status": "ok"})
