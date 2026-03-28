from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.utils import timezone
from datetime import timedelta
import random
import uuid

# Validator for ID: Starts with S, then 6 digits (S000001 - S999999)
id_validator = RegexValidator(
    regex=r'^S\d{6}$',
    message="ID must start with 'S' followed by 6 digits (e.g., S000001)."
)

class StudentMasterList(models.Model):
    """The Mock Database: Pre-authorized students allowed to use the system."""
    student_id = models.CharField(max_length=7, unique=True, validators=[id_validator])
    full_name = models.CharField(max_length=255)
    course = models.CharField(max_length=100)
    major = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15)
    is_graduated = models.BooleanField(default=False, help_text="Whether the student has graduated")
    
    @property
    def masked_email(self):
        try:
            email_part, domain_part = self.email.split('@')
            return f"{email_part[0]}****@{domain_part}"
        except:
            return "your registered email"

    @property
    def masked_phone(self):
        try:
            return f"{self.phone_number[:2]}*******{self.phone_number[-2:]}"
        except:
            return "your registered phone"
    
    def get_tor_request_count(self):
        """Get the count of TOR requests for this student."""
        # Get the user associated with this student
        from django.contrib.auth.models import User
        user = User.objects.filter(username=self.student_id).first()
        if not user:
            return 0
        from .models import DocumentRequest, DocumentType
        # Count TOR requests (both completed and in-progress)
        tor_type = DocumentType.objects.filter(name__icontains='TOR').first()
        if not tor_type:
            return 0
        return DocumentRequest.objects.filter(
            student=user, 
            document_type=tor_type,
            is_deleted=False
        ).exclude(status='REJECTED').count()

