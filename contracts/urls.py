from django.urls import path

from . import views

app_name = 'contracts'

urlpatterns = [
    # Service rates
    path('rates/',              views.ServiceRateListView.as_view(),   name='rate_list'),
    path('rates/new/',          views.ServiceRateCreateView.as_view(), name='rate_create'),
    path('rates/<uuid:pk>/edit/', views.ServiceRateUpdateView.as_view(), name='rate_update'),

    # Contract templates
    path('templates/',                        views.ContractTemplateListView.as_view(),   name='template_list'),
    path('templates/new/',                    views.ContractTemplateCreateView.as_view(), name='template_create'),
    path('templates/<uuid:pk>/',              views.ContractTemplateDetailView.as_view(), name='template_detail'),
    path('templates/<uuid:pk>/edit/',         views.ContractTemplateUpdateView.as_view(), name='template_update'),

    # Contracts
    path('',                    views.ContractListView.as_view(),   name='contract_list'),
    path('new/',                views.ContractCreateView.as_view(), name='contract_create'),
    path('<uuid:pk>/',          views.ContractDetailView.as_view(), name='contract_detail'),
    path('<uuid:pk>/edit/',     views.ContractUpdateView.as_view(), name='contract_update'),
    path('<uuid:pk>/print/',    views.ContractPrintView.as_view(),  name='contract_print'),
]
