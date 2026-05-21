import uuid, time, requests, json, base64, csv, os, re
import logging
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal, ROUND_UP
from urllib.parse import urlencode
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout as django_logout
from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponse
from django.db.models import Sum, Q
from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken

import random

# Local Imports
from .serializers import RequestSerializer, DocumentTypeSerializer
from .tracking_service import LBCTracker
from .models import (
    DocumentRequest,
    StudentMasterList,
    OTPToken,
    DocumentType,
    StudentBalance,
    Notification,
    SystemCounter,
    CollectionLog,
    Profile,
    AuditLog,
    TORRequestHistory,
)
from .forms import StudentRequestForm, StudentIDLoginForm, OTPVerifyForm
from .decorators import role_required

# --- 1. HELPERS ---

logger = logging.getLogger(__name__)
GENERATED_LBC_TRACKING_RE = re.compile(r"^LBC-[A-F0-9]{10}$")


def log_audit(user, action, resource, resource_id, details):
    AuditLog.objects.create(
        user=user,
        action=action,
        resource_type=resource,
        resource_id=str(resource_id),
        details=details,
    )


def is_authentication_document(document_request):
    return "Authentication" in str(document_request.document_type.name)


def get_base_document_name(document_name):
    if document_name.startswith("Authentication - "):
        return document_name.replace("Authentication - ", "", 1)
    return document_name


def build_summary_item(item):
    is_auth = is_authentication_document(item)

    if is_auth:
        base_name = get_base_document_name(item.document_type.name)
        doc_display = f"Authentication - {base_name}"
        base_amount = item.get_base_price()
        total_amount = item.get_base_price()
    else:
        doc_display = item.document_type.name
        base_amount = item.get_base_price()
        total_amount = base_amount * 2 if (item.rush_processing) else base_amount

    return {
        "name": doc_display,
        "base_amount": base_amount,
        "total_amount": total_amount,
        "is_authentication": is_auth,
        "is_rush": item.rush_processing and not is_auth,
    }


def get_authentication_summary_items(items):
    auth_items = [item for item in items if is_authentication_document(item)]
    summary_items = []

    for auth_item in auth_items:
        summary_items.append(build_summary_item(auth_item))

    return summary_items


def get_payment_summary(items):
    display_items = []
    document_total = Decimal("0.00")

    # List ALL items exactly as they appear in the database
    for item in items:
        summary_item = build_summary_item(item)
        display_items.append(summary_item)
        document_total += Decimal(str(summary_item["total_amount"]))

    lbc_charges = get_batch_lbc_charges(items)
    total_amount = document_total + lbc_charges["total_lbc_fee"]

    return display_items, total_amount


def normalize_city_name(city_name):
    return " ".join((city_name or "").strip().upper().split())


def get_lbc_rates_csv_path():
    return os.path.join(settings.BASE_DIR, "lbc_shipping_rates_legazpi.csv")


def lookup_lbc_shipping_fee(destination_city):
    normalized_destination = normalize_city_name(destination_city)
    csv_path = get_lbc_rates_csv_path()

    if not normalized_destination or not os.path.exists(csv_path):
        return None

    with open(csv_path, newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            row_city = normalize_city_name(row.get("Destination_City"))
            if row_city == normalized_destination:
                return Decimal(str(row.get("Price_PHP") or "0")).quantize(
                    Decimal("0.01")
                )
    return None


def calculate_lbc_valuation_fee(declared_value):
    declared_value = Decimal(str(declared_value or "0"))
    if declared_value <= 0:
        return Decimal("0.00")

    units = (declared_value / Decimal("500")).quantize(
        Decimal("1"), rounding=ROUND_UP
    )
    fee = Decimal("10.00") + (units * Decimal("5.00"))
    return fee.quantize(Decimal("0.01"))


def get_document_subtotal(items):
    subtotal = Decimal("0.00")
    for item in items:
        subtotal += Decimal(str(build_summary_item(item)["total_amount"]))
    return subtotal.quantize(Decimal("0.01"))


def get_batch_lbc_charges(items):
    batch_items = list(items) if not hasattr(items, "first") else list(items)
    lbc_item = next(
        (item for item in batch_items if (item.delivery_method or "PICKUP") == "LBC"),
        None,
    )
    if not lbc_item:
        return {
            "shipping_fee": Decimal("0.00"),
            "valuation_fee": Decimal("0.00"),
            "declared_value": Decimal("0.00"),
            "total_lbc_fee": Decimal("0.00"),
        }

    shipping_fee = Decimal(str(lbc_item.shipping_fee or "0"))
    valuation_fee = Decimal(str(lbc_item.valuation_fee or "0"))
    declared_value = Decimal(str(lbc_item.declared_value or "0"))
    total_lbc_fee = Decimal(str(lbc_item.lbc_total_fee or "0"))

    return {
        "shipping_fee": shipping_fee.quantize(Decimal("0.01")),
        "valuation_fee": valuation_fee.quantize(Decimal("0.01")),
        "declared_value": declared_value.quantize(Decimal("0.01")),
        "total_lbc_fee": total_lbc_fee.quantize(Decimal("0.01")),
    }


def compute_lbc_batch_fees(items, destination_city):
    document_subtotal = get_document_subtotal(items)
    shipping_fee = lookup_lbc_shipping_fee(destination_city)
    if shipping_fee is None:
        shipping_fee = Decimal("140.00")
    valuation_fee = calculate_lbc_valuation_fee(document_subtotal)
    total_lbc_fee = (shipping_fee + valuation_fee).quantize(Decimal("0.01"))

    return {
        "declared_value": document_subtotal,
        "shipping_fee": shipping_fee,
        "valuation_fee": valuation_fee,
        "total_lbc_fee": total_lbc_fee,
    }


def generate_lbc_tracking_number():
    return f"LBC-{uuid.uuid4().hex[:10].upper()}"


def normalize_tracking_number(tracking_number):
    return re.sub(r"\s+", "", (tracking_number or "")).upper()


def is_generated_lbc_tracking_number(tracking_number):
    return bool(GENERATED_LBC_TRACKING_RE.fullmatch(normalize_tracking_number(tracking_number)))


def is_internal_reference_number(tracking_number):
    normalized = normalize_tracking_number(tracking_number)
    return normalized.startswith("CATC-")


def register_batch_tracking_with_trackingmore(items, tracking_number):
    batch_items = list(items)
    normalized_tracking_number = normalize_tracking_number(tracking_number)
    if not batch_items or not normalized_tracking_number:
        return {
            "success": False,
            "code": 400,
            "message": "Tracking number is required.",
            "result": {},
        }

    lbc_item = next(
        (item for item in batch_items if item.delivery_method == "LBC"),
        None,
    )
    if lbc_item is None:
        return {
            "success": True,
            "code": 200,
            "message": "No LBC shipment in batch.",
            "result": {},
        }
    if is_internal_reference_number(normalized_tracking_number):
        logger.info(
            "Skipping TrackingMore registration for internal reference %s",
            normalized_tracking_number,
        )
        return {
            "success": False,
            "code": 400,
            "message": "Internal reference numbers cannot be synced to TrackingMore.",
            "result": {},
        }

    try:
        tracker = LBCTracker()
        result = tracker.register_lbc_tracking(normalized_tracking_number, lbc_item)
        status_code = result.get("meta", {}).get("code", 500)
        if status_code in {200, 201}:
            return {
                "success": True,
                "code": status_code,
                "message": result.get("meta", {}).get("message", "Tracking synced."),
                "result": result,
            }
        if status_code >= 400 or status_code == 202:
            logger.warning(
                "TrackingMore registration may have failed for %s: %s",
                normalized_tracking_number,
                result,
            )
            return {
                "success": False,
                "code": status_code,
                "message": result.get("meta", {}).get(
                    "message",
                    "TrackingMore could not sync this shipment.",
                ),
                "result": result,
            }
        return {
            "success": False,
            "code": status_code,
            "message": result.get("meta", {}).get(
                "message",
                "TrackingMore returned an unexpected response.",
            ),
            "result": result,
        }
    except Exception as exc:
        logger.warning(
            "TrackingMore registration failed for %s: %s",
            normalized_tracking_number,
            exc,
        )
        return {
            "success": False,
            "code": 500,
            "message": str(exc),
            "result": {},
        }


def ensure_batch_tracking_number(items):
    batch_items = list(items)
    if not batch_items:
        return ""

    has_lbc_delivery = any(item.delivery_method == "LBC" for item in batch_items)
    tracking_number = next(
        (
            normalize_tracking_number(item.tracking_number)
            for item in batch_items
            if item.tracking_number and item.tracking_number.strip()
        ),
        "",
    )
    if not tracking_number:
        tracking_number = (
            generate_lbc_tracking_number()
            if has_lbc_delivery
            else f"CATC-{uuid.uuid4().hex[:8].upper()}"
        )

    if tracking_number:
        missing_ids = [
            item.id
            for item in batch_items
            if not item.tracking_number or not item.tracking_number.strip()
        ]
        if missing_ids:
            DocumentRequest.objects.filter(id__in=missing_ids).update(
                tracking_number=tracking_number
            )

    if tracking_number:
        register_batch_tracking_with_trackingmore(batch_items, tracking_number)
    return tracking_number


def build_trackingmore_page_url(tracking_number, courier_code="lbcexpress"):
    base_url = getattr(settings, "TRACKINGMORE_TRACKING_PAGE_URL", "").strip()
    if not base_url or not tracking_number:
        return ""

    separator = "&" if "?" in base_url else "?"
    query = urlencode(
        {
            "tracking_number": tracking_number,
            "trackingNumber": tracking_number,
            "courier_code": courier_code,
            "carrier_code": courier_code,
            "courierCode": courier_code,
            "carrierCode": courier_code,
        }
    )
    return f"{base_url}{separator}{query}"


def get_tracking_stage_definitions():
    return [
        {
            "key": "AWAITING_COURIER_PICKUP",
            "label": "Awaiting for Pickup",
            "description": "Your document is prepared and waiting for courier handoff.",
        },
        {
            "key": "PICKED_UP_AWAITING_DELIVERY",
            "label": "Document Picked Up",
            "description": "The courier has picked up your document from the office.",
        },
        {
            "key": "IN_TRANSIT",
            "label": "In delivery",
            "description": "Your document is already on the way to the destination.",
        },
        {
            "key": "DELIVERED",
            "label": "Delivered",
            "description": "Your document has been delivered successfully.",
        },
    ]


def get_tracking_stage_index(status):
    status_order = {
        "AWAITING_COURIER_PICKUP": 0,
        "PICKED_UP_AWAITING_DELIVERY": 1,
        "IN_TRANSIT": 2,
        "DELIVERED": 3,
    }
    return status_order.get(status, 0)


def build_tracking_timeline(status):
    current_index = get_tracking_stage_index(status)
    timeline = []

    for index, stage in enumerate(get_tracking_stage_definitions()):
        if index < current_index:
            state = "completed"
        elif index == current_index:
            state = "current"
        else:
            state = "upcoming"

        timeline.append(
            {
                "key": stage["key"],
                "label": stage["label"],
                "description": stage["description"],
                "state": state,
            }
        )

    return timeline


def build_student_history_groups(user_requests):
    grouped = OrderedDict()

    for item in user_requests:
        grouping_id = item.batch_id or f"request-{item.id}"
        if grouping_id not in grouped:
            grouped[grouping_id] = {
                "grouper": item.batch_id or grouping_id,
                "list": [],
                "delivery_groups": OrderedDict(),
            }

        group = grouped[grouping_id]
        group["list"].append(item)

        delivery_key = item.delivery_method or "PICKUP"
        if delivery_key not in group["delivery_groups"]:
            group["delivery_groups"][delivery_key] = {
                "grouper": item.batch_id or grouping_id,
                "delivery_method": delivery_key,
                "list": [],
            }
        group["delivery_groups"][delivery_key]["list"].append(item)

    final_groups = []
    for group in grouped.values():
        group["delivery_groups"] = list(group["delivery_groups"].values())
        _, summary_total = get_payment_summary(group["list"])
        group["summary_total"] = summary_total
        final_groups.append(group)

    return final_groups


def build_registrar_batch_groups(items):
    grouped = OrderedDict()

    for item in items:
        grouping_id = item.batch_id or f"request-{item.id}"
        if grouping_id not in grouped:
            grouped[grouping_id] = {
                "grouper": item.batch_id,
                "list": [],
                "has_tor": False,
                "has_non_tor": False,
            }

        group = grouped[grouping_id]
        group["list"].append(item)

        is_tor_item = (
            "TOR" in item.document_type.name.upper()
            or "TRANSCRIPT" in item.document_type.name.upper()
        )
        if is_tor_item:
            group["has_tor"] = True
        else:
            group["has_non_tor"] = True

    return list(grouped.values())


def normalize_payment_delivery_method(delivery_method):
    if delivery_method in {"PICKUP", "LBC"}:
        return delivery_method
    return None


def get_payment_scope_queryset(
    *,
    batch_id,
    delivery_method=None,
    statuses=None,
    student=None,
    include_deleted=False,
):
    queryset = DocumentRequest.objects.all()
    if not include_deleted:
        queryset = queryset.filter(is_deleted=False)
    queryset = queryset.filter(batch_id=batch_id)

    normalized_method = normalize_payment_delivery_method(delivery_method)
    if normalized_method:
        queryset = queryset.filter(delivery_method=normalized_method)

    if statuses:
        queryset = queryset.filter(status__in=statuses)

    if student is not None:
        queryset = queryset.filter(student=student)

    return queryset


def build_payment_url(batch_id, delivery_method=None):
    normalized_method = normalize_payment_delivery_method(delivery_method)
    if normalized_method:
        return reverse("pay_with_xendit_scoped", args=[batch_id, normalized_method])
    return reverse("pay_with_xendit", args=[batch_id])


def build_xendit_external_id(batch_id, delivery_method=None):
    normalized_method = normalize_payment_delivery_method(delivery_method) or "ALL"
    return f"BATCH::{batch_id}::{normalized_method}::{uuid.uuid4().hex[:6]}"


def parse_xendit_external_id(external_id):
    if not external_id:
        return None, None

    if external_id.startswith("BATCH::"):
        parts = external_id.split("::", 3)
        if len(parts) >= 4:
            return parts[1], normalize_payment_delivery_method(parts[2])

    if external_id.startswith("BATCH-"):
        parts = external_id.split("-", 2)
        if len(parts) >= 2:
            return parts[1], None

    return None, None


def map_trackingmore_status(delivery_status, substatus=""):
    normalized_status = (delivery_status or "").strip().lower()
    normalized_substatus = (substatus or "").strip().lower()
    composite = f"{normalized_status}:{normalized_substatus}".strip(":")

    status_map = {
        "pending": "AWAITING_COURIER_PICKUP",
        "pending001": "AWAITING_COURIER_PICKUP",
        "pending002": "AWAITING_COURIER_PICKUP",
        "pickup": "PICKED_UP_AWAITING_DELIVERY",
        "info_received": "AWAITING_COURIER_PICKUP",
        "notfound": "AWAITING_COURIER_PICKUP",
        "transit": "IN_TRANSIT",
        "shipment collected": "PICKED_UP_AWAITING_DELIVERY",
        "intransit": "IN_TRANSIT",
        "out for delivery": "IN_TRANSIT",
        "out_for_delivery": "IN_TRANSIT",
        "exception": "IN_TRANSIT",
        "failed attempt": "IN_TRANSIT",
        "expired": "IN_TRANSIT",
        "transit:delivery_attempt_failure": "IN_TRANSIT",
        "transit:delivery_failed": "IN_TRANSIT",
        "transit:out_for_delivery": "IN_TRANSIT",
        "delivered": "DELIVERED",
        "delivered001": "DELIVERED",
        "delivered002": "DELIVERED",
        "delivered003": "DELIVERED",
        "delivered004": "DELIVERED",
        "delivered:delivered": "DELIVERED",
    }
    return status_map.get(composite) or status_map.get(normalized_status) or "IN_TRANSIT"


def get_xendit_paid_amount(items):
    payment_reference = items.first().payment_reference if items.exists() else None
    if not payment_reference:
        return None

    try:
        auth = base64.b64encode(f"{settings.XENDIT_SECRET_KEY}:".encode()).decode()
        xendit_res = requests.get(
            f"https://api.xendit.co/v2/invoices/{payment_reference}",
            headers={"Authorization": f"Basic {auth}"},
            timeout=5,
        )
        if xendit_res.status_code == 200:
            amount = xendit_res.json().get("amount")
            return amount if amount is not None else None
    except Exception:
        return None

    return None


def send_otp_sms(phone_number, otp_code, provider="iprog"):
    """
    Send OTP via SMS. Supports multiple providers.

    Args:
        phone_number: Target phone number
        otp_code: The OTP code to send
        provider: SMS provider - 'iprog' (default) or 'httpsms'
    """
    message = f"Your CATC Portal OTP is: {otp_code}. Valid for 10 minutes."

    clean_phone = phone_number.replace(" ", "").replace("-", "").replace("+", "")
    if clean_phone.startswith("0"):
        clean_phone = "+63" + clean_phone[1:]
    elif not clean_phone.startswith("63"):
        clean_phone = "+63" + clean_phone
    else:
        clean_phone = "+" + clean_phone

    # HTTPSMS requires E.164 format WITHOUT + prefix
    clean_phone = clean_phone.replace("+", "")

    if provider == "httpsms":
        return _send_httpsms_sms(clean_phone, message)
    else:
        return _send_iprog_sms(clean_phone, message)


def _send_httpsms_sms(clean_phone, message):
    """Send SMS via HTTP SMS API."""
    try:
        api_key = settings.HTTPSMS_API_KEY.strip()
        from_num = settings.HTTPSMS_FROM_NUMBER.strip().replace("+", "")

        print(f"HTTPSMS: from={from_num}, to={clean_phone}")

        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
        }

        data = {
            "content": message,
            "from": from_num,
            "to": clean_phone,
        }

        response = requests.post(
            "https://api.httpsms.com/v1/messages/send",
            json=data,
            headers=headers,
            timeout=15,
        )

        print(f"HTTPSMS Response: {response.status_code}")
        print(f"HTTPSMS Body: {response.text}")

        if response.status_code in [200, 201]:
            return True
        else:
            print(f"HTTPSMS Error: {response.text}")
            return False
    except Exception as e:
        print(f"HTTPSMS Exception: {e}")
        return False


