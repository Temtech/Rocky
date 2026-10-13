import os
from pathlib import Path
from urllib.parse import urlsplit, unquote
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
DEBUG = os.environ.get('DEBUG', '0') == '1'
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError('DJANGO_SECRET_KEY is required outside local development')
    local = BASE_DIR / '.local'
    local.mkdir(exist_ok=True)
    keyfile = local / 'secret'
    if not keyfile.exists():
        from django.core.management.utils import get_random_secret_key
        keyfile.write_text(get_random_secret_key())
        keyfile.chmod(0o600)
    SECRET_KEY = keyfile.read_text()
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
INSTALLED_APPS = ['django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','operations']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','whitenoise.middleware.WhiteNoiseMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','operations.middleware.ActiveSessionMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'rocky.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages','operations.context.brand']}}]
WSGI_APPLICATION = 'rocky.wsgi.application'
u = urlsplit(os.environ.get('DATABASE_URL', 'postgresql://rocky@127.0.0.1:5432/rocky'))
DATABASES = {'default': {'ENGINE':'django.db.backends.postgresql','NAME':u.path.lstrip('/'),'USER':unquote(u.username or ''),'PASSWORD':unquote(u.password or ''),'HOST':u.hostname or '127.0.0.1','PORT':u.port or 5432,'CONN_MAX_AGE':0 if os.environ.get('VERCEL') else 60,'OPTIONS':{'sslmode':os.environ.get('DB_SSLMODE','prefer')}}}
AUTH_USER_MODEL = 'operations.User'
AUTH_PASSWORD_VALIDATORS = [{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator','OPTIONS':{'min_length':12}},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
PASSWORD_HASHERS = ['django.contrib.auth.hashers.Argon2PasswordHasher','django.contrib.auth.hashers.PBKDF2PasswordHasher']
TIME_ZONE = 'America/Denver'
USE_TZ = True
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR/'static']
STATIC_ROOT = BASE_DIR/'staticfiles'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO','https')
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_AGE = 43200
PASSWORD_RESET_TIMEOUT = 3600
EMAIL_PROVIDER = os.environ.get('EMAIL_PROVIDER','smtp')
RESEND_API_KEY = os.environ.get('RESEND_API_KEY','')
EMAIL_BACKEND = 'operations.resend_backend.EmailBackend' if EMAIL_PROVIDER=='resend' else 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS','1') == '1'
EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL','0') == '1'
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL','accounts@localhost')
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGGING = {'version':1,'disable_existing_loggers':False,'filters':{'redact':{'()':'operations.logging.RedactResetLinks'}},'handlers':{'safe_console':{'class':'logging.StreamHandler','filters':['redact']}},'loggers':{'django.request':{'handlers':['safe_console'],'level':'WARNING','propagate':False},'django.server':{'handlers':['safe_console'],'level':'INFO','propagate':False}}}
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
CSRF_TRUSTED_ORIGINS = [x for x in os.environ.get('CSRF_TRUSTED_ORIGINS','').split(',') if x]
SECURE_REFERRER_POLICY = 'same-origin'

# Trust only the platform-assigned host for this deployment, not all vercel.app domains.
if os.environ.get('VERCEL_URL'):
    ALLOWED_HOSTS.append(os.environ['VERCEL_URL'])
    CSRF_TRUSTED_ORIGINS.append('https://'+os.environ['VERCEL_URL'])
