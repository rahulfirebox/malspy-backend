from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api_keys", "0003_apikey_key_prefix"),
    ]

    operations = [
        migrations.AlterField(
            model_name="apikey",
            name="key_hash",
            field=models.CharField(db_index=True, max_length=64, unique=True),
        ),
    ]
