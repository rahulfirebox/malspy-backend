

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_passwordresettoken_purpose_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="organization",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
        migrations.AlterField(
            model_name="user",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
    ]
