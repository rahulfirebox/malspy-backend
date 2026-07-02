from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api_keys", "0004_apikey_key_hash_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="apikey",
            name="expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
