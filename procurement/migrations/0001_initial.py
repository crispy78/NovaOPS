import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('catalog', '0006_productoption'),
        ('relations', '0007_communication_employer_organization'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PurchaseOrder',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('ref', models.CharField(editable=False, max_length=30, unique=True)),
                ('status', models.CharField(
                    choices=[
                        ('draft', 'Draft'),
                        ('sent', 'Sent'),
                        ('partial', 'Partially received'),
                        ('received', 'Fully received'),
                        ('cancelled', 'Cancelled'),
                    ],
                    default='draft',
                    max_length=20,
                )),
                ('expected_delivery_date', models.DateField(blank=True, null=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('supplier', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='purchase_orders', to='relations.organization')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at'], 'verbose_name': 'purchase order', 'verbose_name_plural': 'purchase orders'},
        ),
        migrations.CreateModel(
            name='PurchaseOrderLine',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('description', models.CharField(blank=True, max_length=500)),
                ('qty_ordered', models.DecimalField(decimal_places=3, max_digits=12)),
                ('unit_cost', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('qty_received', models.DecimalField(decimal_places=3, default=0, max_digits=12)),
                ('purchase_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='procurement.purchaseorder')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='purchase_order_lines', to='catalog.product')),
            ],
            options={'verbose_name': 'purchase order line', 'verbose_name_plural': 'purchase order lines'},
        ),
    ]
