from django.core.exceptions import PermissionDenied

def role_required(allowed_roles=[]):
    def decorator(view_func):
        def wrap(request, *args, **kwargs):
            if request.user.groups.filter(name__in=allowed_roles).exists() or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return wrap
    return decorator