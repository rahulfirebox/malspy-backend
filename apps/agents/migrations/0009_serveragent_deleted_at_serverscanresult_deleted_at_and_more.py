

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0008_serveragent_token_hash_notnull"),
    ]

    operations = [
        migrations.AddField(
            model_name="serveragent",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="serverscanresult",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="serverscanresult",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
