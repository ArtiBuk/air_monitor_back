import json

from django.contrib import admin, messages
from django.db import transaction
from django.utils.html import format_html

from .models import (
    DatasetSnapshot,
    ExperimentRun,
    ExperimentSeries,
    ForecastEvaluation,
    ForecastRecord,
    ForecastRun,
    ModelVersion,
    Observation,
    ScheduledMonitoringTask,
)
from .services.task_queue import MonitoringTaskQueueService

admin.site.site_header = "Air Monitor Admin"
admin.site.site_title = "Air Monitor Admin"
admin.site.index_title = "Управление данными мониторинга качества воздуха"


class MonitoringAdminMixin(admin.ModelAdmin):
    list_per_page = 50
    show_full_result_count = True
    save_on_top = True

    @staticmethod
    def _pretty_json(value):
        if value in (None, "", {}, []):
            return "-"
        return format_html(
            "<pre style='white-space: pre-wrap; margin: 0'>{}</pre>", json.dumps(value, ensure_ascii=False, indent=2)
        )


@admin.action(description="Сделать выбранную готовую модель активной")
def make_model_active(modeladmin, request, queryset):
    if queryset.count() != 1:
        modeladmin.message_user(request, "Нужно выбрать ровно одну модель.", level=messages.ERROR)
        return

    model = queryset.first()
    if model.status != ModelVersion.Status.READY:
        modeladmin.message_user(
            request, "Активной можно сделать только модель со статусом ready.", level=messages.ERROR
        )
        return

    with transaction.atomic():
        ModelVersion.objects.filter(is_active=True).update(is_active=False)
        queryset.update(is_active=True)

    modeladmin.message_user(request, f"Активная модель переключена на {model.name}.", level=messages.SUCCESS)


@admin.action(description="Отменить выбранные запланированные задачи")
def cancel_scheduled_tasks(modeladmin, request, queryset):
    service = MonitoringTaskQueueService()
    cancelled = 0
    skipped = 0

    for task in queryset:
        if task.status != ScheduledMonitoringTask.Status.SCHEDULED:
            skipped += 1
            continue
        service.cancel_scheduled_task(scheduled_task_id=str(task.id))
        cancelled += 1

    if cancelled:
        modeladmin.message_user(request, f"Отменено задач: {cancelled}.", level=messages.SUCCESS)
    if skipped:
        modeladmin.message_user(
            request,
            f"Пропущено задач не в статусе scheduled: {skipped}.",
            level=messages.WARNING,
        )


@admin.register(Observation)
class ObservationAdmin(MonitoringAdminMixin):
    date_hierarchy = "observed_at_utc"
    ordering = ("-observed_at_utc",)
    list_display = (
        "observed_at_utc",
        "time_window_utc",
        "source",
        "metric",
        "value",
        "unit",
        "station_name",
        "station_id",
    )
    list_filter = ("source", "metric", "source_kind", "unit")
    search_fields = ("id", "fingerprint", "station_name", "station_id", "metric")
    readonly_fields = ("id", "fingerprint", "created_at", "updated_at", "extra_preview")
    fields = (
        "id",
        "fingerprint",
        "source",
        "source_kind",
        "station_id",
        "station_name",
        ("lat", "lon"),
        ("observed_at_utc", "time_bucket_utc", "time_window_utc"),
        ("metric", "value", "unit"),
        "extra",
        "extra_preview",
        ("created_at", "updated_at"),
    )

    @admin.display(description="Extra preview")
    def extra_preview(self, obj):
        return self._pretty_json(obj.extra)


class ForecastRecordInline(admin.TabularInline):
    model = ForecastRecord
    extra = 0
    can_delete = False
    readonly_fields = ("timestamp_utc", "values", "created_at", "updated_at")
    ordering = ("timestamp_utc",)


@admin.register(ForecastRun)
class ForecastRunAdmin(MonitoringAdminMixin):
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_display = (
        "id",
        "status",
        "model_version",
        "generated_from_timestamp_utc",
        "forecast_horizon_hours",
        "record_count",
        "created_at",
    )
    list_filter = ("status", "forecast_horizon_hours")
    search_fields = ("id", "model_version__id", "model_version__name", "error_message")
    autocomplete_fields = ("requested_by", "model_version")
    readonly_fields = ("id", "created_at", "updated_at", "metadata_preview")
    inlines = [ForecastRecordInline]

    @admin.display(description="Records")
    def record_count(self, obj):
        return obj.records.count()

    @admin.display(description="Metadata preview")
    def metadata_preview(self, obj):
        return self._pretty_json(obj.metadata)


@admin.register(ForecastEvaluation)
class ForecastEvaluationAdmin(MonitoringAdminMixin):
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_display = (
        "id",
        "status",
        "forecast_run",
        "model_version_name",
        "coverage_ratio",
        "matched_record_count",
        "expected_record_count",
        "evaluated_at_utc",
    )
    list_filter = ("status",)
    search_fields = ("id", "forecast_run__id", "forecast_run__model_version__name", "error_message")
    autocomplete_fields = ("forecast_run",)
    readonly_fields = ("id", "created_at", "updated_at", "metrics_preview")

    @admin.display(description="Model")
    def model_version_name(self, obj):
        return getattr(obj.forecast_run.model_version, "name", "-")

    @admin.display(description="Metrics preview")
    def metrics_preview(self, obj):
        return self._pretty_json(obj.metrics)


