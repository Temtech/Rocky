import json, uuid, hashlib
from datetime import timedelta, date
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction, IntegrityError
from django.db.models import Count
from django.http import JsonResponse, HttpResponseForbidden, HttpResponse
from django.shortcuts import render,redirect,get_object_or_404
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import *
from .forms import *
from .services import *
from .auth_views import email_reset,email_configured

def manager_only(view):
    @wraps(view)
    @login_required
    def wrapped(request,*args,**kwargs):
        if request.user.role!='management': return HttpResponseForbidden('Management permission required.')
        return view(request,*args,**kwargs)
    return wrapped

def own_shift(request,pk):
    query=Shift.objects.all()
    if request.user.role!='management': query=query.filter(employee=request.user)
    return get_object_or_404(query,pk=pk)

def active_shift(user):
    return Shift.objects.filter(employee=user,end=None).first()

def policy(): return Policy.objects.get_or_create(pk=1)[0]

@login_required
def dashboard(request):
    if request.user.role=='management': return redirect('management')
    s=active_shift(request.user)
    now=timezone.now()
    schedules=Schedule.objects.filter(employee=request.user,end__gte=now-timedelta(days=1))[:5]
    pending=Handoff.objects.filter(Q(sender=request.user)|Q(recipient=request.user),acknowledged_at=None).select_related('sender','recipient')
    return render(request,'operations/dashboard.html',{'shift':s,'metrics':metrics(s) if s else None,'status':shift_status(s) if s else 'Off Shift','schedules':schedules,'duties':s.duties.select_related('version__duty') if s else [],'issues':Issue.objects.filter(owner=request.user,status__in=UNRESOLVED).order_by('deadline'),'handoffs':pending,'recent':Shift.objects.filter(employee=request.user)[:8],'policy':policy(),'server_time':now.isoformat(),'request_id':uuid.uuid4()})

@login_required
@require_POST
def shift_action(request):
    try:
        data=json.loads(request.body) if request.content_type=='application/json' else request.POST
        result=attendance_action(request.user,data.get('action'),data.get('request_id'))
        return JsonResponse(result)
    except (WorkflowError,ValueError,IntegrityError) as exc:
        return JsonResponse({'saved':False,'error':str(exc) if not isinstance(exc,IntegrityError) else 'Concurrent action conflict. Refresh and retry.'},status=409)

@login_required
def sync(request):
    now=timezone.now(); user=request.user
    if user.role=='management':
        return JsonResponse({'server_time':now.isoformat(),'coverage':[shift_data(s) for s in Shift.objects.filter(end=None).select_related('employee','schedule').prefetch_related('breaks')],'open_issues':Issue.objects.filter(status__in=UNRESOLVED).count(),'pending_handoffs':Handoff.objects.filter(acknowledged_at=None).count()})
    s=active_shift(user)
    return JsonResponse({'server_time':now.isoformat(),'shift':shift_data(s) if s else None,'open_issues':Issue.objects.filter(owner=user,status__in=UNRESOLVED).count(),'pending_handoffs':Handoff.objects.filter(recipient=user,acknowledged_at=None).count()})

@login_required
def attendance(request):
    shifts=Shift.objects.all() if request.user.role=='management' else Shift.objects.filter(employee=request.user)
    return render(request,'operations/attendance.html',{'shifts':shifts.select_related('employee','schedule').prefetch_related('breaks')[:200]})

@login_required
def shift_detail(request,pk):
    s=own_shift(request,pk)
    data=shift_data(s)
    revisions=SummaryRevision.objects.filter(summary__shift=s).order_by('-created_at')
    return render(request,'operations/shift_detail.html',{'shift':s,'data':data,'metrics':metrics(s),'breaks':s.breaks.all(),'events':s.events.all(),'corrections':s.corrections.select_related('manager'),'duties':s.duties.select_related('version__duty'),'revisions':revisions,'handoffs':s.handoffs.select_related('sender','recipient','acknowledged_by')})

@login_required
def shift_api(request,pk): return JsonResponse(shift_data(own_shift(request,pk)))

@login_required
def issues(request):
    query=Issue.objects.select_related('owner','reporter','duty').order_by('deadline')
    if request.GET.get('status'): query=query.filter(status=request.GET['status'])
    return render(request,'operations/issues.html',{'issues':query[:300],'now':timezone.now()})

