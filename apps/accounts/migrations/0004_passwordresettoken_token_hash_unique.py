from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_basemodel_organisation_is_active_activationtoken"),
    ]

    operations = [
        migrations.AlterField(
            model_name="passwordresettoken",
            name="token_hash",
            field=models.CharField(max_length=64, unique=True),
        ),
    ]
