from django.http import HttpResponse
from ninja import Router
from ninja.responses import Status

from apps.authentication.security.jwt import JWTAuth

from ...selectors import get_monitoring_overview
from ...services.executive_report import build_monitoring_executive_report_pdf
from ..schemas import MonitoringOverviewSchema

router = Router(tags=["Мониторинг: overview"])


@router.get("/overview", response=MonitoringOverviewSchema)
def monitoring_overview(request):
    """Возвращает реальные counts и конфиг автоматического hourly-сбора."""
    return Status(200, get_monitoring_overview())


@router.get("/overview/report.pdf", auth=JWTAuth())
def monitoring_overview_report(request):
    """Скачивает краткий PDF-отчёт по текущему состоянию мониторингового пайплайна."""
    payload = build_monitoring_executive_report_pdf()
    response = HttpResponse(payload, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="air-monitor-report.pdf"'
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response
