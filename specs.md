# NovaOPS 0.1 - Product Specification

## Overview

NovaOPS is a server-rendered Django 5.2 business operations platform for wholesale distributors and B2B companies. It covers the full commercial lifecycle from product master data through CRM, quoting, order management, invoicing, warehouse fulfilment, procurement, asset tracking, and contract management - all in a single application with no REST API.

**Stack:** Django 5.2 · SQLite · Tailwind CSS 3.4 · Gunicorn · Nginx  
**Auth:** Email-based login · UUID primary keys · Permission-based access control

---

## Table of Contents

1. [Authentication & Users](#1-authentication--users)
2. [Dashboard](#2-dashboard)
3. [Catalog - Product Management](#3-catalog---product-management)
4. [Relations - CRM](#4-relations---crm)
5. [Sales Pipeline](#5-sales-pipeline)
6. [Inventory & Warehousing](#6-inventory--warehousing)
7. [Procurement](#7-procurement)
8. [Assets & Service](#8-assets--service)
9. [Pricing Rules](#9-pricing-rules)
10. [Contracts](#10-contracts)
11. [Audit Log](#11-audit-log)
12. [Reports](#12-reports)
13. [Site Settings](#13-site-settings)
14. [Search](#14-search)
15. [Demo Mode](#15-demo-mode)
16. [Architectural Patterns](#16-architectural-patterns)
17. [Permission Reference](#17-permission-reference)

---

## 1. Authentication & Users

### Login
- Email-address and password login (no username required)
- No public self-registration - accounts are created by administrators
- Password change via profile settings

### User Management (admin only)
- User list with active/inactive filter
- Create user with name, email, password, staff flag
- Edit user details and reset password
- Granular Django permission assignment per user
- User directory listing all active accounts

### Access Control
- Every page requires login (`LoginRequiredMixin` on all views)
- Sensitive operations protected with `PermissionRequiredMixin`
- Custom permissions: `view_product_purchase_price`, `edit_product_pricing`, `archive_product`, `archive_organization`, `archive_person`

---

## 2. Dashboard

Central overview page injected with live counts and summary data:

- Revenue charts (sales over time)
- Outstanding invoice value and overdue count
- Recent quotes, orders, and invoices
- Low-stock alerts
- Quick-links to common actions

The cart item count is injected into every page context automatically.

---

## 3. Catalog - Product Management

### Products

Full product master record with 50+ fields:

**Identity**
- SKU (unique identifier), EAN/GTIN, MPN, UPC/ISBN
- Name, brand, short description (255 chars), long description (rich text)
- Lifecycle status: Draft · Active · End of Life · Unavailable

**Physical**
- Dimensions: length, width, height (with unit), weight net/gross (with unit)
- Color, material, size or volume text

**Financial Defaults**
- Purchase price (cost), list price, MSRP/RRP
- Currency (per-product default, overridden by site setting in documents)
- Tax rate (FK to TaxRate)
- Discount group (FK to DiscountGroup)

**Logistics**
- Unit of measure (piece, roll, box, etc.)
- Minimum order quantity (MOQ)
- Reorder point, lead time days, lead time text
- Warehouse location (bin/aisle reference)
- Inventory tracked flag

**Asset / Service**
- Serial number required flag
- Warranty months
- Maintenance interval text
- Depreciation months
- Asset type (sold, loaned, rental)

**Soft Delete**
- `is_archived` / `archived_at` - archived products are hidden from lists but retained for historical documents

### Product Lifecycle
- Create, edit, archive, unarchive
- Bulk archive selected products
- CSV export of full catalog

### Price Tiers
- Quantity break pricing: min quantity → max quantity → unit price
- Multiple tiers per product; overlap validation enforced
- Used when snapshotting quote and order lines

### Bill of Materials (BOM)
- Bundle products contain component lines (product + quantity)
- Components resolved at kit build / order fulfilment

### Product Options
- **Inline options** - non-standalone add-ons with custom name, SKU, price delta
- **Product-as-option** - existing standalone product sold as add-on
- Options can be required, default-selected, or optional
- Appear on cart, quote, and order line creation

### Product Relations
- Cross-sell link types: Accessory · Alternative · Upsell · Replacement
- Displayed on product detail for sales guidance

### Images
- Primary image + gallery with sort order
- Alt text per image
- Image library view across all products

### Documents
- Attach datasheets, manuals, certifications, MSDS
- Document type classification
- File download from product detail

### Technical Specifications
Optional one-to-one spec tables for specific device categories:

| Spec Type | Key Fields |
|---|---|
| IT | OS, CPU, RAM, Storage |
| Connectivity | I/O ports, wireless |
| Scanner / Handheld | Scan engine, drop spec, IP rating, battery mAh, battery hours |
| Printer | Print technology, resolution, print width, cutter type |
| Display / Monitor | Diagonal, resolution, touchscreen type |

### Categories
- Hierarchical (parent → child, unlimited depth)
- Used for price rule assignments and catalog filtering

### Tax Rates
- Code, name, percentage
- Assigned per product; copied to document lines at snapshot time
- CRUD management view

### Discount Groups
- Named segments (e.g., Wholesale, Retail, Partner)
- Assigned to product; referenced by pricing rules

---

## 4. Relations - CRM

### Organizations

Hierarchical entity model covering holding companies, subsidiaries, departments, and branches.

**Structure**
- Parent-child hierarchy (unlimited depth)
- Unit kind: Legal Entity · Department · Branch · Team · Other
- Breadcrumb path generation
- PROTECT foreign key prevents deletion of parents with children

**Classification**
- Primary category tag: Customer · Prospect · Supplier · Partner · Strategic · Internal
- Multi-tag secondary categories

**Data**
- Legal name, tax ID / VAT number, registration number
- Industry, website
- Notes (internal)
- Created / updated timestamps
- Soft delete (`is_archived` / `archived_at`)

**Lateral Links**
- Organisation-to-organisation relationships outside the hierarchy
- Configurable link types (e.g., Strategic partnership, Logistics provider, Distributor)
- Date range (start / end date)
- Notes per link

### People

Individual contacts linked to organizations via affiliations.

**Data**
- Title prefix, first name, last name
- Pronouns, date of birth, bio, notes
- Soft delete (`is_archived` / `archived_at`)

**Affiliations**
- Links Person → Organization with job title and date range
- Primary role indicator
- Multiple active affiliations supported (consultant at multiple orgs)
- Historical affiliations retained

**Special Events**
- Birthdays, anniversaries, or custom reminders attached to a person

### Generic Contact Details

Address, Communication, and SocialProfile attach to **both** Person and Organization via `GenericForeignKey` — no duplication.

**Addresses**
- Types: Billing · Shipping · Visiting · Home · Postal · Other
- Full postal fields: street, street2, city, state/province, zipcode, country
- Label and primary indicator

**Communications**
- Types: Phone · Email · Fax
- Label (Work, Mobile, Direct, etc.) and primary indicator
- Optional employer organisation link on person records

**Social Profiles**
- Platform name (LinkedIn, Instagram, X, etc.)
- URL and handle

---

## 5. Sales Pipeline

Complete order-to-cash flow:

```
Cart → Quote → SalesOrder → Invoice
                         → FulfillmentOrder → ShippingOrder → Shipment
                                                           → InvoicePayment
```

### Cart
- One cart per logged-in user
- Add products (with options) to cart
- Update quantities, remove lines
- Cart item count shown in every page header
- Cart → Quote creation (with snapshot)
- Cart → Order creation (direct, no quote)

### Quotes

**Creation**
- From cart (snapshot of current lines) or directly
- Links to a customer / prospect organization

**Data**
- Reference: `Q-YYYY-NNNNN`
- Internal reference, valid-until date, notes
- Status: Draft · Sent · Accepted · Cancelled · Expired

**Line Snapshot Pattern**
Quote lines capture at creation time:
- Product name, SKU, brand
- Quantity, unit price (from price tier if applicable)
- Tax rate percentage
- Currency, line total

Lines **never** read live catalog prices. Historical quotes remain accurate.

**Actions**
- Refresh prices (re-snapshot lines from current catalog)
- Mark as Sent, Accepted, Cancelled, Expired
- Create sales order from accepted quote (quote is then locked)
- Print / PDF view

### Sales Orders

- Reference: `SO-YYYY-NNNNN`
- Status: Draft · Confirmed · Cancelled · Fulfilled
- Optional quote link (locked when order is created from quote)
- Order lines snapshot at creation time
- Create invoice from order
- Create fulfillment order from order
- Update status

### Invoices

- Reference: `INV-YYYY-NNNNN`
- Linked to sales order (PROTECT - order cannot be deleted while invoice exists)
- Status: Draft · Issued · Cancelled
- Currency, due date, bill-to organization
- Invoice lines snapshot from order lines

**Financials (calculated, not stored)**
- Subtotal (ex. VAT)
- VAT total (grouped by rate)
- Grand total
- Amount paid (sum of payments)
- Balance due

**Payments**
- Append-only payment records (amount, reference note)
- Multiple partial payments supported
- `is_paid_in_full` when balance due = 0

**Credit Notes**
- Reference: `CN-YYYY-NNNNN`
- Issued against an invoice
- Reason text, organization
- Line items with optional link to original invoice lines
- Print view

**Actions**
- Issue invoice (Draft → Issued)
- Record payment
- Cancel invoice
- Create credit note
- Update due date
- Print / PDF view
- CSV export of invoice list

### Fulfilment Orders

- Reference: `FO-YYYY-NNNNN`
- Generated from a sales order
- Status: Pending · In Progress · Completed · Cancelled
- Lines include product name, SKU, quantity, and warehouse bin location
- Mark as complete when all items picked

### Shipping Orders

- Reference: `SHP-YYYY-NNNNN`
- Linked to fulfilment order and sales order
- Status: Draft · Released · Partially Shipped · Shipped · Cancelled
- Lines link to fulfilment lines with quantity (supports partial shipment)
- Multiple shipments per shipping order

### Shipments

- One physical dispatch (parcel, pallet, truck)
- Carrier, tracking number, shipped-at timestamp
- Status: Planned · In Transit · Delivered · Cancelled
- Sequence number (1st shipment, 2nd, etc.)
- Lines link to shipping order lines

---

## 6. Inventory & Warehousing

### Warehouses
- Code (unique), name, address, country
- Active / inactive flag

### Stock Locations
- Bin / rack / aisle within a warehouse (e.g., `A-01-02`, `Shelf 3B`)
- Unique code per warehouse
- Active / inactive flag

### Stock Entries
- Denormalized current stock level per product per location
- Updated on every movement (receipt, shipment, adjustment, transfer)
- Unique constraint: (product, location)

### Stock Movements (append-only)
- Types: Purchase receipt · Shipment · Manual adjustment · Transfer in · Transfer out · Customer return
- Delta (positive = stock in, negative = stock out)
- Reference field (e.g., PO-2026-00001)
- Created by user + timestamp

### Features
- Stock adjustment (manual correction with notes)
- Stock transfer between locations
- Low-stock report (products below reorder point)
- Full movement history per product/location

---

## 7. Procurement

### Purchase Orders

- Reference: `PO-YYYY-NNNNN` (auto-generated on save)
- Supplier (organization, optional)
- Status: Draft · Sent · Partially Received · Fully Received · Cancelled
- Expected delivery date, notes

**Line Items**
- Product (PROTECT - product cannot be deleted while PO line exists)
- Description, quantity ordered, unit cost
- Quantity received (updated on goods-in)
- Calculated: quantity outstanding, line total

**Properties**
- `total_cost` - sum of all line totals
- `is_editable` - true for Draft and Sent
- `can_receive` - true for Sent, Partial, Draft

### Features
- Create, edit, send, receive (partial or full), cancel POs
- Goods receipt creates stock movements in inventory
- Outstanding quantity tracking per line
- Print view

---

## 8. Assets & Service

### Assets

Long-lived customer-installed equipment with full lifecycle tracking.

**Data**
- Organization (customer), contact person
- Linked product, parent asset (for options/add-ons)
- Source sales order line
- Display name (defaults to product name)
- Serial number, asset tag
- Dates: purchase, installation, warranty end, expected EOL
- Status: Pending Install · In Service · Under Repair · Warranty · EOL Near · Retired · Disposed
- Location note, notes
- Soft delete

**Asset Components**
- Non-standalone options installed on an asset
- Name, SKU, price at installation
- Installation date, linked order line and product option

**Transfer History**
- Append-only record of every organization change
- From org → to org, transferred by user, timestamp

### Service Events (Timeline)

Every significant action recorded on the asset timeline:

| Event Type | Use Case |
|---|---|
| Installation | Initial deployment |
| Repair | Break-fix work order |
| Inspection | Annual check / audit |
| Recall / Safety Service | Linked to a recall campaign |
| Calibration | Measurement equipment |
| Warranty Claim | RMA submission |
| Advisory / Upsell | Recommendation note |
| General Note | Free-text entry |

Each event captures: title, description, date, vendor, external reference, cost, and optional related product (spare part SKU).

### Recall Campaigns

- Reference: `REC-YYYY-NNNNN`
- Title, description, remedy/action required
- Product filter (typical product family affected)
- Announced date, active flag

**Asset Recall Links**
- Ties specific assets to a campaign
- Status per asset: Pending · Action Required · In Progress · Completed · Not Affected · Exempt
- Completed date, notes

### Maintenance Plans (MJOP)

Multi-year service and replacement roadmaps per customer.

- Reference: `MJOP-YYYY-NNNNN`
- Organization, name, valid from/until
- Status: Draft · Active · Archived

**Plan Lines**
- Plan year (e.g., 2027)
- Title, description, sort order
- Related asset (specific unit being serviced)
- Recommended product (spare, bundle, or replacement SKU)
- Promoted flag (highlights budget-significant items)
- Estimated cost note
- Line status: Planned · Scheduled · In Progress · Completed · Deferred · Cancelled

### Replacement Recommendations

Sales queue for proactive upsell/replacement opportunities.

- Asset + suggested product
- Rationale text
- Priority: Low · Medium · High
- Status: Open · Accepted · Dismissed · Superseded
- Created by user

---

## 9. Pricing Rules

Dynamic pricing engine for calculating sell prices from product costs.

### Pricing Methods

| Method | How It Works |
|---|---|
| Cost + markup % | `list = cost × (1 + value/100)` |
| Gross margin % | `list = cost / (1 - value/100)` |
| MSRP - discount % | `list = msrp × (1 - value/100)` |
| List price - discount % | `list = list × (1 - value/100)` |
| Fixed multiplier | `list = list × value` |

### Rounding Options
None · Nearest cent · 10c · 50c · 1.00 · 5 · 10 · Custom increment

### Rule Assignments
- Assign a rule to a **product** (specific SKU) or a **category**
- Category assignments optionally cascade to subcategories
- Priority value resolves conflicts (lower number = higher priority)

### Features
- Rules can be active or inactive
- Product-level rules override category rules at the same priority
- Notes field for documenting intent

---

## 10. Contracts

Template-based service contracts with formula-driven cost calculation.

### Service Rates

Hourly or unit rates used as formula variables.

- Code (slug, unique), name, description
- Rate per hour, currency
- Active / inactive flag

### Contract Templates

Reusable blueprints for recurring contract types.

- Name, description
- **Formula** - Python-style arithmetic expression
  - Allowed: `+`, `-`, `*`, `/`, `()`
  - Built-in variables: `duration_years`, `duration_months`, `quote_total`, `order_total`, `asset_purchase_price`
  - Custom variables defined per template
- Result label (e.g., "Annual SLA cost (EUR)")
- Active flag

**Template Variables**

| Type | Behaviour |
|---|---|
| User input | Value entered per contract instance, with optional default |
| Service rate | Value pulled from the linked ServiceRate (rate_per_hour) |
| Constant | Fixed value embedded in the template |

Each variable has: name (Python identifier), label, unit (%, hours, EUR, etc.), sort order.

### Contracts

- Reference: `CTR-YYYY-NNNNN`
- Template, organization, status: Draft · Active · Expired · Terminated
- Start date, end date
- Optional links: quote, sales order, asset
- Tax rate for VAT on the computed result
- Notes

**Variable Values**
- One value record per template variable per contract
- User-input variables require a value entry; service rates and constants are resolved automatically

**Computed Result**
- Formula evaluated server-side with variable values substituted
- Result cached on `Contract` with computed-at timestamp
- Recalculated on save

**Features**
- Print view for customer-facing contract summary
- Duration properties (`duration_years`, `duration_months`) available in formulas
- Validation prevents reserved variable names and invalid formula syntax

---

## 11. Audit Log

Append-only event stream for all significant state changes.

**Every log entry records:**
- Actor (user, or null for system actions)
- Action string (e.g., `quote.accepted`, `cart.line_added`)
- Entity type and entity ID (the primary object affected)
- Metadata (JSON, flexible per action type)
- Timestamp

**Properties**
- Immutable - no updates or deletes
- Indexed on action, entity_type, entity_id, and created_at
- Ordered by most recent first

**Audit view** shows filterable event list for administrators.

---

## 12. Reports

### Sales Report
- Revenue by period with configurable date range
- Filter by organization
- Export to CSV

### Aged Debtors
- Outstanding invoices grouped by aging bucket (current, 30, 60, 90+ days)
- Per-organization breakdown
- Total balance due

### Inventory Valuation
- Stock on hand × purchase price per product
- Grouped by warehouse / location
- Export to CSV

---

## 13. Site Settings

Singleton configuration record:

- **Site currency** - code or symbol shown on all quotes, invoices, and documents (e.g., EUR, GBP, USD, €, £)

Currency is injected into every template context via a context processor. All historical documents show the currency that was active when they were created (snapshotted).

---

## 14. Search

Global full-text search across:
- Products (name, SKU, brand, description)
- Organizations (name, legal name)
- People (first name, last name)

Results grouped by type with links to detail pages.

---

## 15. Demo Mode

Activated by setting `DEMO_MODE=true` in the environment.

### Behaviour
- Persistent amber banner across the top of every page (cannot be dismissed)
- "Show logins" dropdown reveals all 6 demo role credentials
- Login page shows click-to-fill credential cards for all 6 roles
- Django Admin (`/admin/`) is blocked and redirects to dashboard
- User creation and deletion endpoints are blocked via middleware

### Demo Roles

| Email | Role | Access |
|---|---|---|
| `admin@demo.com` | Administrator | Full access - all modules, settings, reports |
| `catalog@demo.com` | Product Manager | Products, categories, pricing, purchase price view |
| `sales@demo.com` | Sales Manager | Quotes, orders, invoices, customers, cart |
| `accounts@demo.com` | Account Manager | CRM, contacts, contracts, view-only sales pipeline |
| `warehouse@demo.com` | Warehouse / Shipping | Inventory, fulfilment, shipping, purchase orders |
| `finance@demo.com` | Finance | Invoices, payments, credit notes, contracts, reports |

All demo accounts share the password `Demo1234!`.

### Auto-Reset
- `python manage.py reset_demo` command wipes all business data and reseeds
- Systemd timer (`nova-demo-reset.timer`) runs this every 30 minutes
- Users are recreated with known credentials on every reset
- All active sessions are cleared after reset (visitors must re-login)

### Demo Data (Meridian Group BV)
A fictional premium lifestyle and home goods wholesale distributor:

**Company structure**
- Meridian Group BV (holding, Amsterdam)
  - Meridian Living NL BV (NL subsidiary) + 5 departments, 5 staff each
  - Meridian Lifestyle DE GmbH (DE subsidiary) + 5 departments
  - Meridian Trade BE BV (BE subsidiary) + 5 departments
- 25 internal staff across 5 holding departments
- 7 external contacts at customer and supplier organizations

**Products** (13 SKUs)
- Insulated water bottles (500ml, 750ml)
- Ceramic canisters (300ml, 800ml)
- Stationery collections, notebooks, wooden brush sets, plant pots
- Desk gift sets, kitchen gift sets, wellness bundles, seasonal collection
- 3 products have real product photography; remaining have generated placeholders

**Pipeline data**
- 8 quotes (draft, sent, accepted, expired)
- 5 sales orders (draft, confirmed, fulfilled)
- 5 invoices (issued, partial payment, overdue)
- 3 purchase orders (received, partial)
- 2 warehouses, 7 locations, 18 stock entries
- 3 assets with recall campaign and maintenance plan
- 4 contracts across 2 templates
- 4 pricing rules

---

## 16. Architectural Patterns

### Snapshot Pattern
Quote, order, invoice, and fulfilment lines capture `product_name`, `sku`, `brand`, `unit_price`, `tax_rate_pct`, `currency`, and `line_total` at creation time. They never read live catalog data. Historical documents remain accurate after product edits or price changes.

### Soft Delete
Products, Organizations, People, and Assets set `is_archived = True` rather than being deleted. All list views filter these out by default. The records remain visible in historical documents and audit logs.

### Generic Contacts
`Address`, `Communication`, and `SocialProfile` attach to both `Person` and `Organization` via Django's `GenericForeignKey`. No duplication of contact detail models.

### Atomic Reference Numbers
`ReferenceSequence` uses `SELECT FOR UPDATE` to generate gapless, collision-free human-readable references (`Q-2026-00001`, `SO-2026-00001`, etc.) under concurrent load.

### Append-Only Records
`EventLog`, `StockMovement`, `InvoicePayment`, and `AssetOrganizationTransfer` are never updated or deleted. They form a permanent audit trail.

### Hierarchies
`Organization` and `ProductCategory` support unlimited parent-child depth. Utility methods generate breadcrumbs and ancestor lists. PROTECT foreign keys prevent accidental deletion of parents with children.

### Status State Machines
Quote, SalesOrder, Invoice, FulfillmentOrder, ShippingOrder, Shipment, Asset, Contract, and MaintenancePlan all have explicit `status` fields with defined valid transitions enforced in views and services.

### Service Layer
Complex multi-model operations (cart → quote, quote → order, order → invoice, fulfilment creation) live in `sales/services.py` as standalone transactional functions, not model methods. This keeps models thin and logic testable.

### Context Processors
Three values injected into every template context automatically:
- `cart_item_count` - number of lines in the current user's cart
- `SITE_CURRENCY` - configured currency code/symbol
- `DEMO_MODE` - boolean flag for demo-specific UI

### Decimal Precision
All financial fields use `max_digits=12, decimal_places=2` (defined as a module-level `MONEY` constant). Stock quantities use `decimal_places=3` for sub-unit precision.

---

## 17. Permission Reference

### Built-in Django Permissions
Every model automatically generates `view_`, `add_`, `change_`, `delete_` permissions.

### Custom Permissions

| Codename | Model | Purpose |
|---|---|---|
| `view_product_purchase_price` | Product | Can see purchase cost on catalog pages |
| `edit_product_pricing` | Product | Can edit list price, MSRP, currency, tax, discount group |
| `archive_product` | Product | Can archive and unarchive products |
| `archive_organization` | Organization | Can archive and unarchive organizations |
| `archive_person` | Person | Can archive and unarchive people |

### Demo Role Permission Sets

**Admin** - all permissions across: catalog, sales, relations, assets, contracts, inventory, procurement, core, accounts, audit, pricing

**Product Manager** - product/category CRUD, pricing rules, purchase price view, view-only on orders/invoices/stock/POs

**Sales Manager** - quote/order/invoice create+edit, cart, CRM view+edit, fulfilment view, shipping view, contracts view, stock view

**Account Manager** - full CRM (org + people), quote create+edit, view orders/invoices, assets view, contracts create+change

**Warehouse** - full inventory (stock, warehouses, locations, movements), fulfilment change, shipping + shipment create+change, PO create+change, org view

**Finance** - invoice+payment+credit note create+change, contracts create+change, view orders/quotes/stock/POs, tax rate view
