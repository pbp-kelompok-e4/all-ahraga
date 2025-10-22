from django.urls import path
from . import views

urlpatterns = [
    path('', views.main_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('venue/<int:venue_id>/', views.venue_detail_view, name='venue_detail'),
    path('dashboard/customer/', views.customer_dashboard_view, name='customer_dashboard'),
    path('dashboard/venue/', views.venue_dashboard_view, name='venue_dashboard'),
    path('dashboard/coach/', views.coach_dashboard_view, name='coach_dashboard'),
    path('dashboard/admin/', views.admin_dashboard_view, name='admin_dashboard'),
    path('venue/<int:venue_id>/book/', views.create_booking, name='create_booking'),
    path('customer/payment/<int:booking_id>/', views.customer_payment, name='customer_payment'),
]