from django.contrib.auth import logout
from django.shortcuts import redirect
from django.http import JsonResponse
import json
class ActiveSessionMiddleware:
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        if request.user.is_authenticated:
            version=request.session.get('version')
            if not request.user.is_active or (version is not None and version != request.user.session_version):
                logout(request)
            elif version is None:
                request.session['version']=request.user.session_version
        if request.user.is_authenticated and request.user.must_change_password and request.path not in ['/account/password/', '/logout/']:
            if request.path.startswith('/api/'):
                return JsonResponse({'error':'Change your initial password before using the workspace.'},status=403)
            return redirect('/account/password/')
        response=self.get_response(request)
        if request.headers.get('X-Requested-With')=='RockyForm' and response.status_code==302:
            destination=response['Location']
            response.status_code=200
            response.content=json.dumps({'navigate':destination})
            response['Content-Type']='application/json'
            del response['Location']
        if request.user.is_authenticated or '/reset/' in request.path:
            response['Cache-Control']='no-store, private'
            response['Referrer-Policy']='same-origin'
        return response
