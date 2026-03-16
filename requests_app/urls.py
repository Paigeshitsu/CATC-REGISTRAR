from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('staff/login/', views.staff_login, name='staff_login'),
    path('logout/', views.logout_view, name='logout'),
    path('api/document-types/', views.get_document_types, name='get_document_types'),
    path('dashboard/', views.student_dashboard, name='student_dashboard'),
    path('registrar/inbox/', views.registrar_dashboard, name='registrar_dashboard'),
    
    path('cashier/terminal/', views.cashier_dashboard, name='cashier_dashboard'),
    path('cashier/receipt/<int:req_id>/', views.generate_receipt, name='generate_receipt'),
    
    path('accounting/manage/', views.accounting_dashboard, name='accounting_dashboard'),
    path('notifications/read/', views.mark_notifications_read, name='mark_notifications_read'),
    path('settings/signature/', views.signature_settings, name='signature_settings'),
    path('payment/xendit/<str:batch_id>/', views.pay_with_xendit, name='pay_with_xendit'),
    path('payment/success/', views.payment_success, name='payment_success'),
    path('login/', views.api_login_request),
    path('verify/', views.api_verify_otp),
    path('payment/webhook/', views.xendit_webhook, name='xendit_webhook'),
    path('accounting/export/csv/', views.export_collection_csv, name='export_collection_csv'),
]
