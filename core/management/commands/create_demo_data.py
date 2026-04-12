"""
Management command: seed comprehensive demo data for Meridian Group BV.

Meridian Group BV is a fictional premium lifestyle & home goods wholesale
distributor. The demo showcases a holding with three subsidiaries, a full
sales pipeline, warehouse operations, purchase orders, contracts and more.

Usage:
  python manage.py create_demo_data           # seed (idempotent)
  python manage.py create_demo_data --clear   # wipe everything first, then seed
  python manage.py create_demo_data --skip-images  # skip image loading
"""

from __future__ import annotations

import io
import os
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
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
    ProductDocument,
    ProductDocumentType,
    ProductImage,
    ProductPriceTier,
    ProductRelation,
    ProductRelationType,
    ProductStatus,
    TaxRate,
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

# ── Inventory & Procurement ────────────────────────────────────────────────────
from inventory.models import (
    MovementType,
    StockEntry,
    StockLocation,
    StockMovement,
    Warehouse,
)
from procurement.models import POStatus, PurchaseOrder, PurchaseOrderLine


# ── Stable UUID namespaces ──────────────────────────────────────────────────────

def _uuid(ns: str, key: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f'demo-{ns}-seed:{key}')

def _cat_uuid(k: str)  -> uuid.UUID: return _uuid('catalog', k)
def _rel_uuid(k: str)  -> uuid.UUID: return _uuid('relations', k)
def _ast_uuid(k: str)  -> uuid.UUID: return _uuid('assets', k)
def _sal_uuid(k: str)  -> uuid.UUID: return _uuid('sales', k)
def _inv_uuid(k: str)  -> uuid.UUID: return _uuid('inventory', k)
def _prc_uuid(k: str)  -> uuid.UUID: return _uuid('procurement', k)


# ── Demo references ─────────────────────────────────────────────────────────────
_REFS = {
    # Quotes
    'q1':  'Q-DEMO-0001', 'q2':  'Q-DEMO-0002', 'q3':  'Q-DEMO-0003',
    'q4':  'Q-DEMO-0004', 'q5':  'Q-DEMO-0005', 'q6':  'Q-DEMO-0006',
    'q7':  'Q-DEMO-0007', 'q8':  'Q-DEMO-0008',
    # Sales orders
    'so1': 'SO-DEMO-0001', 'so2': 'SO-DEMO-0002', 'so3': 'SO-DEMO-0003',
    'so4': 'SO-DEMO-0004', 'so5': 'SO-DEMO-0005',
    # Fulfillment orders
    'fo1': 'FO-DEMO-0001', 'fo2': 'FO-DEMO-0002', 'fo3': 'FO-DEMO-0003',
    # Shipping orders
    'sho1': 'SHP-DEMO-0001', 'sho2': 'SHP-DEMO-0002', 'sho3': 'SHP-DEMO-0003',
    # Invoices
    'inv1': 'INV-DEMO-0001', 'inv2': 'INV-DEMO-0002', 'inv3': 'INV-DEMO-0003',
    'inv4': 'INV-DEMO-0004', 'inv5': 'INV-DEMO-0005',
    # Purchase orders
    'po1': 'PO-DEMO-0001', 'po2': 'PO-DEMO-0002', 'po3': 'PO-DEMO-0003',
    # Misc
    'recall_1': 'RC-DEMO-0001',
    'mjop_1':   'MJOP-DEMO-0001',
}

_DEMO_ASSETS_DIR = Path(__file__).parent / 'demo_assets'
_DEMO_DOC_BODY = (
    b'Document demo attachment\n'
    b'This file is synthetic seed data for UI testing only.\n'
    b'Do not distribute or use in production.\n'
)


# ── Image helpers ───────────────────────────────────────────────────────────────

def _load_asset_image(filename: str) -> bytes | None:
    """Load a bundled demo image from the demo_assets/ directory."""
    path = _DEMO_ASSETS_DIR / filename
    if path.exists():
        return path.read_bytes()
    return None


