from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.student_dashboard, name='student_dashboard'),
    path('registrar/', views.registrar_queue, name='registrar_queue'),
    path('cashier/', views.cashier_queue, name='cashier_queue'),
]