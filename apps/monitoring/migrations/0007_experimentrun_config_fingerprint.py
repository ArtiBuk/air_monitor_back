from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring", "0006_experimentseries_and_run_series"),
    ]

    operations = [
        migrations.AddField(
            model_name="experimentrun",
            name="config_fingerprint",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddIndex(
            model_name="experimentrun",
            index=models.Index(fields=["status", "config_fingerprint"], name="monitoring__status_6a6f6b_idx"),
        ),
    ]