def _send_iprog_sms(clean_phone, message):
    """Send SMS via iProg SMS API."""
    if not settings.IPROG_SMS_API_TOKEN:
        print("iProg SMS API token not configured")
        return False

    try:
        # iProg expects format: 63917... not +63917...
        phone_for_iprog = clean_phone.replace("+", "")

        data = {
            "api_token": settings.IPROG_SMS_API_TOKEN,
            "phone_number": phone_for_iprog,
            "message": message,
            "sms_provider": 0,
        }

        print(f"[IPROG] Sending to {phone_for_iprog}, message: {message}")

        response = requests.post(
            "https://www.iprogsms.com/api/v1/sms_messages",
            data=data,
            timeout=15,
        )

        print(f"[IPROG] Response status: {response.status_code}")
        print(f"[IPROG] Response text: {response.text[:500]}")

        if response.status_code in [200, 201]:
            result = response.json()
            print(f"[IPROG] Result: {result}")
            if result.get("status") == 200:
                print(f"iProg SMS sent successfully to {clean_phone}")
                return True
            else:
                print(f"iProg SMS API error: {result}")
                return False
        else:
            print(f"iProg SMS API error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"iProg SMS API exception: {e}")
        return False


def create_notification(user, role, message):
    Notification.objects.create(user=user, sender_role=role, message=message)


# --- 2. LOGIN FLOW ---


def login_view(request):
    print(f"[LOGIN_VIEW] Request method: {request.method}")
    print(f"[LOGIN_VIEW] POST data: {request.POST}")
    if request.user.is_authenticated:
        django_logout(request)
    if request.method == "POST":
        print("[LOGIN_VIEW] Processing POST request")
        last_sent = request.session.get("otp_last_sent")
        if last_sent and time.time() - last_sent < 60:
            messages.error(request, "Please wait before requesting a new code.")
            return render(
                request, "login_id.html", {"form": StudentIDLoginForm(request.POST)}
            )
        form = StudentIDLoginForm(request.POST)
        print(f"[LOGIN_VIEW] Form valid: {form.is_valid()}")
        if not form.is_valid():
            print(f"[LOGIN_VIEW] Form errors: {form.errors}")
            return render(request, "login_id.html", {"form": form})

        sid = form.cleaned_data["student_id"].upper()
        otp_method = form.cleaned_data["otp_method"]
        print(f"[LOGIN_VIEW] Student ID: {sid}, OTP method: {otp_method}")
        master_student = StudentMasterList.objects.filter(student_id=sid).first()
        print(f"[LOGIN_VIEW] Master student found: {master_student}")
        django_logout(request)
    if request.method == "POST":
        last_sent = request.session.get("otp_last_sent")
        if last_sent and time.time() - last_sent < 60:
            messages.error(request, "Please wait before requesting a new code.")
            return render(
                request, "login_id.html", {"form": StudentIDLoginForm(request.POST)}
            )
        form = StudentIDLoginForm(request.POST)
        if form.is_valid():
            sid = form.cleaned_data["student_id"].upper()
            otp_method = form.cleaned_data["otp_method"]
            master_student = StudentMasterList.objects.filter(student_id=sid).first()
            if master_student:
                user, created = User.objects.get_or_create(
                    username=sid, defaults={"email": master_student.email}
                )
                if created:
                    group, _ = Group.objects.get_or_create(name="Student")
                    user.groups.add(group)

                # Always create a new OTP token for this login attempt
                # Delete any existing unverified OTP tokens for this user
                OTPToken.objects.filter(user=user, is_verified=False).delete()

                # Create new OTP token
                otp_obj = OTPToken.objects.create(user=user)
                otp_obj.generate_code()

                # Get Google Authenticator provisioning URI
                google_auth_uri = otp_obj.get_google_auth_uri()

                # Send OTP via chosen method
                try:
                    if otp_method == "email":
                        # Send email with OTP
                        email_message = f"""
Your CATC Portal Login Code: {otp_obj.otp_code}

This code is valid for 10 minutes.

To use Google Authenticator:
1. Download Google Authenticator app on your phone
2. The secret key for setup is: {otp_obj.google_auth_secret}

Or scan this QR code in the Google Authenticator app.
"""
                        send_mail(
                            "Login OTP",
                            email_message,
                            settings.DEFAULT_FROM_EMAIL,
                            [master_student.email],
                        )
                        print(f"[EMAIL] OTP sent to {master_student.email}")
                        messages.success(
                            request,
                            f"OTP sent to your email: {master_student.masked_email}",
                        )
                    else:
                        # Always use HTTPSMS for SMS - DEFAULT
                        print(
                            f"[DEBUG] Calling send_otp_sms to {master_student.phone_number}"
                        )
                        sms_sent = send_otp_sms(
                            master_student.phone_number,
                            otp_obj.otp_code,
                            provider="httpsms",
                        )
                        print(f"[DEBUG] sms_sent result: {sms_sent}")
                        if sms_sent:
                            print(
                                f"[SMS] OTP sent via HTTPSMS to {master_student.phone_number}"
                            )
                            messages.success(
                                request,
                                f"OTP sent to your phone: {master_student.masked_phone}",
                            )
                        else:
                            print(
                                f"[SMS] FAILED: HTTPSMS to {master_student.phone_number}"
                            )
                            messages.error(
                                request,
                                "Failed to send OTP via SMS. Please try again or use email.",
                            )
                            return render(
                                request, "login_id.html", {"form": StudentIDLoginForm()}
                            )
                except Exception as e:
                    print(f"OTP sending failed: {e}")
                    messages.error(request, "Failed to send OTP. Please try again.")
                    print(
                        f"[LOGIN DEBUG] Phone number from DB: '{master_student.phone_number}'"
                    )

                request.session["masked_email"], request.session["masked_phone"] = (
                    master_student.masked_email,
                    master_student.masked_phone,
                )
                request.session["otp_last_sent"], request.session["otp_user_id"] = (
                    time.time(),
                    user.id,
                )
                request.session["google_auth_secret"] = otp_obj.google_auth_secret
                request.session["otp_sent_success"] = True

                return redirect("verify_otp")
            else:
                messages.error(request, "Student ID not found.")
    return render(request, "login_id.html", {"form": StudentIDLoginForm()})


def verify_otp(request):
    user_id = request.session.get("otp_user_id")
    if not user_id:
        return redirect("login")
    user = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        form = OTPVerifyForm(request.POST)
        if form.is_valid():
            threshold = timezone.now() - timedelta(minutes=10)
            input_code = form.cleaned_data["otp_code"].strip()

            # First, try to find any unverified OTP for this user within the time window
            otp_record = OTPToken.objects.filter(
                user=user, is_verified=False, created_at__gte=threshold
            ).last()

            if otp_record:
                # Check if user is entering a Google Authenticator code (6 digits)
                # or the regular email/SMS OTP code
                if otp_record.google_auth_enabled and otp_record.google_auth_secret:
                    # Try Google Authenticator first
                    try:
                        import pyotp

                        totp = pyotp.TOTP(otp_record.google_auth_secret)
                        # Use valid_window=1 to allow for 30-second time drift on either side
                        if totp.verify(input_code, valid_window=1):
                            otp_record.is_verified = True
                            otp_record.save()
                            login(request, user)
                            del request.session["otp_user_id"]
                            return redirect("student_dashboard")
                    except ImportError:
                        pass

                # Fall back to regular OTP code
                if otp_record.otp_code == input_code:
                    otp_record.is_verified = True
                    otp_record.save()
                    login(request, user)
                    del request.session["otp_user_id"]
                    return redirect("student_dashboard")

                messages.error(request, "Invalid or expired OTP code.")
            else:
                messages.error(
                    request,
                    "No pending OTP verification found. Please request a new code.",
                )

    # Pass Google Auth secret to template for manual entry if needed
    google_auth_secret = request.session.get("google_auth_secret")
    return render(
        request,
        "login_otp.html",
        {
            "form": OTPVerifyForm(),
            "masked_email": request.session.get("masked_email"),
            "masked_phone": request.session.get("masked_phone"),
            "google_auth_secret": google_auth_secret,
        },
    )


# --- 3. STUDENT DASHBOARD ---


@role_required(allowed_roles=["Student"])
def student_dashboard(request):
    # Auto-verify pending Xendit payment when student returns from payment page
    pending_invoice = request.session.pop("pending_xendit_invoice", None)
    if pending_invoice:
        try:
            auth = base64.b64encode(f"{settings.XENDIT_SECRET_KEY}:".encode()).decode()
            xendit_res = requests.get(
                f"https://api.xendit.co/v2/invoices/{pending_invoice['invoice_id']}",
                headers={"Authorization": f"Basic {auth}"},
                timeout=5,
            )
            if xendit_res.status_code == 200:
                inv_status = xendit_res.json().get("status", "")
                if inv_status == "PAID":
                    payable_scope = get_payment_scope_queryset(
                        batch_id=pending_invoice["batch_id"],
                        delivery_method=pending_invoice.get("delivery_method"),
                        statuses=["APPROVED", "PAYMENT_REQUIRED"],
                    )
                    if payable_scope.exists():
                        payable_scope.update(status="PAID")
                        messages.success(
                            request,
                            "Payment Verified! Your documents are being processed.",
                        )
        except Exception:
            pass  # Webhook will handle it as fallback

    student_info = StudentMasterList.objects.filter(
        student_id=request.user.username
    ).first()
    balance_record = StudentBalance.objects.filter(
        student__student_id=request.user.username
    ).first()
    has_balance = balance_record.outstanding_amount > 0 if balance_record else False
    user_requests = DocumentRequest.objects.filter(
        student=request.user, is_deleted=False
    ).order_by("-created_at")
    history_groups = build_student_history_groups(user_requests)

    greetings = [
        "Welcome! Have a Good Day.",
        "Hello!",
        "Your documents, our priority.",
        "Making paperwork easier!",
    ]
    random_greeting = random.choice(greetings)

    all_docs = DocumentType.objects.all()
    base_docs = all_docs.exclude(name__startswith="Authentication")
    auth_docs = all_docs.filter(name__startswith="Authentication")

    # RESTRICTED KEYWORDS
    RESTRICTED_KEYWORDS = ["TOR", "TRANSCRIPT", "DIPLOMA", "CLEARANCE"]

    # Check if student is graduated
    is_graduated = student_info.is_graduated if student_info else False

    # Get TOR request count for this student
    tor_request_count = 0
    if student_info:
        tor_type = DocumentType.objects.filter(name__icontains="TOR").first()
        if tor_type:
            tor_request_count = (
                DocumentRequest.objects.filter(
                    student=request.user, document_type=tor_type, is_deleted=False
                )
                .exclude(status="REJECTED")
                .count()
            )

    # Check if first TOR request (free for graduates)
    is_first_tor_request = is_graduated and tor_request_count == 0

    grouped_docs = []
    for base in base_docs:
        auth_match = auth_docs.filter(name__icontains=base.name).first()
        # Specific check: is this a restricted document?
        is_restricted = any(key in base.name.upper() for key in RESTRICTED_KEYWORDS)

        # Special handling for TOR
        is_tor = "TOR" in base.name.upper() or "TRANSCRIPT" in base.name.upper()

        # For TOR: if graduated and first request, show as FREE
        tor_display_price = None
        if is_tor and is_first_tor_request:
            tor_display_price = 0  # Free for first TOR request
        elif is_tor and not is_first_tor_request:
            tor_display_price = "100php per page"

        grouped_docs.append(
            {
                "id": base.id,
                "name": base.name,
                "price": base.price,
                "has_auth": bool(auth_match),
                "auth_id": auth_match.id if auth_match else None,
                # Block ONLY if it is restricted AND user has a balance
                "is_blocked": (is_restricted and has_balance),
                # TOR-specific info
                "is_tor": is_tor,
                "tor_display_price": tor_display_price,
                "is_first_tor_request": is_first_tor_request,
            }
        )

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "delete_request":
            batch_id = request.POST.get("batch_id")
            DocumentRequest.objects.filter(
                batch_id=batch_id, student=request.user
            ).update(is_deleted=True)
            messages.success(request, "Request cancelled successfully.")
            return redirect("student_dashboard")

        if action in ["preview_lbc_shipping", "save_lbc_shipping"]:
            batch_id = request.POST.get("batch_id")
            receiver_raw = request.POST.get("lbc_receiver", "{}")
            receiver = {}
            try:
                receiver = json.loads(receiver_raw)
            except json.JSONDecodeError:
                receiver = {}

            batch = DocumentRequest.objects.filter(
                batch_id=batch_id,
                student=request.user,
                delivery_method="LBC",
            )
            batch_sample = batch.first()
            is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

            if not batch_sample:
                payload = {"success": False, "message": "LBC batch not found."}
                return JsonResponse(payload, status=404 if is_ajax else 200)

            required_fields = [
                "firstname",
                "lastname",
                "phone",
                "province",
                "city",
                "barangay",
                "floor",
                "street",
            ]
            missing_fields = [field for field in required_fields if not str(receiver.get(field, "")).strip()]
            if missing_fields:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Please complete the LBC receiver information.",
                    },
                    status=400,
                )

            fee_data = compute_lbc_batch_fees(batch, receiver.get("city"))
            response_payload = {
                "success": True,
                "message": (
                    f"LBC shipping info saved. Shipping fee: PHP {fee_data['shipping_fee']}, "
                    f"valuation fee: PHP {fee_data['valuation_fee']}."
                ),
                "payment_url": build_payment_url(
                    batch_id, batch_sample.delivery_method or "LBC"
                ),
                "fees": {
                    "declared_value": str(fee_data["declared_value"]),
                    "shipping_fee": str(fee_data["shipping_fee"]),
                    "valuation_fee": str(fee_data["valuation_fee"]),
                    "total_lbc_fee": str(fee_data["total_lbc_fee"]),
                },
                "calculator": {
                    "shipment_type": "Within the Philippines",
                    "category": "Document",
                    "packaging": "Courier N-Pouch Regular",
                    "packaging_size": "6.5 x 11 x 1.75 in",
                    "origin_city": "City of Legazpi",
                    "destination_city": receiver.get("city", "").strip(),
                    "content_description": "Documents",
                },
            }

            if action == "preview_lbc_shipping":
                response_payload["message"] = "LBC shipping preview computed."
                return JsonResponse(response_payload)

            batch.update(
                lbc_type="BRANCH"
                if request.POST.get("lbc_delivery_type") == "branch_pickup"
                else "RIDER",
                lbc_branch_name=request.POST.get("lbc_branch_name", "").strip() or None,
                shipping_first_name=receiver.get("firstname", "").strip(),
                shipping_last_name=receiver.get("lastname", "").strip(),
                shipping_phone=receiver.get("phone", "").strip(),
                shipping_floor=receiver.get("floor", "").strip(),
                shipping_street=receiver.get("street", "").strip(),
                shipping_province=receiver.get("province", "").strip(),
                shipping_city=receiver.get("city", "").strip(),
                shipping_barangay=receiver.get("barangay", "").strip(),
                shipping_zip=receiver.get("zip", "").strip() or None,
                shipping_landmark=receiver.get("landmark", "").strip() or None,
                declared_value=fee_data["declared_value"],
                shipping_fee=fee_data["shipping_fee"],
                valuation_fee=fee_data["valuation_fee"],
                lbc_total_fee=fee_data["total_lbc_fee"],
                status="PAYMENT_REQUIRED",
            )
            ensure_batch_tracking_number(batch)

            if is_ajax:
                return JsonResponse(response_payload)

            messages.success(request, response_payload["message"])
            return redirect("student_dashboard")

        if action == "submit_request":
            reason = request.POST.get("reason")
            batch_id = str(uuid.uuid4())[:8]
            found_any = False

            for base in base_docs:
                selection = request.POST.get(f"selection_{base.id}")
                if not selection or selection == "none":
                    continue

                # SERVER-SIDE PROTECTION: Check if they tried to bypass the UI block
                is_restricted = any(
                    key in base.name.upper() for key in RESTRICTED_KEYWORDS
                )
                if is_restricted and has_balance:
                    messages.error(
                        request,
                        f"Cannot request {base.name} due to outstanding balance.",
                    )
                    return redirect("student_dashboard")

                found_any = True
                delivery = request.POST.get(f"delivery_{base.id}", "PICKUP")

                to_create = []
                if selection == "doc":
                    to_create.append(base)
                elif selection == "auth":
                    to_create.append(
                        auth_docs.filter(name__icontains=base.name).first()
                    )
                elif selection == "both":
                    to_create.append(base)
                    to_create.append(
                        auth_docs.filter(name__icontains=base.name).first()
                    )

                for dt in to_create:
                    if dt:
                        # Check if this is a TOR request
                        is_tor = (
                            "TOR" in dt.name.upper() or "TRANSCRIPT" in dt.name.upper()
                        )

                        # Check if rush processing is requested
                        rush_requested = request.POST.get(f"rush_{base.id}") == "1"

                        # Set processing_days: 1 for rush, default 3
                        processing_days_value = 1 if rush_requested else 3

                        # Create the document request
                        doc_request = DocumentRequest.objects.create(
                            student=request.user,
                            document_type=dt,
                            reason=reason,
                            batch_id=batch_id,
                            delivery_method=delivery,
                            lbc_type=request.POST.get(f"lbc_type_{base.id}"),
                            lbc_branch_name=request.POST.get(f"lbc_branch_{base.id}"),
                            rush_processing=rush_requested,
                            processing_days=processing_days_value,
                        )

                        # Special handling for TOR
                        if is_tor and is_first_tor_request:
                            # First TOR request for graduate is FREE
                            doc_request.tor_price_override = 0
                            doc_request.save()
                            if rush_requested:
                                messages.info(
                                    request,
                                    f"Your {dt.name} request is FREE as it's your first request as a graduate. Rush processing applies (2x = ₱0 still free).",
                                )
                            else:
                                messages.info(
                                    request,
                                    f"Your {dt.name} request is FREE as it's your first request as a graduate.",
                                )
                        elif is_tor:
                            # Subsequent TOR requests need registrar to count pages
                            if rush_requested:
                                messages.info(
                                    request,
                                    f"Your {dt.name} request will be reviewed by the Registrar with rush processing. You will be notified of the page count and payment amount (2x price).",
                                )
                            else:
                                messages.info(
                                    request,
                                    f"Your {dt.name} request will be reviewed by the Registrar. You will be notified of the page count and payment amount.",
                                )

            if found_any:
                messages.success(request, "Document requests submitted!")
            else:
                messages.warning(request, "No documents were selected.")
            return redirect("student_dashboard")

    # Get active shipment for tracking panel (most recent shipment with tracking number)
    active_shipment = (
        user_requests.filter(tracking_number__isnull=False, tracking_number__gt="")
        .exclude(status__in=["COMPLETED", "DELIVERED", "REJECTED"])
        .first()
    )

    return render(
        request,
        "dashboard.html",
        {
            "grouped_docs": grouped_docs,
            "history_groups": history_groups,
            "requests": user_requests,
            "student": student_info,
            "random_greeting": random_greeting,
            "has_balance": has_balance,
            "balance_amount": balance_record.outstanding_amount
            if balance_record
            else 0,
            "unread_count": Notification.objects.filter(
                user=request.user, is_read=False
            ).count(),
            "notifications": Notification.objects.filter(user=request.user).order_by(
                "-created_at"
            )[:10],
            "active_shipment": active_shipment,
            "system_tracking_page_url": reverse("system_tracking_page"),
            "trackingmore_tracking_page_url": reverse("system_tracking_page"),
        },
    )


