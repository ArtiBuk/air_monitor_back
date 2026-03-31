import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring", "0003_modelversion_training_config"),
    ]

    operations = [
        migrations.CreateModel(
            name="ForecastEvaluation",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("completed", "Completed"), ("failed", "Failed")],
                        db_index=True,
                        default="pending",
                        max_length=32,
                    ),
                ),
                ("expected_record_count", models.PositiveIntegerField(default=0)),
                ("matched_record_count", models.PositiveIntegerField(default=0)),
                ("coverage_ratio", models.FloatField(default=0.0)),
                ("evaluated_at_utc", models.DateTimeField(blank=True, null=True)),
                ("metrics", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
                (
                    "forecast_run",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        related_name="evaluation",
                        to="monitoring.forecastrun",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
