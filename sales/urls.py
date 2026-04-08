from django.urls import path

from . import views

app_name = 'sales'

urlpatterns = [
    path('cart/add/<uuid:product_pk>/', views.CartAddView.as_view(), name='cart_add'),
    path('cart/line/<uuid:line_pk>/update/', views.CartLineUpdateView.as_view(), name='cart_line_update'),
    path('cart/', views.CartView.as_view(), name='cart'),
    path('cart/quote/', views.QuoteCreateFromCartView.as_view(), name='cart_create_quote'),
    path('cart/order/', views.OrderCreateFromCartView.as_view(), name='cart_create_order'),
    path('quotes/', views.QuoteListView.as_view(), name='quote_list'),
    path('quotes/<uuid:pk>/', views.QuoteDetailView.as_view(), name='quote_detail'),
    path('quotes/<uuid:pk>/refresh-prices/', views.QuoteRefreshPricesView.as_view(), name='quote_refresh_prices'),
    path('quotes/<uuid:pk>/create-order/', views.QuoteCreateOrderView.as_view(), name='quote_create_order'),
    path('quotes/<uuid:pk>/accept/', views.QuoteAcceptView.as_view(), name='quote_accept'),
    path('orders/', views.SalesOrderListView.as_view(), name='order_list'),
    path('orders/<uuid:pk>/', views.SalesOrderDetailView.as_view(), name='order_detail'),
    path('orders/<uuid:pk>/status/', views.SalesOrderStatusUpdateView.as_view(), name='order_status_update'),
    path('orders/<uuid:pk>/create-invoice/', views.InvoiceCreateFromOrderView.as_view(), name='order_create_invoice'),
    path('orders/<uuid:pk>/create-fulfillment/', views.FulfillmentCreateFromOrderView.as_view(), name='order_create_fulfillment'),
    path('fulfillments/', views.FulfillmentOrderListView.as_view(), name='fulfillment_list'),
    path('fulfillments/<uuid:pk>/', views.FulfillmentOrderDetailView.as_view(), name='fulfillment_detail'),
    path('fulfillments/<uuid:pk>/complete/', views.FulfillmentOrderCompleteView.as_view(), name='fulfillment_complete'),
    path(
        'fulfillments/<uuid:fulfillment_pk>/shipping/new/',
        views.ShippingOrderCreateFromFulfillmentView.as_view(),
        name='fulfillment_create_shipping',
    ),
    path('shipping/', views.ShippingOrderListView.as_view(), name='shipping_list'),
    path('shipping/<uuid:pk>/', views.ShippingOrderDetailView.as_view(), name='shipping_detail'),
    path('invoices/export.csv', views.InvoiceCsvExportView.as_view(), name='invoice_csv_export'),
    path('invoices/', views.InvoiceListView.as_view(), name='invoice_list'),
    path('invoices/<uuid:pk>/', views.InvoiceDetailView.as_view(), name='invoice_detail'),
    path('invoices/<uuid:pk>/print/', views.InvoicePrintView.as_view(), name='invoice_print'),
    path('quotes/<uuid:pk>/print/', views.QuotePrintView.as_view(), name='quote_print'),
]
