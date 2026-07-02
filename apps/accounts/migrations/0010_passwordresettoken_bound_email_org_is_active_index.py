

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_delete_emailverificationtoken"),
    ]

    operations = [
        migrations.AddField(
            model_name="passwordresettoken",
            name="bound_email",
            field=models.EmailField(default="", max_length=254),
        ),
        migrations.AlterField(
            model_name="organization",
            name="is_active",
            field=models.BooleanField(db_index=True, default=True),
        ),
    ]
