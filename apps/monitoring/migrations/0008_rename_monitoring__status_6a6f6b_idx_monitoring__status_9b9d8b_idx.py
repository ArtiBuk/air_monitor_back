from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring", "0007_experimentrun_config_fingerprint"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="experimentrun",
            new_name="monitoring__status_9b9d8b_idx",
            old_name="monitoring__status_6a6f6b_idx",
        ),
    ]
