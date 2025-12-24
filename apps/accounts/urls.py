from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # 인증
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # 관리자 페이지
    path('admin/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/user/create/', views.user_create, name='user_create'),
    path('admin/user/<int:user_id>/edit/', views.user_edit, name='user_edit'),
    path('admin/user/<int:user_id>/delete/', views.user_delete, name='user_delete'),
    path('admin/user/<int:user_id>/toggle-active/', views.user_toggle_active, name='user_toggle_active'),
]
