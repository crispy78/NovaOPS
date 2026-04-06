# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Python setup
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt

# Django
python manage.py migrate
python manage.py runserver
python manage.py createsuperuser
python manage.py test <app>          # e.g. python manage.py test catalog

# CSS (Tailwind)
npm install
npm run build:css    # one-time build
npm run watch:css    # watch mode during development
```

## Architecture

**Stack:** Django 5.2 (MTV, server-rendered), SQLite, Tailwind CSS 3.4. No REST API — pure Django templates.

**Apps:**
- `core/` — `UUIDPrimaryKeyModel` abstract base (all domain models inherit this); protected media file serving
- `accounts/` — email-based auth, user profiles
- `audit/` — append-only `EventLog` model; use `log_event()` for all significant state changes
- `catalog/` — product master data (see below)
- `relations/` — CRM: organizations, people, affiliations, addresses (via GenericForeignKey)
- `sales/` — full order-to-cash pipeline
- `assets/` — installed equipment tracking and service history

**Sales pipeline order:** Cart → Quote → SalesOrder → Invoice + FulfillmentOrder → ShippingOrder → Shipment → InvoicePayment. All creation logic lives in `sales/services.py` as standalone transactional functions (not model methods).

**Catalog data model:** `Product` is the rich master record. Spec detail goes into optional OneToOne tables (`ProductITSpec`, `ProductScannerSpec`, `ProductPrinterSpec`, etc.). Pricing uses `ProductPriceTier` (quantity breaks) and `TaxRate`. BOM composition via `ProductBOMLine`.

**Snapshot pattern:** `QuoteLine`, `OrderLine`, `InvoiceLine` snapshot product name/SKU/price at creation time via `snapshot_line_from_product()`. Never read live product prices from historical documents.

**Soft delete:** Products, Organizations, People, and Assets use `is_archived` / `is_archived_at`. Filter these out in list queries; they're retained for audit history.

**Generic contacts:** `Address`, `Communication`, `SocialProfile` attach to both `Person` and `Organization` via `GenericForeignKey` — no duplication.

**Reference numbers:** Human-readable refs (`Q-{year}-{count:05d}`, `SO-...`, `INV-...`, `FO-...`, `SHP-...`) are used in URLs and UI. UUIDs are internal PKs only.

**Permissions:** `LoginRequiredMixin` on all views; `PermissionRequiredMixin` for sensitive ops. Custom model permissions on `Product` (`view_product_purchase_price`, `edit_product_pricing`, `archive_product`) and on `Organization`/`Person`.

**CSS:** Tailwind source is in `static_src/`. The custom color palette is named `nova` (blue shades). Always run `watch:css` during template work.

**Context processors:** Cart item count is injected into every template context automatically.

**Decimal fields:** Models use a `MONEY = dict(max_digits=12, decimal_places=2)` module-level constant for consistent money field definitions.
