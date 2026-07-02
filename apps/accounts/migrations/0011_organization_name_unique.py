from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_passwordresettoken_bound_email_org_is_active_index"),
    ]

    operations = [
        migrations.AlterField(
            model_name="organization",
            name="name",
            field=models.CharField(max_length=200, unique=True),
        ),
    ]
