from django.conf import settings
from django.contrib import admin
from django.urls import path, re_path
from django.views.static import serve

from apps.common.api.health import liveness_probe, readiness_probe
from config.api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("health/live/", liveness_probe),
    path("health/ready/", readiness_probe),
    re_path(r"^static/(?P<path>.*)$", serve, {"document_root": settings.STATIC_ROOT}),
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
