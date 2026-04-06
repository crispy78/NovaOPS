from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

User = get_user_model()

_INPUT = (
    'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm '
    'focus:border-nova-500 focus:outline-none focus:ring-1 focus:ring-nova-500'
)


class EmailLoginForm(AuthenticationForm):
    """Log in with email: the ``username`` field is labeled as email (value stored in ``username``)."""

    username = forms.CharField(
        label='Email address',
        widget=forms.EmailInput(attrs={'autocomplete': 'email', 'class': _INPUT, 'autofocus': True}),
    )
    password = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password', 'class': _INPUT}),
    )


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for _name, field in self.fields.items():
            field.widget.attrs.setdefault('class', _INPUT)
            if 'password' in _name.lower():
                field.widget.attrs.setdefault('autocomplete', 'new-password' if 'new' in _name else 'current-password')


class UserProfileForm(forms.ModelForm):
    """
    Profile fields for the default User model.
    Email is the sign-in identity: ``username`` is kept equal to ``email``.
    """

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name')
        labels = {
            'email': 'Email address',
            'first_name': 'First name',
            'last_name': 'Last name',
        }
        help_texts = {
            'email': 'Used to sign in. Must be unique.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        css = (
            'mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm '
            'focus:border-nova-500 focus:outline-none focus:ring-1 focus:ring-nova-500'
        )
        for _name, field in self.fields.items():
            field.widget.attrs.setdefault('class', css)
            if _name == 'email':
                field.widget.attrs.setdefault('type', 'email')
                field.widget.attrs.setdefault('autocomplete', 'email')

    def clean_email(self) -> str:
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if not email:
            raise forms.ValidationError('Enter a valid email address.')
        qs = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('This email address is already in use.')
        qs2 = User.objects.filter(username__iexact=email).exclude(pk=self.instance.pk)
        if qs2.exists():
            raise forms.ValidationError('This email address is already in use.')
        return email

    def save(self, commit: bool = True):  # type: ignore[override]
        user = super().save(commit=False)
        email = user.email.strip().lower()
        user.email = email
        user.username = email
        if commit:
            user.save()
        return user
