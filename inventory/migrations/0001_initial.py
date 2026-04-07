import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('catalog', '0006_productoption'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Warehouse',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('code', models.CharField(max_length=20, unique=True)),
                ('address_line1', models.CharField(blank=True, max_length=200)),
                ('address_line2', models.CharField(blank=True, max_length=200)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('country', models.CharField(blank=True, max_length=100)),
                ('notes', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['name'], 'verbose_name': 'warehouse', 'verbose_name_plural': 'warehouses'},
        ),
        migrations.CreateModel(
            name='StockLocation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('code', models.CharField(max_length=50)),
                ('notes', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('warehouse', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='locations', to='inventory.warehouse')),
            ],
            options={'ordering': ['warehouse', 'code'], 'verbose_name': 'stock location', 'verbose_name_plural': 'stock locations'},
        ),
        migrations.AddConstraint(
            model_name='stocklocation',
            constraint=models.UniqueConstraint(fields=('warehouse', 'code'), name='inventory_stocklocation_unique_warehouse_code'),
        ),
        migrations.CreateModel(
            name='StockEntry',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('quantity_on_hand', models.DecimalField(decimal_places=3, default=0, max_digits=12)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stock_entries', to='catalog.product')),
                ('location', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stock_entries', to='inventory.stocklocation')),
            ],
            options={'verbose_name': 'stock entry', 'verbose_name_plural': 'stock entries'},
        ),
        migrations.AddConstraint(
            model_name='stockentry',
            constraint=models.UniqueConstraint(fields=('product', 'location'), name='inventory_stockentry_unique_product_location'),
        ),
        migrations.CreateModel(
            name='StockMovement',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('delta', models.DecimalField(decimal_places=3, max_digits=12)),
                ('movement_type', models.CharField(
                    choices=[
                        ('receipt', 'Purchase receipt'),
                        ('shipment', 'Shipment'),
                        ('adjustment', 'Manual adjustment'),
                        ('transfer_in', 'Transfer in'),
                        ('transfer_out', 'Transfer out'),
                        ('return', 'Customer return'),
                    ],
                    max_length=20,
                )),
                ('reference', models.CharField(blank=True, max_length=200)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to='catalog.product')),
                ('location', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to='inventory.stocklocation')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at'], 'verbose_name': 'stock movement', 'verbose_name_plural': 'stock movements'},
        ),
    ]
