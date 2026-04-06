"""
URL configuration for NovaOPS project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
"""
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, reverse_lazy

from accounts.forms import EmailLoginForm, StyledPasswordChangeForm
from core.views import DashboardView, protected_media

urlpatterns = [
    path('admin/', admin.site.urls),
    path(
        'accounts/profile/',
        include('accounts.urls'),
    ),
    path(
        'accounts/login/',
        auth_views.LoginView.as_view(
            template_name='registration/login.html',
            authentication_form=EmailLoginForm,
        ),
        name='login',
    ),
    path(
        'accounts/logout/',
        auth_views.LogoutView.as_view(),
        name='logout',
    ),
    path(
        'accounts/password_change/done/',
        auth_views.PasswordChangeDoneView.as_view(
            template_name='registration/password_change_done.html',
        ),
        name='password_change_done',
    ),
    path(
        'accounts/password_change/',
        auth_views.PasswordChangeView.as_view(
            template_name='registration/password_change_form.html',
            form_class=StyledPasswordChangeForm,
            success_url=reverse_lazy('password_change_done'),
        ),
        name='password_change',
    ),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('relations/', include('relations.urls')),
    path('assets/', include('assets.urls')),
    path('', include('catalog.urls')),
    path('pricing/', include('pricing.urls')),
    path('sales/', include('sales.urls')),
    path('contracts/', include('contracts.urls')),
]

if settings.DEBUG:
    urlpatterns += [
        path('media/<path:path>', protected_media, name='protected_media'),
    ]
