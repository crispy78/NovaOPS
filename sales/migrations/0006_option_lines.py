import uuid
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0006_productoption'),
        ('sales', '0005_shipping_orders'),
    ]

    operations = [
        # ── CartLine: drop old unique constraint, add new fields ──────────────
        migrations.RemoveConstraint(
            model_name='cartline',
            name='sales_cartline_unique_product',
        ),
        migrations.AlterField(
            model_name='cartline',
            name='product',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='cart_lines', to='catalog.product'),
        ),
        migrations.AddField(
            model_name='cartline',
            name='parent_line',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='option_lines', to='sales.cartline', verbose_name='parent line'),
        ),
        migrations.AddField(
            model_name='cartline',
            name='product_option',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cart_lines', to='catalog.productoption'),
        ),
        migrations.AddField(
            model_name='cartline',
            name='option_name',
            field=models.CharField(blank=True, default='', max_length=200),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='cartline',
            name='option_sku',
            field=models.CharField(blank=True, default='', max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='cartline',
            name='option_price_delta',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12),
        ),
        migrations.AddConstraint(
            model_name='cartline',
            constraint=models.UniqueConstraint(
                condition=models.Q(parent_line__isnull=True),
                fields=['cart', 'product'],
                name='sales_cartline_unique_product_main',
            ),
        ),

        # ── QuoteLine ────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='quoteline',
            name='parent_line',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='option_lines', to='sales.quoteline', verbose_name='parent line'),
        ),
        migrations.AddField(
            model_name='quoteline',
            name='product_option',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='quote_lines', to='catalog.productoption'),
        ),

        # ── OrderLine ────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='orderline',
            name='parent_line',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='option_lines', to='sales.orderline', verbose_name='parent line'),
        ),
        migrations.AddField(
            model_name='orderline',
            name='product_option',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='order_lines', to='catalog.productoption'),
        ),

        # ── InvoiceLine ──────────────────────────────────────────────────────
        migrations.AddField(
            model_name='invoiceline',
            name='parent_line',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='option_lines', to='sales.invoiceline', verbose_name='parent line'),
        ),
        migrations.AddField(
            model_name='invoiceline',
            name='product_option',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='invoice_lines', to='catalog.productoption'),
        ),

        # ── FulfillmentOrderLine ─────────────────────────────────────────────
        migrations.AddField(
            model_name='fulfillmentorderline',
            name='parent_line',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='option_lines', to='sales.fulfillmentorderline', verbose_name='parent line'),
        ),
    ]
