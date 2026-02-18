import uuid
import requests, json, base64
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
from django.http import JsonResponse
from django.db.models import Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .serializers import RequestSerializer, DocumentTypeSerializer

# Import the Tracking Service
from .tracking_service import LBCTracker

from .models import (
    DocumentRequest, StudentMasterList, OTPToken, 
    DocumentType, StudentBalance, Notification, SystemCounter,
    CollectionLog, Profile
)
from .forms import StudentRequestForm, StudentIDLoginForm, OTPVerifyForm
from .decorators import role_required

# --- HELPERS ---

def send_otp_sms(phone_number, otp_code):
    """Sends the OTP code via Semaphore API."""
    if not settings.SEMAPHORE_API_KEY or settings.SEMAPHORE_API_KEY == 'YOUR_API_KEY_HERE':
        print(f"SMS Mock: To {phone_number} -> Code: {otp_code} (API Key missing)")
        return False

    url = "https://api.semaphore.co/api/v4/messages"
    message = f"Your CATC Portal OTP is: {otp_code}. Valid for 5 minutes. Do not share this code."
    
    data = {
        'apikey': settings.SEMAPHORE_API_KEY,
        'number': phone_number,
        'message': message,
        'sendername': settings.SEMAPHORE_SENDER_NAME
    }

    try:
        response = requests.post(url, data=data)
        return response.status_code == 200
    except Exception as e:
        print(f"SMS Error: {e}")
        return False

def create_notification(user, role, message):
    Notification.objects.create(user=user, sender_role=role, message=message)

# --- STUDENT LOGIN FLOW ---

def login_view(request):
    # PREVENT SESSION CONFLICT: Logout existing staff if any
    if request.user.is_authenticated:
        django_logout(request)

    if request.method == 'POST':
        form = StudentIDLoginForm(request.POST)
        if form.is_valid():
            sid = form.cleaned_data['student_id'].upper()
            master_student = StudentMasterList.objects.filter(student_id=sid).first()
            if master_student:
                user, created = User.objects.get_or_create(username=sid, defaults={'email': master_student.email})
                
                if created:
                    group, _ = Group.objects.get_or_create(name='Student')
                    user.groups.add(group)
                
                otp_obj = OTPToken.objects.create(user=user)
                otp_obj.generate_code()

                try:
                    send_mail('Login OTP', f'Code: {otp_obj.otp_code}', settings.DEFAULT_FROM_EMAIL, [master_student.email])
                except: pass 

                sms_sent = send_otp_sms(master_student.phone_number, otp_obj.otp_code)
                
                if sms_sent:
                    messages.success(request, f"OTP sent to your phone (*******{master_student.phone_number[-3:]}) and email.")
                else:
                    messages.warning(request, "SMS server busy. Please check your email for the OTP.")

                request.session['otp_user_id'] = user.id
                return redirect('verify_otp')
            else:
                messages.error(request, "Student ID not found.")
    else: 
        form = StudentIDLoginForm()
    return render(request, 'login_id.html', {'form': form})

def verify_otp(request):
    user_id = request.session.get('otp_user_id')
    if not user_id: return redirect('login')
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        form = OTPVerifyForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['otp_code']
            otp_record = OTPToken.objects.filter(user=user, otp_code=code, is_verified=False).last()
            if otp_record:
                otp_record.is_verified = True
                otp_record.save()
                login(request, user)
                del request.session['otp_user_id']
                return redirect('student_dashboard')
            else: messages.error(request, "Invalid OTP.")
    else: form = OTPVerifyForm()
    return render(request, 'login_otp.html', {'form': form, 'email': user.email})

def staff_login(request):
    # PREVENT SESSION CONFLICT: Logout existing student if any
    if request.user.is_authenticated:
        django_logout(request)

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            user_groups = user.groups.values_list('name', flat=True)
            if any(role in user_groups for role in ['Registrar', 'Cashier', 'Accounting']):
                login(request, user)
                if 'Registrar' in user_groups: return redirect('registrar_dashboard')
                if 'Cashier' in user_groups: return redirect('cashier_dashboard')
                if 'Accounting' in user_groups: return redirect('accounting_dashboard')
            else: messages.error(request, "Access denied.")
    else: form = AuthenticationForm()
    return render(request, 'staff_login.html', {'form': form})

# --- STUDENT DASHBOARD ---

