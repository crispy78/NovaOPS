from django.urls import path

from . import views

app_name = 'catalog'

urlpatterns = [
    path('', views.ProductListView.as_view(), name='index'),
    path('images/', views.ImageLibraryView.as_view(), name='image_library'),
    path('products/<uuid:pk>/', views.ProductDetailView.as_view(), name='product_detail'),
    path('products/<uuid:pk>/edit/', views.ProductUpdateView.as_view(), name='product_edit'),
    path('products/<uuid:pk>/images/add/', views.ProductImageAddView.as_view(), name='product_image_add'),
    path(
        'products/<uuid:pk>/images/<uuid:image_pk>/delete/',
        views.ProductImageDeleteView.as_view(),
        name='product_image_delete',
    ),
    path(
        'products/<uuid:pk>/replacement/add/',
        views.ProductReplacementAddView.as_view(),
        name='product_replacement_add',
    ),
]
