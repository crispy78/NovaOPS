from django.urls import path

from . import views

app_name = 'accounts'

urlpatterns = [
    path('', views.ProfileUpdateView.as_view(), name='profile'),
    path('directory/', views.ActiveUserListView.as_view(), name='user_directory'),
]
