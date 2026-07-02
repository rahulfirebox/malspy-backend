from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="serveragent",
            name="token_hash",
            field=models.CharField(
                blank=True,
                db_index=True,
                default=None,
                max_length=64,
                null=True,
                unique=True,
            ),
        ),
    ]
