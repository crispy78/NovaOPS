from __future__ import annotations

import uuid

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from audit.services import log_event
from catalog.models import Product
from relations.list_filters import organization_descendant_ids, querystring_excluding_page
from relations.models import Organization, Person

from .forms import (
    AssetEventForm,
    AssetForm,
    AssetRecallLinkForm,
    MaintenancePlanForm,
    MaintenancePlanLineForm,
    RecallCampaignForm,
    RecallLinkStatusForm,
    ReplacementRecommendationForm,
)
from .models import (
    Asset,
    AssetEvent,
    AssetOrganizationTransfer,
    AssetRecallLink,
    AssetReplacementRecommendation,
    AssetStatus,
    MaintenancePlan,
    MaintenancePlanLine,
    RecallCampaign,
    next_mjop_reference,
    next_recall_reference,
)


def _org_tree(orgs) -> list[tuple]:
    """Return (org, depth) in parent-first tree order for a flat list of org objects."""
    by_parent: dict = {}
    for o in orgs:
        by_parent.setdefault(o.parent_id, []).append(o)

    result: list[tuple] = []

    def _walk(parent_id, depth):
        for o in sorted(by_parent.get(parent_id, []), key=lambda x: x.name):
            result.append((o, depth))
            _walk(o.id, depth + 1)

    _walk(None, 0)
    return result


class AssetListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'assets.view_asset'
    model = Asset
    template_name = 'assets/asset_list.html'
    context_object_name = 'assets'
    paginate_by = 25

    def get_queryset(self):
        qs = (
            Asset.objects.filter(is_archived=False)
            .select_related('organization__parent', 'product', 'person')
            .order_by('organization__name', 'product__name', 'serial_number')
        )
        g = self.request.GET

        org_id = (g.get('org') or '').strip()
        if org_id:
            try:
                root = uuid.UUID(str(org_id))
            except ValueError:
                org_id = ''
            else:
                if g.get('include_children'):
                    qs = qs.filter(organization_id__in=organization_descendant_ids(root))
                else:
                    qs = qs.filter(organization_id=root)

        person_id = (g.get('person') or '').strip()
        if person_id:
            try:
                uuid.UUID(str(person_id))
            except ValueError:
                pass
            else:
                qs = qs.filter(person_id=person_id)

        product_id = g.get('product') or ''
        if product_id:
            qs = qs.filter(product_id=product_id)

        status = g.get('status') or ''
        if status:
            qs = qs.filter(status=status)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        g = self.request.GET

        all_orgs = list(
            Organization.objects.filter(is_archived=False)
            .select_related('parent')
            .only('id', 'name', 'parent_id', 'unit_kind')
            .order_by('name')
        )
        ctx['org_tree'] = _org_tree(all_orgs)
        ctx['filter_organizations'] = Organization.objects.filter(is_archived=False).order_by('name')

        ctx['products'] = (
            Product.objects.filter(is_archived=False, customer_assets__is_archived=False)
            .distinct()
            .order_by('name')
        )

        ctx['status_choices'] = AssetStatus.choices
        ctx['filter_org'] = (g.get('org') or '').strip()
        ctx['filter_include_children'] = bool(g.get('include_children'))
        ctx['filter_person'] = (g.get('person') or '').strip()
        ctx['filter_product'] = g.get('product') or ''
        ctx['filter_status'] = g.get('status') or ''
        ctx['filter_people'] = Person.objects.filter(is_archived=False).order_by('last_name', 'first_name')
        ctx['filter_querystring'] = querystring_excluding_page(self.request)

        if ctx['filter_org']:
            try:
                ctx['filter_org_name'] = Organization.objects.get(pk=ctx['filter_org']).name
            except (Organization.DoesNotExist, ValueError):
                ctx['filter_org_name'] = ''
        return ctx


class AssetCreateView(LoginRequiredMixin, CreateView):
    model = Asset
    form_class = AssetForm
    template_name = 'assets/asset_form.html'

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        resp = super().form_valid(form)
        AssetOrganizationTransfer.objects.create(
            asset=self.object,
            from_organization=None,
            to_organization=self.object.organization,
            transferred_by=self.request.user,
            note='',
        )
        log_event(
            action='asset.created',
            entity_type='Asset',
            entity_id=self.object.id,
            request=self.request,
            metadata={'organization_id': str(self.object.organization_id)},
        )
        messages.success(self.request, f'Asset registered: {self.object.display_name()}.')
        return resp


class AssetUpdateView(LoginRequiredMixin, UpdateView):
    model = Asset
    form_class = AssetForm
    template_name = 'assets/asset_form.html'
    context_object_name = 'asset'

    def get_queryset(self):
        return Asset.objects.filter(is_archived=False)

    def form_valid(self, form):
        prev_org_id = self.get_object().organization_id
        resp = super().form_valid(form)
        if prev_org_id != self.object.organization_id:
            AssetOrganizationTransfer.objects.create(
                asset=self.object,
                from_organization_id=prev_org_id,
                to_organization=self.object.organization,
                transferred_by=self.request.user,
                note='',
            )
            log_event(
                action='asset.organization_transferred',
                entity_type='Asset',
                entity_id=self.object.id,
                request=self.request,
                metadata={
                    'from_organization_id': str(prev_org_id),
                    'to_organization_id': str(self.object.organization_id),
                },
            )
        log_event(
            action='asset.updated',
            entity_type='Asset',
            entity_id=self.object.id,
            request=self.request,
            metadata={},
        )
        messages.success(self.request, 'Asset updated.')
        return resp


