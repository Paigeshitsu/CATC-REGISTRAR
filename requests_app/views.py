import uuid, time, requests, json, base64, csv
from datetime import timedelta
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
from django.db.models import Sum
from django.core.cache import cache 
from django.views.decorators.csrf import csrf_exempt

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

# Local Imports
from .serializers import RequestSerializer, DocumentTypeSerializer
from .tracking_service import LBCTracker
from .models import (
    DocumentRequest, StudentMasterList, OTPToken, 
    DocumentType, StudentBalance, Notification, SystemCounter,
    CollectionLog, Profile, AuditLog, random 
)
from .forms import StudentRequestForm, StudentIDLoginForm, OTPVerifyForm
from .decorators import role_required

# --- 1. HELPERS ---

def log_audit(user, action, resource, resource_id, details):
    AuditLog.objects.create(
        user=user,
        action=action,
        resource_type=resource,
        resource_id=str(resource_id),
        details=details
    )

def send_otp_sms(phone_number, otp_code):
    if not settings.SEMAPHORE_API_KEY or settings.SEMAPHORE_API_KEY == 'YOUR_API_KEY_HERE':
        print(f"SMS Mock: To {phone_number} -> Code: {otp_code}")
        return False
    url = "https://api.semaphore.co/api/v4/messages"
    message = f"Your CATC Portal OTP is: {otp_code}. Valid for 10 minutes."
    data = {'apikey': settings.SEMAPHORE_API_KEY, 'number': phone_number, 'message': message, 'sendername': settings.SEMAPHORE_SENDER_NAME}
    try:
        response = requests.post(url, data=data, timeout=10)
        return response.status_code == 200
    except: return False

def create_notification(user, role, message):
    Notification.objects.create(user=user, sender_role=role, message=message)

# --- 2. LOGIN FLOW ---

def login_view(request):
    if request.user.is_authenticated: django_logout(request)
    if request.method == 'POST':
        last_sent = request.session.get('otp_last_sent')
        if last_sent and time.time() - last_sent < 60:
            messages.error(request, "Please wait before requesting a new code.")
            return render(request, 'login_id.html', {'form': StudentIDLoginForm(request.POST)})
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
                send_mail('Login OTP', f'Code: {otp_obj.otp_code}', settings.DEFAULT_FROM_EMAIL, [master_student.email])
                send_otp_sms(master_student.phone_number, otp_obj.otp_code)
                request.session['masked_email'], request.session['masked_phone'] = master_student.masked_email, master_student.masked_phone
                request.session['otp_last_sent'], request.session['otp_user_id'] = time.time(), user.id
                return redirect('verify_otp')
            else: messages.error(request, "Student ID not found.")
    return render(request, 'login_id.html', {'form': StudentIDLoginForm()})

def verify_otp(request):
    user_id = request.session.get('otp_user_id')
    if not user_id: return redirect('login')
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        form = OTPVerifyForm(request.POST)
        if form.is_valid():
            threshold = timezone.now() - timedelta(minutes=10)
            otp_record = OTPToken.objects.filter(user=user, otp_code=form.cleaned_data['otp_code'], is_verified=False, created_at__gte=threshold).last()
            if otp_record:
                otp_record.is_verified = True; otp_record.save()
                login(request, user); del request.session['otp_user_id']
                return redirect('student_dashboard')
            else: messages.error(request, "Invalid or expired OTP code.")
    return render(request, 'login_otp.html', {'form': OTPVerifyForm(), 'masked_email': request.session.get('masked_email'), 'masked_phone': request.session.get('masked_phone')})

# --- 3. STUDENT DASHBOARD ---

