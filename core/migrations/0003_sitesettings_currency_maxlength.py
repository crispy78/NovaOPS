from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_site_settings'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sitesettings',
            name='currency',
            field=models.CharField(
                default='GBP',
                help_text='Currency code or symbol, e.g. GBP, €, $, ₿.',
                max_length=10,
                verbose_name='default currency',
            ),
        ),
    ]
