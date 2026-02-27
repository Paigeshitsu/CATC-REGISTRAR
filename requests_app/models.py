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

class OTPToken(models.Model):
    """Temporary storage for OTP codes"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def generate_code(self):
        self.otp_code = str(random.randint(100000, 999999))
        self.save()

    def is_valid(self):
        """Returns True if the OTP is unverified and less than 10 minutes old."""
        expiration_time = self.created_at + timedelta(minutes=10)
        return not self.is_verified and timezone.now() < expiration_time

class DocumentType(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.name} - ₱{self.price}"

class DocumentRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending Review'),
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