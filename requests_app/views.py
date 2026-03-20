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
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

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
    print(f"[SMS DEBUG] Attempting to send OTP to phone: {phone_number}")
    
    # Try iProg SMS API first (as primary)
    if settings.IPROG_SMS_API_TOKEN:
        url = settings.IPROG_SMS_API_URL
        message = f"Your CATC Portal OTP is: {otp_code}. Valid for 10 minutes."
        
        # Ensure phone number is in E.164 format (with country code)
        # Add +63 for Philippines if not already present
        clean_phone = phone_number.replace(' ', '').replace('-', '')
        if not clean_phone.startswith('+'):
            if clean_phone.startswith('0'):
                clean_phone = '+63' + clean_phone[1:]
            elif clean_phone.startswith('63'):
                clean_phone = '+' + clean_phone
            else:
                clean_phone = '+63' + clean_phone
        
        print(f"[SMS DEBUG] Sending to iProg API - Clean phone: {clean_phone}")
        
        try:
            response = requests.post(
                url,
                data={
                    'api_token': settings.IPROG_SMS_API_TOKEN,
                    'message': message,
                    'phone_number': clean_phone
                },
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded'
                },
                timeout=15
            )
            print(f"[SMS DEBUG] iProg API response: {response.status_code} - {response.text}")
            if response.status_code == 200:
                return True
            print(f"iProg SMS API error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"iProg SMS API exception: {e}")
    
    # Fallback to other SMS APIs if iProg fails
    # Try primary SMS API
    if settings.SMS_API_KEY and settings.SMS_API_KEY != 'YOUR_API_KEY':
        url = settings.SMS_API_URL
        message = f"Your CATC Portal OTP is: {otp_code}. Valid for 10 minutes."
        
        # Ensure phone number is in E.164 format (with country code)
        clean_phone = phone_number.replace(' ', '').replace('-', '')
        if not clean_phone.startswith('+'):
            if clean_phone.startswith('0'):
                clean_phone = '+63' + clean_phone[1:]
            elif clean_phone.startswith('63'):
                clean_phone = '+' + clean_phone
            else:
                clean_phone = '+63' + clean_phone
        
        try:
            response = requests.post(
                url,
                json={
                    'recipient': clean_phone,
                    'message': message
                },
                headers={
                    'x-api-key': settings.SMS_API_KEY,
                    'Content-Type': 'application/json'
                },
                timeout=10
            )
            if response.status_code == 200:
                return True
        except Exception as e:
            print(f"SMS API error: {e}")
    
    # Fallback to Semaphore
    if not settings.SEMAPHORE_API_KEY or settings.SEMAPHORE_API_KEY == 'YOUR_API_KEY_HERE':
        print(f"SMS Mock: To {phone_number} -> Code: {otp_code}")
        return False
    url = "https://api.semaphore.co/api/v4/messages"
    message = f"Your CATC Portal OTP is: {otp_code}. Valid for 10 minutes."
    data = {'apikey': settings.SEMAPHORE_API_KEY, 'number': phone_number, 'message': message, 'sendername': settings.SEMAPHORE_SENDER_NAME}
    try:
        response = requests.post(url, data=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Semaphore SMS API error: {e}")
        return False

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
                
                # Always create a new OTP token for this login attempt
                # Delete any existing unverified OTP tokens for this user
                OTPToken.objects.filter(user=user, is_verified=False).delete()
                
                # Create new OTP token
                otp_obj = OTPToken.objects.create(user=user)
                otp_obj.generate_code()
                
                # Debug: Print the generated OTP code
                print(f"\n===== DEBUG: OTP Generated for {sid} =====")
                print(f"OTP Code: {otp_obj.otp_code}")
                print(f"Google Auth Secret: {otp_obj.google_auth_secret}")
                print(f"===========================================\n")
                
                # Get Google Authenticator provisioning URI
                google_auth_uri = otp_obj.get_google_auth_uri()
                
                # Print OTP to console for testing
                print(f"\n===== OTP for {sid}: {otp_obj.otp_code} =====")
                print(f"===== Google Auth Secret: {otp_obj.google_auth_secret} =====")
                print(f"===== Google Auth URI: {google_auth_uri} =====\n")
                
                # Try sending email, but continue if it fails
                try:
                    # Include both the regular OTP and Google Auth setup info in email
                    email_message = f"""
Your CATC Portal Login Code: {otp_obj.otp_code}

This code is valid for 10 minutes.

To use Google Authenticator:
1. Download Google Authenticator app on your phone
2. The secret key for setup is: {otp_obj.google_auth_secret}

Or scan this QR code in the Google Authenticator app.
"""
                    # Send email and SMS simultaneously using threading
                    import threading
                    
                    def send_email_thread():
                        try:
                            send_mail('Login OTP', email_message, settings.DEFAULT_FROM_EMAIL, [master_student.email])
                            print(f"[EMAIL] OTP sent to {master_student.email}")
                        except Exception as e:
                            print(f"Email sending failed: {e}")
                    
                    def send_sms_thread():
                        try:
                            send_otp_sms(master_student.phone_number, otp_obj.otp_code)
                            print(f"[SMS] OTP sent to {master_student.phone_number}")
                        except Exception as e:
                            print(f"SMS sending failed: {e}")
                    
                    # Start both email and SMS threads simultaneously
                    email_thread = threading.Thread(target=send_email_thread)
                    sms_thread = threading.Thread(target=send_sms_thread)
                    email_thread.start()
                    sms_thread.start()
                    # Wait for both to complete
                    email_thread.join()
                    sms_thread.join()
                except Exception as e:
                    print(f"Email/SMS sending failed: {e}")
                    
                    print(f"[LOGIN DEBUG] Phone number from DB: '{master_student.phone_number}'")
                    request.session['masked_email'], request.session['masked_phone'] = master_student.masked_email, master_student.masked_phone
                request.session['otp_last_sent'], request.session['otp_user_id'] = time.time(), user.id
                request.session['google_auth_secret'] = otp_obj.google_auth_secret
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
            input_code = form.cleaned_data['otp_code'].strip()
            
            # Debug: Print the input code
            print(f"[DEBUG] Input code: {input_code}")
            
            # First, try to find any unverified OTP for this user within the time window
            otp_record = OTPToken.objects.filter(user=user, is_verified=False, created_at__gte=threshold).last()
            
            if otp_record:
                print(f"[DEBUG] Found OTP record: {otp_record.otp_code}")
                print(f"[DEBUG] Stored code: '{otp_record.otp_code}'")
                print(f"[DEBUG] Input code: '{input_code}'")
                print(f"[DEBUG] Match: {otp_record.otp_code == input_code}")
                
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
                            del request.session['otp_user_id']
                            return redirect('student_dashboard')
                    except ImportError:
                        pass
                
                # Fall back to regular OTP code
                if otp_record.otp_code == input_code:
                    otp_record.is_verified = True
                    otp_record.save()
                    login(request, user)
                    del request.session['otp_user_id']
                    return redirect('student_dashboard')
                
                messages.error(request, "Invalid or expired OTP code.")
            else:
                # Debug: Print all OTP records for this user
                all_otps = OTPToken.objects.filter(user=user).order_by('-created_at')[:5]
                print(f"[DEBUG] No OTP found. User's recent OTPs:")
                for otp in all_otps:
                    print(f"  - Code: {otp.otp_code}, Verified: {otp.is_verified}, Created: {otp.created_at}")
                messages.error(request, "No pending OTP verification found. Please request a new code.")
    
    # Pass Google Auth secret to template for manual entry if needed
    google_auth_secret = request.session.get('google_auth_secret')
    return render(request, 'login_otp.html', {
        'form': OTPVerifyForm(), 
        'masked_email': request.session.get('masked_email'), 
        'masked_phone': request.session.get('masked_phone'),
        'google_auth_secret': google_auth_secret
    })

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
    
    # Check if student is graduated
    is_graduated = student_info.is_graduated if student_info else False
    
    # Get TOR request count for this student
    tor_request_count = 0
    if student_info:
        tor_type = DocumentType.objects.filter(name__icontains='TOR').first()
        if tor_type:
            tor_request_count = DocumentRequest.objects.filter(
                student=request.user,
                document_type=tor_type,
                is_deleted=False
            ).exclude(status='REJECTED').count()
    
    # Check if first TOR request (free for graduates)
    is_first_tor_request = is_graduated and tor_request_count == 0

    grouped_docs = []
    for base in base_docs:
        auth_match = auth_docs.filter(name__icontains=base.name).first()
        # Specific check: is this a restricted document?
        is_restricted = any(key in base.name.upper() for key in RESTRICTED_KEYWORDS)
        
        # Special handling for TOR
        is_tor = 'TOR' in base.name.upper() or 'TRANSCRIPT' in base.name.upper()
        
        # For TOR: if graduated and first request, show as FREE
        tor_display_price = None
        if is_tor and is_first_tor_request:
            tor_display_price = 0  # Free for first TOR request
        elif is_tor and not is_first_tor_request:
            tor_display_price = "Pay per page (₱100/page)"
        
        grouped_docs.append({
            'id': base.id, 
            'name': base.name, 
            'price': base.price,
            'has_auth': bool(auth_match), 
            'auth_id': auth_match.id if auth_match else None,
            # Block ONLY if it is restricted AND user has a balance
            'is_blocked': (is_restricted and has_balance),
            # TOR-specific info
            'is_tor': is_tor,
            'tor_display_price': tor_display_price,
            'is_first_tor_request': is_first_tor_request
        })

    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'delete_request':
            batch_id = request.POST.get('batch_id') 
            DocumentRequest.objects.filter(batch_id=batch_id, student=request.user).update(is_deleted=True)
            messages.success(request, "Request cancelled successfully.")
            return redirect('student_dashboard')

        if action == 'update_tracking':
            batch_id = request.POST.get('batch_id')
            tracking_number = request.POST.get('student_tracking_number', '').strip()
            lbc_delivery_type = request.POST.get('lbc_delivery_type', 'door_to_door')
            lbc_branch_name = request.POST.get('lbc_branch_name', '').strip()
            lbc_consignee_name = request.POST.get('lbc_consignee_name', '').strip()
            
            if tracking_number:
                # Check if this is an AJAX request
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    # Update tracking number for all documents in the batch
                    DocumentRequest.objects.filter(batch_id=batch_id, student=request.user).update(
                        tracking_number=tracking_number,
                        lbc_type='BRANCH' if lbc_delivery_type == 'branch_pickup' else 'RIDER',
                        lbc_branch_name=lbc_branch_name if lbc_branch_name else None
                    )
                    # Register tracking with LBC API
                    LBCTracker().register_lbc_tracking(tracking_number)
                    return JsonResponse({'success': True, 'message': 'Tracking number saved!'})
                else:
                    # Regular form submission
                    DocumentRequest.objects.filter(batch_id=batch_id, student=request.user).update(
                        tracking_number=tracking_number,
                        lbc_type='BRANCH' if lbc_delivery_type == 'branch_pickup' else 'RIDER',
                        lbc_branch_name=lbc_branch_name if lbc_branch_name else None
                    )
                    LBCTracker().register_lbc_tracking(tracking_number)
                    messages.success(request, f"Tracking number {tracking_number} submitted successfully!")
                    return redirect('student_dashboard')
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': 'Please enter a valid tracking number.'})
                messages.error(request, "Please enter a valid tracking number.")
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
                
                # AUTO-FILL LBC PICKUP ADDRESS: When LBC is selected, use college address for rider pickup
                if delivery == 'LBC':
                    # Fixed college address for LBC rider pickup
                    college_floor = "Computer Arts Technological College - New Main Building"
                    college_street = "Binanuahan West"
                    college_city = "Legazpi City"
                    college_province = "Albay"
                    college_barangay = "Binanuahan West"
                    college_zip = "4500"
                    college_landmark = "New Main Building"
                    college_phone = "(052) 742-0628"
                    # Use fixed college name as sender
                    college_first_name = "CATC"
                    college_last_name = "Registrar Office"
                else:
                    college_floor = request.POST.get(f'sfloor_{base.id}')
                    college_street = request.POST.get(f'sstreet_{base.id}')
                    college_city = request.POST.get(f'scity_{base.id}')
                    college_province = request.POST.get(f'sprovince_{base.id}')
                    college_barangay = request.POST.get(f'sbarangay_{base.id}')
                    college_zip = ""
                    college_landmark = request.POST.get(f'sfloor_{base.id}')
                    college_phone = request.POST.get(f'sphone_{base.id}')
                    college_first_name = request.POST.get(f'sfname_{base.id}')
                    college_last_name = request.POST.get(f'slname_{base.id}')
                
                to_create = []
                if selection == 'doc': to_create.append(base)
                elif selection == 'auth': to_create.append(auth_docs.filter(name__icontains=base.name).first())
                elif selection == 'both':
                    to_create.append(base)
                    to_create.append(auth_docs.filter(name__icontains=base.name).first())

                for dt in to_create:
                    if dt:
                        # Check if this is a TOR request
                        is_tor = 'TOR' in dt.name.upper() or 'TRANSCRIPT' in dt.name.upper()
                        
                        # Check if rush processing is requested
                        rush_requested = request.POST.get(f'rush_{base.id}') == '1'
                        
                        # Set processing_days: 1 for rush, default 3
                        processing_days_value = 1 if rush_requested else 3
                        
                        # Create the document request
                        doc_request = DocumentRequest.objects.create(
                            student=request.user, document_type=dt, reason=reason, batch_id=batch_id, delivery_method=delivery,
                            lbc_type=request.POST.get(f'lbc_type_{base.id}'), shipping_first_name=college_first_name,
                            shipping_last_name=college_last_name, shipping_phone=college_phone,
                            shipping_floor=college_floor, shipping_street=college_street,
                            shipping_province=college_province, shipping_city=college_city,
                            shipping_barangay=college_barangay, shipping_zip=college_zip, shipping_landmark=college_landmark,
                            lbc_branch_name=request.POST.get(f'lbc_branch_{base.id}'),
                            rush_processing=rush_requested,
                            processing_days=processing_days_value
                        )
                        
                        # Special handling for TOR
                        if is_tor and is_first_tor_request:
                            # First TOR request for graduate is FREE
                            doc_request.tor_price_override = 0
                            doc_request.save()
                            if rush_requested:
                                messages.info(request, f"Your {dt.name} request is FREE as it's your first request as a graduate. Rush processing applies (2x = ₱0 still free).")
                            else:
                                messages.info(request, f"Your {dt.name} request is FREE as it's your first request as a graduate.")
                        elif is_tor:
                            # Subsequent TOR requests need registrar to count pages
                            if rush_requested:
                                messages.info(request, f"Your {dt.name} request will be reviewed by the Registrar with rush processing. You will be notified of the page count and payment amount (2x price).")
                            else:
                                messages.info(request, f"Your {dt.name} request will be reviewed by the Registrar. You will be notified of the page count and payment amount.")
            
            if found_any: messages.success(request, "Document requests submitted!")
            else: messages.warning(request, "No documents were selected.")
            return redirect('student_dashboard')

    # Get active shipment for tracking panel (most recent shipment with tracking number)
    active_shipment = user_requests.filter(
        tracking_number__isnull=False,
        tracking_number__gt=''
    ).exclude(status__in=['COMPLETED', 'REJECTED']).first()

    return render(request, 'dashboard.html', {
        'grouped_docs': grouped_docs, 
        'requests': user_requests, 
        'student': student_info,
        'random_greeting': random_greeting, 
        'has_balance': has_balance,
        'balance_amount': balance_record.outstanding_amount if balance_record else 0,
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count(),
        'notifications': Notification.objects.filter(user=request.user).order_by('-created_at')[:10],
        'active_shipment': active_shipment,
    })

# --- 4. REGISTRAR ---

@role_required(allowed_roles=['Registrar'])
def registrar_dashboard(request):
    active_requests = DocumentRequest.objects.filter(is_deleted=False).exclude(status__in=['COMPLETED', 'REJECTED']).order_by('-created_at')
    history = DocumentRequest.objects.filter(is_deleted=False, status__in=['COMPLETED', 'REJECTED']).order_by('-created_at')
    
    # Calculate stats for cards
    pending_count = active_requests.filter(status='PENDING').count()
    ready_count = active_requests.filter(status='READY').count()
    paid_count = active_requests.filter(status='PAID').count() + active_requests.filter(status='PROCESSING').count()
    processing_count = active_requests.filter(status='PROCESSING').count()
    if request.method == 'POST':
        action, batch_id = request.POST.get('action'), request.POST.get('batch_id')
        batch = DocumentRequest.objects.filter(batch_id=batch_id)
        if action == 'approve':
            # Approve non-TOR requests for payment
            # TOR requests are handled by 'send_to_tor' action
            
            # Filter out TOR requests - they go through send_to_tor action
            non_tor_batch = batch.exclude(document_type__name__icontains='TOR')
            
            if non_tor_batch.exists():
                non_tor_batch.update(status='APPROVED')
                log_audit(request.user, 'UPDATE', 'DocumentRequest', batch_id, "Approved for payment.")
                # Notify student
                for item in non_tor_batch:
                    if item.rush_processing:
                        create_notification(item.student, 'Registrar', f"Your {item.document_type.name} request has been approved (RUSH - 2x Price). Please proceed to payment.")
                    else:
                        create_notification(item.student, 'Registrar', f"Your {item.document_type.name} request has been approved. Please proceed to payment.")
                messages.success(request, f"Request approved for payment.")
            else:
                messages.info(request, "No non-TOR requests to approve in this batch.")
        elif action == 'send_to_tor':
            # Directly send TOR requests to TOR dashboard for page counting
            # Only update TOR items in the batch
            tor_items = batch.filter(document_type__name__icontains='TOR')
            tor_items.update(status='PENDING_TOR_COUNT')
            log_audit(request.user, 'UPDATE', 'DocumentRequest', batch_id, "Sent to TOR Desk for page counting.")
            # Notify TOR desk and student
            for item in tor_items:
                rush_msg = ' (RUSH - PRIORITY)' if item.rush_processing else ''
                create_notification(item.student, 'TOR Desk', 
                    f"Your TOR request has been sent to TOR Desk for page counting.{rush_msg} Please wait for the TOR Desk to process.")
            messages.success(request, f"TOR request sent to TOR Desk for page counting.")
        elif action == 'reject':
            batch.update(status='REJECTED')
            log_audit(request.user, 'UPDATE', 'DocumentRequest', batch_id, "Rejected batch.")
            # Get rejection reason from POST data
            rejection_reason = request.POST.get('rejection_reason', '').strip()
            for item in batch:
                if rejection_reason:
                    create_notification(item.student, 'Registrar', f"Your {item.document_type.name} request has been rejected. Reason: {rejection_reason}")
                else:
                    create_notification(item.student, 'Registrar', f"Your {item.document_type.name} request has been rejected.")
        elif action == 'mark_ready':
            t_no = request.POST.get('tracking_number_input', '').strip()
            processing_days = request.POST.get('processing_days')
            try:
                processing_days = int(processing_days) if processing_days else None
            except ValueError:
                processing_days = None
            
            # Update each item with tracking number and processing days
            # For LBC delivery: mark as COMPLETED (LBC will notify student)
            # For Pickup: mark as READY (student needs to claim)
            for item in batch:
                item.tracking_number = t_no if t_no else None
                item.processing_days = processing_days
                if item.delivery_method == 'LBC':
                    item.status = 'COMPLETED'  # LBC handles notification
                else:
                    item.status = 'READY'  # Student comes to claim
                item.save()
            
            # Register tracking with LBC API if tracking number provided
            if t_no:
                try:
                    tracker = LBCTracker()
                    result = tracker.register_lbc_tracking(t_no)
                    if result.get('meta', {}).get('code', 200) >= 400:
                        messages.warning(request, f"LBC tracking registration may have failed. Please verify manually.")
                        print(f"[LBC WARNING] Tracking registration for {t_no}: {result}")
                except Exception as e:
                    messages.warning(request, f"LBC tracking registration failed: {str(e)}")
                    print(f"[LBC ERROR] Tracking registration error: {e}")
            # Success message for marking as ready
            ready_count = batch.count()
            lbc_count = batch.filter(delivery_method='LBC').count()
            pickup_count = ready_count - lbc_count
            
            if lbc_count > 0:
                messages.success(request, f"{lbc_count} LBC document(s) marked as COMPLETED (LBC will notify student). Tracking: {t_no or 'N/A'}")
            if pickup_count > 0:
                messages.success(request, f"{pickup_count} pickup document(s) marked as READY - waiting for student to claim.")
            log_audit(request.user, 'UPDATE', 'DocumentRequest', batch_id, f"Marked as READY. Tracking: {t_no}, Days: {processing_days}")
            
            print(f"[DEBUG] mark_ready completed. Batch ID: {batch_id}, Items updated: {ready_count}")
            
            # Notify student about status
            for item in batch:
                if item.delivery_method == 'LBC':
                    create_notification(item.student, 'Registrar', 
                        f"Your {item.document_type.name} has been shipped via LBC. Tracking: {t_no or 'N/A'}. LBC will notify you when package arrives.")
                else:
                    if processing_days:
                        create_notification(item.student, 'Registrar', 
                            f"Your {item.document_type.name} will be ready in {processing_days} day(s). Please proceed to pickup.")
            
            # Explicit redirect with success message
            messages.success(request, f"Success! {ready_count} document(s) updated.")
            return redirect('registrar_dashboard')
        elif action == 'mark_completed': 
            batch.update(status='COMPLETED')
            messages.success(request, f"{batch.count()} document(s) marked as COMPLETED.")
        elif action == 'extend_processing':
            extend_days = request.POST.get('extend_days', '1')
            extend_reason = request.POST.get('extend_reason', '').strip()
            if not extend_reason:
                messages.error(request, 'Please provide a reason for the extension.')
                return redirect('registrar_dashboard')
            try:
                extend_days = int(extend_days)
            except ValueError:
                extend_days = 1
            for item in batch:
                item.processing_days = (item.processing_days or 3) + extend_days
                item.save()
                create_notification(item.student, 'Registrar',
                    f"Processing Extended: Your {item.document_type.name} will require {extend_days} additional day(s). "
                    f"Reason: {extend_reason}. Please expect further updates.")
            messages.success(request, f'Processing extended by {extend_days} day(s). Student has been notified.')
        return redirect('registrar_dashboard')
    return render(request, 'registrar_dashboard.html', {
        'active_requests': active_requests, 
        'history': history,
        'pending_count': pending_count,
        'ready_count': ready_count,
        'paid_count': paid_count,
        'processing_count': processing_count
    })

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
        elif action == 'clear_balance':
            record = get_object_or_404(StudentBalance, id=request.POST.get('balance_id'))
            amount_cleared = record.outstanding_amount
            record.clear_balance()
            log_audit(request.user, 'BALANCE', 'StudentBalance', record.id, f"Cleared balance: ₱{amount_cleared}")
            messages.success(request, f"Balance of ₱{amount_cleared} cleared for {record.student.student_id}")
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
    online_pending = DocumentRequest.objects.filter(is_deleted=False, status='PENDING_CASHIER_APPROVAL').order_by('-created_at')
    awaiting = DocumentRequest.objects.filter(is_deleted=False, status='PAID').order_by('-created_at')
    
    # Combine all active payments into one list
    all_payments = (list(unpaid) + list(online_pending) + list(awaiting))
    # Sort by created_at descending
    all_payments = sorted(all_payments, key=lambda x: x.created_at, reverse=True)
    
    history = DocumentRequest.objects.filter(is_deleted=False, status__in=['PROCESSING', 'READY', 'COMPLETED']).order_by('-created_at')
    collection_history = CollectionLog.objects.all().order_by('-created_at')
    if request.method == 'POST':
        action, req_id = request.POST.get('action'), request.POST.get('request_id')
        doc_req = get_object_or_404(DocumentRequest, id=req_id)
        
        if action == 'confirm_payment':
            # Updated filter: Find the batch by ID and include PENDING_CASHIER_APPROVAL
            batch = DocumentRequest.objects.filter(
                batch_id=doc_req.batch_id, 
                status__in=['PAYMENT_REQUIRED', 'PENDING_CASHIER_APPROVAL']
            )
            
            # Identify if this was an online payment for the log
            was_online = any(item.status == 'PENDING_CASHIER_APPROVAL' for item in batch)
            
            new_no = SystemCounter.get_next_receipt_no()
            
            # Calculate total price considering TOR price overrides and rush processing
            total = 0
            for item in batch:
                total += float(item.get_price())
            
            # Update all items in the batch to PAID
            batch.update(status='PAID', receipt_number=new_no)
            
            CollectionLog.objects.create(
                receipt_number=new_no,
                student_id=doc_req.student.username,
                student_name=doc_req.get_student_name(),
                amount_paid=total,
                documents_included=", ".join([i.document_type.name for i in batch]),
                collected_by=request.user,
                # Set payment method dynamically
                payment_method='ONLINE' if was_online else 'CASH'
            )
            
            log_audit(request.user, 'UPDATE', 'DocumentRequest', doc_req.batch_id, "Payment confirmed by Cashier.")
            return redirect('cashier_dashboard')
    return render(request, 'cashier_dashboard.html', {
        'all_payments': all_payments, 
        'history': history,
        'collection_history': collection_history
    })

# --- 7. PAYMENTS & MISC ---

@csrf_exempt
@api_view(['POST'])
def xendit_webhook(request):
    if request.headers.get('x-callback-token') != getattr(settings, 'XENDIT_CALLBACK_TOKEN', None): return Response(status=403)
    data = request.data
    ext_id, status = data.get('external_id'), data.get('status')
    if status == 'PAID' and ext_id.startswith('BATCH-'):
        batch_id = ext_id.split('-')[1]
        items = DocumentRequest.objects.filter(batch_id=batch_id, status__in=['APPROVED', 'PAYMENT_REQUIRED'])
        if items.exists():
            new_no = SystemCounter.get_next_receipt_no()
            
            # Calculate total price considering TOR price overrides and rush processing
            total = 0
            for item in items:
                total += float(item.get_price())
            
            # Change status to your "Pending" value. 
# Also, remove receipt_number if you want the cashier to assign it later.
            items.update(status='PAID')
            CollectionLog.objects.create(
                receipt_number=new_no, student_id=items.first().student.username, 
                student_name=items.first().get_student_name(), amount_paid=total, 
                documents_included=", ".join([i.document_type.name for i in items]), payment_method='ONLINE'
            )
    return Response(status=200)

def payment_success(request):
    # Check if user is authenticated
    try:
        if request.user.is_authenticated:
            # Update any pending payments to PAID for this user
            pending_payments = DocumentRequest.objects.filter(student=request.user, status__in=['APPROVED', 'PAYMENT_REQUIRED'])
            if pending_payments.exists():
                pending_payments.update(status='PAID')
                messages.success(request, "Payment Verified! Your documents are being processed.")
            else:
                messages.success(request, "Payment completed successfully!")
            return redirect('student_dashboard')
    except Exception as e:
        print(f"Payment success error: {e}")
    
    # Fallback: try to get user from session
    user_id = request.session.get('otp_user_id')
    if user_id:
        return redirect('verify_otp')
    
    # Default fallback
    return redirect('login')

@login_required
def generate_receipt(request, req_id):
    doc_req = get_object_or_404(DocumentRequest, id=req_id)
    is_staff = request.user.groups.filter(name__in=['Registrar', 'Cashier', 'Accounting']).exists()
    if not (doc_req.student == request.user or is_staff or request.user.is_superuser): raise PermissionDenied()
    batch = DocumentRequest.objects.filter(receipt_number=doc_req.receipt_number) if doc_req.receipt_number else DocumentRequest.objects.filter(id=req_id)
    student = StudentMasterList.objects.filter(student_id=doc_req.student.username).first()
    
    # Calculate total considering TOR price overrides and rush processing
    total_amount = 0
    for item in batch:
        total_amount += float(item.get_price())
    
    # Check if LBC delivery is selected
    is_lbc_delivery = doc_req.delivery_method == 'LBC'
    
    return render(request, 'receipt_invoice.html', {
        'doc': doc_req, 
        'batch_items': batch, 
        'student': student, 
        'today': timezone.now(), 
        'total_amount': total_amount, 
        'display_receipt_no': doc_req.receipt_number or "PENDING",
        'is_lbc_delivery': is_lbc_delivery
    })

def staff_login(request):
    if request.user.is_authenticated: django_logout(request)
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            user_groups = user.groups.values_list('name', flat=True)
            if any(role in user_groups for role in ['Registrar', 'Cashier', 'Accounting', 'TOR Desk']) or user.is_superuser or user.username == 'Lotivio01':
                login(request, user)
                if 'Registrar' in user_groups: return redirect('registrar_dashboard')
                if 'Cashier' in user_groups: return redirect('cashier_dashboard')
                if 'TOR Desk' in user_groups or user.username == 'Lotivio01': return redirect('tor_dashboard')
                return redirect('accounting_dashboard')
            else: messages.error(request, "Access denied.")
    return render(request, 'staff_login.html', {'form': AuthenticationForm()})

def logout_view(request):
    is_staff = request.user.is_authenticated and (request.user.groups.filter(name__in=['Registrar', 'Cashier', 'Accounting', 'TOR']).exists() or request.user.is_superuser)
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
        
        # Get or create OTP token with Google Authenticator support
        otp = OTPToken.objects.filter(user=user).first()
        if not otp:
            otp = OTPToken.objects.create(user=user)
        otp.generate_code()
        
        # Get Google Authenticator provisioning URI
        google_auth_uri = otp.get_google_auth_uri()
        
        # Send email with OTP and Google Auth info
        email_message = f"""
Your CATC Portal Login Code: {otp.otp_code}

This code is valid for 10 minutes.

To use Google Authenticator:
1. Download Google Authenticator app on your phone
2. The secret key for setup is: {otp.google_auth_secret}

Or scan this QR code in the Google Authenticator app.
"""
        # Send email and SMS simultaneously using threading
        import threading
        
        def send_email_thread():
            try:
                send_mail('Login OTP', email_message, settings.DEFAULT_FROM_EMAIL, [master_student.email])
            except Exception as e:
                print(f"API Email sending failed: {e}")
        
        def send_sms_thread():
            try:
                send_otp_sms(master_student.phone_number, otp.otp_code)
            except Exception as e:
                print(f"API SMS sending failed: {e}")
        
        # Start both email and SMS threads simultaneously
        email_thread = threading.Thread(target=send_email_thread)
        sms_thread = threading.Thread(target=send_sms_thread)
        email_thread.start()
        sms_thread.start()
        # Wait for both to complete
        email_thread.join()
        sms_thread.join()
        
        cache.set(f"otp_api_lock_{sid}", True, 60)
        return Response({
            "status": "success", 
            "masked_email": master_student.masked_email, 
            "masked_phone": master_student.masked_phone,
            "google_auth_secret": otp.google_auth_secret
        })
    return Response(status=404)

@api_view(['POST'])
def api_verify_otp(request):
    sid, code = request.data.get('student_id', '').upper(), request.data.get('otp_code')
    user = get_object_or_404(User, username=sid)
    threshold = timezone.now() - timedelta(minutes=10)
    otp = OTPToken.objects.filter(user=user, is_verified=False, created_at__gte=threshold).last()
    
    if otp:
        # Check if user is entering a Google Authenticator code
        if otp.google_auth_enabled and otp.google_auth_secret:
            try:
                import pyotp
                totp = pyotp.TOTP(otp.google_auth_secret)
                if totp.verify(code):
                    otp.is_verified = True
                    otp.save()
                    return Response({"status": "success", "access": str(RefreshToken.for_user(user).access_token)})
            except ImportError:
                pass
        
        # Fall back to regular OTP code
        if otp.otp_code == code:
            otp.is_verified = True
            otp.save()
            return Response({"status": "success", "access": str(RefreshToken.for_user(user).access_token)})
    
    return Response({"status": "error", "message": "Expired/Invalid."}, status=400)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_student_dashboard(request):
    return Response(RequestSerializer(DocumentRequest.objects.filter(student=request.user, is_deleted=False).order_by('-created_at'), many=True).data)

# Import at module level for performance
import urllib.request
import urllib.error
import logging

logger = logging.getLogger(__name__)


def _get_tracking_data(tracking_num):
    """
    Fetch tracking data from LBC API.
    Returns tuple: (success: bool, data: dict, error: str or None)
    """
    lbc_api_host = os.getenv('LBC_API_HOST', 'localhost')
    lbc_api_port = os.getenv('LBC_API_PORT', '3000')
    api_url = f'http://{lbc_api_host}:{lbc_api_port}/api/track/{tracking_num}'
    
    try:
        req = urllib.request.Request(api_url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return (True, data.get('data', {}), None)
    except urllib.error.HTTPError as e:
        logger.error(f"LBC API HTTP error: {e.code} - {e.reason}")
        return (False, None, f"HTTP Error: {e.code}")
    except urllib.error.URLError as e:
        logger.error(f"LBC API connection error: {e.reason}")
        return (False, None, "Connection failed")
    except json.JSONDecodeError as e:
        logger.error(f"LBC API JSON decode error: {e}")
        return (False, None, "Invalid response format")
    except Exception as e:
        logger.error(f"Unexpected error fetching tracking: {e}")
        return (False, None, str(e))


def _get_mock_tracking_data(tracking_num):
    """Generate mock tracking data for development/fallback."""
    return {
        'trackingNumber': tracking_num,
        'status': 'IN TRANSIT',
        'origin': 'Legazpi City, Albay',
        'destination': 'To be determined',
        'timeline': [
            {'dateTime': timezone.now().strftime('%Y-%m-%d %H:%M'), 'location': 'Legazpi City, Albay', 'status': 'Shipment booked'},
            {'dateTime': '', 'location': 'Legazpi City Hub', 'status': 'Picked up by LBC Rider'},
            {'dateTime': '', 'location': 'Legazpi City Hub', 'status': 'In transit to destination'},
            {'dateTime': '', 'location': 'Destination', 'status': 'Out for delivery'},
        ]
    }


def _save_tracking_notification(user, tracking_num, tracking_data):
    """
    Helper function to save tracking result as notification.
    Returns: (success: bool, error: str or None)
    """
    try:
        status = tracking_data.get('status', 'Unknown') if tracking_data else 'Unknown'
        location = tracking_data.get('destination', 'Unknown') if tracking_data else 'Unknown'
        
        message = f"📦 Shipment Tracking Update\n"
        message += f"Tracking #: {tracking_num}\n"
        message += f"Status: {status}\n"
        message += f"Destination: {location}"
        
        Notification.objects.create(
            user=user,
            sender_role='System',
            message=message
        )
        logger.info(f"Tracking notification saved for user {user.id}: {tracking_num}")
        return (True, None)
    except Exception as e:
        logger.error(f"Failed to save tracking notification: {e}")
        return (False, str(e))


# LBC Tracking API View
@api_view(['GET'])
@login_required
def track_lbc_shipment(request, tracking_num):
    """
    Track LBC shipment using the LBC API.
    Returns tracking data in consistent format.
    """
    # Validate input
    if not tracking_num or len(tracking_num.strip()) == 0:
        return JsonResponse({
            'success': False,
            'error': 'Tracking number is required'
        }, status=400)
    
    tracking_num = tracking_num.strip()
    
    # Try to get real tracking data
    success, data, error = _get_tracking_data(tracking_num)
    
    if success and data:
        return JsonResponse({
            'success': True,
            'data': data
        })
    
    # Fallback to mock data if API unavailable
    logger.info(f"Using mock tracking data for {tracking_num} (LBC API unavailable: {error})")
    mock_data = _get_mock_tracking_data(tracking_num)
    
    return JsonResponse({
        'success': True,
        'data': mock_data,
        'note': 'Demo mode - LBC API unavailable'
    })


@api_view(['POST'])
@login_required
def track_and_notify(request, tracking_num):
    """
    Track LBC shipment and save notification.
    Combines tracking + notification in one call.
    """
    if not tracking_num or len(tracking_num.strip()) == 0:
        return JsonResponse({
            'success': False,
            'error': 'Tracking number is required'
        }, status=400)
    
    tracking_num = tracking_num.strip()
    
    # Get tracking data
    success, data, error = _get_tracking_data(tracking_num)
    
    tracking_data = data if (success and data) else _get_mock_tracking_data(tracking_num)
    
    # Save notification
    notif_success, notif_error = _save_tracking_notification(
        request.user, tracking_num, tracking_data
    )
    
    if not notif_success:
        logger.warning(f"Failed to save notification: {notif_error}")
    
    return JsonResponse({
        'success': True,
        'data': tracking_data,
        'notification_saved': notif_success
    })

# TOR Page Counting Dashboard for Mr. Lotivio
@login_required
def tor_dashboard(request):
    # Check if user is authorized (Mr. Lotivio or admin)
    if not (request.user.username == 'Lotivio01' or request.user.is_superuser or request.user.is_staff):
        raise PermissionDenied()
    
    # Get TOR requests that need page counting
    # These are TOR requests sent by registrar but need page count
    tor_requests = DocumentRequest.objects.filter(
        document_type__name__icontains='TOR',
        status__in=['APPROVED', 'PAYMENT_REQUIRED', 'PAID', 'READY'],
        is_deleted=False,
        tor_page_count__isnull=False
    ).select_related('document_type', 'student').order_by('-created_at')[:50]  # Last 50 processed
    
    # Also get TRANSCRIPT requests that have been processed
    transcript_processed = DocumentRequest.objects.filter(
        document_type__name__icontains='TRANSCRIPT',
        status__in=['APPROVED', 'PAYMENT_REQUIRED', 'PAID', 'READY'],
        is_deleted=False,
        tor_page_count__isnull=False
    ).select_related('document_type', 'student').order_by('-created_at')[:50]
    
    # Combine both
    tor_requests = tor_requests | transcript_processed
    
    # Also get TOR requests that are PENDING_TOR_COUNT (new requests waiting for page count)
    processing_tor = DocumentRequest.objects.filter(
        document_type__name__icontains='TOR',
        status='PENDING_TOR_COUNT',
        is_deleted=False
    ).select_related('document_type', 'student').order_by('-created_at')
    
    # Also get TRANSCRIPT requests in PENDING_TOR_COUNT status
    transcript_requests = DocumentRequest.objects.filter(
        document_type__name__icontains='TRANSCRIPT',
        status='PENDING_TOR_COUNT',
        is_deleted=False
    ).select_related('document_type', 'student').order_by('-created_at')
    
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
            batch_items = DocumentRequest.objects.filter(batch_id=tor.batch_id, is_deleted=False)
            tor.batch_count = batch_items.count()
            tor.has_auth = any('Authentication' in str(item.document_type.name) for item in batch_items if item.id != tor.id)
        else:
            tor.batch_count = 1
            tor.has_auth = False
    
    # For processing_tor, also check for batched Authentication
    for tor in processing_tor:
        if tor.batch_id:
            batch_items = DocumentRequest.objects.filter(batch_id=tor.batch_id, is_deleted=False)
            tor.batch_count = batch_items.count()
            # Check if there's an Authentication request in the same batch
            auth_items = [item for item in batch_items if 'Authentication' in str(item.document_type.name)]
            if auth_items:
                tor.has_auth = True
                tor.auth_price = auth_items[0].get_price() if auth_items[0].document_type.price else 0
            else:
                tor.has_auth = False
                tor.auth_price = 0
        else:
            tor.batch_count = 1
            tor.has_auth = False
            tor.auth_price = 0
    
    context = {
        'tor_requests': tor_requests,
        'processing_tor': processing_tor,
        'tor_price_per_page': TOR_PRICE_PER_PAGE,
        'rush_multiplier': RUSH_MULTIPLIER,
    }
    
    return render(request, 'tor_dashboard.html', context)

@login_required
def submit_tor_page_count(request):
    """
    Handle page count submission from Mr. Lotivio
    """
    if not (request.user.username == 'Lotivio01' or request.user.is_superuser or request.user.is_staff):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    
    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        page_count = request.POST.get('page_count')
        
        try:
            doc_request = DocumentRequest.objects.get(id=request_id)
            doc_request.tor_page_count = int(page_count)
            
            # Calculate the TOR price based on page count
            TOR_PRICE_PER_PAGE = 100
            tor_price = doc_request.tor_page_count * TOR_PRICE_PER_PAGE
            
            # Apply rush multiplier if rush processing
            if doc_request.rush_processing:
                tor_price = tor_price * 2
            
            # Check if this is a FREE TOR request (tor_price_override = 0)
            is_free_tor = doc_request.tor_price_override is not None and doc_request.tor_price_override == 0
            
            # Check if there's a batch with other requests
            if doc_request.batch_id:
                batch_items = DocumentRequest.objects.filter(batch_id=doc_request.batch_id, is_deleted=False)
                total_price = tor_price  # Start with TOR price
                
                # Add other items' price if exists (Authentication, etc.)
                for item in batch_items:
                    if item.id != doc_request.id:
                        # For Authentication or other paid items
                        if 'Authentication' in str(item.document_type.name):
                            total_price += item.get_price()
                        # Set all other items to APPROVED
                        if item.status != 'APPROVED':
                            item.status = 'APPROVED'
                            item.save()
                
                # If this is a FREE TOR and there are other paid items in batch, 
                # keep the batch as APPROVED so student can pay for other items
                # If this is FREE TOR and it's the ONLY item in batch, mark as PAID directly
                if is_free_tor and batch_items.count() == 1:
                    # This is a FREE TOR request - no payment needed
                    doc_request.price = 0
                    doc_request.status = 'PAID'
                    doc_request.save()
                    
                    # Create notification for student
                    Notification.objects.create(
                        user=doc_request.student,
                        sender_role='TOR Desk',
                        message=f'Your TOR request ({doc_request.document_type.name}) has been processed. {page_count} pages. Your first TOR request as a graduate is FREE!'
                    )
                    
                    # Log the action
                    log_audit(request.user, 'UPDATE', 'DocumentRequest', str(doc_request.id), f"TOR page count set to {page_count}. FREE request - marked as PAID.")
                    
                    return JsonResponse({'success': True, 'message': f'Page count submitted. FREE TOR - marked as PAID.'})
                else:
                    # Regular paid TOR or batch with other items
                    doc_request.price = total_price
                    doc_request.status = 'APPROVED'
                    doc_request.save()
                    
                    # Create notification for student
                    Notification.objects.create(
                        user=doc_request.student,
                        sender_role='TOR Desk',
                        message=f'Your TOR request ({doc_request.document_type.name}) has been processed. {page_count} pages. Total: ₱{tor_price}. Please proceed to payment.'
                    )
                    
                    # Log the action
                    log_audit(request.user, 'UPDATE', 'DocumentRequest', str(doc_request.id), f"TOR page count set to {page_count}. Price: ₱{tor_price}")
                    
                    return JsonResponse({'success': True, 'message': f'Page count submitted. Price: ₱{tor_price}'})
            else:
                # No batch - single TOR request
                if is_free_tor:
                    doc_request.price = 0
                    doc_request.status = 'PAID'
                    doc_request.save()
                    
                    # Create notification for student
                    Notification.objects.create(
                        user=doc_request.student,
                        sender_role='TOR Desk',
                        message=f'Your TOR request ({doc_request.document_type.name}) has been processed. {page_count} pages. Your first TOR request as a graduate is FREE!'
                    )
                    
                    log_audit(request.user, 'UPDATE', 'DocumentRequest', str(doc_request.id), f"TOR page count set to {page_count}. FREE request - marked as PAID.")
                    
                    return JsonResponse({'success': True, 'message': f'Page count submitted. FREE TOR - marked as PAID.'})
                else:
                    total_price = tor_price
                    doc_request.price = total_price
                    # Set to APPROVED so student can proceed to pay
                    doc_request.status = 'APPROVED'
                    doc_request.save()
                    
                    # Create notification for student
                    Notification.objects.create(
                        user=doc_request.student,
                        sender_role='TOR Desk',
                        message=f'Your TOR request ({doc_request.document_type.name}) has been processed. {page_count} pages. Total: ₱{tor_price}. Please proceed to payment.'
                    )
                    
                    # Log the action
                    log_audit(request.user, 'UPDATE', 'DocumentRequest', str(doc_request.id), f"TOR page count set to {page_count}. Price: ₱{tor_price}")
                    
                    return JsonResponse({'success': True, 'message': f'Page count submitted. Price: ₱{tor_price}'})
            
        except DocumentRequest.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Request not found'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

@login_required
@role_required(allowed_roles=['Student'])
def pay_with_xendit(request, batch_id):
    batch = DocumentRequest.objects.filter(batch_id=batch_id, status__in=['APPROVED', 'PAYMENT_REQUIRED'])
    if not batch.exists(): 
        # Debug: check what status the batch has
        existing = DocumentRequest.objects.filter(batch_id=batch_id).first()
        if existing:
            print(f"DEBUG: Batch {batch_id} exists but status is {existing.status}")
            # Check if already PAID (e.g., FREE TOR requests)
            if existing.status == 'PAID':
                messages.info(request, "This request has already been processed.")
        else:
            print(f"DEBUG: Batch {batch_id} does not exist")
        return redirect('student_dashboard')
    
    # Calculate total price, considering TOR price overrides and rush processing
    total = 0
    for item in batch:
        total += float(item.get_price())
    
    # Handle FREE requests (total = 0)
    if total <= 0:
        # Mark as PAID directly without going through Xendit
        batch.update(status='PAID')
        # Create notifications for all items
        for item in batch:
            Notification.objects.create(
                user=item.student,
                sender_role='System',
                message=f'Your {item.document_type.name} request has been confirmed at no cost.'
            )
        messages.success(request, "Your request has been confirmed! No payment required.")
        return redirect('student_dashboard')
    
    auth = base64.b64encode(f"{settings.XENDIT_SECRET_KEY}:".encode()).decode()
    data = {"external_id": f"BATCH-{batch_id}-{uuid.uuid4().hex[:6]}", "amount": total, "description": f"Payment Batch {batch_id}", "payer_email": request.user.email, "success_redirect_url": settings.XENDIT_REDIRECT_URL, "currency": "PHP", "payment_methods": ["GCASH", "PAYMAYA", "CARD"]}
    try:
        res = requests.post("https://api.xendit.co/v2/invoices", headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"}, data=json.dumps(data), timeout=10)
        if res.status_code in [200, 201]: return redirect(res.json().get("invoice_url"))
        # Handle non-success response from Xendit
        messages.error(request, f"Payment processing failed. Status: {res.status_code}")
    except requests.exceptions.Timeout:
        messages.error(request, "Payment request timed out. Please try again.")
    except Exception as e:
        messages.error(request, f"Xendit connection failed: {str(e)}")
    return redirect('student_dashboard')


@api_view(['GET'])
@permission_classes([AllowAny])
def get_document_types(request):
    docs = DocumentType.objects.filter(is_active=True).values('id', 'name', 'price')
    return Response(list(docs))
