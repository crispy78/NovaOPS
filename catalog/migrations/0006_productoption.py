import uuid
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0005_alter_productimage_options_productimage_file_size_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductOption',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(blank=True, max_length=200, verbose_name='option name')),
                ('sku', models.CharField(blank=True, max_length=100, verbose_name='SKU')),
                ('price_delta', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Price added to the parent when selected. Ignored when a linked product is set.', max_digits=12, verbose_name='additional price')),
                ('is_required', models.BooleanField(default=False, help_text='Always included; shown pre-selected and cannot be unchecked.', verbose_name='required')),
                ('is_default', models.BooleanField(default=False, verbose_name='selected by default')),
                ('sort_order', models.PositiveSmallIntegerField(default=0, verbose_name='sort order')),
                ('linked_product', models.ForeignKey(blank=True, help_text='Set this when the option is an existing standalone product.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='as_option_in', to='catalog.product', verbose_name='linked product')),
                ('parent_product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='options', to='catalog.product', verbose_name='parent product')),
            ],
            options={
                'verbose_name': 'product option',
                'verbose_name_plural': 'product options',
                'ordering': ['parent_product', 'sort_order', 'name'],
            },
        ),
    ]