# --- 4. REGISTRAR ---


@role_required(allowed_roles=["Registrar"])
def registrar_dashboard(request):
    active_requests = (
        DocumentRequest.objects.filter(is_deleted=False)
        .exclude(status__in=["COMPLETED", "DELIVERED", "REJECTED"])
        .order_by("-created_at")
    )
    history = DocumentRequest.objects.filter(
        is_deleted=False, status__in=["COMPLETED", "DELIVERED", "REJECTED"]
    ).order_by("-created_at")

    # Calculate stats for cards
    pending_count = active_requests.filter(status="PENDING").count()
    ready_count = active_requests.filter(
        status__in=[
            "READY",
            "AWAITING_COURIER_PICKUP",
            "PICKED_UP_AWAITING_DELIVERY",
            "IN_TRANSIT",
        ]
    ).count()
    paid_count = (
        active_requests.filter(status="PAID").count()
        + active_requests.filter(status="PROCESSING").count()
    )
    processing_count = active_requests.filter(
        status__in=[
            "PROCESSING",
            "AWAITING_COURIER_PICKUP",
            "PICKED_UP_AWAITING_DELIVERY",
            "IN_TRANSIT",
        ]
    ).count()
    if request.method == "POST":
        action = request.POST.get("action")
        batch_id = (request.POST.get("batch_id") or "").strip()
        request_id = request.POST.get("request_id")
        print(
            f"[DEBUG] Registrar POST - action: {action}, batch_id: {batch_id}, request_id: {request_id}"
        )

        batch = DocumentRequest.objects.none()
        batch_ref = batch_id

        if batch_id:
            batch = DocumentRequest.objects.filter(batch_id=batch_id, is_deleted=False)
        elif request_id:
            target_request = get_object_or_404(
                DocumentRequest, pk=request_id, is_deleted=False
            )
            if target_request.batch_id:
                batch_ref = target_request.batch_id
                batch = DocumentRequest.objects.filter(
                    batch_id=target_request.batch_id, is_deleted=False
                )
            else:
                batch_ref = str(target_request.id)
                batch = DocumentRequest.objects.filter(
                    pk=target_request.pk, is_deleted=False
                )

        if action == "approve":
            # Approve non-TOR requests for payment
            # TOR requests are handled by 'send_to_tor' action

            # Filter out TOR requests - they go through send_to_tor action
            non_tor_batch = batch.exclude(
                Q(document_type__name__icontains="TOR")
                | Q(document_type__name__icontains="TRANSCRIPT")
            )

            if non_tor_batch.exists():
                non_tor_batch.update(status="PAYMENT_REQUIRED")
                log_audit(
                    request.user,
                    "UPDATE",
                    "DocumentRequest",
                    batch_ref,
                    "Approved and marked as awaiting payment.",
                )
                # Notify student
                for item in non_tor_batch:
                    if item.delivery_method == "LBC":
                        approval_message = (
                            f"Your {item.document_type.name} request has been approved. "
                            "Please complete your LBC shipping information so the system can compute your shipping and valuation fees before payment."
                        )
                    elif item.rush_processing:
                        approval_message = (
                            f"Your {item.document_type.name} request has been approved (RUSH - 2x Price). Please proceed to payment."
                        )
                    else:
                        approval_message = (
                            f"Your {item.document_type.name} request has been approved. Please proceed to payment."
                        )

                    create_notification(item.student, "Registrar", approval_message)
                messages.success(request, f"Request approved for payment.")
            else:
                messages.info(request, "No non-TOR requests to approve in this batch.")
        elif action == "send_to_tor":
            # Directly send TOR requests to TOR dashboard for page counting
            # Only update TOR/Transcript items in the batch
            tor_items = batch.filter(
                Q(document_type__name__icontains="TOR")
                | Q(document_type__name__icontains="TRANSCRIPT")
            )
            tor_items.update(status="PENDING_TOR_COUNT")
            log_audit(
                request.user,
                "UPDATE",
                "DocumentRequest",
                batch_ref,
                "Sent to TOR Desk for page counting.",
            )
            # Notify TOR desk and student
            for item in tor_items:
                rush_msg = " (RUSH - PRIORITY)" if item.rush_processing else ""
                create_notification(
                    item.student,
                    "TOR Desk",
                    f"Your TOR request has been sent to TOR Desk for page counting.{rush_msg} Please wait for the TOR Desk to process.",
                )
            messages.success(
                request, f"TOR request sent to TOR Desk for page counting."
            )
        elif action == "reject":
            batch.update(status="REJECTED")
            log_audit(
                request.user, "UPDATE", "DocumentRequest", batch_ref, "Rejected batch."
            )
            # Get rejection reason from POST data
            rejection_reason = request.POST.get("rejection_reason", "").strip()
            for item in batch:
                if rejection_reason:
                    create_notification(
                        item.student,
                        "Registrar",
                        f"Your {item.document_type.name} request has been rejected. Reason: {rejection_reason}",
                    )
                else:
                    create_notification(
                        item.student,
                        "Registrar",
                        f"Your {item.document_type.name} request has been rejected.",
                    )
        elif action == "mark_ready":
            processing_days = request.POST.get("processing_days")
            batch_sample = batch.first()
            try:
                processing_days = int(processing_days) if processing_days else None
            except ValueError:
                processing_days = None

            # Pickup batches keep an internal CATC reference.
            # LBC batches wait for the real courier tracking number.
            t_no = ensure_batch_tracking_number(batch)

            # Update each item with tracking number and processing days.
            # LBC requests wait for courier pickup after registrar marks them ready.
            for item in batch:
                if t_no:
                    item.tracking_number = t_no
                item.processing_days = processing_days
                if item.delivery_method == "LBC":
                    item.status = "AWAITING_COURIER_PICKUP"
                else:
                    item.status = "READY"
                item.save()
            # Success message for marking as ready
            ready_count = batch.count()
            lbc_count = batch.filter(delivery_method="LBC").count()
            pickup_count = ready_count - lbc_count

            if lbc_count > 0:
                messages.success(
                    request,
                    f"{lbc_count} LBC document(s) marked as awaiting courier pickup with system tracking enabled.",
                )
            if pickup_count > 0:
                messages.success(
                    request,
                    f"{pickup_count} pickup document(s) marked as READY - waiting for student to claim. Tracking: {t_no}",
                )
            log_audit(
                request.user,
                "UPDATE",
                "DocumentRequest",
                batch_ref,
                f"Marked as ready for release. Tracking: {t_no}, Days: {processing_days}",
            )

            print(
                f"[DEBUG] mark_ready completed. Batch ID: {batch_id}, Items updated: {ready_count}"
            )

            # Notify student about status
            for item in batch:
                if item.delivery_method == "LBC":
                    create_notification(
                        item.student,
                        "Registrar",
                        f"Your {item.document_type.name} is ready and is now waiting for LBC courier pickup. You can already track it using your system tracking number.",
                    )
                else:
                    if processing_days:
                        create_notification(
                            item.student,
                            "Registrar",
                            f"Your {item.document_type.name} will be ready in {processing_days} day(s). Your Reference Number: {t_no}. Please proceed to pickup.",
                        )
                    else:
                        create_notification(
                            item.student,
                            "Registrar",
                            f"Your {item.document_type.name} is ready for pickup. Your Reference Number: {t_no}. Please proceed to claim.",
                        )

            # Explicit redirect with success message
            messages.success(request, f"Success! {ready_count} document(s) updated.")
            return redirect("registrar_dashboard")
        elif action == "mark_done":
            # Mark as DONE - for office pickup when student has collected the document
            # This moves the request to history
            print(
                f"[DEBUG] mark_done action received. Batch ID: {batch_id}, Items in batch: {batch.count()}"
            )
            for item in batch:
                # Check if this is a TOR/Transcript request - create permanent history record
                is_tor_request = (
                    "TOR" in str(item.document_type.name).upper()
                    or "TRANSCRIPT" in str(item.document_type.name).upper()
                )

                if is_tor_request:
                    # Create permanent TORRequestHistory record (cannot be deleted by students)
                    # Note: TORRequestHistory.student is a ForeignKey to User (same as DocumentRequest.student)
                    TORRequestHistory.objects.create(
                        student=item.student,
                        document_type=item.document_type.name,
                        page_count=item.tor_page_count,
                        price=item.get_price() or 0,
                        is_free=(item.get_price() == 0),
                        requested_at=item.created_at,
                        completed_at=timezone.now(),
                        batch_id=item.batch_id,
                    )
                    print(
                        f"[DEBUG] Created TORRequestHistory for student {item.student.username}, is_free: {item.get_price() == 0}"
                    )

                item.status = "COMPLETED"
                item.save()
                create_notification(
                    item.student,
                    "Registrar",
                    f"Your {item.document_type.name} has been marked as COMPLETED. Thank you!",
                )

            done_count = batch.count()
            messages.success(
                request,
                f"{done_count} document(s) marked as DONE and moved to history.",
            )
            log_audit(
                request.user,
                "UPDATE",
                "DocumentRequest",
                batch_id,
                "Marked as DONE (completed). Moved to history.",
            )
            return redirect("registrar_dashboard")
        elif action == "mark_completed":
            batch.update(status="COMPLETED")
            messages.success(
                request, f"{batch.count()} document(s) marked as COMPLETED."
            )
        elif action == "extend_processing":
            extend_days = request.POST.get("extend_days", "1")
            extend_reason = request.POST.get("extend_reason", "").strip()
            if not extend_reason:
                messages.error(request, "Please provide a reason for the extension.")
                return redirect("registrar_dashboard")
            try:
                extend_days = int(extend_days)
            except ValueError:
                extend_days = 1
            for item in batch:
                item.processing_days = (item.processing_days or 3) + extend_days
                item.save()
                create_notification(
                    item.student,
                    "Registrar",
                    f"Processing Extended: Your {item.document_type.name} will require {extend_days} additional day(s). "
                    f"Reason: {extend_reason}. Please expect further updates.",
                )
            messages.success(
                request,
                f"Processing extended by {extend_days} day(s). Student has been notified.",
            )
        return redirect("registrar_dashboard")
    # Separate filtered requests for tabs
    pending_requests = active_requests.filter(status="PENDING")
    pending_groups = build_registrar_batch_groups(pending_requests)
    paid_requests = active_requests.filter(status="PAID")
    processing_requests = active_requests.filter(status="PROCESSING")
    ready_requests = active_requests.filter(
        status__in=[
            "READY",
            "AWAITING_COURIER_PICKUP",
            "PICKED_UP_AWAITING_DELIVERY",
            "IN_TRANSIT",
        ]
    )

    return render(
        request,
        "registrar_dashboard.html",
        {
            "active_requests": active_requests,
            "history": history,
            "pending_count": pending_count,
            "ready_count": ready_count,
            "paid_count": paid_count,
            "processing_count": processing_count,
            "pending_requests": pending_requests,
            "pending_groups": pending_groups,
            "paid_requests": paid_requests,
            "processing_requests": processing_requests,
            "ready_requests": ready_requests,
        },
    )


