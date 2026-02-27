from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from thesis.admin import custom_admin_site

urlpatterns = [
    # Custom Django Admin panel with blue gradient theme
    path('admin/', custom_admin_site.urls),

    # This connects the main website to your requests_app
    # Empty string '' means the home page will use your app's URLs
    path('', include('requests_app.urls')),
]

# This part allows the browser to display uploaded files (like receipts)
# It only runs during development (when DEBUG is True)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
