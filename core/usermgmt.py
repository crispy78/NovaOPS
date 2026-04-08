from __future__ import annotations

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Permission
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import DetailView, ListView

User = get_user_model()

# Permissions relevant to NovaOPS (curated list for the UI)
PERMISSION_GROUPS = {
    'Catalog': [
        'catalog.view_product',
        'catalog.add_product',
        'catalog.change_product',
        'catalog.view_product_purchase_price',
        'catalog.edit_product_pricing',
        'catalog.archive_product',
    ],
    'Pricing': [
        'pricing.view_pricingrule',
        'pricing.add_pricingrule',
        'pricing.change_pricingrule',
        'pricing.delete_pricingrule',
    ],
    'Sales': [
        'sales.view_quote',
        'sales.add_quote',
        'sales.change_quote',
        'sales.view_salesorder',
        'sales.add_salesorder',
        'sales.view_fulfillmentorder',
        'sales.view_shippingorder',
        'sales.view_invoice',
        'sales.add_invoice',
        'sales.view_creditnote',
        'sales.add_creditnote',
    ],
    'Inventory': [
        'inventory.view_warehouse',
        'inventory.view_stockentry',
        'inventory.change_stockentry',
        'inventory.view_stockmovement',
    ],
    'Procurement': [
        'procurement.view_purchaseorder',
        'procurement.add_purchaseorder',
        'procurement.change_purchaseorder',
    ],
    'Relations': [
        'relations.view_organization',
        'relations.add_organization',
        'relations.change_organization',
        'relations.archive_organization',
        'relations.view_person',
        'relations.add_person',
        'relations.change_person',
    ],
    'Assets': [
        'assets.view_asset',
        'assets.add_asset',
        'assets.change_asset',
        'assets.view_recallcampaign',
        'assets.add_recallcampaign',
        'assets.view_maintenanceplan',
        'assets.add_maintenanceplan',
        'assets.change_maintenanceplan',
    ],
    'Contracts': [
        'contracts.view_contract',
        'contracts.add_contract',
        'contracts.change_contract',
        'contracts.view_contracttemplate',
        'contracts.add_contracttemplate',
        'contracts.change_contracttemplate',
        'contracts.view_servicerate',
        'contracts.add_servicerate',
        'contracts.change_servicerate',
    ],
}


class StaffRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_staff:
            messages.error(request, 'Staff access required.')
            return redirect('dashboard')
        return super().dispatch(request, *args, **kwargs)


class UserListView(StaffRequiredMixin, ListView):
    model = User
    template_name = 'core/usermgmt/user_list.html'
    context_object_name = 'users'
    paginate_by = 30

    def get_queryset(self):
        qs = User.objects.order_by('last_name', 'first_name', 'username')
        q = (self.request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(
                Q(username__icontains=q) | Q(first_name__icontains=q) |
                Q(last_name__icontains=q) | Q(email__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = (self.request.GET.get('q') or '').strip()
        return ctx


class UserDetailView(StaffRequiredMixin, DetailView):
    model = User
    template_name = 'core/usermgmt/user_detail.html'
    context_object_name = 'target_user'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.object
        # Build permission matrix
        user_perms = set(
            user.user_permissions.values_list('content_type__app_label', 'codename')
        )
        # Also include group perms
        group_perms = set(
            Permission.objects
            .filter(group__user=user)
            .values_list('content_type__app_label', 'codename')
        )
        all_perms = {f'{app}.{code}' for app, code in user_perms | group_perms}

        permission_matrix = {}
        for group_name, perm_list in PERMISSION_GROUPS.items():
            permission_matrix[group_name] = [
                {'perm': p, 'label': p.split('.', 1)[1].replace('_', ' ').title(), 'has': p in all_perms}
                for p in perm_list
            ]
        ctx['permission_matrix'] = permission_matrix
        return ctx


class NewUserForm(forms.ModelForm):
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm password', widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'is_staff']

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Passwords do not match.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class UserCreateView(StaffRequiredMixin, View):
    template_name = 'core/usermgmt/user_form.html'

    def get(self, request):
        return render(request, self.template_name, {'form': NewUserForm()})

    def post(self, request):
        form = NewUserForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'User {user.username} created.')
            return redirect('core:user_detail', pk=user.pk)
        return render(request, self.template_name, {'form': form})


class UserPermissionsView(StaffRequiredMixin, View):
    """Grant or revoke individual permissions for a user."""

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        # Collect all known permissions
        all_perm_strings = [p for perms in PERMISSION_GROUPS.values() for p in perms]
        granted = set(request.POST.getlist('permissions'))

        perms_to_add = []
        perms_to_remove = []
        for perm_str in all_perm_strings:
            app_label, codename = perm_str.split('.', 1)
            try:
                perm_obj = Permission.objects.get(content_type__app_label=app_label, codename=codename)
            except Permission.DoesNotExist:
                continue
            if perm_str in granted:
                perms_to_add.append(perm_obj)
            else:
                perms_to_remove.append(perm_obj)

        user.user_permissions.add(*perms_to_add)
        user.user_permissions.remove(*perms_to_remove)
        messages.success(request, f'Permissions updated for {user.get_full_name() or user.username}.')
        return redirect('core:user_detail', pk=user.pk)
