from django.urls import path

from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.WarehouseListView.as_view(), name='warehouse_list'),
    path('<uuid:pk>/', views.WarehouseDetailView.as_view(), name='warehouse_detail'),
]