def _pil_placeholder(name: str, sku: str, category: str = '') -> bytes:
    """Generate a gradient placeholder image with Pillow."""
    from PIL import Image, ImageDraw
    W, H = 800, 600
    img = Image.new('RGB', (W, H), (245, 240, 235))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        r = int(245 + (230 - 245) * t)
        g = int(240 + (225 - 240) * t)
        b = int(235 + (220 - 235) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    draw.rounded_rectangle([80, 100, W - 80, H - 100], radius=20, fill=(255, 255, 255),
                            outline=(210, 200, 195))
    draw.text((W // 2, H // 2 - 20), sku[:28], fill=(120, 100, 90), anchor='mm')
    if category:
        draw.text((W // 2, H // 2 + 20), category[:30], fill=(160, 140, 130), anchor='mm')
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=88)
    return buf.getvalue()


def _get_product_image(sku: str, name: str, category: str, asset_file: str | None,
                       skip: bool) -> bytes:
    if not skip and asset_file:
        data = _load_asset_image(asset_file)
        if data:
            return data
    return _pil_placeholder(name, sku, category)


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


# ── Clear all business data ─────────────────────────────────────────────────────

def _clear_all() -> None:
    from contracts.models import (
        Contract, ContractTemplate, ContractTemplateVariable,
        ContractVariableValue, ServiceRate,
    )
    from pricing.models import PricingRule, PricingRuleAssignment

    ContractVariableValue.objects.all().delete()
    Contract.objects.all().delete()
    ContractTemplateVariable.objects.all().delete()
    ContractTemplate.objects.all().delete()
    ServiceRate.objects.all().delete()
    PricingRuleAssignment.objects.all().delete()
    PricingRule.objects.all().delete()

    PurchaseOrderLine.objects.all().delete()
    PurchaseOrder.objects.all().delete()

    StockMovement.objects.all().delete()
    StockEntry.objects.all().delete()
    StockLocation.objects.all().delete()
    Warehouse.objects.all().delete()

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
    Address.objects.all().delete()

    while Organization.objects.exists():
        deleted, _ = Organization.objects.filter(children__isnull=True).delete()
        if not deleted:
            Organization.objects.all().delete()
            break
    OrganizationCategoryTag.objects.all().delete()

    from catalog.models import ProductOption
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


# ── Main command ────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Seed comprehensive demo data - Meridian Group BV lifestyle/home goods distributor.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('--clear', action='store_true',
                            help='Delete all existing data first, then re-seed.')
        parser.add_argument('--skip-images', action='store_true',
                            help='Skip image loading; use Pillow-generated placeholders.')

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        if options['clear']:
            _clear_all()
            self.stdout.write(self.style.WARNING('  Cleared all demo data.'))

        self._skip = options['skip_images']
        self._seed_catalog()
        self._seed_relations()
        self._seed_inventory()
        self._seed_procurement()
        self._seed_assets()
        self._seed_sales()
        self._seed_pricing()
        self._seed_contracts()
        self.stdout.write(self.style.SUCCESS('\nDemo data ready - all screens populated.'))

    # ── CATALOG ────────────────────────────────────────────────────────────────

    def _seed_catalog(self) -> None:
        self.stdout.write('  Seeding catalog...')

        vat21, _ = TaxRate.objects.get_or_create(
            code='NL_STD', defaults={'name': 'VAT standard (NL)', 'rate': Decimal('21.00')})
        vat9, _ = TaxRate.objects.get_or_create(
            code='NL_RED', defaults={'name': 'VAT reduced (NL)', 'rate': Decimal('9.00')})
        TaxRate.objects.get_or_create(
            code='DE_STD', defaults={'name': 'VAT standard (DE)', 'rate': Decimal('19.00')})
        TaxRate.objects.get_or_create(
            code='EU_ZERO', defaults={'name': 'Zero-rated (intra-EU B2B)', 'rate': Decimal('0.00')})

        dg_retail,    _ = DiscountGroup.objects.get_or_create(slug='retail',    defaults={'name': 'Retail list'})
        dg_wholesale, _ = DiscountGroup.objects.get_or_create(slug='wholesale', defaults={'name': 'Wholesale'})
        dg_partner,   _ = DiscountGroup.objects.get_or_create(slug='partner',   defaults={'name': 'Preferred partner'})

        def cat(slug, name, parent=None):
            obj, _ = ProductCategory.objects.get_or_create(
                slug=slug, defaults={'name': name, 'parent': parent})
            if obj.name != name or obj.parent_id != (parent.pk if parent else None):
                obj.name = name; obj.parent = parent; obj.save()
            return obj

        home        = cat('home-living',       'Home & Living')
        hydration   = cat('hydration',         'Hydration & Wellness',    home)
        storage     = cat('kitchen-storage',   'Kitchen & Pantry Storage', home)
        stationery  = cat('stationery',        'Stationery & Office',     home)
        accessories = cat('accessories',       'Accessories',             home)
        bundles     = cat('gift-sets',         'Gift Sets & Bundles',     home)
        seasonal    = cat('seasonal',          'Seasonal Collections',    home)

        def p(sku, *, name, category, status=ProductStatus.ACTIVE, brand='Meridian',
              short='', long_desc='', ean='', purchase=None, list_price=None,
              msrp=None, tax=None, discount_group=None, uom='piece', moq=1,
              lead_days=5, warehouse='A-01-01', serial_req=False, warranty=24,
              inventory_tracked=True, length=None, width=None, height=None,
              w_net=None, w_gross=None, color='', material='',
              asset_file=None, **kwargs) -> Product:
            defaults = dict(
                name=name, short_description=short[:255], long_description=long_desc,
                brand=brand, category=category, status=status, ean_gtin=ean,
                purchase_price=purchase, list_price=list_price, msrp=msrp,
                currency='EUR', tax_rate=tax or vat21,
                discount_group=discount_group or dg_wholesale,
                unit_of_measure=uom, minimum_order_quantity=moq,
                lead_time_days=lead_days, warehouse_location=warehouse,
                inventory_tracked=inventory_tracked,
                serial_number_required=serial_req, warranty_months=warranty,
                length=length, width=width, height=height,
                weight_net=w_net, weight_gross=w_gross,
                color=color, material=material,
            )
            defaults.update(kwargs)
            obj, created = Product.objects.update_or_create(sku=sku, defaults=defaults)
            if not self._skip and asset_file and (created or not ProductImage.objects.filter(product=obj).exists()):
                img_bytes = _get_product_image(sku, name, category.name, asset_file, self._skip)
                ProductImage.objects.create(
                    product=obj,
                    image=ContentFile(img_bytes, name=f'{sku}.png'),
                    is_primary=True, sort_order=0, alt_text=name,
                )
            elif self._skip and (created or not ProductImage.objects.filter(product=obj).exists()):
                img_bytes = _pil_placeholder(name, sku, category.name)
                ProductImage.objects.create(
                    product=obj,
                    image=ContentFile(img_bytes, name=f'{sku}.jpg'),
                    is_primary=True, sort_order=0, alt_text=name,
                )
            return obj

        # ── Products ──────────────────────────────────────────────────────────

        btl500 = p('MERID-BTL-500',
            name='Meridian Insulated Bottle 500ml - Ivory White',
            category=hydration, brand='Meridian Living',
            short='Double-wall vacuum insulated stainless steel bottle with bamboo cap. Keeps drinks cold 24h / hot 12h.',
            long_desc=(
                'The Meridian 500ml bottle is crafted from 18/8 food-grade stainless steel with a '
                'powder-coated exterior in warm Ivory White. The genuine bamboo cap adds a natural '
                'touch and is hand-wash only. BPA-free. Suitable for most standard car cup holders. '
                'MOQ 12 units for retail display stands. Comes in branded gift box.'
            ),
            ean='8720001100015', purchase=Decimal('7.50'), list_price=Decimal('24.95'),
            msrp=Decimal('29.95'), discount_group=dg_wholesale,
            moq=12, lead_days=7, warehouse='A-01-01',
            length=Decimal('70'), width=Decimal('70'), height=Decimal('225'),
            w_net=Decimal('280'), w_gross=Decimal('380'),
            color='Ivory White', material='18/8 stainless steel, bamboo cap',
            asset_file='product_1.png',
        )

        btl750 = p('MERID-BTL-750',
            name='Meridian Insulated Bottle 750ml - Sage Green',
            category=hydration, brand='Meridian Living',
            short='Larger format double-wall vacuum insulated bottle with bamboo cap. Ideal for outdoors and gym.',
            long_desc=(
                'Same premium stainless steel construction as the 500ml but in a generous 750ml '
                'format. Sage Green powder coat with contrasting natural bamboo cap. '
                'Wide-mouth opening fits ice cubes. Compatible with standard hydration accessories.'
            ),
            ean='8720001100022', purchase=Decimal('9.20'), list_price=Decimal('29.95'),
            msrp=Decimal('34.95'), discount_group=dg_wholesale,
            moq=12, lead_days=7, warehouse='A-01-02',
            length=Decimal('75'), width=Decimal('75'), height=Decimal('270'),
            w_net=Decimal('330'), w_gross=Decimal('440'),
            color='Sage Green', material='18/8 stainless steel, bamboo cap',
        )

        sta_set = p('MERID-STA-CLASSIC',
            name='Meridian Classic Stationery Collection',
            category=stationery, brand='Meridian Living',
            short='Curated desk collection: A5 notebook, ceramic pen holder, mini ceramic jar and wooden ruler.',
            long_desc=(
                'The Classic Stationery Collection is a bestselling retail display set combining '
                'a thread-bound A5 notebook (120 pages, dot-grid), a hand-turned ceramic pen holder, '
                'a matching ceramic storage jar with cork lid, and a laser-engraved wooden ruler. '
                'Presented in a kraft gift box with tissue paper. Minimum 6 sets per retail display unit.'
            ),
            ean='8720001200019', purchase=Decimal('12.40'), list_price=Decimal('39.95'),
            msrp=Decimal('49.95'), discount_group=dg_wholesale,
            tax=vat21, moq=6, lead_days=10, warehouse='B-02-01',
            length=Decimal('220'), width=Decimal('160'), height=Decimal('80'),
            w_net=Decimal('620'), w_gross=Decimal('750'),
            color='Natural / White', material='Ceramic, paper, wood',
            asset_file='product_2.png',
        )

        can_sm = p('MERID-CAN-SM',
            name='Meridian Ceramic Canister Small 300ml - Chalk White',
            category=storage, brand='Meridian Living',
            short='Hand-thrown ceramic storage canister with bamboo lid and silicone seal. 300ml.',
            long_desc=(
                'Each Meridian canister is individually thrown on a pottery wheel, giving a subtle '
                'organic texture. The bamboo lid includes a food-grade silicone ring to keep contents '
                'fresh. Dishwasher safe body (lid hand-wash only). Suitable for spices, coffee, sugar. '
                'Pairs with the 800ml large canister for a matching kitchen set.'
            ),
            ean='8720001300018', purchase=Decimal('5.80'), list_price=Decimal('18.95'),
            msrp=Decimal('22.95'), discount_group=dg_wholesale,
            moq=6, lead_days=8, warehouse='B-03-01',
            length=Decimal('90'), width=Decimal('90'), height=Decimal('130'),
            w_net=Decimal('390'), w_gross=Decimal('480'),
            color='Chalk White', material='Ceramic, bamboo, silicone',
            asset_file='product_3.png',
        )

        can_lg = p('MERID-CAN-LG',
            name='Meridian Ceramic Canister Large 800ml - Chalk White',
            category=storage, brand='Meridian Living',
            short='Large hand-thrown ceramic storage canister with bamboo lid and silicone seal. 800ml.',
            long_desc=(
                'The large 800ml canister from the same hand-thrown series as the 300ml. '
                'Perfect for pasta, rice, flour or coffee beans. Bamboo lid with silicone food seal. '
                'Dishwasher safe body. Sold individually and as part of the Kitchen Gift Set.'
            ),
            ean='8720001300025', purchase=Decimal('8.40'), list_price=Decimal('24.95'),
            msrp=Decimal('29.95'), discount_group=dg_wholesale,
            moq=6, lead_days=8, warehouse='B-03-02',
            length=Decimal('115'), width=Decimal('115'), height=Decimal('175'),
            w_net=Decimal('610'), w_gross=Decimal('740'),
            color='Chalk White', material='Ceramic, bamboo, silicone',
        )

        nbook = p('MERID-NBOOK-A5',
            name='Meridian Dot-Grid Notebook A5 - Recycled Kraft Cover',
            category=stationery, brand='Meridian Living',
            short='Thread-bound A5 notebook, 160 dot-grid pages, recycled kraft hardcover.',
            long_desc=(
                'Sustainably sourced kraft board cover with thread binding for lay-flat opening. '
                '160 pages of 90gsm acid-free dot-grid paper. Elastic closure band and ribbon bookmark. '
                'Packaged in compostable sleeve. Available in single units and in 6-pack display boxes.'
            ),
            ean='8720001400015', purchase=Decimal('2.90'), list_price=Decimal('9.95'),
            msrp=Decimal('12.95'), discount_group=dg_wholesale,
            moq=12, lead_days=5, warehouse='B-02-02',
            length=Decimal('210'), width=Decimal('148'), height=Decimal('14'),
            w_net=Decimal('220'), w_gross=Decimal('260'),
            color='Natural Kraft', material='Recycled kraft, paper',
        )

        brush_set = p('MERID-BRUSH-WD',
            name='Meridian Wooden Brush Set (3-piece)',
            category=accessories, brand='Meridian Living',
            short='Natural beech wood and sisal brush set: hand brush, nail brush, dish brush.',
            long_desc=(
                'Three-piece set crafted from FSC-certified beech wood with natural sisal bristles. '
                'Suitable as bathroom accessories or kitchen set. Presented on a natural cotton ribbon. '
                'Plastic-free packaging. Popular for eco-lifestyle retail sections.'
            ),
            ean='8720001500012', purchase=Decimal('6.20'), list_price=Decimal('19.95'),
            msrp=Decimal('24.95'), discount_group=dg_wholesale,
            moq=6, lead_days=7, warehouse='B-04-01',
            w_net=Decimal('320'), w_gross=Decimal('410'),
            color='Natural Beech', material='FSC beech wood, sisal',
        )

        plant_pot = p('MERID-PLANT-12',
            name='Meridian Ceramic Plant Pot 12cm - Matte White',
            category=accessories, brand='Meridian Living',
            short='Minimalist matte white ceramic plant pot with drainage hole and bamboo tray. 12cm diameter.',
            long_desc=(
                'Clean Scandinavian-inspired design with a hand-applied matte glaze. '
                'Drainage hole with matching bamboo drip tray included. Suitable for succulents, '
                'small herbs, and indoor plants. Pairs with the Stationery Collection for desk styling.'
            ),
            ean='8720001600011', purchase=Decimal('4.10'), list_price=Decimal('13.95'),
            msrp=Decimal('16.95'), discount_group=dg_wholesale,
            moq=6, lead_days=7, warehouse='B-04-02',
            length=Decimal('120'), width=Decimal('120'), height=Decimal('110'),
            w_net=Decimal('480'), w_gross=Decimal('580'),
            color='Matte White', material='Ceramic, bamboo',
        )

        gift_desk = p('MERID-GIFT-DESK',
            name='Meridian Desk Gift Set',
            category=bundles, brand='Meridian Living',
            short='Curated desk gift set: Stationery Collection + A5 Notebook + Wooden Brush Set in luxury box.',
            long_desc=(
                'The Desk Gift Set combines three bestselling lines in a premium rigid gift box with '
                'magnetic closure and custom tissue paper. A ready-made gifting solution for corporate '
                'and retail buyers. Minimum 4 sets. Lead time includes assembly time.'
            ),
            ean='8720001700010', purchase=Decimal('24.50'), list_price=Decimal('69.95'),
            msrp=Decimal('84.95'), discount_group=dg_partner,
            moq=4, lead_days=10, warehouse='C-01-01',
            w_net=Decimal('980'), w_gross=Decimal('1200'),
            color='Mixed', material='Various - see components',
        )

        gift_kitchen = p('MERID-GIFT-KITCHEN',
            name='Meridian Kitchen Gift Set',
            category=bundles, brand='Meridian Living',
            short='Kitchen gift set: Small Canister + Large Canister in gift box with ribbon.',
            long_desc=(
                'Matching pair of hand-thrown ceramic canisters presented together in a branded gift '
                'box. A popular wedding and housewarming gift. Minimum 4 sets.'
            ),
            ean='8720001700027', purchase=Decimal('17.80'), list_price=Decimal('49.95'),
            msrp=Decimal('59.95'), discount_group=dg_partner,
            moq=4, lead_days=10, warehouse='C-01-02',
            w_net=Decimal('1100'), w_gross=Decimal('1350'),
            color='Chalk White', material='Ceramic, bamboo, packaging',
        )

        gift_wellness = p('MERID-GIFT-WELLNESS',
            name='Meridian Wellness Bundle',
            category=bundles, brand='Meridian Living',
            short='Wellness gift bundle: Insulated Bottle 500ml + Plant Pot + Notebook in kraft gift box.',
            long_desc=(
                'A popular wellness-themed corporate gift: insulated bottle in Ivory White, '
                'ceramic plant pot, and dot-grid notebook. Assembled in a kraft box with '
                'natural raffia ribbon. Minimum 4 sets per order.'
            ),
            ean='8720001700034', purchase=Decimal('19.90'), list_price=Decimal('54.95'),
            msrp=Decimal('64.95'), discount_group=dg_partner,
            moq=4, lead_days=10, warehouse='C-01-03',
            w_net=Decimal('890'), w_gross=Decimal('1100'),
            color='Mixed', material='Various - see components',
        )

        seasonal_box = p('MERID-SEAS-WINTER',
            name='Meridian Winter Warmth Collection (limited edition)',
            category=seasonal, brand='Meridian Living',
            short='Limited seasonal collection: Bottle 500ml + Small Canister + Notebook in festive packaging.',
            long_desc=(
                'Annual limited-edition winter seasonal box. Contents and packaging vary per season; '
                'this listing covers the standard Winter Warmth assortment. Pre-order required - '
                'no stock replenishment after sell-out. Suitable for gift and department stores.'
            ),
            status=ProductStatus.ACTIVE,
            ean='8720001800019', purchase=Decimal('22.00'), list_price=Decimal('59.95'),
            msrp=Decimal('74.95'), discount_group=dg_partner,
            moq=6, lead_days=21, warehouse='C-02-01',
            w_net=Decimal('860'), w_gross=Decimal('1050'),
        )

        p('MERID-BTL-TRAVL',
            name='Meridian Travel Cap Set (accessory)',
            category=accessories, brand='Meridian Living',
            short='Replacement bamboo cap + straw set compatible with all Meridian bottles.',
            ean='8720001500029', purchase=Decimal('2.10'), list_price=Decimal('6.95'),
            msrp=Decimal('8.95'), discount_group=dg_retail,
            moq=24, lead_days=5, warehouse='A-01-03',
            w_net=Decimal('45'), w_gross=Decimal('75'),
            material='Bamboo, food-grade silicone straw',
        )

        p('MERID-DISP-STAND',
            name='Meridian Floor Display Stand (POS accessory)',
            category=accessories, brand='Meridian Living',
            short='Branded 8-pocket wire floor stand for Meridian bottle/canister retail display.',
            purchase=None, list_price=Decimal('89.00'),
            inventory_tracked=False, warranty=None,
            status=ProductStatus.ACTIVE,
            moq=1, lead_days=14, warehouse='',
            material='Powder-coated steel wire, branded card header',
        )

        # ── Price tiers ────────────────────────────────────────────────────────
        for min_q, max_q, price in [(12, 47, '24.95'), (48, 119, '22.50'), (120, None, '19.95')]:
            ProductPriceTier.objects.update_or_create(
                product=btl500, min_quantity=min_q,
                defaults={'max_quantity': max_q, 'unit_price': Decimal(price)},
            )
        for min_q, max_q, price in [(12, 47, '29.95'), (48, 119, '26.95'), (120, None, '23.95')]:
            ProductPriceTier.objects.update_or_create(
                product=btl750, min_quantity=min_q,
                defaults={'max_quantity': max_q, 'unit_price': Decimal(price)},
            )
        for min_q, max_q, price in [(6, 23, '39.95'), (24, 59, '35.95'), (60, None, '31.95')]:
            ProductPriceTier.objects.update_or_create(
                product=sta_set, min_quantity=min_q,
                defaults={'max_quantity': max_q, 'unit_price': Decimal(price)},
            )
        for min_q, max_q, price in [(6, 23, '18.95'), (24, 59, '16.95'), (60, None, '14.95')]:
            ProductPriceTier.objects.update_or_create(
                product=can_sm, min_quantity=min_q,
                defaults={'max_quantity': max_q, 'unit_price': Decimal(price)},
            )
        for min_q, max_q, price in [(6, 23, '24.95'), (24, 59, '21.95'), (60, None, '18.95')]:
            ProductPriceTier.objects.update_or_create(
                product=can_lg, min_quantity=min_q,
                defaults={'max_quantity': max_q, 'unit_price': Decimal(price)},
            )

        # ── BOM lines for bundles ──────────────────────────────────────────────
        for bundle_prod, component, qty in [
            (gift_desk,    sta_set,   Decimal('1')),
            (gift_desk,    nbook,     Decimal('1')),
            (gift_desk,    brush_set, Decimal('1')),
            (gift_kitchen, can_sm,    Decimal('1')),
            (gift_kitchen, can_lg,    Decimal('1')),
            (gift_wellness,btl500,    Decimal('1')),
            (gift_wellness,plant_pot, Decimal('1')),
            (gift_wellness,nbook,     Decimal('1')),
        ]:
            ProductBOMLine.objects.update_or_create(
                bundle_product=bundle_prod, component_product=component,
                defaults={'quantity': qty},
            )

        # ── Product relations ──────────────────────────────────────────────────
        for from_p, to_p, rtype, order in [
            (btl500, btl750,     ProductRelationType.UPSELL,      0),
            (btl500, gift_wellness, ProductRelationType.UPSELL,   1),
            (can_sm, can_lg,     ProductRelationType.UPSELL,      0),
            (can_sm, gift_kitchen, ProductRelationType.UPSELL,    1),
            (sta_set, nbook,     ProductRelationType.ACCESSORY,   0),
            (sta_set, brush_set, ProductRelationType.ACCESSORY,   1),
            (sta_set, gift_desk, ProductRelationType.UPSELL,      2),
            (btl500, btl750,     ProductRelationType.ALTERNATIVE, 0),
            (gift_desk, gift_kitchen, ProductRelationType.ALTERNATIVE, 0),
        ]:
            ProductRelation.objects.update_or_create(
                from_product=from_p, to_product=to_p, relation_type=rtype,
                defaults={'sort_order': order},
            )

        # ── Demo documents ─────────────────────────────────────────────────────
        for prod_obj, doc_type, title, fname in [
            (btl500,  ProductDocumentType.DATASHEET,     'Bottle 500ml - product sheet (demo)',      'merid-btl500-sheet.txt'),
            (btl500,  ProductDocumentType.CERTIFICATION, 'Bottle 500ml - food safety cert (demo)',   'merid-btl500-cert.txt'),
            (sta_set, ProductDocumentType.DATASHEET,     'Stationery Collection - trade sheet (demo)','merid-sta-sheet.txt'),
            (can_sm,  ProductDocumentType.DATASHEET,     'Ceramic Canister - range overview (demo)',  'merid-can-sheet.txt'),
            (gift_desk, ProductDocumentType.MANUAL,      'Desk Gift Set - assembly guide (demo)',     'merid-desk-set-assembly.txt'),
        ]:
            ProductDocument.objects.update_or_create(
                product=prod_obj, title=title,
                defaults={'document_type': doc_type,
                          'file': ContentFile(_DEMO_DOC_BODY, name=fname)},
            )

        self.stdout.write(
            f'    {ProductCategory.objects.count()} categories, '
            f'{Product.objects.count()} products, '
            f'{ProductImage.objects.count()} images'
        )

    # ── RELATIONS ──────────────────────────────────────────────────────────────

    def _seed_relations(self) -> None:
        self.stdout.write('  Seeding relations...')

        # ── Organisation category tags ─────────────────────────────────────────
        cat_objs = {}
        for code, label in OrganizationCategory.choices:
            ct, _ = OrganizationCategoryTag.objects.get_or_create(
                code=code, defaults={'label': label})
            if ct.label != label:
                ct.label = label; ct.save(update_fields=['label'])
            cat_objs[code] = ct

        # ── Link types ─────────────────────────────────────────────────────────
        strategic, _ = OrganizationLinkType.objects.update_or_create(
            name='Strategic partnership',
            defaults={'description': 'Long-term commercial alignment or preferred supplier status.'},
        )
        logistics, _ = OrganizationLinkType.objects.update_or_create(
            name='Logistics provider',
            defaults={'description': 'Handles warehousing, fulfilment, or transport.'},
        )
        distributor, _ = OrganizationLinkType.objects.update_or_create(
            name='Distribution partner',
            defaults={'description': 'Exclusive or preferred regional distribution agreement.'},
        )

        def org(key, name, *, parent=None, kind=OrganizationUnitKind.LEGAL_ENTITY,
                primary_cat=None, categories=(), **defaults):
            obj, _ = Organization.objects.get_or_create(
                id=_rel_uuid(key), name=name, defaults=defaults)
            obj.unit_kind = kind
            obj.parent = parent
            if primary_cat:
                obj.primary_category = cat_objs[primary_cat]
            obj.save(update_fields=['unit_kind', 'parent', 'primary_category'])
            obj.categories.set([cat_objs[c] for c in categories])
            return obj

        # ──────────────────────────────────────────────────────────────────────
        # MERIDIAN GROUP BV - Holding company (our own entity)
        # ──────────────────────────────────────────────────────────────────────
        holding = org('org:meridian-group', 'Meridian Group BV',
            kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.INTERNAL,
            categories=[OrganizationCategory.INTERNAL],
            legal_name='Meridian Group BV',
            industry='Lifestyle & home goods wholesale distribution',
            website='https://meridiangroup.example',
            tax_id_vat='NL999900001B01', registration_number='KvK 10000001',
            notes='Holding company. Three operating subsidiaries: NL, DE, BE.',
        )

        # Holding departments
        dept_exec    = org('org:meridian-group:executive', 'Executive & Strategy',
            parent=holding, kind=OrganizationUnitKind.DEPARTMENT,
            notes='Group-level leadership, M&A, investor relations.')
        dept_finance = org('org:meridian-group:finance', 'Group Finance & Accounting',
            parent=holding, kind=OrganizationUnitKind.DEPARTMENT,
            notes='Consolidated reporting, treasury, tax compliance.')
        dept_hr      = org('org:meridian-group:hr', 'People & Culture',
            parent=holding, kind=OrganizationUnitKind.DEPARTMENT,
            notes='Group HR, recruitment, L&D, employer brand.')
        dept_product = org('org:meridian-group:product', 'Product & Brand',
            parent=holding, kind=OrganizationUnitKind.DEPARTMENT,
            notes='Product development, brand guidelines, sustainability.')
        dept_it      = org('org:meridian-group:it', 'IT & Digital',
            parent=holding, kind=OrganizationUnitKind.DEPARTMENT,
            notes='Group IT infrastructure, ERP, e-commerce platforms.')

        # ── Subsidiary 1: Meridian Living NL BV ───────────────────────────────
        sub_nl = org('org:meridian-nl', 'Meridian Living NL BV',
            parent=holding, kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.INTERNAL,
            categories=[OrganizationCategory.INTERNAL],
            legal_name='Meridian Living NL BV',
            industry='Home goods wholesale',
            website='https://meridian-nl.example',
            tax_id_vat='NL999900002B01', registration_number='KvK 10000002',
            notes='Primary trading entity for the Netherlands market. Houses main warehouse.',
        )
        nl_sales  = org('org:meridian-nl:sales', 'Sales & Account Management',
            parent=sub_nl, kind=OrganizationUnitKind.DEPARTMENT,
            notes='Manages NL/BE customer accounts and new business.')
        nl_ops    = org('org:meridian-nl:operations', 'Operations & Logistics',
            parent=sub_nl, kind=OrganizationUnitKind.DEPARTMENT,
            notes='Warehouse, inbound goods, fulfilment, returns.')
        nl_cs     = org('org:meridian-nl:customer-service', 'Customer Service',
            parent=sub_nl, kind=OrganizationUnitKind.DEPARTMENT,
            notes='Order queries, returns handling, retailer support.')
        nl_fin    = org('org:meridian-nl:finance', 'Finance & Administration',
            parent=sub_nl, kind=OrganizationUnitKind.DEPARTMENT,
            notes='Local accounting, credit control, AP/AR.')
        nl_mktg   = org('org:meridian-nl:marketing', 'Marketing & Trade Marketing',
            parent=sub_nl, kind=OrganizationUnitKind.DEPARTMENT,
            notes='Campaigns, catalogue, trade show coordination.')

        # ── Subsidiary 2: Meridian Lifestyle DE GmbH ──────────────────────────
        sub_de = org('org:meridian-de', 'Meridian Lifestyle DE GmbH',
            parent=holding, kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.INTERNAL,
            categories=[OrganizationCategory.INTERNAL],
            legal_name='Meridian Lifestyle DE GmbH',
            industry='Home goods wholesale',
            website='https://meridian-de.example',
            tax_id_vat='DE999900001', registration_number='HRB 200001',
            notes='German subsidiary. Serves DACH market from Hamburg distribution centre.',
        )
        de_sales  = org('org:meridian-de:sales', 'Vertrieb (Sales)',
            parent=sub_de, kind=OrganizationUnitKind.DEPARTMENT,
            notes='DACH account management.')
        de_ops    = org('org:meridian-de:operations', 'Lager & Logistik (Operations)',
            parent=sub_de, kind=OrganizationUnitKind.DEPARTMENT,
            notes='Hamburg warehouse and cross-dock.')
        de_cs     = org('org:meridian-de:cs', 'Kundendienst (Customer Service)',
            parent=sub_de, kind=OrganizationUnitKind.DEPARTMENT)
        de_fin    = org('org:meridian-de:finance', 'Finanzen (Finance)',
            parent=sub_de, kind=OrganizationUnitKind.DEPARTMENT)
        de_mktg   = org('org:meridian-de:marketing', 'Marketing',
            parent=sub_de, kind=OrganizationUnitKind.DEPARTMENT)

        # ── Subsidiary 3: Meridian Trade BE BV ────────────────────────────────
        sub_be = org('org:meridian-be', 'Meridian Trade BE BV',
            parent=holding, kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.INTERNAL,
            categories=[OrganizationCategory.INTERNAL],
            legal_name='Meridian Trade BE BV',
            industry='Home goods wholesale',
            website='https://meridian-be.example',
            tax_id_vat='BE0999900001', registration_number='RPM 200001',
            notes='Belgian subsidiary. Primarily serves BE/LU retail chains and gift buyers.',
        )
        be_sales  = org('org:meridian-be:sales', 'Ventes (Sales)',
            parent=sub_be, kind=OrganizationUnitKind.DEPARTMENT)
        be_ops    = org('org:meridian-be:operations', 'Operations',
            parent=sub_be, kind=OrganizationUnitKind.DEPARTMENT)
        be_cs     = org('org:meridian-be:cs', 'Service Client (Customer Service)',
            parent=sub_be, kind=OrganizationUnitKind.DEPARTMENT)
        be_fin    = org('org:meridian-be:finance', 'Finance',
            parent=sub_be, kind=OrganizationUnitKind.DEPARTMENT)
        be_mktg   = org('org:meridian-be:marketing', 'Marketing',
            parent=sub_be, kind=OrganizationUnitKind.DEPARTMENT)

        # ──────────────────────────────────────────────────────────────────────
        # EXTERNAL ORGANISATIONS - customers, prospects, supplier
        # ──────────────────────────────────────────────────────────────────────
        bloom = org('org:bloom-co', 'Bloom & Co.',
            kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.CUSTOMER,
            categories=[OrganizationCategory.CUSTOMER, OrganizationCategory.STRATEGIC],
            legal_name='Bloom & Co. Retail BV',
            industry='Lifestyle & garden retail',
            website='https://bloomandco.example',
            tax_id_vat='NL888800001B01', registration_number='KvK 20000001',
            notes='24-location lifestyle retail chain across NL. Biggest single account. Annual catalogue order in Q4, re-orders throughout.',
        )
        nordic = org('org:nordic-home', 'Nordic Home',
            kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.CUSTOMER,
            categories=[OrganizationCategory.CUSTOMER],
            legal_name='Nordic Home Interiors BV',
            industry='Scandinavian home goods retail',
            website='https://nordichome.example',
            tax_id_vat='NL888800002B01', registration_number='KvK 20000002',
            notes='Boutique Scandi home goods chain, 8 stores NL. Prefers sustainable product lines.',
        )
        atelier = org('org:atelier-gifts', 'Atelier Gifts',
            kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.CUSTOMER,
            categories=[OrganizationCategory.CUSTOMER],
            legal_name='Atelier Gifts & Interiors BVBA',
            industry='Specialty gift retail',
            website='https://ateliergifts.example',
            tax_id_vat='BE0888800001', registration_number='RPM 100001',
            notes='Belgian gift boutique chain, 6 stores. Buys seasonal and bundle lines. Good payment history.',
        )
        gift_more = org('org:gift-more-de', 'Gift & More GmbH',
            kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.CUSTOMER,
            categories=[OrganizationCategory.CUSTOMER],
            legal_name='Gift & More GmbH',
            industry='Gift & novelty retail',
            website='https://giftmore.example',
            tax_id_vat='DE888800001', registration_number='HRB 300001',
            notes='German gift retailer, 12 stores. New account via Meridian DE, first order Q1 2026.',
        )
        fresh = org('org:fresh-concepts', 'Fresh Concepts',
            kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.PROSPECT,
            categories=[OrganizationCategory.PROSPECT],
            legal_name='Fresh Concepts Online BV',
            industry='Online home goods retail',
            website='https://freshconcepts.example',
            notes='Fast-growing online retailer. In discussion for dropship or wholesale programme. High volume potential.',
        )
        maison = org('org:maison-deco', 'Maison Deco SARL',
            kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.CUSTOMER,
            categories=[OrganizationCategory.CUSTOMER],
            legal_name='Maison Deco SARL',
            industry='Interior design & gift retail',
            website='https://maisondeco.example',
            tax_id_vat='FR88880000001', registration_number='SIRET 88880000001',
            notes='French boutique chain, 4 stores in Paris/Lyon. Buys premium and seasonal lines.',
        )
        supplier = org('org:premium-home-supplies', 'Premium Home Supplies BV',
            kind=OrganizationUnitKind.LEGAL_ENTITY,
            primary_cat=OrganizationCategory.SUPPLIER,
            categories=[OrganizationCategory.SUPPLIER],
            legal_name='Premium Home Supplies BV',
            industry='Home goods manufacturing & import',
            website='https://premiumhomesupplies.example',
            tax_id_vat='NL777700001B01', registration_number='KvK 30000001',
            notes='Primary supplier for ceramic, wood and stainless product lines. Lead times 6-8 weeks from factory.',
        )

        # ── Org links ──────────────────────────────────────────────────────────
        OrganizationLink.objects.update_or_create(
            from_organization=sub_nl, to_organization=bloom, link_type=strategic,
            defaults={'start_date': date(2021, 2, 1),
                      'notes': 'Annual catalogue agreement + seasonal re-order terms.'},
        )
        OrganizationLink.objects.update_or_create(
            from_organization=sub_be, to_organization=atelier, link_type=distributor,
            defaults={'start_date': date(2022, 9, 1),
                      'notes': 'Exclusive distribution of Meridian seasonal lines in BE.'},
        )
        OrganizationLink.objects.update_or_create(
            from_organization=sub_nl, to_organization=supplier, link_type=logistics,
            defaults={'start_date': date(2020, 1, 1),
                      'notes': 'Primary manufacturing and import partner.'},
        )

        # ── People ─────────────────────────────────────────────────────────────
        def person(key, first, last, **defaults):
            obj, _ = Person.objects.update_or_create(
                id=_rel_uuid(key),
                defaults=dict(first_name=first, last_name=last, **defaults),
            )
            return obj

        # Holding - Executive & Strategy (5 people)
        ceo    = person('p:ceo',    'Sophie',   'van den Berg',
            title_prefix='Ms.', pronouns='she/her', date_of_birth=date(1974, 4, 12),
            bio='Group CEO. Founder of Meridian Group. Background in sustainable product retail.',
            notes='Key stakeholder for strategic accounts and brand partnerships.')
        cco    = person('p:cco',    'Daniel',   'Hartmann',
            title_prefix='Mr.', date_of_birth=date(1978, 8, 25),
            bio='Chief Commercial Officer. Oversees all three subsidiaries revenue targets.',
            notes='Contact for group commercial strategy and pricing governance.')
        cfo    = person('p:cfo',    'Ingrid',   'Visser',
            title_prefix='Ms.', pronouns='she/her', date_of_birth=date(1980, 11, 3),
            bio='Group CFO. Responsible for treasury, consolidated reporting, tax, and M&A.',
            notes='Approves contracts above EUR 50k. Quarterly analyst calls.')
        cto    = person('p:cto',    'Lars',     'Brouwer',
            title_prefix='Mr.', date_of_birth=date(1982, 6, 17),
            bio='Group CTO. Leads ERP modernisation, e-commerce platforms, and IT infrastructure.',
            notes='Sponsor of current ERP rollout project.')
        cpo    = person('p:cpo',    'Amara',    'Osei',
            title_prefix='Ms.', pronouns='she/her', date_of_birth=date(1985, 2, 28),
            bio='Chief Product Officer. Drives product development roadmap and sustainability agenda.',
            notes='Key contact for new product introductions and supplier relations.')

        # Holding - Group Finance & Accounting (5 people)
        p_fin1 = person('p:fin:controller', 'Pieter', 'de Groot',
            title_prefix='Mr.', date_of_birth=date(1979, 9, 8),
            bio='Group financial controller. Manages intercompany eliminations and audit.',
            notes='Liaison for external auditors.')
        p_fin2 = person('p:fin:treasury', 'Nadine', 'Smits',
            title_prefix='Ms.', date_of_birth=date(1983, 5, 14),
            bio='Treasury & cash management. Manages group banking relationships.')
        p_fin3 = person('p:fin:tax', 'Thomas', 'Koch',
            title_prefix='Mr.', date_of_birth=date(1981, 3, 22),
            bio='Group tax manager. VAT compliance across NL/DE/BE/FR.')
        p_fin4 = person('p:fin:reporting', 'Yasmine', 'El-Amin',
            title_prefix='Ms.', pronouns='she/her', date_of_birth=date(1990, 7, 19),
            bio='Financial reporting analyst. Monthly P&L packs and board reporting.')
        p_fin5 = person('p:fin:ap', 'Joost', 'van Loon',
            title_prefix='Mr.', date_of_birth=date(1988, 12, 5),
            bio='AP/AR coordination at group level. Intercompany billing.')

        # Holding - People & Culture (5 people)
        p_hr1  = person('p:hr:head', 'Fatima', 'Yilmaz',
            title_prefix='Ms.', pronouns='she/her', date_of_birth=date(1980, 10, 15),
            bio='Head of People & Culture. Leads HR across all three subsidiaries.')
        p_hr2  = person('p:hr:recruit', 'Kevin', 'Janssen',
            title_prefix='Mr.', date_of_birth=date(1992, 4, 7),
            bio='Talent acquisition specialist. Focuses on commercial and ops roles.')
        p_hr3  = person('p:hr:ld', 'Chloe', 'Peters',
            title_prefix='Ms.', date_of_birth=date(1993, 8, 21),
            bio='L&D specialist. Onboarding, product knowledge training, management development.')
        p_hr4  = person('p:hr:comp', 'Mark', 'Bakker',
            title_prefix='Mr.', date_of_birth=date(1984, 1, 30),
            bio='Compensation & benefits manager.')
        p_hr5  = person('p:hr:partner', 'Sara', 'Lim',
            title_prefix='Ms.', pronouns='she/her', date_of_birth=date(1987, 6, 12),
            bio='HR business partner supporting NL subsidiary.')

        # Holding - Product & Brand (5 people)
        p_pd1  = person('p:pd:head', 'Mia', 'Vogel',
            title_prefix='Ms.', pronouns='she/her', date_of_birth=date(1983, 3, 9),
            bio='Head of Product. Manages seasonal range development and supplier samples.')
        p_pd2  = person('p:pd:design', 'Roel', 'Hendricks',
            title_prefix='Mr.', date_of_birth=date(1989, 11, 16),
            bio='Senior product designer. Responsible for packaging design and brand visual guidelines.')
        p_pd3  = person('p:pd:sustain', 'Priya', 'Sharma',
            title_prefix='Ms.', pronouns='she/her', date_of_birth=date(1991, 5, 4),
            bio='Sustainability coordinator. Certifications, material sourcing, carbon reporting.')
        p_pd4  = person('p:pd:ranging', 'Tom', 'Muller',
            title_prefix='Mr.', date_of_birth=date(1986, 8, 27),
            bio='Range manager for hydration and storage categories.')
        p_pd5  = person('p:pd:quality', 'Elena', 'Novak',
            title_prefix='Ms.', date_of_birth=date(1988, 2, 14),
            bio='Quality assurance manager. Pre-shipment inspections and compliance testing.')

        # Holding - IT & Digital (5 people)
        p_it1  = person('p:it:head', 'Alex', 'de Boer',
            title_prefix='Mx.', pronouns='they/them', date_of_birth=date(1987, 7, 23),
            bio='Head of IT & Digital. ERP programme lead.')
        p_it2  = person('p:it:erp', 'Nina', 'Schulz',
            title_prefix='Ms.', date_of_birth=date(1990, 9, 11),
            bio='ERP systems analyst. Manages NovaCRM/OPS configuration and rollout.')
        p_it3  = person('p:it:infra', 'Bas', 'van Rijn',
            title_prefix='Mr.', date_of_birth=date(1985, 4, 18),
            bio='Infrastructure & security engineer. Cloud, VPN, endpoint management.')
        p_it4  = person('p:it:ecom', 'Linh', 'Nguyen',
            title_prefix='Ms.', pronouns='she/her', date_of_birth=date(1993, 12, 2),
            bio='E-commerce & integrations developer. B2B portal and EDI connections.')
        p_it5  = person('p:it:support', 'Daan', 'Brink',
            title_prefix='Mr.', date_of_birth=date(1995, 3, 7),
            bio='IT support engineer. Helpdesk, device management, onboarding.')

        # Key external contacts
        ext_bloom_buyer = person('p:bloom:buyer', 'Charlotte', 'van der Meer',
            title_prefix='Ms.', pronouns='she/her', date_of_birth=date(1986, 5, 30),
            bio='Senior buyer at Bloom & Co. Manages homeware and lifestyle category.',
            notes='Key buying contact. Annual range review in September. Prefers digital samples first.')
        ext_bloom_ops   = person('p:bloom:ops', 'Henk', 'Oosterhout',
            title_prefix='Mr.', date_of_birth=date(1981, 10, 12),
            bio='Operations manager at Bloom & Co. Coordinates warehouse deliveries.',
            notes='Contact for delivery windows and routing.')
        ext_nordic_buyer = person('p:nordic:buyer', 'Astrid', 'Lindgren',
            title_prefix='Ms.', pronouns='she/her', date_of_birth=date(1984, 9, 18),
            bio='Head of buying at Nordic Home. Strong preference for FSC/recycled product lines.',
            notes='Buys seasonally. Sustainability certifications required for new listings.')
        ext_atelier_mgr = person('p:atelier:mgr', 'Isabelle', 'Dubois',
            title_prefix='Ms.', pronouns='she/her', date_of_birth=date(1979, 7, 4),
            bio='Managing director at Atelier Gifts & Interiors. Personally manages buying decisions.',
            notes='Prefers quarterly meeting. Makes final approval on all orders above EUR 5k.')
        ext_giftmore_buyer = person('p:giftmore:buyer', 'Klaus', 'Weber',
            title_prefix='Mr.', date_of_birth=date(1983, 2, 22),
            bio='Category buyer at Gift & More GmbH for home and lifestyle category.',
            notes='New contact. Met at Ambiente trade fair January 2026.')
        ext_fresh_ceo   = person('p:fresh:ceo', 'Robin', 'de Lange',
            title_prefix='Mx.', pronouns='they/them', date_of_birth=date(1990, 6, 8),
            bio='CEO & co-founder of Fresh Concepts Online. Evaluating wholesale programme.',
            notes='Decision maker. Wants dropship first, then wholesale. Follow up after quote Q-DEMO-0007.')
        ext_supplier_am = person('p:supplier:am', 'Vincent', 'Claes',
            title_prefix='Mr.', date_of_birth=date(1977, 11, 3),
            bio='Account manager at Premium Home Supplies BV. Manages Meridian Group account.',
            notes='Main contact for orders, lead times, and factory samples.')

        # ── Affiliations ───────────────────────────────────────────────────────
        for p_obj, o_obj, title, start in [
            (ceo,    holding,   'Chief Executive Officer',      date(2016, 3, 1)),
            (cco,    holding,   'Chief Commercial Officer',     date(2018, 6, 1)),
            (cfo,    holding,   'Chief Financial Officer',      date(2019, 1, 1)),
            (cto,    holding,   'Chief Technology Officer',     date(2020, 9, 1)),
            (cpo,    holding,   'Chief Product Officer',        date(2021, 4, 1)),
            (p_fin1, dept_finance, 'Group Financial Controller', date(2020, 2, 1)),
            (p_fin2, dept_finance, 'Treasury Manager',           date(2021, 5, 1)),
            (p_fin3, dept_finance, 'Group Tax Manager',          date(2022, 3, 1)),
            (p_fin4, dept_finance, 'Reporting Analyst',          date(2023, 1, 1)),
            (p_fin5, dept_finance, 'AP/AR Coordinator',          date(2023, 9, 1)),
            (p_hr1,  dept_hr,   'Head of People & Culture',     date(2019, 7, 1)),
            (p_hr2,  dept_hr,   'Talent Acquisition Specialist', date(2021, 3, 1)),
            (p_hr3,  dept_hr,   'L&D Specialist',               date(2022, 1, 1)),
            (p_hr4,  dept_hr,   'Compensation & Benefits Manager', date(2020, 8, 1)),
            (p_hr5,  dept_hr,   'HR Business Partner',          date(2023, 6, 1)),
            (p_pd1,  dept_product, 'Head of Product & Brand',   date(2019, 9, 1)),
            (p_pd2,  dept_product, 'Senior Product Designer',   date(2020, 4, 1)),
            (p_pd3,  dept_product, 'Sustainability Coordinator', date(2022, 2, 1)),
            (p_pd4,  dept_product, 'Range Manager',             date(2021, 11, 1)),
            (p_pd5,  dept_product, 'Quality Assurance Manager', date(2023, 3, 1)),
            (p_it1,  dept_it,   'Head of IT & Digital',         date(2020, 1, 1)),
            (p_it2,  dept_it,   'ERP Systems Analyst',          date(2021, 8, 1)),
            (p_it3,  dept_it,   'Infrastructure Engineer',      date(2020, 6, 1)),
            (p_it4,  dept_it,   'E-commerce Developer',         date(2022, 10, 1)),
            (p_it5,  dept_it,   'IT Support Engineer',          date(2024, 1, 1)),
            (ext_bloom_buyer, bloom, 'Senior Buyer - Homeware',  date(2020, 3, 1)),
            (ext_bloom_ops,   bloom, 'Operations Manager',       date(2018, 7, 1)),
            (ext_nordic_buyer, nordic, 'Head of Buying',         date(2019, 1, 1)),
            (ext_atelier_mgr, atelier, 'Managing Director',      date(2012, 5, 1)),
            (ext_giftmore_buyer, gift_more, 'Category Buyer',    date(2023, 4, 1)),
            (ext_fresh_ceo,  fresh, 'CEO & Co-founder',          date(2018, 9, 1)),
            (ext_supplier_am, supplier, 'Account Manager',       date(2019, 6, 1)),
        ]:
            Affiliation.objects.update_or_create(
                person=p_obj, organization=o_obj,
                defaults={'job_title': title, 'start_date': start,
                          'end_date': None, 'is_primary': True, 'notes': ''},
            )

        person_ct = ContentType.objects.get_for_model(Person)
        org_ct    = ContentType.objects.get_for_model(Organization)

        # ── Communications ─────────────────────────────────────────────────────
        for p_obj, ctype, value, label, primary in [
            (ceo,    CommunicationType.EMAIL, 'sophie.vandenberg@meridiangroup.example', 'Direct', True),
            (ceo,    CommunicationType.PHONE, '+31 20 800 0001', 'Mobile', True),
            (cco,    CommunicationType.EMAIL, 'daniel.hartmann@meridiangroup.example',  'Work', True),
            (cfo,    CommunicationType.EMAIL, 'ingrid.visser@meridiangroup.example',    'Work', True),
            (cfo,    CommunicationType.PHONE, '+31 20 800 0003', 'Direct', False),
            (cto,    CommunicationType.EMAIL, 'lars.brouwer@meridiangroup.example',     'Work', True),
            (cpo,    CommunicationType.EMAIL, 'amara.osei@meridiangroup.example',       'Work', True),
            (ext_bloom_buyer, CommunicationType.EMAIL, 'charlotte.vandermeer@bloomandco.example', 'Work', True),
            (ext_bloom_buyer, CommunicationType.PHONE, '+31 23 555 0101', 'Direct', False),
            (ext_bloom_ops,   CommunicationType.EMAIL, 'henk.oosterhout@bloomandco.example', 'Work', True),
            (ext_nordic_buyer,CommunicationType.EMAIL, 'astrid.lindgren@nordichome.example', 'Work', True),
            (ext_nordic_buyer,CommunicationType.PHONE, '+31 35 555 0201', 'Direct', False),
            (ext_atelier_mgr, CommunicationType.EMAIL, 'isabelle.dubois@ateliergifts.example', 'Work', True),
            (ext_atelier_mgr, CommunicationType.PHONE, '+32 2 555 0301', 'Direct', True),
            (ext_giftmore_buyer, CommunicationType.EMAIL, 'k.weber@giftmore.example', 'Work', True),
            (ext_fresh_ceo,  CommunicationType.EMAIL, 'robin@freshconcepts.example', 'Work', True),
            (ext_supplier_am,CommunicationType.EMAIL, 'v.claes@premiumhome.example', 'Work', True),
            (ext_supplier_am,CommunicationType.PHONE, '+31 10 555 0401', 'Direct', True),
        ]:
            _comm(person_ct, p_obj.id, comm_type=ctype, value=value, label=label, primary=primary)

        for o_obj, ctype, value, label, primary in [
            (holding, CommunicationType.EMAIL, 'info@meridiangroup.example', 'General', True),
            (holding, CommunicationType.PHONE, '+31 20 800 0000', 'Reception', True),
            (sub_nl,  CommunicationType.EMAIL, 'sales@meridian-nl.example',  'Sales', True),
            (sub_nl,  CommunicationType.PHONE, '+31 20 800 0100', 'Main', True),
            (sub_de,  CommunicationType.EMAIL, 'vertrieb@meridian-de.example', 'Sales', True),
            (sub_de,  CommunicationType.PHONE, '+49 40 800 0200', 'Main', True),
            (sub_be,  CommunicationType.EMAIL, 'ventes@meridian-be.example', 'Sales', True),
            (bloom,   CommunicationType.PHONE, '+31 23 555 0100', 'HQ', True),
            (bloom,   CommunicationType.EMAIL, 'inkoop@bloomandco.example', 'Buying', True),
            (nordic,  CommunicationType.EMAIL, 'buying@nordichome.example', 'Buying', True),
            (atelier, CommunicationType.EMAIL, 'bestelling@ateliergifts.example', 'Orders', True),
            (supplier,CommunicationType.EMAIL, 'sales@premiumhomesupplies.example', 'Sales', True),
            (supplier,CommunicationType.PHONE, '+31 10 555 0400', 'Main', True),
            (fresh,   CommunicationType.EMAIL, 'wholesale@freshconcepts.example', 'Wholesale', True),
        ]:
            _comm(org_ct, o_obj.id, comm_type=ctype, value=value, label=label, primary=primary)

        # ── Addresses ──────────────────────────────────────────────────────────
        _addr(org_ct, holding.id, address_type=AddressType.VISITING,
              street='Keizersgracht 456', zipcode='1017 DW', city='Amsterdam', label='HQ',
              state_province='North Holland')
        _addr(org_ct, sub_nl.id, address_type=AddressType.VISITING,
              street='Avelingen-West 30', zipcode='4202 MS', city='Gorinchem', label='Office',
              state_province='South Holland')
        _addr(org_ct, sub_nl.id, address_type=AddressType.SHIPPING,
              street='Avelingen-West 30', zipcode='4202 MS', city='Gorinchem',
              label='NL Warehouse', street2='Loading dock A', state_province='South Holland')
        _addr(org_ct, sub_de.id, address_type=AddressType.VISITING,
              street='Brookdeich 12', zipcode='20457', city='Hamburg',
              country='Germany', label='DE Office', state_province='Hamburg')
        _addr(org_ct, sub_be.id, address_type=AddressType.VISITING,
              street='Rue du Commerce 88', zipcode='1000', city='Brussels',
              country='Belgium', label='BE Office')
        _addr(org_ct, bloom.id, address_type=AddressType.VISITING,
              street='Bloemenweg 14', zipcode='2012 AP', city='Haarlem', label='HQ')
        _addr(org_ct, bloom.id, address_type=AddressType.BILLING,
              street='Postbus 1001', zipcode='2000 AA', city='Haarlem', label='AP/AR')
        _addr(org_ct, bloom.id, address_type=AddressType.SHIPPING,
              street='Logistiekstraat 3', zipcode='2031 BK', city='Haarlem',
              label='Warehouse', street2='Dock 2')
        _addr(org_ct, nordic.id, address_type=AddressType.VISITING,
              street='Zuiderweg 22', zipcode='1321 JH', city='Almere', label='HQ')
        _addr(org_ct, atelier.id, address_type=AddressType.VISITING,
              street='Rue Neuve 200', zipcode='1000', city='Brussels',
              country='Belgium', label='HQ')
        _addr(org_ct, supplier.id, address_type=AddressType.VISITING,
              street='Industrieweg 55', zipcode='3133 AT', city='Vlaardingen',
              label='Warehouse & Office', state_province='South Holland')

        # ── Social profiles ────────────────────────────────────────────────────
        for o_obj, platform, url, handle in [
            (holding, 'LinkedIn', 'https://www.linkedin.com/company/meridian-group-demo/', 'meridian-group'),
            (sub_nl,  'Instagram', 'https://www.instagram.com/meridianliving.nl/', 'meridianliving.nl'),
            (bloom,   'LinkedIn', 'https://www.linkedin.com/company/bloom-co-demo/', 'bloom-co'),
        ]:
            SocialProfile.objects.update_or_create(
                content_type=org_ct, object_id=o_obj.id, platform=platform,
                defaults={'url': url, 'handle': handle},
            )

        SpecialEvent.objects.update_or_create(person=ceo, name='Company founding anniversary',
            defaults={'event_date': date(2016, 3, 1),
                      'notes': 'Meridian Group founded March 2016. Annual team celebration.'})
        SpecialEvent.objects.update_or_create(person=ext_bloom_buyer, name='Annual range review',
            defaults={'event_date': None,
                      'notes': 'Happens each September. Prepare new season catalogue beforehand.'})

        self.stdout.write(
            f'    {Organization.objects.count()} organisations, '
            f'{Person.objects.count()} contacts, '
            f'{Affiliation.objects.count()} affiliations'
        )

    # ── INVENTORY ──────────────────────────────────────────────────────────────

    def _seed_inventory(self) -> None:
        self.stdout.write('  Seeding inventory...')
        User = get_user_model()
        user = User.objects.filter(is_superuser=True).first() or User.objects.order_by('id').first()

        wh_nl, _ = Warehouse.objects.update_or_create(
            code='WH-NL', defaults={
                'name': 'Gorinchem Warehouse (NL)',
                'address_line1': 'Avelingen-West 30',
                'city': 'Gorinchem', 'country': 'Netherlands',
                'notes': 'Main distribution warehouse. Handles all NL and export orders.',
                'is_active': True,
            })
        wh_de, _ = Warehouse.objects.update_or_create(
            code='WH-DE', defaults={
                'name': 'Hamburg Warehouse (DE)',
                'address_line1': 'Brookdeich 12',
                'city': 'Hamburg', 'country': 'Germany',
                'notes': 'DACH distribution centre. Cross-dock for DE/AT/CH orders.',
                'is_active': True,
            })

        def loc(warehouse, code, name):
            obj, _ = StockLocation.objects.update_or_create(
                warehouse=warehouse, code=code, defaults={'name': name, 'is_active': True})
            return obj

        # NL locations
        nl_a01 = loc(wh_nl, 'A-01', 'Aisle A - Hydration products')
        nl_b01 = loc(wh_nl, 'B-01', 'Aisle B - Ceramics & stationery')
        nl_b02 = loc(wh_nl, 'B-02', 'Aisle B - Stationery & accessories')
        nl_c01 = loc(wh_nl, 'C-01', 'Aisle C - Gift sets & bundles')
        nl_incoming = loc(wh_nl, 'INCOMING', 'Goods-in holding area')
        # DE locations
        de_a01 = loc(wh_de, 'A-01', 'DE - Hydration')
        de_b01 = loc(wh_de, 'B-01', 'DE - Ceramics & stationery')

        def prod(sku): return Product.objects.filter(sku=sku).first()

        # Stock levels with movements
        stock_data = [
            # (product_sku, location, qty_on_hand, movement_ref)
            ('MERID-BTL-500',    nl_a01, Decimal('384'), 'PO-DEMO-0001'),
            ('MERID-BTL-750',    nl_a01, Decimal('228'), 'PO-DEMO-0001'),
            ('MERID-STA-CLASSIC',nl_b02, Decimal('156'), 'PO-DEMO-0002'),
            ('MERID-CAN-SM',     nl_b01, Decimal('312'), 'PO-DEMO-0002'),
            ('MERID-CAN-LG',     nl_b01, Decimal('204'), 'PO-DEMO-0002'),
            ('MERID-NBOOK-A5',   nl_b02, Decimal('480'), 'PO-DEMO-0001'),
            ('MERID-BRUSH-WD',   nl_b02, Decimal('144'), 'PO-DEMO-0002'),
            ('MERID-PLANT-12',   nl_b01, Decimal('96'),  'PO-DEMO-0002'),
            ('MERID-GIFT-DESK',  nl_c01, Decimal('48'),  'PO-DEMO-0003'),
            ('MERID-GIFT-KITCHEN',nl_c01,Decimal('60'),  'PO-DEMO-0003'),
            ('MERID-GIFT-WELLNESS',nl_c01,Decimal('36'), 'PO-DEMO-0003'),
            ('MERID-SEAS-WINTER', nl_c01,Decimal('72'),  'PO-DEMO-0003'),
            ('MERID-BTL-TRAVL',  nl_a01, Decimal('240'), 'PO-DEMO-0001'),
            # DE stock
            ('MERID-BTL-500',    de_a01, Decimal('120'), 'PO-DEMO-0001'),
            ('MERID-BTL-750',    de_a01, Decimal('84'),  'PO-DEMO-0001'),
            ('MERID-STA-CLASSIC',de_b01, Decimal('60'),  'PO-DEMO-0002'),
            ('MERID-CAN-SM',     de_b01, Decimal('96'),  'PO-DEMO-0002'),
            ('MERID-CAN-LG',     de_b01, Decimal('60'),  'PO-DEMO-0002'),
        ]

        for sku, location, qty, ref in stock_data:
            product = prod(sku)
            if not product:
                continue
            entry, _ = StockEntry.objects.update_or_create(
                product=product, location=location,
                defaults={'quantity_on_hand': qty},
            )
            StockMovement.objects.get_or_create(
                id=_inv_uuid(f'rcpt:{sku}:{location.code}'),
                defaults={
                    'product': product, 'location': location,
                    'delta': qty, 'movement_type': MovementType.RECEIPT,
                    'reference': ref, 'created_by': user,
                    'notes': 'Initial stock receipt - demo seed',
                },
            )

        self.stdout.write(
            f'    {Warehouse.objects.count()} warehouses, '
            f'{StockLocation.objects.count()} locations, '
            f'{StockEntry.objects.count()} stock entries'
        )

    # ── PROCUREMENT ────────────────────────────────────────────────────────────

    def _seed_procurement(self) -> None:
        self.stdout.write('  Seeding procurement...')
        User = get_user_model()
        user = User.objects.filter(is_superuser=True).first() or User.objects.order_by('id').first()
        if not user:
            return

        supplier = Organization.objects.filter(pk=_rel_uuid('org:premium-home-supplies')).first()

        def prod(sku): return Product.objects.filter(sku=sku).first()

        # PO1 - Received: hydration + stationery replenishment
        po1, _ = PurchaseOrder.objects.get_or_create(
            id=_prc_uuid('po1'),
            defaults={
                'ref': _REFS['po1'], 'supplier': supplier,
                'status': POStatus.RECEIVED,
                'expected_delivery_date': date(2026, 2, 10),
                'notes': 'Q1 2026 stock replenishment - hydration and stationery lines.',
                'created_by': user,
            },
        )
        for sku, qty, unit_cost in [
            ('MERID-BTL-500',  500, Decimal('7.50')),
            ('MERID-BTL-750',  300, Decimal('9.20')),
            ('MERID-NBOOK-A5', 600, Decimal('2.90')),
            ('MERID-BTL-TRAVL',300, Decimal('2.10')),
        ]:
            product = prod(sku)
            if product:
                PurchaseOrderLine.objects.get_or_create(
                    id=_prc_uuid(f'po1:{sku}'),
                    defaults={
                        'purchase_order': po1, 'product': product,
                        'description': product.name,
                        'qty_ordered': Decimal(str(qty)),
                        'qty_received': Decimal(str(qty)),
                        'unit_cost': unit_cost,
                    },
                )

        # PO2 - Received: ceramics and accessories
        po2, _ = PurchaseOrder.objects.get_or_create(
            id=_prc_uuid('po2'),
            defaults={
                'ref': _REFS['po2'], 'supplier': supplier,
                'status': POStatus.RECEIVED,
                'expected_delivery_date': date(2026, 2, 28),
                'notes': 'Q1 2026 ceramics, stationery sets, brushes, plant pots.',
                'created_by': user,
            },
        )
        for sku, qty, unit_cost in [
            ('MERID-STA-CLASSIC', 200, Decimal('12.40')),
            ('MERID-CAN-SM',      400, Decimal('5.80')),
            ('MERID-CAN-LG',      264, Decimal('8.40')),
            ('MERID-BRUSH-WD',    180, Decimal('6.20')),
            ('MERID-PLANT-12',    120, Decimal('4.10')),
        ]:
            product = prod(sku)
            if product:
                PurchaseOrderLine.objects.get_or_create(
                    id=_prc_uuid(f'po2:{sku}'),
                    defaults={
                        'purchase_order': po2, 'product': product,
                        'description': product.name,
                        'qty_ordered': Decimal(str(qty)),
                        'qty_received': Decimal(str(qty)),
                        'unit_cost': unit_cost,
                    },
                )

        # PO3 - Partial: gift sets and seasonal (pre-assembled, delivery in progress)
        po3, _ = PurchaseOrder.objects.get_or_create(
            id=_prc_uuid('po3'),
            defaults={
                'ref': _REFS['po3'], 'supplier': supplier,
                'status': POStatus.PARTIAL,
                'expected_delivery_date': date(2026, 4, 20),
                'notes': 'Q2 2026 gift set assembly order. Seasonal winter boxes included. Partial delivery received.',
                'created_by': user,
            },
        )
        for sku, qty_ord, qty_rcv, unit_cost in [
            ('MERID-GIFT-DESK',    120, 48,  Decimal('24.50')),
            ('MERID-GIFT-KITCHEN', 120, 60,  Decimal('17.80')),
            ('MERID-GIFT-WELLNESS',120, 36,  Decimal('19.90')),
            ('MERID-SEAS-WINTER',  144, 72,  Decimal('22.00')),
        ]:
            product = prod(sku)
            if product:
                PurchaseOrderLine.objects.get_or_create(
                    id=_prc_uuid(f'po3:{sku}'),
                    defaults={
                        'purchase_order': po3, 'product': product,
                        'description': product.name,
                        'qty_ordered': Decimal(str(qty_ord)),
                        'qty_received': Decimal(str(qty_rcv)),
                        'unit_cost': unit_cost,
                    },
                )

        self.stdout.write(
            f'    {PurchaseOrder.objects.count()} purchase orders, '
            f'{PurchaseOrderLine.objects.count()} lines'
        )

    # ── ASSETS ─────────────────────────────────────────────────────────────────

    def _seed_assets(self) -> None:
        self.stdout.write('  Seeding assets...')
        User = get_user_model()
        user = User.objects.filter(is_superuser=True).first() or User.objects.order_by('id').first()
        if not user:
            return

        sub_nl = Organization.objects.filter(pk=_rel_uuid('org:meridian-nl')).first()
        sub_de = Organization.objects.filter(pk=_rel_uuid('org:meridian-de')).first()
        if not sub_nl:
            return

        def prod(sku): return Product.objects.filter(sku=sku).first()
        disp_stand = prod('MERID-DISP-STAND')

        # Recall campaign for a fictional batch defect
        recall, _ = RecallCampaign.objects.get_or_create(
            pk=_ast_uuid('recall:demo-canister-lid-2026'),
            defaults={
                'reference': _REFS['recall_1'],
                'title': 'Demo: Ceramic Canister lid seal inspection (fictional)',
                'description': 'Illustrative recall - silicone seal on batch CAN-SM-2025-B04 may not meet food-grade spec.',
                'remedy_description': 'Inspect lid seal; replace affected batch lids free of charge.',
                'product': prod('MERID-CAN-SM'),
                'announced_date': date(2026, 3, 1),
                'is_active': True,
                'created_by': user,
            },
        )

        def make_asset(key, org, product, serial, tag, purchase_dt, install_dt,
                       warranty_end, status, location, notes, events):
            asset, _ = Asset.objects.update_or_create(
                pk=_ast_uuid(key),
                defaults={
                    'organization': org, 'product': product, 'name': '',
                    'serial_number': serial, 'asset_tag': tag,
                    'purchase_date': purchase_dt, 'installation_date': install_dt,
                    'warranty_end_date': warranty_end, 'expected_end_of_life_date': None,
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

        # NL warehouse display stands (used internally for trade fair / showroom)
        a_stand_nl1 = make_asset(
            'asset:nl:stand-01', sub_nl, disp_stand,
            'STAND-NL-SN-001', 'NL-SHOW-001',
            date(2025, 3, 1), date(2025, 3, 5), date(2027, 3, 1),
            AssetStatus.IN_SERVICE, 'NL Showroom - bottle display row',
            'Meridian floor stand - main showroom demo unit.',
            [
                ('install', AssetEventType.INSTALLATION, 'Installed in NL showroom',
                 'Configured with bottle and canister display units.', date(2025, 3, 5)),
                ('inspect-2026', AssetEventType.INSPECTION, 'Annual condition check',
                 'Good condition. Header card replaced.', date(2026, 1, 10)),
            ],
        )
        make_asset(
            'asset:nl:stand-02', sub_nl, disp_stand,
            'STAND-NL-SN-002', 'NL-SHOW-002',
            date(2025, 3, 1), date(2025, 3, 5), date(2027, 3, 1),
            AssetStatus.IN_SERVICE, 'NL Showroom - gift set display row',
            'Second floor stand - gift sets and seasonal.',
            [
                ('install', AssetEventType.INSTALLATION, 'Installed', '', date(2025, 3, 5)),
            ],
        )
        if sub_de:
            make_asset(
                'asset:de:stand-01', sub_de, disp_stand,
                'STAND-DE-SN-001', 'DE-SHOW-001',
                date(2025, 6, 1), date(2025, 6, 10), date(2027, 6, 1),
                AssetStatus.IN_SERVICE, 'DE Showroom - Hamburg',
                'Display stand for DACH showroom.',
                [
                    ('install', AssetEventType.INSTALLATION, 'Installed DE showroom',
                     'Set up for Ambiente follow-up presentations.', date(2025, 6, 10)),
                ],
            )

        # Maintenance plan for NL showroom stands
        plan, _ = MaintenancePlan.objects.get_or_create(
            pk=_ast_uuid('mjop:nl:showroom-2026-2028'),
            defaults={
                'reference':   _REFS['mjop_1'],
                'organization': sub_nl,
                'name':        'NL Showroom - display stand maintenance 2026-2028 (demo)',
                'valid_from':  date(2026, 1, 1),
                'valid_until': date(2028, 12, 31),
                'status':      MaintenancePlanStatus.ACTIVE,
                'notes':       'Annual inspection and refurbishment of showroom display assets.',
                'created_by':  user,
            },
        )
        for pk_key, year, sort, title, desc, asset_obj, line_status in [
            ('line:2026:inspect', 2026, 1, 'Annual display stand inspection',
             'Check structural condition, replace worn header cards and price holders.',
             a_stand_nl1, MaintenancePlanLineStatus.PLANNED),
            ('line:2027:inspect', 2027, 1, 'Annual display stand inspection',
             'As above - assess need for full refurbishment.',
             a_stand_nl1, MaintenancePlanLineStatus.PLANNED),
            ('line:2027:refresh', 2027, 2, 'Showroom refresh (PROMOTED)',
             'Consider full stand replacement ahead of 2028 trade fair season.',
             None, MaintenancePlanLineStatus.PLANNED),
        ]:
            MaintenancePlanLine.objects.update_or_create(
                pk=_ast_uuid(pk_key),
                defaults={
                    'plan': plan, 'plan_year': year, 'sort_order': sort,
                    'title': title, 'description': desc,
                    'related_asset': asset_obj, 'recommended_product': disp_stand,
                    'is_promoted': (sort == 2), 'estimated_cost_note': 'TBD',
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
        self.stdout.write('  Seeding sales pipeline...')
        User = get_user_model()
        user = User.objects.filter(is_superuser=True).first() or User.objects.order_by('id').first()
        if not user:
            self.stdout.write(self.style.WARNING('    No user found - skipping sales.'))
            return

        bloom   = Organization.objects.filter(pk=_rel_uuid('org:bloom-co')).first()
        nordic  = Organization.objects.filter(pk=_rel_uuid('org:nordic-home')).first()
        atelier = Organization.objects.filter(pk=_rel_uuid('org:atelier-gifts')).first()
        giftmore= Organization.objects.filter(pk=_rel_uuid('org:gift-more-de')).first()
        fresh   = Organization.objects.filter(pk=_rel_uuid('org:fresh-concepts')).first()
        maison  = Organization.objects.filter(pk=_rel_uuid('org:maison-deco')).first()

        def prod(sku): return Product.objects.filter(sku=sku).first()

        btl500    = prod('MERID-BTL-500')
        btl750    = prod('MERID-BTL-750')
        sta_set   = prod('MERID-STA-CLASSIC')
        can_sm    = prod('MERID-CAN-SM')
        can_lg    = prod('MERID-CAN-LG')
        nbook     = prod('MERID-NBOOK-A5')
        brush_set = prod('MERID-BRUSH-WD')
        plant_pot = prod('MERID-PLANT-12')
        gift_desk = prod('MERID-GIFT-DESK')
        gift_kit  = prod('MERID-GIFT-KITCHEN')
        gift_well = prod('MERID-GIFT-WELLNESS')
        seasonal  = prod('MERID-SEAS-WINTER')

        def qline(quote, product, qty, sort, discount_pct=Decimal('0')):
            if not product:
                return None
            data = snapshot_line_from_product(product, qty)
            if discount_pct:
                disc = (data['unit_price'] * discount_pct / Decimal('100')).quantize(Decimal('0.01'))
                data['unit_price'] -= disc
                data['line_total'] = (data['unit_price'] * qty).quantize(Decimal('0.01'))
            obj, _ = QuoteLine.objects.update_or_create(
                pk=_sal_uuid(f'ql:{quote.pk}:{product.pk}:{sort}'),
                defaults={**data, 'quote': quote, 'sort_order': sort},
            )
            return obj

        def oline(order, product, qty, sort):
            if not product:
                return None
            data = snapshot_line_from_product(product, qty)
            obj, _ = OrderLine.objects.update_or_create(
                pk=_sal_uuid(f'ol:{order.pk}:{product.pk}:{sort}'),
                defaults={**data, 'order': order, 'sort_order': sort},
            )
            return obj

        def fo_line(fo, order_line, loc_code, sort):
            if not order_line:
                return None
            obj, _ = FulfillmentOrderLine.objects.update_or_create(
                pk=_sal_uuid(f'fol:{fo.pk}:{order_line.pk}'),
                defaults={
                    'fulfillment_order': fo,
                    'product': order_line.product,
                    'product_name': order_line.product_name,
                    'sku': order_line.sku,
                    'brand': order_line.brand or '',
                    'quantity': int(order_line.quantity),
                    'warehouse_location': loc_code,
                    'sort_order': sort,
                },
            )
            return obj

        def shol(sho, fol):
            if not fol:
                return None
            obj, _ = ShippingOrderLine.objects.update_or_create(
                pk=_sal_uuid(f'shol:{sho.pk}:{fol.pk}'),
                defaults={'shipping_order': sho, 'fulfillment_line': fol,
                          'quantity': fol.quantity},
            )
            return obj

        def inv_line(invoice, ol, sort):
            if not ol:
                return None
            obj, _ = InvoiceLine.objects.update_or_create(
                pk=_sal_uuid(f'il:{invoice.pk}:{ol.pk}'),
                defaults={
                    'invoice': invoice, 'product': ol.product,
                    'product_name': ol.product_name, 'sku': ol.sku,
                    'brand': ol.brand or '', 'quantity': ol.quantity,
                    'unit_price': ol.unit_price, 'currency': ol.currency,
                    'line_total': ol.line_total, 'sort_order': sort,
                },
            )
            return obj

        def payment(invoice, amount, ref):
            InvoicePayment.objects.update_or_create(
                pk=_sal_uuid(f'pay:{invoice.pk}:{ref}'),
                defaults={'invoice': invoice, 'amount': amount,
                          'reference_note': ref, 'created_by': user},
            )

        # ── Q1: Bloom & Co. - Annual catalogue order (ACCEPTED) ───────────────
        q1, _ = Quote.objects.update_or_create(
            pk=_sal_uuid('quote:bloom-annual-2026'),
            defaults={
                'reference': _REFS['q1'], 'created_by': user,
                'relation_organization': bloom, 'status': QuoteStatus.ACCEPTED,
                'valid_until': date(2026, 3, 31),
                'internal_reference': 'BLOOM-2026-ANN',
                'notes': 'Annual catalogue order - 24 stores. Confirmed by Charlotte van der Meer 20 Feb.',
            },
        )
        qline(q1, btl500, 288, 0)
        qline(q1, btl750, 144, 1)
        qline(q1, can_sm, 144, 2)
        qline(q1, can_lg, 96,  3)
        qline(q1, gift_desk, 48, 4, Decimal('5'))
        qline(q1, gift_kit,  48, 5, Decimal('5'))

        # ── Q2: Nordic Home - Sustainable range proposal (SENT) ───────────────
        q2, _ = Quote.objects.update_or_create(
            pk=_sal_uuid('quote:nordic-sustainable-2026'),
            defaults={
                'reference': _REFS['q2'], 'created_by': user,
                'relation_organization': nordic, 'status': QuoteStatus.SENT,
                'valid_until': date(2026, 5, 15),
                'internal_reference': 'NORDIC-2026-Q1',
                'notes': 'Sustainable product range proposal. Awaiting Astrid Lindgren sign-off.',
            },
        )
        qline(q2, nbook,    120, 0)
        qline(q2, brush_set, 72, 1)
        qline(q2, plant_pot, 60, 2)
        qline(q2, sta_set,   48, 3)
        qline(q2, gift_well, 24, 4, Decimal('3'))

        # ── Q3: Atelier Gifts BE - Seasonal gift sets (ACCEPTED) ──────────────
        q3, _ = Quote.objects.update_or_create(
            pk=_sal_uuid('quote:atelier-seasonal-2026'),
            defaults={
                'reference': _REFS['q3'], 'created_by': user,
                'relation_organization': atelier, 'status': QuoteStatus.ACCEPTED,
                'valid_until': date(2026, 4, 30),
                'internal_reference': 'ATL-2026-S1',
                'notes': 'Spring/summer seasonal gift sets. Isabelle approved. Agreed 5% volume discount.',
            },
        )
        qline(q3, gift_kit,  60, 0, Decimal('5'))
        qline(q3, gift_well, 60, 1, Decimal('5'))
        qline(q3, seasonal,  36, 2, Decimal('5'))

        # ── Q4: Gift & More DE - New account first order (SENT) ───────────────
        q4, _ = Quote.objects.update_or_create(
            pk=_sal_uuid('quote:giftmore-intro-2026'),
            defaults={
                'reference': _REFS['q4'], 'created_by': user,
                'relation_organization': giftmore, 'status': QuoteStatus.SENT,
                'valid_until': date(2026, 5, 1),
                'internal_reference': 'GIFT-DE-2026-01',
                'notes': 'Introductory order following Ambiente fair. Follow up Klaus Weber w/c 14 Apr.',
            },
        )
        qline(q4, btl500, 120, 0)
        qline(q4, btl750, 60,  1)
        qline(q4, can_sm, 60,  2)
        qline(q4, can_lg, 36,  3)

        # ── Q5: Fresh Concepts - Wholesale programme proposal (DRAFT) ─────────
        q5, _ = Quote.objects.update_or_create(
            pk=_sal_uuid('quote:fresh-wholesale-2026'),
            defaults={
                'reference': _REFS['q5'], 'created_by': user,
                'relation_organization': fresh, 'status': QuoteStatus.DRAFT,
                'valid_until': date(2026, 6, 30),
                'internal_reference': 'FRESH-2026-WHLSL',
                'notes': 'Draft wholesale programme quote - pending commercial terms approval by CCO.',
            },
        )
        qline(q5, btl500, 240, 0, Decimal('10'))
        qline(q5, btl750, 120, 1, Decimal('10'))
        qline(q5, gift_well, 48, 2, Decimal('8'))

        # ── Q6: Maison Deco - Premium line (EXPIRED) ──────────────────────────
        q6, _ = Quote.objects.update_or_create(
            pk=_sal_uuid('quote:maison-premium-2025'),
            defaults={
                'reference': _REFS['q6'], 'created_by': user,
                'relation_organization': maison, 'status': QuoteStatus.EXPIRED,
                'valid_until': date(2025, 12, 31),
                'internal_reference': 'MAISON-2025-Q4',
                'notes': 'Expired - customer requested updated pricing for 2026 season. New quote to follow.',
            },
        )
        qline(q6, sta_set,  36, 0)
        qline(q6, gift_desk,24, 1)

        # ── Q7: Nordic Home - Hydration reorder (SENT) ────────────────────────
        q7, _ = Quote.objects.update_or_create(
            pk=_sal_uuid('quote:nordic-hydration-q2-2026'),
            defaults={
                'reference': _REFS['q7'], 'created_by': user,
                'relation_organization': nordic, 'status': QuoteStatus.SENT,
                'valid_until': date(2026, 5, 31),
                'internal_reference': 'NORDIC-2026-Q2',
                'notes': 'Q2 hydration reorder - bottle line performing well in NL stores.',
            },
        )
        qline(q7, btl500, 96, 0)
        qline(q7, btl750, 72, 1)

        # ── Q8: Bloom & Co. - Gift set top-up (ACCEPTED) ──────────────────────
        q8, _ = Quote.objects.update_or_create(
            pk=_sal_uuid('quote:bloom-giftset-topup-2026'),
            defaults={
                'reference': _REFS['q8'], 'created_by': user,
                'relation_organization': bloom, 'status': QuoteStatus.ACCEPTED,
                'valid_until': date(2026, 4, 30),
                'internal_reference': 'BLOOM-2026-TOP',
                'notes': 'Gift set top-up order - Wellness Bundle sold out faster than expected.',
            },
        )
        qline(q8, gift_well, 48, 0)
        qline(q8, seasonal,  24, 1)

        # ── SO1: Bloom annual (from Q1) - FULFILLED ───────────────────────────
        so1, _ = SalesOrder.objects.update_or_create(
            pk=_sal_uuid('order:bloom-annual-2026'),
            defaults={
                'reference': _REFS['so1'], 'created_by': user, 'quote': q1,
                'relation_organization': bloom, 'status': OrderStatus.FULFILLED,
                'notes': f'From {q1.reference}. Annual catalogue order - 24 stores.',
            },
        )
        ol_btl500 = oline(so1, btl500, 288, 0)
        ol_btl750 = oline(so1, btl750, 144, 1)
        ol_can_sm = oline(so1, can_sm,  144, 2)
        ol_can_lg = oline(so1, can_lg,   96, 3)
        ol_gdesk  = oline(so1, gift_desk, 48, 4)
        ol_gkit   = oline(so1, gift_kit,  48, 5)

        fo1, _ = FulfillmentOrder.objects.update_or_create(
            pk=_sal_uuid('fo:bloom-annual-2026'),
            defaults={
                'reference': _REFS['fo1'], 'sales_order': so1, 'created_by': user,
                'status': FulfillmentOrderStatus.COMPLETED,
                'notes': 'Full order picked and dispatched in two consignments.',
            },
        )
        fol_btl500 = fo_line(fo1, ol_btl500, 'A-01', 0)
        fol_btl750 = fo_line(fo1, ol_btl750, 'A-01', 1)
        fol_can_sm = fo_line(fo1, ol_can_sm,  'B-01', 2)
        fol_can_lg = fo_line(fo1, ol_can_lg,  'B-01', 3)
        fol_gdesk  = fo_line(fo1, ol_gdesk,   'C-01', 4)
        fol_gkit   = fo_line(fo1, ol_gkit,    'C-01', 5)

        sho1, _ = ShippingOrder.objects.update_or_create(
            pk=_sal_uuid('sho:bloom-annual-2026'),
            defaults={
                'reference': _REFS['sho1'], 'fulfillment_order': fo1, 'sales_order': so1,
                'created_by': user, 'status': ShippingOrderStatus.SHIPPED,
                'notes': 'Shipped in two pallets via DHL Freight.',
            },
        )
        sh1_lines = [shol(sho1, f) for f in [fol_btl500, fol_btl750, fol_can_sm, fol_can_lg, fol_gdesk, fol_gkit]]
        sh1, _ = Shipment.objects.update_or_create(
            pk=_sal_uuid('sh:bloom-annual-2026'),
            defaults={
                'shipping_order': sho1, 'sequence': 1, 'carrier': 'DHL Freight',
                'tracking_number': 'JD0001000000001', 'status': ShipmentStatus.DELIVERED,
                'notes': 'Delivered 2026-03-05 to Bloom Haarlem warehouse dock 2.',
            },
        )
        for sl in sh1_lines:
            if sl:
                ShipmentLine.objects.update_or_create(
                    pk=_sal_uuid(f'shl:{sh1.pk}:{sl.pk}'),
                    defaults={'shipment': sh1, 'shipping_order_line': sl, 'quantity': sl.quantity},
                )

        inv1, _ = Invoice.objects.update_or_create(
            pk=_sal_uuid('inv:bloom-annual-2026'),
            defaults={
                'reference': _REFS['inv1'], 'order': so1, 'created_by': user,
                'relation_organization': bloom, 'status': InvoiceStatus.ISSUED,
                'currency': 'EUR', 'due_date': date(2026, 4, 5),
            },
        )
        for i, ol in enumerate(ol for ol in [ol_btl500, ol_btl750, ol_can_sm, ol_can_lg, ol_gdesk, ol_gkit] if ol):
            inv_line(inv1, ol, i)
        inv1_total = sum(ol.line_total for ol in [ol_btl500, ol_btl750, ol_can_sm, ol_can_lg, ol_gdesk, ol_gkit] if ol)
        payment(inv1, inv1_total.quantize(Decimal('0.01')), 'Bank transfer BLOOM-AP-2026-0305')

        # ── SO2: Atelier seasonal (from Q3) - CONFIRMED, fulfillment in progress
        so2, _ = SalesOrder.objects.update_or_create(
            pk=_sal_uuid('order:atelier-seasonal-2026'),
            defaults={
                'reference': _REFS['so2'], 'created_by': user, 'quote': q3,
                'relation_organization': atelier, 'status': OrderStatus.CONFIRMED,
                'notes': f'From {q3.reference}. Seasonal gift sets - spring/summer.',
            },
        )
        ol_gkit2  = oline(so2, gift_kit,  60, 0)
        ol_gwell  = oline(so2, gift_well, 60, 1)
        ol_seas   = oline(so2, seasonal,  36, 2)

        fo2, _ = FulfillmentOrder.objects.update_or_create(
            pk=_sal_uuid('fo:atelier-seasonal-2026'),
            defaults={
                'reference': _REFS['fo2'], 'sales_order': so2, 'created_by': user,
                'status': FulfillmentOrderStatus.IN_PROGRESS,
                'notes': 'Gift kits picked; wellness bundles pending assembly completion.',
            },
        )
        fo_line(fo2, ol_gkit2, 'C-01', 0)
        fo_line(fo2, ol_gwell, 'C-01', 1)
        fo_line(fo2, ol_seas,  'C-01', 2)

        inv2, _ = Invoice.objects.update_or_create(
            pk=_sal_uuid('inv:atelier-seasonal-2026'),
            defaults={
                'reference': _REFS['inv2'], 'order': so2, 'created_by': user,
                'relation_organization': atelier, 'status': InvoiceStatus.ISSUED,
                'currency': 'EUR', 'due_date': date(2026, 5, 10),
            },
        )
        for i, ol in enumerate(ol for ol in [ol_gkit2, ol_gwell, ol_seas] if ol):
            inv_line(inv2, ol, i)
        inv2_total = sum(ol.line_total for ol in [ol_gkit2, ol_gwell, ol_seas] if ol)
        payment(inv2, (inv2_total * Decimal('0.5')).quantize(Decimal('0.01')),
                '50% deposit ATL-DEP-2026-04')

        # ── SO3: Bloom gift set top-up (from Q8) - CONFIRMED ──────────────────
        so3, _ = SalesOrder.objects.update_or_create(
            pk=_sal_uuid('order:bloom-topup-2026'),
            defaults={
                'reference': _REFS['so3'], 'created_by': user, 'quote': q8,
                'relation_organization': bloom, 'status': OrderStatus.CONFIRMED,
                'notes': f'From {q8.reference}. Wellness bundle sell-out replenishment.',
            },
        )
        ol_gwell2  = oline(so3, gift_well, 48, 0)
        ol_seas2   = oline(so3, seasonal,  24, 1)

        fo3, _ = FulfillmentOrder.objects.update_or_create(
            pk=_sal_uuid('fo:bloom-topup-2026'),
            defaults={
                'reference': _REFS['fo3'], 'sales_order': so3, 'created_by': user,
                'status': FulfillmentOrderStatus.PENDING,
                'notes': 'Awaiting remaining gift set assembly from PO-DEMO-0003.',
            },
        )
        fo_line(fo3, ol_gwell2, 'C-01', 0)
        fo_line(fo3, ol_seas2,  'C-01', 1)

        inv3, _ = Invoice.objects.update_or_create(
            pk=_sal_uuid('inv:bloom-topup-2026'),
            defaults={
                'reference': _REFS['inv3'], 'order': so3, 'created_by': user,
                'relation_organization': bloom, 'status': InvoiceStatus.ISSUED,
                'currency': 'EUR', 'due_date': date(2026, 5, 1),
            },
        )
        for i, ol in enumerate(ol for ol in [ol_gwell2, ol_seas2] if ol):
            inv_line(inv3, ol, i)

        # ── SO4: Nordic Home stationery (from Q2 portion) - CONFIRMED ─────────
        so4, _ = SalesOrder.objects.update_or_create(
            pk=_sal_uuid('order:nordic-stationery-2026'),
            defaults={
                'reference': _REFS['so4'], 'created_by': user, 'quote': q2,
                'relation_organization': nordic, 'status': OrderStatus.CONFIRMED,
                'notes': 'Partial conversion from Q-DEMO-0002 - stationery items confirmed; hydration TBC.',
            },
        )
        ol_nbook  = oline(so4, nbook,    120, 0)
        ol_brush  = oline(so4, brush_set, 72, 1)
        ol_plant  = oline(so4, plant_pot, 60, 2)

        inv4, _ = Invoice.objects.update_or_create(
            pk=_sal_uuid('inv:nordic-stationery-2026'),
            defaults={
                'reference': _REFS['inv4'], 'order': so4, 'created_by': user,
                'relation_organization': nordic, 'status': InvoiceStatus.ISSUED,
                'currency': 'EUR', 'due_date': date(2026, 4, 20),
            },
        )
        for i, ol in enumerate(ol for ol in [ol_nbook, ol_brush, ol_plant] if ol):
            inv_line(inv4, ol, i)

        # ── SO5: Gift & More DE (no quote, verbal) - DRAFT ────────────────────
        so5, _ = SalesOrder.objects.update_or_create(
            pk=_sal_uuid('order:giftmore-verbal-2026'),
            defaults={
                'reference': _REFS['so5'], 'created_by': user, 'quote': None,
                'relation_organization': giftmore, 'status': OrderStatus.DRAFT,
                'notes': 'Verbal order from Klaus Weber post-Ambiente. Formal PO from customer pending.',
            },
        )
        oline(so5, btl500, 60, 0)
        oline(so5, btl750, 36, 1)

        # Invoice 5 - Overdue (Nordic, old small order, no payment)
        inv5, _ = Invoice.objects.update_or_create(
            pk=_sal_uuid('inv:nordic-overdue-2026'),
            defaults={
                'reference': _REFS['inv5'], 'order': so4, 'created_by': user,
                'relation_organization': nordic, 'status': InvoiceStatus.ISSUED,
                'currency': 'EUR', 'due_date': date(2026, 3, 1),
                'notes': 'Overdue - second reminder sent 2026-03-20. Chased by finance.',
            },
        )
        if ol_nbook:
            InvoiceLine.objects.update_or_create(
                pk=_sal_uuid(f'il5:{inv5.pk}:{ol_nbook.pk}'),
                defaults={
                    'invoice': inv5, 'product': ol_nbook.product,
                    'product_name': ol_nbook.product_name, 'sku': ol_nbook.sku,
                    'brand': ol_nbook.brand or '', 'quantity': Decimal('24'),
                    'unit_price': ol_nbook.unit_price, 'currency': ol_nbook.currency,
                    'line_total': (ol_nbook.unit_price * 24).quantize(Decimal('0.01')),
                    'sort_order': 0,
                },
            )

        # ── Shipping order for SO3 (partial) ──────────────────────────────────
        sho2, _ = ShippingOrder.objects.update_or_create(
            pk=_sal_uuid('sho:atelier-seasonal-partial'),
            defaults={
                'reference': _REFS['sho2'], 'fulfillment_order': fo2, 'sales_order': so2,
                'created_by': user, 'status': ShippingOrderStatus.PARTIALLY_SHIPPED,
                'notes': 'Kitchen gift sets dispatched; wellness bundles to follow.',
            },
        )
        fol_gkit2 = FulfillmentOrderLine.objects.filter(
            pk=_sal_uuid(f'fol:{fo2.pk}:{ol_gkit2.pk}')).first() if ol_gkit2 else None
        sl_gkit2 = shol(sho2, fol_gkit2)
        if sl_gkit2:
            sh2, _ = Shipment.objects.update_or_create(
                pk=_sal_uuid('sh:atelier-seasonal-partial'),
                defaults={
                    'shipping_order': sho2, 'sequence': 1, 'carrier': 'PostNL Pakketten',
                    'tracking_number': '3SYZKA987654321', 'status': ShipmentStatus.IN_TRANSIT,
                    'notes': 'Kitchen gift sets in transit - estimated delivery 2 business days.',
                },
            )
            ShipmentLine.objects.update_or_create(
                pk=_sal_uuid(f'shl:{sh2.pk}:{sl_gkit2.pk}'),
                defaults={'shipment': sh2, 'shipping_order_line': sl_gkit2,
                          'quantity': sl_gkit2.quantity},
            )

        # ── Demo cart for logged-in user ───────────────────────────────────────
        cart, _ = Cart.objects.get_or_create(user=user)
        for product, qty in [(btl500, 24), (gift_desk, 6), (can_sm, 12)]:
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
        self.stdout.write('  Seeding pricing rules...')
        from pricing.models import PricingMethod, PricingRule, PricingRuleAssignment, RoundingMethod

        def cat(slug): return ProductCategory.objects.filter(slug=slug).first()
        def prod(sku): return Product.objects.filter(sku=sku).first()

        rule1, _ = PricingRule.objects.get_or_create(
            name='Standard wholesale markup - home goods',
            defaults={
                'description': 'Standard 3x cost-plus markup across all Home & Living categories.',
                'method': PricingMethod.COST_MARKUP, 'value': Decimal('230.000000'),
                'rounding': RoundingMethod.NEAREST_EURO, 'is_active': True,
                'notes': 'Target 70% gross margin at standard wholesale pricing. Override for partner accounts.',
            },
        )
        home_cat = cat('home-living')
        if home_cat:
            PricingRuleAssignment.objects.get_or_create(
                rule=rule1, category=home_cat,
                defaults={'include_subcategories': True, 'priority': 10},
            )

        rule2, _ = PricingRule.objects.get_or_create(
            name='Bundle / gift set - fixed multiplier 0.85',
            defaults={
                'description': 'Gift sets and bundle SKUs carry a 0.85 list-price multiplier for preferred partners.',
                'method': PricingMethod.FIXED_MULTIPLIER, 'value': Decimal('0.850000'),
                'rounding': RoundingMethod.NEAREST_EURO, 'is_active': True,
                'notes': 'Applied when ordering partner-tier quantities (MOQ 4). Verify discount group.',
            },
        )
        bundles_cat = cat('gift-sets')
        if bundles_cat:
            PricingRuleAssignment.objects.get_or_create(
                rule=rule2, category=bundles_cat,
                defaults={'include_subcategories': True, 'priority': 10},
            )

        rule3, _ = PricingRule.objects.get_or_create(
            name='Meridian Insulated Bottle - volume enterprise pricing',
            defaults={
                'description': 'Enterprise channel pricing: 12% off MSRP for bottle lines at high volume.',
                'method': PricingMethod.MSRP_DISCOUNT, 'value': Decimal('12.000000'),
                'rounding': RoundingMethod.NEAREST_CENT, 'is_active': True,
            },
        )
        btl = prod('MERID-BTL-500')
        if btl:
            PricingRuleAssignment.objects.get_or_create(
                rule=rule3, product=btl, defaults={'priority': 5},
            )

        rule4, _ = PricingRule.objects.get_or_create(
            name='Stationery & accessories - 65% gross margin target',
            defaults={
                'description': 'Higher margin target for stationery and accessory lines.',
                'method': PricingMethod.GROSS_MARGIN, 'value': Decimal('65.000000'),
                'rounding': RoundingMethod.NEAREST_CENT, 'is_active': True,
            },
        )
        for cat_slug in ['stationery', 'accessories']:
            c = cat(cat_slug)
            if c:
                PricingRuleAssignment.objects.get_or_create(
                    rule=rule4, category=c,
                    defaults={'include_subcategories': True, 'priority': 10},
                )

        from pricing.models import PricingRuleAssignment as PRA
        self.stdout.write(
            f'    {PricingRule.objects.count()} rules, {PRA.objects.count()} assignments'
        )

    # ── CONTRACTS ─────────────────────────────────────────────────────────────

    def _seed_contracts(self) -> None:
        self.stdout.write('  Seeding contracts...')
        from contracts.models import (
            Contract, ContractStatus, ContractTemplate, ContractTemplateVariable,
            ContractVariableType, ContractVariableValue, ServiceRate,
        )
        from contracts.services import create_variable_value_stubs, refresh_computed_result

        # ── Service rates ──────────────────────────────────────────────────────
        trade_mgr, _ = ServiceRate.objects.get_or_create(
            code='trade_manager',
            defaults={
                'name': 'Trade account manager',
                'description': 'Dedicated account management, range planning, and trade support.',
                'rate_per_hour': Decimal('75.00'), 'currency': 'EUR', 'is_active': True,
            },
        )
        ServiceRate.objects.get_or_create(
            code='logistics_coord',
            defaults={
                'name': 'Logistics coordinator',
                'description': 'Order coordination, customs, freight booking.',
                'rate_per_hour': Decimal('55.00'), 'currency': 'EUR', 'is_active': True,
            },
        )
        ServiceRate.objects.get_or_create(
            code='key_account',
            defaults={
                'name': 'Key account director',
                'description': 'Strategic account direction for top-tier retail partners.',
                'rate_per_hour': Decimal('110.00'), 'currency': 'EUR', 'is_active': True,
            },
        )

        # ── Template 1: Annual Supply Agreement ───────────────────────────────
        tmpl1, _ = ContractTemplate.objects.get_or_create(
            name='Annual Supply Agreement',
            defaults={
                'description': (
                    'Fixed-term wholesale supply agreement. Calculates committed annual value '
                    'based on agreed unit volumes, price tier, and a logistics flat fee.'
                ),
                'formula':      'annual_units * unit_price + logistics_fee',
                'result_label': 'Annual commitment value (EUR)',
                'is_active':    True,
                'notes': (
                    'Use for annual frame contracts with retail chains. '
                    'unit_price should reflect agreed volume tier. '
                    'logistics_fee covers allocated freight/handling cost.'
                ),
            },
        )
        for name, label, vtype, const_val, default_val, unit, sort in [
            ('annual_units',  'Committed units per year',    ContractVariableType.USER_INPUT, None, Decimal('1200'), 'units',  10),
            ('unit_price',    'Agreed unit price (EUR)',     ContractVariableType.USER_INPUT, None, Decimal('22.50'), 'EUR',   20),
            ('logistics_fee', 'Annual logistics allowance',  ContractVariableType.USER_INPUT, None, Decimal('480'),  'EUR',   30),
        ]:
            ContractTemplateVariable.objects.get_or_create(
                template=tmpl1, name=name,
                defaults={'label': label, 'variable_type': vtype, 'service_rate': None,
                          'constant_value': const_val, 'default_value': default_val,
                          'unit': unit, 'sort_order': sort},
            )

        # ── Template 2: Trade Support SLA ─────────────────────────────────────
        tmpl2, _ = ContractTemplate.objects.get_or_create(
            name='Trade Support SLA',
            defaults={
                'description': (
                    'Annual cost model for dedicated trade account support. Combines '
                    'account management hours at trade manager rate with a fixed '
                    'marketing support allowance.'
                ),
                'formula':      '(support_days * 8 * mgr_rate) + mktg_allowance',
                'result_label': 'Annual support cost (EUR)',
                'is_active':    True,
                'notes': 'Typical values: 10-20 support days, mktg_allowance EUR 1000-2500.',
            },
        )
        for name, label, vtype, svc_rate, const_val, default_val, unit, sort in [
            ('support_days',   'Dedicated support days/year', ContractVariableType.USER_INPUT,   None,      None, Decimal('12'), 'days', 10),
            ('mgr_rate',       'Trade manager hourly rate',   ContractVariableType.SERVICE_RATE, trade_mgr, None, None,          'EUR/h', 20),
            ('mktg_allowance', 'Marketing support allowance', ContractVariableType.USER_INPUT,   None,      None, Decimal('1500'), 'EUR', 30),
        ]:
            ContractTemplateVariable.objects.get_or_create(
                template=tmpl2, name=name,
                defaults={'label': label, 'variable_type': vtype, 'service_rate': svc_rate,
                          'constant_value': const_val, 'default_value': default_val,
                          'unit': unit, 'sort_order': sort},
            )

        # ── Contract instances ─────────────────────────────────────────────────
        bloom   = Organization.objects.filter(pk=_rel_uuid('org:bloom-co')).first()
        nordic  = Organization.objects.filter(pk=_rel_uuid('org:nordic-home')).first()
        atelier = Organization.objects.filter(pk=_rel_uuid('org:atelier-gifts')).first()
        so1     = SalesOrder.objects.filter(reference=_REFS['so1']).first()
        so2     = SalesOrder.objects.filter(reference=_REFS['so2']).first()

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

        if bloom:
            make_contract(
                'SVC-DEMO-0001', bloom, tmpl1, so1,
                date(2026, 3, 1), date(2027, 2, 28), ContractStatus.ACTIVE,
                {'annual_units': Decimal('1440'), 'unit_price': Decimal('21.50'),
                 'logistics_fee': Decimal('720')},
                f'Annual supply agreement linked to {_REFS["so1"]}. Covers full catalogue range. '
                f'24-store rollout; logistics fee covers quarterly pallet deliveries.',
            )
            make_contract(
                'SVC-DEMO-0002', bloom, tmpl2, None,
                date(2026, 1, 1), date(2026, 12, 31), ContractStatus.ACTIVE,
                {'support_days': Decimal('16'), 'mktg_allowance': Decimal('2000')},
                'Annual trade support SLA for Bloom & Co. Includes 16 dedicated account manager '
                'days and EUR 2000 co-op marketing allowance for in-store activations.',
            )

        if nordic:
            make_contract(
                'SVC-DEMO-0003', nordic, tmpl1, so2,
                date(2026, 4, 1), date(2027, 3, 31), ContractStatus.ACTIVE,
                {'annual_units': Decimal('600'), 'unit_price': Decimal('24.50'),
                 'logistics_fee': Decimal('360')},
                f'Annual supply frame for Nordic Home. Covers sustainable product lines. '
                f'Includes FSC certification requirement clause.',
            )

        if atelier:
            make_contract(
                'SVC-DEMO-0004', atelier, tmpl2, None,
                date(2026, 1, 1), date(2026, 12, 31), ContractStatus.ACTIVE,
                {'support_days': Decimal('8'), 'mktg_allowance': Decimal('1000')},
                'Light-touch trade support for Atelier Gifts BE. 8 days account management '
                'and EUR 1000 seasonal marketing support allowance.',
            )

        from contracts.models import Contract as C
        self.stdout.write(
            f'    3 service rates, {ContractTemplate.objects.count()} templates, '
            f'{C.objects.count()} contracts'
        )