# --- 5. ACCOUNTING & CSV EXPORT ---


@role_required(allowed_roles=["Accounting"])
def export_collection_csv(request):
    transactions = CollectionLog.objects.all().order_by("-created_at")
    filter_type = request.GET.get("filter_type", "all")
    target_date = request.GET.get("target_date")

    if target_date:
        try:
            date_obj = timezone.datetime.strptime(target_date, "%Y-%m-%d").date()
            if filter_type == "daily":
                transactions = transactions.filter(created_at__date=date_obj)
            elif filter_type == "weekly":
                start = date_obj - timedelta(days=date_obj.weekday())
                transactions = transactions.filter(
                    created_at__date__range=[start, start + timedelta(days=6)]
                )
            elif filter_type == "monthly":
                transactions = transactions.filter(
                    created_at__year=date_obj.year, created_at__month=date_obj.month
                )
            elif filter_type == "yearly":
                transactions = transactions.filter(created_at__year=date_obj.year)
        except:
            pass

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="CATC_Ledger.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "Timestamp",
            "OR Number",
            "Student ID",
            "Student Name",
            "Method",
            "Amount",
            "Docs",
        ]
    )
    for t in transactions:
        writer.writerow(
            [
                t.created_at.strftime("%Y-%m-%d %H:%M"),
                t.receipt_number,
                t.student_id,
                t.student_name,
                t.payment_method,
                t.amount_paid,
                t.documents_included,
            ]
        )
    return response


