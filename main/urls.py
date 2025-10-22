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
    path('dashboard/venue/add/', views.venue_create_view, name='venue_create'),
    path('dashboard/venue/<int:venue_id>/manage/', views.venue_manage_view, name='venue_manage'),
    path('dashboard/coach/', views.coach_dashboard_view, name='coach_dashboard'),
    path('dashboard/admin/', views.admin_dashboard_view, name='admin_dashboard'),
    path('dashboard/venue/revenue/', views.venue_revenue_view, name='venue_revenue'),
    path('venue/delete/<int:venue_id>/', views.delete_venue_view, name='delete_venue'),
]