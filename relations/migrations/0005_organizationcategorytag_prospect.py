# Generated manually - ensure Prospect tag exists for quoting (demo / upgrades).

from django.db import migrations


def add_prospect_tag(apps, schema_editor):
    OrganizationCategoryTag = apps.get_model('relations', 'OrganizationCategoryTag')
    OrganizationCategoryTag.objects.get_or_create(
        code='prospect',
        defaults={'label': 'Prospect'},
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('relations', '0004_quote_relation_and_references'),
    ]

    operations = [
        migrations.RunPython(add_prospect_tag, noop_reverse),
    ]
