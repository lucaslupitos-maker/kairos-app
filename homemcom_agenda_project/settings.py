from pathlib import Path
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'troque-esta-chave-em-producao'

DEBUG = True

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    ".railway.app",
    "web-production-6e6e2.up.railway.app",
]

CSRF_TRUSTED_ORIGINS = [
    "https://*.railway.app",
    "https://web-production-6e6e2.up.railway.app",
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'agenda',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

'whitenoise.middleware.WhiteNoiseMiddleware',

'agenda.middleware.PaymentGateMiddleware',
]

ROOT_URLCONF = 'homemcom_agenda_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],  # pasta global de templates
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',

'agenda.context_processors.current_account',
            ],
        },
    },
]

WSGI_APPLICATION = 'homemcom_agenda_project.wsgi.application'


# Banco de dados simples (sqlite)
DATABASES = {
    'default': dj_database_url.config(
        default='sqlite:///db.sqlite3',
        conn_max_age=600
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'pt-br'

TIME_ZONE = 'America/Sao_Paulo'

USE_I18N = True

USE_TZ = True


STATIC_URL = 'static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Auth
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'homemcom_dashboard'
LOGOUT_REDIRECT_URL = 'login'


STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# PIX (Bloco 1)
PIX_CHAVE = "42506340866"  # seu CPF (sem pontuação)
PIX_BANCO = "Nubank"
PIX_BENEFICIARIO = "Lucas Castiglioni Toledo de Souza"
PIX_VALOR_SUGERIDO = None  # ou 39.90, se quiser sugerir
PIX_QR_IMAGE = "agenda/img/pix_nubank_qr.png"  # caminho dentro de /static/
WHATSAPP_SUPORTE = "5519981514883"  # seu número com DDI+DDD (sem +, sem espaços)