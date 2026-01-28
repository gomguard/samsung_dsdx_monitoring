from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # 인증
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # 관리자 페이지 - 회원관리
    path('admin/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/user/create/', views.user_create, name='user_create'),
    path('admin/user/<int:user_id>/edit/', views.user_edit, name='user_edit'),
    path('admin/user/<int:user_id>/delete/', views.user_delete, name='user_delete'),
    path('admin/user/<int:user_id>/toggle-active/', views.user_toggle_active, name='user_toggle_active'),

    # 관리자 페이지 - 수집항목 관리
    path('admin/retail-columns/', views.retail_columns, name='retail_columns'),
    path('admin/retail-columns/create/', views.retail_columns_create, name='retail_columns_create'),
    path('admin/retail-columns/<int:column_id>/update/', views.retail_columns_update, name='retail_columns_update'),
    path('admin/retail-columns/<int:column_id>/delete/', views.retail_columns_delete, name='retail_columns_delete'),
    path('admin/retail-columns/<int:column_id>/toggle/', views.retail_columns_toggle, name='retail_columns_toggle'),

    # 관리자 페이지 - 예외조건 관리
    path('admin/exclude-rules/', views.exclude_rules, name='exclude_rules'),
    path('admin/exclude-rules/create/', views.exclude_rules_create, name='exclude_rules_create'),
    path('admin/exclude-rules/<int:rule_id>/update/', views.exclude_rules_update, name='exclude_rules_update'),
    path('admin/exclude-rules/<int:rule_id>/delete/', views.exclude_rules_delete, name='exclude_rules_delete'),
    path('admin/exclude-rules/<int:rule_id>/toggle/', views.exclude_rules_toggle, name='exclude_rules_toggle'),

    # 관리자 페이지 - DS 스케줄 설정
    path('admin/schedule-settings/', views.schedule_settings, name='schedule_settings'),
    path('admin/schedule-settings/create/', views.schedule_settings_create, name='schedule_settings_create'),
    path('admin/schedule-settings/<int:target_id>/update/', views.schedule_settings_update, name='schedule_settings_update'),
    path('admin/schedule-settings/<int:target_id>/delete/', views.schedule_settings_delete, name='schedule_settings_delete'),
    path('admin/schedule-settings/<int:target_id>/toggle/', views.schedule_settings_toggle, name='schedule_settings_toggle'),

    # 관리자 페이지 - DX 수집 스케줄 설정
    path('admin/dx-schedule-settings/', views.dx_schedule_settings, name='dx_schedule_settings'),
    path('admin/dx-schedule-settings/create/', views.dx_schedule_settings_create, name='dx_schedule_settings_create'),
    path('admin/dx-schedule-settings/<int:schedule_id>/update/', views.dx_schedule_settings_update, name='dx_schedule_settings_update'),
    path('admin/dx-schedule-settings/<int:schedule_id>/delete/', views.dx_schedule_settings_delete, name='dx_schedule_settings_delete'),
    path('admin/dx-schedule-settings/<int:schedule_id>/toggle/', views.dx_schedule_settings_toggle, name='dx_schedule_settings_toggle'),
]
