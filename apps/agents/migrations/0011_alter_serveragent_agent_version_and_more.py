

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0010_serveragent_unique_active_agent_name_condition'),
    ]

    operations = [
        migrations.AlterField(
            model_name='serveragent',
            name='agent_version',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AlterField(
            model_name='serverscanresult',
            name='agent_version',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AlterField(
            model_name='serverscanresult',
            name='server_path',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AddConstraint(
            model_name='serveragent',
            constraint=models.CheckConstraint(check=models.Q(('status__in', ['active', 'inactive', 'error', 'revoked'])), name='agent_status_valid'),
        ),
        migrations.AddConstraint(
            model_name='serveragent',
            constraint=models.CheckConstraint(check=models.Q(('agent_type__in', ['wordpress_plugin', 'php_script', 'python_script'])), name='agent_type_valid'),
        ),
        migrations.AddConstraint(
            model_name='serverscanresult',
            constraint=models.CheckConstraint(check=models.Q(('status__in', ['pending', 'completed', 'failed'])), name='server_scan_result_status_valid'),
        ),
    ]
