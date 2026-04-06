from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='ReferenceSequence',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=32, unique=True)),
                ('last_n', models.PositiveIntegerField(default=0)),
            ],
            options={
                'verbose_name': 'reference sequence',
                'verbose_name_plural': 'reference sequences',
            },
        ),
    ]
