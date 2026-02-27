from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from .models import StudentMasterList, DocumentRequest, DocumentType, OTPToken, Profile, CollectionLog

@admin.action(description='⚠️ Delete ALL students in Master List')
def wipe_entire_master_list(modeladmin, request, queryset):
    count = StudentMasterList.objects.all().count()
    StudentMasterList.objects.all().delete()
    modeladmin.message_user(request, f"Successfully wiped {count} records.", messages.WARNING)

@admin.register(StudentMasterList)
class StudentMasterListAdmin(admin.ModelAdmin):
    list_display = ('student_id', 'full_name', 'course', 'email', 'phone_number')
    search_fields = ('student_id', 'full_name', 'email')
    actions = [wipe_entire_master_list]

@admin.register(DocumentRequest)
class DocumentRequestAdmin(admin.ModelAdmin):
    list_display = ('student', 'document_type', 'status_colored', 'created_at')
    list_filter = ('status', 'document_type')

    def status_colored(self, obj):
        colors = {'PENDING': '#6c757d', 'PAYMENT_REQUIRED': '#fd7e14', 'PAID': '#0d6efd', 'COMPLETED': '#198754', 'REJECTED': '#dc3545'}
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', colors.get(obj.status, 'black'), obj.get_status_display())

@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'price')

@admin.register(OTPToken)
class OTPTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'otp_code', 'created_at', 'is_verified')

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'must_change_password')

@admin.register(CollectionLog)
class CollectionLogAdmin(admin.ModelAdmin):
    list_display = ('receipt_number', 'student_id', 'amount_paid', 'created_at')
    readonly_fields = ('created_at',)