@role_required(allowed_roles=['Student'])
def student_dashboard(request):
    student_info = StudentMasterList.objects.filter(student_id=request.user.username).first()
    balance_record = StudentBalance.objects.filter(student__student_id=request.user.username).first()
    has_balance = balance_record.outstanding_amount > 0 if balance_record else False
    user_requests = DocumentRequest.objects.filter(student=request.user, is_deleted=False).order_by('-created_at')

    greetings = ["Welcome! Have a Good Day.", "Hello!", "Your documents, our priority.", "Making paperwork easier!"]
    random_greeting = random.choice(greetings)

    all_docs = DocumentType.objects.all()
    base_docs = all_docs.exclude(name__startswith="Authentication")
    auth_docs = all_docs.filter(name__startswith="Authentication")

    # RESTRICTED KEYWORDS
    RESTRICTED_KEYWORDS = ["TOR", "TRANSCRIPT", "DIPLOMA", "CLEARANCE"]

    grouped_docs = []
    for base in base_docs:
        auth_match = auth_docs.filter(name__icontains=base.name).first()
        # Specific check: is this a restricted document?
        is_restricted = any(key in base.name.upper() for key in RESTRICTED_KEYWORDS)
        
        grouped_docs.append({
            'id': base.id, 
            'name': base.name, 
            'price': base.price,
            'has_auth': bool(auth_match), 
            'auth_id': auth_match.id if auth_match else None,
            # Block ONLY if it is restricted AND user has a balance
            'is_blocked': (is_restricted and has_balance) 
        })

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'delete_request':
            batch_id = request.POST.get('batch_id') 
            DocumentRequest.objects.filter(batch_id=batch_id, student=request.user).update(is_deleted=True)
            messages.success(request, "Request cancelled successfully.")
            return redirect('student_dashboard')

        if action == 'submit_request':
            reason = request.POST.get('reason')
            batch_id = str(uuid.uuid4())[:8]
            found_any = False
    
            for base in base_docs:
                selection = request.POST.get(f'selection_{base.id}')
                if not selection or selection == 'none':
                    continue
                
                # SERVER-SIDE PROTECTION: Check if they tried to bypass the UI block
                is_restricted = any(key in base.name.upper() for key in RESTRICTED_KEYWORDS)
                if is_restricted and has_balance:
                    messages.error(request, f"Cannot request {base.name} due to outstanding balance.")
                    return redirect('student_dashboard')

                found_any = True
                delivery = request.POST.get(f'delivery_{base.id}', 'PICKUP')
                
                to_create = []
                if selection == 'doc': to_create.append(base)
                elif selection == 'auth': to_create.append(auth_docs.filter(name__icontains=base.name).first())
                elif selection == 'both':
                    to_create.append(base)
                    to_create.append(auth_docs.filter(name__icontains=base.name).first())

                for dt in to_create:
                    if dt:
                        DocumentRequest.objects.create(
                            student=request.user, document_type=dt, reason=reason, batch_id=batch_id, delivery_method=delivery,
                            lbc_type=request.POST.get(f'lbc_type_{base.id}'), shipping_first_name=request.POST.get(f'sfname_{base.id}'),
                            shipping_last_name=request.POST.get(f'slname_{base.id}'), shipping_phone=request.POST.get(f'sphone_{base.id}'),
                            shipping_floor=request.POST.get(f'sfloor_{base.id}'), shipping_street=request.POST.get(f'sstreet_{base.id}'),
                            shipping_province=request.POST.get(f'sprovince_{base.id}'), shipping_city=request.POST.get(f'scity_{base.id}'),
                            shipping_barangay=request.POST.get(f'sbarangay_{base.id}'), lbc_branch_name=request.POST.get(f'lbc_branch_{base.id}')
                        )
            
            if found_any: messages.success(request, "Document requests submitted!")
            else: messages.warning(request, "No documents were selected.")
            return redirect('student_dashboard')

    return render(request, 'dashboard.html', {
        'grouped_docs': grouped_docs, 
        'requests': user_requests, 
        'student': student_info,
        'random_greeting': random_greeting, 
        'has_balance': has_balance,
        'balance_amount': balance_record.outstanding_amount if balance_record else 0,
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count(),
        'notifications': Notification.objects.filter(user=request.user).order_by('-created_at')[:10],
    })

# --- 4. REGISTRAR ---

