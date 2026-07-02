

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0011_alter_serveragent_agent_version_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="serveragent",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
        migrations.AlterField(
            model_name="serverscanresult",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
    ]
