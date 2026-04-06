from django.urls import path

from . import views

app_name = 'assets'

urlpatterns = [
    path('', views.AssetListView.as_view(), name='asset_list'),
    path('new/', views.AssetCreateView.as_view(), name='asset_create'),
    path('<uuid:pk>/', views.AssetDetailView.as_view(), name='asset_detail'),
    path('<uuid:pk>/edit/', views.AssetUpdateView.as_view(), name='asset_update'),
    path('<uuid:asset_pk>/events/new/', views.AssetEventCreateView.as_view(), name='asset_event_create'),
    path(
        '<uuid:asset_pk>/recommendations/new/',
        views.ReplacementRecommendationCreateView.as_view(),
        name='asset_recommendation_create',
    ),
    path('recall-links/<uuid:pk>/update/', views.RecallLinkUpdateView.as_view(), name='recall_link_update'),
    path('recalls/', views.RecallCampaignListView.as_view(), name='recall_list'),
    path('recalls/new/', views.RecallCampaignCreateView.as_view(), name='recall_create'),
    path('recalls/<uuid:pk>/edit/', views.RecallCampaignUpdateView.as_view(), name='recall_update'),
    path('recalls/<uuid:pk>/', views.RecallCampaignDetailView.as_view(), name='recall_detail'),
    path('mjop/', views.MaintenancePlanListView.as_view(), name='mjop_list'),
    path('mjop/new/', views.MaintenancePlanCreateView.as_view(), name='mjop_create'),
    path('mjop/<uuid:pk>/', views.MaintenancePlanDetailView.as_view(), name='mjop_detail'),
    path('mjop/<uuid:pk>/edit/', views.MaintenancePlanUpdateView.as_view(), name='mjop_update'),
    path(
        'mjop/<uuid:plan_pk>/lines/new/',
        views.MaintenancePlanLineCreateView.as_view(),
        name='mjop_line_create',
    ),
]
