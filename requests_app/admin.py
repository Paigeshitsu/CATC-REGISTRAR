from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from .models import StudentMasterList, DocumentRequest, DocumentType, OTPToken, Profile, CollectionLog

# --- 1. ACTION DEFINITIONS ---

@admin.action(description='⚠️ Delete ALL students in Master List')
def wipe_entire_master_list(modeladmin, request, queryset):
    """Wipes the entire student master list table."""
    count = StudentMasterList.objects.all().count()
    StudentMasterList.objects.all().delete()
    modeladmin.message_user(request, f"Successfully wiped {count} records from the Master List.", messages.WARNING)

@admin.action(description='Registrar: Approve & Request Payment')
def registrar_approve(modeladmin, request, queryset):
    updated = queryset.filter(status='PENDING').update(status='PAYMENT_REQUIRED')
    modeladmin.message_user(request, f"Approved {updated} requests.", messages.SUCCESS)

@admin.action(description='Cashier: Mark as Paid & Assign Receipt')
def cashier_approve(modeladmin, request, queryset):
    from .models import SystemCounter, CollectionLog
    
    updated_count = 0
    for obj in queryset.filter(status='PAYMENT_REQUIRED'):
        new_no = SystemCounter.get_next_receipt_no()
        obj.status = 'PAID'
        obj.receipt_number = new_no
        obj.save()
        
        # Also create a financial log so Accounting sees it
        CollectionLog.objects.create(
            receipt_number=new_no,
            student_id=obj.student.username,
            student_name=obj.student.username,
            amount_paid=obj.document_type.price,
            documents_included=obj.document_type.name,
            collected_by=request.user
        )
        updated_count += 1
        
    modeladmin.message_user(request, f"Successfully processed {updated_count} payments with Receipt Numbers.", messages.SUCCESS)

# --- 2. ADMIN REGISTRATIONS ---

@admin.register(StudentMasterList)
class StudentMasterListAdmin(admin.ModelAdmin):
    list_display = ('student_id', 'full_name', 'course', 'email', 'phone_number')
    search_fields = ('student_id', 'full_name', 'email')
    ordering = ('student_id',)
    # This includes the mass delete script in the dropdown
    actions = [wipe_entire_master_list]

@admin.register(DocumentRequest)
class DocumentRequestAdmin(admin.ModelAdmin):
    list_display = ('student', 'document_type', 'status_colored', 'created_at')
    list_filter = ('status', 'document_type')
    actions = [registrar_approve, cashier_approve]

    @admin.display(description='Status')
    def status_colored(self, obj):
        colors = {
            'PENDING': '#6c757d', 
            'PAYMENT_REQUIRED': '#fd7e14',
            'PAID': '#0d6efd', 
            'COMPLETED': '#198754', 
            'REJECTED': '#dc3545',
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, 'black'),
            obj.get_status_display()
        )

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