# Business forms only expose allowed fields. Every write runs in a transaction,
# locks the acting account and relevant record, and produces an audit entry.
@login_required
def issue_edit(request,pk=None):
    item=get_object_or_404(Issue,pk=pk) if pk else None
    if item and request.user.role!='management' and request.user not in [item.owner,item.reporter]:
        if request.method=='POST': return HttpResponseForbidden('Only the owner, reporter or management may update this issue.')
        return render(request,'operations/issue_read.html',{'issue':item})
    form=IssueForm(request.POST or None,instance=item)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            User.objects.select_for_update().get(pk=request.user.pk)
            before=state(Issue.objects.select_for_update().get(pk=item.pk)) if item else {}
            obj=form.save(commit=False)
            if not item: obj.reporter=request.user; obj.shift=active_shift(request.user)
            if obj.status in ['Resolved','Closed']:
                if not item or before.get('status') not in ['Resolved','Closed']: obj.resolved_at=timezone.now()
            else: obj.resolved_at=None
            obj.save(); audit(request.user,'exception.updated' if item else 'exception.created',obj,before)
            if item and before.get('status') in ['Resolved','Closed'] and obj.status in UNRESOLVED and obj.shift:
                invalidate_link(request.user,obj.shift,obj.duty,'exception',obj.pk)
            if obj.status in ['Resolved','Closed'] and obj.shift: verify_link(request.user,obj.shift,obj.duty,'exception',f'Resolution of issue {obj.id}')
        messages.success(request,'Exception saved.'); return redirect('issues')
    return form_page(request,form,'Update exception' if item else 'Report operational exception','Routine successful dispatch belongs in Ground Alliance. Unresolved issues require an owner, next action and deadline.')

@login_required
def productivity(request):
    v=Verification.objects.all(); p=Prospect.objects.all(); sends=Outreach.objects.all()
    if request.user.role!='management': v=v.filter(employee=request.user); p=p.filter(employee=request.user); sends=sends.filter(employee=request.user)
    return render(request,'operations/productivity.html',{'verifications':v.select_related('employee')[:200],'prospects':p[:200],'sent':sends.count(),'unique':sends.values('prospect_id').distinct().count(),'policy':policy()})

@login_required
def verification_edit(request,pk=None):
    item=get_object_or_404(Verification,pk=pk) if pk else None
    if item and request.user.role!='management' and item.employee!=request.user: return HttpResponseForbidden('Private employee record.')
    form=VerificationForm(request.POST or None,instance=item)
    if request.method=='POST' and form.is_valid():
        s=item.shift if item else active_shift(request.user)
        if not s: form.add_error(None,'Start a shift before recording downtime work.')
        elif shift_status(s)=='On Break' or (not item and s.end): form.add_error(None,'Return to work before recording downtime activity.')
        elif not policy().verification_criteria.strip(): form.add_error(None,'Management must configure approved verification criteria first.')
        else:
            with transaction.atomic():
                User.objects.select_for_update().get(pk=request.user.pk)
                before=state(Verification.objects.select_for_update().get(pk=item.pk)) if item else {}
                obj=form.save(commit=False)
                if not item: obj.employee=request.user; obj.shift=s; obj.criteria=policy().verification_criteria
                elif obj.outcome!='Pending': obj.outcome='Pending'; obj.approved_by=None; obj.reviewed_at=None
                obj.save(); audit(request.user,'verification.researched',obj,before)
                if item and before.get('outcome')=='Approved': invalidate_link(request.user,obj.shift,obj.duty,'verification',obj.pk)
            messages.success(request,'Research saved. Approval remains a separate management action.'); return redirect('productivity')
    return form_page(request,form,'Affiliate / driver verification','Stop downtime work immediately when an operational responsibility needs attention.')

