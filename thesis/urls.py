from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # The default Django Admin panel (where you create Roles/Groups)
    path('admin/', admin.site.urls),

    # This connects the main website to your requests_app
    # Empty string '' means the home page will use your app's URLs
    path('', include('requests_app.urls')),
]

# This part allows the browser to display uploaded files (like receipts)
# It only runs during development (when DEBUG is True)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)