@role_required(allowed_roles=['Student'])
def student_dashboard(request):
    student_info = StudentMasterList.objects.filter(student_id=request.user.username).first()
    balance_record = StudentBalance.objects.filter(student__student_id=request.user.username).first()
    
    has_balance = balance_record.outstanding_amount > 0 if balance_record else False
    balance_amount = balance_record.outstanding_amount if balance_record else 0
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:10]
    user_requests = DocumentRequest.objects.filter(student=request.user).order_by('-created_at')

    all_docs = DocumentType.objects.all()
    base_docs = all_docs.exclude(name__startswith="Authentication")
    auth_docs = all_docs.filter(name__startswith="Authentication")

    grouped_docs = []
    for base in base_docs:
        auth_match = auth_docs.filter(name__icontains=base.name).first()
        is_restricted_doc = any(key in base.name.upper() for key in ["TOR", "TRANSCRIPT", "DIPLOMA", "CLEARANCE"])
        
        grouped_docs.append({
            'id': base.id,
            'name': base.name,
            'price': base.price,
            'has_auth': bool(auth_match),
            'auth_id': auth_match.id if auth_match else None,
            'auth_price': auth_match.price if auth_match else 0,
            'is_blocked': (is_restricted_doc and has_balance) 
        })

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'delete_request':
            req_id = request.POST.get('request_id')
            DocumentRequest.objects.filter(
                id=req_id, 
                student=request.user, 
                status__in=['PENDING', 'COMPLETED', 'REJECTED']
            ).delete()
            messages.success(request, "Record removed from your history.")
            return redirect('student_dashboard')

        if action == 'submit_request':
            reason = request.POST.get('reason')
            batch_id = str(uuid.uuid4())[:8]
            requested_count = 0

            for base in base_docs:
                selection = request.POST.get(f'selection_{base.id}')
                delivery = request.POST.get(f'delivery_{base.id}', 'PICKUP')
                
                if not selection or selection == 'none': continue

                auth_match = auth_docs.filter(name__icontains=base.name).first()

                if selection == 'doc':
                    DocumentRequest.objects.create(student=request.user, document_type=base, reason=reason, batch_id=batch_id, delivery_method=delivery)
                    requested_count += 1
                elif selection == 'auth' and auth_match:
                    DocumentRequest.objects.create(student=request.user, document_type=auth_match, reason=reason, batch_id=batch_id, delivery_method=delivery)
                    requested_count += 1
                elif selection == 'both' and auth_match:
                    DocumentRequest.objects.create(student=request.user, document_type=base, reason=reason, batch_id=batch_id, delivery_method=delivery)
                    DocumentRequest.objects.create(student=request.user, document_type=auth_match, reason=reason, batch_id=batch_id, delivery_method=delivery)
                    requested_count += 2

            if requested_count > 0:
                messages.success(request, f"Successfully submitted {requested_count} requests.")
            return redirect('student_dashboard')

    return render(request, 'dashboard.html', {
        'grouped_docs': grouped_docs, 
        'requests': user_requests, 
        'student': student_info,
        'notifications': notifications, 
        'unread_count': unread_count, 
        'has_balance': has_balance, 
        'balance_amount': balance_amount,
    })

# --- REGISTRAR DASHBOARD ---

@role_required(allowed_roles=['Registrar'])
def registrar_dashboard(request):
    active_requests = DocumentRequest.objects.exclude(status__in=['COMPLETED', 'REJECTED']).order_by('-created_at')
    history = DocumentRequest.objects.filter(status__in=['COMPLETED', 'REJECTED']).order_by('-created_at')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        batch_id = request.POST.get('batch_id')
        req_id = request.POST.get('request_id')

        if batch_id:
            batch_items = DocumentRequest.objects.filter(batch_id=batch_id)
            if batch_items.exists():
                if action == 'approve':
                    batch_items.update(status='PAYMENT_REQUIRED')
                    messages.success(request, f"Batch {batch_id} approved for payment.")
                elif action == 'reject':
                    batch_items.update(status='REJECTED')
                    for item in batch_items:
                        create_notification(item.student, 'Registrar', f"Your request for {item.document_type.name} was rejected. Please contact the office.")
                
                elif action == 'mark_ready':
                    # LBC INTEGRATION START
                    tracking_no = request.POST.get('tracking_number_input')
                    tracker = LBCTracker()
                    
                    batch_items.filter(status__in=['PAID', 'PROCESSING']).update(status='READY')
                    
                    for item in batch_items:
                        method_label = "pickup"
                        if item.delivery_method == 'LBC':
                            method_label = "LBC shipping"
                            if tracking_no:
                                item.tracking_number = tracking_no
                                item.save()
                                # Register the tracking number with the external API
                                tracker.register_lbc_tracking(tracking_no)
                        
                        notif_msg = f"Your {item.document_type.name} is now ready for {method_label}."
                        if item.tracking_number:
                            notif_msg += f" Tracking No: {item.tracking_number}"
                            
                        create_notification(item.student, 'Registrar', notif_msg)
                    # LBC INTEGRATION END
                    
                    messages.success(request, "Documents marked as READY and tracking registered if applicable.")
                
                elif action == 'mark_completed':
                    batch_items.update(status='COMPLETED')
            return redirect('registrar_dashboard')

        elif action == 'delete' and req_id:
            get_object_or_404(DocumentRequest, id=req_id).delete()
            return redirect('registrar_dashboard')

    return render(request, 'registrar_dashboard.html', {
        'active_requests': active_requests, 
        'history': history,
        'today': timezone.now()
    })