@login_required
def prospect_edit(request,pk=None):
    item=get_object_or_404(Prospect,pk=pk) if pk else None
    if item and request.user.role!='management' and item.employee!=request.user: return HttpResponseForbidden('Private employee record.')
    post=request.POST.copy() if request.method=='POST' else None
    if post is not None: post['email']=post.get('email','').lower()
    form=ProspectForm(post,instance=item)
    if request.method=='POST' and form.is_valid():
        s=item.shift if item else active_shift(request.user)
        if not s: form.add_error(None,'Start a shift before recording downtime work.')
        elif item and item.response=='Do Not Contact' and form.cleaned_data['response']!='Do Not Contact' and request.user.role!='management': form.add_error('response','Only management may remove a Do Not Contact restriction.')
        elif not policy().marketing_template.strip() or not policy().targeting.strip(): form.add_error(None,'Management must approve targeting and a marketing template first.')
        else:
            with transaction.atomic():
                User.objects.select_for_update().get(pk=request.user.pk)
                before=state(Prospect.objects.select_for_update().get(pk=item.pk)) if item else {}
                obj=form.save(commit=False)
                if not item: obj.employee=request.user; obj.shift=s; obj.template=policy().marketing_template; obj.targeting=policy().targeting
                obj.email=obj.email.lower(); obj.save()
                if obj.response=='Do Not Contact': obj.follow_up=None; obj.save(update_fields=['follow_up'])
                if not item or before.get('response')!=obj.response: Response.objects.create(prospect=obj,employee=request.user,status=obj.response,notes=obj.notes)
                audit(request.user,'prospect.updated',obj,before)
            messages.success(request,'Prospect saved. No email send has been recorded.'); return redirect('productivity')
    return form_page(request,form,'Marketing prospect','Entering a prospect does not send an email. Do Not Contact records are excluded from follow-up lists.')

@login_required
def outreach(request,pk):
    p=get_object_or_404(Prospect,pk=pk)
    if request.user.role!='management' and p.employee!=request.user: return HttpResponseForbidden('Private employee record.')
    form=OutreachForm(request.POST or None)
    key=request.POST.get('request_id') or str(uuid.uuid4())
    if request.method=='POST' and form.is_valid():
        try:
            with transaction.atomic():
                actor=User.objects.select_for_update().get(pk=request.user.pk)
                p=Prospect.objects.select_for_update().get(pk=pk)
                s=active_shift(actor)
                if not s or shift_status(s)!='Working': raise WorkflowError('An active working shift is required.')
                if p.response=='Do Not Contact': raise WorkflowError('Outreach is blocked: Do Not Contact.')
                if not policy().marketing_template or not policy().targeting: raise WorkflowError('Approved targeting and template are required.')
                payload=hashlib.sha256(json.dumps({'prospect':str(p.pk),**form.cleaned_data},sort_keys=True).encode()).hexdigest()
                old=Idempotency.objects.filter(user=actor,key=uuid.UUID(key)).first()
                if old and (old.action!='outreach' or old.fingerprint!=payload): raise WorkflowError('Request ID conflicts with another submission.')
                if not old:
                    event=Outreach.objects.create(prospect=p,employee=actor,shift=s,confirmation=form.cleaned_data['confirmation'],template_snapshot=policy().marketing_template)
                    audit(actor,'outreach.confirmed_by_employee',event)
                    verify_link(actor,s,p.duty,'outreach',f'Employee-confirmed outreach {event.pk}')
                    Idempotency.objects.create(user=actor,key=uuid.UUID(key),action='outreach',fingerprint=payload,result={'id':str(event.pk)})
            messages.success(request,'Actual send confirmation saved.'); return redirect('productivity')
        except (WorkflowError,ValueError) as exc: form.add_error(None,str(exc))
    return form_page(request,form,'Confirm an actual email send',f'{p.company} · {p.email}',request_id=key)

def form_page(request,form,title,description='',**extra):
    return render(request,'operations/form.html',{'form':form,'title':title,'description':description,**extra})

@login_required
def summary(request,pk):
    s=own_shift(request,pk)
    if s.employee!=request.user: return HttpResponseForbidden('Only the employee may submit their summary.')
    form=CloseoutForm(request.POST or None)
    key=request.POST.get('request_id') or str(uuid.uuid4())
    live=summary_snapshot(s)
    if request.method=='POST' and form.is_valid():
        try:
            with transaction.atomic():
                User.objects.select_for_update().get(pk=request.user.pk)
                if not s.end: raise WorkflowError('End the actual shift before submitting its daily summary.')
                fingerprint=hashlib.sha256(form.cleaned_data['comments'].encode()).hexdigest()
                old=Idempotency.objects.filter(user=request.user,key=uuid.UUID(key)).first()
                if old and (old.action!=f'summary:{s.pk}' or old.fingerprint!=fingerprint): raise WorkflowError('Request ID conflict.')
                if not old:
                    obj,_=Summary.objects.get_or_create(shift=s)
                    revision=SummaryRevision.objects.create(summary=obj,author=request.user,snapshot=summary_snapshot(s),comments=form.cleaned_data['comments'])
                    obj.review='Pending'; obj.save()
                    audit(request.user,'summary.submitted',revision)
                    Idempotency.objects.create(user=request.user,key=uuid.UUID(key),action=f'summary:{s.pk}',fingerprint=fingerprint,result={'id':str(revision.pk)})
            messages.success(request,'Summary snapshot saved. Actual shift end is unchanged.'); return redirect('shift-detail',pk=s.pk)
        except (WorkflowError,ValueError) as exc: form.add_error(None,str(exc))
    return render(request,'operations/summary.html',{'form':form,'shift':s,'snapshot':live,'snapshot_text':json.dumps(live,indent=2),'request_id':key})

