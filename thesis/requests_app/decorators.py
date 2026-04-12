from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.contrib import messages

def role_required(allowed_roles=[]):
    def decorator(view_func):
        def wrap(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            # Check if user has any of the allowed roles
            user_groups = request.user.groups.values_list('name', flat=True)
            
            if any(role in user_groups for role in allowed_roles) or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            else:
                # INSTEAD OF CRASHING: Redirect them to their actual home
                if 'Student' in user_groups:
                    return redirect('student_dashboard')
                elif 'Registrar' in user_groups:
                    return redirect('registrar_dashboard')
                elif 'Cashier' in user_groups:
                    return redirect('cashier_dashboard')
                elif 'Accounting' in user_groups:
                    return redirect('accounting_dashboard')
                
                # If they have no recognized role
                messages.error(request, "Access Denied: Invalid Role.")
                return redirect('login')
        return wrap
    return decorator