import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0001_initial'),
        ('catalog', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='contract',
            name='tax_rate',
            field=models.ForeignKey(
                blank=True,
                help_text='VAT rate applied to the computed contract value.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='contracts',
                to='catalog.taxrate',
                verbose_name='VAT rate',
            ),
        ),
    ]
