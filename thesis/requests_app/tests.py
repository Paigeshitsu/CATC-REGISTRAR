from django.test import TestCase
from django.contrib.auth.models import User, Group
from .models import (
    StudentMasterList,
    DocumentType,
    DocumentRequest,
    OTPToken,
    StudentBalance,
    Notification,
    TORRequestHistory,
    SystemCounter,
)


class ModelTests(TestCase):
    def setUp(self):
        self.group_student = Group.objects.create(name="Student")
        self.group_registrar = Group.objects.create(name="Registrar")
        
        self.student_master = StudentMasterList.objects.create(
            student_id="S000001",
            full_name="Test Student",
            course="BSIT",
            email="test@example.com",
            phone_number="+639123456789",
            is_graduated=False,
        )
        
        self.user = User.objects.create_user(
            username="S000001",
            email="test@example.com",
        )
        self.user.groups.add(self.group_student)
        
        self.document_type = DocumentType.objects.create(
            name=" TOR",
            price=100.00,
        )
        
    def test_student_master_list_creation(self):
        self.assertEqual(self.student_master.student_id, "S000001")
        self.assertEqual(self.student_master.masked_email, "t****@example.com")
        self.assertEqual(self.student_master.masked_phone, "+6*******89")
        
    def test_document_request_price_calculation(self):
        doc_request = DocumentRequest.objects.create(
            student=self.user,
            document_type=self.document_type,
            reason="Test request",
            batch_id="TEST001",
        )
        
        self.assertEqual(doc_request.get_price(), 100.00)
        
    def test_document_request_rush_processing(self):
        doc_request = DocumentRequest.objects.create(
            student=self.user,
            document_type=self.document_type,
            reason="Test request",
            batch_id="TEST002",
            rush_processing=True,
        )
        
        self.assertEqual(doc_request.get_price(), 200.00)
        
    def test_system_counter_receipt_number(self):
        SystemCounter.objects.all().delete()
        
        receipt1 = SystemCounter.get_next_receipt_no()
        receipt2 = SystemCounter.get_next_receipt_no()
        
        self.assertEqual(len(receipt1), 7)
        self.assertEqual(int(receipt1), 1)
        self.assertEqual(int(receipt2), 2)
        
    def test_document_request_status_choices(self):
        doc_request = DocumentRequest.objects.create(
            student=self.user,
            document_type=self.document_type,
            reason="Test request",
            status="PENDING",
        )
        
        self.assertEqual(doc_request.status, "PENDING")
        
    def test_tor_history_creation(self):
        TORRequestHistory.objects.create(
            student=self.user,
            document_type="TOR",
            page_count=5,
            price=500.00,
            is_free=False,
        )
        
        history = TORRequestHistory.objects.first()
        self.assertEqual(history.student.username, "S000001")
        self.assertEqual(history.page_count, 5)


class ViewTests(TestCase):
    def setUp(self):
        self.group_student = Group.objects.create(name="Student")
        
        self.student_master = StudentMasterList.objects.create(
            student_id="S000001",
            full_name="Test Student",
            course="BSIT",
            email="test@example.com",
            phone_number="+639123456789",
            is_graduated=True,
        )
        
        self.user = User.objects.create_user(
            username="S000001",
            email="test@example.com",
        )
        self.user.groups.add(self.group_student)
        
        self.document_type = DocumentType.objects.create(
            name="TOR",
            price=100.00,
        )
        
    def test_student_dashboard_requires_login(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 302)
        
    def test_student_dashboard_with_authentication(self):
        self.client.force_login(self.user)
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        
    def test_login_view_get(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)


class WorkflowTests(TestCase):
    def setUp(self):
        self.group_student = Group.objects.create(name="Student")
        
        self.student_master = StudentMasterList.objects.create(
            student_id="S000001",
            full_name="Test Student",
            course="BSIT",
            email="test@example.com",
            phone_number="+639123456789",
            is_graduated=True,
        )
        
        self.user = User.objects.create_user(
            username="S000001",
            email="test@example.com",
        )
        self.user.groups.add(self.group_student)
        
    def test_document_request_workflow(self):
        doc_type = DocumentType.objects.create(name="Form 137", price=50.00)
        
        doc_request = DocumentRequest.objects.create(
            student=self.user,
            document_type=doc_type,
            reason="For employment",
            batch_id="BATCH001",
            status="PENDING",
        )
        
        self.assertEqual(doc_request.status, "PENDING")
        
        doc_request.status = "APPROVED"
        doc_request.save()
        
        doc_request.status = "PAID"
        doc_request.save()
        
        doc_request.status = "PROCESSING"
        doc_request.save()
        
        doc_request.status = "READY"
        doc_request.save()
        
        doc_request.status = "COMPLETED"
        doc_request.save()
        
        self.assertEqual(doc_request.status, "COMPLETED")