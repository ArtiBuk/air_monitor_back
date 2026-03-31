from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="modelversion",
            name="training_config",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
