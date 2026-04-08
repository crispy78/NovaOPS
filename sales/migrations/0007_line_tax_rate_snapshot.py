from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0006_option_lines'),
    ]

    operations = [
        migrations.AddField(
            model_name='quoteline',
            name='tax_rate_pct',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='tax rate (%)'
            ),
        ),
        migrations.AddField(
            model_name='orderline',
            name='tax_rate_pct',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='tax rate (%)'
            ),
        ),
        migrations.AddField(
            model_name='invoiceline',
            name='tax_rate_pct',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='tax rate (%)'
            ),
        ),
    ]