# --- XENDIT PAYMENT SYSTEM ---

@login_required
@role_required(allowed_roles=['Student'])
def pay_with_xendit(request, batch_id):
    batch_items = DocumentRequest.objects.filter(batch_id=batch_id, status='PAYMENT_REQUIRED')
    if not batch_items.exists():
        messages.error(request, "No pending payments found for this batch.")
        return redirect('student_dashboard')

    total_amount = float(batch_items.aggregate(Sum('document_type__price'))['document_type__price__sum'])
    
    secret_key = "xnd_development_r74WN7uDM75BGgolHprlxlcOpPaMPujI4C6PCtuwiDzZld8vZzCuZOtesrliMxV"
    url = "https://api.xendit.co/v2/invoices"
    
    auth_header = base64.b64encode(f"{secret_key}:".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/json",
    }
    
    data = {
        "external_id": f"BATCH-{batch_id}-{uuid.uuid4().hex[:6]}",
        "amount": total_amount,
        "description": f"Payment for Documents Batch {batch_id}",
        "payer_email": request.user.email,
        "success_redirect_url": "http://127.0.0.1:8000/payment/success/",
        "failure_redirect_url": "http://127.0.0.1:8000/dashboard/",
        "currency": "PHP",
        "payment_methods": ["GCASH", "PAYMAYA", "GRABPAY", "CARD"]
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
        res_data = response.json()

        if response.status_code == 201 or response.status_code == 200:
            invoice_id = res_data.get("id")
            invoice_url = res_data.get("invoice_url")
            batch_items.update(payment_reference=invoice_id)
            return redirect(invoice_url)
        else:
            messages.error(request, "Xendit Gateway Error. Please try again later.")
            return redirect('student_dashboard')

    except Exception as e:
        messages.error(request, f"Xendit Connection Error: {str(e)}")
        return redirect('student_dashboard')

@login_required
def payment_success(request):
    """Callback after Xendit success."""
    batch_items = DocumentRequest.objects.filter(
        student=request.user, 
        status='PAYMENT_REQUIRED',
        payment_reference__isnull=False
    )

    if batch_items.exists():
        new_receipt_no = SystemCounter.get_next_receipt_no()
        total_amt = batch_items.aggregate(Sum('document_type__price'))['document_type__price__sum']
        docs_list = [item.document_type.name for item in batch_items]

        batch_items.update(status='PAID', receipt_number=new_receipt_no)
        
        CollectionLog.objects.create(
            receipt_number=new_receipt_no,
            student_id=request.user.username,
            student_name=request.user.username,
            amount_paid=total_amt,
            documents_included=", ".join(docs_list),
            collected_by=User.objects.filter(groups__name='Cashier').first()
        )
        messages.success(request, f"Payment Verified! Summary № {new_receipt_no} generated.")
    
    return redirect('student_dashboard')

# --- CASHIER DASHBOARD ---

@role_required(allowed_roles=['Cashier'])
def cashier_dashboard(request):
    unpaid_requests = DocumentRequest.objects.filter(status='PAYMENT_REQUIRED').order_by('-created_at')
    awaiting_issuance = DocumentRequest.objects.filter(status='PAID').order_by('-created_at')
    history = DocumentRequest.objects.filter(status__in=['PROCESSING', 'READY', 'COMPLETED']).order_by('-created_at')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        req_id = request.POST.get('request_id')
        doc_req = get_object_or_404(DocumentRequest, id=req_id)

        if action == 'confirm_payment':
            batch_items = DocumentRequest.objects.filter(batch_id=doc_req.batch_id, status='PAYMENT_REQUIRED')
            new_receipt_no = SystemCounter.get_next_receipt_no()
            
            total_amt = 0
            docs_list = []
            for item in batch_items:
                item.status = 'PAID'
                item.receipt_number = new_receipt_no 
                item.save()
                total_amt += item.document_type.price
                docs_list.append(item.document_type.name)
            
            CollectionLog.objects.create(
                receipt_number=new_receipt_no, 
                student_id=doc_req.student.username, 
                student_name=doc_req.student.username, 
                amount_paid=total_amt, 
                documents_included=", ".join(docs_list), 
                collected_by=request.user
            )
            messages.success(request, f"Manual Payment confirmed for Reference № {new_receipt_no}.")

        elif action == 'issue_receipt':
            batch_items = DocumentRequest.objects.filter(receipt_number=doc_req.receipt_number)
            for item in batch_items:
                item.status = 'PROCESSING'
                item.save()
                create_notification(item.student, 'Cashier', f"Payment № {item.receipt_number} verified. Registrar has been notified.")
            
            messages.success(request, "Payment verified and items moved to processing.")

        return redirect('cashier_dashboard')

    return render(request, 'cashier_dashboard.html', {
        'requests': unpaid_requests, 
        'awaiting_issuance': awaiting_issuance,
        'history': history
    })

# --- ACCOUNTING DASHBOARD ---

@role_required(allowed_roles=['Accounting'])
def accounting_dashboard(request):
    doc_types = DocumentType.objects.all()
    debtors = StudentBalance.objects.filter(outstanding_amount__gt=0).select_related('student')
    transactions = CollectionLog.objects.all().order_by('-created_at')
    total_revenue = transactions.aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_price':
            doc = get_object_or_404(DocumentType, id=request.POST.get('doc_id'))
            doc.price = request.POST.get('new_price')
            doc.save()
            messages.success(request, f"Updated price for {doc.name}")
        elif action == 'notify_balance':
            record = get_object_or_404(StudentBalance, id=request.POST.get('balance_id'))
            try:
                send_mail(
                    'Balance Notice', 
                    f'Dear Student, you have a balance of ₱{record.outstanding_amount}. Please settle this to request credentials.', 
                    settings.DEFAULT_FROM_EMAIL, 
                    [record.student.email]
                )
                record.last_notified = timezone.now()
                record.save()
                messages.success(request, f"Notice sent to {record.student.full_name}.")
            except:
                messages.error(request, "Failed to send notice.")
        return redirect('accounting_dashboard')
    
    return render(request, 'accounting_dashboard.html', {
        'doc_types': doc_types, 
        'debtors': debtors, 
        'transactions': transactions, 
        'total_revenue': total_revenue
    })

# --- STAFF SIGNATURE SETTINGS ---

@role_required(allowed_roles=['Registrar', 'Cashier', 'Accounting'])
def signature_settings(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        profile.printed_name = request.POST.get('printed_name')
        signature_image = request.POST.get('signature_data') 
        if signature_image:
            profile.signature_data = signature_image
            
        profile.save()
        messages.success(request, "Profile signature and name updated successfully!")
        
        user_groups = request.user.groups.values_list('name', flat=True)
        if 'Cashier' in user_groups: return redirect('cashier_dashboard')
        if 'Registrar' in user_groups: return redirect('registrar_dashboard')
        if 'Accounting' in user_groups: return redirect('accounting_dashboard')
        return redirect('login')

    return render(request, 'signature_settings.html', {'profile': profile})

# --- UTILS & PRINTING ---

@login_required
def generate_receipt(request, req_id):
    """Generates a simplified Payment Summary."""
    doc_req = get_object_or_404(DocumentRequest, id=req_id)
    is_staff = request.user.groups.filter(name__in=['Cashier', 'Registrar', 'Accounting']).exists()
    if doc_req.student != request.user and not is_staff:
        raise PermissionDenied

    cashier_profile = None
    if doc_req.receipt_number:
        log = CollectionLog.objects.filter(receipt_number=doc_req.receipt_number).first()
        if log and log.collected_by:
            cashier_profile = Profile.objects.filter(user=log.collected_by).first()

    batch_items = DocumentRequest.objects.filter(receipt_number=doc_req.receipt_number) if doc_req.receipt_number else DocumentRequest.objects.filter(id=req_id)
    total_amount = batch_items.aggregate(Sum('document_type__price'))['document_type__price__sum'] or 0
    student = StudentMasterList.objects.filter(student_id=doc_req.student.username).first()
    
    return render(request, 'receipt_invoice.html', {
        'doc': doc_req, 
        'batch_items': batch_items, 
        'total_amount': total_amount,
        'student': student, 
        'cashier_profile': cashier_profile,
        'today': timezone.now(),
        'display_receipt_no': doc_req.receipt_number or "PENDING"
    })

@login_required
def mark_notifications_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'status': 'success'})

def logout_view(request):
    is_staff = request.user.is_authenticated and request.user.groups.filter(name__in=['Registrar', 'Cashier', 'Accounting']).exists()
    django_logout(request)
    return redirect('staff_login' if is_staff else 'login')

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_student_dashboard(request):
    user_requests = DocumentRequest.objects.filter(student=request.user).order_at('-created_at')
    serializer = RequestSerializer(user_requests, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_submit_request(request):
    # Logic to handle mobile request submission
    # (Similar to your POST logic in student_dashboard)
    return Response({"status": "Request Submitted"})