@role_required(allowed_roles=["Accounting"])
def accounting_dashboard(request):
    transactions = CollectionLog.objects.all().order_by("-created_at")
    audit_logs = AuditLog.objects.all().order_by("-timestamp")[:100]
    all_requests_history = DocumentRequest.objects.all().order_by("-created_at")

    filter_type, target_date = (
        request.GET.get("filter_type", "all"),
        request.GET.get("target_date"),
    )
    if target_date:
        try:
            date_obj = timezone.datetime.strptime(target_date, "%Y-%m-%d").date()
            if filter_type == "daily":
                transactions = transactions.filter(created_at__date=date_obj)
            elif filter_type == "weekly":
                start = date_obj - timedelta(days=date_obj.weekday())
                transactions = transactions.filter(
                    created_at__date__range=[start, start + timedelta(days=6)]
                )
            elif filter_type == "monthly":
                transactions = transactions.filter(
                    created_at__year=date_obj.year, created_at__month=date_obj.month
                )
            elif filter_type == "yearly":
                transactions = transactions.filter(created_at__year=date_obj.year)
        except:
            pass

    cash_total = (
        transactions.filter(payment_method="CASH").aggregate(Sum("amount_paid"))[
            "amount_paid__sum"
        ]
        or 0
    )
    online_total = (
        transactions.filter(payment_method="ONLINE").aggregate(Sum("amount_paid"))[
            "amount_paid__sum"
        ]
        or 0
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_price":
            doc = get_object_or_404(DocumentType, id=request.POST.get("doc_id"))
            doc.price = request.POST.get("new_price")
            doc.save()
            log_audit(request.user, "PRICE", "DocumentType", doc.id, "Price updated.")
        elif action == "notify_balance":
            record = get_object_or_404(
                StudentBalance, id=request.POST.get("balance_id")
            )
            send_mail(
                "Balance Notice",
                f"Balance: ₱{record.outstanding_amount}.",
                settings.DEFAULT_FROM_EMAIL,
                [record.student.email],
            )
            record.last_notified = timezone.now()
            record.save()
        elif action == "clear_balance":
            record = get_object_or_404(
                StudentBalance, id=request.POST.get("balance_id")
            )
            amount_cleared = record.outstanding_amount
            record.clear_balance()
            log_audit(
                request.user,
                "BALANCE",
                "StudentBalance",
                record.id,
                f"Cleared balance: ₱{amount_cleared}",
            )
            messages.success(
                request,
                f"Balance of ₱{amount_cleared} cleared for {record.student.student_id}",
            )
        return redirect("accounting_dashboard")

    return render(
        request,
        "accounting_dashboard.html",
        {
            "transactions": transactions,
            "cash_total": cash_total,
            "online_total": online_total,
            "total_revenue": cash_total + online_total,
            "filter_type": filter_type,
            "target_date": target_date,
            "audit_logs": audit_logs,
            "doc_types": DocumentType.objects.all(),
            "debtors": StudentBalance.objects.filter(
                outstanding_amount__gt=0
            ).select_related("student"),
            "all_requests_history": all_requests_history,
        },
    )


# --- 6. CASHIER ---


@role_required(allowed_roles=["Cashier"])
def cashier_dashboard(request):
    unpaid = DocumentRequest.objects.filter(
        is_deleted=False, status="PAYMENT_REQUIRED"
    ).filter(
        Q(delivery_method="PICKUP") | Q(delivery_method="LBC", shipping_fee__isnull=False)
    ).order_by("-created_at")
    online_pending = DocumentRequest.objects.filter(
        is_deleted=False, status="PENDING_CASHIER_APPROVAL"
    ).order_by("-created_at")
    awaiting = DocumentRequest.objects.filter(is_deleted=False, status="PAID").order_by(
        "-created_at"
    )

    # Combine all active payments into one list
    all_payments = list(unpaid) + list(online_pending) + list(awaiting)
    # Sort by created_at descending
    all_payments = sorted(all_payments, key=lambda x: x.created_at, reverse=True)
    for item in all_payments:
        scope_items = get_payment_scope_queryset(
            batch_id=item.batch_id,
            delivery_method=item.delivery_method,
        )
        _, item.display_amount = get_payment_summary(scope_items)

    history = DocumentRequest.objects.filter(
        is_deleted=False,
        status__in=[
            "PROCESSING",
            "READY",
            "AWAITING_COURIER_PICKUP",
            "PICKED_UP_AWAITING_DELIVERY",
            "IN_TRANSIT",
            "DELIVERED",
            "COMPLETED",
        ],
    ).order_by("-created_at")
    collection_history = CollectionLog.objects.all().order_by("-created_at")
    collection_search = request.GET.get("collection_search", "").strip()
    collection_method = request.GET.get("collection_method", "all")
    collection_filter_type = request.GET.get("collection_filter_type", "all")
    collection_target_date = request.GET.get("collection_target_date", "")

    if collection_search:
        collection_history = collection_history.filter(
            Q(receipt_number__icontains=collection_search)
            | Q(student_id__icontains=collection_search)
            | Q(student_name__icontains=collection_search)
            | Q(documents_included__icontains=collection_search)
        )

    if collection_method in ["CASH", "ONLINE"]:
        collection_history = collection_history.filter(payment_method=collection_method)

    if collection_target_date:
        try:
            date_obj = timezone.datetime.strptime(
                collection_target_date, "%Y-%m-%d"
            ).date()
            if collection_filter_type == "daily":
                collection_history = collection_history.filter(created_at__date=date_obj)
            elif collection_filter_type == "weekly":
                start = date_obj - timedelta(days=date_obj.weekday())
                collection_history = collection_history.filter(
                    created_at__date__range=[start, start + timedelta(days=6)]
                )
            elif collection_filter_type == "monthly":
                collection_history = collection_history.filter(
                    created_at__year=date_obj.year,
                    created_at__month=date_obj.month,
                )
            elif collection_filter_type == "yearly":
                collection_history = collection_history.filter(
                    created_at__year=date_obj.year
                )
        except ValueError:
            pass

    collection_history_count = collection_history.count()
    if request.method == "POST":
        action, req_id = request.POST.get("action"), request.POST.get("request_id")
        doc_req = get_object_or_404(DocumentRequest, id=req_id)

        if action == "confirm_payment":
            payable_batch = get_payment_scope_queryset(
                batch_id=doc_req.batch_id,
                delivery_method=doc_req.delivery_method,
                statuses=["PAYMENT_REQUIRED", "PENDING_CASHIER_APPROVAL"],
            )

            if doc_req.payment_reference:
                payable_batch = payable_batch.filter(
                    payment_reference=doc_req.payment_reference
                )

            # Identify if this was an online payment for the log
            was_online = any(
                item.status == "PENDING_CASHIER_APPROVAL" for item in payable_batch
            )

            new_no = SystemCounter.get_next_receipt_no()

            _, total = get_payment_summary(payable_batch)
            payable_ids = list(payable_batch.values_list("id", flat=True))

            # Update all items in the batch to PAID and attach the
            # student-facing tracking/reference number at payment time.
            payable_batch.update(status="PAID", receipt_number=new_no)
            ensure_batch_tracking_number(
                DocumentRequest.objects.filter(id__in=payable_ids)
            )

            CollectionLog.objects.create(
                receipt_number=new_no,
                student_id=doc_req.student.username,
                student_name=doc_req.get_student_name(),
                amount_paid=total,
                documents_included=", ".join(
                    [i.document_type.name for i in payable_batch]
                ),
                collected_by=request.user,
                # Set payment method dynamically
                payment_method="ONLINE" if was_online else "CASH",
            )

            log_audit(
                request.user,
                "UPDATE",
                "DocumentRequest",
                doc_req.batch_id,
                "Payment confirmed by Cashier.",
            )
            messages.success(
                request,
                "Payment verified and approved. You can now issue and finalize the summary.",
            )
            return redirect("cashier_dashboard")

        elif action == "issue_receipt":
            # Issue and finalize summary - make it visible to student
            batch = get_payment_scope_queryset(
                batch_id=doc_req.batch_id,
                delivery_method=doc_req.delivery_method,
                statuses=["PAID"],
            )

            # After cashier issues the summary, registrar takes over processing.
            for item in batch:
                item.status = "PROCESSING"
                item.save()

            log_audit(
                request.user,
                "UPDATE",
                "DocumentRequest",
                doc_req.batch_id,
                "Receipt issued and finalized by Cashier.",
            )
            messages.success(
                request,
                "Summary issued and finalized. The request is now in processing.",
            )

            return redirect("cashier_dashboard")
    return render(
        request,
        "cashier_dashboard.html",
        {
            "all_payments": all_payments,
            "history": history,
            "collection_history": collection_history,
            "collection_history_count": collection_history_count,
            "collection_filters": {
                "search": collection_search,
                "method": collection_method,
                "filter_type": collection_filter_type,
                "target_date": collection_target_date,
                "is_active": any(
                    [
                        collection_search,
                        collection_method != "all",
                        collection_filter_type != "all",
                        collection_target_date,
                        request.GET.get("show_collection_history"),
                    ]
                ),
            },
        },
    )


def courier_dashboard(request):
    pickup_queue = (
        DocumentRequest.objects.filter(
            is_deleted=False,
            delivery_method="LBC",
            status__in=["AWAITING_COURIER_PICKUP", "PROCESSING"],
        ).order_by("-created_at")
    )
    active_deliveries = (
        DocumentRequest.objects.filter(
            is_deleted=False,
            delivery_method="LBC",
            status__in=["PICKED_UP_AWAITING_DELIVERY", "IN_TRANSIT"],
        ).order_by("-created_at")
    )

    if request.method == "POST":
        action = request.POST.get("action")
        batch_id = (request.POST.get("batch_id") or "").strip()

        if action == "mark_picked_up" and batch_id:
            pickup_option = (request.POST.get("pickup_option") or "").strip()
            batch = DocumentRequest.objects.filter(
                batch_id=batch_id,
                is_deleted=False,
                delivery_method="LBC",
                status__in=["AWAITING_COURIER_PICKUP", "PROCESSING"],
            )

            if not batch.exists():
                messages.error(request, "No courier pickup batch found.")
                return redirect("courier_dashboard")

            if pickup_option not in dict(
                DocumentRequest.COURIER_PICKUP_OPTION_CHOICES
            ):
                messages.error(request, "Please choose a valid pickup option.")
                return redirect("courier_dashboard")
            batch_items = list(batch)
            tracking_number = normalize_tracking_number(
                batch_items[0].tracking_number or ensure_batch_tracking_number(batch_items)
            )

            batch.update(
                status="PICKED_UP_AWAITING_DELIVERY",
                courier_pickup_option=pickup_option,
            )

            pickup_label = dict(DocumentRequest.COURIER_PICKUP_OPTION_CHOICES)[
                pickup_option
            ]
            for item in batch_items:
                item.tracking_number = tracking_number
                create_notification(
                    item.student,
                    "Courier",
                    f"Your {item.document_type.name} has been picked up via {pickup_label} and is now awaiting delivery. Tracking: {tracking_number}.",
                )

            log_audit(
                request.user if request.user.is_authenticated else None,
                "UPDATE",
                "DocumentRequest",
                batch_id,
                "Courier marked batch as picked up. "
                f"Pickup option: {pickup_label}. Tracking: {tracking_number}.",
            )
            messages.success(
                request,
                f"Batch {batch_id} marked as picked up. Tracking: {tracking_number}.",
            )
            return redirect("courier_dashboard")

        if action == "mark_in_delivery" and batch_id:
            batch = DocumentRequest.objects.filter(
                batch_id=batch_id,
                is_deleted=False,
                delivery_method="LBC",
                status="PICKED_UP_AWAITING_DELIVERY",
            )

            if not batch.exists():
                messages.error(request, "No picked up LBC batch found.")
                return redirect("courier_dashboard")

            batch_items = list(batch)
            batch.update(status="IN_TRANSIT")

            for item in batch_items:
                create_notification(
                    item.student,
                    "Courier",
                    f"Your {item.document_type.name} is now in delivery. Tracking: {item.tracking_number}.",
                )

            log_audit(
                request.user if request.user.is_authenticated else None,
                "UPDATE",
                "DocumentRequest",
                batch_id,
                "Courier marked batch as IN TRANSIT.",
            )
            messages.success(
                request,
                f"Batch {batch_id} marked as in delivery.",
            )
            return redirect("courier_dashboard")

        if action == "mark_delivered" and batch_id:
            batch = DocumentRequest.objects.filter(
                batch_id=batch_id,
                is_deleted=False,
                delivery_method="LBC",
                status="IN_TRANSIT",
            )

            if not batch.exists():
                messages.error(request, "No active LBC delivery batch found.")
                return redirect("courier_dashboard")

            batch_items = list(batch)
            batch.update(status="DELIVERED")

            for item in batch_items:
                create_notification(
                    item.student,
                    "Courier",
                    f"Your {item.document_type.name} has been marked as delivered. Tracking: {item.tracking_number}.",
                )

            log_audit(
                request.user if request.user.is_authenticated else None,
                "UPDATE",
                "DocumentRequest",
                batch_id,
                "Courier marked batch as DELIVERED.",
            )
            messages.success(
                request,
                f"Batch {batch_id} marked as delivered.",
            )
            return redirect("courier_dashboard")

    return render(
        request,
        "courier_dashboard.html",
        {
            "pickup_queue": pickup_queue,
            "active_deliveries": active_deliveries,
            "pickup_option_choices": DocumentRequest.COURIER_PICKUP_OPTION_CHOICES,
        },
    )


@login_required
def system_tracking_page(request):
    tracking_number = normalize_tracking_number(
        request.GET.get("tracking_number") or request.GET.get("tracking") or ""
    )
    batch_items = []
    tracking_summary = None
    tracking_error = None

    if tracking_number:
        batch_items = list(
            DocumentRequest.objects.filter(
                student=request.user,
                is_deleted=False,
                delivery_method="LBC",
                tracking_number=tracking_number,
            )
            .select_related("document_type")
            .order_by("created_at")
        )

        if batch_items:
            current_status = batch_items[-1].status
            batch_sample = batch_items[0]
            tracking_summary = {
                "tracking_number": tracking_number,
                "status": current_status,
                "status_label": dict(DocumentRequest.STATUS_CHOICES).get(
                    current_status, current_status
                ),
                "display_status": next(
                    (
                        stage["label"]
                        for stage in get_tracking_stage_definitions()
                        if stage["key"] == current_status
                    ),
                    dict(DocumentRequest.STATUS_CHOICES).get(
                        current_status, current_status
                    ),
                ),
                "timeline": build_tracking_timeline(current_status),
                "batch_id": batch_sample.batch_id,
                "created_at": batch_sample.created_at,
                "pickup_option": batch_sample.get_courier_pickup_option_display()
                if batch_sample.courier_pickup_option
                else "",
                "receiver_name": " ".join(
                    part
                    for part in [
                        batch_sample.shipping_first_name or "",
                        batch_sample.shipping_last_name or "",
                    ]
                    if part
                ),
                "destination": ", ".join(
                    part
                    for part in [
                        batch_sample.shipping_floor or "",
                        batch_sample.shipping_street or "",
                        batch_sample.shipping_barangay or "",
                        batch_sample.shipping_city or "",
                        batch_sample.shipping_province or "",
                    ]
                    if part
                ),
                "documents": [item.document_type.name for item in batch_items],
            }
        else:
            tracking_error = (
                "No shipment was found for that tracking number in your account."
            )

    return render(
        request,
        "system_tracking_page.html",
        {
            "tracking_number": tracking_number,
            "tracking_summary": tracking_summary,
            "tracking_error": tracking_error,
        },
    )


# --- 7. PAYMENTS & MISC ---


@csrf_exempt
@api_view(["POST"])
def xendit_webhook(request):
    if request.headers.get("x-callback-token") != getattr(
        settings, "XENDIT_CALLBACK_TOKEN", None
    ):
        return Response(status=403)
    data = request.data
    ext_id, status = data.get("external_id"), data.get("status")
    batch_id, delivery_method = parse_xendit_external_id(ext_id)
    if status == "PAID" and batch_id:
        items = get_payment_scope_queryset(
            batch_id=batch_id,
            delivery_method=delivery_method,
            statuses=["APPROVED", "PAYMENT_REQUIRED"],
        )
        if items.exists():
            new_no = SystemCounter.get_next_receipt_no()
            first_item = items.first()

            _, total = get_payment_summary(items)
            item_ids = list(items.values_list("id", flat=True))

            items.update(status="PENDING_CASHIER_APPROVAL")
            ensure_batch_tracking_number(DocumentRequest.objects.filter(id__in=item_ids))
            CollectionLog.objects.create(
                receipt_number=new_no,
                student_id=first_item.student.username,
                student_name=first_item.get_student_name(),
                amount_paid=total,
                documents_included=", ".join([i.document_type.name for i in items]),
                payment_method="ONLINE",
            )
    return Response(status=200)


@csrf_exempt
def payment_success(request):
    # Clear pending invoice from session - payment is being processed here
    pending_invoice = request.session.pop("pending_xendit_invoice", None)
    try:
        if request.user.is_authenticated:
            # Prefer the specific batch that just returned from Xendit.
            pending_payments = DocumentRequest.objects.filter(
                student=request.user, is_deleted=False
            )
            if pending_invoice and pending_invoice.get("batch_id"):
                pending_payments = pending_payments.filter(
                    batch_id=pending_invoice["batch_id"]
                )
                delivery_method = normalize_payment_delivery_method(
                    pending_invoice.get("delivery_method")
                )
                if delivery_method:
                    pending_payments = pending_payments.filter(
                        delivery_method=delivery_method
                    )
            pending_payments = pending_payments.filter(
                status__in=["APPROVED", "PAYMENT_REQUIRED"]
            )
            if pending_payments.exists():
                pending_ids = list(pending_payments.values_list("id", flat=True))
                pending_payments.update(status="PENDING_CASHIER_APPROVAL")
                ensure_batch_tracking_number(
                    DocumentRequest.objects.filter(id__in=pending_ids)
                )
                messages.success(
                    request, "Payment Verified! Your documents are being processed."
                )
            else:
                messages.success(request, "Payment completed successfully!")
            return redirect("student_dashboard")

        # Session expired during Xendit redirect - use invoice_id to recover batch
        invoice_id = request.GET.get("id", "")
        if invoice_id:
            try:
                auth = base64.b64encode(
                    f"{settings.XENDIT_SECRET_KEY}:".encode()
                ).decode()
                xendit_res = requests.get(
                    f"https://api.xendit.co/v2/invoices/{invoice_id}",
                    headers={"Authorization": f"Basic {auth}"},
                    timeout=5,
                )
                if xendit_res.status_code == 200:
                    ext_id = xendit_res.json().get("external_id", "")
                    batch_id, delivery_method = parse_xendit_external_id(ext_id)
                    if batch_id:
                        payable_batch = get_payment_scope_queryset(
                            batch_id=batch_id,
                            delivery_method=delivery_method,
                            statuses=["APPROVED", "PAYMENT_REQUIRED"],
                        )
                        if payable_batch.exists():
                            payable_ids = list(payable_batch.values_list("id", flat=True))
                            payable_batch.update(status="PENDING_CASHIER_APPROVAL")
                            ensure_batch_tracking_number(
                                DocumentRequest.objects.filter(id__in=payable_ids)
                            )
            except Exception:
                pass  # Webhook will handle it as fallback
            messages.success(
                request,
                "Payment completed! Your documents are now visible in your dashboard.",
            )
            return redirect("student_dashboard")

    except Exception as e:
        print(f"Payment success error: {e}")

    # Default fallback
    return redirect("student_dashboard")


@login_required
@login_required
def generate_receipt(request, req_id):
    doc_req = get_object_or_404(DocumentRequest, id=req_id)
    is_staff = request.user.groups.filter(
        name__in=["Registrar", "Cashier", "Accounting"]
    ).exists()
    if not (doc_req.student == request.user or is_staff or request.user.is_superuser):
        raise PermissionDenied()
    batch = get_payment_scope_queryset(
        batch_id=doc_req.batch_id,
        delivery_method=doc_req.delivery_method,
        include_deleted=True,
    )
    student = StudentMasterList.objects.filter(
        student_id=doc_req.student.username
    ).first()
    batch_tracking_number = (
        batch.exclude(tracking_number__isnull=True)
        .exclude(tracking_number__exact="")
        .values_list("tracking_number", flat=True)
        .first()
    )
    if not batch_tracking_number and doc_req.delivery_method == "LBC":
        batch_tracking_number = ensure_batch_tracking_number(batch)

    summary_items, total_amount = get_payment_summary(batch)
    lbc_charges = get_batch_lbc_charges(batch)
    xendit_total_amount = get_xendit_paid_amount(batch)
    if xendit_total_amount is not None:
        total_amount = xendit_total_amount

    # Check if LBC delivery is selected
    is_lbc_delivery = doc_req.delivery_method == "LBC"
    receipt_tracking_id = batch_tracking_number

    return render(
        request,
        "receipt_invoice.html",
        {
            "doc": doc_req,
            "batch_items": batch,
            "summary_items": summary_items,
            "student": student,
            "today": timezone.now(),
            "total_amount": total_amount,
            "lbc_charges": lbc_charges,
            "batch_tracking_number": batch_tracking_number,
            "receipt_tracking_id": receipt_tracking_id,
            "trackingmore_tracking_url": build_trackingmore_page_url(
                batch_tracking_number
            ),
            "display_receipt_no": doc_req.receipt_number or "PENDING",
            "is_lbc_delivery": is_lbc_delivery,
        },
    )


def staff_login(request):
    if request.user.is_authenticated:
        django_logout(request)
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            user_groups = user.groups.values_list("name", flat=True)
            if (
                any(
                    role in user_groups
                    for role in ["Registrar", "Cashier", "Accounting", "TOR Desk", "Courier"]
                )
                or user.is_superuser
                or user.username == "Lotivio01"
            ):
                login(request, user)
                if "Registrar" in user_groups:
                    return redirect("registrar_dashboard")
                if "Cashier" in user_groups:
                    return redirect("cashier_dashboard")
                if "TOR Desk" in user_groups or user.username == "Lotivio01":
                    return redirect("tor_dashboard")
                if "Courier" in user_groups:
                    return redirect("courier_dashboard")
                return redirect("accounting_dashboard")
            else:
                messages.error(request, "Access denied.")
    return render(request, "staff_login.html", {"form": AuthenticationForm()})


def logout_view(request):
    is_staff = request.user.is_authenticated and (
        request.user.groups.filter(
            name__in=["Registrar", "Cashier", "Accounting", "TOR"]
        ).exists()
        or request.user.is_superuser
    )
    django_logout(request)
    return redirect("staff_login" if is_staff else "login")


@login_required
def mark_notifications_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({"status": "success"})


@role_required(allowed_roles=["Registrar", "Cashier", "Accounting"])
def signature_settings(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        profile.printed_name = request.POST.get("printed_name")
        if request.POST.get("signature_data"):
            profile.signature_data = request.POST.get("signature_data")
        profile.save()
        messages.success(request, "Updated.")
        return redirect("registrar_dashboard")
    return render(request, "signature_settings.html", {"profile": profile})


@api_view(["POST"])
def api_login_request(request):
    sid = request.data.get("student_id", "").strip().upper()
    otp_method = request.data.get("otp_method", "email")  # Default to email
    if cache.get(f"otp_api_lock_{sid}"):
        return Response({"status": "error", "message": "Wait 1 min."}, status=429)
    master_student = StudentMasterList.objects.filter(student_id=sid).first()
    if master_student:
        user, _ = User.objects.get_or_create(
            username=sid, defaults={"email": master_student.email}
        )

        # Get or create OTP token with Google Authenticator support
        otp = OTPToken.objects.filter(user=user).first()
        if not otp:
            otp = OTPToken.objects.create(user=user)
        otp.generate_code()

        # Get Google Authenticator provisioning URI
        google_auth_uri = otp.get_google_auth_uri()

        # Send OTP via chosen method
        try:
            if otp_method == "email":
                # Send email with OTP and Google Auth info
                email_message = f"""
Your CATC Portal Login Code: {otp.otp_code}

This code is valid for 10 minutes.

To use Google Authenticator:
1. Download Google Authenticator app on your phone
2. The secret key for setup is: {otp.google_auth_secret}

Or scan this QR code in the Google Authenticator app.
"""
                send_mail(
                    "Login OTP",
                    email_message,
                    settings.DEFAULT_FROM_EMAIL,
                    [master_student.email],
                )
                print(f"[API EMAIL] OTP sent to {master_student.email}")
            elif otp_method in ["httpsms", "iprog"]:
                # Send SMS with OTP via specified provider
                send_otp_sms(
                    master_student.phone_number, otp.otp_code, provider=otp_method
                )
                print(
                    f"[API SMS] OTP sent via {otp_method} to {master_student.phone_number}"
                )
        except Exception as e:
            print(f"API OTP sending failed: {e}")

        cache.set(f"otp_api_lock_{sid}", True, 60)
        return Response(
            {
                "status": "success",
                "masked_email": master_student.masked_email,
                "masked_phone": master_student.masked_phone,
                "google_auth_secret": otp.google_auth_secret,
            }
        )
    return Response(status=404)


@api_view(["POST"])
def api_verify_otp(request):
    sid, code = request.data.get("student_id", "").upper(), request.data.get("otp_code")
    user = get_object_or_404(User, username=sid)
    threshold = timezone.now() - timedelta(minutes=10)
    otp = OTPToken.objects.filter(
        user=user, is_verified=False, created_at__gte=threshold
    ).last()

    if otp:
        # Check if user is entering a Google Authenticator code
        if otp.google_auth_enabled and otp.google_auth_secret:
            try:
                import pyotp

                totp = pyotp.TOTP(otp.google_auth_secret)
                if totp.verify(code):
                    otp.is_verified = True
                    otp.save()
                    return Response(
                        {
                            "status": "success",
                            "access": str(RefreshToken.for_user(user).access_token),
                        }
                    )
            except ImportError:
                pass

        # Fall back to regular OTP code
        if otp.otp_code == code:
            otp.is_verified = True
            otp.save()
            return Response(
                {
                    "status": "success",
                    "access": str(RefreshToken.for_user(user).access_token),
                }
            )

    return Response({"status": "error", "message": "Expired/Invalid."}, status=400)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def api_student_dashboard(request):
    return Response(
        RequestSerializer(
            DocumentRequest.objects.filter(
                student=request.user, is_deleted=False
            ).order_by("-created_at"),
            many=True,
        ).data
    )


# Import at module level for performance
import urllib.request
import urllib.error
import logging

logger = logging.getLogger(__name__)


def _get_tracking_data(tracking_num):
    """
    Fetch tracking data from TrackingMore API.
    Returns tuple: (success: bool, data: dict, error: str or None)
    """
    try:
        from requests_app.tracking_service import LBCTracker

        tracker = LBCTracker()
        result = tracker.get_status(tracking_num)

        if result.get("meta", {}).get("code") == 200:
            data = result.get("data", {})

            # Transform TrackingMore format to our format
            tracking_details = data.get("tracking_details", [])
            timeline = []
            for detail in tracking_details:
                timeline.append(
                    {
                        "dateTime": detail.get("datetime", ""),
                        "location": detail.get("location", ""),
                        "status": detail.get("status", detail.get("description", "")),
                    }
                )

            return (
                True,
                {
                    "trackingNumber": tracking_num,
                    "status": data.get("delivery_status", "UNKNOWN"),
                    "origin": data.get("origin", ""),
                    "destination": data.get("destination", ""),
                    "substatus": data.get("substatus", ""),
                    "lastEvent": data.get("last_event", ""),
                    "transitTime": data.get("transit_time", 0),
                    "timeline": timeline,
                },
                None,
            )
        else:
            error_msg = result.get("meta", {}).get("message", "Unknown error")
            logger.warning(f"TrackingMore API error: {error_msg}")
            return (False, None, error_msg)

    except Exception as e:
        logger.error(f"Unexpected error fetching tracking: {e}")
        return (False, None, str(e))


def _save_tracking_notification(user, tracking_num, tracking_data):
    """
    Helper function to save tracking result as notification.
    Returns: (success: bool, error: str or None)
    """
    try:
        status = tracking_data.get("status", "Unknown") if tracking_data else "Unknown"
        location = (
            tracking_data.get("destination", "Unknown") if tracking_data else "Unknown"
        )

        message = f"📦 Shipment Tracking Update\n"
        message += f"Tracking #: {tracking_num}\n"
        message += f"Status: {status}\n"
        message += f"Destination: {location}"

        Notification.objects.create(user=user, sender_role="System", message=message)
        logger.info(f"Tracking notification saved for user {user.id}: {tracking_num}")
        return (True, None)
    except Exception as e:
        logger.error(f"Failed to save tracking notification: {e}")
        return (False, str(e))


# LBC Tracking API View
@api_view(["GET"])
@login_required
def track_lbc_shipment(request, tracking_num):
    """
    Track LBC shipment using the LBC API.
    Returns tracking data in consistent format.
    """
    # Validate input
    if not tracking_num or len(tracking_num.strip()) == 0:
        return JsonResponse(
            {"success": False, "error": "Tracking number is required"}, status=400
        )

    tracking_num = tracking_num.strip()

    # Try to get real tracking data
    success, data, error = _get_tracking_data(tracking_num)

    if success and data:
        return JsonResponse(
            {
                "success": True,
                "data": data,
                "trackingmore_url": build_trackingmore_page_url(tracking_num),
            }
        )

    return JsonResponse(
        {
            "success": False,
            "error": error or "TrackingMore could not find this shipment yet.",
            "trackingmore_url": build_trackingmore_page_url(tracking_num),
        },
        status=404,
    )


@api_view(["POST"])
@login_required
def track_and_notify(request, tracking_num):
    """
    Track LBC shipment and save notification.
    Combines tracking + notification in one call.
    """
    if not tracking_num or len(tracking_num.strip()) == 0:
        return JsonResponse(
            {"success": False, "error": "Tracking number is required"}, status=400
        )

    tracking_num = tracking_num.strip()

    # Get tracking data
    success, data, error = _get_tracking_data(tracking_num)
    if not success or not data:
        return JsonResponse(
            {
                "success": False,
                "error": error or "TrackingMore could not find this shipment yet.",
                "trackingmore_url": build_trackingmore_page_url(tracking_num),
            },
            status=404,
        )

    tracking_data = data

    # Save notification
    notif_success, notif_error = _save_tracking_notification(
        request.user, tracking_num, tracking_data
    )

    if not notif_success:
        logger.warning(f"Failed to save notification: {notif_error}")

    return JsonResponse(
        {"success": True, "data": tracking_data, "notification_saved": notif_success}
    )


@login_required
def mark_as_delivered(request):
    """
    Mark a document request as delivered when tracking shows package arrived.
    """
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "error": "Only POST allowed"}, status=405
        )

    try:
        data = json.loads(request.body)
        tracking_number = data.get("tracking_number", "").strip()
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    if not tracking_number:
        return JsonResponse(
            {"success": False, "error": "Tracking number required"}, status=400
        )

    # Find the document request with this tracking number
    doc_requests = DocumentRequest.objects.filter(
        tracking_number=tracking_number, student=request.user
    )

    if not doc_requests.exists():
        return JsonResponse(
            {"success": False, "error": "No request found with this tracking number"},
            status=404,
        )

    # Update status to DELIVERED
    updated_count = doc_requests.update(status="DELIVERED")

    # Create notification
    create_notification(
        request.user,
        "System",
        f"Your document request has been marked as DELIVERED. Tracking: {tracking_number}",
    )

    return JsonResponse({"success": True, "updated": updated_count})


