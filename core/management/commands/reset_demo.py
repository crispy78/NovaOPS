"""
Management command: reset the demo environment.

Clears all business data, resets demo user accounts to known credentials,
clears all active sessions, and re-seeds fresh demo data.

Usage:
  python manage.py reset_demo
  python manage.py reset_demo --skip-images  # faster, uses placeholder images

Should be run every 30 minutes via cron or a systemd timer.
Only runs when DEMO_MODE=true is set in the environment.
"""
from __future__ import annotations

import sys
from datetime import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

User = get_user_model()

# ---------------------------------------------------------------------------
# Demo account definitions
# ---------------------------------------------------------------------------

_DEMO_ACCOUNTS = [
    {
        'email': 'admin@demo.com',
        'first_name': 'Alex',
        'last_name': 'Admin',
        'password': 'Demo1234!',
        'is_staff': True,
        'is_superuser': True,
        'role': 'admin',
    },
    {
        'email': 'catalog@demo.com',
        'first_name': 'Casey',
        'last_name': 'Catalog',
        'password': 'Demo1234!',
        'is_staff': False,
        'role': 'catalog',
    },
    {
        'email': 'sales@demo.com',
        'first_name': 'Sam',
        'last_name': 'Sales',
        'password': 'Demo1234!',
        'is_staff': False,
        'role': 'sales',
    },
    {
        'email': 'accounts@demo.com',
        'first_name': 'Ava',
        'last_name': 'Accounts',
        'password': 'Demo1234!',
        'is_staff': False,
        'role': 'accounts',
    },
    {
        'email': 'warehouse@demo.com',
        'first_name': 'Will',
        'last_name': 'Warehouse',
        'password': 'Demo1234!',
        'is_staff': False,
        'role': 'warehouse',
    },
    {
        'email': 'finance@demo.com',
        'first_name': 'Fiona',
        'last_name': 'Finance',
        'password': 'Demo1234!',
        'is_staff': False,
        'role': 'finance',
    },
]

# App labels whose permissions are granted to the admin demo account.
_ADMIN_APPS = [
    'catalog', 'sales', 'relations', 'assets', 'contracts',
    'inventory', 'procurement', 'core', 'accounts', 'audit', 'pricing',
]

# Product manager: full catalog + pricing, view-only sales context.
_CATALOG_CODENAMES = [
    'view_product', 'add_product', 'change_product', 'archive_product',
    'view_product_purchase_price', 'edit_product_pricing',
    'view_productcategory', 'add_productcategory', 'change_productcategory',
    'view_taxrate', 'add_taxrate', 'change_taxrate',
    'view_productimage', 'add_productimage', 'change_productimage', 'delete_productimage',
    'view_discountgroup', 'add_discountgroup', 'change_discountgroup',
    'view_pricingrule', 'add_pricingrule', 'change_pricingrule',
    'view_pricingruleassignment', 'add_pricingruleassignment', 'change_pricingruleassignment',
    'view_stockentry', 'view_warehouse',
    'view_purchaseorder',
    'view_quote', 'view_salesorder', 'view_invoice',
]

# Sales manager: quotes, orders, customer relations.
_SALES_CODENAMES = [
    'view_product', 'view_productcategory', 'view_taxrate',
    'view_productimage', 'view_discountgroup',
    'view_organization', 'add_organization', 'change_organization',
    'view_person', 'add_person', 'change_person',
    'view_quote', 'add_quote', 'change_quote',
    'view_salesorder', 'add_salesorder', 'change_salesorder',
    'view_invoice', 'add_invoice',
    'view_fulfillmentorder',
    'view_shippingorder',
    'view_shipment',
    'view_cart', 'add_cart', 'change_cart',
    'view_contract', 'view_contracttemplate', 'view_servicerate',
    'view_stockentry', 'view_warehouse',
]

# Account manager: CRM-focused, full relations + view sales pipeline.
_ACCOUNTS_CODENAMES = [
    'view_organization', 'add_organization', 'change_organization',
    'view_person', 'add_person', 'change_person',
    'view_product', 'view_productcategory',
    'view_quote', 'add_quote', 'change_quote',
    'view_salesorder', 'view_invoice',
    'view_asset',
    'view_contract', 'view_contracttemplate', 'view_servicerate',
    'add_contract', 'change_contract',
    'view_stockentry',
]

