import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assets', '0003_asset_organization_transfer'),
        ('catalog', '0006_productoption'),
        ('sales', '0006_option_lines'),
    ]

    operations = [
        migrations.AddField(
            model_name='asset',
            name='parent_asset',
            field=models.ForeignKey(blank=True, help_text='Set when this asset was installed as an option/add-on of another asset.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sub_assets', to='assets.asset', verbose_name='parent asset'),
        ),
        migrations.CreateModel(
            name='AssetComponent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200, verbose_name='component name')),
                ('sku', models.CharField(blank=True, max_length=100, verbose_name='SKU')),
                ('price', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='price at installation')),
                ('installed_at', models.DateField(blank=True, default=django.utils.timezone.localdate, null=True, verbose_name='installed on')),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('asset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='components', to='assets.asset', verbose_name='asset')),
                ('order_line', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='asset_components', to='sales.orderline', verbose_name='order line')),
                ('product_option', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='asset_components', to='catalog.productoption', verbose_name='product option')),
            ],
            options={
                'verbose_name': 'asset component',
                'verbose_name_plural': 'asset components',
                'ordering': ['asset', 'installed_at', 'name'],
            },
        ),
    ]
