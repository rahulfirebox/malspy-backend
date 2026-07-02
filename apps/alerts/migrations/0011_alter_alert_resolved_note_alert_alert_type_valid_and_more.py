

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('alerts', '0010_alert_unique_active_alert_per_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='alert',
            name='resolved_note',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddConstraint(
            model_name='alert',
            constraint=models.CheckConstraint(check=models.Q(('type__in', ['malware_detected', 'blacklisted', 'tls_expiring', 'missing_headers'])), name='alert_type_valid'),
        ),
        migrations.AddConstraint(
            model_name='alert',
            constraint=models.CheckConstraint(check=models.Q(('severity__in', ['critical', 'high', 'medium', 'low'])), name='alert_severity_valid'),
        ),
    ]
