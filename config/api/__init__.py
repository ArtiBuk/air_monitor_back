from ninja import NinjaAPI

from apps.authentication.api.router import router as auth_router
from apps.monitoring.api.router import router as monitoring_router
from apps.users.api.router import router as users_router

api = NinjaAPI(
    title="Air Monitor API",
    version="1.0.0",
    urls_namespace="air-monitor-api",
)

api.add_router("/auth/", auth_router)
api.add_router("/users/", users_router)
api.add_router("/monitoring/", monitoring_router)
