from django.conf import settings
from django.db import models

from apps.common.models import UUIDPrimaryKeyModel

from .querysets import ObservationQuerySet


class Observation(UUIDPrimaryKeyModel):
    fingerprint = models.CharField(max_length=64, unique=True, db_index=True)
    source = models.CharField(max_length=64, db_index=True)
    source_kind = models.CharField(max_length=64, blank=True)
    station_id = models.CharField(max_length=128, blank=True)
    station_name = models.CharField(max_length=255, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    observed_at_utc = models.DateTimeField(db_index=True)
    time_bucket_utc = models.DateTimeField(null=True, blank=True, db_index=True)
    time_window_utc = models.DateTimeField(null=True, blank=True, db_index=True)
    metric = models.CharField(max_length=64, db_index=True)
    value = models.FloatField(null=True, blank=True)
    unit = models.CharField(max_length=32, blank=True)
    extra = models.JSONField(default=dict, blank=True)

    objects = ObservationQuerySet.as_manager()

    class Meta:
        ordering = ["-observed_at_utc", "source", "metric"]
        indexes = [
            models.Index(fields=["metric", "observed_at_utc"]),
            models.Index(fields=["source", "observed_at_utc"]),
        ]

    def __str__(self) -> str:
        return f"{self.source}:{self.metric}@{self.observed_at_utc.isoformat()}"


class DatasetSnapshot(UUIDPrimaryKeyModel):
    input_len_hours = models.PositiveSmallIntegerField(default=72)
    forecast_horizon_hours = models.PositiveSmallIntegerField(default=24)
    master_row_count = models.PositiveIntegerField(default=0)
    sample_count = models.PositiveIntegerField(default=0)
    feature_columns = models.JSONField(default=list)
    target_columns = models.JSONField(default=list)
    metadata = models.JSONField(default=dict, blank=True)
    payload_npz = models.BinaryField()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"dataset:{self.created_at.isoformat()}"


class ModelVersion(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        TRAINING = "training", "Training"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    dataset = models.ForeignKey(
        DatasetSnapshot,
        on_delete=models.SET_NULL,
        related_name="models",
        null=True,
        blank=True,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="trained_models",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=128, default="default")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.TRAINING, db_index=True)
    input_len_hours = models.PositiveSmallIntegerField(default=72)
    forecast_horizon_hours = models.PositiveSmallIntegerField(default=24)
    feature_names = models.JSONField(default=list)
    target_names = models.JSONField(default=list)
    training_config = models.JSONField(default=dict, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    history = models.JSONField(default=dict, blank=True)
    checkpoint_blob = models.BinaryField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    is_active = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"model:{self.name}:{self.status}"


class ForecastRun(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        STARTED = "started", "Started"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="forecast_runs",
        null=True,
        blank=True,
    )
    model_version = models.ForeignKey(
        ModelVersion,
        on_delete=models.SET_NULL,
        related_name="forecast_runs",
        null=True,
        blank=True,
    )
    generated_from_timestamp_utc = models.DateTimeField(null=True, blank=True, db_index=True)
    forecast_horizon_hours = models.PositiveSmallIntegerField(default=24)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.STARTED, db_index=True)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.status}:{self.created_at.isoformat()}"


class ForecastRecord(UUIDPrimaryKeyModel):
    forecast_run = models.ForeignKey(ForecastRun, on_delete=models.CASCADE, related_name="records")
    timestamp_utc = models.DateTimeField(db_index=True)
    values = models.JSONField(default=dict)

    class Meta:
        ordering = ["timestamp_utc"]
        indexes = [
            models.Index(fields=["forecast_run", "timestamp_utc"]),
        ]

    def __str__(self) -> str:
        return self.timestamp_utc.isoformat()


class ForecastEvaluation(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    forecast_run = models.OneToOneField(ForecastRun, on_delete=models.CASCADE, related_name="evaluation")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING, db_index=True)
    expected_record_count = models.PositiveIntegerField(default=0)
    matched_record_count = models.PositiveIntegerField(default=0)
    coverage_ratio = models.FloatField(default=0.0)
    evaluated_at_utc = models.DateTimeField(null=True, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"evaluation:{self.status}:{self.forecast_run_id}"


class ExperimentSeries(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="experiment_series",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=128, unique=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    configuration = models.JSONField(default=dict, blank=True)
    summary = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"series:{self.name}:{self.status}"


class ExperimentRun(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="experiment_runs",
        null=True,
        blank=True,
    )
    series = models.ForeignKey(
        ExperimentSeries,
        on_delete=models.SET_NULL,
        related_name="runs",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=128, default="experiment")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING, db_index=True)
    dataset_snapshot = models.ForeignKey(
        DatasetSnapshot,
        on_delete=models.SET_NULL,
        related_name="experiment_runs",
        null=True,
        blank=True,
    )
    model_version = models.ForeignKey(
        ModelVersion,
        on_delete=models.SET_NULL,
        related_name="experiment_runs",
        null=True,
        blank=True,
    )
    forecast_run = models.ForeignKey(
        ForecastRun,
        on_delete=models.SET_NULL,
        related_name="experiment_runs",
        null=True,
        blank=True,
    )
    forecast_evaluation = models.ForeignKey(
        ForecastEvaluation,
        on_delete=models.SET_NULL,
        related_name="experiment_runs",
        null=True,
        blank=True,
    )
    input_len_hours = models.PositiveSmallIntegerField(default=72)
    forecast_horizon_hours = models.PositiveSmallIntegerField(default=24)
    feature_columns = models.JSONField(default=list)
    target_columns = models.JSONField(default=list)
    training_config = models.JSONField(default=dict, blank=True)
    backtest_config = models.JSONField(default=dict, blank=True)
    config_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    summary = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "config_fingerprint"]),
        ]

    def __str__(self) -> str:
        return f"experiment:{self.name}:{self.status}"