@login_required
def handoff(request,pk):
    s=own_shift(request,pk)
    if s.employee!=request.user: return HttpResponseForbidden('Only the employee may submit their handoff.')
    form=HandoffForm(request.POST or None); form.fields['recipient'].queryset=User.objects.filter(is_active=True).exclude(pk=request.user.pk)
    key=request.POST.get('request_id') or str(uuid.uuid4())
    if request.method=='POST' and form.is_valid():
        try:
            with transaction.atomic():
                User.objects.select_for_update().get(pk=request.user.pk)
                recipient=form.cleaned_data['recipient']
                fingerprint=hashlib.sha256((str(recipient.pk)+form.cleaned_data['notes']).encode()).hexdigest()
                old=Idempotency.objects.filter(user=request.user,key=uuid.UUID(key)).first()
                if old and (old.action!=f'handoff:{s.pk}' or old.fingerprint!=fingerprint): raise WorkflowError('Request ID conflict.')
                if not old:
                    items=issue_snapshot(Issue.objects.filter(status__in=UNRESOLVED).filter(Q(handoff=True)|Q(owner=request.user)))
                    obj=Handoff.objects.create(shift=s,sender=request.user,recipient=recipient,snapshot={'items':items},notes=form.cleaned_data['notes'])
                    audit(request.user,'handoff.submitted',obj)
                    Idempotency.objects.create(user=request.user,key=uuid.UUID(key),action=f'handoff:{s.pk}',fingerprint=fingerprint,result={'id':str(obj.pk)})
            messages.success(request,'Handoff saved and awaiting recipient acknowledgment.'); return redirect('handoffs')
        except (WorkflowError,ValueError) as exc: form.add_error(None,str(exc))
    return form_page(request,form,'Submit shift handoff','Unresolved exceptions, owners, deadlines and next actions are populated automatically.',request_id=key)

@login_required
def handoffs(request):
    q=Handoff.objects.all() if request.user.role=='management' else Handoff.objects.filter(Q(sender=request.user)|Q(recipient=request.user))
    return render(request,'operations/handoffs.html',{'handoffs':q.select_related('sender','recipient','acknowledged_by').order_by('-created_at')[:200]})

@login_required
@require_POST
def acknowledge(request,pk):
    with transaction.atomic():
        h=get_object_or_404(Handoff.objects.select_for_update(),pk=pk)
        if h.recipient!=request.user: return HttpResponseForbidden('Only the authorized recipient may acknowledge this handoff.')
        if not h.acknowledged_at:
            h.acknowledged_by=request.user; h.acknowledged_at=timezone.now(); h.save(); audit(request.user,'handoff.acknowledged',h)
    messages.success(request,'Handoff acknowledged.'); return redirect('handoffs')

