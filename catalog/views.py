import csv

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Case, F, IntegerField, Value, When
from django.db.models import Prefetch, Q
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView, UpdateView

from audit.models import EventLog

from .forms import ProductForm, ProductImageUploadForm, ProductOptionForm
from .models import (
    Product,
    ProductBOMLine,
    ProductCategory,
    ProductImage,
    ProductOption,
    ProductRelation,
    ProductRelationType,
    ProductStatus,
    TaxRate,
)
from django.views.generic.edit import CreateView, DeleteView
from django.urls import reverse_lazy
from .permissions import get_product_page_permissions


class ProductListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'catalog.view_product'
    model = Product
    context_object_name = 'products'
    template_name = 'catalog/product_list.html'
    paginate_by = 24

    _SORT_OPTIONS = {
        'name': ('category__name', 'name'),
        'price_asc': (F('list_price').asc(nulls_last=True), 'name'),
        'price_desc': (F('list_price').desc(nulls_last=True), 'name'),
        'sku': ('sku',),
    }
    _DEFAULT_SORT = 'name'

    def get_queryset(self):
        qs = (
            Product.objects.select_related('category')
            .prefetch_related(
                Prefetch(
                    'images',
                    queryset=ProductImage.objects.order_by('-is_primary', 'sort_order', 'pk'),
                ),
            )
        )
        if not self.request.user.has_perm('catalog.change_product'):
            qs = qs.filter(is_archived=False)

        status = self.request.GET.get('status')
        if status == '__all__':
            pass
        elif status in ProductStatus.values:
            qs = qs.filter(status=status)
        else:
            qs = qs.exclude(status=ProductStatus.DRAFT)

        category_slug = self.request.GET.get('category')
        if category_slug:
            qs = qs.filter(category__slug=category_slug)

        q = (self.request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(sku__icontains=q)
                | Q(short_description__icontains=q)
                | Q(brand__icontains=q)
                | Q(mpn__icontains=q)
                | Q(ean_gtin__icontains=q),
            )

        sort_key = self.request.GET.get('sort') or self._DEFAULT_SORT
        if sort_key not in self._SORT_OPTIONS:
            sort_key = self._DEFAULT_SORT
        qs = qs.order_by(*self._SORT_OPTIONS[sort_key])
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['categories'] = ProductCategory.objects.order_by('name')
        ctx['status_choices'] = ProductStatus.choices
        ctx['current_category'] = self.request.GET.get('category') or ''
        ctx['current_status'] = self.request.GET.get('status') or ''
        ctx['search_query'] = (self.request.GET.get('q') or '').strip()
        sort_key = self.request.GET.get('sort') or self._DEFAULT_SORT
        ctx['current_sort'] = sort_key if sort_key in self._SORT_OPTIONS else self._DEFAULT_SORT
        ctx['product_page_permissions'] = get_product_page_permissions(self.request.user)
        return ctx


