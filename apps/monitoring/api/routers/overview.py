from ninja import Router
from ninja.responses import Status

from ...selectors import get_monitoring_overview
from ..schemas import MonitoringOverviewSchema

router = Router(tags=["Мониторинг: overview"])


@router.get("/overview", response=MonitoringOverviewSchema)
def monitoring_overview(request):
    """Возвращает реальные counts и конфиг автоматического hourly-сбора."""
    return Status(200, get_monitoring_overview())