@role_required(allowed_roles=['Registrar'])
def registrar_dashboard(request):
    active_requests = DocumentRequest.objects.filter(is_deleted=False).exclude(status__in=['COMPLETED', 'REJECTED']).order_by('-created_at')
    history = DocumentRequest.objects.filter(is_deleted=False, status__in=['COMPLETED', 'REJECTED']).order_by('-created_at')
    if request.method == 'POST':
        action, batch_id = request.POST.get('action'), request.POST.get('batch_id')
        batch = DocumentRequest.objects.filter(batch_id=batch_id)
        if action == 'approve': 
            batch.update(status='PAYMENT_REQUIRED')
            log_audit(request.user, 'UPDATE', 'DocumentRequest', batch_id, "Approved for payment.")
        elif action == 'reject':
            batch.update(status='REJECTED')
            log_audit(request.user, 'UPDATE', 'DocumentRequest', batch_id, "Rejected batch.")
            for item in batch: create_notification(item.student, 'Registrar', f"Request for {item.document_type.name} rejected.")
        elif action == 'mark_ready':
            t_no = request.POST.get('tracking_number_input', '').strip()
            batch.update(status='READY', tracking_number=t_no if t_no else None)
            if t_no: LBCTracker().register_lbc_tracking(t_no)
        elif action == 'mark_completed': batch.update(status='COMPLETED')
        return redirect('registrar_dashboard')
    return render(request, 'registrar_dashboard.html', {'active_requests': active_requests, 'history': history})

# --- 5. ACCOUNTING & CSV EXPORT ---

@role_required(allowed_roles=['Accounting'])
def export_collection_csv(request):
    transactions = CollectionLog.objects.all().order_by('-created_at')
    filter_type = request.GET.get('filter_type', 'all')
    target_date = request.GET.get('target_date')
    
    if target_date:
        try:
            date_obj = timezone.datetime.strptime(target_date, '%Y-%m-%d').date()
            if filter_type == 'daily': transactions = transactions.filter(created_at__date=date_obj)
            elif filter_type == 'weekly':
                start = date_obj - timedelta(days=date_obj.weekday())
                transactions = transactions.filter(created_at__date__range=[start, start + timedelta(days=6)])
            elif filter_type == 'monthly': transactions = transactions.filter(created_at__year=date_obj.year, created_at__month=date_obj.month)
            elif filter_type == 'yearly': transactions = transactions.filter(created_at__year=date_obj.year)
        except: pass

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="CATC_Ledger.csv"'
    writer = csv.writer(response)
    writer.writerow(['Timestamp', 'OR Number', 'Student ID', 'Student Name', 'Method', 'Amount', 'Docs'])
    for t in transactions:
        writer.writerow([t.created_at.strftime("%Y-%m-%d %H:%M"), t.receipt_number, t.student_id, t.student_name, t.payment_method, t.amount_paid, t.documents_included])
    return response

@role_required(allowed_roles=['Accounting'])
def accounting_dashboard(request):
    transactions = CollectionLog.objects.all().order_by('-created_at')
    audit_logs = AuditLog.objects.all().order_by('-timestamp')[:100]
    all_requests_history = DocumentRequest.objects.all().order_by('-created_at') 

    filter_type, target_date = request.GET.get('filter_type', 'all'), request.GET.get('target_date')
    if target_date:
        try:
            date_obj = timezone.datetime.strptime(target_date, '%Y-%m-%d').date()
            if filter_type == 'daily': transactions = transactions.filter(created_at__date=date_obj)
            elif filter_type == 'weekly':
                start = date_obj - timedelta(days=date_obj.weekday())
                transactions = transactions.filter(created_at__date__range=[start, start + timedelta(days=6)])
            elif filter_type == 'monthly': transactions = transactions.filter(created_at__year=date_obj.year, created_at__month=date_obj.month)
            elif filter_type == 'yearly': transactions = transactions.filter(created_at__year=date_obj.year)
        except: pass

    cash_total = transactions.filter(payment_method='CASH').aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0
    online_total = transactions.filter(payment_method='ONLINE').aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_price':
            doc = get_object_or_404(DocumentType, id=request.POST.get('doc_id'))
            doc.price = request.POST.get('new_price'); doc.save()
            log_audit(request.user, 'PRICE', 'DocumentType', doc.id, "Price updated.")
        elif action == 'notify_balance':
            record = get_object_or_404(StudentBalance, id=request.POST.get('balance_id'))
            send_mail('Balance Notice', f'Balance: ₱{record.outstanding_amount}.', settings.DEFAULT_FROM_EMAIL, [record.student.email])
            record.last_notified = timezone.now(); record.save()
        return redirect('accounting_dashboard')
    
    return render(request, 'accounting_dashboard.html', {
        'transactions': transactions, 'cash_total': cash_total, 'online_total': online_total,
        'total_revenue': cash_total + online_total, 'filter_type': filter_type, 'target_date': target_date,
        'audit_logs': audit_logs, 'doc_types': DocumentType.objects.all(), 
        'debtors': StudentBalance.objects.filter(outstanding_amount__gt=0).select_related('student'),
        'all_requests_history': all_requests_history,
    })

