from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_reference_sequence'),
    ]

    operations = [
        migrations.CreateModel(
            name='SiteSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('currency', models.CharField(
                    choices=[
                        ('GBP', 'GBP - British Pound'),
                        ('EUR', 'EUR - Euro'),
                        ('USD', 'USD - US Dollar'),
                        ('CHF', 'CHF - Swiss Franc'),
                        ('SEK', 'SEK - Swedish Krona'),
                        ('NOK', 'NOK - Norwegian Krone'),
                        ('DKK', 'DKK - Danish Krone'),
                        ('PLN', 'PLN - Polish Zloty'),
                        ('AUD', 'AUD - Australian Dollar'),
                        ('CAD', 'CAD - Canadian Dollar'),
                    ],
                    default='GBP',
                    help_text='ISO 4217 code used across all products and documents.',
                    max_length=3,
                    verbose_name='default currency',
                )),
            ],
            options={
                'verbose_name': 'site settings',
            },
        ),
    ]
