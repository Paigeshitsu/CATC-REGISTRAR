from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
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

    def __str__(self):
        return f"{self.student_id} - {self.full_name}"

class OTPToken(models.Model):
    """Temporary storage for OTP codes"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def generate_code(self):
        self.otp_code = str(random.randint(100000, 999999))
        self.save()

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

    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='requests')
    document_type = models.ForeignKey(DocumentType, on_delete=models.CASCADE)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    # ENSURE THESE TWO LINES EXIST:
    batch_id = models.CharField(max_length=100, blank=True, null=True)
    delivery_method = models.CharField(max_length=10, choices=DELIVERY_CHOICES, default='PICKUP')
    
    # Other necessary fields for the system
    receipt_number = models.CharField(max_length=10, blank=True, null=True)
    payment_reference = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    generated_content = models.TextField(null=True, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True, null=True)

    def get_student_name(self):
        from .models import StudentMasterList
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
    """Permanent financial record for the Accounting Department"""
    receipt_number = models.CharField(max_length=20)
    student_name = models.CharField(max_length=255)
    student_id = models.CharField(max_length=20)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    documents_included = models.TextField() # List of docs paid for
    collected_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Receipt {self.receipt_number} - {self.student_id}"

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    must_change_password = models.BooleanField(default=False)
    printed_name = models.CharField(max_length=255, blank=True)
    # Changed from signature_text to signature_data to store the drawing
    signature_data = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.user.username
