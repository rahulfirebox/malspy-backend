

from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0012_passwordresettoken_purpose_and_more'),
        ('billing', '0012_plan_name_unique'),
    ]

    operations = [
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('cashfree_order_id', models.CharField(db_index=True, max_length=255, unique=True)),
                ('cashfree_payment_id', models.CharField(blank=True, default='', max_length=255)),
                ('cashfree_session_id', models.CharField(blank=True, default='', max_length=255)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('currency', models.CharField(default='INR', max_length=3)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('completed', 'Completed'), ('failed', 'Failed'), ('refunded', 'Refunded')], db_index=True, default='pending', max_length=20)),
                ('total_refunded', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12)),
                ('plan_id_snapshot', models.CharField(blank=True, default='', max_length=255)),
                ('idempotency_key', models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
            ],
            options={
                'db_table': 'payments',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PlanPrice',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('country_code', models.CharField(db_index=True, max_length=3)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('currency', models.CharField(default='USD', max_length=3)),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'db_table': 'plan_prices',
                'ordering': ['amount'],
            },
        ),
        migrations.AddField(
            model_name='processedwebhookevent',
            name='event_type',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='processedwebhookevent',
            name='payload',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='processedwebhookevent',
            name='provider',
            field=models.CharField(default='stripe', max_length=50),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='invoice_pdf_url',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AlterField(
            model_name='invoice',
            name='subscription',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='invoices', to='billing.subscription'),
        ),
        migrations.AlterField(
            model_name='plan',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='plan',
            name='is_active',
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.AlterField(
            model_name='processedwebhookevent',
            name='event_id',
            field=models.CharField(db_index=True, max_length=255),
        ),
        migrations.AlterField(
            model_name='subscription',
            name='stripe_subscription_id',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddConstraint(
            model_name='invoice',
            constraint=models.CheckConstraint(check=models.Q(('status__in', ['paid', 'unpaid', 'void'])), name='invoice_status_valid'),
        ),
        migrations.AddConstraint(
            model_name='ledgerentry',
            constraint=models.CheckConstraint(check=models.Q(('entry_type__in', ['payment', 'refund', 'credit', 'debit', 'subscription_activation', 'subscription_cancellation', 'checkout_completed'])), name='ledger_entry_type_valid'),
        ),
        migrations.AddConstraint(
            model_name='processedwebhookevent',
            constraint=models.UniqueConstraint(fields=('provider', 'event_id'), name='unique_webhook_event_per_provider'),
        ),
        migrations.AddConstraint(
            model_name='subscription',
            constraint=models.CheckConstraint(check=models.Q(('status__in', ['active', 'cancelled', 'past_due', 'trialing', 'unpaid'])), name='subscription_status_valid'),
        ),
        migrations.AddField(
            model_name='planprice',
            name='plan',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='prices', to='billing.plan'),
        ),
        migrations.AddField(
            model_name='payment',
            name='organization',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payments', to='accounts.organization'),
        ),
        migrations.AddField(
            model_name='payment',
            name='subscription',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='payments', to='billing.subscription'),
        ),
        migrations.AddConstraint(
            model_name='planprice',
            constraint=models.UniqueConstraint(fields=('plan', 'country_code'), name='unique_plan_price_per_country'),
        ),
        migrations.AddConstraint(
            model_name='payment',
            constraint=models.CheckConstraint(check=models.Q(('status__in', ['pending', 'completed', 'failed', 'refunded'])), name='payment_valid_status'),
        ),
        migrations.AddConstraint(
            model_name='payment',
            constraint=models.CheckConstraint(check=models.Q(('total_refunded__lte', models.F('amount'))), name='payment_refund_cap'),
        ),
    ]
