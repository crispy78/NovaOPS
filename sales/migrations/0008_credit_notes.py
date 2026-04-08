import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0007_line_tax_rate_snapshot'),
        ('relations', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CreditNote',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('reference', models.CharField(db_index=True, max_length=32, unique=True)),
                ('currency', models.CharField(default='EUR', max_length=3)),
                ('reason', models.CharField(blank=True, help_text='Short reason for issuing this credit note.', max_length=255, verbose_name='reason')),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='credit_notes_created', to=settings.AUTH_USER_MODEL)),
                ('invoice', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='credit_notes', to='sales.invoice', verbose_name='invoice')),
                ('relation_organization', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='credit_notes', to='relations.organization', verbose_name='organization')),
            ],
            options={
                'verbose_name': 'credit note',
                'verbose_name_plural': 'credit notes',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CreditNoteLine',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('product_name', models.CharField(max_length=255)),
                ('sku', models.CharField(blank=True, max_length=64)),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=12)),
                ('tax_rate_pct', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='tax rate (%)')),
                ('currency', models.CharField(default='EUR', max_length=3)),
                ('line_total', models.DecimalField(decimal_places=2, max_digits=12)),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
                ('credit_note', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='sales.creditnote')),
                ('invoice_line', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='credit_note_lines', to='sales.invoiceline', verbose_name='invoice line')),
            ],
            options={
                'ordering': ['credit_note', 'sort_order', 'id'],
            },
        ),
    ]
