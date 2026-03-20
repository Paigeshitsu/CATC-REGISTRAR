import os
from pathlib import Path
from dotenv import load_dotenv

# 1. Load environment variables from .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# 2. Security Settings from Env
SECRET_KEY = os.getenv('SECRET_KEY')

# os.getenv returns a string, so we compare it to 'True' to get a Boolean
DEBUG = os.getenv('DEBUG', 'False') == 'True'

# Pull list from env, split by comma
# This tells Django to split the string by the comma
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '*').split(',')
ALLOWED_HOSTS.append('127.0.0.1')  # Ensure localhost is always allowed

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# 3. Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party apps
    'rest_framework',      
    'corsheaders',         
    'requests_app', 
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

CORS_ALLOWED_ORIGINS = [
    "http://76.13.220.96",
    "https://catcreg.online",
]

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

ROOT_URLCONF = 'thesis.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'thesis.wsgi.application'

# 4. Database: Setup for transition to PostgreSQL
# Change this when moving to production
if os.getenv('DATABASE_URL'): # If you provide a DB URL in .env
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.config(conn_max_age=600, ssl_require=True)
    }
else:
    # Standard SQLite for Development
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True

# Static and Media Files
# THIS MUST BE A STRING (TEXT), NOT BASE_DIR / 'static/'
STATIC_URL = 'static/'

# These two are folders, so BASE_DIR / is okay here
STATIC_ROOT = BASE_DIR / 'staticfiles'

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Media settings (for signatures/receipts)
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Authentication & Redirection ---
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'student_dashboard'
LOGOUT_REDIRECT_URL = 'login'

# --- Session & Security Settings ---
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 3600  
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True

# CSRF Settings
CSRF_TRUSTED_ORIGINS = [
    'https://catcreg.online',
    'https://www.catcreg.online'
]

# Only use Secure Cookies if not in Debug mode (Production)
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

# 5. Secure Email Configuration
# Email settings - Use SMTP for Gmail
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # Uncomment for testing only
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = f'CATC Portal <{EMAIL_HOST_USER}>'

# 6. Secure Semaphore SMS API
SEMAPHORE_API_KEY = os.getenv('SEMAPHORE_API_KEY')
SEMAPHORE_SENDER_NAME = os.getenv('SEMAPHORE_SENDER_NAME', 'CATC Portal')

# 6b. iProg SMS API
IPROG_SMS_API_TOKEN = os.getenv('IPROG_SMS_API_TOKEN', '0f00f99e0ed2eb37be04627a929f4b5075f20616')
IPROG_SMS_API_URL = os.getenv('IPROG_SMS_API_URL', 'https://www.iprogsms.com/api/v1/sms_messages')

# 6c. SMS API (Primary)
SMS_API_KEY = os.getenv('SMS_API_KEY')
SMS_API_URL = os.getenv('SMS_API_URL', 'https://smsapiph.onrender.com/api/v1/send/sms')

# 7. Secure Xendit Configuration
XENDIT_SECRET_KEY = os.getenv('XENDIT_SECRET_KEY')
# IMPORTANT: The verification logic in your webhook requires this token from Xendit dashboard
XENDIT_CALLBACK_TOKEN = os.getenv('XENDIT_CALLBACK_TOKEN') 
XENDIT_REDIRECT_URL = os.getenv('XENDIT_REDIRECT_URL', 'https://catcreg.online/payment/success/') 

# 8. Site Configuration (Used for QR code generation)
SITE_URL = "https://catcreg.online" if not DEBUG else "http://127.0.0.1:8000"

# 9. Custom Admin Site Configuration
# This makes Django use our custom admin site with CATC branding
ADMIN_SITE = 'thesis.admin.custom_admin_site'
ADMIN_SITE_TITLE = 'CATC Admin'
ADMIN_SITE_HEADER = 'CATC Administrator'

# 10. LBC CBIP Track and Trace API Configuration
LBC_API_KEY = os.getenv('LBC_API_KEY')
LBC_SUBSCRIPTION_KEY = os.getenv('LBC_SUBSCRIPTION_KEY')

# 11. LBC API Host Configuration (for VPS deployment)
LBC_API_HOST = os.getenv('LBC_API_HOST', 'localhost')
LBC_API_PORT = os.getenv('LBC_API_PORT', '3000')
