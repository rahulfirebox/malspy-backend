from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0006_serveragent_revoked"),
    ]

    operations = [
        migrations.AddField(
            model_name="serverscanresult",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="completed",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="serverscanresult",
            name="scan_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="serverscanresult",
            name="scan_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="serverscanresult",
            name="completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="serverscanresult",
            name="server_path",
            field=models.CharField(blank=True, max_length=500, null=True),
        ),
    ]
