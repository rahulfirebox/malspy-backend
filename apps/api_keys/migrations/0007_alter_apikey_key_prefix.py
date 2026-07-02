

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api_keys", "0006_apikey_updated_by_unique_name"),
    ]

    operations = [
        migrations.AlterField(
            model_name="apikey",
            name="key_prefix",
            field=models.CharField(max_length=20),
        ),
    ]
