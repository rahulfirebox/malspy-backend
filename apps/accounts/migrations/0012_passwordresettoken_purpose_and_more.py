

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_organization_name_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='passwordresettoken',
            name='purpose',
            field=models.CharField(choices=[('password_reset', 'Password Reset'), ('email_verify', 'Email Verify')], db_index=True, default='password_reset', max_length=30),
        ),
        migrations.AlterField(
            model_name='organization',
            name='stripe_customer_id',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AlterField(
            model_name='organization',
            name='stripe_subscription_id',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AlterField(
            model_name='passwordresettoken',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AddConstraint(
            model_name='passwordresettoken',
            constraint=models.CheckConstraint(check=models.Q(('purpose__in', ['password_reset', 'email_verify'])), name='passwordresettoken_purpose_valid'),
        ),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.CheckConstraint(check=models.Q(('role__in', ['owner', 'admin', 'member', 'viewer', 'superadmin'])), name='user_role_valid'),
        ),
    ]