@admin.register(DatasetSnapshot)
class DatasetSnapshotAdmin(MonitoringAdminMixin):
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_display = (
        "id",
        "input_len_hours",
        "forecast_horizon_hours",
        "master_row_count",
        "sample_count",
        "feature_count",
        "target_count",
        "payload_size_kb",
        "created_at",
    )
    list_filter = ("input_len_hours", "forecast_horizon_hours")
    search_fields = ("id",)
    readonly_fields = ("id", "created_at", "updated_at", "payload_size_kb", "metadata_preview")

    @admin.display(description="Features")
    def feature_count(self, obj):
        return len(obj.feature_columns)

    @admin.display(description="Targets")
    def target_count(self, obj):
        return len(obj.target_columns)

    @admin.display(description="Payload, KB")
    def payload_size_kb(self, obj):
        return round(len(obj.payload_npz or b"") / 1024, 2)

    @admin.display(description="Metadata preview")
    def metadata_preview(self, obj):
        return self._pretty_json(obj.metadata)


@admin.register(ModelVersion)
class ModelVersionAdmin(MonitoringAdminMixin):
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_display = (
        "id",
        "name",
        "status",
        "is_active",
        "dataset",
        "input_len_hours",
        "forecast_horizon_hours",
        "overall_rmse",
        "created_at",
    )
    list_filter = ("status", "is_active", "forecast_horizon_hours", "input_len_hours")
    search_fields = ("id", "name", "dataset__id", "error_message")
    autocomplete_fields = ("dataset", "requested_by")
    readonly_fields = ("id", "created_at", "updated_at", "metrics_preview", "history_preview")
    actions = [make_model_active]

    @admin.display(description="Overall RMSE")
    def overall_rmse(self, obj):
        return obj.metrics.get("summary", {}).get("overall_rmse", "-")

    @admin.display(description="Metrics preview")
    def metrics_preview(self, obj):
        return self._pretty_json(obj.metrics)

    @admin.display(description="History preview")
    def history_preview(self, obj):
        return self._pretty_json(obj.history)


@admin.register(ExperimentSeries)
class ExperimentSeriesAdmin(MonitoringAdminMixin):
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_display = ("id", "name", "status", "run_count", "created_at")
    list_filter = ("status",)
    search_fields = ("id", "name", "description")
    readonly_fields = ("id", "created_at", "updated_at", "configuration_preview", "summary_preview")

    @admin.display(description="Runs")
    def run_count(self, obj):
        return obj.runs.count()

    @admin.display(description="Configuration preview")
    def configuration_preview(self, obj):
        return self._pretty_json(obj.configuration)

    @admin.display(description="Summary preview")
    def summary_preview(self, obj):
        return self._pretty_json(obj.summary)


@admin.register(ExperimentRun)
class ExperimentRunAdmin(MonitoringAdminMixin):
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_display = (
        "id",
        "name",
        "status",
        "series",
        "dataset_snapshot",
        "model_version",
        "forecast_run",
        "created_at",
    )
    list_filter = ("status", "input_len_hours", "forecast_horizon_hours")
    search_fields = ("id", "name", "series__name", "error_message")
    autocomplete_fields = (
        "requested_by",
        "series",
        "dataset_snapshot",
        "model_version",
        "forecast_run",
        "forecast_evaluation",
    )
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "training_config_preview",
        "backtest_config_preview",
        "summary_preview",
    )

    @admin.display(description="Training config preview")
    def training_config_preview(self, obj):
        return self._pretty_json(obj.training_config)

    @admin.display(description="Backtest config preview")
    def backtest_config_preview(self, obj):
        return self._pretty_json(obj.backtest_config)

    @admin.display(description="Summary preview")
    def summary_preview(self, obj):
        return self._pretty_json(obj.summary)


@admin.register(ScheduledMonitoringTask)
class ScheduledMonitoringTaskAdmin(MonitoringAdminMixin):
    date_hierarchy = "scheduled_for"
    ordering = ("-scheduled_for", "-created_at")
    list_display = ("id", "operation", "status", "scheduled_for", "requested_by", "celery_task_id", "created_at")
    list_filter = ("operation", "status")
    search_fields = ("id", "celery_task_id", "requested_by__email")
    autocomplete_fields = ("requested_by",)
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
        "payload_preview",
        "result_preview",
    )
    actions = [cancel_scheduled_tasks]

    @admin.display(description="Payload preview")
    def payload_preview(self, obj):
        return self._pretty_json(obj.payload)

    @admin.display(description="Result preview")
    def result_preview(self, obj):
        return self._pretty_json(obj.result)