# --- 6. CASHIER ---

@role_required(allowed_roles=['Cashier'])
def cashier_dashboard(request):
    unpaid = DocumentRequest.objects.filter(is_deleted=False, status='PAYMENT_REQUIRED').order_by('-created_at')
    awaiting = DocumentRequest.objects.filter(is_deleted=False, status='PAID').order_by('-created_at')
    history = DocumentRequest.objects.filter(is_deleted=False, status__in=['PROCESSING', 'READY', 'COMPLETED']).order_by('-created_at')
    if request.method == 'POST':
        action, req_id = request.POST.get('action'), request.POST.get('request_id')
        doc_req = get_object_or_404(DocumentRequest, id=req_id)
        if action == 'confirm_payment':
            batch = DocumentRequest.objects.filter(batch_id=doc_req.batch_id, status='PAYMENT_REQUIRED')
            new_no = SystemCounter.get_next_receipt_no()
            total = batch.aggregate(Sum('document_type__price'))['document_type__price__sum']
            batch.update(status='PAID', receipt_number=new_no)
            CollectionLog.objects.create(
                receipt_number=new_no, student_id=doc_req.student.username, student_name=doc_req.get_student_name(), 
                amount_paid=total, documents_included=", ".join([i.document_type.name for i in batch]),
                collected_by=request.user, payment_method='CASH'
            )
            log_audit(request.user, 'UPDATE', 'DocumentRequest', doc_req.batch_id, "Cash payment confirmed.")
        return redirect('cashier_dashboard')
    return render(request, 'cashier_dashboard.html', {'requests': unpaid, 'awaiting_issuance': awaiting, 'history': history})

# --- 7. PAYMENTS & MISC ---

@csrf_exempt
@api_view(['POST'])
def xendit_webhook(request):
    if request.headers.get('x-callback-token') != getattr(settings, 'XENDIT_CALLBACK_TOKEN', None): return Response(status=403)
    data = request.data
    ext_id, status = data.get('external_id'), data.get('status')
    if status == 'PAID' and ext_id.startswith('BATCH-'):
        batch_id = ext_id.split('-')[1]
        items = DocumentRequest.objects.filter(batch_id=batch_id, status='PAYMENT_REQUIRED')
        if items.exists():
            new_no = SystemCounter.get_next_receipt_no()
            total = items.aggregate(Sum('document_type__price'))['document_type__price__sum']
            items.update(status='PAID', receipt_number=new_no)
            CollectionLog.objects.create(
                receipt_number=new_no, student_id=items.first().student.username, 
                student_name=items.first().get_student_name(), amount_paid=total, 
                documents_included=", ".join([i.document_type.name for i in items]), payment_method='ONLINE'
            )
    return Response(status=200)

@login_required
def payment_success(request):
    messages.success(request, "Payment Verified!")
    return redirect('student_dashboard')

@login_required
def generate_receipt(request, req_id):
    doc_req = get_object_or_404(DocumentRequest, id=req_id)
    is_staff = request.user.groups.filter(name__in=['Registrar', 'Cashier', 'Accounting']).exists()
    if not (doc_req.student == request.user or is_staff or request.user.is_superuser): raise PermissionDenied()
    batch = DocumentRequest.objects.filter(receipt_number=doc_req.receipt_number) if doc_req.receipt_number else DocumentRequest.objects.filter(id=req_id)
    student = StudentMasterList.objects.filter(student_id=doc_req.student.username).first()
    return render(request, 'receipt_invoice.html', {'doc': doc_req, 'batch_items': batch, 'student': student, 'today': timezone.now(), 'total_amount': batch.aggregate(Sum('document_type__price'))['document_type__price__sum'] or 0, 'display_receipt_no': doc_req.receipt_number or "PENDING"})

