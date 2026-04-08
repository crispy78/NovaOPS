from django.urls import path

from . import views

app_name = 'inventory'

urlpatterns = [
    path('', views.WarehouseListView.as_view(), name='warehouse_list'),
    path('<uuid:pk>/', views.WarehouseDetailView.as_view(), name='warehouse_detail'),
    path('adjust/', views.StockAdjustView.as_view(), name='stock_adjust'),
    path('low-stock/', views.LowStockListView.as_view(), name='low_stock'),
    path('transfer/', views.StockTransferView.as_view(), name='stock_transfer'),
]
