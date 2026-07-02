import hashlib

from django.db import migrations, models


def fill_null_token_hashes(apps, schema_editor):
    ServerAgent = apps.get_model("agents", "ServerAgent")
    for agent in ServerAgent.objects.filter(token_hash__isnull=True):
        agent.token_hash = hashlib.sha256(str(agent.id).encode()).hexdigest()
        agent.save(update_fields=["token_hash"])


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0007_serverresult_status_timestamps_path"),
    ]

    operations = [
        migrations.RunPython(fill_null_token_hashes, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name="serveragent",
            name="token_hash",
            field=models.CharField(db_index=True, max_length=64, unique=True),
        ),
    ]