# Warehouse / shipping: inventory, fulfillment, shipping, purchase orders.
_WAREHOUSE_CODENAMES = [
    'view_product', 'view_productcategory',
    'view_stockentry', 'add_stockentry', 'change_stockentry',
    'view_warehouse', 'add_warehouse', 'change_warehouse',
    'view_stocklocation', 'add_stocklocation', 'change_stocklocation',
    'view_stockmovement', 'add_stockmovement',
    'view_salesorder', 'view_fulfillmentorder', 'change_fulfillmentorder',
    'view_shippingorder', 'add_shippingorder', 'change_shippingorder',
    'view_shipment', 'add_shipment', 'change_shipment',
    'view_purchaseorder', 'add_purchaseorder', 'change_purchaseorder',
    'view_organization',
]

# Finance: invoices, payments, credit notes, contracts, reports.
_FINANCE_CODENAMES = [
    'view_product', 'view_productcategory', 'view_taxrate',
    'view_organization', 'view_person',
    'view_salesorder', 'view_quote',
    'view_invoice', 'add_invoice', 'change_invoice',
    'view_invoicepayment', 'add_invoicepayment',
    'view_creditnote', 'add_creditnote', 'change_creditnote',
    'view_contract', 'view_contracttemplate', 'view_servicerate',
    'add_contract', 'change_contract',
    'view_stockentry',
    'view_purchaseorder',
]


def _apply_permissions(user: 'User', role: str) -> None:
    if role == 'admin':
        perms = Permission.objects.filter(content_type__app_label__in=_ADMIN_APPS)
        user.user_permissions.set(perms)
    elif role == 'catalog':
        perms = Permission.objects.filter(codename__in=_CATALOG_CODENAMES)
        user.user_permissions.set(perms)
    elif role == 'sales':
        perms = Permission.objects.filter(codename__in=_SALES_CODENAMES)
        user.user_permissions.set(perms)
    elif role == 'accounts':
        perms = Permission.objects.filter(codename__in=_ACCOUNTS_CODENAMES)
        user.user_permissions.set(perms)
    elif role == 'warehouse':
        perms = Permission.objects.filter(codename__in=_WAREHOUSE_CODENAMES)
        user.user_permissions.set(perms)
    elif role == 'finance':
        perms = Permission.objects.filter(codename__in=_FINANCE_CODENAMES)
        user.user_permissions.set(perms)


def _reset_demo_users() -> None:
    for spec in _DEMO_ACCOUNTS:
        user, created = User.objects.get_or_create(
            email=spec['email'],
            defaults={
                'username': spec['email'],
                'first_name': spec['first_name'],
                'last_name': spec['last_name'],
                'is_staff': spec['is_staff'],
                'is_superuser': spec.get('is_superuser', False),
                'is_active': True,
            },
        )
        if not created:
            user.username = spec['email']
            user.first_name = spec['first_name']
            user.last_name = spec['last_name']
            user.is_staff = spec['is_staff']
            user.is_superuser = spec.get('is_superuser', False)
            user.is_active = True
            user.save()
        user.set_password(spec['password'])
        user.save()
        _apply_permissions(user, spec['role'])


def _clear_sessions() -> None:
    try:
        from django.contrib.sessions.models import Session
        Session.objects.all().delete()
    except Exception:
        pass


class Command(BaseCommand):
    help = 'Reset the demo environment: clear data, reset users, re-seed.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('--skip-images', action='store_true',
                            help='Skip image loading; use placeholders.')
        parser.add_argument('--force', action='store_true',
                            help='Run even if DEMO_MODE is not set (use with caution).')

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        if not getattr(settings, 'DEMO_MODE', False) and not options['force']:
            self.stderr.write(self.style.ERROR(
                'DEMO_MODE is not enabled. Set DEMO_MODE=true in your environment '
                'or pass --force to override.'
            ))
            sys.exit(1)

        start = datetime.now()
        self.stdout.write(f'[{start:%H:%M:%S}] Starting demo reset...')

        self.stdout.write('  Resetting demo user accounts...')
        _reset_demo_users()

        self.stdout.write('  Clearing and re-seeding business data...')
        seed_args = ['--clear']
        if options['skip_images']:
            seed_args.append('--skip-images')
        call_command('create_demo_data', *seed_args, verbosity=0)

        self.stdout.write('  Clearing active sessions...')
        _clear_sessions()

        elapsed = (datetime.now() - start).total_seconds()
        self.stdout.write(self.style.SUCCESS(f'  Demo reset complete in {elapsed:.1f}s.'))