def staff_login(request):
    if request.user.is_authenticated: django_logout(request)
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            user_groups = user.groups.values_list('name', flat=True)
            if any(role in user_groups for role in ['Registrar', 'Cashier', 'Accounting']):
                login(request, user)
                if 'Registrar' in user_groups: return redirect('registrar_dashboard')
                if 'Cashier' in user_groups: return redirect('cashier_dashboard')
                return redirect('accounting_dashboard')
            else: messages.error(request, "Access denied.")
    return render(request, 'staff_login.html', {'form': AuthenticationForm()})

def logout_view(request):
    is_staff = request.user.is_authenticated and (request.user.groups.filter(name__in=['Registrar', 'Cashier', 'Accounting']).exists() or request.user.is_superuser)
    django_logout(request); return redirect('staff_login' if is_staff else 'login')

@login_required
def mark_notifications_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'status': 'success'})

@role_required(allowed_roles=['Registrar', 'Cashier', 'Accounting'])
def signature_settings(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        profile.printed_name = request.POST.get('printed_name')
        if request.POST.get('signature_data'): profile.signature_data = request.POST.get('signature_data')
        profile.save(); messages.success(request, "Updated.")
        return redirect('registrar_dashboard')
    return render(request, 'signature_settings.html', {'profile': profile})

@api_view(['POST'])
def api_login_request(request):
    sid = request.data.get('student_id', '').strip().upper()
    if cache.get(f"otp_api_lock_{sid}"): return Response({"status": "error", "message": "Wait 1 min."}, status=429)
    master_student = StudentMasterList.objects.filter(student_id=sid).first()
    if master_student:
        user, _ = User.objects.get_or_create(username=sid, defaults={'email': master_student.email})
        otp = OTPToken.objects.create(user=user); otp.generate_code()
        send_mail('Login OTP', f'Code: {otp.otp_code}', settings.DEFAULT_FROM_EMAIL, [master_student.email])
        cache.set(f"otp_api_lock_{sid}", True, 60)
        return Response({"status": "success", "masked_email": master_student.masked_email, "masked_phone": master_student.masked_phone})
    return Response(status=404)

@api_view(['POST'])
def api_verify_otp(request):
    sid, code = request.data.get('student_id', '').upper(), request.data.get('otp_code')
    user = get_object_or_404(User, username=sid)
    otp = OTPToken.objects.filter(user=user, otp_code=code, is_verified=False, created_at__gte=timezone.now() - timedelta(minutes=10)).last()
    if otp:
        otp.is_verified = True; otp.save()
        return Response({"status": "success", "access": str(RefreshToken.for_user(user).access_token)})
    return Response({"status": "error", "message": "Expired/Invalid."}, status=400)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_student_dashboard(request):
    return Response(RequestSerializer(DocumentRequest.objects.filter(student=request.user, is_deleted=False).order_by('-created_at'), many=True).data)

@login_required
@role_required(allowed_roles=['Student'])
def pay_with_xendit(request, batch_id):
    batch = DocumentRequest.objects.filter(batch_id=batch_id, status='PAYMENT_REQUIRED')
    if not batch.exists(): return redirect('student_dashboard')
    total = float(batch.aggregate(Sum('document_type__price'))['document_type__price__sum'])
    auth = base64.b64encode(f"{settings.XENDIT_SECRET_KEY}:".encode()).decode()
    data = {"external_id": f"BATCH-{batch_id}-{uuid.uuid4().hex[:6]}", "amount": total, "description": f"Payment Batch {batch_id}", "payer_email": request.user.email, "success_redirect_url": settings.XENDIT_REDIRECT_URL, "currency": "PHP", "payment_methods": ["GCASH", "PAYMAYA", "CARD"]}
    try:
        res = requests.post("https://api.xendit.co/v2/invoices", headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"}, data=json.dumps(data), timeout=10)
        if res.status_code in [200, 201]: return redirect(res.json().get("invoice_url"))
    except: messages.error(request, "Xendit connection failed.")
    return redirect('student_dashboard')