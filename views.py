from django.shortcuts import render, redirect, get_object_ some_or_404
from django.contrib.auth.decorators import login_required
from .models import DocumentRequest
from .forms import StudentRequestForm
from .decorators import role_required

# --- STUDENT SIDE ---
@login_required
@role_required(allowed_roles=['Student'])
def student_dashboard(request):
    user_requests = DocumentRequest.objects.filter(student=request.user).order_by('-created_at')
    form = StudentRequestForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        new_req = form.save(commit=False)
        new_req.student = request.user
        new_req.save()
        return redirect('student_dashboard')
        
    return render(request, 'dashboard.html', {'form': form, 'requests': user_requests})

# --- REGISTRAR SIDE ---
@role_required(allowed_roles=['Registrar'])
def registrar_queue(request):
    # Flow: R_Queue [Inbox: Document Requests]
    reqs = DocumentRequest.objects.filter(status='PENDING')
    if request.method == 'POST':
        req_id = request.POST.get('req_id')
        action = request.POST.get('action')
        req = get_object_or_404(DocumentRequest, id=req_id)
        # Flow: R_Decision {Needs Payment?}
        req.status = 'PAYMENT_REQUIRED' if action == 'approve' else 'REJECTED'
        req.save()
        return redirect('registrar_queue')
    return render(request, 'registrar_queue.html', {'requests': reqs})

# --- CASHIER SIDE ---
@role_required(allowed_roles=['Cashier'])
def cashier_queue(request):
    # Flow: C_Queue [Inbox: Payment Requests]
    reqs = DocumentRequest.objects.filter(status='PAYMENT_REQUIRED')
    if request.method == 'POST':
        req_id = request.POST.get('req_id')
        req = get_object_or_404(DocumentRequest, id=req_id)
        # Flow: C_Approve [Approve Payment]
        req.status = 'COMPLETED'
        req.save()
        return redirect('cashier_queue')
    return render(request, 'cashier_queue.html', {'requests': reqs})