from django.contrib.admin import AdminSite
from django.utils.safestring import mark_safe


class CustomAdminSite(AdminSite):
    """
    Custom Admin Site with CATC dashboard theme styling.
    This inherits from Django's default AdminSite but adds custom styling.
    """
    
    # Custom admin header (the blue gradient banner)
    site_header = mark_safe('''
        <div style="display: flex; align-items: center; gap: 15px;">
            <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" fill="white" class="bi bi-shield-lock" viewBox="0 0 16 16">
                <path d="M8 1a2 2 0 0 1 2 2v4H6V3a2 2 0 0 1 2-2zm3 6V3a3 3 0 0 0-6 0v4a2 2 0 0 0-2 2v5a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"/>
            </svg>
            <div>
                <div style="font-weight: bold; font-size: 1.3rem; line-height: 1.2;">CATC Administrator</div>
                <div style="font-size: 0.75rem; opacity: 0.85;">Document Request Management System</div>
            </div>
        </div>
    ''')
    
    # Title shown in browser tab
    site_title = 'CATC Admin'
    
    # Index title
    index_title = 'Dashboard'
    
    # Custom CSS to match dashboard theme
    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',)
        }


# Create instance of custom admin site
custom_admin_site = CustomAdminSite(name='admin')

# Register Django's built-in auth models
from django.contrib.auth.models import Group, User
custom_admin_site.register(Group)
custom_admin_site.register(User)

# Register models from requests_app by copying from default admin
from django.contrib import admin as default_admin
from django.apps import apps

def copy_registrations_to_custom_site(app_name, custom_site, default_site):
    """Copy model registrations from default admin to custom admin."""
    try:
        app_config = apps.get_app_config(app_name)
        for model in app_config.get_models():
            if model in default_site._registry:
                model_admin = default_site._registry.get(model)
                if model_admin:
                    custom_site.register(model, type(model_admin))
    except LookupError:
        pass

# Copy registrations from requests_app/admin.py
copy_registrations_to_custom_site('requests_app', custom_admin_site, default_admin.site)
