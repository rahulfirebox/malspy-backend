

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_remove_organization_created_by_and_more"),
    ]

    operations = [
        migrations.DeleteModel(
            name="EmailVerificationToken",
        ),
    ]
