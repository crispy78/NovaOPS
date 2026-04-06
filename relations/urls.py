from django.urls import path

from . import views

app_name = 'relations'

urlpatterns = [
    path('organizations/', views.OrganizationListView.as_view(), name='organization_list'),
    path('organizations/new/', views.OrganizationCreateView.as_view(), name='organization_create'),
    path('organizations/<uuid:pk>/', views.OrganizationDetailView.as_view(), name='organization_detail'),
    path('organizations/<uuid:pk>/edit/', views.OrganizationUpdateView.as_view(), name='organization_update'),
    path('people/', views.PersonListView.as_view(), name='person_list'),
    path('people/new/', views.PersonCreateView.as_view(), name='person_create'),
    path('people/<uuid:pk>/', views.PersonDetailView.as_view(), name='person_detail'),
    path('people/<uuid:pk>/edit/', views.PersonUpdateView.as_view(), name='person_update'),
]

