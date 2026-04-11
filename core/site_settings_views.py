from __future__ import annotations

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic.edit import FormView

from .models import SiteSettings

_INPUT = (
    'mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm '
    'shadow-sm focus:border-nova-500 focus:outline-none focus:ring-1 focus:ring-nova-500'
)


class SiteSettingsForm(forms.Form):
    currency = forms.CharField(
        max_length=10,
        label='Default currency',
        help_text=(
            'Enter any currency code or symbol — e.g. GBP, EUR, USD, £, €, $, ₿, USDT. '
            'This is shown on all quotes, invoices, and documents.'
        ),
        widget=forms.TextInput(attrs={'class': _INPUT, 'placeholder': 'e.g. GBP or £'}),
    )


class SiteSettingsView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    template_name = 'core/site_settings.html'
    form_class = SiteSettingsForm

    def test_func(self):
        return self.request.user.is_staff

    def get_initial(self):
        return {'currency': SiteSettings.get().currency}

    def form_valid(self, form):
        settings = SiteSettings.get()
        old = settings.currency
        settings.currency = form.cleaned_data['currency'].strip()
        settings.save()
        if old != settings.currency:
            messages.success(
                self.request,
                f'Currency changed from {old} to {settings.currency}.',
            )
        else:
            messages.info(self.request, 'No changes made.')
        return self.render_to_response(self.get_context_data(form=form))