@csrf_exempt
def trackingmore_webhook(request):
    """
    Webhook endpoint for TrackingMore to push delivery status updates.
    When TrackingMore status changes, this automatically updates the request status.
    """
    if request.method != "POST":
        return JsonResponse(
            {"meta": {"code": 405, "message": "Method not allowed"}}, status=405
        )

    try:
        data = json.loads(request.body)
        logger.info(f"TrackingMore webhook received: {json.dumps(data)}")

        # Extract tracking data
        tracking_data = data.get("data", {})
        if isinstance(tracking_data, list):
            tracking_data = tracking_data[0] if tracking_data else {}
        tracking_number = tracking_data.get("tracking_number", "").strip()
        delivery_status = tracking_data.get("delivery_status", "").lower()
        substatus = tracking_data.get("substatus", "").lower()
        latest_event = tracking_data.get("latest_event") or tracking_data.get(
            "status_info", ""
        )
        last_updated = tracking_data.get("update_at") or tracking_data.get(
            "latest_checkpoint_time", ""
        )

        if not tracking_number:
            return JsonResponse(
                {"meta": {"code": 400, "message": "Tracking number missing"}},
                status=400,
            )

        logger.info(
            f"TrackingMore webhook: {tracking_number} status = {delivery_status}"
        )

        # Get the mapped status
        new_status = map_trackingmore_status(delivery_status, substatus)
        logger.info(f"Mapped status: {delivery_status}/{substatus} -> {new_status}")

        # Find all document requests with this tracking number (LBC delivery only)
        doc_requests = DocumentRequest.objects.filter(
            tracking_number=tracking_number, delivery_method="LBC"
        )

        logger.info(
            f"Found {doc_requests.count()} requests for tracking number: {tracking_number}"
        )

        if doc_requests.exists():
            updated_count = 0
            for req in doc_requests:
                # Only update if status actually changed
                if req.status != new_status:
                    req.status = new_status
                    req.save()
                    updated_count += 1

                    logger.info(
                        f"Updated request {req.id}: {tracking_number} status → {new_status}"
                    )

                    # Send notification for status changes
                    status_messages = {
                        "AWAITING_COURIER_PICKUP": f"Your document shipment is now awaiting LBC courier pickup. Tracking: {tracking_number}",
                        "PICKED_UP_AWAITING_DELIVERY": f"Your document shipment has been picked up and is now awaiting delivery scheduling. Tracking: {tracking_number}",
                        "IN_TRANSIT": f"Your document is already in transit with LBC. Tracking: {tracking_number}",
                        "DELIVERED": f"Your document has been DELIVERED by LBC. Tracking: {tracking_number}",
                    }

                    if new_status in status_messages:
                        extra_details = ""
                        if latest_event:
                            extra_details += f" Latest update: {latest_event}."
                        if last_updated:
                            extra_details += f" Updated: {last_updated}."
                        create_notification(
                            req.student,
                            "System",
                            f"{status_messages[new_status]}{extra_details}",
                        )

            logger.info(
                f"Total updated: {updated_count} requests for tracking {tracking_number}"
            )
            return JsonResponse(
                {
                    "meta": {
                        "code": 200,
                        "message": f"Updated {updated_count} requests to {new_status}",
                    }
                }
            )
        else:
            logger.info(f"No LBC requests found for tracking {tracking_number}")
            return JsonResponse(
                {"meta": {"code": 200, "message": "No matching requests"}}
            )

    except json.JSONDecodeError:
        logger.error("TrackingMore webhook: Invalid JSON received")
        return JsonResponse(
            {"meta": {"code": 400, "message": "Invalid JSON"}}, status=400
        )
    except Exception as e:
        logger.error(f"TrackingMore webhook error: {e}")
        return JsonResponse(
            {"meta": {"code": 500, "message": "Internal error"}}, status=500
        )