class OTPToken(models.Model):
    """Temporary storage for OTP codes"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)
    # Google Authenticator (TOTP) secret key
    google_auth_secret = models.CharField(max_length=32, blank=True, null=True)
    # Track if user has set up Google Authenticator
    google_auth_enabled = models.BooleanField(default=False)

    def generate_code(self):
        # Generate a random 6-digit code as fallback
        self.otp_code = str(random.randint(100000, 999999))
        
        # Try to generate Google Authenticator secret if pyotp is available
        try:
            import pyotp
            if not self.google_auth_secret:
                self.google_auth_secret = pyotp.random_base32()
                # Enable Google Auth when secret is generated
                self.google_auth_enabled = True
        except ImportError:
            # If pyotp is not installed, just skip Google Auth setup
            pass
        
        self.save()

    def get_google_auth_uri(self):
        """Get the Google Authenticator provisioning URI"""
        if not self.google_auth_secret:
            return None
        try:
            import pyotp
            totp = pyotp.TOTP(self.google_auth_secret)
            return totp.provisioning_uri(name=self.user.username, issuer_name='CATC Portal')
        except ImportError:
            return None

    def verify_google_auth_code(self, code):
        """Verify a Google Authenticator TOTP code"""
        if not self.google_auth_secret or not self.google_auth_enabled:
            return False
        try:
            import pyotp
            totp = pyotp.TOTP(self.google_auth_secret)
            return totp.verify(code)
        except ImportError:
            return False

    def verify_otp_code(self, code):
        """Verify either Google Auth code or regular OTP code"""
        # First try Google Authenticator
        if self.google_auth_enabled and self.google_auth_secret:
            if self.verify_google_auth_code(code):
                return True
        # Fall back to regular OTP code
        return self.otp_code == code and self.is_valid()

class DocumentType(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.name} - ₱{self.price}"

class DocumentRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending Review'),
        ('PENDING_TOR_COUNT', 'Pending TOR Page Count'),
        ('APPROVED', 'Approved - Awaiting Payment'),
        ('REJECTED', 'Rejected'),
        ('PAYMENT_REQUIRED', 'Awaiting Payment'),
        ('PAID', 'Paid - To be Processed'),
        ('PROCESSING', 'Processing Document'),
        ('READY', 'Ready for Pickup / Shipping'),
        ('COMPLETED', 'Claimed/Finished'),
    ]

    DELIVERY_CHOICES = [
        ('PICKUP', 'In-person Pickup'),
        ('LBC', 'LBC Delivery'),
    ]
      
    LBC_TYPE_CHOICES = [
        ('RIDER', 'Rider Delivery (Home)'),
        ('BRANCH', 'Branch Pick Up'),
    ]

    lbc_type = models.CharField(max_length=10, choices=LBC_TYPE_CHOICES, default='RIDER', null=True, blank=True)
    lbc_branch_name = models.CharField(max_length=255, blank=True, null=True)
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='requests')
    document_type = models.ForeignKey(DocumentType, on_delete=models.CASCADE)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    batch_id = models.CharField(max_length=100, blank=True, null=True)
    delivery_method = models.CharField(max_length=10, choices=DELIVERY_CHOICES, default='PICKUP')
    is_deleted = models.BooleanField(default=False)
    
    receipt_number = models.CharField(max_length=10, blank=True, null=True)
    payment_reference = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    generated_content = models.TextField(null=True, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True, null=True)
    shipping_first_name = models.CharField(max_length=100, blank=True, null=True)
    shipping_last_name = models.CharField(max_length=100, blank=True, null=True)
    shipping_phone = models.CharField(max_length=15, blank=True, null=True)
    shipping_floor = models.CharField(max_length=100, blank=True, null=True)
    shipping_street = models.CharField(max_length=255, blank=True, null=True)
    shipping_province = models.CharField(max_length=100, blank=True, null=True)
    shipping_city = models.CharField(max_length=100, blank=True, null=True)
    shipping_barangay = models.CharField(max_length=100, blank=True, null=True)
    shipping_zip = models.CharField(max_length=10, blank=True, null=True)
    shipping_landmark = models.CharField(max_length=255, blank=True, null=True)
    
    # TOR-specific fields
    tor_page_count = models.PositiveIntegerField(null=True, blank=True, help_text="Number of pages for TOR (Transcript of Records)")
    tor_price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Custom price for TOR based on page count")
    
    # Rush processing field
    rush_processing = models.BooleanField(default=False, help_text="If true, processing is rushed (1 day) at double price")
    
    # Processing days field
    processing_days = models.PositiveIntegerField(null=True, blank=True, help_text="Number of days to process the document")
    
    # TOR price per page
    TOR_PRICE_PER_PAGE = 100
    
    def get_price(self):
        """Calculate the price for this document request, considering TOR special pricing and rush processing."""
        # Get base price
        base_price = self.tor_price_override if self.tor_price_override is not None else self.document_type.price
        
        # Apply rush processing multiplier (double the price)
        if self.rush_processing:
            base_price = base_price * 2
        
        return base_price
    
    def get_student_name(self):
        student_record = StudentMasterList.objects.filter(student_id=self.student.username).first()
        return student_record.full_name if student_record else self.student.username

    def __str__(self):
        return f"{self.student.username} - {self.document_type.name}"

class SystemCounter(models.Model):
    name = models.CharField(max_length=50, default="receipt")
    last_value = models.IntegerField(default=0)

    @classmethod
    def get_next_receipt_no(cls):
        from django.db import transaction
        with transaction.atomic():
            counter, _ = cls.objects.get_or_create(name="receipt")
            counter.last_value += 1
            counter.save()
            return f"{counter.last_value:07d}"

class StudentBalance(models.Model):
    student = models.OneToOneField(StudentMasterList, on_delete=models.CASCADE, related_name='balance_record')
    outstanding_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    last_notified = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.student.student_id} - ₱{self.outstanding_amount}"
    
    def clear_balance(self):
        """Clear the outstanding balance by setting it to 0."""
        self.outstanding_amount = 0
        self.save()

class Notification(models.Model):
    SENDER_CHOICES = [
        ('Registrar', 'Registrar Office'),
        ('Accounting', 'Accounting Office'),
        ('Cashier', 'Cashier Office'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    sender_role = models.CharField(max_length=20, choices=SENDER_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.sender_role} -> {self.user.username}: {self.message[:30]}"

class CollectionLog(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'Cash (Manual)'),
        ('ONLINE', 'Xendit (Online)'),
    ]
    receipt_number = models.CharField(max_length=20)
    student_name = models.CharField(max_length=255)
    student_id = models.CharField(max_length=20)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    documents_included = models.TextField()
    collected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES, default='CASH')

    def __str__(self):
        return f"Receipt {self.receipt_number} - {self.student_id}"

class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'Created'),
        ('UPDATE', 'Updated Status'),
        ('DELETE', 'Soft Deleted'),
        ('PRICE', 'Changed Pricing'),
        ('BALANCE', 'Notified Balance'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    resource_type = models.CharField(max_length=50)
    resource_id = models.CharField(max_length=50)
    details = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.action} at {self.timestamp}"

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    must_change_password = models.BooleanField(default=False)
    printed_name = models.CharField(max_length=255, blank=True)
    signature_data = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.user.username


class TORRequestHistory(models.Model):
    """
    Permanent TOR request history that cannot be deleted by students.
    This tracks all TOR requests regardless of whether the student
    deletes their request history in the dashboard.
    """
    student = models.ForeignKey(StudentMasterList, on_delete=models.CASCADE, related_name='tor_history')
    document_type = models.CharField(max_length=255)
    page_count = models.IntegerField(null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_free = models.BooleanField(default=False, help_text="Whether this was a free TOR request")
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    batch_id = models.CharField(max_length=50, null=True, blank=True)
    
    class Meta:
        ordering = ['-requested_at']
        verbose_name = "TOR Request History"
        verbose_name_plural = "TOR Request Histories"
    
    def __str__(self):
        return f"{self.student.student_id} - {self.document_type} - {'FREE' if self.is_free else 'PAID'}"