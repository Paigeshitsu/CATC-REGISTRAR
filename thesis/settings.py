from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-0$-m$)1sf1q1syiik60qk3ccqf0mrs*ytyh62j36c#s4!e6*o4'

DEBUG = True

ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party apps
    'rest_framework',      # Added for Mobile App
    'corsheaders',         # Added for Mobile App
    'requests_app', 
]


MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # This must be at the very top
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

CORS_ALLOW_ALL_ORIGINS = True 

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

# Database
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
CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:8000', 'http://localhost:8000']
CSRF_COOKIE_SECURE = False 

# --- EMAIL CONFIGURATION (GMAIL SMTP) ---

# Email backend for Gmail SMTP
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

# Gmail SMTP settings
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'rivengod18@gmail.com'
EMAIL_HOST_PASSWORD = 'wvtl rnnn ygun coxe'

# Default sender address
DEFAULT_FROM_EMAIL = 'CATC Portal <rivengod18@gmail.com>'

# NOTE: To switch back to console backend for testing, uncomment the line below:
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# --- SEMAPHORE SMS API CONFIGURATION ---
SEMAPHORE_API_KEY = 'a49cb936fca6db2dc238e4aba043d59b'
SEMAPHORE_SENDER_NAME = 'CATC Portal'

# --- CORS CONFIGURATION ---
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
]

XENDIT_SECRET_KEY = "xnd_development_r74WN7uDM75BGgolHprlxlcOpPaMPujI4C6PCtuwiDzZld8vZzCuZOtesrliMxV"
# URL where Xendit will send the student back after payment
XENDIT_REDIRECT_URL = "http://127.0.0.1:8000/payment/success/"