class AssetDetailView(LoginRequiredMixin, DetailView):
    model = Asset
    template_name = 'assets/asset_detail.html'
    context_object_name = 'asset'

    def get_queryset(self):
        return (
            Asset.objects.filter(is_archived=False)
            .select_related('organization', 'person', 'product', 'order_line__order', 'created_by')
            .prefetch_related(
                'events__created_by',
                'events__related_product',
                'recall_links__recall_campaign',
                'replacement_recommendations__suggested_product',
                'organization_transfers__from_organization',
                'organization_transfers__to_organization',
                'organization_transfers__transferred_by',
            )
        )


class AssetEventCreateView(LoginRequiredMixin, CreateView):
    model = AssetEvent
    form_class = AssetEventForm
    template_name = 'assets/asset_event_form.html'

    def dispatch(self, request, asset_pk, *args, **kwargs):
        self.asset = get_object_or_404(Asset.objects.filter(is_archived=False), pk=asset_pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.asset = self.asset
        form.instance.created_by = self.request.user
        resp = super().form_valid(form)
        log_event(
            action='asset_event.created',
            entity_type='AssetEvent',
            entity_id=self.object.id,
            request=self.request,
            metadata={'asset_id': str(self.asset.id), 'type': self.object.event_type},
        )
        messages.success(self.request, 'Event recorded.')
        return resp

    def get_success_url(self) -> str:
        return self.asset.get_absolute_url()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['asset'] = self.asset
        return ctx


class ReplacementRecommendationCreateView(LoginRequiredMixin, CreateView):
    model = AssetReplacementRecommendation
    form_class = ReplacementRecommendationForm
    template_name = 'assets/recommendation_form.html'

    def dispatch(self, request, asset_pk, *args, **kwargs):
        self.asset = get_object_or_404(Asset.objects.filter(is_archived=False), pk=asset_pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.asset = self.asset
        form.instance.created_by = self.request.user
        resp = super().form_valid(form)
        log_event(
            action='asset_recommendation.created',
            entity_type='AssetReplacementRecommendation',
            entity_id=self.object.id,
            request=self.request,
            metadata={'asset_id': str(self.asset.id)},
        )
        messages.success(self.request, 'Replacement recommendation added.')
        return resp

    def get_success_url(self) -> str:
        return self.asset.get_absolute_url()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['asset'] = self.asset
        return ctx


class RecallLinkUpdateView(LoginRequiredMixin, UpdateView):
    """Update the status (and optional completion date) of an asset recall link."""

    model = AssetRecallLink
    form_class = RecallLinkStatusForm
    template_name = 'assets/recall_link_update.html'

    def get_object(self, queryset=None):
        return get_object_or_404(
            AssetRecallLink.objects.select_related('asset', 'recall_campaign'),
            pk=self.kwargs['pk'],
        )

    def form_valid(self, form):
        link = form.save()
        log_event(
            action='asset_recall_link.updated',
            entity_type='AssetRecallLink',
            entity_id=link.id,
            request=self.request,
            metadata={
                'asset_id': str(link.asset_id),
                'recall_reference': link.recall_campaign.reference,
                'new_status': link.status,
                'completed_on': str(link.completed_on) if link.completed_on else None,
            },
        )
        messages.success(self.request, 'Recall status updated.')
        return redirect(link.asset.get_absolute_url())

    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return redirect(self.get_object().asset.get_absolute_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['link'] = self.object
        return ctx


class RecallCampaignListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'assets.view_recallcampaign'
    model = RecallCampaign
    template_name = 'assets/recall_list.html'
    context_object_name = 'recalls'
    paginate_by = 25

    def get_queryset(self):
        return RecallCampaign.objects.filter(is_archived=False).select_related('product', 'created_by').order_by(
            '-announced_date',
            '-created_at',
        )


class RecallCampaignCreateView(LoginRequiredMixin, CreateView):
    model = RecallCampaign
    form_class = RecallCampaignForm
    template_name = 'assets/recall_form.html'

    def form_valid(self, form):
        ref = next_recall_reference()
        while RecallCampaign.objects.filter(reference=ref).exists():
            ref = next_recall_reference()
        form.instance.reference = ref
        form.instance.created_by = self.request.user
        resp = super().form_valid(form)
        log_event(
            action='recall_campaign.created',
            entity_type='RecallCampaign',
            entity_id=self.object.id,
            request=self.request,
            metadata={'reference': self.object.reference},
        )
        messages.success(self.request, f'Recall campaign {self.object.reference} created.')
        return resp

    def get_success_url(self) -> str:
        return self.object.get_absolute_url()


class RecallCampaignUpdateView(LoginRequiredMixin, UpdateView):
    model = RecallCampaign
    form_class = RecallCampaignForm
    template_name = 'assets/recall_form.html'
    context_object_name = 'recall'

    def get_queryset(self):
        return RecallCampaign.objects.filter(is_archived=False)

    def form_valid(self, form):
        resp = super().form_valid(form)
        log_event(
            action='recall_campaign.updated',
            entity_type='RecallCampaign',
            entity_id=self.object.id,
            request=self.request,
            metadata={'reference': self.object.reference},
        )
        messages.success(self.request, f'Recall campaign {self.object.reference} updated.')
        return resp

    def get_success_url(self) -> str:
        return self.object.get_absolute_url()


class RecallCampaignDetailView(LoginRequiredMixin, DetailView):
    model = RecallCampaign
    template_name = 'assets/recall_detail.html'
    context_object_name = 'recall'

    def get_queryset(self):
        return RecallCampaign.objects.filter(is_archived=False).select_related('product').prefetch_related(
            'asset_links__asset__organization',
            'asset_links__asset__product',
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['link_form'] = AssetRecallLinkForm(campaign=self.object)
        return ctx

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = AssetRecallLinkForm(request.POST, campaign=self.object)
        if form.is_valid():
            link = form.save(commit=False)
            link.recall_campaign = self.object
            link.save()
            log_event(
                action='recall_campaign.asset_linked',
                entity_type='RecallCampaign',
                entity_id=self.object.id,
                request=request,
                metadata={'asset_id': str(link.asset_id)},
            )
            messages.success(request, 'Asset linked to this recall.')
            return redirect(self.object)
        ctx = self.get_context_data(object=self.object)
        ctx['link_form'] = form
        return self.render_to_response(ctx)


class MaintenancePlanListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'assets.view_maintenanceplan'
    model = MaintenancePlan
    template_name = 'assets/mjop_list.html'
    context_object_name = 'plans'
    paginate_by = 25

    def get_queryset(self):
        qs = (
            MaintenancePlan.objects.filter(is_archived=False)
            .select_related('organization', 'created_by')
            .order_by('-valid_from', '-created_at')
        )
        org = self.request.GET.get('organization')
        if org:
            qs = qs.filter(organization_id=org)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filter_organization_id'] = self.request.GET.get('organization') or ''
        return ctx


class MaintenancePlanCreateView(LoginRequiredMixin, CreateView):
    model = MaintenancePlan
    form_class = MaintenancePlanForm
    template_name = 'assets/mjop_form.html'

    def form_valid(self, form):
        ref = next_mjop_reference()
        while MaintenancePlan.objects.filter(reference=ref).exists():
            ref = next_mjop_reference()
        form.instance.reference = ref
        form.instance.created_by = self.request.user
        resp = super().form_valid(form)
        log_event(
            action='mjop.created',
            entity_type='MaintenancePlan',
            entity_id=self.object.id,
            request=self.request,
            metadata={'reference': self.object.reference},
        )
        messages.success(self.request, f'Maintenance plan {self.object.reference} created.')
        return resp

    def get_success_url(self) -> str:
        return self.object.get_absolute_url()


class MaintenancePlanUpdateView(LoginRequiredMixin, UpdateView):
    model = MaintenancePlan
    form_class = MaintenancePlanForm
    template_name = 'assets/mjop_form.html'
    context_object_name = 'plan'

    def get_queryset(self):
        return MaintenancePlan.objects.filter(is_archived=False)

    def form_valid(self, form):
        resp = super().form_valid(form)
        log_event(
            action='mjop.updated',
            entity_type='MaintenancePlan',
            entity_id=self.object.id,
            request=self.request,
            metadata={},
        )
        messages.success(self.request, 'Maintenance plan updated.')
        return resp

    def get_success_url(self) -> str:
        return self.object.get_absolute_url()


class MaintenancePlanDetailView(LoginRequiredMixin, DetailView):
    model = MaintenancePlan
    template_name = 'assets/mjop_detail.html'
    context_object_name = 'plan'

    def get_queryset(self):
        return MaintenancePlan.objects.filter(is_archived=False).select_related('organization').prefetch_related(
            'lines__related_asset',
            'lines__recommended_product',
        )


class MaintenancePlanLineCreateView(LoginRequiredMixin, CreateView):
    model = MaintenancePlanLine
    form_class = MaintenancePlanLineForm
    template_name = 'assets/mjop_line_form.html'

    def dispatch(self, request, plan_pk, *args, **kwargs):
        self.plan = get_object_or_404(MaintenancePlan.objects.filter(is_archived=False), pk=plan_pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.plan = self.plan
        resp = super().form_valid(form)
        log_event(
            action='mjop.line_created',
            entity_type='MaintenancePlan',
            entity_id=self.plan.id,
            request=self.request,
            metadata={'line_id': str(self.object.id)},
        )
        messages.success(self.request, 'Maintenance plan line added.')
        return resp

    def get_success_url(self) -> str:
        return self.plan.get_absolute_url()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['plan'] = self.plan
        return ctx
