from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0009_serveragent_deleted_at_serverscanresult_deleted_at_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="serveragent",
            name="unique_active_agent_name_per_org",
        ),
        migrations.AddConstraint(
            model_name="serveragent",
            constraint=models.UniqueConstraint(
                condition=models.Q(deleted_at__isnull=True),
                fields=["organization", "name"],
                name="unique_active_agent_name_per_org",
            ),
        ),
    ]