class ProductDetailView(LoginRequiredMixin, DetailView):
    """Public detail URL uses the product UUID (primary key), not guessable business codes like SKU."""

    model = Product
    context_object_name = 'product'
    template_name = 'catalog/product_detail.html'

    def get_queryset(self):
        return (
            Product.objects.select_related(
                'category',
                'tax_rate',
                'discount_group',
                'it_spec',
                'connectivity_spec',
                'scanner_spec',
                'printer_spec',
                'display_spec',
            )
            .prefetch_related(
                Prefetch(
                    'images',
                    queryset=ProductImage.objects.order_by('-is_primary', 'sort_order', 'pk'),
                ),
                'price_tiers',
                Prefetch(
                    'bundle_components',
                    queryset=ProductBOMLine.objects.select_related('component_product'),
                ),
                Prefetch(
                    'relations_from',
                    queryset=ProductRelation.objects.select_related('to_product').order_by(
                        'relation_type',
                        'sort_order',
                        'pk',
                    ),
                ),
                'documents',
                Prefetch(
                    'options',
                    queryset=ProductOption.objects.select_related('linked_product').order_by('sort_order', 'name'),
                ),
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        product = ctx['product']
        ctx['product_page_permissions'] = get_product_page_permissions(
            self.request.user,
            product,
        )
        for attr in (
            'it_spec',
            'connectivity_spec',
            'scanner_spec',
            'printer_spec',
            'display_spec',
        ):
            try:
                ctx[attr] = getattr(product, attr)
            except ObjectDoesNotExist:
                ctx[attr] = None

        if self.request.user.is_authenticated:
            from sales.forms import AddToCartForm, ReplacementPickForm

            ctx['add_to_cart_form'] = AddToCartForm()
            ctx['product_options'] = list(product.options.all())
            if self.request.user.has_perm('catalog.change_product'):
                existing = list(
                    product.relations_from.filter(relation_type=ProductRelationType.REPLACEMENT).values_list(
                        'to_product_id',
                        flat=True,
                    ),
                )
                ctx['replacement_form'] = ReplacementPickForm(
                    exclude_product_ids=[product.pk, *existing],
                )
                ctx['image_upload_form'] = ProductImageUploadForm()
                ctx['option_form'] = ProductOptionForm(parent_product=product)
        if self.request.user.has_perm('inventory.view_stockentry'):
            from decimal import Decimal
            from inventory.models import StockEntry
            entries = list(
                StockEntry.objects
                .filter(product=product, quantity_on_hand__gt=0)
                .select_related('location__warehouse')
                .order_by('location__warehouse__name', 'location__code')
            )
            ctx['stock_entries'] = entries
            ctx['stock_total'] = sum((e.quantity_on_hand for e in entries), Decimal('0'))

        ctx['replacement_links'] = (
            product.relations_from.filter(relation_type=ProductRelationType.REPLACEMENT)
            .select_related('to_product')
            .order_by('sort_order', 'pk')
        )
        _action_labels = {
            'product.updated': 'Updated',
            'product.image_uploaded': 'Image uploaded',
            'product.image_deleted': 'Image deleted',
            'product.replacement_assigned': 'Replacement assigned',
            'product.created': 'Created',
        }
        raw_events = EventLog.objects.filter(
            entity_type='Product',
            entity_id=product.id,
        ).order_by('-created_at')[:50]
        ctx['product_events'] = [
            {
                'ev': ev,
                'label': _action_labels.get(ev.action, ev.action.replace('.', ' › ').replace('_', ' ').title()),
            }
            for ev in raw_events
        ]
        return ctx


class ProductImageAddView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'catalog.change_product'

    def post(self, request, pk, *args, **kwargs):
        product = get_object_or_404(Product, pk=pk)
        form = ProductImageUploadForm(request.POST, request.FILES)
        if form.is_valid():
            im: ProductImage = form.save(commit=False)
            im.product = product
            im.save()
            if im.is_primary:
                ProductImage.objects.filter(product=product).exclude(pk=im.pk).update(is_primary=False)
            from audit.services import log_event

            log_event(
                action='product.image_uploaded',
                entity_type='Product',
                entity_id=product.id,
                request=request,
                metadata={
                    'sku': product.sku,
                    'product_image_id': str(im.id),
                },
            )
            messages.success(request, 'Image uploaded.')
        else:
            messages.error(request, 'Please choose a valid image file.')
        return redirect(product.get_absolute_url())


class ProductImageDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'catalog.delete_productimage'

    def post(self, request, pk, image_pk, *args, **kwargs):
        product = get_object_or_404(Product, pk=pk)
        im = get_object_or_404(ProductImage, pk=image_pk, product=product)
        from audit.services import log_event

        log_event(
            action='product.image_deleted',
            entity_type='Product',
            entity_id=product.id,
            request=request,
            metadata={
                'sku': product.sku,
                'product_image_id': str(im.id),
                'file': im.image.name,
            },
        )
        im.image.delete(save=False)
        im.delete()
        messages.success(request, 'Image deleted.')
        return redirect(product.get_absolute_url())


class ImageLibraryView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ProductImage
    template_name = 'catalog/image_library.html'
    context_object_name = 'images'
    paginate_by = 48
    permission_required = 'catalog.view_productimage'

    def get_queryset(self):
        qs = ProductImage.objects.select_related('product')
        q = (self.request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(Q(product__sku__icontains=q) | Q(product__name__icontains=q) | Q(alt_text__icontains=q))

        used = (self.request.GET.get('used') or '').strip().lower()
        if used in {'yes', 'true', '1'}:
            qs = qs.filter(product__isnull=False)
        elif used in {'no', 'false', '0'}:
            qs = qs.filter(product__isnull=True)

        sort = (self.request.GET.get('sort') or 'uploaded').strip().lower()
        direction = (self.request.GET.get('dir') or 'desc').strip().lower()
        desc = direction != 'asc'

        if sort == 'name':
            order = '-original_filename' if desc else 'original_filename'
            qs = qs.order_by(order, '-uploaded_at', 'pk')
        elif sort == 'size':
            order = '-file_size' if desc else 'file_size'
            qs = qs.order_by(order, '-uploaded_at', 'pk')
        elif sort == 'used':
            # used_first=1 when product is set; 0 otherwise
            qs = qs.annotate(
                used_first=Case(
                    When(product__isnull=False, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            )
            order = '-used_first' if desc else 'used_first'
            qs = qs.order_by(order, '-uploaded_at', 'pk')
        else:  # uploaded
            order = '-uploaded_at' if desc else 'uploaded_at'
            qs = qs.order_by(order, 'pk')

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['sort'] = (self.request.GET.get('sort') or 'uploaded').strip().lower()
        ctx['dir'] = (self.request.GET.get('dir') or 'desc').strip().lower()
        ctx['used'] = (self.request.GET.get('used') or '').strip().lower()
        return ctx


class ProductReplacementAddView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'catalog.change_product'

    def post(self, request, pk, *args, **kwargs):
        from sales.forms import ReplacementPickForm

        product = get_object_or_404(Product, pk=pk)
        existing = list(
            product.relations_from.filter(relation_type=ProductRelationType.REPLACEMENT).values_list(
                'to_product_id',
                flat=True,
            ),
        )
        form = ReplacementPickForm(
            request.POST,
            exclude_product_ids=[product.pk, *existing],
        )
        if form.is_valid():
            to_p = form.cleaned_data['replacement_product']
            ProductRelation.objects.update_or_create(
                from_product=product,
                to_product=to_p,
                relation_type=ProductRelationType.REPLACEMENT,
                defaults={'sort_order': 0},
            )
            from audit.services import log_event

            log_event(
                action='product.replacement_assigned',
                entity_type='Product',
                entity_id=product.id,
                request=request,
                metadata={
                    'sku': product.sku,
                    'replacement_sku': to_p.sku,
                    'replacement_id': str(to_p.id),
                },
            )
            messages.success(
                request,
                f'Replacement set to {to_p.name} ({to_p.sku}).',
            )
        else:
            messages.error(request, 'Choose a valid replacement product.')
        return redirect(product.get_absolute_url())


class ProductUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Edit product master data from the catalog UI (RBAC-ready via Django permissions)."""

    model = Product
    form_class = ProductForm
    template_name = 'catalog/product_form.html'
    permission_required = 'catalog.change_product'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_queryset(self):
        return Product.objects.select_related('category', 'tax_rate', 'discount_group')

    def form_valid(self, form):
        changed = list(form.changed_data)
        before = {k: getattr(self.object, k) for k in changed}
        response = super().form_valid(form)
        if changed:
            from audit.services import log_event

            after = {k: getattr(self.object, k) for k in changed}
            log_event(
                action='product.updated',
                entity_type='Product',
                entity_id=self.object.pk,
                request=self.request,
                metadata={
                    'sku': self.object.sku,
                    'fields': {
                        k: {'before': str(before[k]), 'after': str(after[k])} for k in changed
                    },
                },
            )
        messages.success(self.request, 'Product saved successfully.')
        return response

    def get_success_url(self):
        return self.object.get_absolute_url()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['product_page_permissions'] = get_product_page_permissions(
            self.request.user,
            self.object,
        )
        return ctx


class ProductCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Create a new product from the catalog UI."""

    model = Product
    form_class = ProductForm
    template_name = 'catalog/product_form.html'
    permission_required = 'catalog.add_product'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        from core.models import SiteSettings
        form.instance.currency = SiteSettings.get().currency
        response = super().form_valid(form)
        from audit.services import log_event
        log_event(
            action='product.created',
            entity_type='Product',
            entity_id=self.object.pk,
            request=self.request,
            metadata={'sku': self.object.sku, 'name': self.object.name},
        )
        messages.success(self.request, f'Product "{self.object.name}" created.')
        return response

    def get_success_url(self):
        return self.object.get_absolute_url()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_create'] = True
        return ctx


class ProductOptionAddView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Add a single option to a product from the product detail page."""

    permission_required = 'catalog.change_product'

    def post(self, request, pk, *args, **kwargs):
        product = get_object_or_404(Product, pk=pk)
        form = ProductOptionForm(request.POST, parent_product=product)
        if form.is_valid():
            opt = form.save(commit=False)
            opt.parent_product = product
            opt.save()
            messages.success(request, f'Option "{opt.display_name}" added.')
        else:
            for field_errors in form.errors.values():
                for err in field_errors:
                    messages.error(request, err)
        return redirect(product.get_absolute_url() + '#options')


class ProductOptionDeleteView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Delete a product option from the product detail page."""

    permission_required = 'catalog.change_product'

    def post(self, request, pk, option_pk, *args, **kwargs):
        product = get_object_or_404(Product, pk=pk)
        option = get_object_or_404(ProductOption, pk=option_pk, parent_product=product)
        name = option.display_name
        option.delete()
        messages.success(request, f'Option "{name}" removed.')
        return redirect(product.get_absolute_url() + '#options')


class ProductCsvExportView(LoginRequiredMixin, View):
    """Download the full (non-archived) product catalog as CSV."""

    def get(self, request, *args, **kwargs):
        qs = (
            Product.objects.filter(is_archived=False)
            .select_related('category', 'tax_rate')
            .order_by('category__name', 'name')
        )

        def rows():
            header = ['SKU', 'Name', 'Category', 'Status', 'Brand', 'List price', 'Currency', 'Tax rate', 'EAN/GTIN', 'MPN']
            yield header
            for p in qs:
                yield [
                    p.sku,
                    p.name,
                    p.category.name if p.category_id else '',
                    p.get_status_display(),
                    p.brand,
                    str(p.list_price) if p.list_price is not None else '',
                    p.currency,
                    str(p.tax_rate.rate) if p.tax_rate_id else '',
                    p.ean_gtin,
                    p.mpn,
                ]

        def stream():
            import io
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            for row in rows():
                writer.writerow(row)
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate(0)

        response = StreamingHttpResponse(stream(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="products.csv"'
        return response


class ProductBulkArchiveView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Archive (or unarchive) multiple products at once via a checkbox form on the product list."""

    permission_required = 'catalog.archive_product'

    def post(self, request, *args, **kwargs):
        from django.utils import timezone
        action = request.POST.get('bulk_action')
        pks = request.POST.getlist('product_ids')
        if not pks:
            messages.warning(request, 'No products selected.')
            return redirect('catalog:index')
        if action not in ('archive', 'unarchive'):
            messages.error(request, 'Unknown action.')
            return redirect('catalog:index')
        qs = Product.objects.filter(pk__in=pks)
        if action == 'archive':
            count = qs.filter(is_archived=False).update(is_archived=True, archived_at=timezone.now())
            messages.success(request, f'{count} product(s) archived.')
        else:
            count = qs.filter(is_archived=True).update(is_archived=False, archived_at=None)
            messages.success(request, f'{count} product(s) unarchived.')
        return redirect('catalog:index')


# ── VAT / Tax Rate management ─────────────────────────────────────────────────

class TaxRateListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = TaxRate
    template_name = 'catalog/taxrate_list.html'
    context_object_name = 'tax_rates'
    permission_required = 'catalog.view_product'
    ordering = ['name']


class TaxRateCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = TaxRate
    template_name = 'catalog/taxrate_form.html'
    permission_required = 'catalog.add_product'
    fields = ['name', 'code', 'rate']
    success_url = reverse_lazy('catalog:taxrate_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_create'] = True
        return ctx

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        _css = (
            'mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm '
            'shadow-sm focus:border-nova-500 focus:outline-none focus:ring-1 focus:ring-nova-500'
        )
        for field in form.fields.values():
            field.widget.attrs.setdefault('class', _css)
        return form


class TaxRateUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = TaxRate
    template_name = 'catalog/taxrate_form.html'
    permission_required = 'catalog.change_product'
    fields = ['name', 'code', 'rate']
    success_url = reverse_lazy('catalog:taxrate_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['is_create'] = False
        return ctx

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        _css = (
            'mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm '
            'shadow-sm focus:border-nova-500 focus:outline-none focus:ring-1 focus:ring-nova-500'
        )
        for field in form.fields.values():
            field.widget.attrs.setdefault('class', _css)
        return form


class TaxRateDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = TaxRate
    template_name = 'catalog/taxrate_confirm_delete.html'
    permission_required = 'catalog.delete_product'
    success_url = reverse_lazy('catalog:taxrate_list')
