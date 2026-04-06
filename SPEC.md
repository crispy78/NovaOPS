# NovaCRM 0.1 — Technical Specification

**Version:** 0.1  
**Stack:** Django 5.2 · SQLite · Tailwind CSS 3.4 · Python 3.13  
**Architecture:** Monolithic Django MTV, server-rendered templates, no REST API

---

## Table of Contents

1. [Project Purpose](#1-project-purpose)
2. [Technology Stack](#2-technology-stack)
3. [Architecture Overview](#3-architecture-overview)
4. [URL Structure](#4-url-structure)
5. [Authentication & Permissions](#5-authentication--permissions)
6. [Cross-cutting Concerns](#6-cross-cutting-concerns)
7. [App: core](#7-app-core)
8. [App: accounts](#8-app-accounts)
9. [App: audit](#9-app-audit)
10. [App: catalog](#10-app-catalog)
11. [App: pricing](#11-app-pricing)
12. [App: relations](#12-app-relations)
13. [App: sales](#13-app-sales)
14. [App: assets](#14-app-assets)
15. [App: contracts](#15-app-contracts)
16. [Frontend & Templating](#16-frontend--templating)
17. [Data Design Patterns](#17-data-design-patterns)
18. [Demo Data](#18-demo-data)

---

## 1. Project Purpose

NovaCRM 0.1 is an internal B2B CRM and operations platform for a hardware reseller operating in the Benelux market. It supports the full commercial lifecycle from product catalogue management through customer relationships, quoting, order-to-cash, installed asset tracking, multi-year maintenance planning, and contract management.

The system is intentionally a single integrated application — not a collection of microservices — so that all data lives in one place and every workflow can follow a document from inquiry through to invoice and beyond without leaving the platform.

**Primary users:**
- Sales staff (quoting, order entry, cart)
- Operations / warehouse (fulfillment, shipping)
- Finance (invoicing, payment recording)
- Account management (CRM, assets, contracts)
- Management (dashboard overview)

---

## 2. Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Language | Python 3.13 | |
| Web framework | Django 5.2 | MTV pattern; class-based views throughout |
| Database | SQLite | Development and initial production; switchable via `DATABASES` setting |
| ORM | Django ORM | No raw SQL; all queries via ORM |
| Image processing | Pillow ≥ 10 | Product image upload handling |
| CSS framework | Tailwind CSS 3.4 | Via CDN in dev; build output for production |
| Icons | FontAwesome 6 (self-hosted) | `fa-solid`, `fa-regular` style classes |
| Template engine | Django Templates | Server-rendered; no client-side framework |
| Auth | Django `contrib.auth` | Extended with email-based login |
| Session | Django sessions | Cookie-based, HTTP-only, secure in production |
| Static files | Django `staticfiles` | `STATIC_URL = '/static/'` |
| Media files | Django file storage | `MEDIA_URL = '/media/'`, `MEDIA_ROOT = BASE_DIR / 'media'` |
| Version indicator | Custom `core.version` | Automatic build hash from source file mtimes |

**Python dependencies** (`requirements.txt`):
```
Django>=5.2,<6
Pillow>=10
```

---

## 3. Architecture Overview

### Django apps

```
novaops/          ← project package (settings, root urls, wsgi)
core/             ← shared abstractions (base model, reference sequences, dashboard, version)
accounts/         ← authentication, user profiles
audit/            ← append-only event log
catalog/          ← product master data
pricing/          ← pricing rules and category/product assignments
relations/        ← CRM: organizations, people, contacts
sales/            ← order-to-cash pipeline (cart → quote → order → invoice → fulfillment → shipping)
assets/           ← installed asset lifecycle, maintenance planning, recalls
contracts/        ← service contracts with formula-based pricing
```

### Layering convention

| Layer | Location | Responsibility |
|-------|----------|---------------|
| Models | `<app>/models.py` | Data definition, field validation, `clean()`, `get_absolute_url()`, simple computed properties |
| Services | `<app>/services.py` | All multi-step transactional business logic as standalone `@transaction.atomic` functions |
| Views | `<app>/views.py` | HTTP handling, form binding, rendering; call services for writes |
| Forms | `<app>/forms.py` | Input validation, widget configuration |
| Templates | `<app>/templates/<app>/` | Presentation only |

Business logic is **never** implemented as model methods or in views directly — it lives exclusively in `services.py`. This keeps models thin and makes logic testable without HTTP.

### Sales pipeline order

```
Cart → Quote → SalesOrder → Invoice
                         ↘ FulfillmentOrder → ShippingOrder → Shipment → ShipmentLine
                                                                       ↘ InvoicePayment
```

---

## 4. URL Structure

### Root (`novaops/urls.py`)

| Path | Handler | Name |
|------|---------|------|
| `admin/` | Django admin | — |
| `accounts/login/` | `LoginView` (EmailLoginForm) | `login` |
| `accounts/logout/` | `LogoutView` | `logout` |
| `accounts/password_change/` | `PasswordChangeView` | `password_change` |
| `accounts/password_change/done/` | `PasswordChangeDoneView` | `password_change_done` |
| `accounts/profile/` | include `accounts.urls` | — |
| `dashboard/` | `DashboardView` | `dashboard` |
| `relations/` | include `relations.urls` | — |
| `assets/` | include `assets.urls` | — |
| `pricing/` | include `pricing.urls` | — |
| `sales/` | include `sales.urls` | — |
| `contracts/` | include `contracts.urls` | — |
| `media/<path>` | `protected_media` (DEBUG only) | `protected_media` |
| `` (root) | include `catalog.urls` | — |

### App namespaces

| App | Namespace | Base path |
|-----|-----------|-----------|
| catalog | `catalog` | `/` |
| relations | `relations` | `/relations/` |
| assets | `assets` | `/assets/` |
| pricing | `pricing` | `/pricing/` |
| sales | `sales` | `/sales/` |
| contracts | `contracts` | `/contracts/` |
| accounts | `accounts` | `/accounts/profile/` |

### `catalog` URLs

| URL | View | Name |
|-----|------|------|
| `/` | `ProductListView` | `catalog:index` |
| `/images/` | `ImageLibraryView` | `catalog:image_library` |
| `/products/<uuid:pk>/` | `ProductDetailView` | `catalog:product_detail` |
| `/products/<uuid:pk>/edit/` | `ProductUpdateView` | `catalog:product_edit` |
| `/products/<uuid:pk>/images/add/` | `ProductImageAddView` | `catalog:product_image_add` |
| `/products/<uuid:pk>/images/<uuid:image_pk>/delete/` | `ProductImageDeleteView` | `catalog:product_image_delete` |
| `/products/<uuid:pk>/replacement/add/` | `ProductReplacementAddView` | `catalog:product_replacement_add` |

### `sales` URLs

| URL | View | Name |
|-----|------|------|
| `cart/` | `CartView` | `sales:cart` |
| `cart/add/<uuid:product_pk>/` | `CartAddView` | `sales:cart_add` |
| `cart/line/<uuid:line_pk>/update/` | `CartLineUpdateView` | `sales:cart_line_update` |
| `cart/quote/` | `QuoteCreateFromCartView` | `sales:cart_create_quote` |
| `cart/order/` | `OrderCreateFromCartView` | `sales:cart_create_order` |
| `quotes/` | `QuoteListView` | `sales:quote_list` |
| `quotes/<uuid:pk>/` | `QuoteDetailView` (GET+POST) | `sales:quote_detail` |
| `quotes/<uuid:pk>/refresh-prices/` | `QuoteRefreshPricesView` | `sales:quote_refresh_prices` |
| `quotes/<uuid:pk>/create-order/` | `QuoteCreateOrderView` | `sales:quote_create_order` |
| `orders/` | `SalesOrderListView` | `sales:order_list` |
| `orders/<uuid:pk>/` | `SalesOrderDetailView` | `sales:order_detail` |
| `orders/<uuid:pk>/status/` | `SalesOrderStatusUpdateView` | `sales:order_status_update` |
| `orders/<uuid:pk>/create-invoice/` | `InvoiceCreateFromOrderView` | `sales:order_create_invoice` |
| `orders/<uuid:pk>/create-fulfillment/` | `FulfillmentCreateFromOrderView` | `sales:order_create_fulfillment` |
| `fulfillments/` | `FulfillmentOrderListView` | `sales:fulfillment_list` |
| `fulfillments/<uuid:pk>/` | `FulfillmentOrderDetailView` | `sales:fulfillment_detail` |
| `fulfillments/<uuid:fulfillment_pk>/shipping/new/` | `ShippingOrderCreateFromFulfillmentView` | `sales:fulfillment_create_shipping` |
| `shipping/` | `ShippingOrderListView` | `sales:shipping_list` |
| `shipping/<uuid:pk>/` | `ShippingOrderDetailView` (GET+POST) | `sales:shipping_detail` |
| `invoices/` | `InvoiceListView` | `sales:invoice_list` |
| `invoices/<uuid:pk>/` | `InvoiceDetailView` (GET+POST) | `sales:invoice_detail` |

### `relations` URLs

| URL | View | Name |
|-----|------|------|
| `organizations/` | `OrganizationListView` | `relations:organization_list` |
| `organizations/new/` | `OrganizationCreateView` | `relations:organization_create` |
| `organizations/<uuid:pk>/` | `OrganizationDetailView` | `relations:organization_detail` |
| `organizations/<uuid:pk>/edit/` | `OrganizationUpdateView` | `relations:organization_update` |
| `people/` | `PersonListView` | `relations:person_list` |
| `people/new/` | `PersonCreateView` | `relations:person_create` |
| `people/<uuid:pk>/` | `PersonDetailView` | `relations:person_detail` |
| `people/<uuid:pk>/edit/` | `PersonUpdateView` | `relations:person_update` |

### `assets` URLs

| URL | View | Name |
|-----|------|------|
| `` | `AssetListView` | `assets:asset_list` |
| `new/` | `AssetCreateView` | `assets:asset_create` |
| `<uuid:pk>/` | `AssetDetailView` | `assets:asset_detail` |
| `<uuid:pk>/edit/` | `AssetUpdateView` | `assets:asset_update` |
| `<uuid:asset_pk>/events/new/` | `AssetEventCreateView` | `assets:asset_event_create` |
| `<uuid:asset_pk>/recommendations/new/` | `ReplacementRecommendationCreateView` | `assets:asset_recommendation_create` |
| `recall-links/<uuid:pk>/update/` | `RecallLinkUpdateView` | `assets:recall_link_update` |
| `recalls/` | `RecallCampaignListView` | `assets:recall_list` |
| `recalls/new/` | `RecallCampaignCreateView` | `assets:recall_create` |
| `recalls/<uuid:pk>/edit/` | `RecallCampaignUpdateView` | `assets:recall_update` |
| `recalls/<uuid:pk>/` | `RecallCampaignDetailView` | `assets:recall_detail` |
| `mjop/` | `MaintenancePlanListView` | `assets:mjop_list` |
| `mjop/new/` | `MaintenancePlanCreateView` | `assets:mjop_create` |
| `mjop/<uuid:pk>/` | `MaintenancePlanDetailView` | `assets:mjop_detail` |
| `mjop/<uuid:pk>/edit/` | `MaintenancePlanUpdateView` | `assets:mjop_update` |
| `mjop/<uuid:plan_pk>/lines/new/` | `MaintenancePlanLineCreateView` | `assets:mjop_line_create` |

### `contracts` URLs

| URL | View | Name |
|-----|------|------|
| `rates/` | `ServiceRateListView` | `contracts:rate_list` |
| `rates/new/` | `ServiceRateCreateView` | `contracts:rate_create` |
| `rates/<uuid:pk>/edit/` | `ServiceRateUpdateView` | `contracts:rate_update` |
| `templates/` | `ContractTemplateListView` | `contracts:template_list` |
| `templates/new/` | `ContractTemplateCreateView` | `contracts:template_create` |
| `templates/<uuid:pk>/` | `ContractTemplateDetailView` | `contracts:template_detail` |
| `templates/<uuid:pk>/edit/` | `ContractTemplateUpdateView` | `contracts:template_update` |
| `` | `ContractListView` | `contracts:contract_list` |
| `new/` | `ContractCreateView` | `contracts:contract_create` |
| `<uuid:pk>/` | `ContractDetailView` | `contracts:contract_detail` |
| `<uuid:pk>/edit/` | `ContractUpdateView` | `contracts:contract_update` |

### `pricing` URLs

| URL | View | Name |
|-----|------|------|
| `` | `PricingRuleListView` | `pricing:rule_list` |
| `new/` | `PricingRuleCreateView` | `pricing:rule_create` |
| `<uuid:pk>/` | `PricingRuleDetailView` | `pricing:rule_detail` |
| `<uuid:pk>/edit/` | `PricingRuleUpdateView` | `pricing:rule_update` |

### `accounts` URLs

| URL | View | Name |
|-----|------|------|
| `` | `ProfileUpdateView` | `accounts:profile` |
| `directory/` | `ActiveUserListView` | `accounts:user_directory` |

---

## 5. Authentication & Permissions

### Authentication

- All views require `LoginRequiredMixin` (no anonymous access beyond the login page).
- Login uses a custom `EmailLoginForm` so users authenticate with email address, not username.
- `LOGIN_URL = '/accounts/login/'`
- `LOGIN_REDIRECT_URL = '/dashboard/'`
- `LOGOUT_REDIRECT_URL = '/'`
- Password change is provided via Django's built-in views with a custom styled form (`StyledPasswordChangeForm`).

### Custom model permissions

Sensitive operations use `PermissionRequiredMixin` backed by Django's permission system. Defined custom permissions:

**catalog.Product:**
| Codename | Purpose |
|----------|---------|
| `view_product_purchase_price` | See purchase/cost price fields |
| `edit_product_pricing` | Edit list price, MSRP, price tiers |
| `archive_product` | Archive a product (soft delete) |

**relations.Organization / relations.Person:**
Custom permissions control which users can create, edit, or archive organization and contact records.

### Session security

| Setting | Value |
|---------|-------|
| `SESSION_COOKIE_HTTPONLY` | `True` |
| `CSRF_COOKIE_SECURE` | `True` in production |
| `SESSION_COOKIE_SECURE` | `True` in production |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` |
| `X_FRAME_OPTIONS` | `'DENY'` |
| `SECURE_REFERRER_POLICY` | `'same-origin'` |
| `SECURE_SSL_REDIRECT` | `True` in production |
| `SECURE_HSTS_SECONDS` | `604800` (1 week) in production |

---

## 6. Cross-cutting Concerns

### UUID primary keys

Every domain model inherits from `core.models.UUIDPrimaryKeyModel`:

```python
class UUIDPrimaryKeyModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class Meta:
        abstract = True
```

UUIDs are internal PKs used in URLs. Human-readable reference numbers (e.g. `Q-2026-00001`) are used in the UI and document headers.

### Human-readable reference numbers

Generated by `core.models.next_reference(prefix, year, pad=5)` using a `ReferenceSequence` table with `SELECT FOR UPDATE` to ensure atomicity under concurrent requests.

Format: `{PREFIX}-{YEAR}-{COUNTER:05d}`

| Document | Prefix | Example |
|----------|--------|---------|
| Quote | `Q` | `Q-2026-00001` |
| Sales Order | `SO` | `SO-2026-00001` |
| Invoice | `INV` | `INV-2026-00001` |
| Fulfillment Order | `FO` | `FO-2026-00001` |
| Shipping Order | `SHP` | `SHP-2026-00001` |
| Recall Campaign | `RC` | `RC-2026-0001` |
| Maintenance Plan | `MJOP` | `MJOP-2026-0001` |
| Service Contract | `SVC` | `SVC-2026-0001` |

### Soft delete

`Product`, `Organization`, `Person`, and `Asset` use soft deletion:

- `is_archived: BooleanField(default=False, db_index=True)`
- `archived_at: DateTimeField(null=True, blank=True)`

Archived records are excluded from list queries but retained in the database for audit and reference integrity. Detail views remain accessible for historical context.

### Snapshot pattern

`QuoteLine`, `OrderLine`, and `InvoiceLine` each snapshot the product's commercial data at the moment of creation via `sales.models.snapshot_line_from_product(product, quantity, sort_order)`:

```python
# Fields snapshotted:
product_name, sku, brand, unit_price, currency, line_total, sort_order
```

This means historical documents are never retroactively changed by catalog updates. The `product` FK is nullable (`SET_NULL`) — if a product is deleted the line still shows the correct name and price from the time of the transaction.

### Audit log

All significant state changes are recorded by `audit.services.log_event()`:

```python
log_event(
    action='quote.created',     # dot-notation action name
    entity_type='Quote',        # model name string
    entity_id=quote.id,         # UUID
    request=request,            # for actor resolution
    metadata={'reference': 'Q-2026-00001'},  # arbitrary JSON
)
```

The `EventLog` is append-only (no update/delete in the application layer).

### Generic contacts

`Address`, `Communication`, and `SocialProfile` attach to both `Organization` and `Person` via Django's `GenericForeignKey` (`content_type` + `object_id`). This avoids duplicate contact tables while maintaining full polymorphism.

### Context processors

Two context processors inject into every template:

| Processor | Variables injected |
|-----------|-------------------|
| `sales.context_processors.cart_item_count` | `cart_item_count` (int) |
| `core.context_processors.app_version` | `app_version` (str), `app_build` (str) |

`app_build` is a 6-hex-digit build hash derived from the newest `.py` or `.html` source file's mtime, computed once per process start and cached in a module-level variable.

### Money fields

All monetary values use a shared constant:

```python
MONEY = dict(max_digits=12, decimal_places=2)
```

Currency is stored as a 3-character ISO 4217 code (default `'EUR'`) alongside each amount. There is no multi-currency conversion layer — amounts are stored as-entered.

---

## 7. App: core

**Purpose:** Shared abstractions used by all other apps.

### Models

#### `UUIDPrimaryKeyModel` (abstract)
Base class for all domain models. Provides a `uuid4` primary key.

#### `ReferenceSequence`
Persistent counter table for human-readable reference generation.

| Field | Type | Notes |
|-------|------|-------|
| `prefix` | CharField(20) | e.g. `'Q'` |
| `year` | PositiveSmallIntegerField | Calendar year |
| `last_value` | PositiveIntegerField | Last-issued counter value |

Unique together: `(prefix, year)`.

#### `next_reference(prefix, year, pad=5) -> str`
Atomic function using `SELECT FOR UPDATE` to safely increment the counter. Returns formatted reference string.

### Views

#### `DashboardView` (LoginRequired, TemplateView)
Template: `core/templates/core/dashboard.html`

Context:
- `open_orders_count` — SalesOrders in DRAFT or CONFIRMED status
- `active_quotes_count` — Quotes in DRAFT or SENT status
- `expiring_quotes_count` — Active quotes where `valid_until < today`
- `unpaid_invoices_count` — Issued invoices with positive balance
- `recent_quotes` — 5 most recent active quotes
- `recent_orders` — 5 most recent open orders
- `recent_unpaid_invoices` — 5 most recent unpaid invoices with annotated balance
- `today` — `timezone.localdate()`

#### `protected_media(request, path)` (function-based, DEBUG only)
Serves `MEDIA_ROOT` files behind `@login_required`. In production, media should be served by the web server with equivalent authentication.

### Other modules

#### `core.version`
- `VERSION = "0.1"` — bump manually on release
- `get_build_hash() -> str` — scans source mtimes, returns 6-hex hash, cached per process

#### `core.context_processors`
- `app_version(request)` — returns `{"app_version": VERSION, "app_build": get_build_hash()}`

---

## 8. App: accounts

**Purpose:** Email-based authentication and user profiles.

### Auth customisation

- `EmailLoginForm` overrides the username field label and authentication logic to accept email addresses.
- `StyledPasswordChangeForm` applies consistent Tailwind CSS widget classes to the password change form.

### Views

| View | URL name | Notes |
|------|----------|-------|
| `ProfileUpdateView` | `accounts:profile` | Edit own profile |
| `ActiveUserListView` | `accounts:user_directory` | Staff directory |

### Notes

The accounts app is intentionally minimal in 0.1. The `accounts/models.py` file currently contains no custom models — Django's built-in `User` is used as-is. A custom user model or profile extension is a planned future addition.

---

## 9. App: audit

**Purpose:** Immutable event log for compliance and debugging.

### Model: `EventLog`

| Field | Type | Notes |
|-------|------|-------|
| `actor` | FK → User (SET_NULL, nullable) | User who triggered the event |
| `action` | CharField(80) | Dot-notation name, e.g. `'quote.created'` |
| `entity_type` | CharField(80) | Model name string, e.g. `'Quote'` |
| `entity_id` | UUIDField(nullable) | PK of the affected record |
| `metadata` | JSONField(default=dict) | Arbitrary context |
| `created_at` | DateTimeField(auto_now_add, db_index) | |

### `audit.services.log_event()`

```python
def log_event(
    action: str,
    entity_type: str,
    entity_id,
    request=None,
    metadata: dict | None = None,
) -> EventLog
```

Resolves actor from `request.user` if provided (or `None` for system events). Creates and returns the `EventLog` record.

### Known action names

| Action | Triggered by |
|--------|-------------|
| `cart.line_added` | `add_to_cart()` |
| `cart.line_removed` | `set_cart_line_quantity()` with qty=0 |
| `cart.line_quantity_set` | `set_cart_line_quantity()` |
| `cart.cleared` | Quote/order creation from cart |
| `quote.created` | `create_quote_from_cart()` |
| `quote.updated` | `QuoteDetailView.post()` |
| `quote.prices_refreshed` | `refresh_quote_prices_from_catalog()` |
| `quote.locked` | `create_order_from_quote()` |
| `order.created` | `create_order_from_cart()` |
| `order.created_from_quote` | `create_order_from_quote()` |
| `order.confirmed` | `SalesOrderStatusUpdateView` |
| `order.cancelled` | `SalesOrderStatusUpdateView` |
| `invoice.created` | `create_invoice_from_order()` |
| `invoice.payment_recorded` | `add_invoice_payment()` |
| `fulfillment_order.created` | `create_fulfillment_order_from_sales_order()` |
| `shipping_order.created` | `create_shipping_order_from_fulfillment()` |
| `shipment.created` | `create_shipment_for_shipping_order()` |
| `asset.created` | `AssetCreateView.form_valid()` |
| `asset.updated` | `AssetUpdateView.form_valid()` |
| `asset.organization_transferred` | `AssetUpdateView.form_valid()` when org changes |

---

## 10. App: catalog

**Purpose:** Product master data — the authoritative source for all product information, pricing, and specifications.

### Models

#### `TaxRate`
| Field | Type |
|-------|------|
| `name` | CharField(80) |
| `code` | CharField(20), unique |
| `rate` | DecimalField(max_digits=6, decimal_places=2) |

#### `DiscountGroup`
| Field | Type |
|-------|------|
| `name` | CharField(80) |
| `slug` | SlugField(unique) |

#### `ProductCategory`
Self-referential hierarchy. `parent` FK to self (nullable, SET_NULL).

| Field | Type |
|-------|------|
| `name` | CharField(120) |
| `slug` | SlugField(unique) |
| `parent` | FK → self (nullable) |

#### `ProductStatus` (TextChoices)
`DRAFT`, `ACTIVE`, `END_OF_LIFE`, `UNAVAILABLE`

#### `AssetType` (TextChoices)
`LOAN`, `SOLD`, `INTERNAL`

#### `Product`
The central model. All other catalog models relate to it.

| Field group | Fields |
|-------------|--------|
| Identification | `name`, `short_description`, `long_description`, `brand`, `sku` (unique), `ean_gtin`, `mpn`, `upc_isbn` |
| Classification | `category` (FK → ProductCategory, PROTECT), `status`, `asset_type` |
| Financial | `purchase_price`, `list_price`, `msrp` (all Decimal MONEY, nullable), `currency`, `tax_rate` (FK), `discount_group` (FK) |
| Physical | `length`, `width`, `height` (Decimal DIM=12,4), `dimension_unit`, `weight_net`, `weight_gross` (DIM), `weight_unit`, `color`, `material`, `size_or_volume` |
| Logistics | `unit_of_measure`, `minimum_order_quantity`, `lead_time_days`, `lead_time_text`, `warehouse_location`, `inventory_tracked` |
| Service/Asset | `serial_number_required`, `warranty_months`, `maintenance_interval`, `depreciation_months`, `asset_type` |
| Lifecycle | `is_archived`, `archived_at`, `created_at`, `updated_at` |

#### `ProductPriceTier`
Quantity-break pricing attached to a product.

| Field | Type |
|-------|------|
| `product` | FK → Product (CASCADE) |
| `min_quantity` | PositiveIntegerField |
| `max_quantity` | PositiveIntegerField (nullable) |
| `unit_price` | DecimalField MONEY |

#### `ProductBOMLine`
Bill of materials / bundle composition.

| Field | Type |
|-------|------|
| `bundle_product` | FK → Product (CASCADE) |
| `component_product` | FK → Product (PROTECT) |
| `quantity` | DecimalField BOM_QTY (max_digits=10, decimal_places=3) |

#### `ProductRelationType` (TextChoices)
`ACCESSORY`, `ALTERNATIVE`, `UPSELL`, `REPLACEMENT`

#### `ProductRelation`
Cross-sell and upsell links between products.

| Field | Type |
|-------|------|
| `from_product` | FK → Product (CASCADE) |
| `to_product` | FK → Product (PROTECT) |
| `relation_type` | CharField choices |
| `sort_order` | PositiveSmallIntegerField |

#### `ProductImage`
| Field | Type |
|-------|------|
| `product` | FK → Product (CASCADE) |
| `image` | ImageField (upload via `product_image_upload_to()`) |
| `is_primary` | BooleanField |
| `sort_order` | PositiveSmallIntegerField |
| `alt_text` | CharField |
| `file_size` | PositiveIntegerField (nullable) |
| `original_filename` | CharField (nullable) |
| `uploaded_at` | DateTimeField (auto_now_add) |

Upload path: `catalog/product-images/{product_id}/{image_id}{ext}`

#### `ProductDocumentType` (TextChoices)
`DATASHEET`, `MANUAL`, `CERTIFICATION`, `MSDS`, `OTHER`

#### `ProductDocument`
| Field | Type |
|-------|------|
| `product` | FK → Product (CASCADE) |
| `document_type` | CharField choices |
| `title` | CharField(200) |
| `file` | FileField (upload_to `catalog/documents/%Y/%m/`) |
| `uploaded_at` | DateTimeField (auto_now_add) |

#### Specification models (OneToOne → Product, CASCADE)

Each spec model is an optional extension table. Multiple spec types can coexist on one product.

| Model | Key fields |
|-------|-----------|
| `ProductITSpec` | `operating_system`, `cpu`, `ram`, `storage` |
| `ProductConnectivitySpec` | `io_ports`, `wireless` (both TextField) |
| `ProductScannerSpec` | `scan_engine`, `drop_spec`, `ip_rating`, `battery_mah`, `battery_hours` |
| `ProductPrinterSpec` | `print_technology`, `print_resolution`, `print_width`, `cutter_type` |
| `ProductDisplaySpec` | `diagonal`, `resolution`, `touchscreen_type` (TouchscreenType: NONE, CAPACITIVE, RESISTIVE) |

### Views

| View | Method | Notes |
|------|--------|-------|
| `ProductListView` | GET | Filterable by status, category; excludes archived |
| `ProductDetailView` | GET | Full product with specs, images, documents, relations, price tiers |
| `ProductUpdateView` | GET/POST | Edit product fields; requires `edit_product_pricing` permission for price fields |
| `ProductImageAddView` | POST | Upload new image |
| `ProductImageDeleteView` | POST | Delete image |
| `ProductReplacementAddView` | GET/POST | Add a REPLACEMENT relation via `ReplacementPickForm` |
| `ImageLibraryView` | GET | Gallery of all product images; requires `view_productimage` permission |

---

## 11. App: pricing

**Purpose:** Define and assign pricing strategies to products or categories. The pricing rules are informational/advisory in 0.1 — they document the intended margin strategy but do not automatically recompute prices.

### Models

#### `PricingMethod` (TextChoices)
| Value | Label |
|-------|-------|
| `COST_MARKUP` | Cost + markup % |
| `GROSS_MARGIN` | Gross margin % |
| `MSRP_DISCOUNT` | MSRP discount % |
| `LIST_DISCOUNT` | List price discount % |
| `FIXED_MULTIPLIER` | Fixed multiplier on list price |

#### `RoundingMethod` (TextChoices)
`NONE`, `NEAREST_CENT`, `NEAREST_10C`, `NEAREST_50C`, `NEAREST_EURO`, `NEAREST_5`, `NEAREST_10`, `CUSTOM`

#### `PricingRule`
| Field | Type |
|-------|------|
| `name` | CharField(160), unique |
| `description` | TextField |
| `method` | CharField choices (PricingMethod) |
| `value` | DecimalField(max_digits=14, decimal_places=6) |
| `rounding` | CharField choices (RoundingMethod) |
| `rounding_increment` | DecimalField (nullable, for CUSTOM rounding) |
| `is_active` | BooleanField |
| `notes` | TextField |

`clean()` validates that `value` is positive and makes sense for the chosen method.  
`save()` calls `full_clean()` on every save.  
`method_value_display()` returns a human-readable summary, e.g. `"Cost + 55.00%"`.

#### `PricingRuleAssignment`
Links a rule to either a `Product` or a `ProductCategory` — exactly one must be set (enforced by `clean()`).

| Field | Type |
|-------|------|
| `rule` | FK → PricingRule (CASCADE) |
| `product` | FK → Product (CASCADE, nullable) |
| `category` | FK → ProductCategory (CASCADE, nullable) |
| `include_subcategories` | BooleanField (only relevant for category assignments) |
| `priority` | PositiveSmallIntegerField (lower = higher priority) |

Constraint: `(rule, product)` unique; `(rule, category)` unique.

### Views

| View | Notes |
|------|-------|
| `PricingRuleListView` | Lists all rules with assignment counts |
| `PricingRuleCreateView` | Create new rule |
| `PricingRuleDetailView` | Rule detail with all assignments |
| `PricingRuleUpdateView` | Edit rule and assignments |

---

## 12. App: relations

**Purpose:** CRM layer — hierarchical organizations, people, and all associated contact data.

### Models

#### `OrganizationCategory` (TextChoices)
`CUSTOMER`, `PROSPECT`, `SUPPLIER`, `PARTNER`, `STRATEGIC`, `INTERNAL`

#### `OrganizationUnitKind` (TextChoices)
`LEGAL_ENTITY`, `DEPARTMENT`, `BRANCH`, `TEAM`, `OTHER`

#### `OrganizationCategoryTag`
Configuration model for category labels (one row per `OrganizationCategory` value).

| Field | Type |
|-------|------|
| `code` | CharField(30), unique |
| `label` | CharField(80) |

#### `Organization`
Hierarchical: `parent` FK to self (nullable). Supports multi-category tagging.

| Field | Type |
|-------|------|
| `name` | CharField(200) |
| `legal_name` | CharField(200) |
| `parent` | FK → self (nullable, SET_NULL) |
| `unit_kind` | CharField choices |
| `primary_category` | FK → OrganizationCategoryTag (nullable, SET_NULL) |
| `categories` | ManyToManyField → OrganizationCategoryTag |
| `industry` | CharField(120) |
| `tax_id_vat` | CharField(50) |
| `registration_number` | CharField(60) |
| `website` | URLField |
| `notes` | TextField |
| `is_archived` / `archived_at` | Soft delete |

Key methods:
- `is_customer_or_prospect_relation() -> bool` — checks `primary_category` and `categories` M2M for CUSTOMER or PROSPECT codes. Used to validate quote and order counterparty eligibility.
- `hierarchy_breadcrumb(cache=None) -> str` — returns `"Root › Parent › Child"` string using optional pre-built cache dict to avoid N+1 queries.
- `build_hierarchy_cache() -> dict` — returns `{pk: (parent_id, name)}` for all organizations.
- `category_labels() -> list[str]` — human-readable category label list.
- `category_pairs() -> list[tuple]` — `[(code, label)]` tuples.

#### `OrganizationLinkType`
Configurable relationship type vocabulary (e.g. "Strategic partnership", "Logistics provider").

| Field | Type |
|-------|------|
| `name` | CharField(120), unique |
| `description` | TextField |

#### `OrganizationLink`
Lateral relationship between two organizations.

| Field | Type |
|-------|------|
| `from_organization` | FK → Organization (CASCADE) |
| `to_organization` | FK → Organization (CASCADE) |
| `link_type` | FK → OrganizationLinkType (PROTECT) |
| `start_date` | DateField (nullable) |
| `end_date` | DateField (nullable) |
| `notes` | TextField |

#### `Person`
| Field | Type |
|-------|------|
| `title_prefix` | CharField(20) |
| `first_name` | CharField(80) |
| `last_name` | CharField(120) |
| `date_of_birth` | DateField (nullable) |
| `pronouns` | CharField(40) |
| `bio` | TextField |
| `notes` | TextField |
| `is_archived` / `archived_at` | Soft delete |

#### `Affiliation`
Employment / membership timeline linking a Person to an Organization.

| Field | Type |
|-------|------|
| `person` | FK → Person (CASCADE) |
| `organization` | FK → Organization (CASCADE) |
| `job_title` | CharField(120) |
| `start_date` | DateField (nullable) |
| `end_date` | DateField (nullable) |
| `is_primary` | BooleanField |
| `notes` | TextField |

#### Generic contact models

`Address`, `Communication`, and `SocialProfile` attach to any model via `GenericForeignKey(content_type, object_id)`.

**`AddressType`:** `BILLING`, `SHIPPING`, `VISITING`, `HOME`, `POSTAL`, `OTHER`

**`Address`:**
| Field | Type |
|-------|------|
| `content_type` | FK → ContentType |
| `object_id` | UUIDField |
| `address_type` | CharField choices |
| `label` | CharField(80) |
| `street` | CharField(200) |
| `street2` | CharField(200) |
| `city` | CharField(100) |
| `state_province` | CharField(100) |
| `zipcode` | CharField(20) |
| `country` | CharField(100) |
| `is_primary` | BooleanField |

**`CommunicationType`:** `PHONE`, `EMAIL`, `FAX`

**`Communication`:**
| Field | Type |
|-------|------|
| `content_type` | FK → ContentType |
| `object_id` | UUIDField |
| `comm_type` | CharField choices |
| `label` | CharField(80) |
| `value` | CharField(200) |
| `is_primary` | BooleanField |
| `employer_organization` | FK → Organization (nullable, SET_NULL) |

`clean()` validates: phone values may only link to `employer_organization` when the GFK target is a Person.

**`SocialProfile`:**
| Field | Type |
|-------|------|
| `content_type` | FK → ContentType |
| `object_id` | UUIDField |
| `platform` | CharField(80) |
| `url` | URLField |
| `handle` | CharField(120) |

**`SpecialEvent`:**
Relationship-relevant dates/notes attached to a Person.

| Field | Type |
|-------|------|
| `person` | FK → Person (CASCADE) |
| `name` | CharField(120) |
| `event_date` | DateField (nullable) |
| `notes` | TextField |

### Views

| View | Notes |
|------|-------|
| `OrganizationListView` | Filterable by category; excludes archived by default |
| `OrganizationCreateView` | Creates org with initial category assignment |
| `OrganizationDetailView` | Full CRM view: contacts, addresses, affiliations, related quotes/orders, assets |
| `OrganizationUpdateView` | Edit org fields |
| `PersonListView` | Filterable; excludes archived |
| `PersonCreateView` | Create person; supports inline affiliation |
| `PersonDetailView` | Full contact view: affiliations, contact details, special events |
| `PersonUpdateView` | Edit person fields |

---

## 13. App: sales

**Purpose:** Complete order-to-cash pipeline. All transactional logic lives in `sales/services.py`.

### Models

#### Cart / CartLine

One cart per user (`OneToOneField`). `CartLine` is unique on `(cart, product)`.

#### `QuoteStatus` (TextChoices)
`DRAFT`, `SENT`, `ACCEPTED`, `CANCELLED`, `EXPIRED`

#### `Quote`
| Field | Type |
|-------|------|
| `reference` | CharField(32), unique |
| `created_by` | FK → User (PROTECT) |
| `relation_organization` | FK → Organization (PROTECT, nullable) |
| `internal_reference` | CharField(80) |
| `external_reference` | CharField(80) |
| `status` | CharField choices |
| `valid_until` | DateField (nullable) |
| `notes` | TextField |
| `is_locked` | BooleanField — frozen after order creation |

`clean()` validates that `relation_organization` passes `is_customer_or_prospect_relation()`.

#### `QuoteLine`
Snapshot line on a Quote.

| Field | Type |
|-------|------|
| `quote` | FK → Quote (CASCADE) |
| `product` | FK → Product (nullable, SET_NULL) |
| `product_name` | CharField(255) — snapshot |
| `sku` | CharField(64) — snapshot |
| `brand` | CharField(120) — snapshot |
| `quantity` | PositiveIntegerField |
| `unit_price` | DecimalField MONEY — snapshot |
| `currency` | CharField(3) — snapshot |
| `line_total` | DecimalField MONEY — snapshot |
| `sort_order` | PositiveSmallIntegerField |

#### `OrderStatus` (TextChoices)
`DRAFT`, `CONFIRMED`, `CANCELLED`, `FULFILLED`

**Valid status transitions** (enforced by `SalesOrderStatusUpdateView`):
- `DRAFT` → `CONFIRMED` (confirm action)
- `DRAFT` → `CANCELLED` (cancel action)
- `CONFIRMED` → `CANCELLED` (cancel action)

#### `SalesOrder`
| Field | Type |
|-------|------|
| `reference` | CharField(32), unique |
| `created_by` | FK → User (PROTECT) |
| `quote` | FK → Quote (nullable, SET_NULL) |
| `relation_organization` | FK → Organization (PROTECT, nullable) |
| `status` | CharField choices |
| `notes` | TextField |

#### `OrderLine`
Same structure as `QuoteLine` but FK to `SalesOrder`.

#### `InvoiceStatus` (TextChoices)
`DRAFT`, `ISSUED`, `CANCELLED`

#### `Invoice`
| Field | Type |
|-------|------|
| `reference` | CharField(32), unique |
| `order` | FK → SalesOrder (PROTECT) |
| `created_by` | FK → User (PROTECT) |
| `relation_organization` | FK → Organization (PROTECT, nullable) |
| `status` | CharField choices |
| `currency` | CharField(3) |
| `due_date` | DateField (nullable) |
| `notes` | TextField |

Methods: `total()`, `amount_paid()`, `balance_due()`, `is_paid_in_full()` — all compute from related lines/payments.

#### `InvoiceLine`
Same structure as `QuoteLine` / `OrderLine` but FK to `Invoice`.

#### `InvoicePayment`
| Field | Type |
|-------|------|
| `invoice` | FK → Invoice (CASCADE) |
| `amount` | DecimalField MONEY |
| `reference_note` | CharField(120) |
| `created_by` | FK → User (PROTECT) |
| `created_at` | DateTimeField (auto_now_add) |

#### `FulfillmentOrderStatus` (TextChoices)
`PENDING`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`

#### `FulfillmentOrder`
Warehouse pick list generated from a SalesOrder.

| Field | Type |
|-------|------|
| `reference` | CharField(32), unique |
| `sales_order` | FK → SalesOrder (PROTECT) |
| `created_by` | FK → User (PROTECT) |
| `status` | CharField choices |
| `notes` | TextField |

#### `FulfillmentOrderLine`
| Field | Type |
|-------|------|
| `fulfillment_order` | FK → FulfillmentOrder (CASCADE) |
| `product` | FK → Product (nullable, SET_NULL) |
| `product_name`, `sku`, `brand` | Snapshot fields |
| `quantity` | PositiveIntegerField |
| `warehouse_location` | CharField(60) — snapshot from Product |
| `sort_order` | PositiveSmallIntegerField |

#### `ShippingOrderStatus` (TextChoices)
`DRAFT`, `RELEASED`, `PARTIALLY_SHIPPED`, `SHIPPED`, `CANCELLED`

#### `ShippingOrder`
Outbound shipment document, may cover partial fulfillment quantities.

| Field | Type |
|-------|------|
| `reference` | CharField(32), unique |
| `fulfillment_order` | FK → FulfillmentOrder (PROTECT) |
| `sales_order` | FK → SalesOrder (PROTECT) |
| `created_by` | FK → User (PROTECT) |
| `status` | CharField choices |
| `notes` | TextField |

#### `ShippingOrderLine`
| Field | Type |
|-------|------|
| `shipping_order` | FK → ShippingOrder (CASCADE) |
| `fulfillment_line` | FK → FulfillmentOrderLine (PROTECT) |
| `quantity` | PositiveIntegerField |

#### `ShipmentStatus` (TextChoices)
`PLANNED`, `IN_TRANSIT`, `DELIVERED`, `CANCELLED`

#### `Shipment`
One physical dispatch event under a shipping order.

| Field | Type |
|-------|------|
| `shipping_order` | FK → ShippingOrder (CASCADE) |
| `sequence` | PositiveSmallIntegerField |
| `carrier` | CharField(120) |
| `tracking_number` | CharField(120) |
| `status` | CharField choices |
| `notes` | TextField |

Unique together: `(shipping_order, sequence)`.

#### `ShipmentLine`
| Field | Type |
|-------|------|
| `shipment` | FK → Shipment (CASCADE) |
| `shipping_order_line` | FK → ShippingOrderLine (PROTECT) |
| `quantity` | PositiveIntegerField |

### `snapshot_line_from_product(product, quantity, sort_order) -> dict`
Returns a dict of snapshot fields ready for `QuoteLine`, `OrderLine`, or `InvoiceLine` creation. Reads `product.list_price` as `unit_price` and computes `line_total = unit_price × quantity`.

### Services (`sales/services.py`)

All functions are `@transaction.atomic` and accept an optional `request` for audit logging.

| Function | Description |
|----------|-------------|
| `get_or_create_cart(user)` | Returns the user's Cart, creating if absent |
| `add_to_cart(*, user, product, quantity, request)` | Adds/increments CartLine, logs `cart.line_added` |
| `set_cart_line_quantity(*, user, line_id, quantity, request)` | Updates or deletes CartLine; logs change |
| `create_quote_from_cart(*, user, relation_organization, internal_reference, external_reference, request)` | Creates Quote + QuoteLines from cart, clears cart |
| `create_order_from_cart(*, user, relation_organization, request)` | Creates SalesOrder + OrderLines from cart, clears cart |
| `refresh_quote_prices_from_catalog(quote, *, request)` | Updates unlocked QuoteLine prices from live catalog; returns count |
| `create_order_from_quote(*, quote, user, request)` | Creates SalesOrder (CONFIRMED) from accepted quote; locks quote |
| `create_invoice_from_order(*, order, user, request)` | Creates Invoice + InvoiceLines from OrderLines |
| `add_invoice_payment(*, invoice, amount, reference_note, user, request)` | Records payment; validates balance |
| `create_fulfillment_order_from_sales_order(*, order, user, request)` | Creates FulfillmentOrder + FulfillmentOrderLines |
| `fulfillment_line_unallocated_quantity(fo_line)` | Returns qty not yet allocated to any ShippingOrderLine |
| `shipping_order_line_unshipped_quantity(sol)` | Returns qty not yet on any non-cancelled ShipmentLine |
| `refresh_shipping_order_status(shipping_order)` | Updates ShippingOrder status based on shipment coverage |
| `create_shipping_order_from_fulfillment(*, fulfillment_order, user, quantities_by_line_id, notes, request)` | Creates ShippingOrder from allocation dict |
| `create_shipment_for_shipping_order(*, shipping_order, user, carrier, tracking_number, lines_qty, notes, request)` | Creates Shipment + ShipmentLines; updates ShippingOrder status |

### Forms

| Form | Purpose |
|------|---------|
| `CreateQuoteFromCartForm` | Organization + reference fields for quote creation |
| `CreateOrderFromCartForm` | Organization field for direct order from cart |
| `QuoteHeaderForm` | Edit Quote fields (ModelForm) |
| `QuoteLineEditForm` | Edit QuoteLine qty/price/currency |
| `QuoteLineFormSet` | InlineFormSet for all lines on a quote |
| `AddToCartForm` | Quantity input on product detail page |
| `CartLineQuantityForm` | Update/remove cart line quantity |
| `ReplacementPickForm` | Pick a replacement product |
| `InvoicePaymentForm` | Payment amount + reference; accepts `max_amount=` kwarg to set `max_value` |
| `ShipmentHeaderForm` | Carrier, tracking, notes |
| `make_create_shipping_order_form(fulfillment)` | Dynamic form with one qty field per fulfillment line |
| `make_shipment_lines_form(shipping_order)` | Dynamic form with one qty field per shipping order line |

### `InvoicePaymentForm` — max_amount

The form constructor accepts `max_amount` to set a dynamic `max_value` on the amount field:

```python
InvoicePaymentForm(max_amount=invoice.balance_due())
```

This prevents recording a payment larger than the outstanding balance.

### List filtering

`sales.list_filtering` provides reusable filter helpers applied to all list views:
- `apply_reference_icontains(qs, params)` — search by reference
- `apply_relation_org_in(qs, params, field)` — filter by organization
- `apply_status(qs, params, status_class)` — filter by status value
- `sales_list_filter_context(request, status_choices)` — returns common context dict for filter UI

---

## 14. App: assets

**Purpose:** Installed asset lifecycle management. Tracks customer-site equipment from installation through maintenance, recalls, and eventual replacement.

### Models

#### `AssetStatus` (TextChoices)
`PENDING_INSTALL`, `IN_SERVICE`, `UNDER_REPAIR`, `WARRANTY`, `END_OF_LIFE_NEAR`, `RETIRED`, `DISPOSED`

#### `Asset`
Central model. Represents one physical unit at a customer site.

| Field | Type |
|-------|------|
| `organization` | FK → Organization (PROTECT) |
| `person` | FK → Person (nullable, SET_NULL) — primary contact |
| `product` | FK → Product (nullable, SET_NULL) |
| `order_line` | FK → OrderLine (nullable, SET_NULL) — purchase reference |
| `name` | CharField(200) — optional; if blank, `display_name()` uses product name |
| `serial_number` | CharField(120) |
| `asset_tag` | CharField(80) |
| `purchase_date` | DateField (nullable) |
| `installation_date` | DateField (nullable) |
| `warranty_end_date` | DateField (nullable) |
| `expected_end_of_life_date` | DateField (nullable) |
| `status` | CharField choices |
| `location_note` | CharField(200) |
| `notes` | TextField |
| `is_archived` / `archived_at` | Soft delete |
| `created_by` | FK → User (PROTECT) |

`display_name()` — returns `name` if set, else `product.name`, else `"Asset {asset_tag}"`.  
`clean()` — validates that `organization` passes `is_customer_or_prospect_relation()` when set.

#### `AssetOrganizationTransfer`
Append-only audit trail of asset ownership changes.

| Field | Type |
|-------|------|
| `asset` | FK → Asset (CASCADE) |
| `from_organization` | FK → Organization (nullable, SET_NULL) |
| `to_organization` | FK → Organization (PROTECT) |
| `transferred_by` | FK → User (PROTECT) |
| `transferred_at` | DateTimeField (auto_now_add) |
| `note` | TextField |

#### `AssetEventType` (TextChoices)
`INSTALLATION`, `REPAIR`, `INSPECTION`, `RECALL_SERVICE`, `CALIBRATION`, `WARRANTY_CLAIM`, `RECOMMENDATION`, `NOTE`, `OTHER`

#### `AssetEvent`
Timeline entry on an asset.

| Field | Type |
|-------|------|
| `asset` | FK → Asset (CASCADE) |
| `event_type` | CharField choices |
| `title` | CharField(200) |
| `description` | TextField |
| `occurred_on` | DateField |
| `vendor_name` | CharField(120) |
| `reference_external` | CharField(120) |
| `cost_amount` | DecimalField MONEY (nullable) |
| `cost_currency` | CharField(3) |
| `related_product` | FK → Product (nullable, SET_NULL) |
| `recall_campaign` | FK → RecallCampaign (nullable, SET_NULL) |
| `created_by` | FK → User (PROTECT) |

#### `RecallCampaign`
Manufacturer or regulatory recall campaign.

| Field | Type |
|-------|------|
| `reference` | CharField(32), unique |
| `title` | CharField(200) |
| `description` | TextField |
| `remedy_description` | TextField |
| `product` | FK → Product (nullable, SET_NULL) |
| `announced_date` | DateField (nullable) |
| `is_active` | BooleanField |
| `is_archived` / `archived_at` | Soft delete |
| `created_by` | FK → User (PROTECT) |

#### `AssetRecallStatus` (TextChoices)
`PENDING`, `ACTION_REQUIRED`, `IN_PROGRESS`, `COMPLETED`, `NOT_AFFECTED`, `EXEMPT`

#### `AssetRecallLink`
Links a specific asset to a recall campaign with status tracking.

| Field | Type |
|-------|------|
| `recall_campaign` | FK → RecallCampaign (CASCADE) |
| `asset` | FK → Asset (CASCADE) |
| `status` | CharField choices |
| `completed_on` | DateField (nullable) |
| `notes` | TextField |

Unique together: `(recall_campaign, asset)`.

#### `MaintenancePlanStatus` (TextChoices)
`DRAFT`, `ACTIVE`, `ARCHIVED`

#### `MaintenancePlan`
Multi-year maintenance outlook (MJOP — *Meerjarenonderhoudsplan*) for an organization's hardware estate.

| Field | Type |
|-------|------|
| `reference` | CharField(32), unique |
| `organization` | FK → Organization (PROTECT) |
| `name` | CharField(200) |
| `valid_from` | DateField |
| `valid_until` | DateField |
| `status` | CharField choices |
| `notes` | TextField |
| `created_by` | FK → User (PROTECT) |

`clean()` validates `valid_from < valid_until`.

#### `MaintenancePlanLineStatus` (TextChoices)
`PLANNED`, `SCHEDULED`, `IN_PROGRESS`, `COMPLETED`, `DEFERRED`, `CANCELLED`

#### `MaintenancePlanLine`
One year-bucket entry in a maintenance plan. Can represent a routine maintenance task or a promoted replacement recommendation.

| Field | Type |
|-------|------|
| `plan` | FK → MaintenancePlan (CASCADE) |
| `plan_year` | PositiveSmallIntegerField |
| `sort_order` | PositiveSmallIntegerField |
| `title` | CharField(200) |
| `description` | TextField |
| `related_asset` | FK → Asset (nullable, SET_NULL) |
| `recommended_product` | FK → Product (nullable, SET_NULL) |
| `is_promoted` | BooleanField — highlights replacement/investment rows |
| `estimated_cost_note` | CharField(200) |
| `line_status` | CharField choices |

#### `ReplacementPriority` (TextChoices)
`LOW`, `MEDIUM`, `HIGH`

#### `ReplacementRecommendationStatus` (TextChoices)
`OPEN`, `ACCEPTED`, `DISMISSED`, `SUPERSEDED`

#### `AssetReplacementRecommendation`
Replacement suggestion attached to an asset, feeding the sales pipeline.

| Field | Type |
|-------|------|
| `asset` | FK → Asset (CASCADE) |
| `suggested_product` | FK → Product (nullable, SET_NULL) |
| `rationale` | TextField |
| `priority` | CharField choices |
| `status` | CharField choices |
| `is_archived` / `archived_at` | Soft delete |
| `created_by` | FK → User (PROTECT) |

### Views

| View | Notes |
|------|-------|
| `AssetListView` | Multi-faceted filtering: org tree, product, person, status |
| `AssetCreateView` | Creates asset + initial `AssetOrganizationTransfer`; logs event |
| `AssetUpdateView` | Detects org change; creates transfer record if changed |
| `AssetDetailView` | Full timeline: events, recall links, recommendations, transfers |
| `AssetEventCreateView` | Add timeline event to asset |
| `ReplacementRecommendationCreateView` | Add replacement recommendation to asset |
| `RecallLinkUpdateView` | Update recall link status for a specific asset |
| `RecallCampaignListView` | Active recall campaigns |
| `RecallCampaignCreateView` | Create recall campaign |
| `RecallCampaignDetailView` | Campaign detail with affected asset list |
| `RecallCampaignUpdateView` | Edit campaign |
| `MaintenancePlanListView` | Plans filterable by organization |
| `MaintenancePlanCreateView` | Create MJOP |
| `MaintenancePlanDetailView` | Full MJOP with year-grouped lines |
| `MaintenancePlanUpdateView` | Edit plan header |
| `MaintenancePlanLineCreateView` | Add a line to an existing plan |

---

## 15. App: contracts

**Purpose:** Template-based service contracts with a formula engine for computing annual costs.

### Models

#### `ServiceRate`
Hourly rate reference for use in contract formulas.

| Field | Type |
|-------|------|
| `name` | CharField(120) |
| `code` | SlugField, unique — used as variable name in formulas |
| `description` | TextField |
| `rate_per_hour` | DecimalField MONEY |
| `currency` | CharField(3) |
| `is_active` | BooleanField |

#### `ContractVariableType` (TextChoices)
`USER_INPUT`, `SERVICE_RATE`, `CONSTANT`

#### `ContractTemplate`
Reusable blueprint defining a formula and its variables.

| Field | Type |
|-------|------|
| `name` | CharField(160), unique |
| `description` | TextField |
| `formula` | TextField — arithmetic expression using variable names |
| `result_label` | CharField(120) — label for computed output |
| `is_active` | BooleanField |
| `notes` | TextField |

`clean()` validates the formula syntax using `contracts.services.validate_formula()`.

#### `ContractTemplateVariable`
Named variable in a template formula.

| Field | Type |
|-------|------|
| `template` | FK → ContractTemplate (CASCADE) |
| `name` | CharField(60) — Python identifier; used in formula |
| `label` | CharField(120) — UI label |
| `variable_type` | CharField choices |
| `service_rate` | FK → ServiceRate (nullable, SET_NULL) — used when type=SERVICE_RATE |
| `constant_value` | DecimalField (nullable) — used when type=CONSTANT |
| `default_value` | DecimalField (nullable) — pre-fill for USER_INPUT |
| `unit` | CharField(40) — display unit, e.g. `'EUR/h'`, `'%'` |
| `sort_order` | PositiveSmallIntegerField |

`clean()` validates reserved variable names (`duration_years`, `duration_months`, `quote_total`, `order_total`, `asset_purchase_price`) are not redefined.

`resolved_value() -> Decimal | None` — returns the variable's resolved value regardless of type.

#### `ContractStatus` (TextChoices)
`DRAFT`, `ACTIVE`, `EXPIRED`, `TERMINATED`

#### `Contract`
Instance of a template, computed against a specific organization and linked documents.

| Field | Type |
|-------|------|
| `reference` | CharField(32), unique |
| `template` | FK → ContractTemplate (PROTECT) |
| `organization` | FK → Organization (PROTECT) |
| `status` | CharField choices |
| `start_date` | DateField (nullable) |
| `end_date` | DateField (nullable) |
| `quote` | FK → Quote (nullable, SET_NULL) |
| `sales_order` | FK → SalesOrder (nullable, SET_NULL) |
| `asset` | FK → Asset (nullable, SET_NULL) |
| `notes` | TextField |
| `computed_result` | DecimalField MONEY (nullable) |
| `computed_at` | DateTimeField (nullable) |

Properties:
- `duration_years -> Decimal | None` — `(end_date - start_date).days / 365.25`
- `duration_months -> Decimal | None` — `duration_years * 12`

`clean()` validates `start_date < end_date` when both set.

#### `ContractVariableValue`
Stores the user-supplied value for a `USER_INPUT` variable on a specific contract.

| Field | Type |
|-------|------|
| `contract` | FK → Contract (CASCADE) |
| `variable` | FK → ContractTemplateVariable (CASCADE) |
| `value` | DecimalField MONEY |

Unique together: `(contract, variable)`.

### Formula engine (`contracts/services.py`)

The formula engine evaluates arithmetic expressions safely using Python's `ast` module.

**Supported syntax:** numeric literals, variable names, `+`, `-`, `*`, `/`, `**`, unary minus/plus, parentheses. No function calls, string literals, or imports.

**Built-in variables** automatically injected into every formula evaluation:

| Variable | Source |
|----------|--------|
| `duration_years` | `(end_date - start_date).days / 365.25` |
| `duration_months` | `duration_years * 12` |
| `quote_total` | Sum of `quote.lines.line_total` |
| `order_total` | Sum of `sales_order.lines.line_total` |
| `asset_purchase_price` | `asset.order_line.unit_price` |

**Service functions:**

| Function | Description |
|----------|-------------|
| `safe_eval_formula(formula, variables)` | Evaluates formula string against variable dict; raises `ValueError` on bad syntax or unknown variables |
| `validate_formula(formula, variable_names)` | Returns error string or `None`; used in `ContractTemplate.clean()` |
| `build_variable_context(contract)` | Resolves all variables → `(dict, missing_list)` |
| `compute_contract(contract)` | Evaluates formula → `(result, error)` |
| `refresh_computed_result(contract)` | Computes and saves `computed_result` + `computed_at` to the contract |
| `create_variable_value_stubs(contract)` | Creates `ContractVariableValue` rows for all `USER_INPUT` variables (with defaults) |

### Views

| View | Notes |
|------|-------|
| `ServiceRateListView` | All rates with active/inactive indicator |
| `ServiceRateCreateView` | Create rate |
| `ServiceRateUpdateView` | Edit rate |
| `ContractTemplateListView` | All templates |
| `ContractTemplateCreateView` | Create template + variables inline (using `_TemplateMixin` with formset) |
| `ContractTemplateUpdateView` | Edit template + variables inline |
| `ContractTemplateDetailView` | Template with variables and linked contracts (last 10) |
| `ContractListView` | Filterable by status and search |
| `ContractCreateView` | Creates contract, calls `create_variable_value_stubs()` and `refresh_computed_result()` |
| `ContractDetailView` | Full contract with variable rows, computed result, and error display |
| `ContractUpdateView` | Edit contract header + variable values inline (`VariableValueFormSet`); calls `refresh_computed_result()` on save |

---

## 16. Frontend & Templating

### Base template

`catalog/templates/catalog/base.html` is the master template inherited by all pages. It provides:

- Responsive sidebar layout (fixed on desktop, drawer on mobile)
- Navigation with active-state highlighting by URL namespace and name
- Flash message display with typed icons (error, warning, success, info)
- POST form loading state: submit buttons are disabled and show a spinner on click
- Footer showing version (`{{ app_version }}`) and build hash (`{{ app_build }}`)
- Skip-to-content link for accessibility

### Sidebar navigation sections

| Section | Links |
|---------|-------|
| (top) | Dashboard |
| Catalog | Products, Image library (permission-gated), Pricing rules |
| Sales | Cart (with item count badge), Quotes, Orders, Invoices, Fulfillment, Shipping |
| CRM | Organizations, Contacts |
| Assets | Assets, Recalls, Maintenance plans |
| Contracts | Service rates, Templates, Contracts |
| Account | Profile, User directory |

### Tailwind CSS

Tailwind 3.4 is loaded via CDN in development. The custom color palette is named `nova` (sky blue shades: 50, 100, 200, 500, 600, 700, 900). All interactive elements use `nova-600` / `nova-700` as primary action colors.

For production builds: `npm run build:css` processes `static_src/` into the compiled CSS file. Watch mode: `npm run watch:css`.

### Icons

FontAwesome 6 is self-hosted in `static/vendor/fontawesome/`. All icons use `fa-solid` or `fa-regular` with `aria-hidden="true"` for accessibility.

### JavaScript

No JavaScript framework is used. Inline `<script>` blocks handle:
- Sidebar open/close on mobile
- POST form submit loading state (disable button, show spinner)
- Invoice payment progress bar (percentage computed from template variables)

### Template inheritance

```
catalog/base.html          ← master layout
  └── sales/quote_detail.html
  └── sales/order_detail.html
  └── sales/invoice_detail.html
  └── catalog/product_detail.html
  └── core/dashboard.html
  └── ... (all other templates)
```

---

## 17. Data Design Patterns

### 1. UUID primary keys everywhere

All domain models use UUID4 primary keys. This means:
- No predictable sequential IDs are exposed in URLs
- Records can be created off-database and synced safely
- Human-readable references (`Q-2026-00001`) are displayed in the UI

### 2. Snapshot on creation

`QuoteLine`, `OrderLine`, and `InvoiceLine` store a copy of the product's commercial data at the time the document is created. Subsequent catalog changes do not alter historical records. The `product` FK is retained but nullable — if the product is deleted, the line data persists.

### 3. Service layer isolation

All multi-step writes go through `services.py` functions. Views call services; models contain only field definitions and single-object validation. This makes business logic independently testable and prevents duplication across API endpoints or management commands.

### 4. Append-only audit log

The `EventLog` model is never updated or deleted in the application. It provides a tamper-evident record of who did what and when.

### 5. Generic contacts via ContentType

`Address`, `Communication`, and `SocialProfile` use Django's `GenericForeignKey` to attach to either `Organization` or `Person`. This avoids duplicating contact tables and allows future attachment to other entity types without schema changes.

### 6. Asset transfer audit trail

When an `Asset` changes ownership (its `organization` FK changes), `AssetUpdateView` creates an `AssetOrganizationTransfer` record before saving. This gives a complete, ordered history of where the asset has been.

### 7. Formula-based contract pricing

Contract costs are not hardcoded. A `ContractTemplate` stores a formula string and variable definitions. Each `Contract` stores user-supplied values for its variables. The formula engine (`contracts.services.safe_eval_formula`) evaluates the expression at save time and caches the result on the `Contract.computed_result` field.

### 8. Soft deletes for archivable entities

`Product`, `Organization`, `Person`, `Asset`, `RecallCampaign`, and `AssetReplacementRecommendation` are never hard-deleted by the application. They receive `is_archived=True` and `archived_at=<timestamp>`. List views filter these out; detail views retain them for reference.

---

## 18. Demo Data

A management command seeds comprehensive demo data covering all screens:

```bash
python manage.py create_demo_data                   # idempotent seed
python manage.py create_demo_data --clear           # wipe + re-seed
python manage.py create_demo_data --clear --skip-images  # skip internet downloads
```

### Seeded data summary

| Category | Records |
|----------|---------|
| Tax rates | 4 (NL standard 21%, NL reduced 9%, EU zero-rate, DE standard 19%) |
| Discount groups | 3 (Retail, Wholesale, Partner/integrator) |
| Product categories | 9 (hierarchical) |
| Products | 14 (active, EOL, draft, unavailable statuses) |
| Product images | 10 (downloaded from loremflickr.com; Pillow gradient fallback) |
| Product price tiers | 4 sets |
| Product documents | 6 (datasheet, manual, certification) |
| Technical specs | 14 spec records across 5 spec tables |
| Organizations | 11 (including hierarchy, sub-departments) |
| People | 8 |
| Affiliations | 10 |
| Quotes | 5 (Draft, Sent, Accepted/locked, Draft, Expired) |
| Sales orders | 4 (Fulfilled, Confirmed ×2, Draft) |
| Invoices | 3 (partial payment, overdue/unpaid, paid in full) |
| Fulfillment orders | 3 (Completed, Pending, In progress) |
| Shipping orders | 2 (Shipped, Partially shipped) |
| Shipments | 2 (Delivered, In transit) |
| Assets | 6 (across 2 customer organizations) |
| Asset events | 9 |
| Recall campaigns | 1 (with linked asset) |
| Maintenance plan | 1 (5-year MJOP with 5 lines, 2 promoted) |
| Replacement recommendations | 1 |
| Pricing rules | 4 (with assignments) |
| Service rates | 3 |
| Contract templates | 2 (with variables) |
| Contracts | 3 (Active, with computed results) |
| Cart | Pre-loaded for demo user |

### Image strategy
Product images are downloaded from `loremflickr.com` using category-specific keywords and a lock seed for consistency. If the network is unavailable or the download fails, a Pillow-generated gradient placeholder is created automatically. The `--skip-images` flag forces Pillow generation for all products.