@manager_only
def management(request):
    now=timezone.now(); p=policy(); shifts=Shift.objects.all()
    employee=request.GET.get('employee','')
    if employee:
        try: shifts=shifts.filter(employee_id=uuid.UUID(employee))
        except ValueError: return HttpResponse('Invalid employee filter.',status=400)
    for name,lookup in [('from','shift_date__gte'),('to','shift_date__lte')]:
        value=request.GET.get(name)
        if value:
            try: shifts=shifts.filter(**{lookup:date.fromisoformat(value)})
            except ValueError: return HttpResponse('Invalid date filter.',status=400)
    if request.GET.get('review'): shifts=shifts.filter(review=request.GET['review'])
    status=request.GET.get('status')
    if status=='Working': shifts=shifts.filter(end=None).exclude(breaks__end=None,breaks__id__isnull=False)
    elif status=='On Break': shifts=shifts.filter(end=None,breaks__end=None,breaks__id__isnull=False)
    elif status=='Ended': shifts=shifts.filter(end__isnull=False)
    rows=[]
    for s in shifts.select_related('employee','schedule').prefetch_related('breaks')[:200]: rows.append({'shift':s,'status':shift_status(s),'warnings':attendance_warnings(s),'metrics':metrics(s)})
    duties=ShiftDuty.objects.filter(shift__in=shifts).select_related('version__duty','shift__employee')
    if request.GET.get('duty_status'): duties=[d for d in duties if duty_status(d)==request.GET['duty_status']]
    missed=[]
    for sc in Schedule.objects.filter(start__lt=now-timedelta(minutes=p.grace_minutes),employee__is_active=True).exclude(shift__isnull=False).select_related('employee'):
        if not Leave.objects.filter(employee=sc.employee,start__lt=sc.end,end__gt=sc.start).exists(): missed.append(sc)
    backlog=Issue.objects.filter(status__in=UNRESOLVED).select_related('owner').order_by('deadline')
    sends=Outreach.objects.filter(shift__in=shifts)
    verifications=Verification.objects.filter(shift__in=shifts).values('outcome').annotate(total=Count('id'))
    closeouts=shifts.filter(end__isnull=False)
    summary_pending=Summary.objects.filter(shift__in=shifts,review='Pending').count()
    return render(request,'operations/management.html',{'rows':rows,'coverage':Shift.objects.filter(end=None).select_related('employee').prefetch_related('breaks'),'employees':User.objects.all(),'backlog':backlog,'overdue':backlog.filter(deadline__lt=now).count(),'approaching':backlog.filter(deadline__gte=now,deadline__lte=now+timedelta(minutes=p.warning_minutes)),'handoffs':Handoff.objects.filter(acknowledged_at=None).select_related('sender','recipient'),'missed':missed,'duties':duties,'verification_totals':verifications,'sent':sends.count(),'unique':sends.values('prospect_id').distinct().count(),'researched':Prospect.objects.filter(shift__in=shifts).count(),'followups':Prospect.objects.exclude(response='Do Not Contact').filter(follow_up__lte=now),'responses':Response.objects.filter(created_at__gte=now-timedelta(days=1)).count(),'missing_summaries':closeouts.filter(summary__isnull=True).count(),'pending_summaries':summary_pending,'server_time':now.isoformat(),'now':now})

@manager_only
def employees(request): return render(request,'operations/employees.html',{'employees':User.objects.all().order_by('first_name')})

@manager_only
def invite(request):
    form=InviteForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        if not email_configured():
            form.add_error(None,'Email delivery is not configured. No invitation was sent. Configure Resend with EMAIL_PROVIDER=resend, RESEND_API_KEY and a verified DEFAULT_FROM_EMAIL, or configure SMTP.')
        else:
            try:
                with transaction.atomic():
                    user=User.objects.create(username=form.cleaned_data['email'],email=form.cleaned_data['email'],first_name=form.cleaned_data['name'],role=form.cleaned_data['role'])
                    user.set_unusable_password(); user.save()
                    email_reset(request,user); audit(request.user,'account.invited',user)
                messages.success(request,'Account created and invitation sent.'); return redirect('employees')
            except Exception: form.add_error(None,'Invitation delivery failed. The new account was not created. Check email-provider configuration.')
    return form_page(request,form,'Invite employee','No public registration and no default passwords. New accounts receive a secure, expiring password setup link.')

@manager_only
@require_POST
def reset_invite(request,pk):
    user=get_object_or_404(User,pk=pk,is_active=True)
    try: email_reset(request,user); audit(request.user,'account.reset_invitation',user); messages.success(request,'Password reset invitation sent.')
    except Exception: messages.error(request,'Reset invitation could not be delivered. Check email-provider configuration.')
    return redirect('employees')

@manager_only
def deactivate(request,pk):
    employee=get_object_or_404(User,pk=pk)
    if employee==request.user: return HttpResponseForbidden('You cannot deactivate your own account.')
    form=DeactivateForm(request.POST or None); form.fields['recipient'].queryset=User.objects.filter(is_active=True).exclude(pk=employee.pk)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            employee=User.objects.select_for_update().get(pk=pk)
            s=active_shift(employee)
            if s and not form.cleaned_data['close_active_shift']: form.add_error(None,'The employee has an active shift. Select close active shift to record its end now.')
            else:
                now=timezone.now(); recipient=form.cleaned_data['recipient']; reason=form.cleaned_data['reason']
                if s:
                    for b in s.breaks.filter(end=None): b.end=now; b.save(); audit(request.user,'break.closed_on_deactivation',b)
                    s.end=s.original_end=now; s.save(); ShiftEvent.objects.create(shift=s,actor=request.user,action='deactivation_end'); audit(request.user,'shift.closed_on_deactivation',s)
                for h in Handoff.objects.select_for_update().filter(recipient=employee,acknowledged_at=None):
                    before=state(h); h.recipient=recipient; h.save(); audit(request.user,'handoff.reassigned',h,before)
                for i in Issue.objects.select_for_update().filter(owner=employee,status__in=UNRESOLVED):
                    before=state(i); i.owner=recipient; i.save(); audit(request.user,'exception.owner_reassigned',i,before)
                before=state(employee); employee.is_active=False; employee.session_version+=1; employee.save(); audit(request.user,'account.deactivated',employee,{**before,'reason':reason})
                messages.success(request,'Access revoked, history retained and open responsibilities reassigned.'); return redirect('employees')
    return form_page(request,form,f'Deactivate {employee}','All sessions are revoked. Active shifts are closed using server time only after the explicit selection below. History is preserved.')

