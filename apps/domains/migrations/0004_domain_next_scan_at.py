

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("domains", "0003_domain_created_by_updated_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="domain",
            name="next_scan_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
