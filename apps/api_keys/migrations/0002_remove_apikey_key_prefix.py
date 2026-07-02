from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api_keys", "0001_initial"),
    ]


    operations = [
        migrations.RemoveField(
            model_name="apikey",
            name="key_prefix",
        ),
    ]