@manager_only
@require_POST
def reactivate(request,pk):
    with transaction.atomic():
        employee=get_object_or_404(User.objects.select_for_update(),pk=pk)
        before=state(employee); employee.is_active=True; employee.session_version+=1; employee.save(); audit(request.user,'account.reactivated',employee,before)
    messages.success(request,'Account reactivated.'); return redirect('employees')

@manager_only
def employee_role(request,pk):
    employee=get_object_or_404(User,pk=pk)
    class RoleForm(forms.Form):
        role=forms.ChoiceField(choices=User._meta.get_field('role').choices)
        reason=forms.CharField()
    form=RoleForm(request.POST or None,initial={'role':employee.role})
    if request.method=='POST' and form.is_valid():
        if employee==request.user: form.add_error(None,'Use another manager to change your role.')
        elif active_shift(employee): form.add_error(None,'End the active shift before changing this role.')
        else:
            with transaction.atomic():
                employee=User.objects.select_for_update().get(pk=pk)
                if active_shift(employee):
                    form.add_error(None,'End the active shift before changing this role.')
                    return form_page(request,form,f'Role for {employee}')
                before=state(employee); employee.role=form.cleaned_data['role']; employee.session_version+=1; employee.save(); audit(request.user,'account.role_changed',employee,{**before,'reason':form.cleaned_data['reason']})
            return redirect('employees')
    return form_page(request,form,f'Role for {employee}')

@manager_only
def settings_view(request):
    obj=policy(); form=PolicyForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            before=state(Policy.objects.select_for_update().get(pk=1)); obj=form.save(); audit(request.user,'policy.changed',obj,before)
        messages.success(request,'Policies saved.'); return redirect('settings')
    return form_page(request,form,'Operating policies','Configure approved criteria and marketing guidance before employees can record those activities. Net hours are not automatically paid hours.')

@manager_only
def schedules(request):
    return render(request,'operations/schedules.html',{'schedules':Schedule.objects.select_related('employee').order_by('-start')[:200],'leaves':Leave.objects.select_related('employee','approved_by').order_by('-start')[:200]})

