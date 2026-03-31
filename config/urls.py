from django.contrib import admin
from django.urls import path

from apps.common.api.health import liveness_probe, readiness_probe
from config.api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("health/live/", liveness_probe),
    path("health/ready/", readiness_probe),
]
