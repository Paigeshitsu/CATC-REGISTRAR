from django.test import TestCase
from unittest.mock import patch
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
        self.group_registrar = Group.objects.create(name="Registrar")
        
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
        self.registrar = User.objects.create_user(
            username="registrar1",
            email="registrar@example.com",
            password="testpass123",
        )
        self.registrar.groups.add(self.group_registrar)
        
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

    def test_unpaid_pickup_cannot_generate_receipt(self):
        unpaid_request = DocumentRequest.objects.create(
            student=self.user,
            document_type=self.document_type,
            reason="For records",
            batch_id="BATCH-UNPAID-PICKUP",
            status="READY",
            delivery_method="PICKUP",
            receipt_number=None,
        )

        self.client.force_login(self.user)
        response = self.client.get(f"/cashier/receipt/{unpaid_request.id}/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")

    def test_registrar_cannot_mark_lbc_ready_without_tracking_number(self):
        lbc_request = DocumentRequest.objects.create(
            student=self.user,
            document_type=self.document_type,
            reason="Ship via LBC",
            batch_id="BATCH-LBC-001",
            status="PAID",
            delivery_method="LBC",
        )

        self.client.force_login(self.registrar)
        response = self.client.post(
            "/registrar/inbox/",
            {"action": "mark_ready", "batch_id": lbc_request.batch_id, "tracking_number_input": ""},
            follow=True,
        )

        lbc_request.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(lbc_request.status, "PAID")
        self.assertIsNone(lbc_request.tracking_number)
        self.assertContains(response, "Enter the actual LBC tracking number")

    @patch("requests_app.views.LBCTracker")
    def test_registrar_registers_lbc_tracking_when_marked_ready(self, mock_tracker_class):
        lbc_request = DocumentRequest.objects.create(
            student=self.user,
            document_type=self.document_type,
            reason="Ship via LBC",
            batch_id="BATCH-LBC-002",
            status="PAID",
            delivery_method="LBC",
        )
        mock_tracker = mock_tracker_class.return_value
        mock_tracker.register_lbc_tracking.return_value = {"meta": {"code": 200}}

        self.client.force_login(self.registrar)
        response = self.client.post(
            "/registrar/inbox/",
            {
                "action": "mark_ready",
                "batch_id": lbc_request.batch_id,
                "tracking_number_input": "176012345678",
            },
        )

        lbc_request.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/registrar/inbox/")
        self.assertEqual(lbc_request.status, "PROCESSING")
        self.assertEqual(lbc_request.tracking_number, "LBC176012345678")
        mock_tracker.register_lbc_tracking.assert_called_once_with("LBC176012345678")

    @patch("requests_app.views._send_httpsms_sms")
    def test_login_httpsms_success(self, mock_httpsms):
        mock_httpsms.return_value = {
            "sent": True,
            "provider": "httpsms",
        }

        response = self.client.post(
            "/",
            {"student_id": "S000001", "otp_method": "httpsms"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/verify-otp/")
        self.assertTrue(self.client.session.get("otp_user_id"))
        mock_httpsms.assert_called_once()

    @patch("requests_app.views._send_httpsms_sms")
    def test_login_stays_on_page_when_httpsms_fails(self, mock_httpsms):
        mock_httpsms.return_value = {
            "sent": False,
            "provider": "httpsms",
            "error_code": "httpsms_quota_exceeded",
            "error_message": "HTTPSMS quota reached",
        }

        response = self.client.post(
            "/",
            {"student_id": "S000001", "otp_method": "httpsms"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "HTTPSMS quota has been reached")
        self.assertIsNone(self.client.session.get("otp_user_id"))
        mock_httpsms.assert_called_once()


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
