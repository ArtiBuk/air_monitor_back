import django.db.models.deletion
import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring", "0004_forecastevaluation"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ExperimentRun",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(default="experiment", max_length=128)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("completed", "Completed"), ("failed", "Failed")],
                        db_index=True,
                        default="pending",
                        max_length=32,
                    ),
                ),
                ("input_len_hours", models.PositiveSmallIntegerField(default=72)),
                ("forecast_horizon_hours", models.PositiveSmallIntegerField(default=24)),
                ("feature_columns", models.JSONField(default=list)),
                ("target_columns", models.JSONField(default=list)),
                ("training_config", models.JSONField(blank=True, default=dict)),
                ("backtest_config", models.JSONField(blank=True, default=dict)),
                ("summary", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
                (
                    "dataset_snapshot",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="experiment_runs",
                        to="monitoring.datasetsnapshot",
                    ),
                ),
                (
                    "forecast_evaluation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="experiment_runs",
                        to="monitoring.forecastevaluation",
                    ),
                ),
                (
                    "forecast_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="experiment_runs",
                        to="monitoring.forecastrun",
                    ),
                ),
                (
                    "model_version",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="experiment_runs",
                        to="monitoring.modelversion",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="experiment_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
