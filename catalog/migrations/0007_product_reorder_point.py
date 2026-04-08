from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0006_productoption'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='reorder_point',
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name='reorder point',
                help_text='Alert when total stock on hand falls at or below this quantity.',
            ),
        ),
    ]
