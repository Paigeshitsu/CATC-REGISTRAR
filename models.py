from django.db import models
from django.contrib.auth.models import User

class DocumentType(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return self.name

class DocumentRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending Registrar Review'),
        ('PAYMENT_REQUIRED', 'Awaiting Payment'),
        ('VERIFYING_PAYMENT', 'Payment Under Review'),
        ('COMPLETED', 'Completed'),
        ('REJECTED', 'Rejected'),
    ]

    student = models.ForeignKey(User, on_delete=models.CASCADE)
    document_type = models.ForeignKey(DocumentType, on_delete=models.CASCADE)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    receipt_image = models.ImageField(upload_to='receipts/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.username} - {self.document_type}"