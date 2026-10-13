"""Django transactional mail backend using Resend's verified HTTPS endpoint."""
import json
import urllib.request
import urllib.error
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend

class EmailBackend(BaseEmailBackend):
    def send_messages(self,email_messages):
        sent=0
        for message in email_messages or []:
            try:
                if not settings.RESEND_API_KEY: raise ImproperlyConfigured('RESEND_API_KEY is not configured.')
                payload={'from':message.from_email,'to':list(message.to),'subject':message.subject,'text':message.body}
                for name in ['cc','bcc','reply_to']:
                    value=getattr(message,name,None)
                    if value: payload[name]=list(value)
                for alternative in getattr(message,'alternatives',[]):
                    if alternative.mimetype=='text/html': payload['html']=alternative.content
                request=urllib.request.Request('https://api.resend.com/emails',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+settings.RESEND_API_KEY,'Content-Type':'application/json','User-Agent':'Rockys-Operations/1.0'},method='POST')
                with urllib.request.urlopen(request,timeout=settings.EMAIL_TIMEOUT) as response:
                    result=json.loads(response.read())
                    if not 200<=response.status<300 or not result.get('id'): raise RuntimeError('Resend did not confirm acceptance.')
                sent+=1
            except Exception:
                # Never include provider error bodies, recipient data, tokens or keys in diagnostics.
                if not self.fail_silently: raise RuntimeError('Transactional email was not confirmed accepted by Resend. Check provider configuration and delivery logs.') from None
        return sent
