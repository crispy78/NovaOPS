from django.urls import path

from . import views

app_name = 'procurement'

urlpatterns = [
    path('', views.POListView.as_view(), name='po_list'),
    path('new/', views.POCreateView.as_view(), name='po_create'),
    path('<uuid:pk>/', views.PODetailView.as_view(), name='po_detail'),
    path('<uuid:pk>/edit/', views.POUpdateView.as_view(), name='po_edit'),
    path('<uuid:pk>/receive/', views.POReceiveView.as_view(), name='po_receive'),
]
