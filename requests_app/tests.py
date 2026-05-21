import json
from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.contrib.auth.models import User, Group
from django.urls import reverse
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

    @patch("requests_app.views.LBCTracker")
    def test_save_lbc_shipping_auto_issues_lbc_tracking_number(self, tracker_cls):
        tracker_cls.return_value.register_lbc_tracking.return_value = {
            "meta": {"code": 200}
        }
        doc_request = DocumentRequest.objects.create(
            student=self.user,
            document_type=self.document_type,
            reason="Shipping",
            batch_id="BOOKLBC001",
            status="APPROVED",
            delivery_method="LBC",
        )

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("student_dashboard"),
            {
                "action": "save_lbc_shipping",
                "batch_id": "BOOKLBC001",
                "lbc_delivery_type": "door_to_door",
                "lbc_receiver": json.dumps(
                    {
                        "firstname": "Juan",
                        "lastname": "Dela Cruz",
                        "phone": "09171234567",
                        "province": "Albay",
                        "city": "Legazpi City",
                        "barangay": "Binanuahan West",
                        "floor": "2F",
                        "street": "Rizal Street",
                        "zip": "4500",
                    }
                ),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        doc_request.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(doc_request.status, "PAYMENT_REQUIRED")
        self.assertTrue(doc_request.tracking_number.startswith("LBC-"))
        tracker_cls.return_value.register_lbc_tracking.assert_called_once()

    @patch("requests_app.views.LBCTracker")
    def test_save_lbc_shipping_uses_only_lbc_items_in_mixed_batch(self, tracker_cls):
        tracker_cls.return_value.register_lbc_tracking.return_value = {
            "meta": {"code": 200}
        }
        pickup_type = DocumentType.objects.create(name="Diploma", price=150.00)
        DocumentRequest.objects.create(
            student=self.user,
            document_type=pickup_type,
            reason="Pickup item",
            batch_id="BOOKLBCMIX1",
            status="APPROVED",
            delivery_method="PICKUP",
        )
        lbc_request = DocumentRequest.objects.create(
            student=self.user,
            document_type=self.document_type,
            reason="Shipping",
            batch_id="BOOKLBCMIX1",
            status="APPROVED",
            delivery_method="LBC",
        )

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("student_dashboard"),
            {
                "action": "save_lbc_shipping",
                "batch_id": "BOOKLBCMIX1",
                "lbc_delivery_type": "door_to_door",
                "lbc_receiver": json.dumps(
                    {
                        "firstname": "Juan",
                        "lastname": "Dela Cruz",
                        "phone": "09171234567",
                        "province": "Albay",
                        "city": "Legazpi City",
                        "barangay": "Binanuahan West",
                        "floor": "2F",
                        "street": "Rizal Street",
                        "zip": "4500",
                    }
                ),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        lbc_request.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(lbc_request.status, "PAYMENT_REQUIRED")
        self.assertTrue(lbc_request.tracking_number.startswith("LBC-"))
        tracker_cls.return_value.register_lbc_tracking.assert_called_once()


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


class PaymentTrackingAssignmentTests(TestCase):
    def setUp(self):
        self.group_student = Group.objects.create(name="Student")

        StudentMasterList.objects.create(
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
            password="pw12345",
        )
        self.user.groups.add(self.group_student)

        self.document_type = DocumentType.objects.create(
            name="Transcript of Records", price=100.00
        )

    @patch("requests_app.views.LBCTracker")
    def test_payment_success_auto_issues_lbc_tracking_number(self, tracker_cls):
        tracker_cls.return_value.register_lbc_tracking.return_value = {
            "meta": {"code": 200}
        }
        doc_request = DocumentRequest.objects.create(
            student=self.user,
            document_type=self.document_type,
            reason="Shipping",
            batch_id="PAYLBC001",
            status="PAYMENT_REQUIRED",
            delivery_method="LBC",
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("payment_success"))

        doc_request.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(doc_request.status, "PENDING_CASHIER_APPROVAL")
        self.assertTrue(doc_request.tracking_number.startswith("LBC-"))
        tracker_cls.return_value.register_lbc_tracking.assert_called_once()

    def test_payment_success_assigns_pickup_reference_number(self):
        doc_request = DocumentRequest.objects.create(
            student=self.user,
            document_type=self.document_type,
            reason="Pickup",
            batch_id="PAYPICK001",
            status="PAYMENT_REQUIRED",
            delivery_method="PICKUP",
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("payment_success"))

        doc_request.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(doc_request.status, "PENDING_CASHIER_APPROVAL")
        self.assertTrue(doc_request.tracking_number.startswith("CATC-"))

    @patch("requests_app.views.requests.post")
    def test_scoped_pickup_payment_excludes_lbc_item_in_same_batch(self, post_mock):
        pickup_request = DocumentRequest.objects.create(
            student=self.user,
            document_type=self.document_type,
            reason="Pickup",
            batch_id="PAYMIX001",
            status="PAYMENT_REQUIRED",
            delivery_method="PICKUP",
        )
        lbc_type = DocumentType.objects.create(name="Diploma", price=150.00)
        lbc_request = DocumentRequest.objects.create(
            student=self.user,
            document_type=lbc_type,
            reason="Shipping",
            batch_id="PAYMIX001",
            status="PAYMENT_REQUIRED",
            delivery_method="LBC",
            shipping_fee=Decimal("140.00"),
            valuation_fee=Decimal("10.00"),
            declared_value=Decimal("150.00"),
            lbc_total_fee=Decimal("150.00"),
        )

        post_mock.return_value = Mock(
            status_code=201,
            json=Mock(
                return_value={
                    "id": "inv_pickup_only",
                    "invoice_url": "https://example.com/invoice/pickup",
                }
            ),
        )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("pay_with_xendit_scoped", args=["PAYMIX001", "PICKUP"])
        )

        pickup_request.refresh_from_db()
        lbc_request.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://example.com/invoice/pickup")
        payload = json.loads(post_mock.call_args.kwargs["data"])
        self.assertEqual(payload["amount"], 100.0)
        self.assertEqual(pickup_request.payment_reference, "inv_pickup_only")
        self.assertIsNone(lbc_request.payment_reference)

    def test_payment_success_only_updates_matching_delivery_method_scope(self):
        pickup_request = DocumentRequest.objects.create(
            student=self.user,
            document_type=self.document_type,
            reason="Pickup",
            batch_id="PAYMIX002",
            status="PAYMENT_REQUIRED",
            delivery_method="PICKUP",
        )
        lbc_type = DocumentType.objects.create(name="Certificate", price=80.00)
        lbc_request = DocumentRequest.objects.create(
            student=self.user,
            document_type=lbc_type,
            reason="Shipping",
            batch_id="PAYMIX002",
            status="PAYMENT_REQUIRED",
            delivery_method="LBC",
        )

        self.client.force_login(self.user)
        session = self.client.session
        session["pending_xendit_invoice"] = {
            "invoice_id": "inv_pickup_only",
            "batch_id": "PAYMIX002",
            "delivery_method": "PICKUP",
        }
        session.save()

        response = self.client.get(reverse("payment_success"))

        pickup_request.refresh_from_db()
        lbc_request.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(pickup_request.status, "PENDING_CASHIER_APPROVAL")
        self.assertEqual(lbc_request.status, "PAYMENT_REQUIRED")

    def test_student_dashboard_does_not_render_tracking_button(self):
        DocumentRequest.objects.create(
            student=self.user,
            document_type=self.document_type,
            reason="Shipping",
            batch_id="PAYLBC002",
            status="IN_TRANSIT",
            delivery_method="LBC",
            tracking_number="LBC-TEST12345",
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("student_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Tracking: LBC-TEST12345")


class RegistrarTorRoutingTests(TestCase):
    def setUp(self):
        self.registrar_group = Group.objects.create(name="Registrar")
        self.student_group = Group.objects.create(name="Student")

        self.registrar = User.objects.create_user(
            username="registrar1",
            email="registrar@example.com",
            password="pw12345",
        )
        self.registrar.groups.add(self.registrar_group)

        StudentMasterList.objects.create(
            student_id="S000001",
            full_name="Test Student",
            course="BSIT",
            email="student@example.com",
            phone_number="+639123456789",
            is_graduated=True,
        )
        self.student = User.objects.create_user(
            username="S000001",
            email="student@example.com",
            password="pw12345",
        )
        self.student.groups.add(self.student_group)

        self.tor_type = DocumentType.objects.create(name="TOR", price=100.00)

    def test_send_to_tor_updates_batched_request_status(self):
        doc_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=self.tor_type,
            reason="For board exam",
            batch_id="BATCH123",
            status="PENDING",
        )

        self.client.force_login(self.registrar)
        response = self.client.post(
            reverse("registrar_dashboard"),
            {
                "action": "send_to_tor",
                "batch_id": "BATCH123",
                "request_id": doc_request.id,
            },
        )

        doc_request.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(doc_request.status, "PENDING_TOR_COUNT")

    def test_send_to_tor_updates_legacy_request_without_batch_id(self):
        doc_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=self.tor_type,
            reason="Legacy request",
            batch_id=None,
            status="PENDING",
        )

        self.client.force_login(self.registrar)
        response = self.client.post(
            reverse("registrar_dashboard"),
            {
                "action": "send_to_tor",
                "batch_id": "",
                "request_id": doc_request.id,
            },
        )

        doc_request.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(doc_request.status, "PENDING_TOR_COUNT")

    def test_sent_to_tor_request_is_removed_from_registrar_pending_list(self):
        doc_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=self.tor_type,
            reason="For evaluation",
            batch_id="BATCH456",
            status="PENDING",
        )

        self.client.force_login(self.registrar)
        self.client.post(
            reverse("registrar_dashboard"),
            {
                "action": "send_to_tor",
                "batch_id": "BATCH456",
                "request_id": doc_request.id,
            },
        )

        response = self.client.get(reverse("registrar_dashboard"))
        pending_requests = list(response.context["pending_requests"])

        doc_request.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(doc_request.status, "PENDING_TOR_COUNT")
        self.assertNotIn(doc_request, pending_requests)

    def test_processing_tor_batch_shows_mark_as_ready_button(self):
        doc_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=self.tor_type,
            reason="For release",
            batch_id="BATCH789",
            status="PROCESSING",
        )

        self.client.force_login(self.registrar)
        response = self.client.get(reverse("registrar_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="action" value="mark_ready"', html=False)
        self.assertContains(response, "BATCH789")

    def test_registrar_pending_mixed_batch_shows_send_to_tor_even_if_first_item_is_not_tor(self):
        diploma_type = DocumentType.objects.create(name="Diploma", price=150.00)
        DocumentRequest.objects.create(
            student=self.student,
            document_type=diploma_type,
            reason="Employment",
            batch_id="BATCHMIX1",
            status="PENDING",
        )
        DocumentRequest.objects.create(
            student=self.student,
            document_type=DocumentType.objects.create(
                name="Transcript of Records", price=100.00
            ),
            reason="Employment",
            batch_id="BATCHMIX1",
            status="PENDING",
        )

        self.client.force_login(self.registrar)
        response = self.client.get(reverse("registrar_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="action" value="send_to_tor"', html=False)
        self.assertContains(response, 'name="action" value="approve"', html=False)

    def test_approve_does_not_move_transcript_request_out_of_tor_flow(self):
        transcript_type = DocumentType.objects.create(
            name="Transcript of Records", price=100.00
        )
        transcript_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=transcript_type,
            reason="Employment",
            batch_id="BATCHTR1",
            status="PENDING",
        )

        self.client.force_login(self.registrar)
        response = self.client.post(
            reverse("registrar_dashboard"),
            {
                "action": "approve",
                "batch_id": "BATCHTR1",
                "request_id": transcript_request.id,
            },
        )

        transcript_request.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(transcript_request.status, "PENDING")


class TorPageCountPaymentRoutingTests(TestCase):
    def setUp(self):
        self.student_group = Group.objects.create(name="Student")
        StudentMasterList.objects.create(
            student_id="S000001",
            full_name="Test Student",
            course="BSIT",
            email="student@example.com",
            phone_number="+639123456789",
            is_graduated=False,
        )
        self.student = User.objects.create_user(
            username="S000001",
            email="student@example.com",
            password="pw12345",
        )
        self.student.groups.add(self.student_group)

        self.tor_desk = User.objects.create_user(
            username="Lotivio01",
            email="tor@example.com",
            password="pw12345",
            is_staff=True,
        )

        self.tor_type = DocumentType.objects.create(name="Transcript of Records", price=100.00)
        self.auth_type = DocumentType.objects.create(
            name="Authentication - Transcript of Records", price=50.00
        )

    def test_submit_tor_page_count_marks_whole_pickup_batch_as_payment_required(self):
        tor_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=self.tor_type,
            reason="Employment",
            batch_id="TOR001",
            status="PENDING_TOR_COUNT",
            delivery_method="PICKUP",
        )
        auth_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=self.auth_type,
            reason="Employment",
            batch_id="TOR001",
            status="PENDING_TOR_COUNT",
            delivery_method="PICKUP",
        )

        self.client.force_login(self.tor_desk)
        response = self.client.post(
            reverse("submit_tor_page_count"),
            {"request_id": tor_request.id, "page_count": 3},
        )

        tor_request.refresh_from_db()
        auth_request.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tor_request.status, "PAYMENT_REQUIRED")
        self.assertEqual(auth_request.status, "PAYMENT_REQUIRED")

    def test_submit_tor_page_count_only_updates_matching_delivery_scope_in_mixed_batch(self):
        tor_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=self.tor_type,
            reason="Employment",
            batch_id="TORMIX001",
            status="PENDING_TOR_COUNT",
            delivery_method="LBC",
        )
        pickup_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=DocumentType.objects.create(name="Diploma", price=150.00),
            reason="Employment",
            batch_id="TORMIX001",
            status="APPROVED",
            delivery_method="PICKUP",
        )

        self.client.force_login(self.tor_desk)
        response = self.client.post(
            reverse("submit_tor_page_count"),
            {"request_id": tor_request.id, "page_count": 3},
        )

        tor_request.refresh_from_db()
        pickup_request.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tor_request.status, "PAYMENT_REQUIRED")
        self.assertEqual(pickup_request.status, "APPROVED")

    def test_student_dashboard_shows_pay_for_approved_pickup_batches(self):
        DocumentRequest.objects.create(
            student=self.student,
            document_type=self.tor_type,
            reason="Employment",
            batch_id="TOR002",
            status="APPROVED",
            delivery_method="PICKUP",
        )

        self.client.force_login(self.student)
        response = self.client.get(reverse("student_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PAY")

    def test_student_dashboard_shows_pay_for_approved_lbc_batches_without_shipping_fee(self):
        DocumentRequest.objects.create(
            student=self.student,
            document_type=self.tor_type,
            reason="Employment",
            batch_id="TOR003",
            status="APPROVED",
            delivery_method="LBC",
        )

        self.client.force_login(self.student)
        response = self.client.get(reverse("student_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PAY")

    def test_student_dashboard_separates_mixed_delivery_batch_actions(self):
        DocumentRequest.objects.create(
            student=self.student,
            document_type=self.tor_type,
            reason="Employment",
            batch_id="MIX001",
            status="APPROVED",
            delivery_method="LBC",
            shipping_fee=Decimal("140.00"),
            valuation_fee=Decimal("15.00"),
            declared_value=Decimal("100.00"),
            lbc_total_fee=Decimal("155.00"),
        )
        DocumentRequest.objects.create(
            student=self.student,
            document_type=DocumentType.objects.create(name="Diploma", price=150.00),
            reason="Employment",
            batch_id="MIX001",
            status="APPROVED",
            delivery_method="PICKUP",
        )

        self.client.force_login(self.student)
        response = self.client.get(reverse("student_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LBC")
        self.assertContains(response, "PICKUP")
        self.assertContains(response, "Batch Total")
        self.assertContains(response, "405.00")


@override_settings(
    TRACKINGMORE_TRACKING_PAGE_URL="https://kyoukoisbigsad8t.trackingmore.org/?page=tracking-page"
)
class TrackingMoreIntegrationTests(TestCase):
    def setUp(self):
        self.student_group = Group.objects.create(name="Student")
        StudentMasterList.objects.create(
            student_id="S000001",
            full_name="Test Student",
            course="BSIT",
            email="student@example.com",
            phone_number="+639123456789",
            is_graduated=False,
        )
        self.student = User.objects.create_user(
            username="S000001",
            email="student@example.com",
            password="pw12345",
        )
        self.student.groups.add(self.student_group)
        self.doc_type = DocumentType.objects.create(
            name="Transcript of Records", price=100.00
        )

    def test_trackingmore_webhook_updates_lbc_request_status(self):
        doc_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=self.doc_type,
            reason="Shipping",
            batch_id="LBC001",
            status="AWAITING_COURIER_PICKUP",
            delivery_method="LBC",
            tracking_number="LBC123456789",
        )

        response = self.client.post(
            reverse("trackingmore_webhook"),
            data=json.dumps(
                {
                    "data": {
                        "tracking_number": "LBC123456789",
                        "delivery_status": "delivered",
                        "substatus": "delivered",
                        "latest_event": "Delivered to recipient",
                        "update_at": "2026-04-19T10:00:00+08:00",
                    }
                }
            ),
            content_type="application/json",
        )

        doc_request.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(doc_request.status, "DELIVERED")

    def test_student_dashboard_track_button_uses_system_tracking_page(self):
        DocumentRequest.objects.create(
            student=self.student,
            document_type=self.doc_type,
            reason="Shipping",
            batch_id="LBC002",
            status="IN_TRANSIT",
            delivery_method="LBC",
            tracking_number="LBC987654321",
        )

        self.client.force_login(self.student)
        response = self.client.get(reverse("student_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["trackingmore_tracking_page_url"],
            reverse("system_tracking_page"),
        )

    def test_receipt_includes_tracking_number_and_hosted_tracking_link(self):
        doc_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=self.doc_type,
            reason="Shipping",
            batch_id="LBC003",
            status="PAID",
            delivery_method="LBC",
            tracking_number="LBC555444333",
            receipt_number="0000001",
        )

        self.client.force_login(self.student)
        response = self.client.get(reverse("generate_receipt", args=[doc_request.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LBC555444333")
        self.assertContains(response, "tracking_number=LBC555444333")
        self.assertContains(response, "courier_code=lbcexpress")

    def test_lbc_receipt_shows_tracking_number_above_the_summary(self):
        doc_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=self.doc_type,
            reason="Shipping",
            batch_id="BOOKSHIP001",
            status="PAID",
            delivery_method="LBC",
            tracking_number="LBC555444333",
            receipt_number="0000002",
        )

        self.client.force_login(self.student)
        response = self.client.get(reverse("generate_receipt", args=[doc_request.id]))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Receipt No:", body)
        self.assertIn("Tracking ID:", body)
        self.assertLess(body.index("Receipt No:"), body.index("Tracking ID:"))
        self.assertNotContains(response, "LBC Tracking ID")
        self.assertNotContains(response, "Pending courier assignment")

    @patch("requests_app.views.LBCTracker")
    def test_lbc_receipt_auto_generates_tracking_number_when_missing(self, tracker_cls):
        tracker_cls.return_value.register_lbc_tracking.return_value = {
            "meta": {"code": 200}
        }
        doc_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=self.doc_type,
            reason="Shipping",
            batch_id="BOOKSHIP002",
            status="PAID",
            delivery_method="LBC",
            receipt_number="0000003",
        )

        self.client.force_login(self.student)
        response = self.client.get(reverse("generate_receipt", args=[doc_request.id]))

        doc_request.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(doc_request.tracking_number.startswith("LBC-"))
        self.assertContains(response, doc_request.tracking_number)
        self.assertNotContains(response, "Pending courier assignment")


class CourierDashboardTests(TestCase):
    def setUp(self):
        self.courier_group = Group.objects.create(name="Courier")
        self.registrar_group = Group.objects.create(name="Registrar")
        self.student_group = Group.objects.create(name="Student")

        self.courier = User.objects.create_user(
            username="courier1",
            email="courier@example.com",
            password="pw12345",
        )
        self.courier.groups.add(self.courier_group)

        self.registrar = User.objects.create_user(
            username="registrar1",
            email="registrar@example.com",
            password="pw12345",
            is_staff=True,
        )
        self.registrar.groups.add(self.registrar_group)

        StudentMasterList.objects.create(
            student_id="S000001",
            full_name="Test Student",
            course="BSIT",
            email="student@example.com",
            phone_number="+639123456789",
            is_graduated=False,
        )
        self.student = User.objects.create_user(
            username="S000001",
            email="student@example.com",
            password="pw12345",
        )
        self.student.groups.add(self.student_group)

        self.doc_type = DocumentType.objects.create(
            name="Transcript of Records", price=100.00
        )

    def test_courier_dashboard_marks_batch_as_picked_up(self):
        doc_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=self.doc_type,
            reason="Shipping",
            batch_id="COURIER001",
            status="AWAITING_COURIER_PICKUP",
            delivery_method="LBC",
        )

        self.client.force_login(self.courier)
        response = self.client.post(
            reverse("courier_dashboard"),
            {
                "action": "mark_picked_up",
                "batch_id": "COURIER001",
                "pickup_option": "RIDER_PICKUP",
            },
        )

        doc_request.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(doc_request.status, "PICKED_UP_AWAITING_DELIVERY")
        self.assertEqual(doc_request.courier_pickup_option, "RIDER_PICKUP")
        self.assertTrue(doc_request.tracking_number.startswith("LBC-"))
        self.assertTrue(
            Notification.objects.filter(
                user=self.student,
                sender_role="Courier",
                message__icontains="awaiting delivery",
            ).exists()
        )

    def test_courier_dashboard_generates_tracking_number_when_marked_picked_up(self):
        doc_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=self.doc_type,
            reason="Shipping",
            batch_id="COURIER001A",
            status="AWAITING_COURIER_PICKUP",
            delivery_method="LBC",
        )

        self.client.force_login(self.courier)
        response = self.client.post(
            reverse("courier_dashboard"),
            {
                "action": "mark_picked_up",
                "batch_id": "COURIER001A",
                "pickup_option": "RIDER_PICKUP",
            },
        )

        doc_request.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(doc_request.status, "PICKED_UP_AWAITING_DELIVERY")
        self.assertTrue(doc_request.tracking_number.startswith("LBC-"))

    def test_student_dashboard_shows_picked_up_awaiting_delivery_status(self):
        DocumentRequest.objects.create(
            student=self.student,
            document_type=self.doc_type,
            reason="Shipping",
            batch_id="COURIER002",
            status="PICKED_UP_AWAITING_DELIVERY",
            delivery_method="LBC",
            tracking_number="LBC333444555",
            courier_pickup_option="BRANCH_DROPOFF",
        )

        self.client.force_login(self.student)
        response = self.client.get(reverse("student_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PICKED UP - AWAITING DELIVERY")

    def test_staff_user_can_open_courier_dashboard_without_courier_group(self):
        self.client.force_login(self.registrar)
        response = self.client.get(reverse("courier_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Courier Dashboard")

    def test_anonymous_user_can_open_courier_dashboard(self):
        response = self.client.get(reverse("courier_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Courier Dashboard")

    def test_courier_dashboard_marks_batch_as_in_delivery(self):
        doc_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=self.doc_type,
            reason="Shipping",
            batch_id="COURIER003",
            status="PICKED_UP_AWAITING_DELIVERY",
            delivery_method="LBC",
            tracking_number="LBC999000111",
            courier_pickup_option="RIDER_PICKUP",
        )

        self.client.force_login(self.courier)
        response = self.client.post(
            reverse("courier_dashboard"),
            {
                "action": "mark_in_delivery",
                "batch_id": "COURIER003",
            },
        )

        doc_request.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(doc_request.status, "IN_TRANSIT")
        self.assertTrue(
            Notification.objects.filter(
                user=self.student,
                sender_role="Courier",
                message__icontains="now in delivery",
            ).exists()
        )

    def test_courier_dashboard_marks_batch_as_delivered(self):
        doc_request = DocumentRequest.objects.create(
            student=self.student,
            document_type=self.doc_type,
            reason="Shipping",
            batch_id="COURIER004",
            status="IN_TRANSIT",
            delivery_method="LBC",
            tracking_number="LBC999000112",
            courier_pickup_option="RIDER_PICKUP",
        )

        self.client.force_login(self.courier)
        response = self.client.post(
            reverse("courier_dashboard"),
            {
                "action": "mark_delivered",
                "batch_id": "COURIER004",
            },
        )

        doc_request.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(doc_request.status, "DELIVERED")
        self.assertTrue(
            Notification.objects.filter(
                user=self.student,
                sender_role="Courier",
                message__icontains="marked as delivered",
            ).exists()
        )
