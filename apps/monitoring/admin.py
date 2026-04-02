from django.contrib import admin

from .models import DatasetSnapshot, ForecastRecord, ForecastRun, ModelVersion, Observation, ScheduledMonitoringTask


@admin.register(Observation)
class ObservationAdmin(admin.ModelAdmin):
    list_display = ("source", "metric", "value", "observed_at_utc", "station_name")
    list_filter = ("source", "metric")
    search_fields = ("station_name", "station_id", "metric")


class ForecastRecordInline(admin.TabularInline):
    model = ForecastRecord
    extra = 0
    can_delete = False
    readonly_fields = ("timestamp_utc", "values", "created_at", "updated_at")


@admin.register(ForecastRun)
class ForecastRunAdmin(admin.ModelAdmin):
    list_display = ("status", "generated_from_timestamp_utc", "forecast_horizon_hours", "created_at")
    list_filter = ("status",)
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [ForecastRecordInline]


@admin.register(DatasetSnapshot)
class DatasetSnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "input_len_hours", "forecast_horizon_hours", "sample_count", "created_at")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "is_active", "input_len_hours", "forecast_horizon_hours", "created_at")
    list_filter = ("status", "is_active")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ScheduledMonitoringTask)
class ScheduledMonitoringTaskAdmin(admin.ModelAdmin):
    list_display = ("operation", "status", "scheduled_for", "requested_by", "celery_task_id", "created_at")
    list_filter = ("operation", "status")
    search_fields = ("celery_task_id",)
    readonly_fields = ("id", "created_at", "updated_at", "started_at", "finished_at")
