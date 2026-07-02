from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0011_plan_expires_at_protect_fks"),
    ]

    operations = [
        migrations.AlterField(
            model_name="plan",
            name="name",
            field=models.CharField(max_length=50, unique=True),
        ),
    ]
