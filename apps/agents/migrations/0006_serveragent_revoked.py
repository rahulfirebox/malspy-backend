from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0005_serveragent_updated_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="serveragent",
            name="revoked",
            field=models.BooleanField(default=False, db_index=True),
        ),
    ]
