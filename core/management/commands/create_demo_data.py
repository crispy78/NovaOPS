"""
Management command: seed comprehensive demo data.

Usage:
  python manage.py create_demo_data          # seed (idempotent)
  python manage.py create_demo_data --clear  # wipe everything first, then seed
  python manage.py create_demo_data --skip-images  # skip slow image downloads

Images are downloaded from loremflickr.com (CC-licensed) with a Pillow gradient
fallback so the command always succeeds without a network connection.
"""

from __future__ import annotations

import io
import urllib.error
import urllib.request
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

# ── Catalog ────────────────────────────────────────────────────────────────────
from catalog.models import (
    AssetType,
    DiscountGroup,
    Product,
    ProductBOMLine,
    ProductCategory,
    ProductConnectivitySpec,
    ProductDisplaySpec,
    ProductDocument,
    ProductDocumentType,
    ProductImage,
    ProductITSpec,
    ProductPriceTier,
    ProductPrinterSpec,
    ProductRelation,
    ProductRelationType,
    ProductScannerSpec,
    ProductStatus,
    TaxRate,
    TouchscreenType,
)

# ── Relations ──────────────────────────────────────────────────────────────────
from relations.models import (
    Address,
    AddressType,
    Affiliation,
    Communication,
    CommunicationType,
    Organization,
    OrganizationCategory,
    OrganizationCategoryTag,
    OrganizationLink,
    OrganizationLinkType,
    OrganizationUnitKind,
    Person,
    SocialProfile,
    SpecialEvent,
)

# ── Assets ─────────────────────────────────────────────────────────────────────
from assets.models import (
    Asset,
    AssetEvent,
    AssetEventType,
    AssetOrganizationTransfer,
    AssetRecallLink,
    AssetRecallStatus,
    AssetReplacementRecommendation,
    AssetStatus,
    MaintenancePlan,
    MaintenancePlanLine,
    MaintenancePlanLineStatus,
    MaintenancePlanStatus,
    RecallCampaign,
    ReplacementPriority,
    ReplacementRecommendationStatus,
)

# ── Sales ──────────────────────────────────────────────────────────────────────
from sales.models import (
    Cart,
    CartLine,
    FulfillmentOrder,
    FulfillmentOrderLine,
    FulfillmentOrderStatus,
    Invoice,
    InvoiceLine,
    InvoicePayment,
    InvoiceStatus,
    OrderLine,
    OrderStatus,
    Quote,
    QuoteLine,
    QuoteStatus,
    SalesOrder,
    Shipment,
    ShipmentLine,
    ShipmentStatus,
    ShippingOrder,
    ShippingOrderLine,
    ShippingOrderStatus,
    snapshot_line_from_product,
)


# ── Stable UUID namespaces ──────────────────────────────────────────────────────

def _uuid(ns: str, key: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f'demo-{ns}-seed:{key}')

def _cat_uuid(k: str)  -> uuid.UUID: return _uuid('catalog', k)
def _rel_uuid(k: str)  -> uuid.UUID: return _uuid('relations', k)
def _ast_uuid(k: str)  -> uuid.UUID: return _uuid('assets', k)
def _sal_uuid(k: str)  -> uuid.UUID: return _uuid('sales', k)


# ── Hardcoded demo references (won't collide with real sequence counters) ───────
_REFS = {
    'recall_1':   'RC-DEMO-0001',
    'mjop_1':     'MJOP-DEMO-0001',
    'q1':         'Q-DEMO-0001',
    'q2':         'Q-DEMO-0002',
    'q3':         'Q-DEMO-0003',
    'q4':         'Q-DEMO-0004',
    'q5':         'Q-DEMO-0005',
    'so1':        'SO-DEMO-0001',
    'so2':        'SO-DEMO-0002',
    'so3':        'SO-DEMO-0003',
    'so4':        'SO-DEMO-0004',
    'fo1':        'FO-DEMO-0001',
    'fo2':        'FO-DEMO-0002',
    'fo3':        'FO-DEMO-0003',
    'sho1':       'SHP-DEMO-0001',
    'sho2':       'SHP-DEMO-0002',
    'inv1':       'INV-DEMO-0001',
    'inv2':       'INV-DEMO-0002',
    'inv3':       'INV-DEMO-0003',
}

# ── Product image URLs (loremflickr.com - CC-licensed, keyword-matched) ─────────
# loremflickr returns a consistent photo for each lock seed.
_IMAGE_URLS: dict[str, str] = {
    'NEW-MT93-4G':         'https://loremflickr.com/800/600/handheld,terminal,scanner?lock=401',
    'NEW-HR15-W':          'https://loremflickr.com/800/600/barcode,scanner?lock=402',
    'NEW-HR22-BT':         'https://loremflickr.com/800/600/bluetooth,scanner?lock=403',
    'BOCA-LEMUR-X':        'https://loremflickr.com/800/600/ticket,printer?lock=404',
    'DURAPOS-DPT201':      'https://loremflickr.com/800/600/receipt,printer?lock=405',
    'DISP-USB-101':        'https://loremflickr.com/800/600/monitor,display,screen?lock=406',
    'HP-ENGAGE-ONE-PRIME': 'https://loremflickr.com/800/600/pos,terminal,touchscreen?lock=407',
    'SYS-MINIPC-I5':       'https://loremflickr.com/800/600/minipc,computer,hardware?lock=408',
    'MON-15-TOUCH':        'https://loremflickr.com/800/600/touchscreen,monitor?lock=409',
    'BUNDLE-WKP-BASIC':    'https://loremflickr.com/800/600/workstation,office,computer?lock=410',
}

_DEMO_DOC_BODY = (
    b'Document demo attachment\n'
    b'This file is synthetic seed data for UI testing only.\n'
    b'Do not distribute or use in production.\n'
)


# ── Image helpers ───────────────────────────────────────────────────────────────

