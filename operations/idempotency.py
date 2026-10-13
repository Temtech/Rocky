import hashlib, json, uuid
from functools import wraps
from django.db import transaction, IntegrityError
from django.http import HttpResponse,JsonResponse
from django.shortcuts import redirect
from .models import User,Idempotency

def protected_write(view):
    """Serialize writes per account, recheck revocation, replay committed redirects."""
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        if request.method!='POST' or not request.user.is_authenticated: return view(request,*args,**kwargs)
        try: key=uuid.UUID(request.POST.get('request_id',''))
        except (ValueError,TypeError): return HttpResponse('Missing or invalid request ID. Reload this form.',status=400)
        payload={k:request.POST.getlist(k) for k in sorted(request.POST) if k not in ['csrfmiddlewaretoken','request_id']}
        # Hash uploaded source bytes without persisting the upload in the request ledger.
        for name,upload in request.FILES.items():
            digest=hashlib.sha256()
            for chunk in upload.chunks(): digest.update(chunk)
            upload.seek(0);payload[name]=digest.hexdigest()
        digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        action=f'form:{request.path}'
        with transaction.atomic():
            actor=User.objects.select_for_update().get(pk=request.user.pk)
            if not actor.is_active or actor.session_version!=request.user.session_version: return HttpResponse('Access has been revoked. Sign in again.',status=403)
            request.user=actor
            old=Idempotency.objects.filter(user=actor,key=key).first()
            if old:
                if old.action!=action or old.fingerprint!=digest: return HttpResponse('Request ID was already used for a different submission.',status=409)
                return redirect(old.result['redirect'])
            response=view(request,*args,**kwargs)
            if response.status_code==302:
                Idempotency.objects.create(user=actor,key=key,action=action,fingerprint=digest,result={'redirect':response['Location']})
            return response
    return wrapped

def rechecked_write(view):
    """For workflows with their own request ledger, recheck identity under the lock."""
    @wraps(view)
    def wrapped(request,*args,**kwargs):
        if request.method!='POST' or not request.user.is_authenticated:return view(request,*args,**kwargs)
        with transaction.atomic():
            actor=User.objects.select_for_update().get(pk=request.user.pk)
            if not actor.is_active or actor.session_version!=request.user.session_version:return HttpResponse('Access was revoked. Sign in again.',status=403)
            request.user=actor
            return view(request,*args,**kwargs)
    return wrapped
