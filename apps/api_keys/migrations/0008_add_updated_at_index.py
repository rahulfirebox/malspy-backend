

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api_keys", "0007_alter_apikey_key_prefix"),
    ]

    operations = [
        migrations.AlterField(
            model_name="apikey",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
    ]