@manager_only
def schedule_edit(request,pk=None,leave=False):
    model=Leave if leave else Schedule; cls=LeaveForm if leave else ScheduleForm
    obj=get_object_or_404(model,pk=pk) if pk else None
    form=cls(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        if not leave and obj and Shift.objects.filter(schedule=obj).exists(): form.add_error(None,'This schedule is already used by a shift. Historical scheduled times are protected; create a new future schedule.')
        elif form.cleaned_data['end']<=form.cleaned_data['start']: form.add_error('end','End must be after start.')
        else:
            with transaction.atomic():
                before=state(model.objects.select_for_update().get(pk=obj.pk)) if obj else {}
                item=form.save(commit=False)
                if leave: item.approved_by=request.user
                item.save(); audit(request.user,'leave.changed' if leave else 'schedule.changed',item,before)
            messages.success(request,'Schedule / leave saved.'); return redirect('schedules')
    return form_page(request,form,'Approved leave' if leave else 'Assigned schedule','Start and end include full dates; overnight shifts must use the following end date.')

@login_required
def duties(request):
    if request.user.role=='management':
        register=[]
        for d in Duty.objects.all().order_by('code'): register.append({'duty':d,'version':d.versions.order_by('-created_at').first(),'assignments':d.assignments.filter(active=True),'assignment_history':d.assignments.order_by('-created_at')})
        assignments=ShiftDuty.objects.select_related('version__duty','shift__employee').order_by('-created_at')[:200]
    else:
        register=[]; assignments=ShiftDuty.objects.filter(shift__employee=request.user).select_related('version__duty','shift')[:200]
    count=Duty.objects.filter(code__in=[f'D{i:02}' for i in range(1,61)]).count()
    return render(request,'operations/duties.html',{'register':register,'assignments':assignments,'source_count':count,'groups':DutyGroup.objects.all() if request.user.role=='management' else [],'source_complete':count==60,'conditions':Condition.objects.all()[:100] if request.user.role=='management' else []})

@manager_only
def duty_edit(request,pk=None):
    obj=get_object_or_404(Duty,pk=pk) if pk else None
    version=obj.versions.order_by('-created_at').first() if obj else None
    initial={**(state(version) if version else {}),'code':obj.code if obj else '', 'active':obj.active if obj else True}
    form=DutyForm(request.POST or None,initial=initial)
    if request.method=='POST' and form.is_valid():
        if not obj and Duty.objects.filter(code=form.cleaned_data['code']).exists(): form.add_error('code','This duty ID already exists.')
        elif obj and form.cleaned_data['code']!=obj.code: form.add_error('code','Duty IDs are permanent.')
        else:
            with transaction.atomic():
                d=form.cleaned_data.copy(); code=d.pop('code'); active=d.pop('active')
                before=state(Duty.objects.select_for_update().get(pk=obj.pk)) if obj else {}
                if not obj: obj=Duty.objects.create(code=code,active=active)
                else: obj.active=active; obj.save()
                v=DutyVersion.objects.create(duty=obj,author=request.user,**d)
                audit(request.user,'duty.version_created',v); audit(request.user,'duty.changed',obj,before)
            messages.success(request,'New duty version saved. Earlier shift assignments retain their historical version.'); return redirect('duties')
    return form_page(request,form,'Duty definition','Complete descriptions, original frequency and instructions are retained in immutable historical versions.')

@manager_only
def assignment_edit(request,pk=None):
    obj=get_object_or_404(DutyAssignment,pk=pk) if pk else None
    form=AssignmentForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            before=state(DutyAssignment.objects.select_for_update().get(pk=obj.pk)) if obj else {}
            item=form.save(commit=False)
            desired_active=form.cleaned_data['active']
            if obj:
                DutyAssignment.objects.filter(pk=obj.pk).update(active=False)
                item.pk=uuid.uuid4(); item.created_at=timezone.now()
            item.active=desired_active
            item.save(); audit(request.user,'duty.assignment_created',item,before)
        messages.success(request,'Assignment saved. Applies to subsequent shift starts. Previous assignments remain available in history.'); return redirect('duties')
    return form_page(request,form,'Duty assignment','Original workbook frequency remains intact; this explicit cadence determines applicability. Inactive, future or unassigned duties do not create missed-duty alerts.')

@manager_only
def condition_create(request):
    form=ConditionForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        obj=form.save(commit=False); obj.recorded_by=request.user; obj.save(); audit(request.user,'duty.condition_recorded',obj)
        return redirect('duties')
    return form_page(request,form,'Record conditional applicability','Use the same condition name configured in a conditional duty assignment.')

@manager_only
def duty_evidence(request,pk):
    obj=get_object_or_404(ShiftDuty,pk=pk); form=EvidenceForm(request.POST or None,initial={'status':obj.status,'evidence':obj.evidence})
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            obj=ShiftDuty.objects.select_for_update().get(pk=pk); before=state(obj)
            obj.status=form.cleaned_data['status']; obj.evidence=form.cleaned_data['evidence']; obj.save(); audit(request.user,'duty.reviewed',obj,before)
        return redirect('duties')
    return form_page(request,form,'Duty evidence review','Assignment or display does not establish completion. Record the source evidence before verifying.')

@manager_only
def approval(request,pk):
    obj=get_object_or_404(Verification,pk=pk); form=ApprovalForm(request.POST or None,initial={'outcome':obj.outcome,'notes':obj.notes})
    if request.method=='POST' and form.is_valid():
        if obj.research_status!='Research Complete': form.add_error(None,'Research must be completed before a management outcome can be recorded.')
        else:
            with transaction.atomic():
                obj=Verification.objects.select_for_update().get(pk=pk); before=state(obj)
                obj.outcome=form.cleaned_data['outcome']; obj.notes=form.cleaned_data['notes']; obj.approved_by=request.user; obj.reviewed_at=timezone.now(); obj.save(); audit(request.user,'verification.approved_or_reviewed',obj,before)
                if obj.outcome=='Approved': verify_link(request.user,obj.shift,obj.duty,'verification',f'Management approval of review {obj.pk}')
            return redirect('productivity')
    return form_page(request,form,f'Review {obj.subject}','Only management can approve. Research completion and approval are separate.')

@manager_only
def correction(request,pk):
    s=get_object_or_404(Shift,pk=pk); form=CorrectionForm(request.POST or None,initial={'start':s.start,'end':s.end})
    if request.method=='POST' and form.is_valid():
        try:
            correct_shift(request.user,s,form.cleaned_data['start'],form.cleaned_data['end'],form.cleaned_data['reason'])
            messages.success(request,'Correction saved. Original events and submitted summary snapshots are preserved. Current calculations have been updated.'); return redirect('shift-detail',pk=pk)
        except WorkflowError as exc: form.add_error(None,str(exc))
    return form_page(request,form,'Audited attendance correction','Preserves original, previous effective and corrected timestamps. Corrections cannot manufacture or remove an actual shift-end event.')

@manager_only
def review(request,pk):
    s=get_object_or_404(Shift,pk=pk); form=ReviewForm(request.POST or None,initial={'review':s.review,'manager_comments':s.manager_comments})
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            s=Shift.objects.select_for_update().get(pk=pk); before=state(s)
            s.review=form.cleaned_data['review']; s.manager_comments=form.cleaned_data['manager_comments']; s.save(); audit(request.user,'shift.management_review',s,before)
            sm=Summary.objects.filter(shift=s).first()
            if sm:
                before=state(sm); sm.review=s.review; sm.manager_comments=s.manager_comments; sm.save(); audit(request.user,'summary.management_review',sm,before)
        return redirect('shift-detail',pk=pk)
    return form_page(request,form,'Management review')

@manager_only
def audit_history(request):
    return render(request,'operations/audit.html',{'events':Audit.objects.select_related('actor')[:500]})

@login_required
def account(request): return render(request,'operations/account.html')

@login_required
@require_POST
def revoke_sessions(request):
    from django.contrib.auth import update_session_auth_hash
    with transaction.atomic():
        u=User.objects.select_for_update().get(pk=request.user.pk); u.session_version+=1; u.save(); audit(u,'account.other_sessions_revoked',u)
    request.session['version']=u.session_version
    messages.success(request,'Other sessions revoked.'); return redirect('account')

@manager_only
@require_POST
def revoke_employee_sessions(request,pk):
    with transaction.atomic():
        u=get_object_or_404(User.objects.select_for_update(),pk=pk); u.session_version+=1; u.save(); audit(request.user,'account.sessions_revoked_by_manager',u)
    messages.success(request,'Employee sessions revoked.'); return redirect('employees')
@manager_only
def duty_import(request):
    from django import forms
    from .workbook import import_workbook
    import tempfile, os
    class ImportForm(forms.Form):
        workbook=forms.FileField(help_text='CSV or XLSX. Headers: code, description, instructions, frequency; optional section. D01–D60 exactly once. Blank rows ignored. Original text is preserved.')
    form=ImportForm(request.POST or None,request.FILES or None)
    if request.method=='POST' and form.is_valid():
        upload=form.cleaned_data['workbook']; suffix=os.path.splitext(upload.name)[1].lower()
        if suffix not in ['.xlsx','.csv'] or upload.size>5*1024*1024: form.add_error('workbook','Upload a CSV/XLSX file smaller than 5 MB.')
        else:
            name=None
            try:
                with tempfile.NamedTemporaryFile(suffix=suffix,delete=False) as f:
                    name=f.name
                    for chunk in upload.chunks(): f.write(chunk)
                count=import_workbook(name,request.user)
                messages.success(request,f'{count} source duties imported. Existing identical imports are not duplicated. Configure assignments and evidence mappings before use.')
                return redirect('duties')
            except (WorkflowError,ValueError,OSError) as exc: form.add_error(None,str(exc))
            finally:
                if name: os.unlink(name)
    return form_page(request,form,'Import D01–D60 source workbook','No generic replacement duties are created. Import is atomic and must reconcile all 60 IDs.')

@manager_only
def group_edit(request,pk=None):
    obj=get_object_or_404(DutyGroup,pk=pk) if pk else None
    form=GroupForm(request.POST or None,instance=obj)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            before=state(DutyGroup.objects.select_for_update().get(pk=obj.pk)) if obj else {}
            item=form.save();audit(request.user,'duty.group_changed',item,before)
        messages.success(request,'Duty group saved. Changes apply to subsequent shifts.');return redirect('duties')
    return form_page(request,form,'Dispatcher duty group','Named groups let management assign applicable duties to multiple dispatchers. Earlier shift assignments remain intact.')
