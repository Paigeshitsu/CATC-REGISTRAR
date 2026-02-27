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
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '*').split(',')

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
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = '/media/'
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
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = f'CATC Portal <{EMAIL_HOST_USER}>'

# 6. Secure Semaphore SMS API
SEMAPHORE_API_KEY = os.getenv('SEMAPHORE_API_KEY')
SEMAPHORE_SENDER_NAME = os.getenv('SEMAPHORE_SENDER_NAME', 'CATC Portal')

# 7. Secure Xendit Configuration
XENDIT_SECRET_KEY = os.getenv('XENDIT_SECRET_KEY')
# IMPORTANT: The verification logic in your webhook requires this token from Xendit dashboard
XENDIT_CALLBACK_TOKEN = os.getenv('XENDIT_CALLBACK_TOKEN') 
XENDIT_REDIRECT_URL = "https://catcreg.online/payment/success/" if not DEBUG else "http://127.0.0.1:8000/payment/success/"

# 8. Site Configuration (Used for QR code generation)
SITE_URL = "https://catcreg.online" if not DEBUG else "http://127.0.0.1:8000"

# 9. Custom Admin Site Configuration
# This makes Django use our custom admin site with CATC branding
ADMIN_SITE = 'thesis.admin.custom_admin_site'
ADMIN_SITE_TITLE = 'CATC Admin'
ADMIN_SITE_HEADER = 'CATC Administrator'
