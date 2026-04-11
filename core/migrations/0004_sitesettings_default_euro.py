from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_sitesettings_currency_maxlength'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sitesettings',
            name='currency',
            field=models.CharField(
                default='€',
                help_text='Currency code or symbol, e.g. GBP, EUR, £, €, ₿.',
                max_length=10,
                verbose_name='default currency',
            ),
        ),
    ]
