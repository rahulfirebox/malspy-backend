

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0011_alter_alert_resolved_note_alert_alert_type_valid_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="alert",
            name="unique_active_alert_per_type",
        ),
        migrations.AlterField(
            model_name="alert",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
        migrations.AddConstraint(
            model_name="alert",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_resolved", False), ("deleted_at__isnull", True)),
                fields=("organization", "domain", "type"),
                name="unique_active_alert_per_type",
            ),
        ),
    ]