def _download_image(url: str, timeout: int = 10) -> bytes | None:
    """Try to download image bytes; return None on any failure."""
    try:
        req = urllib.request.Request(
            url, headers={'User-Agent': 'Mozilla/5.0 (compatible; DemoSeeder/1.0)'}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def _pil_placeholder(name: str, sku: str, category: str = '') -> bytes:
    """
    Generate a clean gradient placeholder image using Pillow.
    Used as fallback when network download fails.
    """
    from PIL import Image, ImageDraw

    W, H = 800, 600
    # Dark navy-to-slate gradient background
    img = Image.new('RGB', (W, H), (15, 23, 42))
    draw = ImageDraw.Draw(img)

    for y in range(H):
        t = y / H
        r = int(15 + (30 - 15) * t)
        g = int(23 + (41 - 23) * t)
        b = int(42 + (59 - 42) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Card panel
    draw.rounded_rectangle([60, 80, W - 60, H - 80], radius=16,
                            fill=(30, 41, 59), outline=(51, 65, 85))

    # Blue accent bar at top of card
    draw.rounded_rectangle([60, 80, W - 60, 130], radius=12, fill=(2, 132, 199))

    # Subtle grid dots for texture
    for gx in range(80, W - 60, 40):
        for gy in range(150, H - 90, 40):
            draw.ellipse([gx - 1, gy - 1, gx + 1, gy + 1], fill=(51, 65, 85))

    # Category chip
    if category:
        label = category[:22].upper()
        chip_w = len(label) * 7 + 20
        draw.rounded_rectangle([80, 148, 80 + chip_w, 170], radius=8, fill=(14, 165, 233))

    # SKU
    sku_label = sku[:28]
    draw.text((W // 2, H // 2 - 20), sku_label, fill=(148, 163, 184), anchor='mm')

    # Bottom rule
    draw.line([(80, H - 100), (W - 80, H - 100)], fill=(51, 65, 85), width=1)

    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=88)
    return buf.getvalue()


def _get_product_image(sku: str, name: str, category: str, skip: bool) -> bytes:
    """Return image bytes: download from internet or fall back to Pillow placeholder."""
    if not skip and sku in _IMAGE_URLS:
        data = _download_image(_IMAGE_URLS[sku])
        if data:
            return data
    return _pil_placeholder(name, sku, category)


# ── Clear helpers ───────────────────────────────────────────────────────────────

def _clear_all() -> None:
    # Contracts and pricing must go first (they reference orgs/orders via PROTECT)
    from contracts.models import (
        Contract, ContractTemplate, ContractTemplateVariable, ContractVariableValue, ServiceRate,
    )
    from pricing.models import PricingRule, PricingRuleAssignment
    from procurement.models import PurchaseOrder, PurchaseOrderLine
    from catalog.models import ProductOption

    ContractVariableValue.objects.all().delete()
    Contract.objects.all().delete()
    ContractTemplateVariable.objects.all().delete()
    ContractTemplate.objects.all().delete()
    ServiceRate.objects.all().delete()
    PricingRuleAssignment.objects.all().delete()
    PricingRule.objects.all().delete()

    # Purchase orders reference Product via PROTECT - must go before products.
    PurchaseOrderLine.objects.all().delete()
    PurchaseOrder.objects.all().delete()

    ShipmentLine.objects.all().delete()
    Shipment.objects.all().delete()
    ShippingOrderLine.objects.all().delete()
    ShippingOrder.objects.all().delete()
    FulfillmentOrderLine.objects.all().delete()
    FulfillmentOrder.objects.all().delete()
    InvoicePayment.objects.all().delete()
    InvoiceLine.objects.all().delete()
    Invoice.objects.all().delete()
    OrderLine.objects.all().delete()
    SalesOrder.objects.all().delete()
    QuoteLine.objects.all().delete()
    Quote.objects.all().delete()
    CartLine.objects.all().delete()
    Cart.objects.all().delete()

    AssetEvent.objects.all().delete()
    AssetRecallLink.objects.all().delete()
    AssetOrganizationTransfer.objects.all().delete()
    AssetReplacementRecommendation.objects.all().delete()
    Asset.objects.all().delete()
    MaintenancePlanLine.objects.all().delete()
    MaintenancePlan.objects.all().delete()
    RecallCampaign.objects.all().delete()

    Affiliation.objects.all().delete()
    OrganizationLink.objects.all().delete()
    OrganizationLinkType.objects.all().delete()
    Communication.objects.all().delete()
    SocialProfile.objects.all().delete()
    SpecialEvent.objects.all().delete()
    Person.objects.all().delete()
    while Organization.objects.exists():
        deleted, _ = Organization.objects.filter(children__isnull=True).delete()
        if not deleted:
            Organization.objects.all().delete()
            break
    OrganizationCategoryTag.objects.all().delete()

    # ProductOption references Product via PROTECT - must go before products.
    ProductOption.objects.all().delete()
    ProductImage.objects.all().delete()
    ProductDocument.objects.all().delete()
    ProductBOMLine.objects.all().delete()
    ProductRelation.objects.all().delete()
    ProductPriceTier.objects.all().delete()
    Product.objects.all().delete()
    while ProductCategory.objects.exists():
        deleted, _ = (
            ProductCategory.objects.annotate(_n=Count('children')).filter(_n=0).delete()
        )
        if not deleted:
            ProductCategory.objects.all().delete()
            break
    TaxRate.objects.all().delete()
    DiscountGroup.objects.all().delete()

    from audit.models import EventLog
    EventLog.objects.all().delete()


# ── Generic contact helpers ─────────────────────────────────────────────────────

def _comm(ct, oid, *, comm_type, value, label='', primary=False):
    Communication.objects.update_or_create(
        content_type=ct, object_id=oid, comm_type=comm_type, value=value,
        defaults={'label': label, 'is_primary': primary},
    )


def _addr(ct, oid, *, address_type, street, zipcode, city,
          country='Netherlands', label='', street2='', state_province=''):
    Address.objects.update_or_create(
        content_type=ct, object_id=oid, address_type=address_type,
        street=street, zipcode=zipcode, city=city,
        defaults={'country': country, 'label': label, 'street2': street2,
                  'state_province': state_province},
    )


# ── Main command ────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Seed comprehensive demo data for all screens (catalog, relations, assets, sales, contracts).'

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--clear', action='store_true',
            help='Delete all existing data first, then re-seed.',
        )
        parser.add_argument(
            '--skip-images', action='store_true',
            help='Skip internet image downloads; use Pillow-generated placeholders only.',
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        if options['clear']:
            _clear_all()
            self.stdout.write(self.style.WARNING('  Cleared all demo data.'))

        self._skip_images = options['skip_images']

        self._seed_catalog()
        self._seed_relations()
        self._seed_assets()
        self._seed_sales()
        self._seed_pricing()
        self._seed_contracts()
        self.stdout.write(self.style.SUCCESS('\nDemo data ready -- all screens populated.'))

    # ── CATALOG ────────────────────────────────────────────────────────────────

    def _seed_catalog(self) -> None:
        self.stdout.write('  Seeding catalog…')

        vat21, _ = TaxRate.objects.get_or_create(
            code='NL_STD',
            defaults={'name': 'VAT standard (Netherlands)', 'rate': Decimal('21.00')},
        )
        TaxRate.objects.get_or_create(
            code='NL_RED',
            defaults={'name': 'VAT reduced (Netherlands)', 'rate': Decimal('9.00')},
        )
        TaxRate.objects.get_or_create(
            code='EU_ZERO',
            defaults={'name': 'Zero-rated (intra-EU B2B)', 'rate': Decimal('0.00')},
        )
        TaxRate.objects.get_or_create(
            code='DE_STD',
            defaults={'name': 'VAT standard (Germany)', 'rate': Decimal('19.00')},
        )

        dg_retail,    _ = DiscountGroup.objects.get_or_create(slug='retail',    defaults={'name': 'Retail list'})
        dg_wholesale, _ = DiscountGroup.objects.get_or_create(slug='wholesale', defaults={'name': 'Wholesale'})
        dg_partner,   _ = DiscountGroup.objects.get_or_create(slug='partner',   defaults={'name': 'Partner / integrator'})

        def cat(slug, name, parent=None):
            obj, _ = ProductCategory.objects.get_or_create(slug=slug, defaults={'name': name, 'parent': parent})
            if obj.name != name or obj.parent_id != (parent.pk if parent else None):
                obj.name = name; obj.parent = parent; obj.save()
            return obj

        hardware    = cat('hardware',            'Hardware')
        pos         = cat('point-of-sale',       'Point of sale',              hardware)
        terminals   = cat('pos-terminals',       'Terminals & mobile computers', pos)
        scanners    = cat('pos-scanners',        'Scanners',                    pos)
        printers    = cat('pos-printers',        'Receipt & ticket printers',   pos)
        displays    = cat('pos-displays',        'Customer displays',           pos)
        cables      = cat('cables-accessories',  'Cables & accessories',        hardware)
        consumables = cat('consumables',         'Consumables')
        bundles     = cat('bundles-kits',        'Bundles & kits',              hardware)

        def p(sku, *, name, category, status=ProductStatus.ACTIVE, brand='', short='',
              long_desc='', ean='', mpn='', upc='', size_or_volume='', lead_time_text='',
              purchase=None, list_price=None, msrp=None, tax=None, discount_group=None,
              uom='piece', moq=1, lead_days=3, warehouse='A-12-03', serial_req=False,
              warranty=24, maintenance='', depreciation=None, asset_type=None,
              inventory_tracked=True, length=None, width=None, height=None, dim_unit='mm',
              w_net=None, w_gross=None, w_unit='g', color='', material='',
              fetch_image=False, **kwargs) -> Product:
            defaults = dict(
                name=name, short_description=short[:255], long_description=long_desc,
                brand=brand, category=category, status=status, ean_gtin=ean, mpn=mpn,
                upc_isbn=upc, size_or_volume=size_or_volume, lead_time_text=lead_time_text,
                purchase_price=purchase, list_price=list_price, msrp=msrp, currency='EUR',
                tax_rate=tax or vat21, discount_group=discount_group, unit_of_measure=uom,
                minimum_order_quantity=moq, lead_time_days=lead_days,
                warehouse_location=warehouse, inventory_tracked=inventory_tracked,
                serial_number_required=serial_req, warranty_months=warranty,
                maintenance_interval=maintenance, depreciation_months=depreciation,
                asset_type=asset_type, length=length, width=width, height=height,
                dimension_unit=dim_unit, weight_net=w_net, weight_gross=w_gross,
                weight_unit=w_unit, color=color, material=material,
            )
            defaults.update(kwargs)
            obj, created = Product.objects.update_or_create(sku=sku, defaults=defaults)
            if fetch_image and (created or not ProductImage.objects.filter(product=obj).exists()):
                self.stdout.write(f'    Fetching image for {sku}…')
                img_bytes = _get_product_image(sku, name, category.name, self._skip_images)
                ext = '.jpg'
                ProductImage.objects.create(
                    product=obj,
                    image=ContentFile(img_bytes, name=f'{sku}{ext}'),
                    is_primary=True, sort_order=0, alt_text=name,
                )
            return obj

        # ── Products ──────────────────────────────────────────────────────────

        mt93 = p('NEW-MT93-4G',
            name='Newland MT93 Falcon mobile data terminal (4G)', category=terminals, brand='Newland',
            short='Rugged Android 13 mobile computer with 2D imager, Wi-Fi 6, 4G, NFC - events & retail.',
            long_desc=(
                'The MT93 Falcon is suited for scan-intensive workflows: ticketing, access control, and '
                'line busting. Supports GS1 barcodes and QR from phone screens. Includes enterprise '
                'Android lifecycle options for security patching. Battery hot-swap capable.'
            ),
            ean='8719324001234', mpn='MT93-4G-EU', upc='843849012345',
            size_or_volume='Handheld form factor (see L×W×H)',
            lead_time_text='Usually 5–7 business days from NL stock',
            purchase=Decimal('485.00'), list_price=Decimal('749.00'), msrp=Decimal('799.00'),
            discount_group=dg_retail, serial_req=True, warranty=36,
            maintenance='Every 12 months - battery check & cleaning recommended',
            depreciation=36, asset_type=AssetType.SOLD,
            length=Decimal('165'), width=Decimal('78'), height=Decimal('24'),
            w_net=Decimal('285'), w_gross=Decimal('520'),
            color='Black', material='Polycarbonate / rubber grips', lead_days=5,
            fetch_image=True,
        )
        hr15 = p('NEW-HR15-W',
            name='Newland HR15 Marlin wired 2D scanner', category=scanners, brand='Newland',
            short='Handheld USB 2D imager - strong performance on phone-screen QR and damaged labels.',
            long_desc='Ideal companion for fixed POS: lightweight, desk stand optional, USB-HID keyboard wedge.',
            ean='8719324001456', mpn='HR15-W1-USB', upc='843849012401',
            lead_time_text='1–3 business days when in stock',
            purchase=Decimal('42.00'), list_price=Decimal('89.00'), msrp=Decimal('99.00'),
            discount_group=dg_wholesale, warranty=24,
            length=Decimal('175'), width=Decimal('65'), height=Decimal('95'),
            w_net=Decimal('145'), w_gross=Decimal('280'), fetch_image=True,
        )
        hr22 = p('NEW-HR22-BT',
            name='Newland HR22 Dorada Bluetooth 2D scanner', category=scanners, brand='Newland',
            short='Wireless 2D scanner with batch mode; pairs with tablets and mobile POS.',
            long_desc=(
                'HR22 connects via Bluetooth HID or SPP. Batch mode stores up to 10,000 scans offline '
                'for areas with unreliable wireless. Ships with USB base cradle.'
            ),
            ean='8719324001678', mpn='HR22-BT-BK', upc='843849012418',
            lead_time_text='1–3 business days when in stock',
            purchase=Decimal('58.00'), list_price=Decimal('119.00'), warranty=24, fetch_image=True,
        )
        boca = p('BOCA-LEMUR-X',
            name='BOCA Lemur-X direct thermal ticket printer', category=printers, brand='BOCA',
            short='Compact kiosk/event printer for tickets and wristbands; USB + RS232.',
            long_desc=(
                'Common in box office and venue deployments. Pair with cash drawers via RJ11 where '
                'supported. Confirm media width with the venue template before quoting.'
            ),
            mpn='LEMUR-X-USB-RS232', upc='843849010002',
            lead_time_text='Factory lead time ~7 days; confirm before quoting',
            purchase=Decimal('310.00'), list_price=Decimal('529.00'), msrp=Decimal('579.00'),
            serial_req=True, warranty=24, lead_days=7, warehouse='B-04-01', fetch_image=True,
        )
        durapos = p('DURAPOS-DPT201',
            name='Durapos DPT-201 receipt printer', category=printers, brand='Durapos',
            short='80mm thermal receipt printer, auto-cutter, USB + Ethernet.',
            long_desc=(
                'DPT-201 supports ESC/POS and OPOS/JavaPOS drivers. Auto-cutter is partial; '
                'paper-near indicator via USB status. Cash drawer RJ11 port included.'
            ),
            mpn='DPT-201-ETH', upc='843849010019',
            lead_time_text='2–5 business days from distributor stock',
            purchase=Decimal('175.00'), list_price=Decimal('289.00'), warranty=24, fetch_image=True,
        )
        disp_usb = p('DISP-USB-101',
            name='10.1" USB customer display (capacitive touch)', category=displays, brand='Generic OEM',
            short='USB-powered pole or VESA customer-facing display; 1280×800, PCAP touch.',
            upc='843849020033', lead_time_text='3–5 business days',
            purchase=Decimal('95.00'), list_price=Decimal('169.00'), warranty=12,
            length=Decimal('246'), width=Decimal('164'), height=Decimal('18'),
            w_net=Decimal('620'), fetch_image=True,
        )
        hp_eol = p('HP-ENGAGE-ONE-PRIME',
            name='HP Engage One Prime (legacy) all-in-one POS', category=terminals, brand='HP',
            short='End-of-life all-in-one - stock only for existing installed base spares.',
            long_desc='Use for like-for-like replacements where the customer standardises on this chassis.',
            status=ProductStatus.END_OF_LIFE, mpn='Engage-One-Prime-EOL', upc='889894123456',
            lead_time_text='EOL - remaining stock only; confirm availability before quoting',
            purchase=Decimal('220.00'), list_price=Decimal('399.00'), warranty=0,
            maintenance='EOL - advise customer migration path', serial_req=True,
            asset_type=AssetType.SOLD, fetch_image=True,
        )
        minipc = p('SYS-MINIPC-I5',
            name='Industrial mini PC - Intel Core i5, 8GB RAM, 256GB NVMe',
            category=terminals, brand='Durapos',
            short='Fanless mini PC for POS back-office or kiosk; Windows 11 IoT ready.',
            long_desc=(
                'Fanless design for dust-heavy environments. All ports accessible from rear panel. '
                'VESA-mountable. Supports dual 4K displays via HDMI + USB-C DP Alt mode.'
            ),
            mpn='MINI-I5-8-256-W11IOT', upc='843849030044',
            lead_time_text='Typically 4 business days (build-to-order batches)',
            purchase=Decimal('410.00'), list_price=Decimal('649.00'),
            serial_req=True, warranty=36, depreciation=60,
            asset_type=AssetType.SOLD, lead_days=4, fetch_image=True,
        )
        mon_touch = p('MON-15-TOUCH',
            name='15.6" PCAP touch monitor (POS)', category=displays, brand='Elo (example)',
            short='Full HD PCAP touch display; VESA 75; USB touch interface.',
            long_desc=(
                'Glare-resistant glass, 10-touch PCAP, USB touch controller. '
                'Portrait/landscape VESA mount. For mounting on counter arm or kiosk enclosure.'
            ),
            mpn='ELO-156-PCAP', upc='843849020050', lead_time_text='5–7 business days',
            purchase=Decimal('265.00'), list_price=Decimal('429.00'), warranty=36,
            fetch_image=True,
        )
        cable = p('CAB-USB-C-A-2M',
            name='USB-C to USB-A cable, 2m', category=cables, brand='Club3D',
            short='USB 3.2 Gen1 cable for peripherals and charging (where supported).',
            upc='8713439123456', size_or_volume='2 m',
            lead_time_text='Same day dispatch when in stock',
            purchase=Decimal('3.20'), list_price=Decimal('9.95'),
            warranty=None, serial_req=False, moq=5, warehouse='C-01-22',
        )
        roll = p('ROLL-THERM-80x80',
            name='Thermal roll 80mm × 80m (BPA-free)', category=consumables, brand='OfficeBrand',
            short='Fits most 80mm thermal printers; verify core size (25/38mm) on site.',
            size_or_volume='80 mm width × 80 m length; core 25 mm',
            lead_time_text='Next-day for pallet orders; 2 days below MOQ',
            purchase=Decimal('0.42'), list_price=Decimal('1.15'),
            uom='roll', moq=20, warehouse='D-ROLL-01',
            serial_req=False, warranty=None, lead_days=2,
        )
        bundle = p('BUNDLE-WKP-BASIC',
            name='Basic POS workstation bundle', category=bundles, brand='Workshop',
            short='Mini PC + 15.6" touch monitor + Bluetooth scanner - quoted as one SKU.',
            long_desc='Components ship together; serial numbers captured per line on delivery.',
            upc='843849099001',
            lead_time_text='Ships when all components available - usually within 5 business days',
            purchase=Decimal('733.00'), list_price=Decimal('1149.00'),
            discount_group=dg_partner, serial_req=True, warranty=36, lead_days=5,
            fetch_image=True,
        )
        p('SRVC-ONSITE-DAY',
            name='On-site installation & configuration (per day)', category=hardware,
            brand='Workshop Services',
            short='Travel time billed separately; includes go-live checklist and handover.',
            status=ProductStatus.DRAFT, purchase=None, list_price=Decimal('650.00'),
            inventory_tracked=False, warehouse='', warranty=None, serial_req=False,
            lead_time_days=None, lead_time_text='By agreement',
        )
        p('LEGACY-PINPAD-X',
            name='Legacy PIN pad model X (discontinued)', category=hardware, brand='Generic',
            short='No longer orderable - reference only.',
            status=ProductStatus.UNAVAILABLE, purchase=None, list_price=None,
            inventory_tracked=False,
        )

        # ── Price tiers ────────────────────────────────────────────────────────
        for min_q, max_q, price in [(1, 9, '749.00'), (10, 49, '699.00'), (50, None, '659.00')]:
            ProductPriceTier.objects.update_or_create(
                product=mt93, min_quantity=min_q,
                defaults={'max_quantity': max_q, 'unit_price': Decimal(price)},
            )
        for min_q, max_q, price in [(1, 4, '89.00'), (5, 19, '79.00'), (20, None, '69.00')]:
            ProductPriceTier.objects.update_or_create(
                product=hr15, min_quantity=min_q,
                defaults={'max_quantity': max_q, 'unit_price': Decimal(price)},
            )
        ProductPriceTier.objects.update_or_create(
            product=roll, min_quantity=100,
            defaults={'max_quantity': None, 'unit_price': Decimal('0.98')},
        )

        # ── BOM ────────────────────────────────────────────────────────────────
        for component in [minipc, mon_touch, hr22]:
            ProductBOMLine.objects.update_or_create(
                bundle_product=bundle, component_product=component,
                defaults={'quantity': Decimal('1')},
            )

        # ── Product relations ──────────────────────────────────────────────────
        for from_p, to_p, rtype, order in [
            (mt93,    cable,    ProductRelationType.ACCESSORY,   10),
            (mt93,    roll,     ProductRelationType.ACCESSORY,   20),
            (mt93,    hr22,     ProductRelationType.ACCESSORY,   30),
            (boca,    durapos,  ProductRelationType.ALTERNATIVE,  0),
            (hr15,    hr22,     ProductRelationType.UPSELL,       0),
            (minipc,  cable,    ProductRelationType.ACCESSORY,    0),
            (durapos, roll,     ProductRelationType.ACCESSORY,    0),
            (hp_eol,  minipc,   ProductRelationType.REPLACEMENT,  0),
            (hp_eol,  mon_touch,ProductRelationType.REPLACEMENT,  1),
        ]:
            ProductRelation.objects.update_or_create(
                from_product=from_p, to_product=to_p, relation_type=rtype,
                defaults={'sort_order': order},
            )

        # ── Demo documents ─────────────────────────────────────────────────────
        for prod, doc_type, title, fname in [
            (mt93,    ProductDocumentType.DATASHEET,     'MT93 Falcon - spec sheet (demo)',     'mt93-datasheet-demo.txt'),
            (mt93,    ProductDocumentType.MANUAL,        'MT93 - quick start guide (demo)',     'mt93-quickstart-demo.txt'),
            (mt93,    ProductDocumentType.CERTIFICATION, 'MT93 - CE / RED declaration (demo)', 'mt93-ce-demo.txt'),
            (boca,    ProductDocumentType.DATASHEET,     'Lemur-X - technical summary (demo)', 'lemur-x-datasheet-demo.txt'),
            (durapos, ProductDocumentType.DATASHEET,     'DPT-201 - specifications (demo)',    'dpt201-datasheet-demo.txt'),
            (minipc,  ProductDocumentType.CERTIFICATION, 'Mini PC - CE declaration (demo)',    'minipc-ce-demo.txt'),
        ]:
            ProductDocument.objects.update_or_create(
                product=prod, title=title,
                defaults={'document_type': doc_type,
                          'file': ContentFile(_DEMO_DOC_BODY, name=fname)},
            )

        # ── Technical specs ────────────────────────────────────────────────────
        ProductITSpec.objects.update_or_create(product=mt93, defaults={
            'operating_system': 'Android 13 (GMS) - enterprise lifecycle per vendor program',
            'cpu': 'Qualcomm octa-core (variant per MT93 revision)',
            'ram': '4 GB LPDDR4', 'storage': '64 GB eMMC',
        })
        ProductConnectivitySpec.objects.update_or_create(product=mt93, defaults={
            'io_ports': '1× USB-C (OTG/charging), 1× USB-A host, 1× nano-SIM, charging contacts',
            'wireless': 'Wi-Fi 6 (802.11ax), Bluetooth 5.2, NFC (HCE), 4G LTE Cat.6',
        })
        ProductScannerSpec.objects.update_or_create(product=mt93, defaults={
            'scan_engine': '2D CMOS imager (high density, mobile screen friendly)',
            'drop_spec': '1.5 m to concrete (with protective boot - verify SKU variant)',
            'ip_rating': 'IP65', 'battery_mah': 5000, 'battery_hours': Decimal('10.00'),
        })
        ProductScannerSpec.objects.update_or_create(product=hr15, defaults={
            'scan_engine': '2D CMOS imager', 'drop_spec': '1.2 m to concrete',
            'ip_rating': 'IP42', 'battery_mah': None, 'battery_hours': None,
        })
        ProductConnectivitySpec.objects.update_or_create(product=hr15, defaults={
            'io_ports': 'USB-A captive cable (~1.8 m); HID keyboard wedge - bus powered',
            'wireless': 'N/A (wired USB)',
        })
        ProductConnectivitySpec.objects.update_or_create(product=hr22, defaults={
            'io_ports': 'Charging cradle: USB-C (data + charge); optional pistol grip',
            'wireless': 'Bluetooth 5.0 (SPP/HID); batch mode with offline buffer',
        })
        ProductScannerSpec.objects.update_or_create(product=hr22, defaults={
            'scan_engine': '2D CMOS imager (high motion tolerance)',
            'drop_spec': '1.5 m to concrete', 'ip_rating': 'IP42',
            'battery_mah': 3200, 'battery_hours': Decimal('12.00'),
        })
        ProductConnectivitySpec.objects.update_or_create(product=boca, defaults={
            'io_ports': 'USB-B device, DE-9 RS232; DC barrel jack for external PSU',
            'wireless': 'N/A',
        })
        ProductPrinterSpec.objects.update_or_create(product=boca, defaults={
            'print_technology': 'Direct thermal', 'print_resolution': '300 dpi',
            'print_width': '80 mm (max); ticket templates vary by venue',
            'cutter_type': 'Optional auto-cutter (factory option)',
        })
        ProductConnectivitySpec.objects.update_or_create(product=durapos, defaults={
            'io_ports': 'USB-B device, RJ45 Ethernet; cash drawer kick-out (RJ11)',
            'wireless': 'N/A (optional Wi-Fi SKU not in this demo)',
        })
        ProductPrinterSpec.objects.update_or_create(product=durapos, defaults={
            'print_technology': 'Direct thermal', 'print_resolution': '203 dpi',
            'print_width': '80 mm', 'cutter_type': 'Auto-cutter',
        })
        ProductDisplaySpec.objects.update_or_create(product=disp_usb, defaults={
            'diagonal': '10.1 inch', 'resolution': '1280×800',
            'touchscreen_type': TouchscreenType.CAPACITIVE,
        })
        ProductDisplaySpec.objects.update_or_create(product=mon_touch, defaults={
            'diagonal': '15.6 inch', 'resolution': '1920×1080 (Full HD)',
            'touchscreen_type': TouchscreenType.CAPACITIVE,
        })
        ProductITSpec.objects.update_or_create(product=minipc, defaults={
            'operating_system': 'Windows 11 IoT Enterprise LTSC (licence excluded unless quoted)',
            'cpu': 'Intel Core i5-1145G7', 'ram': '8 GB DDR4', 'storage': '256 GB NVMe SSD',
        })
        ProductConnectivitySpec.objects.update_or_create(product=minipc, defaults={
            'io_ports': '4× USB-A 3.2, 1× USB-C (DP Alt), 2× RJ45, 1× HDMI 2.0',
            'wireless': 'Intel AX201 Wi-Fi 6, Bluetooth 5.1',
        })
        ProductITSpec.objects.update_or_create(product=hp_eol, defaults={
            'operating_system': 'Windows 10 IoT Enterprise (frozen baseline)',
            'cpu': 'Intel embedded platform (generation varies per unit)',
            'ram': '4 GB / 8 GB (configuration dependent)', 'storage': '128 GB SSD',
        })

        self.stdout.write(
            f'    {ProductCategory.objects.count()} categories, '
            f'{Product.objects.count()} products, '
            f'{ProductImage.objects.count()} images'
        )

    # ── RELATIONS ──────────────────────────────────────────────────────────────

    def _seed_relations(self) -> None:
        self.stdout.write('  Seeding relations…')

        strategic, _ = OrganizationLinkType.objects.update_or_create(
            name='Strategic partnership',
            defaults={'description': 'Long-term commercial alignment, joint go-to-market, or preferred supplier status.'},
        )
        logistics, _ = OrganizationLinkType.objects.update_or_create(
            name='Logistics provider',
            defaults={'description': 'Handles warehousing, fulfilment, or transport between parties.'},
        )
        integrator, _ = OrganizationLinkType.objects.update_or_create(
            name='Systems integrator',
            defaults={'description': 'Implements or supports solutions using hardware/software from the linked organization.'},
        )

        cat_objs = {}
        for code, label in OrganizationCategory.choices:
            ct, _ = OrganizationCategoryTag.objects.get_or_create(code=code, defaults={'label': label})
            if ct.label != label:
                ct.label = label; ct.save(update_fields=['label'])
            cat_objs[code] = ct

        def org(key, name, *, parent=None, kind=OrganizationUnitKind.LEGAL_ENTITY,
                primary_cat=None, categories=(), **defaults):
            obj, _ = Organization.objects.get_or_create(id=_rel_uuid(key), name=name, defaults=defaults)
            obj.unit_kind = kind
            obj.parent = parent
            if primary_cat:
                obj.primary_category = cat_objs[primary_cat]
            obj.save(update_fields=['unit_kind', 'parent', 'primary_category'])
            obj.categories.set([cat_objs[c] for c in categories])
            return obj

        # ── Organizations ──────────────────────────────────────────────────────

        nova = org('org:nova-retail-solutions', 'Nova Retail Solutions B.V.',
            kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.INTERNAL,
            categories=[OrganizationCategory.PARTNER],
            legal_name='Nova Retail Solutions B.V.',
            industry='Retail technology / systems integration',
            website='https://nova.example',
            tax_id_vat='NL999999999B01', registration_number='KvK 12345678',
            notes='Internal legal entity (demo).',
        )
        org('org:nova:operations-nl', 'Operations (NL)',
            parent=nova, kind=OrganizationUnitKind.DEPARTMENT,
            notes='Service delivery + warehousing.',
        )
        org('org:nova:sales-benelux', 'Sales (Benelux)',
            parent=nova, kind=OrganizationUnitKind.DEPARTMENT,
            notes='Account management and quoting.',
        )

        customer = org('org:stadium-events-group', 'Stadium Events Group',
            kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.CUSTOMER,
            categories=[OrganizationCategory.CUSTOMER, OrganizationCategory.STRATEGIC],
            legal_name='Stadium Events Group N.V.',
            industry='Events / venue operations',
            website='https://stadiumevents.example',
            tax_id_vat='NL111111111B01', registration_number='KvK 87654321',
            notes='Venue operator with ticketing and access control needs. Framework agreement active.',
        )
        seg_it = org('org:stadium-events-group:it', 'IT Department',
            parent=customer, kind=OrganizationUnitKind.DEPARTMENT,
            notes='Owns device lifecycle, MDM, and security reviews.',
        )
        seg_boxoffice = org('org:stadium-events-group:box-office', 'Box Office',
            parent=customer, kind=OrganizationUnitKind.DEPARTMENT,
            notes='Ticket printers and peripheral infrastructure.',
        )

        prospect = org('org:metro-arena-prospect', 'Metro Arena N.V.',
            kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.PROSPECT,
            categories=[OrganizationCategory.PROSPECT],
            legal_name='Metro Arena N.V.',
            industry='Sports & entertainment venue',
            website='https://metroarena.example',
            notes='Evaluating mobile POS and access control for concourse upgrade - RFP expected Q3.',
        )

        qsr = org('org:quickserve-restaurants', 'QuickServe Restaurant Group',
            kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.CUSTOMER,
            categories=[OrganizationCategory.CUSTOMER],
            legal_name='QuickServe Restaurant Group B.V.',
            industry='Food service / QSR',
            website='https://quickserve.example',
            tax_id_vat='NL222222222B01', registration_number='KvK 22334455',
            notes='84 outlets across NL/BE. Annual POS hardware refresh cycle (Q1). Standing order for consumables.',
        )

        vendor = org('org:scantech-distribution', 'ScanTech Distribution',
            kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.SUPPLIER,
            categories=[OrganizationCategory.SUPPLIER],
            legal_name='ScanTech Distribution GmbH',
            industry='IT distribution', website='https://scantech.example',
            tax_id_vat='DE999999999', registration_number='HRB 98765',
            notes='Primary vendor for handheld terminals and scanners.',
        )
        vendor_nl = org('org:scantech-distribution:benelux-sales', 'Benelux Sales Office',
            parent=vendor, kind=OrganizationUnitKind.BRANCH,
        )

        rvta = org('org:rvta', 'Retail Venue Technology Alliance',
            kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.STRATEGIC,
            categories=[OrganizationCategory.STRATEGIC],
            legal_name='Retail Venue Technology Alliance (RVTA)',
            industry='Industry association / standards body',
            website='https://rvta.example',
            notes=(
                'Sets POS interoperability standards and publishes annual venue-tech benchmarks. '
                'Tracked for market intelligence and event invitations.'
            ),
        )

        # ── Org links ──────────────────────────────────────────────────────────
        OrganizationLink.objects.update_or_create(
            from_organization=nova, to_organization=vendor, link_type=integrator,
            defaults={'start_date': date(2018, 3, 1),
                      'notes': 'Nova specifies and supports ScanTech hardware on retail projects.'},
        )
        OrganizationLink.objects.update_or_create(
            from_organization=customer, to_organization=nova, link_type=strategic,
            defaults={'start_date': date(2020, 9, 15),
                      'notes': 'Framework for venue POS refreshes and event-season surge capacity.'},
        )
        OrganizationLink.objects.update_or_create(
            from_organization=vendor, to_organization=customer, link_type=logistics,
            defaults={'start_date': date(2019, 6, 1),
                      'notes': 'Drop-ship and RMA logistics for handheld estate.'},
        )
        OrganizationLink.objects.update_or_create(
            from_organization=qsr, to_organization=nova, link_type=strategic,
            defaults={'start_date': date(2023, 1, 15),
                      'notes': 'Preferred hardware partner for annual refresh program.'},
        )

        # ── People ─────────────────────────────────────────────────────────────
        def person(key, first, last, **defaults):
            obj, _ = Person.objects.update_or_create(
                id=_rel_uuid(key),
                defaults=dict(first_name=first, last_name=last, **defaults),
            )
            return obj

        alice = person('person:alice-van-dijk', 'Alice', 'van Dijk',
            title_prefix='Ms.', date_of_birth=date(1988, 3, 12), pronouns='she/her',
            bio='Runs box-office operations and seasonal staffing for major events.',
            notes='Ticketing program owner. Key contact for printer hardware.',
        )
        bob = person('person:bob-janssen', 'Bob', 'Janssen',
            title_prefix='Mr.', date_of_birth=date(1981, 11, 2), pronouns='he/him',
            bio='Responsible for endpoint security, MDM, and vendor risk reviews.',
            notes='IT security lead. Signs off on new device models.',
        )
        chloe = person('person:chloe-de-vries', 'Chloë', 'de Vries',
            title_prefix='Ms.', date_of_birth=date(1992, 7, 21),
            bio='Owns hardware tenders and framework agreements for the venue group.',
            notes='Procurement contact - prefers formal quotation on letterhead.',
        )
        marc = person('person:marc-keller', 'Marc', 'Keller',
            title_prefix='Mr.', date_of_birth=date(1979, 5, 30), pronouns='he/him',
            bio='Covers Benelux accounts for mobile computing and scanning lines at ScanTech.',
            notes='Vendor account manager. Good escalation path for stock issues.',
        )
        diana = person('person:diana-hoek', 'Diana', 'Hoek',
            title_prefix='Dr.', pronouns='she/her',
            bio=(
                'Independent venue-technology consultant and RVTA committee member. '
                'Advises Stadium Events Group on long-range POS roadmap.'
            ),
            notes='Keep looped in on roadmap calls; influences RVTA benchmark criteria.',
        )
        elena = person('person:elena-martens', 'Elena', 'Martens',
            title_prefix='Ms.', date_of_birth=date(1990, 4, 5), pronouns='she/her',
            bio='IT director at QuickServe Restaurant Group. Owns the annual POS refresh budget.',
            notes='Decision maker for QSR hardware. Annual review in January.',
        )
        frank = person('person:frank-willems', 'Frank', 'Willems',
            title_prefix='Mr.', date_of_birth=date(1975, 8, 19),
            bio='Operations manager at QuickServe. Oversees rollout logistics and field technicians.',
            notes='Co-ordinate with Frank for delivery scheduling at outlets.',
        )
        greta = person('person:greta-vogel', 'Greta', 'Vogel',
            title_prefix='Ms.', date_of_birth=date(1985, 2, 28), pronouns='she/her',
            bio='Head of IT infrastructure at Metro Arena. Evaluating handheld and fixed-mount options.',
            notes='Primary technical contact for Metro Arena RFP.',
        )

        # ── Affiliations ───────────────────────────────────────────────────────
        for p_obj, o_obj, title, start, end, primary, notes in [
            (alice,  seg_boxoffice, 'Box Office Manager',              date(2022, 4, 1),  None,             True,  ''),
            (alice,  rvta,          'Working Group Delegate',          date(2019, 3, 1),  date(2022, 3, 31),False,
             'Delegate during the ticketing interoperability WG - ended when she joined SEG full-time.'),
            (bob,    seg_it,        'IT Security Lead',                date(2021, 9, 1),  None,             True,  ''),
            (chloe,  customer,      'Procurement Specialist',          date(2023, 2, 1),  None,             True,  ''),
            (marc,   vendor_nl,     'Account Manager',                 date(2020, 1, 1),  None,             True,  ''),
            (diana,  rvta,          'Standards Committee Member',      date(2021, 1, 1),  None,             True,  ''),
            (diana,  customer,      'IT Strategy Advisor (freelance)', date(2023, 9, 1),  None,             False, ''),
            (elena,  qsr,           'IT Director',                     date(2019, 6, 1),  None,             True,  ''),
            (frank,  qsr,           'Operations Manager',              date(2017, 3, 1),  None,             True,  ''),
            (greta,  prospect,      'Head of IT Infrastructure',       date(2020, 11, 1), None,             True,  ''),
        ]:
            Affiliation.objects.update_or_create(
                person=p_obj, organization=o_obj,
                defaults={'job_title': title, 'start_date': start, 'end_date': end,
                          'is_primary': primary, 'notes': notes},
            )

        SpecialEvent.objects.update_or_create(person=alice, name='Dietary preference',
            defaults={'event_date': None, 'notes': 'Vegetarian - avoid fish and meat.'},
        )
        SpecialEvent.objects.update_or_create(person=bob, name='Wedding anniversary',
            defaults={'event_date': date(2019, 6, 14), 'notes': ''},
        )
        SpecialEvent.objects.update_or_create(person=elena, name='Company anniversary',
            defaults={'event_date': date(2019, 6, 1), 'notes': '5 years at QuickServe (June 2024).'},
        )

        person_ct = ContentType.objects.get_for_model(Person)
        org_ct    = ContentType.objects.get_for_model(Organization)

        # ── People communications ──────────────────────────────────────────────
        for p_obj, ctype, value, label, primary in [
            (alice, CommunicationType.EMAIL, 'alice.vandijk@stadiumevents.example',  'Work',    True),
            (alice, CommunicationType.PHONE, '+31 20 555 0101',                      'Direct',  True),
            (bob,   CommunicationType.EMAIL, 'bob.janssen@stadiumevents.example',    'Work',    True),
            (bob,   CommunicationType.PHONE, '+31 20 555 0102',                      'Mobile',  False),
            (chloe, CommunicationType.EMAIL, 'procurement@stadiumevents.example',    'Shared',  True),
            (chloe, CommunicationType.PHONE, '+31 20 555 0120',                      'Desk',    False),
            (marc,  CommunicationType.EMAIL, 'marc.keller@scantech.example',         'Work',    True),
            (marc,  CommunicationType.PHONE, '+49 211 555 0142',                     'Mobile',  True),
            (diana, CommunicationType.EMAIL, 'diana.hoek@consultant.example',        'Direct',  True),
            (diana, CommunicationType.PHONE, '+31 6 555 0199',                       'Mobile',  True),
            (elena, CommunicationType.EMAIL, 'elena.martens@quickserve.example',     'Work',    True),
            (elena, CommunicationType.PHONE, '+31 10 555 0301',                      'Direct',  True),
            (frank, CommunicationType.EMAIL, 'frank.willems@quickserve.example',     'Work',    True),
            (frank, CommunicationType.PHONE, '+31 10 555 0302',                      'Mobile',  True),
            (greta, CommunicationType.EMAIL, 'greta.vogel@metroarena.example',       'Work',    True),
            (greta, CommunicationType.PHONE, '+31 20 555 0500',                      'Desk',    False),
        ]:
            _comm(person_ct, p_obj.id, comm_type=ctype, value=value, label=label, primary=primary)

        # ── Org communications ─────────────────────────────────────────────────
        for o_obj, ctype, value, label, primary in [
            (customer, CommunicationType.PHONE, '+31 20 555 0000',             'Main',      True),
            (customer, CommunicationType.EMAIL, 'info@stadiumevents.example',  'General',   True),
            (vendor,   CommunicationType.EMAIL, 'sales@scantech.example',      'Sales',     True),
            (vendor,   CommunicationType.PHONE, '+49 211 555 0200',            'HQ',        True),
            (nova,     CommunicationType.EMAIL, 'hello@nova.example',          'General',   True),
            (nova,     CommunicationType.PHONE, '+31 20 555 0900',             'Reception', True),
            (rvta,     CommunicationType.EMAIL, 'info@rvta.example',           'General',   True),
            (qsr,      CommunicationType.PHONE, '+31 10 555 0300',             'HQ',        True),
            (qsr,      CommunicationType.EMAIL, 'it@quickserve.example',       'IT',        True),
            (prospect, CommunicationType.EMAIL, 'info@metroarena.example',     'General',   True),
        ]:
            _comm(org_ct, o_obj.id, comm_type=ctype, value=value, label=label, primary=primary)

        # ── Addresses ──────────────────────────────────────────────────────────
        _addr(org_ct, customer.id, address_type=AddressType.VISITING,
              street='Arena Boulevard 1', zipcode='1101 AX', city='Amsterdam',
              label='HQ', street2='Tower A', state_province='North Holland')
        _addr(org_ct, customer.id, address_type=AddressType.BILLING,
              street='Postbus 1234', zipcode='1000 AA', city='Amsterdam',
              label='Billing', street2='Finance department')
        _addr(org_ct, customer.id, address_type=AddressType.SHIPPING,
              street='Logistiekweg 50', zipcode='1111 AB', city='Amsterdam',
              label='Warehouse / delivery', street2='Loading bay 3')
        _addr(org_ct, vendor.id, address_type=AddressType.VISITING,
              street='Industriestraße 20', zipcode='40210', city='Düsseldorf',
              country='Germany', label='HQ', street2='Building C',
              state_province='North Rhine-Westphalia')
        _addr(org_ct, nova.id, address_type=AddressType.VISITING,
              street='Science Park 402', zipcode='1098 XH', city='Amsterdam',
              label='Office', street2='Unit 12B')
        _addr(org_ct, rvta.id, address_type=AddressType.VISITING,
              street='Herengracht 182', zipcode='1016 BR', city='Amsterdam', label='Secretariat')
        _addr(org_ct, qsr.id, address_type=AddressType.VISITING,
              street='Rijnhaven 57', zipcode='3011 TG', city='Rotterdam',
              label='HQ', state_province='South Holland')
        _addr(org_ct, qsr.id, address_type=AddressType.BILLING,
              street='Postbus 5678', zipcode='3000 AA', city='Rotterdam',
              label='Billing / Accounts Payable')
        _addr(org_ct, prospect.id, address_type=AddressType.VISITING,
              street='Stadsdeelweg 100', zipcode='1031 HW', city='Amsterdam',
              label='Arena HQ', state_province='North Holland')

        # ── Social profiles ────────────────────────────────────────────────────
        for o_obj, platform, url, handle in [
            (customer, 'LinkedIn', 'https://www.linkedin.com/company/stadium-events-group/',         'stadium-events-group'),
            (vendor,   'LinkedIn', 'https://www.linkedin.com/company/scantech-distribution-demo/',   'scantech-distribution'),
            (nova,     'LinkedIn', 'https://www.linkedin.com/company/nova-retail-solutions-demo/',   'nova-retail-solutions'),
            (qsr,      'LinkedIn', 'https://www.linkedin.com/company/quickserve-restaurant-group/',  'quickserve-restaurants'),
        ]:
            SocialProfile.objects.update_or_create(
                content_type=org_ct, object_id=o_obj.id, platform=platform,
                defaults={'url': url, 'handle': handle},
            )
        SocialProfile.objects.update_or_create(
            content_type=person_ct, object_id=diana.id, platform='LinkedIn',
            defaults={'url': 'https://www.linkedin.com/in/diana-hoek-demo/', 'handle': 'diana-hoek'},
        )

        self.stdout.write(
            f'    {Organization.objects.count()} organizations, '
            f'{Person.objects.count()} contacts, '
            f'{Affiliation.objects.count()} affiliations'
        )

    # ── ASSETS ─────────────────────────────────────────────────────────────────

    def _seed_assets(self) -> None:
        self.stdout.write('  Seeding assets…')
        User = get_user_model()
        user = User.objects.filter(is_superuser=True).first() or User.objects.order_by('id').first()
        if not user:
            self.stdout.write(self.style.WARNING('    No user found - skipping assets.'))
            return

        customer = Organization.objects.filter(pk=_rel_uuid('org:stadium-events-group')).first()
        qsr      = Organization.objects.filter(pk=_rel_uuid('org:quickserve-restaurants')).first()
        if not customer or not qsr:
            self.stdout.write(self.style.WARNING('    Demo organisations missing - run relations first.'))
            return

        def prod(sku): return Product.objects.filter(sku=sku).first()

        mt93      = prod('NEW-MT93-4G')
        dpt201    = prod('DURAPOS-DPT201')
        minipc    = prod('SYS-MINIPC-I5')
        mon_touch = prod('MON-15-TOUCH')
        hr15      = prod('NEW-HR15-W')
        boca      = prod('BOCA-LEMUR-X')

        # ── Recall campaign ────────────────────────────────────────────────────
        recall, _ = RecallCampaign.objects.get_or_create(
            pk=_ast_uuid('recall:demo-thermal-2026'),
            defaults={
                'reference':          _REFS['recall_1'],
                'title':              'Demo: thermal printhead inspection (fictional)',
                'description':        'Illustrative recall for demo UI - not a real manufacturer notice.',
                'remedy_description': 'Inspect printhead; replace if streaking persists after cleaning.',
                'product':            dpt201,
                'announced_date':     date(2026, 1, 15),
                'is_active':          True,
                'created_by':         user,
            },
        )

        def make_asset(key, org, product, serial, tag, purchase_dt, install_dt,
                       warranty_end, eol_dt, status, location, notes, events):
            asset, _ = Asset.objects.update_or_create(
                pk=_ast_uuid(key),
                defaults={
                    'organization': org, 'product': product, 'name': '',
                    'serial_number': serial, 'asset_tag': tag,
                    'purchase_date': purchase_dt, 'installation_date': install_dt,
                    'warranty_end_date': warranty_end,
                    'expected_end_of_life_date': eol_dt,
                    'status': status, 'location_note': location,
                    'notes': notes, 'created_by': user,
                },
            )
            AssetOrganizationTransfer.objects.get_or_create(
                pk=_ast_uuid(f'xfer:{key}:initial'),
                defaults={'asset': asset, 'from_organization': None,
                          'to_organization': org, 'transferred_by': user, 'note': ''},
            )
            for ev_key, ev_type, ev_title, ev_desc, ev_date in events:
                AssetEvent.objects.get_or_create(
                    pk=_ast_uuid(f'event:{key}:{ev_key}'),
                    defaults={
                        'asset': asset, 'event_type': ev_type,
                        'title': ev_title, 'description': ev_desc,
                        'occurred_on': ev_date, 'created_by': user,
                    },
                )
            return asset

        # Stadium Events Group assets
        a_dpt_01 = make_asset(
            'asset:seg:dpt201-01', customer, dpt201,
            'DPT-DEMO-SN-0001', 'SEG-POS-R1-04',
            date(2024, 6, 1), date(2024, 6, 10), date(2026, 6, 1), date(2029, 6, 1),
            AssetStatus.IN_SERVICE, 'Box office - lane 4',
            'Demo asset: maintenance plans and replacement scenarios.',
            [
                ('install',   AssetEventType.INSTALLATION, 'Installed and configured',          'Ethernet + USB failover tested.',                              date(2024, 6, 10)),
                ('clean-jan', AssetEventType.REPAIR,       'Annual cleaning - printhead check', 'Light streaking noted; printhead cleaned; monitoring.',         date(2025, 1, 20)),
                ('recall-chk',AssetEventType.INSPECTION,  'Recall check in progress',          'Waiting for tech availability to perform inspection.',           date(2026, 2, 5)),
            ],
        )
        make_asset(
            'asset:seg:dpt201-02', customer, dpt201,
            'DPT-DEMO-SN-0002', 'SEG-POS-R1-05',
            date(2024, 6, 1), date(2024, 6, 10), date(2026, 6, 1), date(2029, 6, 1),
            AssetStatus.IN_SERVICE, 'Box office - lane 5',
            '',
            [
                ('install',   AssetEventType.INSTALLATION, 'Installed and configured', 'Setup identical to lane 4 unit.', date(2024, 6, 10)),
            ],
        )
        a_minipc_01 = make_asset(
            'asset:seg:minipc-01', customer, minipc,
            'MINI-DEMO-SN-0001', 'SEG-BK-01',
            date(2026, 3, 14), date(2026, 3, 14), date(2029, 3, 14), date(2031, 3, 14),
            AssetStatus.IN_SERVICE, 'Back office - server shelf A',
            'Installed as part of SO-DEMO-0001 deployment.',
            [
                ('install', AssetEventType.INSTALLATION, 'POS back-office compute installed',
                 'Mini PC deployed alongside 15.6" touch monitor.', date(2026, 3, 14)),
            ],
        )
        make_asset(
            'asset:seg:hp-eol-01', customer, prod('HP-ENGAGE-ONE-PRIME'),
            'HP-DEMO-SN-0001', 'SEG-KIOSK-02',
            date(2019, 4, 1), date(2019, 4, 10), None, date(2026, 12, 31),
            AssetStatus.END_OF_LIFE_NEAR, 'Ticketing kiosk - concourse B',
            'EOL device - flagged for replacement in MJOP 2027.',
            [
                ('install',  AssetEventType.INSTALLATION,   'Installed',          '', date(2019, 4, 10)),
                ('inspect',  AssetEventType.INSPECTION,     'Annual check',       'Screen calibration needed; power supply warm.', date(2025, 3, 1)),
                ('eol-warn', AssetEventType.RECOMMENDATION, 'EOL migration flag', 'Recommend replacement with Mini PC + touch monitor.', date(2025, 9, 1)),
            ],
        )

        # QuickServe Restaurant Group assets
        a_hr15_qsr = make_asset(
            'asset:qsr:hr15-01', qsr, hr15,
            'HR15-DEMO-SN-0101', 'QSR-SCAN-001',
            date(2025, 2, 1), date(2025, 2, 5), date(2027, 2, 1), date(2030, 2, 1),
            AssetStatus.IN_SERVICE, 'Rotterdam HQ - front counter',
            'Pilot unit for QSR fixed-scanner deployment.',
            [
                ('install', AssetEventType.INSTALLATION, 'Pilot scanner installed at HQ', '', date(2025, 2, 5)),
            ],
        )
        make_asset(
            'asset:qsr:dpt201-01', qsr, dpt201,
            'DPT-DEMO-SN-0101', 'QSR-PRINT-001',
            date(2025, 2, 1), date(2025, 2, 5), date(2027, 2, 1), date(2030, 2, 1),
            AssetStatus.IN_SERVICE, 'Rotterdam HQ - till 1',
            'Receipt printer - part of QSR pilot.',
            [
                ('install', AssetEventType.INSTALLATION, 'Printer installed', 'Configured for ESC/POS.', date(2025, 2, 5)),
                ('paper',   AssetEventType.NOTE,         'Paper jam report',  'Staff resolved; no damage.', date(2025, 8, 12)),
            ],
        )

        # ── Recall links ───────────────────────────────────────────────────────
        AssetRecallLink.objects.update_or_create(
            recall_campaign=recall, asset=a_dpt_01,
            defaults={'status': AssetRecallStatus.ACTION_REQUIRED,
                      'notes': 'Schedule on-site check with next maintenance visit.'},
        )

        # ── Replacement recommendations ────────────────────────────────────────
        if minipc:
            AssetReplacementRecommendation.objects.update_or_create(
                pk=_ast_uuid('rec:seg:hp-eol-to-minipc'),
                defaults={
                    'asset': Asset.objects.filter(pk=_ast_uuid('asset:seg:hp-eol-01')).first(),
                    'suggested_product': minipc,
                    'rationale': (
                        'HP Engage One Prime is EOL - recommend industrial mini PC with separate '
                        '15.6" touch monitor for modern compute baseline and longer lifecycle.'
                    ),
                    'priority':   ReplacementPriority.HIGH,
                    'status':     ReplacementRecommendationStatus.OPEN,
                    'created_by': user,
                },
            )

        # ── Maintenance plan ───────────────────────────────────────────────────
        plan, _ = MaintenancePlan.objects.get_or_create(
            pk=_ast_uuid('mjop:seg:2026-2030'),
            defaults={
                'reference':   _REFS['mjop_1'],
                'organization': customer,
                'name':        'Stadium Events - infrastructure maintenance plan 2026–2030 (demo)',
                'valid_from':  date(2026, 1, 1),
                'valid_until': date(2030, 12, 31),
                'status':      MaintenancePlanStatus.ACTIVE,
                'notes':       'Five-year maintenance outlook covering POS estate. Mix of routine maintenance and promoted replacement rows.',
                'created_by':  user,
            },
        )
        hp_eol_asset = Asset.objects.filter(pk=_ast_uuid('asset:seg:hp-eol-01')).first()
        for pk_key, year, sort, title, desc, asset_obj, repl_prod, promoted, cost_note, line_status in [
            ('line:2026:dpt-clean',  2026, 1, 'Receipt printer annual service (all lanes)',
             'Clean platen + cutter, check paper path, update firmware.',
             a_dpt_01, None, False, 'Approx. €200 incl. parts + travel', MaintenancePlanLineStatus.PLANNED),
            ('line:2027:dpt-clean',  2027, 1, 'Receipt printer annual service (all lanes)',
             'Same scope as 2026 visit. Assess wear on cutter blade.',
             a_dpt_01, None, False, 'Approx. €200 incl. parts + travel', MaintenancePlanLineStatus.PLANNED),
            ('line:2027:kiosk-repl', 2027, 2, 'Kiosk compute refresh (PROMOTED)',
             'HP Engage One Prime reaching EOL - replace with Mini PC + touch monitor.',
             hp_eol_asset, minipc, True, 'Budget holder approval required - use formal quote',
             MaintenancePlanLineStatus.PLANNED),
            ('line:2028:scanner',    2028, 1, 'Handheld scanner estate review',
             'Assess battery health on all MT93 units; replace worn units.',
             None, mt93, False, 'Indicative 6–8 units; TBD after survey', MaintenancePlanLineStatus.PLANNED),
            ('line:2029:pos-refresh',2029, 1, 'Full POS hardware refresh (PROMOTED)',
             'End-of-lifecycle refresh for all remaining POS compute and display hardware.',
             None, minipc, True, 'Major capital line - initiate RFP 18 months prior',
             MaintenancePlanLineStatus.PLANNED),
        ]:
            MaintenancePlanLine.objects.update_or_create(
                pk=_ast_uuid(pk_key),
                defaults={
                    'plan': plan, 'plan_year': year, 'sort_order': sort,
                    'title': title, 'description': desc,
                    'related_asset': asset_obj, 'recommended_product': repl_prod,
                    'is_promoted': promoted, 'estimated_cost_note': cost_note,
                    'line_status': line_status,
                },
            )

        self.stdout.write(
            f'    {Asset.objects.count()} assets, '
            f'{RecallCampaign.objects.count()} recall campaign, '
            f'{MaintenancePlan.objects.count()} maintenance plan'
        )

    # ── SALES ──────────────────────────────────────────────────────────────────

    def _seed_sales(self) -> None:
        self.stdout.write('  Seeding sales pipeline…')
        User = get_user_model()
        user = User.objects.filter(is_superuser=True).first() or User.objects.order_by('id').first()
        if not user:
            self.stdout.write(self.style.WARNING('    No user found - skipping sales.'))
            return

        customer = Organization.objects.filter(pk=_rel_uuid('org:stadium-events-group')).first()
        prospect = Organization.objects.filter(pk=_rel_uuid('org:metro-arena-prospect')).first()
        qsr      = Organization.objects.filter(pk=_rel_uuid('org:quickserve-restaurants')).first()
        if not customer or not prospect or not qsr:
            self.stdout.write(self.style.WARNING('    Demo organisations missing - run relations first.'))
            return

        def prod(sku): return Product.objects.filter(sku=sku).first()

        mt93      = prod('NEW-MT93-4G')
        hr22      = prod('NEW-HR22-BT')
        hr15      = prod('NEW-HR15-W')
        dpt201    = prod('DURAPOS-DPT201')
        roll      = prod('ROLL-THERM-80x80')
        minipc    = prod('SYS-MINIPC-I5')
        mon_touch = prod('MON-15-TOUCH')
        bundle    = prod('BUNDLE-WKP-BASIC')
        boca      = prod('BOCA-LEMUR-X')

        def qline(quote, product, qty, order):
            if not product: return
            data = snapshot_line_from_product(product, qty, sort_order=order)
            QuoteLine.objects.update_or_create(
                pk=_sal_uuid(f'ql:{quote.pk}:{product.sku}'),
                defaults={'quote': quote, **data},
            )

        def oline(order, product, qty, sort):
            if not product: return None
            data = snapshot_line_from_product(product, qty, sort_order=sort)
            ol, _ = OrderLine.objects.update_or_create(
                pk=_sal_uuid(f'ol:{order.pk}:{product.sku}'),
                defaults={'order': order, **data},
            )
            return ol

        def fo_line(fo, ol, wh_loc, sort):
            if not ol: return None
            fl, _ = FulfillmentOrderLine.objects.update_or_create(
                pk=_sal_uuid(f'fol:{fo.pk}:{ol.pk}'),
                defaults={
                    'fulfillment_order': fo, 'product': ol.product,
                    'product_name': ol.product_name, 'sku': ol.sku,
                    'brand': ol.brand or '', 'quantity': ol.quantity,
                    'warehouse_location': wh_loc, 'sort_order': sort,
                },
            )
            return fl

        # ────────────────────────────────────────────────────────────────────────
        # Q1 - DRAFT: Metro Arena mobile POS proposal
        # ────────────────────────────────────────────────────────────────────────
        q1, _ = Quote.objects.update_or_create(
            pk=_sal_uuid('quote:metro-arena-mobile-pos'),
            defaults={
                'reference': _REFS['q1'], 'created_by': user,
                'relation_organization': prospect, 'status': QuoteStatus.DRAFT,
                'valid_until': date(2026, 6, 30), 'internal_reference': 'CRM-MA-001',
                'notes': (
                    'Initial mobile POS proposal for Metro Arena concourse upgrade. '
                    'Quantities based on briefing call 2026-03-18. Pending final floor plan from Greta Vogel.'
                ),
            },
        )
        qline(q1, mt93, 12, 0); qline(q1, hr22, 6, 1); qline(q1, bundle, 3, 2)

        # ────────────────────────────────────────────────────────────────────────
        # Q2 - SENT: Stadium Events printer refresh
        # ────────────────────────────────────────────────────────────────────────
        q2, _ = Quote.objects.update_or_create(
            pk=_sal_uuid('quote:stadium-printer-refresh'),
            defaults={
                'reference': _REFS['q2'], 'created_by': user,
                'relation_organization': customer, 'status': QuoteStatus.SENT,
                'valid_until': date(2026, 4, 30),
                'internal_reference': 'CRM-SEG-005', 'external_reference': 'SEG-RFQ-2026-04',
                'notes': 'Printer refresh for box office lanes 1–6. Consumables on separate standing order.',
            },
        )
        qline(q2, dpt201, 6, 0); qline(q2, roll, 200, 1); qline(q2, boca, 2, 2)

        # ────────────────────────────────────────────────────────────────────────
        # Q3 - ACCEPTED (locked → SO1): Stadium Events mini PC deployment
        # ────────────────────────────────────────────────────────────────────────
        q3, _ = Quote.objects.update_or_create(
            pk=_sal_uuid('quote:stadium-minipc-deploy'),
            defaults={
                'reference': _REFS['q3'], 'created_by': user,
                'relation_organization': customer, 'status': QuoteStatus.ACCEPTED,
                'is_locked': True, 'valid_until': date(2026, 3, 31),
                'internal_reference': 'CRM-SEG-003', 'external_reference': 'SEG-PO-2026-0042',
                'notes': 'Approved by Bob Janssen (IT). PO received 2026-03-05.',
            },
        )
        qline(q3, minipc, 5, 0); qline(q3, mon_touch, 5, 1)

        # ────────────────────────────────────────────────────────────────────────
        # Q4 - DRAFT: QuickServe annual scanner order
        # ────────────────────────────────────────────────────────────────────────
        q4, _ = Quote.objects.update_or_create(
            pk=_sal_uuid('quote:qsr-scanner-refresh-2026'),
            defaults={
                'reference': _REFS['q4'], 'created_by': user,
                'relation_organization': qsr, 'status': QuoteStatus.DRAFT,
                'valid_until': date(2026, 7, 31), 'internal_reference': 'CRM-QSR-010',
                'notes': (
                    'Annual scanner refresh for 84 QSR outlets. '
                    'Pilot batch of 20 units first; Elena Martens to confirm full rollout scope.'
                ),
            },
        )
        qline(q4, hr15, 20, 0); qline(q4, roll, 500, 1)

        # ────────────────────────────────────────────────────────────────────────
        # Q5 - EXPIRED: Old Metro Arena quick scan quote
        # ────────────────────────────────────────────────────────────────────────
        q5, _ = Quote.objects.update_or_create(
            pk=_sal_uuid('quote:metro-arena-quick-scan-expired'),
            defaults={
                'reference': _REFS['q5'], 'created_by': user,
                'relation_organization': prospect, 'status': QuoteStatus.EXPIRED,
                'valid_until': date(2025, 12, 31), 'internal_reference': 'CRM-MA-000',
                'notes': 'Preliminary scope - superseded by Q-DEMO-0001 which covers full concourse.',
            },
        )
        qline(q5, hr22, 4, 0)

        # ────────────────────────────────────────────────────────────────────────
        # SO1 - FULFILLED: Mini PC deployment (from Q3)
        # Full pipeline: FO (completed) → SHO (shipped) → Shipment (delivered)
        # Invoice: partial payment
        # ────────────────────────────────────────────────────────────────────────
        so1, _ = SalesOrder.objects.update_or_create(
            pk=_sal_uuid('order:stadium-minipc-deploy'),
            defaults={
                'reference': _REFS['so1'], 'created_by': user, 'quote': q3,
                'relation_organization': customer, 'status': OrderStatus.FULFILLED,
                'notes': f'From quote {q3.reference}. {q3.notes}',
            },
        )
        ol_minipc = oline(so1, minipc, 5, 0)
        ol_mon    = oline(so1, mon_touch, 5, 1)

        fo1, _ = FulfillmentOrder.objects.update_or_create(
            pk=_sal_uuid('fo:stadium-minipc-deploy'),
            defaults={
                'reference': _REFS['fo1'], 'sales_order': so1, 'created_by': user,
                'status': FulfillmentOrderStatus.COMPLETED,
                'notes': 'Pick from shelf A-12-03 (mini PCs) and B-02-11 (monitors).',
            },
        )
        fol_minipc = fo_line(fo1, ol_minipc, 'A-12-03', 0)
        fol_mon    = fo_line(fo1, ol_mon,    'B-02-11', 1)

        sho1, _ = ShippingOrder.objects.update_or_create(
            pk=_sal_uuid('sho:stadium-minipc-deploy'),
            defaults={
                'reference': _REFS['sho1'], 'fulfillment_order': fo1, 'sales_order': so1,
                'created_by': user, 'status': ShippingOrderStatus.SHIPPED,
                'notes': 'Full order shipped in one consignment.',
            },
        )
        shol_minipc = shol_mon = None
        if fol_minipc:
            shol_minipc, _ = ShippingOrderLine.objects.update_or_create(
                pk=_sal_uuid(f'shol:{sho1.pk}:{fol_minipc.pk}'),
                defaults={'shipping_order': sho1, 'fulfillment_line': fol_minipc,
                          'quantity': fol_minipc.quantity},
            )
        if fol_mon:
            shol_mon, _ = ShippingOrderLine.objects.update_or_create(
                pk=_sal_uuid(f'shol:{sho1.pk}:{fol_mon.pk}'),
                defaults={'shipping_order': sho1, 'fulfillment_line': fol_mon,
                          'quantity': fol_mon.quantity},
            )
        sh1, _ = Shipment.objects.update_or_create(
            pk=_sal_uuid('sh:stadium-minipc-deploy'),
            defaults={
                'shipping_order': sho1, 'sequence': 1, 'carrier': 'DHL Freight',
                'tracking_number': 'JD0123456789012', 'status': ShipmentStatus.DELIVERED,
                'notes': 'Delivered 2026-03-14 - signed by B. Janssen.',
            },
        )
        for shol in [shol_minipc, shol_mon]:
            if shol:
                ShipmentLine.objects.update_or_create(
                    pk=_sal_uuid(f'shl:{sh1.pk}:{shol.pk}'),
                    defaults={'shipment': sh1, 'shipping_order_line': shol, 'quantity': shol.quantity},
                )

        inv1, _ = Invoice.objects.update_or_create(
            pk=_sal_uuid('inv:stadium-minipc-deploy'),
            defaults={
                'reference': _REFS['inv1'], 'order': so1, 'created_by': user,
                'relation_organization': customer, 'status': InvoiceStatus.ISSUED,
                'currency': 'EUR', 'due_date': date(2026, 4, 14),
            },
        )
        for i, ol in enumerate(x for x in [ol_minipc, ol_mon] if x):
            InvoiceLine.objects.update_or_create(
                pk=_sal_uuid(f'il:{inv1.pk}:{ol.pk}'),
                defaults={
                    'invoice': inv1, 'product': ol.product,
                    'product_name': ol.product_name, 'sku': ol.sku, 'brand': ol.brand or '',
                    'quantity': ol.quantity, 'unit_price': ol.unit_price,
                    'currency': ol.currency, 'line_total': ol.line_total, 'sort_order': i,
                },
            )
        inv1_total = sum(ol.line_total for ol in [ol_minipc, ol_mon] if ol)
        InvoicePayment.objects.update_or_create(
            pk=_sal_uuid('pay:stadium-minipc-50pct'),
            defaults={
                'invoice': inv1,
                'amount': (inv1_total * Decimal('0.5')).quantize(Decimal('0.01')),
                'reference_note': 'Bank transfer - 50% advance per contract terms',
                'created_by': user,
            },
        )

        # ────────────────────────────────────────────────────────────────────────
        # SO2 - CONFIRMED: Wired scanners (no quote) - fulfillment pending
        # Invoice: overdue, unpaid
        # ────────────────────────────────────────────────────────────────────────
        so2, _ = SalesOrder.objects.update_or_create(
            pk=_sal_uuid('order:stadium-scanners-foh'),
            defaults={
                'reference': _REFS['so2'], 'created_by': user, 'quote': None,
                'relation_organization': customer, 'status': OrderStatus.CONFIRMED,
                'notes': 'Repeat standing order - wired scanners for seasonal event staff. No quote needed.',
            },
        )
        ol_hr15 = oline(so2, hr15, 20, 0)

        fo2, _ = FulfillmentOrder.objects.update_or_create(
            pk=_sal_uuid('fo:stadium-scanners-foh'),
            defaults={
                'reference': _REFS['fo2'], 'sales_order': so2, 'created_by': user,
                'status': FulfillmentOrderStatus.PENDING,
                'notes': 'Awaiting goods-in confirmation from ScanTech Benelux.',
            },
        )
        fo_line(fo2, ol_hr15, 'C-02-01', 0)

        inv2, _ = Invoice.objects.update_or_create(
            pk=_sal_uuid('inv:stadium-scanners'),
            defaults={
                'reference': _REFS['inv2'], 'order': so2, 'created_by': user,
                'relation_organization': customer, 'status': InvoiceStatus.ISSUED,
                'currency': 'EUR', 'due_date': date(2026, 3, 15),
            },
        )
        if ol_hr15:
            InvoiceLine.objects.update_or_create(
                pk=_sal_uuid(f'il:{inv2.pk}:{ol_hr15.pk}'),
                defaults={
                    'invoice': inv2, 'product': ol_hr15.product,
                    'product_name': ol_hr15.product_name, 'sku': ol_hr15.sku,
                    'brand': ol_hr15.brand or '', 'quantity': ol_hr15.quantity,
                    'unit_price': ol_hr15.unit_price, 'currency': ol_hr15.currency,
                    'line_total': ol_hr15.line_total, 'sort_order': 0,
                },
            )
        # No payment recorded - invoice is overdue (due 2026-03-15)

        # ────────────────────────────────────────────────────────────────────────
        # SO3 - CONFIRMED: QuickServe pilot order - fulfillment in progress
        # Invoice: paid in full
        # ────────────────────────────────────────────────────────────────────────
        so3, _ = SalesOrder.objects.update_or_create(
            pk=_sal_uuid('order:qsr-pilot'),
            defaults={
                'reference': _REFS['so3'], 'created_by': user, 'quote': None,
                'relation_organization': qsr, 'status': OrderStatus.CONFIRMED,
                'notes': 'Pilot order for QSR Rotterdam HQ. 20 scanners + consumables.',
            },
        )
        ol_hr15_qsr = oline(so3, hr15, 20, 0)
        ol_roll_qsr = oline(so3, roll, 200, 1)

        fo3, _ = FulfillmentOrder.objects.update_or_create(
            pk=_sal_uuid('fo:qsr-pilot'),
            defaults={
                'reference': _REFS['fo3'], 'sales_order': so3, 'created_by': user,
                'status': FulfillmentOrderStatus.IN_PROGRESS,
                'notes': 'Scanners picked; consumables pending.',
            },
        )
        fol_hr15_qsr = fo_line(fo3, ol_hr15_qsr, 'C-02-01', 0)
        fol_roll_qsr = fo_line(fo3, ol_roll_qsr, 'D-ROLL-01', 1)

        sho2, _ = ShippingOrder.objects.update_or_create(
            pk=_sal_uuid('sho:qsr-pilot'),
            defaults={
                'reference': _REFS['sho2'], 'fulfillment_order': fo3, 'sales_order': so3,
                'created_by': user, 'status': ShippingOrderStatus.PARTIALLY_SHIPPED,
                'notes': 'Scanners shipped; consumables to follow in second consignment.',
            },
        )
        if fol_hr15_qsr:
            shol_qsr, _ = ShippingOrderLine.objects.update_or_create(
                pk=_sal_uuid(f'shol:{sho2.pk}:{fol_hr15_qsr.pk}'),
                defaults={'shipping_order': sho2, 'fulfillment_line': fol_hr15_qsr,
                          'quantity': fol_hr15_qsr.quantity},
            )
            sh2, _ = Shipment.objects.update_or_create(
                pk=_sal_uuid('sh:qsr-pilot-scanners'),
                defaults={
                    'shipping_order': sho2, 'sequence': 1, 'carrier': 'PostNL',
                    'tracking_number': '3SYZKA123456789', 'status': ShipmentStatus.IN_TRANSIT,
                    'notes': 'Scanners dispatched - estimated delivery tomorrow.',
                },
            )
            ShipmentLine.objects.update_or_create(
                pk=_sal_uuid(f'shl:{sh2.pk}:{shol_qsr.pk}'),
                defaults={'shipment': sh2, 'shipping_order_line': shol_qsr, 'quantity': shol_qsr.quantity},
            )

        inv3, _ = Invoice.objects.update_or_create(
            pk=_sal_uuid('inv:qsr-pilot'),
            defaults={
                'reference': _REFS['inv3'], 'order': so3, 'created_by': user,
                'relation_organization': qsr, 'status': InvoiceStatus.ISSUED,
                'currency': 'EUR', 'due_date': date(2026, 4, 30),
            },
        )
        for i, ol in enumerate(x for x in [ol_hr15_qsr, ol_roll_qsr] if x):
            InvoiceLine.objects.update_or_create(
                pk=_sal_uuid(f'il:{inv3.pk}:{ol.pk}'),
                defaults={
                    'invoice': inv3, 'product': ol.product,
                    'product_name': ol.product_name, 'sku': ol.sku, 'brand': ol.brand or '',
                    'quantity': ol.quantity, 'unit_price': ol.unit_price,
                    'currency': ol.currency, 'line_total': ol.line_total, 'sort_order': i,
                },
            )
        inv3_total = sum(ol.line_total for ol in [ol_hr15_qsr, ol_roll_qsr] if ol)
        InvoicePayment.objects.update_or_create(
            pk=_sal_uuid('pay:qsr-pilot-full'),
            defaults={
                'invoice': inv3,
                'amount': inv3_total.quantize(Decimal('0.01')),
                'reference_note': 'Bank transfer QSR ref QSR-AP-2026-0311',
                'created_by': user,
            },
        )

        # ────────────────────────────────────────────────────────────────────────
        # SO4 - DRAFT: Metro Arena scanner order
        # ────────────────────────────────────────────────────────────────────────
        so4, _ = SalesOrder.objects.update_or_create(
            pk=_sal_uuid('order:metro-arena-draft'),
            defaults={
                'reference': _REFS['so4'], 'created_by': user, 'quote': None,
                'relation_organization': prospect, 'status': OrderStatus.DRAFT,
                'notes': 'Quick order raised ahead of quote - for internal budget tracking. Needs confirmation.',
            },
        )
        oline(so4, hr22, 4, 0)

        # ── Demo cart (logged-in user gets items pre-loaded) ────────────────────
        cart, _ = Cart.objects.get_or_create(user=user)
        for product, qty in [(mt93, 2), (hr22, 4), (roll, 50)]:
            if product:
                CartLine.objects.update_or_create(
                    cart=cart, product=product, defaults={'quantity': qty},
                )

        self.stdout.write(
            f'    {Quote.objects.count()} quotes, '
            f'{SalesOrder.objects.count()} orders, '
            f'{Invoice.objects.count()} invoices, '
            f'{FulfillmentOrder.objects.count()} fulfillment orders, '
            f'{ShippingOrder.objects.count()} shipping orders'
        )

    # ── PRICING ────────────────────────────────────────────────────────────────

    def _seed_pricing(self) -> None:
        self.stdout.write('  Seeding pricing rules…')
        from pricing.models import PricingMethod, PricingRule, PricingRuleAssignment, RoundingMethod

        def cat(slug): return ProductCategory.objects.filter(slug=slug).first()
        def prod(sku): return Product.objects.filter(sku=sku).first()

        rule1, _ = PricingRule.objects.get_or_create(
            name='Standard reseller markup - POS hardware',
            defaults={
                'description': 'Applies a 55% cost-plus markup across all point-of-sale hardware categories.',
                'method': PricingMethod.COST_MARKUP, 'value': Decimal('55.000000'),
                'rounding': RoundingMethod.NEAREST_EURO, 'is_active': True,
                'notes': 'Standard channel margin. Override per-product for strategic accounts.',
            },
        )
        pos_cat = cat('point-of-sale')
        if pos_cat:
            PricingRuleAssignment.objects.get_or_create(
                rule=rule1, category=pos_cat,
                defaults={'include_subcategories': True, 'priority': 10},
            )

        rule2, _ = PricingRule.objects.get_or_create(
            name='Consumables - 40% gross margin',
            defaults={
                'description': 'Thermal roll consumables carry a 40% gross margin target.',
                'method': PricingMethod.GROSS_MARGIN, 'value': Decimal('40.000000'),
                'rounding': RoundingMethod.NEAREST_CENT, 'is_active': True,
            },
        )
        cons_cat = cat('consumables')
        if cons_cat:
            PricingRuleAssignment.objects.get_or_create(
                rule=rule2, category=cons_cat,
                defaults={'include_subcategories': True, 'priority': 10},
            )

        rule3, _ = PricingRule.objects.get_or_create(
            name='MT93 enterprise pricing - 10% off MSRP',
            defaults={
                'description': 'Specific pricing for the Newland MT93 when sold into enterprise channel.',
                'method': PricingMethod.MSRP_DISCOUNT, 'value': Decimal('10.000000'),
                'rounding': RoundingMethod.NEAREST_EURO, 'is_active': True,
            },
        )
        mt93 = prod('NEW-MT93-4G')
        if mt93:
            PricingRuleAssignment.objects.get_or_create(
                rule=rule3, product=mt93, defaults={'priority': 5},
            )

        rule4, _ = PricingRule.objects.get_or_create(
            name='Partner bundle pricing - fixed multiplier 0.88',
            defaults={
                'description': 'Applies an 0.88 list-price multiplier for partner/integrator bundles.',
                'method': PricingMethod.FIXED_MULTIPLIER, 'value': Decimal('0.880000'),
                'rounding': RoundingMethod.NEAREST_EURO, 'is_active': True,
                'notes': 'Used for bundle SKUs sold through certified integrators.',
            },
        )
        bundles_cat = cat('bundles-kits')
        if bundles_cat:
            PricingRuleAssignment.objects.get_or_create(
                rule=rule4, category=bundles_cat,
                defaults={'include_subcategories': True, 'priority': 10},
            )

        from pricing.models import PricingRuleAssignment as PRA
        self.stdout.write(
            f'    {PricingRule.objects.count()} rules, '
            f'{PRA.objects.count()} assignments'
        )

    # ── CONTRACTS ─────────────────────────────────────────────────────────────

    def _seed_contracts(self) -> None:
        self.stdout.write('  Seeding contracts…')
        from contracts.models import (
            Contract, ContractStatus, ContractTemplate, ContractTemplateVariable,
            ContractVariableType, ContractVariableValue, ServiceRate,
        )
        from contracts.services import create_variable_value_stubs, refresh_computed_result

        # ── Service rates ──────────────────────────────────────────────────────
        field_eng, _ = ServiceRate.objects.get_or_create(
            code='field_engineer',
            defaults={
                'name': 'Field engineer',
                'description': 'Senior field engineer - on-site installation, diagnosis, and complex repairs.',
                'rate_per_hour': Decimal('85.00'), 'currency': 'EUR', 'is_active': True,
            },
        )
        ServiceRate.objects.get_or_create(
            code='technician',
            defaults={
                'name': 'Senior technician',
                'description': 'Certified hardware technician for bench and on-site repair.',
                'rate_per_hour': Decimal('65.00'), 'currency': 'EUR', 'is_active': True,
            },
        )
        ServiceRate.objects.get_or_create(
            code='remote_support',
            defaults={
                'name': 'Remote support',
                'description': 'Remote diagnostics, configuration, and software support.',
                'rate_per_hour': Decimal('45.00'), 'currency': 'EUR', 'is_active': True,
            },
        )

        # ── Template 1: Hardware Maintenance SLA ──────────────────────────────
        tmpl1, _ = ContractTemplate.objects.get_or_create(
            name='Hardware Maintenance SLA',
            defaults={
                'description': (
                    'Annual cost model for hardware maintenance SLAs. Covers a percentage of the '
                    'original order value, a fixed assistance allowance, and repair hours at the '
                    'field engineer rate - spread across the contract duration.'
                ),
                'formula':      '(order_total * contract_pct / 100 + assistance_fee + repair_hours * engineer_rate) / duration_years',
                'result_label': 'Annual SLA cost (EUR)',
                'is_active':    True,
                'notes': (
                    'Typical values: contract_pct = 15 (5-year), 18 (3-year), 20 (2-year).\n'
                    'assistance_fee covers non-billable travel and minor on-site work.\n'
                    'repair_hours is the average estimate per year over the contract lifetime.'
                ),
            },
        )
        for name, label, vtype, svc_rate, const_val, default_val, unit, sort in [
            ('contract_pct',   'Contract % of order value', ContractVariableType.USER_INPUT,   None,      None, Decimal('15'),  '%',     10),
            ('assistance_fee', 'Fixed assistance allowance', ContractVariableType.USER_INPUT,   None,      None, Decimal('500'), 'EUR',   20),
            ('repair_hours',   'Est. repair hours per year', ContractVariableType.USER_INPUT,   None,      None, Decimal('8'),   'hours', 30),
            ('engineer_rate',  'Engineer hourly rate',       ContractVariableType.SERVICE_RATE, field_eng, None, None,           'EUR/h', 40),
        ]:
            ContractTemplateVariable.objects.get_or_create(
                template=tmpl1, name=name,
                defaults={'label': label, 'variable_type': vtype, 'service_rate': svc_rate,
                          'constant_value': const_val, 'default_value': default_val,
                          'unit': unit, 'sort_order': sort},
            )

        # ── Template 2: Annual Consumables Supply Agreement ────────────────────
        tmpl2, _ = ContractTemplate.objects.get_or_create(
            name='Annual Consumables Supply Agreement',
            defaults={
                'description': (
                    'Fixed-price annual supply agreement for consumables (rolls, labels). '
                    'Combines a committed volume discount with a logistics flat fee.'
                ),
                'formula':      'annual_rolls * roll_unit_price + logistics_flat_fee',
                'result_label': 'Annual commitment value (EUR)',
                'is_active':    True,
                'notes': 'Roll unit price reflects volume discount tier; logistics fee covers deliveries.',
            },
        )
        for name, label, vtype, const_val, default_val, unit, sort in [
            ('annual_rolls',     'Committed rolls per year',     ContractVariableType.USER_INPUT, None, Decimal('1200'),  'rolls', 10),
            ('roll_unit_price',  'Unit price per roll (agreed)', ContractVariableType.USER_INPUT, None, Decimal('0.98'),  'EUR',   20),
            ('logistics_flat_fee','Annual logistics fee',        ContractVariableType.USER_INPUT, None, Decimal('350'),   'EUR',   30),
        ]:
            ContractTemplateVariable.objects.get_or_create(
                template=tmpl2, name=name,
                defaults={'label': label, 'variable_type': vtype, 'service_rate': None,
                          'constant_value': const_val, 'default_value': default_val,
                          'unit': unit, 'sort_order': sort},
            )

        # ── Contract instances ─────────────────────────────────────────────────
        customer = Organization.objects.filter(pk=_rel_uuid('org:stadium-events-group')).first()
        qsr      = Organization.objects.filter(pk=_rel_uuid('org:quickserve-restaurants')).first()
        so1      = SalesOrder.objects.filter(reference=_REFS['so1']).first()
        so2      = SalesOrder.objects.filter(reference=_REFS['so2']).first()
        so3      = SalesOrder.objects.filter(reference=_REFS['so3']).first()

        def make_contract(ref, org, tmpl, order, start, end, status, var_overrides, notes):
            c, created = Contract.objects.get_or_create(
                reference=ref,
                defaults={
                    'template': tmpl, 'organization': org, 'status': status,
                    'start_date': start, 'end_date': end, 'sales_order': order, 'notes': notes,
                },
            )
            if created:
                create_variable_value_stubs(c)
                for var_name, val in var_overrides.items():
                    ContractVariableValue.objects.filter(
                        contract=c, variable__name=var_name,
                    ).update(value=val)
                refresh_computed_result(c)
            return c

        if customer:
            c1 = make_contract(
                'SVC-DEMO-0001', customer, tmpl1, so1,
                date(2026, 4, 1), date(2029, 3, 31), ContractStatus.ACTIVE,
                {'contract_pct': Decimal('15'), 'assistance_fee': Decimal('750'), 'repair_hours': Decimal('10')},
                f'3-year hardware SLA linked to {_REFS["so1"]}. Covers all POS terminals and screens deployed at Stadium Events Group.',
            )
            c2 = make_contract(
                'SVC-DEMO-0002', customer, tmpl1, so2,
                date(2026, 4, 1), date(2028, 3, 31), ContractStatus.ACTIVE,
                {'contract_pct': Decimal('18'), 'assistance_fee': Decimal('400'), 'repair_hours': Decimal('6')},
                f'2-year SLA for the wired scanner fleet ({_REFS["so2"]}). Higher % due to shorter term.',
            )

        if qsr:
            c3 = make_contract(
                'SVC-DEMO-0003', qsr, tmpl2, so3,
                date(2026, 3, 1), date(2027, 2, 28), ContractStatus.ACTIVE,
                {'annual_rolls': Decimal('2400'), 'roll_unit_price': Decimal('0.95'), 'logistics_flat_fee': Decimal('480')},
                'Annual consumables supply agreement - 84 outlets across NL/BE. Deliveries coordinated with Frank Willems.',
            )

        from contracts.models import Contract as C
        self.stdout.write(
            f'    3 service rates, {ContractTemplate.objects.count()} templates, {C.objects.count()} contracts'
        )
