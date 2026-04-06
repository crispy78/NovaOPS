from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import ListView, UpdateView

from relations.list_filters import querystring_excluding_page

from .forms import UserProfileForm


class ActiveUserListView(LoginRequiredMixin, ListView):
    """Searchable directory of active application users (login accounts)."""

    template_name = 'accounts/user_list.html'
    context_object_name = 'directory_users'
    paginate_by = 30

    def get_queryset(self):
        User = get_user_model()
        qs = User.objects.filter(is_active=True).order_by('last_name', 'first_name', 'email')
        q = (self.request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(email__icontains=q)
                | Q(username__icontains=q),
            )
        staff = (self.request.GET.get('staff') or '').strip().lower()
        if staff in ('1', 'true', 'yes', 'on'):
            qs = qs.filter(is_staff=True)
        elif staff in ('0', 'no'):
            qs = qs.filter(is_staff=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        g = self.request.GET
        ctx['filter_q'] = (g.get('q') or '').strip()
        ctx['filter_staff'] = g.get('staff', '').strip().lower() in ('1', 'true', 'yes', 'on')
        ctx['filter_staff_non'] = g.get('staff', '').strip().lower() in ('0', 'no')
        ctx['filter_querystring'] = querystring_excluding_page(self.request)
        return ctx


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    """Edit name and email; email doubles as username (no public registration)."""

    form_class = UserProfileForm
    template_name = 'accounts/profile.html'
    success_url = reverse_lazy('accounts:profile')

    def get_object(self):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, 'Your profile was updated.')
        return super().form_valid(form)
