from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api_keys", "0002_remove_apikey_key_prefix"),
    ]

    operations = [
        migrations.AddField(
            model_name="apikey",
            name="key_prefix",
            field=models.CharField(blank=True, max_length=10),
        ),
    ]
