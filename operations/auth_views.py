import hashlib
import logging
from datetime import timedelta
from django.contrib.auth import views as auth, login
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.forms import SetPasswordForm,AuthenticationForm
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction, DatabaseError
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.contrib import messages
from .models import User,RateLimit,Audit

def limited(request,scope,maximum=8):
    raw=f'{scope}:{request.META.get("REMOTE_ADDR", "unknown")}'
    key=hashlib.sha256(raw.encode()).hexdigest()
    with transaction.atomic():
        row,_=RateLimit.objects.get_or_create(key=key)
        row=RateLimit.objects.select_for_update().get(key=key)
        if timezone.now()-row.window>timedelta(minutes=15): row.count=0; row.window=timezone.now()
        row.count+=1; row.save()
        return row.count>maximum

class EmailAuthenticationForm(AuthenticationForm):
    def clean_username(self): return self.cleaned_data['username'].strip().lower()

class LoginView(auth.LoginView):
    authentication_form=EmailAuthenticationForm
    template_name='registration/login.html'
    def post(self,request,*args,**kwargs):
        try:
            if limited(request,'login'): return HttpResponse('Too many attempts. Try again in 15 minutes.',status=429)
            return super().post(request,*args,**kwargs)
        except DatabaseError as exc:
            request.session.clear()
            request.user=AnonymousUser()
            cause=exc.__cause__
            text=str(exc).lower()
            if getattr(cause,'sqlstate',None)=='42P01' or ('relation' in text and 'does not exist' in text):
                category='missing_schema_run_migrations'
            elif 'certificate' in text:
                category='database_tls_configuration'
            elif 'password authentication failed' in text:
                category='database_authentication'
            elif 'connection refused' in text or 'could not translate host' in text or 'name or service not known' in text:
                category='database_connection'
            else:
                category='database_configuration'
            # Never log the raw exception, SQL parameters, connection URL or posted credentials.
            logging.getLogger('django.request').error('Login database unavailable: category=%s exception=%s',category,type(exc).__name__)
            form=self.get_form_class()(request=request,initial={'username':request.POST.get('username','')})
            context=self.get_context_data(form=form)
            context['storage_error']='Sign-in is temporarily unavailable. Your login has not been completed. Please contact management.'
            response=self.render_to_response(context)
            response.status_code=503
            response['Retry-After']='60'
            return response
    def form_valid(self,form):
        with transaction.atomic():
            result=super().form_valid(form)
            self.request.session['version']=self.request.user.session_version
            Audit.objects.create(actor=self.request.user,action='account.login',target=str(self.request.user.pk))
            return result

def email_configured():
    return bool(settings.RESEND_API_KEY) if settings.EMAIL_BACKEND=='operations.resend_backend.EmailBackend' else bool(settings.EMAIL_HOST)

def email_reset(request,user):
    if not email_configured(): raise RuntimeError('Configure Resend API credentials or SMTP before sending invitations or resets.')
    uid=urlsafe_base64_encode(force_bytes(user.pk)); token=default_token_generator.make_token(user)
    path=reverse('reset-confirm',args=[uid,token])
    link=request.build_absolute_uri(path)
    send_mail('Rocky’s · Secure account access',f'A secure password setup or reset was requested for your Rocky’s account.\n\n{link}\n\nThis single-use link expires in one hour. If you did not request it, contact management.',settings.DEFAULT_FROM_EMAIL,[user.email],fail_silently=False)

def forgot(request):
    if request.method=='POST':
        if limited(request,'reset',5): return HttpResponse('Too many attempts. Try again in 15 minutes.',status=429)
        user=User.objects.filter(email__iexact=request.POST.get('email','').strip(),is_active=True).first()
        if user:
            try: email_reset(request,user)
            except Exception:
                Audit.objects.create(actor=None,action='email.reset_delivery_failed',target=str(user.pk))
        return render(request,'registration/reset_done.html')
    return render(request,'registration/forgot.html')

def reset_confirm(request,uid,token):
    if limited(request,'reset-link',30): return HttpResponse('Too many attempts.',status=429)
    try: user=User.objects.get(pk=urlsafe_base64_decode(uid).decode(),is_active=True)
    except (User.DoesNotExist,ValueError,UnicodeError): user=None
    valid=user and default_token_generator.check_token(user,token)
    if not valid: return render(request,'registration/reset_invalid.html',status=400)
    form=SetPasswordForm(user,request.POST or None)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            locked=User.objects.select_for_update().get(pk=user.pk)
            if not locked.is_active or not default_token_generator.check_token(locked,token): return render(request,'registration/reset_invalid.html',status=400)
            locked.set_password(form.cleaned_data['new_password1']); locked.must_change_password=False; locked.session_version+=1; locked.save()
            Audit.objects.create(actor=locked,action='account.password_reset',target=str(locked.pk))
        messages.success(request,'Password saved. Existing sessions have been revoked. Sign in with your new password.')
        return redirect('login')
    return render(request,'registration/reset_confirm.html',{'form':form})

class PasswordChangeView(auth.PasswordChangeView):
    def post(self,request,*args,**kwargs):
        with transaction.atomic():
            if not request.user.is_authenticated:return super().post(request,*args,**kwargs)
            actor=User.objects.select_for_update().get(pk=request.user.pk)
            if not actor.is_active or actor.session_version!=request.user.session_version:return HttpResponse('Session revoked. Sign in again.',status=403)
            request.user=actor
            return super().post(request,*args,**kwargs)
    template_name='registration/change_password.html'
    success_url='/account/'
    def form_valid(self,form):
        response=super().form_valid(form)
        self.request.user.must_change_password=False
        self.request.user.save(update_fields=['must_change_password'])
        Audit.objects.create(actor=self.request.user,action='account.password_changed',target=str(self.request.user.pk))
        messages.success(self.request,'Your password was changed successfully.')
        if email_configured():
            try: send_mail('Rocky’s · Password changed','Your account password was changed. Contact management immediately if this was not you.',settings.DEFAULT_FROM_EMAIL,[self.request.user.email])
            except Exception: messages.warning(self.request,'Password saved, but the notification email could not be delivered.')
        return response
