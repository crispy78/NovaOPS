"""
Management command: load_demo_data

Creates a realistic demo dataset for NovaOPS based on a fictional B2B POS-technology
company selling printers, scanners, POS terminals and displays to Dutch retail/hospitality.

Run: python manage.py load_demo_data
Safe to re-run: skips objects that already exist (idempotent on key fields).
"""
from __future__ import annotations

from decimal import Decimal
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

User = get_user_model()


# ── helpers ──────────────────────────────────────────────────────────────────

def _d(s: str) -> Decimal:
    return Decimal(s)


def _today() -> date:
    return timezone.localdate()


class Command(BaseCommand):
    help = 'Load realistic demo data into the database.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Loading NovaOPS demo data…'))
        with transaction.atomic():
            users   = self._users()
            catalog = self._catalog(users)
            rels    = self._relations()
            inv     = self._inventory(catalog)
            self._procurement(catalog, inv, users)
            self._sales(catalog, rels, users)
            self._assets(catalog, rels, users)
            self._contracts(rels, users)
        self.stdout.write(self.style.SUCCESS('Demo data loaded successfully.'))
        self.stdout.write('')
        self.stdout.write('  Login credentials (password: Demo1234!)')
        self.stdout.write('  -----------------------------------------')
        self.stdout.write('  admin@novaops.demo        (superuser / all permissions)')
        self.stdout.write('  sarah.de.vries@novaops.demo  (sales)')
        self.stdout.write('  mark.bakker@novaops.demo     (procurement / warehouse)')
        self.stdout.write('  lisa.janssen@novaops.demo    (service technician)')

    # ─────────────────────────────────────────────────────────────────────────
    # Users
    # ─────────────────────────────────────────────────────────────────────────

    def _users(self) -> dict:
        self.stdout.write('  Creating users…')
        pw = 'Demo1234!'

        def _make(email, first, last, superuser=False, staff=False):
            username = email.split('@')[0]
            u, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': email, 'first_name': first, 'last_name': last,
                    'is_superuser': superuser, 'is_staff': superuser or staff,
                },
            )
            if created:
                u.set_password(pw)
                u.save()
            return u

        admin  = _make('admin@novaops.demo',            'Alex',  'van den Berg', superuser=True)
        sarah  = _make('sarah.de.vries@novaops.demo',   'Sarah', 'de Vries',     staff=True)
        mark   = _make('mark.bakker@novaops.demo',      'Mark',  'Bakker',       staff=True)
        lisa   = _make('lisa.janssen@novaops.demo',     'Lisa',  'Janssen',      staff=True)
        return {'admin': admin, 'sarah': sarah, 'mark': mark, 'lisa': lisa}

    # ─────────────────────────────────────────────────────────────────────────
    # Catalog
    # ─────────────────────────────────────────────────────────────────────────

    def _catalog(self, users: dict) -> dict:
        self.stdout.write('  Creating catalog…')
        from catalog.models import (
            DiscountGroup, Product, ProductCategory, ProductITSpec,
            ProductOption, ProductPriceTier, ProductScannerSpec,
            ProductPrinterSpec, TaxRate, ProductStatus, AssetType,
        )

        # Tax rates
        vat21, _ = TaxRate.objects.get_or_create(name='21% BTW (standard)',  defaults={'rate': _d('21.00')})
        vat9,  _ = TaxRate.objects.get_or_create(name='9% BTW (reduced)',    defaults={'rate': _d('9.00')})
        vat0,  _ = TaxRate.objects.get_or_create(name='0% BTW (export / EU B2B)', defaults={'rate': _d('0.00')})

        # Discount groups
        dg_std,  _ = DiscountGroup.objects.get_or_create(slug='standard-retail',   defaults={'name': 'Standard retail'})
        dg_pref, _ = DiscountGroup.objects.get_or_create(slug='preferred-partner', defaults={'name': 'Preferred partner'})
        dg_ent,  _ = DiscountGroup.objects.get_or_create(slug='enterprise-chain',  defaults={'name': 'Enterprise / chain'})

        # Categories
        def _cat(name, slug):
            c, _ = ProductCategory.objects.get_or_create(slug=slug, defaults={'name': name})
            return c

        cat_pos  = _cat('POS Terminals',          'pos-terminals')
        cat_rp   = _cat('Receipt Printers',        'receipt-printers')
        cat_lp   = _cat('Label & Ticket Printers', 'label-printers')
        cat_scan = _cat('Barcode Scanners',        'barcode-scanners')
        cat_disp = _cat('Displays & Peripherals',  'displays-peripherals')
        cat_acc  = _cat('Accessories',             'accessories')
        cat_sw   = _cat('Software & Licenses',     'software-licenses')

        # ── Products ─────────────────────────────────────────────────────────
        def _prod(**kw):
            obj, _ = Product.objects.get_or_create(sku=kw['sku'], defaults={**kw, 'status': ProductStatus.ACTIVE})
            return obj

        hp_engage = _prod(
            sku='HP-EOP-10-B',
            name='HP Engage One Pro AiO 10.1"',
            short_description='All-in-one POS terminal with 10.1" full-HD touch display, Intel Celeron J4105, 8GB RAM, 128GB SSD.',
            long_description=(
                'The HP Engage One Pro is a purpose-built all-in-one retail terminal designed for high-traffic '
                'environments. Features a fanless design, integrated MSR, optional fingerprint reader, and a '
                'wide selection of peripheral ports (2× USB-A 3.0, 2× USB-C, 1× RS-232, 1× RJ-12).\n\n'
                'Ships with Windows 10 IoT Enterprise (LTSC). Supports floor-stand, counter, and wall-mount '
                'configurations. IP54-rated for spill resistance.'
            ),
            brand='HP', category=cat_pos,
            purchase_price=_d('695.00'), list_price=_d('1299.00'), currency='EUR',
            tax_rate=vat21, discount_group=dg_ent,
            warranty_months=36, serial_number_required=True, asset_type=AssetType.SOLD,
            lead_time_days=5, weight_net=_d('3.2'), weight_gross=_d('4.1'), weight_unit='kg',
            ean_gtin='0190017430768', mpn='6GW42AA#ABH',
            inventory_tracked=True,
        )

        pax_a920 = _prod(
            sku='PAX-A920P',
            name='PAX A920 Pro Smart POS Terminal',
            short_description='Android 10 smart POS with 5.5" screen, 4G/WiFi/BT, built-in receipt printer.',
            long_description=(
                'The PAX A920 Pro combines a full-featured Android POS with a built-in 58mm thermal printer '
                'and contactless/EMV payment reader. Ideal for table-side ordering, food trucks, and pop-up retail.'
            ),
            brand='PAX', category=cat_pos,
            purchase_price=_d('229.00'), list_price=_d('449.00'), currency='EUR',
            tax_rate=vat21, discount_group=dg_std,
            warranty_months=24, serial_number_required=True, asset_type=AssetType.SOLD,
            lead_time_days=7, weight_net=_d('0.55'), weight_unit='kg',
            mpn='A920Pro',
            inventory_tracked=True,
        )

        ingenico_d5 = _prod(
            sku='ING-D5000-BTH',
            name='Ingenico Desk/5000 Payment Terminal',
            short_description='Countertop payment terminal, Bluetooth/USB, EMV + NFC contactless.',
            brand='Ingenico', category=cat_pos,
            purchase_price=_d('149.00'), list_price=_d('299.00'), currency='EUR',
            tax_rate=vat21, discount_group=dg_std,
            warranty_months=24, serial_number_required=True, asset_type=AssetType.SOLD,
            lead_time_days=3,
            mpn='Desk5000',
            inventory_tracked=True,
        )

        epson_t88 = _prod(
            sku='EP-TM88VII-RE',
            name='Epson TM-T88VII Receipt Printer',
            short_description='High-speed 80mm thermal receipt printer, USB + Ethernet, 500mm/sec.',
            long_description=(
                'The TM-T88VII is Epson\'s flagship desktop receipt printer. 250mm/sec print speed (single '
                'interface), USB and Ethernet, autocutter, and Epson\'s ConnectEasy auto-connection feature. '
                'Compatible with all major POS platforms via OPOS/JavaPOS drivers.'
            ),
            brand='Epson', category=cat_rp,
            purchase_price=_d('189.00'), list_price=_d('399.00'), currency='EUR',
            tax_rate=vat21, discount_group=dg_std,
            warranty_months=24, serial_number_required=False, asset_type=AssetType.SOLD,
            lead_time_days=3, weight_net=_d('1.4'), weight_unit='kg',
            ean_gtin='0010343963580', mpn='C31CH26012',
            inventory_tracked=True,
        )

        star_tsp = _prod(
            sku='STR-TSP143IV-ETH',
            name='Star Micronics TSP143IV Ethernet Receipt Printer',
            short_description='80mm thermal receipt printer, Ethernet, mC-Print3 architecture.',
            brand='Star Micronics', category=cat_rp,
            purchase_price=_d('129.00'), list_price=_d('269.00'), currency='EUR',
            tax_rate=vat21, discount_group=dg_std,
            warranty_months=24, serial_number_required=False, asset_type=AssetType.SOLD,
            lead_time_days=4, weight_net=_d('1.1'), weight_unit='kg',
            mpn='39472090',
            inventory_tracked=True,
        )

        boca_lemp = _prod(
            sku='BOCA-LEMP-203',
            name='BOCA Lemur+ Thermal Ticket/Label Printer',
            short_description='Industrial-grade 80mm thermal ticket printer, 203dpi, USB/Ethernet, fanfold & roll media.',
            long_description=(
                'The BOCA Lemur+ is a heavy-duty thermal printer designed for high-volume ticket and label printing '
                'in venues, transport, and retail. Supports both fanfold and roll media. Optional cutter module '
                'and network interface available as add-ons.'
            ),
            brand='BOCA Systems', category=cat_lp,
            purchase_price=_d('289.00'), list_price=_d('599.00'), currency='EUR',
            tax_rate=vat21, discount_group=dg_std,
            warranty_months=24, serial_number_required=True, asset_type=AssetType.SOLD,
            lead_time_days=10, weight_net=_d('2.8'), weight_unit='kg',
            inventory_tracked=True,
        )

        zebra_zd421 = _prod(
            sku='ZBR-ZD421-DT',
            name='Zebra ZD421 Direct Thermal Label Printer',
            short_description='4" direct thermal desktop label printer, USB/Ethernet/BT, ZPL II.',
            brand='Zebra', category=cat_lp,
            purchase_price=_d('219.00'), list_price=_d('449.00'), currency='EUR',
            tax_rate=vat21, discount_group=dg_std,
            warranty_months=12, serial_number_required=False, asset_type=AssetType.SOLD,
            lead_time_days=5,
            mpn='ZD42042-D0EE00EZ',
            inventory_tracked=True,
        )

        honeywell_voy = _prod(
            sku='HW-1202G-1D',
            name='Honeywell Voyager 1202g Wireless Scanner',
            short_description='Single-line laser barcode scanner, Bluetooth, 2.4GHz base included.',
            brand='Honeywell', category=cat_scan,
            purchase_price=_d('59.00'), list_price=_d('149.00'), currency='EUR',
            tax_rate=vat21, discount_group=dg_std,
            warranty_months=12, serial_number_required=False, asset_type=AssetType.SOLD,
            lead_time_days=2, weight_net=_d('0.16'), weight_unit='kg',
            ean_gtin='0085896785001', mpn='1202G-1USB-5',
            inventory_tracked=True,
        )

        datalogic_qd = _prod(
            sku='DL-QD2430-2D',
            name='Datalogic QuickScan QD2430 2D Scanner',
            short_description='Handheld 2D imager scanner, USB/RS-232, reads all 1D/2D codes incl. QR and Data Matrix.',
            brand='Datalogic', category=cat_scan,
            purchase_price=_d('39.00'), list_price=_d('89.00'), currency='EUR',
            tax_rate=vat21, discount_group=dg_std,
            warranty_months=12, serial_number_required=False,
            lead_time_days=3,
            mpn='QD2430-BK',
            inventory_tracked=True,
        )

        hp_display = _prod(
            sku='HP-E24D-G4',
            name='HP EliteDisplay E24d G4 24" USB-C Monitor',
            short_description='24" FHD IPS display, USB-C 100W PD, HDMI, DP, integrated USB hub.',
            brand='HP', category=cat_disp,
            purchase_price=_d('169.00'), list_price=_d('329.00'), currency='EUR',
            tax_rate=vat21, discount_group=dg_ent,
            warranty_months=36, serial_number_required=False,
            lead_time_days=5, weight_net=_d('4.6'), weight_unit='kg',
            mpn='6PA40AA#ABB',
            inventory_tracked=True,
        )

        cash_drawer = _prod(
            sku='POF-HS3512-BLK',
            name='Posiflex HS-3512 Cash Drawer (Black)',
            short_description='16" cash drawer, 5-bill / 8-coin tray, RJ-12 printer-driven, black.',
            brand='Posiflex', category=cat_acc,
            purchase_price=_d('29.00'), list_price=_d('69.00'), currency='EUR',
            tax_rate=vat21, discount_group=dg_std,
            warranty_months=12, serial_number_required=False,
            lead_time_days=3,
            inventory_tracked=True,
        )

        pos_lite_lic = _prod(
            sku='NVA-POS-LITE-1Y',
            name='NovaOPS POS Lite – Annual License',
            short_description='Cloud-based POS software, up to 3 terminals, standard support, 1-year subscription.',
            brand='NovaOPS', category=cat_sw,
            purchase_price=_d('0.00'), list_price=_d('299.00'), currency='EUR',
            tax_rate=vat21, discount_group=dg_std,
            warranty_months=12, serial_number_required=False,
            inventory_tracked=False,
        )

        pos_pro_lic = _prod(
            sku='NVA-POS-PRO-1Y',
            name='NovaOPS POS Pro – Annual License',
            short_description='Cloud-based POS software, unlimited terminals, loyalty module, priority support, 1-year.',
            brand='NovaOPS', category=cat_sw,
            purchase_price=_d('0.00'), list_price=_d('899.00'), currency='EUR',
            tax_rate=vat21, discount_group=dg_ent,
            warranty_months=12, serial_number_required=False,
            inventory_tracked=False,
        )

        # Price tiers for scanners (volume discount)
        for product, tiers in [
            (honeywell_voy, [
                (1,  9,   '149.00'),
                (10, 49,  '134.00'),
                (50, None,'119.00'),
            ]),
            (datalogic_qd, [
                (1,  19,  '89.00'),
                (20, None,'75.00'),
            ]),
            (epson_t88, [
                (1,  4,   '399.00'),
                (5,  None,'369.00'),
            ]),
        ]:
            for min_q, max_q, price in tiers:
                ProductPriceTier.objects.get_or_create(
                    product=product, min_quantity=min_q,
                    defaults={'max_quantity': max_q, 'unit_price': _d(price)},
                )

        # BOCA product options
        ProductOption.objects.get_or_create(
            parent_product=boca_lemp,
            name='Cutter Module',
            sku='BOCA-CUT-MOD',
            defaults={
                'price_delta': _d('95.00'),
                'is_required': False,
                'is_default': False,
                'sort_order': 1,
            },
        )
        ProductOption.objects.get_or_create(
            parent_product=boca_lemp,
            name='Network Interface Card',
            sku='BOCA-NIC-ETH',
            defaults={
                'price_delta': _d('55.00'),
                'is_required': False,
                'is_default': False,
                'sort_order': 2,
            },
        )

        # HP Engage One Pro options (linked products)
        ProductOption.objects.get_or_create(
            parent_product=hp_engage,
            linked_product=hp_display,
            defaults={
                'name': '',
                'sku': '',
                'price_delta': _d('0.00'),
                'is_required': False,
                'is_default': False,
                'sort_order': 1,
            },
        )
        ProductOption.objects.get_or_create(
            parent_product=hp_engage,
            linked_product=pos_pro_lic,
            defaults={
                'name': '',
                'sku': '',
                'price_delta': _d('0.00'),
                'is_required': False,
                'is_default': False,
                'sort_order': 2,
            },
        )

        # IT specs
        from catalog.models import ProductITSpec
        ProductITSpec.objects.get_or_create(
            product=hp_engage,
            defaults={
                'operating_system': 'Windows 10 IoT Enterprise LTSC 2019',
                'cpu': 'Intel Celeron J4105 (4-core, 1.5GHz)',
                'ram': '8 GB DDR4-2133',
                'storage': '128 GB M.2 SSD',
            },
        )

        # Scanner spec
        from catalog.models import ProductScannerSpec
        ProductScannerSpec.objects.get_or_create(
            product=honeywell_voy,
            defaults={
                'scan_engine': 'Laser (single-line)',
                'drop_spec': '1.5m',
                'ip_rating': 'IP41',
                'battery_mah': 1000,
                'battery_hours': 14,
            },
        )

        # Printer spec
        from catalog.models import ProductPrinterSpec
        for prod, tech, res, width, cutter in [
            (epson_t88,  'Direct thermal', '180 × 180 dpi', '80mm / 79.5mm', 'Auto-cutter'),
            (star_tsp,   'Direct thermal', '203 × 203 dpi', '80mm / 79.5mm', 'Auto-cutter'),
            (boca_lemp,  'Direct thermal', '203 dpi',       '80mm / 78mm',   'Optional cutter module'),
            (zebra_zd421,'Direct thermal', '203 dpi',       '4" / 104mm',    'None'),
        ]:
            ProductPrinterSpec.objects.get_or_create(
                product=prod,
                defaults={
                    'print_technology': tech,
                    'print_resolution': res,
                    'print_width': width,
                    'cutter_type': cutter,
                },
            )

        return {
            'vat21': vat21, 'vat9': vat9, 'vat0': vat0,
            'hp_engage': hp_engage, 'pax_a920': pax_a920, 'ingenico_d5': ingenico_d5,
            'epson_t88': epson_t88, 'star_tsp': star_tsp,
            'boca_lemp': boca_lemp, 'zebra_zd421': zebra_zd421,
            'honeywell_voy': honeywell_voy, 'datalogic_qd': datalogic_qd,
            'hp_display': hp_display, 'cash_drawer': cash_drawer,
            'pos_lite_lic': pos_lite_lic, 'pos_pro_lic': pos_pro_lic,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Relations
    # ─────────────────────────────────────────────────────────────────────────

    def _relations(self) -> dict:
        self.stdout.write('  Creating relations…')
        from relations.models import (
            Affiliation, Communication, CommunicationType,
            Organization, OrganizationCategory, OrganizationCategoryTag,
            Person,
        )

        # Category tags
        def _tag(code, label):
            t, _ = OrganizationCategoryTag.objects.get_or_create(code=code, defaults={'label': label})
            return t

        tag_cust  = _tag('customer',  'Customer')
        tag_prosp = _tag('prospect',  'Prospect')
        tag_supp  = _tag('supplier',  'Supplier / vendor')
        tag_part  = _tag('partner',   'Partner')

        # Organizations
        def _org(name, primary_tag, tags, **kw):
            o, created = Organization.objects.get_or_create(
                name=name,
                defaults={'primary_category': primary_tag, **kw},
            )
            if created:
                o.categories.set(tags)
            return o

        jumbo = _org(
            'Jumbo Supermarkten B.V.', tag_cust, [tag_cust],
            legal_name='Jumbo Food Group B.V.',
            industry='Food retail', tax_id_vat='NL800123456B01',
            website='https://www.jumbo.com',
            notes='National supermarket chain, ~700 stores. Framework contract for POS refresh 2024-2026.',
        )
        blokker = _org(
            'Blokker Retail B.V.', tag_cust, [tag_cust],
            industry='General retail', tax_id_vat='NL800234567B01',
            notes='Mid-size retail chain, ~300 stores. Currently on legacy POS; migration project in scoping.',
        )
        hema = _org(
            'HEMA N.V.', tag_cust, [tag_cust],
            legal_name='HEMA B.V.',
            industry='General retail / lifestyle', tax_id_vat='NL800345678B01',
            notes='European lifestyle retailer, ~600 stores. Primarily Epson receipt printers.',
        )
        marriott = _org(
            'Marriott Amsterdam', tag_cust, [tag_cust],
            industry='Hospitality', tax_id_vat='NL800456789B01',
            notes='Hotel group; F&B outlets use PAX A920 Pro for table-side ordering.',
        )
        foodfirst = _org(
            'FoodFirst B.V.', tag_prosp, [tag_prosp],
            industry='Food & beverage', notes='Fast-growing QSR chain; demo scheduled Q2.',
        )
        hp_nl = _org(
            'HP Netherlands B.V.', tag_supp, [tag_supp],
            industry='Technology manufacturing', tax_id_vat='NL800567890B01',
            website='https://www.hp.com/nl-nl/',
            notes='Primary HP hardware supplier. 30-day payment terms.',
        )
        epson_eu = _org(
            'Epson Europe B.V.', tag_supp, [tag_supp],
            industry='Technology manufacturing', tax_id_vat='NL800678901B01',
            website='https://www.epson.eu',
            notes='Epson EMEA distribution hub. Net 30.',
        )
        ingram = _org(
            'Ingram Micro Netherlands B.V.', tag_supp, [tag_supp],
            industry='IT distribution', tax_id_vat='NL800789012B01',
            notes='Broadline distributor; used for HP, Honeywell, Datalogic, PAX.',
        )
        techpartners = _org(
            'TechPartners B.V.', tag_part, [tag_part],
            industry='IT services / integration', notes='VAR partner; occasional co-delivery on larger projects.',
        )

        # People
        def _person(first, last, **kw):
            p, _ = Person.objects.get_or_create(
                first_name=first, last_name=last,
                defaults=kw,
            )
            return p

        def _affil(person, org, role):
            Affiliation.objects.get_or_create(person=person, organization=org, defaults={'job_title': role})

        def _comm(obj, comm_type, value):
            ct = getattr(CommunicationType, comm_type)
            from django.contrib.contenttypes.models import ContentType
            Communication.objects.get_or_create(
                content_type=ContentType.objects.get_for_model(obj),
                object_id=obj.pk,
                value=value,
                defaults={'comm_type': ct},
            )

        # Jumbo contacts
        petra = _person('Petra', 'van Dijk', bio='IT Procurement Manager at Jumbo. Key decision-maker on POS hardware.')
        _affil(petra, jumbo, 'IT Procurement Manager')
        _comm(petra, 'EMAIL', 'p.van.dijk@jumbo.com')
        _comm(petra, 'PHONE', '+31 73 200 3000')

        bas = _person('Bas', 'Smits', bio='Store Operations Director. Oversees POS rollouts.')
        _affil(bas, jumbo, 'Store Operations Director')
        _comm(bas, 'EMAIL', 'b.smits@jumbo.com')

        # Blokker contacts
        anne = _person('Anne', 'Hofman', bio='CTO at Blokker. Driving the digital transformation programme.')
        _affil(anne, blokker, 'Chief Technology Officer')
        _comm(anne, 'EMAIL', 'a.hofman@blokker.nl')
        _comm(anne, 'PHONE', '+31 20 200 4000')

        # HEMA contacts
        tom = _person('Tom', 'Brouwer', bio='Infrastructure & POS lead.')
        _affil(tom, hema, 'IT Infrastructure Lead')
        _comm(tom, 'EMAIL', 't.brouwer@hema.nl')

        # Marriott contacts
        claire = _person('Claire', 'Dubois', bio='F&B Technology Manager.')
        _affil(claire, marriott, 'F&B Technology Manager')
        _comm(claire, 'EMAIL', 'c.dubois@marriott-amsterdam.com')

        # Supplier contacts
        rob = _person('Rob', 'Willems', bio='HP account manager for NovaOPS.')
        _affil(rob, hp_nl, 'Account Manager')
        _comm(rob, 'EMAIL', 'r.willems@hp.com')

        return {
            'jumbo': jumbo, 'blokker': blokker, 'hema': hema,
            'marriott': marriott, 'foodfirst': foodfirst,
            'hp_nl': hp_nl, 'epson_eu': epson_eu, 'ingram': ingram,
            'techpartners': techpartners,
            'petra': petra, 'bas': bas, 'anne': anne, 'tom': tom,
            'claire': claire,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Inventory
    # ─────────────────────────────────────────────────────────────────────────

    def _inventory(self, catalog: dict) -> dict:
        self.stdout.write('  Creating warehouses & stock…')
        from inventory.models import StockEntry, StockLocation, Warehouse

        # Warehouses
        wh_ams, _ = Warehouse.objects.get_or_create(
            code='WH-AMS',
            defaults={
                'name': 'Amsterdam Central Warehouse',
                'address_line1': 'Transformatorweg 104',
                'city': 'Amsterdam',
                'country': 'Netherlands',
                'notes': 'Main stocking warehouse. Receiving dock on ground floor.',
            },
        )
        wh_rtd, _ = Warehouse.objects.get_or_create(
            code='WH-RTD',
            defaults={
                'name': 'Rotterdam Service Hub',
                'address_line1': 'Waalhaven Z.Z. 19',
                'city': 'Rotterdam',
                'country': 'Netherlands',
                'notes': 'Service & repair hub; loan equipment pool.',
            },
        )

        # Locations
        def _loc(wh, code, name):
            l, _ = StockLocation.objects.get_or_create(warehouse=wh, code=code, defaults={'name': name})
            return l

        recv     = _loc(wh_ams, 'RECV',   'Receiving dock')
        a01      = _loc(wh_ams, 'A-01',   'Aisle A – Bay 01 (POS Terminals)')
        a02      = _loc(wh_ams, 'A-02',   'Aisle A – Bay 02 (Printers)')
        b01      = _loc(wh_ams, 'B-01',   'Aisle B – Bay 01 (Scanners & Accessories)')
        returns  = _loc(wh_ams, 'RETURNS','Returns & Repairs area')
        rtd_main = _loc(wh_rtd, 'MAIN',   'Main floor')
        rtd_loan = _loc(wh_rtd, 'LOANER', 'Loan equipment pool')

        # Seed stock (simulate what was received on previous POs)
        stock = [
            (catalog['hp_engage'],     a01,      12),
            (catalog['pax_a920'],      a01,       8),
            (catalog['ingenico_d5'],   a01,      15),
            (catalog['epson_t88'],     a02,      22),
            (catalog['star_tsp'],      a02,      10),
            (catalog['boca_lemp'],     a02,       6),
            (catalog['zebra_zd421'],   a02,       9),
            (catalog['honeywell_voy'], b01,      45),
            (catalog['datalogic_qd'],  b01,      30),
            (catalog['hp_display'],    a01,      18),
            (catalog['cash_drawer'],   b01,      25),
            # Rotterdam service pool
            (catalog['epson_t88'],     rtd_loan,  3),
            (catalog['hp_engage'],     rtd_loan,  2),
            (catalog['honeywell_voy'], rtd_main,  8),
        ]
        for product, location, qty in stock:
            StockEntry.objects.get_or_create(
                product=product, location=location,
                defaults={'quantity_on_hand': _d(str(qty))},
            )

        return {
            'wh_ams': wh_ams, 'wh_rtd': wh_rtd,
            'recv': recv, 'a01': a01, 'a02': a02,
            'b01': b01, 'returns': returns,
            'rtd_main': rtd_main, 'rtd_loan': rtd_loan,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Procurement
    # ─────────────────────────────────────────────────────────────────────────

    def _procurement(self, catalog: dict, inv: dict, users: dict) -> None:
        self.stdout.write('  Creating purchase orders…')
        from procurement.models import POStatus, PurchaseOrder, PurchaseOrderLine

        def _po(ref, supplier, status, exp_days, notes, lines_data):
            po, created = PurchaseOrder.objects.get_or_create(
                ref=ref,
                defaults={
                    'supplier': supplier,
                    'status': status,
                    'expected_delivery_date': _today() + timedelta(days=exp_days),
                    'notes': notes,
                    'created_by': users['mark'],
                },
            )
            if created:
                for product, qty, cost in lines_data:
                    PurchaseOrderLine.objects.create(
                        purchase_order=po,
                        product=product,
                        qty_ordered=_d(str(qty)),
                        unit_cost=_d(cost),
                        qty_received=_d(str(qty)) if status == POStatus.RECEIVED else _d('0'),
                    )
            return po

        from relations.models import Organization
        ingram  = Organization.objects.filter(name__startswith='Ingram Micro').first()
        epson_e = Organization.objects.filter(name__startswith='Epson Europe').first()

        # PO-1 – fully received (stock already seeded above)
        _po(
            'PO-2026-00001', ingram, POStatus.RECEIVED, -30,
            'Q1 stock replenishment – HP terminals and displays.',
            [
                (catalog['hp_engage'],     15, '695.00'),
                (catalog['hp_display'],    20, '169.00'),
                (catalog['honeywell_voy'], 50, '59.00'),
                (catalog['ingenico_d5'],   20, '149.00'),
            ],
        )

        # PO-2 – partially received
        po2, created2 = PurchaseOrder.objects.get_or_create(
            ref='PO-2026-00002',
            defaults={
                'supplier': epson_e,
                'status': POStatus.PARTIAL,
                'expected_delivery_date': _today() + timedelta(days=7),
                'notes': 'Epson receipt printers – HEMA rollout batch.',
                'created_by': users['mark'],
            },
        )
        if created2:
            PurchaseOrderLine.objects.create(
                purchase_order=po2, product=catalog['epson_t88'],
                qty_ordered=_d('30'), unit_cost=_d('189.00'), qty_received=_d('22'),
            )
            PurchaseOrderLine.objects.create(
                purchase_order=po2, product=catalog['star_tsp'],
                qty_ordered=_d('15'), unit_cost=_d('129.00'), qty_received=_d('10'),
            )

        # PO-3 – draft, not yet sent
        _po(
            'PO-2026-00003', ingram, POStatus.DRAFT, 21,
            'BOCA Lemur+ batch for stadium ticketing customer (pending order confirmation).',
            [
                (catalog['boca_lemp'],     12, '289.00'),
                (catalog['zebra_zd421'],   10, '219.00'),
            ],
        )

        # PO-4 – sent to supplier, awaiting delivery
        _po(
            'PO-2026-00004', ingram, POStatus.SENT, 14,
            'PAX A920 Pro restock – hospitality vertical.',
            [
                (catalog['pax_a920'],      20, '229.00'),
                (catalog['cash_drawer'],   30, '29.00'),
            ],
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Sales
    # ─────────────────────────────────────────────────────────────────────────

    def _sales(self, catalog: dict, rels: dict, users: dict) -> None:
        self.stdout.write('  Creating quotes, orders, invoices…')
        from sales.models import (
            FulfillmentOrder, FulfillmentOrderLine, FulfillmentOrderStatus,
            Invoice, InvoiceLine, InvoicePayment, InvoiceStatus,
            OrderLine, OrderStatus,
            Quote, QuoteLine, QuoteStatus,
            SalesOrder,
        )
        from core.models import next_reference

        year = _today().year
        sarah = users['sarah']
        admin = users['admin']

        def _quote_ref():
            return next_reference('Q', year)

        def _order_ref():
            return next_reference('SO', year)

        def _inv_ref():
            return next_reference('INV', year)

        def _fo_ref():
            return next_reference('FO', year)

        # ── Quote 1: Jumbo – POS refresh pilot (accepted → order → invoice paid) ──
        if not Quote.objects.filter(reference='Q-2026-00001').exists():
            q1 = Quote.objects.create(
                reference='Q-2026-00001',
                created_by=sarah,
                relation_organization=rels['jumbo'],
                status=QuoteStatus.ACCEPTED,
                valid_until=_today() + timedelta(days=30),
                is_locked=True,
                notes='Pilot refresh for 5 Amsterdam stores. Includes POS terminals, displays and Pro licenses.',
            )
            ql1a = QuoteLine.objects.create(
                quote=q1, product=catalog['hp_engage'],
                product_name=catalog['hp_engage'].name,
                sku=catalog['hp_engage'].sku, brand='HP',
                quantity=5, unit_price=_d('1199.00'),
                line_total=_d('5995.00'), sort_order=1,
            )
            ql1b = QuoteLine.objects.create(
                quote=q1, product=catalog['hp_display'],
                product_name=catalog['hp_display'].name,
                sku=catalog['hp_display'].sku, brand='HP',
                quantity=5, unit_price=_d('299.00'),
                line_total=_d('1495.00'), sort_order=2,
            )
            QuoteLine.objects.create(
                quote=q1, product=catalog['pos_pro_lic'],
                product_name=catalog['pos_pro_lic'].name,
                sku=catalog['pos_pro_lic'].sku, brand='NovaOPS',
                quantity=5, unit_price=_d('849.00'),
                line_total=_d('4245.00'), sort_order=3,
            )
            QuoteLine.objects.create(
                quote=q1, product=catalog['cash_drawer'],
                product_name=catalog['cash_drawer'].name,
                sku=catalog['cash_drawer'].sku, brand='Posiflex',
                quantity=5, unit_price=_d('59.00'),
                line_total=_d('295.00'), sort_order=4,
            )

            # Sales order
            so1 = SalesOrder.objects.create(
                reference='SO-2026-00001',
                created_by=sarah,
                quote=q1,
                relation_organization=rels['jumbo'],
                status=OrderStatus.FULFILLED,
            )
            for ql in q1.lines.all():
                OrderLine.objects.create(
                    order=so1, product=ql.product,
                    product_name=ql.product_name, sku=ql.sku, brand=ql.brand,
                    quantity=ql.quantity, unit_price=ql.unit_price,
                    line_total=ql.line_total, sort_order=ql.sort_order,
                )

            # Fulfillment
            fo1 = FulfillmentOrder.objects.create(
                reference='FO-2026-00001',
                sales_order=so1, created_by=admin,
                status=FulfillmentOrderStatus.COMPLETED,
            )
            for ol in so1.lines.all():
                FulfillmentOrderLine.objects.create(
                    fulfillment_order=fo1, product=ol.product,
                    product_name=ol.product_name, sku=ol.sku, brand=ol.brand,
                    quantity=ol.quantity, sort_order=ol.sort_order,
                )

            # Invoice
            inv1 = Invoice.objects.create(
                reference='INV-2026-00001',
                order=so1, created_by=sarah,
                relation_organization=rels['jumbo'],
                status=InvoiceStatus.ISSUED,
                due_date=_today() - timedelta(days=15),
            )
            for ol in so1.lines.all():
                InvoiceLine.objects.create(
                    invoice=inv1, product=ol.product,
                    product_name=ol.product_name, sku=ol.sku, brand=ol.brand,
                    quantity=ol.quantity, unit_price=ol.unit_price,
                    line_total=ol.line_total, sort_order=ol.sort_order,
                )
            InvoicePayment.objects.create(
                invoice=inv1,
                amount=_d('12030.00'),
                reference_note='Jumbo bank transfer REF-JMB-2026-0441',
                created_by=sarah,
            )

        # ── Quote 2: HEMA – receipt printer rollout (order confirmed) ──
        if not Quote.objects.filter(reference='Q-2026-00002').exists():
            q2 = Quote.objects.create(
                reference='Q-2026-00002',
                created_by=sarah,
                relation_organization=rels['hema'],
                status=QuoteStatus.ACCEPTED,
                valid_until=_today() + timedelta(days=60),
                is_locked=True,
                notes='100-store receipt printer upgrade. Epson TM-T88VII + Star as backup option.',
            )
            QuoteLine.objects.create(
                quote=q2, product=catalog['epson_t88'],
                product_name=catalog['epson_t88'].name,
                sku=catalog['epson_t88'].sku, brand='Epson',
                quantity=10, unit_price=_d('369.00'),
                line_total=_d('3690.00'), sort_order=1,
            )

            so2 = SalesOrder.objects.create(
                reference='SO-2026-00002',
                created_by=sarah,
                quote=q2,
                relation_organization=rels['hema'],
                status=OrderStatus.CONFIRMED,
                notes='Waiting on stock from PO-2026-00002.',
            )
            for ql in q2.lines.all():
                OrderLine.objects.create(
                    order=so2, product=ql.product,
                    product_name=ql.product_name, sku=ql.sku, brand=ql.brand,
                    quantity=ql.quantity, unit_price=ql.unit_price,
                    line_total=ql.line_total, sort_order=ql.sort_order,
                )

        # ── Quote 3: Blokker – POS migration scoping quote (sent) ──
        if not Quote.objects.filter(reference='Q-2026-00003').exists():
            Quote.objects.create(
                reference='Q-2026-00003',
                created_by=sarah,
                relation_organization=rels['blokker'],
                status=QuoteStatus.SENT,
                valid_until=_today() + timedelta(days=45),
                notes='Migration from legacy POS to PAX A920 Pro across 50 pilot stores.',
                external_reference='BLK-RFQ-2026-019',
            )
            q3 = Quote.objects.get(reference='Q-2026-00003')
            QuoteLine.objects.create(
                quote=q3, product=catalog['pax_a920'],
                product_name=catalog['pax_a920'].name,
                sku=catalog['pax_a920'].sku, brand='PAX',
                quantity=50, unit_price=_d('419.00'),
                line_total=_d('20950.00'), sort_order=1,
            )
            QuoteLine.objects.create(
                quote=q3, product=catalog['honeywell_voy'],
                product_name=catalog['honeywell_voy'].name,
                sku=catalog['honeywell_voy'].sku, brand='Honeywell',
                quantity=50, unit_price=_d('134.00'),
                line_total=_d('6700.00'), sort_order=2,
            )
            QuoteLine.objects.create(
                quote=q3, product=catalog['pos_lite_lic'],
                product_name=catalog['pos_lite_lic'].name,
                sku=catalog['pos_lite_lic'].sku, brand='NovaOPS',
                quantity=50, unit_price=_d('279.00'),
                line_total=_d('13950.00'), sort_order=3,
            )

        # ── Quote 4: Marriott – hospitality POS (draft) ──
        if not Quote.objects.filter(reference='Q-2026-00004').exists():
            q4 = Quote.objects.create(
                reference='Q-2026-00004',
                created_by=sarah,
                relation_organization=rels['marriott'],
                status=QuoteStatus.DRAFT,
                notes='F&B outlets – 3 restaurants + bar. Table-side ordering and receipt printing.',
            )
            QuoteLine.objects.create(
                quote=q4, product=catalog['pax_a920'],
                product_name=catalog['pax_a920'].name,
                sku=catalog['pax_a920'].sku, brand='PAX',
                quantity=8, unit_price=_d('449.00'),
                line_total=_d('3592.00'), sort_order=1,
            )
            QuoteLine.objects.create(
                quote=q4, product=catalog['epson_t88'],
                product_name=catalog['epson_t88'].name,
                sku=catalog['epson_t88'].sku, brand='Epson',
                quantity=4, unit_price=_d('399.00'),
                line_total=_d('1596.00'), sort_order=2,
            )

        # ── Quote 5: FoodFirst – prospect (draft) ──
        if not Quote.objects.filter(reference='Q-2026-00005').exists():
            q5 = Quote.objects.create(
                reference='Q-2026-00005',
                created_by=sarah,
                relation_organization=rels['foodfirst'],
                status=QuoteStatus.DRAFT,
                notes='QSR kiosk concept – 5 locations, 2 self-service kiosk terminals each.',
            )
            QuoteLine.objects.create(
                quote=q5, product=catalog['hp_engage'],
                product_name=catalog['hp_engage'].name,
                sku=catalog['hp_engage'].sku, brand='HP',
                quantity=10, unit_price=_d('1199.00'),
                line_total=_d('11990.00'), sort_order=1,
            )

        # Ensure reference counters are ahead of our hard-coded refs
        for prefix, min_n in [('Q', 5), ('SO', 2), ('INV', 1), ('FO', 1)]:
            from core.models import ReferenceSequence
            key = f'{prefix}-{year}'
            seq, _ = ReferenceSequence.objects.get_or_create(key=key, defaults={'last_n': 0})
            if seq.last_n < min_n:
                seq.last_n = min_n
                seq.save()

    # ─────────────────────────────────────────────────────────────────────────
    # Assets
    # ─────────────────────────────────────────────────────────────────────────

    def _assets(self, catalog: dict, rels: dict, users: dict) -> None:
        self.stdout.write('  Creating assets…')
        from assets.models import Asset, AssetEvent, AssetEventType, AssetStatus

        admin = users['admin']
        today = _today()

        def _asset(org, product, serial, tag, purchase, install, warranty_end, location, status=AssetStatus.IN_SERVICE, notes=''):
            a, _ = Asset.objects.get_or_create(
                serial_number=serial,
                defaults={
                    'organization': org,
                    'product': product,
                    'asset_tag': tag,
                    'purchase_date': purchase,
                    'installation_date': install,
                    'warranty_end_date': warranty_end,
                    'location_note': location,
                    'status': status,
                    'notes': notes,
                    'created_by': admin,
                },
            )
            return a

        # ── Jumbo assets (HP Engage One Pro at 5 stores) ──
        stores = [
            ('JUMP-AMS-001', 'AT-JMB-001', 'Amsterdam Overtoom – Checkout 1'),
            ('JUMP-AMS-002', 'AT-JMB-002', 'Amsterdam Overtoom – Checkout 2'),
            ('JUMP-AMS-003', 'AT-JMB-003', 'Amsterdam Beethovenstraat – Checkout 1'),
            ('JUMP-AMS-004', 'AT-JMB-004', 'Amsterdam Beethovenstraat – Checkout 2'),
            ('JUMP-AMS-005', 'AT-JMB-005', 'Amsterdam Jordaan – Service desk'),
        ]
        for serial, tag, location in stores:
            _asset(
                rels['jumbo'], catalog['hp_engage'],
                serial, tag,
                purchase=today - timedelta(days=90),
                install=today - timedelta(days=75),
                warranty_end=today + timedelta(days=3*365-75),
                location=location,
            )

        # ── HEMA assets (older Epson TM-T88VI, pre-upgrade) ──
        for i in range(1, 4):
            a = _asset(
                rels['hema'], catalog['epson_t88'],
                f'HEMA-T88-{i:03d}', f'AT-HMA-{i:03d}',
                purchase=today - timedelta(days=3*365),
                install=today - timedelta(days=3*365),
                warranty_end=today - timedelta(days=365),
                location=f'HEMA Kalverstraat Amsterdam – Checkout {i}',
                status=AssetStatus.IN_SERVICE,
                notes='Legacy unit; scheduled for replacement under SO-2026-00002.',
            )

        # ── Marriott assets (PAX A920 Pro, table-side) ──
        for i in range(1, 5):
            _asset(
                rels['marriott'], catalog['pax_a920'],
                f'MAR-PAX-{i:03d}', f'AT-MAR-{i:03d}',
                purchase=today - timedelta(days=365),
                install=today - timedelta(days=350),
                warranty_end=today + timedelta(days=365),
                location=f'Marriott Amsterdam – Restaurant floor, table cluster {i}',
            )

        # Asset events on Jumbo assets
        jumbo_assets = Asset.objects.filter(organization=rels['jumbo'])
        for asset in jumbo_assets[:2]:
            AssetEvent.objects.get_or_create(
                asset=asset,
                event_type=AssetEventType.INSTALLATION,
                title='Initial installation & commissioning',
                defaults={
                    'description': 'HP Engage One Pro configured and handed over to store manager.',
                    'occurred_on': asset.installation_date or today - timedelta(days=75),
                    'created_by': users['lisa'],
                },
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Contracts
    # ─────────────────────────────────────────────────────────────────────────

    def _contracts(self, rels: dict, users: dict) -> None:
        self.stdout.write('  Creating service contracts…')
        from contracts.models import (
            Contract, ContractStatus, ContractTemplate,
            ContractTemplateVariable, ContractVariableType,
            ContractVariableValue, ServiceRate,
        )

        # Service rates
        rate_tech, _ = ServiceRate.objects.get_or_create(
            code='field_engineer',
            defaults={'name': 'Field engineer', 'rate_per_hour': _d('95.00'), 'currency': 'EUR'},
        )
        rate_remote, _ = ServiceRate.objects.get_or_create(
            code='remote_support',
            defaults={'name': 'Remote support', 'rate_per_hour': _d('65.00'), 'currency': 'EUR'},
        )

        # Contract template
        tmpl, created = ContractTemplate.objects.get_or_create(
            name='POS Full Service Agreement',
            defaults={
                'description': 'Annual POS service contract covering on-site and remote support.',
                'formula': 'field_engineer * onsite_hours + remote_support * remote_hours + management_fee',
                'result_label': 'Annual contract value',
                'is_active': True,
            },
        )
        if created:
            ContractTemplateVariable.objects.create(
                template=tmpl, name='field_engineer',
                label='Field engineer rate (€/h)', variable_type=ContractVariableType.SERVICE_RATE,
                service_rate=rate_tech,
            )
            ContractTemplateVariable.objects.create(
                template=tmpl, name='remote_support',
                label='Remote support rate (€/h)', variable_type=ContractVariableType.SERVICE_RATE,
                service_rate=rate_remote,
            )
            ContractTemplateVariable.objects.create(
                template=tmpl, name='onsite_hours',
                label='Contracted on-site hours per year', variable_type=ContractVariableType.USER_INPUT,
            )
            ContractTemplateVariable.objects.create(
                template=tmpl, name='remote_hours',
                label='Contracted remote support hours per year', variable_type=ContractVariableType.USER_INPUT,
            )
            ContractTemplateVariable.objects.create(
                template=tmpl, name='management_fee',
                label='Annual management fee (€)', variable_type=ContractVariableType.CONSTANT,
                constant_value=_d('500.00'),
            )

        sarah = users['sarah']
        today = _today()

        # Jumbo contract
        Contract.objects.get_or_create(
            reference='CTR-2026-00001',
            defaults={
                'template': tmpl,
                'organization': rels['jumbo'],
                'status': ContractStatus.ACTIVE,
                'start_date': today - timedelta(days=60),
                'end_date': today + timedelta(days=305),
                'notes': (
                    'Full service agreement covering all 5 HP Engage One Pro units installed at '
                    'Amsterdam stores. 4-hour SLA on business days, remote support included.'
                ),
            },
        )

        # HEMA contract (basic)
        Contract.objects.get_or_create(
            reference='CTR-2026-00002',
            defaults={
                'template': tmpl,
                'organization': rels['hema'],
                'status': ContractStatus.ACTIVE,
                'start_date': today - timedelta(days=30),
                'end_date': today + timedelta(days=335),
                'notes': 'Basic maintenance contract for existing Epson printer fleet. Covers parts and labour.',
            },
        )

        # Ensure contract reference counter is set
        from core.models import ReferenceSequence
        year = today.year
        key = f'CTR-{year}'
        seq, _ = ReferenceSequence.objects.get_or_create(key=key, defaults={'last_n': 0})
        if seq.last_n < 2:
            seq.last_n = 2
            seq.save()
