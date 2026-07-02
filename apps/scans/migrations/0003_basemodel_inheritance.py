import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scans", "0002_malwaresignature_updated_at"),
    ]

    operations = [

        migrations.AddField(
            model_name="malwaresignature",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