# TOR Page Counting Dashboard for Mr. Lotivio
@login_required
def tor_dashboard(request):
    # Check if user is authorized (Mr. Lotivio or admin)
    if not (
        request.user.username == "Lotivio01"
        or request.user.is_superuser
        or request.user.is_staff
    ):
        raise PermissionDenied()

    # Get ALL processed TOR/Transcript requests
    tor_requests = (
        DocumentRequest.objects.filter(
            (
                Q(document_type__name__icontains="TOR")
                | Q(document_type__name__icontains="TRANSCRIPT")
            ),
            tor_page_count__isnull=False,
            is_deleted=False,
        )
        .exclude(document_type__name__icontains="Authentication")
        .select_related("document_type", "student")
        .order_by("-created_at")[:50]
    )  # Last 50 processed

    # Also get TOR/Transcript requests that are PENDING_TOR_COUNT (new requests waiting for page count)
    # EXCLUDE Authentication documents - they will be bundled with their parent TOR/Transcript request
    processing_tor = (
        DocumentRequest.objects.filter(
            (
                Q(document_type__name__icontains="TOR")
                | Q(document_type__name__icontains="TRANSCRIPT")
            ),
            status="PENDING_TOR_COUNT",
            is_deleted=False,
        )
        .exclude(document_type__name__icontains="Authentication")
        .select_related("document_type", "student")
        .order_by("created_at")
    )

    # Also get TRANSCRIPT requests in PENDING_TOR_COUNT status
    # EXCLUDE Authentication documents
    transcript_requests = (
        DocumentRequest.objects.filter(
            document_type__name__icontains="TRANSCRIPT",
            status="PENDING_TOR_COUNT",
            is_deleted=False,
        )
        .exclude(document_type__name__icontains="Authentication")
        .select_related("document_type", "student")
        .order_by("-created_at")
    )

    # Combine both
    processing_tor = processing_tor | transcript_requests

    # Calculate pricing info - Use model's get_price() method for accurate calculation
    TOR_PRICE_PER_PAGE = 100
    RUSH_MULTIPLIER = 2

    # Pre-calculate prices for tor_requests (history)
    for tor in tor_requests:
        # Use the model's get_price() method which handles all cases correctly
        tor.calculated_price = tor.get_price()
        # Check if this batch has Authentication
        if tor.batch_id:
            batch_items = DocumentRequest.objects.filter(
                batch_id=tor.batch_id, is_deleted=False
            )
            tor.batch_count = batch_items.count()
            tor.has_auth = any(
                "Authentication" in str(item.document_type.name)
                for item in batch_items
                if item.id != tor.id
            )
        else:
            tor.batch_count = 1
            tor.has_auth = False

    # For processing_tor, also check for batched Authentication
    for tor in processing_tor:
        if tor.batch_id:
            batch_items = DocumentRequest.objects.filter(
                batch_id=tor.batch_id, is_deleted=False
            )
            tor.batch_count = batch_items.count()
            # Check if there's an Authentication request in the same batch
            auth_items = [
                item
                for item in batch_items
                if "Authentication" in str(item.document_type.name)
            ]
            if auth_items:
                tor.has_auth = True
                auth_item = auth_items[0]
                tor.auth_price = (
                    auth_item.get_base_price() if auth_item.document_type.price else 0
                )
                if auth_item.rush_processing:
                    tor.auth_price = tor.auth_price * 2
            else:
                tor.has_auth = False
                tor.auth_price = 0
        else:
            tor.batch_count = 1
            tor.has_auth = False
            tor.auth_price = 0

    context = {
        "tor_requests": tor_requests,
        "processing_tor": processing_tor,
        "tor_price_per_page": TOR_PRICE_PER_PAGE,
        "rush_multiplier": RUSH_MULTIPLIER,
    }

    return render(request, "tor_dashboard.html", context)


