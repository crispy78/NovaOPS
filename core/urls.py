from django.urls import path

from . import audit_views, reports, search, site_settings_views, usermgmt

app_name = 'core'

urlpatterns = [
    path('settings/', site_settings_views.SiteSettingsView.as_view(), name='site_settings'),
    path('reports/sales/', reports.SalesReportView.as_view(), name='report_sales'),
    path('reports/sales/export.csv', reports.SalesReportCsvView.as_view(), name='report_sales_csv'),
    path('reports/aged-debtors/', reports.AgedDebtorsReportView.as_view(), name='report_aged_debtors'),
    path('reports/inventory/', reports.InventoryValuationReportView.as_view(), name='report_inventory'),
    path('reports/inventory/export.csv', reports.InventoryValuationCsvView.as_view(), name='report_inventory_csv'),
    path('search/', search.GlobalSearchView.as_view(), name='search'),
    path('users/', usermgmt.UserListView.as_view(), name='user_list'),
    path('users/new/', usermgmt.UserCreateView.as_view(), name='user_create'),
    path('users/<int:pk>/', usermgmt.UserDetailView.as_view(), name='user_detail'),
    path('users/<int:pk>/permissions/', usermgmt.UserPermissionsView.as_view(), name='user_permissions'),
    path('audit/', audit_views.AuditLogView.as_view(), name='audit_log'),
]
