

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_org_scan_quota_check_constraint"),
    ]


    operations = [
        migrations.RemoveField(
            model_name="activationtoken",
            name="user",
        ),
        migrations.RemoveField(
            model_name="organization",
            name="deleted_at",
        ),
        migrations.RemoveField(
            model_name="organization",
            name="is_active",
        ),
        migrations.RemoveField(
            model_name="passwordresettoken",
            name="deleted_at",
        ),
        migrations.RemoveField(
            model_name="passwordresettoken",
            name="updated_at",
        ),
        migrations.RemoveField(
            model_name="user",
            name="deleted_at",
        ),

        migrations.AddIndex(
            model_name="user",
            index=models.Index(
                fields=["organization", "role"], name="users_organiz_6045b8_idx"
            ),
        ),
        migrations.DeleteModel(
            name="ActivationToken",
        ),
    ]