@login_required
def submit_tor_page_count(request):
    """
    Handle page count submission from Mr. Lotivio
    """
    if not (
        request.user.username == "Lotivio01"
        or request.user.is_superuser
        or request.user.is_staff
    ):
        return JsonResponse({"success": False, "error": "Unauthorized"}, status=403)

    if request.method == "POST":
        request_id = request.POST.get("request_id")
        page_count = request.POST.get("page_count")

        try:
            doc_request = DocumentRequest.objects.get(id=request_id)
            doc_request.tor_page_count = int(page_count)

            # Calculate UNRUSHED base price for storage
            TOR_PRICE_PER_PAGE = 100
            tor_base_price = doc_request.tor_page_count * TOR_PRICE_PER_PAGE
            tor_price = (
                tor_base_price * 2 if doc_request.rush_processing else tor_base_price
            )

            # Store ONLY the base price (no rush multiplier applied yet)
            doc_request.tor_price_override = tor_base_price
            doc_request.save()

            # Check if student has any previous COMPLETED/READY TOR/Transcript requests
            # This checks DocumentRequest directly, not TORRequestHistory which is only created after mark_done
            has_previous_tor = (
                DocumentRequest.objects.filter(
                    Q(
                        student=doc_request.student,
                        status__in=["COMPLETED", "READY"],
                        is_deleted=False,
                        document_type__name__icontains="TOR",
                    )
                    | Q(
                        student=doc_request.student,
                        status__in=["COMPLETED", "READY"],
                        is_deleted=False,
                        document_type__name__icontains="TRANSCRIPT",
                    )
                )
                .exclude(id=doc_request.id)
                .exists()
            )

            # Check if this is a FREE TOR request (only free on first TOR/Transcript request)
            is_free_tor = not has_previous_tor

            # Check if there's a batch with other requests
            if doc_request.batch_id:
                batch_items = DocumentRequest.objects.filter(
                    batch_id=doc_request.batch_id, is_deleted=False
                )
                scope_items = batch_items.filter(
                    delivery_method=doc_request.delivery_method
                )
                has_lbc_delivery = scope_items.filter(delivery_method="LBC").exists()
                total_price = (
                    tor_price  # Start with TOR price, including rush if applicable
                )

                # Add other items' price if exists (Authentication, etc.)
                for item in scope_items:
                    if item.id != doc_request.id:
                        # For Authentication or other paid items - use base price (no rush multiplier)
                        # Only the main document (TOR/Transcript/Diploma) gets rush multiplier
                        if "Authentication" in str(item.document_type.name):
                            item_price = item.get_base_price()
                            total_price += item_price
                        # Return companion items to the student as payable too so the dashboard
                        # consistently exposes BOOK SHIPPING / PAY for the whole batch.
                        if item.status != "PAYMENT_REQUIRED":
                            item.status = "PAYMENT_REQUIRED"
                            item.save()

                # If this is a FREE TOR and there are other paid items in batch,
                # keep the batch as APPROVED so student can pay for other items
                # If this is FREE TOR and it's the ONLY item in batch, mark as PROCESSING directly
                if is_free_tor and scope_items.count() == 1 and not has_lbc_delivery:
                    # This is a FREE TOR request - no payment needed
                    doc_request.tor_price_override = 0
                    doc_request.status = "PROCESSING"  # Changed from PAID to PROCESSING to avoid showing "PAYMENT RECEIVED" before actual processing
                    doc_request.save()

                    # Create notification for student
                    if has_previous_tor:
                        # This shouldn't happen since we set is_free_tor based on history, but just in case
                        message = f"Your TOR request ({doc_request.document_type.name}) has been processed. {page_count} pages. Total: ₱{tor_price}. Please proceed to payment."
                    else:
                        message = f"Your TOR request ({doc_request.document_type.name}) has been processed. {page_count} pages. Your first TOR request is FREE! Your document is now being processed."

                    Notification.objects.create(
                        user=doc_request.student,
                        sender_role="TOR Desk",
                        message=message,
                    )

                    # Log the action
                    log_audit(
                        request.user,
                        "UPDATE",
                        "DocumentRequest",
                        str(doc_request.id),
                        f"TOR page count set to {page_count}. FREE request - marked as PROCESSING.",
                    )

                    return JsonResponse(
                        {
                            "success": True,
                            "message": f"Page count submitted. FREE TOR - marked as PROCESSING.",
                        }
                    )
                else:
                    # Regular paid TOR or free TOR with pending LBC shipping charges
                    doc_request.tor_price_override = 0 if is_free_tor else total_price
                    doc_request.status = "PAYMENT_REQUIRED"
                    doc_request.save()

                    # Create notification for student
                    if has_lbc_delivery:
                        tor_message = (
                            f"Your TOR request ({doc_request.document_type.name}) has been page-counted at {page_count} pages. "
                            "Please complete your LBC shipping information so the system can compute shipping and valuation fees before payment."
                        )
                    elif is_free_tor:
                        tor_message = (
                            f"Your TOR request ({doc_request.document_type.name}) has been page-counted at {page_count} pages. "
                            "This TOR is free, but the batch still has charges that must be settled before processing."
                        )
                    else:
                        tor_message = f"Your TOR request ({doc_request.document_type.name}) has been processed. {page_count} pages. Total: ₱{tor_price}. Please proceed to payment."

                    Notification.objects.create(
                        user=doc_request.student,
                        sender_role="TOR Desk",
                        message=tor_message,
                    )

                    # Log the action
                    log_audit(
                        request.user,
                        "UPDATE",
                        "DocumentRequest",
                        str(doc_request.id),
                        f"TOR page count set to {page_count}. Returned to student for payment/shipping.",
                    )

                    return JsonResponse(
                        {
                            "success": True,
                            "message": "Page count submitted and returned to student.",
                        }
                    )
            else:
                # No batch - single TOR request
                if is_free_tor and doc_request.delivery_method != "LBC":
                    doc_request.tor_price_override = 0
                    doc_request.status = "PROCESSING"
                    doc_request.save()

                    # Create notification for student
                    Notification.objects.create(
                        user=doc_request.student,
                        sender_role="TOR Desk",
                        message=f"Your TOR request ({doc_request.document_type.name}) has been processed. {page_count} pages. Your first TOR request as a graduate is FREE! Please wait for it to be ready.",
                    )

                    log_audit(
                        request.user,
                        "UPDATE",
                        "DocumentRequest",
                        str(doc_request.id),
                        f"TOR page count set to {page_count}. FREE request - marked as PROCESSING.",
                    )

                    return JsonResponse(
                        {
                            "success": True,
                            "message": f"Page count submitted. FREE TOR - marked as PROCESSING.",
                        }
                    )
                else:
                    total_price = tor_price
                    doc_request.tor_price_override = 0 if is_free_tor else total_price
                    doc_request.status = "PAYMENT_REQUIRED"
                    doc_request.save()

                    # Create notification for student
                    if doc_request.delivery_method == "LBC":
                        single_tor_message = (
                            f"Your TOR request ({doc_request.document_type.name}) has been page-counted at {page_count} pages. "
                            "Please complete your LBC shipping information so the system can compute shipping and valuation fees before payment."
                        )
                    else:
                        single_tor_message = f"Your TOR request ({doc_request.document_type.name}) has been processed. {page_count} pages. Total: ₱{tor_price}. Please proceed to payment."

                    Notification.objects.create(
                        user=doc_request.student,
                        sender_role="TOR Desk",
                        message=single_tor_message,
                    )

                    # Log the action
                    log_audit(
                        request.user,
                        "UPDATE",
                        "DocumentRequest",
                        str(doc_request.id),
                        f"TOR page count set to {page_count}. Returned to student for payment.",
                    )

                    return JsonResponse(
                        {
                            "success": True,
                            "message": f"Page count submitted. Price: ₱{tor_price}",
                        }
                    )

        except DocumentRequest.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": "Request not found"}, status=404
            )
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)

    return JsonResponse({"success": False, "error": "Invalid request"}, status=400)


@login_required
@role_required(allowed_roles=["Student"])
def pay_with_xendit(request, batch_id, delivery_method=None):
    batch = get_payment_scope_queryset(
        batch_id=batch_id,
        delivery_method=delivery_method,
    )
    payable_batch = get_payment_scope_queryset(
        batch_id=batch_id,
        delivery_method=delivery_method,
        statuses=["APPROVED", "PAYMENT_REQUIRED", "PROCESSING"],
    )
    if not payable_batch.exists():
        # Debug: check what status the batch has
        existing = get_payment_scope_queryset(
            batch_id=batch_id,
            delivery_method=delivery_method,
        ).first()
        if existing:
            print(f"DEBUG: Batch {batch_id} exists but status is {existing.status}")
            # Check if already PAID (e.g., FREE TOR requests)
            if existing.status == "PAID":
                messages.info(request, "This request has already been processed.")
        else:
            print(f"DEBUG: Batch {batch_id} does not exist")
        return redirect("student_dashboard")

    _, total = get_payment_summary(payable_batch)

    # Handle FREE requests (total = 0)
    if total <= 0:
        # Mark as PAID directly without going through Xendit
        payable_batch.update(status="PAID")
        ensure_batch_tracking_number(batch)
        # Create notifications for all items
        for item in batch:
            Notification.objects.create(
                user=item.student,
                sender_role="System",
                message=f"Your {item.document_type.name} request has been confirmed at no cost.",
            )
        messages.success(
            request, "Your request has been confirmed! No payment required."
        )
        return redirect("student_dashboard")

    normalized_method = normalize_payment_delivery_method(delivery_method)
    auth = base64.b64encode(f"{settings.XENDIT_SECRET_KEY}:".encode()).decode()
    data = {
        "external_id": build_xendit_external_id(batch_id, normalized_method),
        "amount": float(total),
        "description": (
            f"Payment Batch {batch_id}"
            + (f" - {normalized_method}" if normalized_method else "")
        ),
        "payer_email": request.user.email,
        "success_redirect_url": settings.XENDIT_REDIRECT_URL,
        "currency": "PHP",
        "payment_methods": ["GCASH", "PAYMAYA", "CARD"],
    }
    try:
        res = requests.post(
            "https://api.xendit.co/v2/invoices",
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/json",
            },
            data=json.dumps(data),
            timeout=10,
        )
        if res.status_code in [200, 201]:
            invoice_data = res.json()
            payable_batch.update(payment_reference=invoice_data.get("id"))
            # Store invoice info in session so dashboard can verify payment on return
            request.session["pending_xendit_invoice"] = {
                "invoice_id": invoice_data.get("id"),
                "batch_id": batch_id,
                "delivery_method": normalized_method,
            }
            return redirect(invoice_data.get("invoice_url"))
        # Handle non-success response from Xendit
        messages.error(request, f"Payment processing failed. Status: {res.status_code}")
    except requests.exceptions.Timeout:
        messages.error(request, "Payment request timed out. Please try again.")
    except Exception as e:
        messages.error(request, f"Xendit connection failed: {str(e)}")
    return redirect("student_dashboard")


@api_view(["GET"])
@permission_classes([AllowAny])
def get_document_types(request):
    docs = DocumentType.objects.all().values("id", "name", "price")
    return Response(list(docs))
