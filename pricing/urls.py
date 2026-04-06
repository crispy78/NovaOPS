from django.urls import path

from . import views

app_name = 'pricing'

urlpatterns = [
    path('',             views.PricingRuleListView.as_view(),   name='rule_list'),
    path('new/',         views.PricingRuleCreateView.as_view(), name='rule_create'),
    path('<uuid:pk>/',   views.PricingRuleDetailView.as_view(), name='rule_detail'),
    path('<uuid:pk>/edit/', views.PricingRuleUpdateView.as_view(), name='rule_update'),
]
