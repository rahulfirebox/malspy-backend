from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0002_serveragent_token_hash_nullable"),
    ]

    operations = [
        migrations.AlterField(
            model_name="serveragent",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("inactive", "Inactive"),
                    ("error", "Error"),
                    ("revoked", "Revoked"),
                ],
                db_index=True,
                default="inactive",
                max_length=20,
            ),
        ),
    ]
