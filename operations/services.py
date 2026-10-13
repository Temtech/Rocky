import hashlib, json, uuid
from datetime import timedelta
from zoneinfo import ZoneInfo
from django.db import transaction
from django.utils import timezone
from django.forms.models import model_to_dict
from .models import *
DENVER=ZoneInfo('America/Denver')
UNRESOLVED=['Open','In Progress','Awaiting Response']
class WorkflowError(Exception): pass

def clean_json(value):
    return json.loads(json.dumps(value,default=str))

def state(obj):
    data=model_to_dict(obj)
    data['id']=str(obj.pk)
    if hasattr(obj,'created_at'): data['created_at']=obj.created_at.isoformat()
    for key in ['password','session_version']:
        data.pop(key,None)
    return clean_json(data)

def audit(actor,action,obj,before=None):
    Audit.objects.create(actor=actor,action=action,target=f'{obj.__class__.__name__}:{obj.pk}',before=before or {},after=state(obj))

def metrics(shift,now=None):
    now=now or timezone.now()
    completed=sum((b.end-b.start).total_seconds() for b in shift.breaks.all() if b.end)
    live_break=sum(((b.end or now)-b.start).total_seconds() for b in shift.breaks.all())
    live=((shift.end or now)-shift.start).total_seconds()
    return {'elapsed_hours':round(live/3600,4) if shift.end else None,'break_hours':round(completed/3600,4),'net_hours':round((live-completed)/3600,4) if shift.end else None,'live_elapsed_hours':round(live/3600,4),'live_net_hours':round((live-live_break)/3600,4),'open_break':shift.breaks.filter(end=None).exists()}

def shift_status(shift):
    if shift.end: return 'Ended'
    if shift.breaks.filter(end=None).exists(): return 'On Break'
    return 'Working'

def attendance_warnings(shift,now=None):
    now=now or timezone.now(); policy=Policy.objects.get_or_create(pk=1)[0]; warnings=[]
    if shift.schedule:
        if shift.start > shift.schedule.start+timedelta(minutes=policy.grace_minutes): warnings.append('Late Start')
        if not shift.end and now > shift.schedule.end+timedelta(minutes=policy.grace_minutes): warnings.append('Missing End')
    b=shift.breaks.filter(end=None).first()
    if b and now>b.start+timedelta(minutes=policy.break_minutes): warnings.append('Break Duration Warning')
    if shift.end and (not Summary.objects.filter(shift=shift).exists() or not shift.handoffs.exists()): warnings.append('Incomplete Closeout')
    return warnings

def populate_duties(shift):
    date=shift.shift_date
    assignments=DutyAssignment.objects.filter(active=True,duty__active=True,effective_start__lte=date).filter(Q(effective_end=None)|Q(effective_end__gte=date)).filter(Q(employee=shift.employee)|Q(group='dispatchers')|Q(team__members=shift.employee,team__active=True)).distinct()
    for a in assignments:
        if a.weekdays and date.weekday() not in a.weekdays: continue
        if a.cadence=='conditional' and not Condition.objects.filter(employee=shift.employee,name=a.condition,applicable_date=date).exists(): continue
        earlier=ShiftDuty.objects.filter(assignment=a,shift__employee=shift.employee)
        if a.cadence=='daily' and earlier.filter(shift__shift_date=date).exists(): continue
        if a.cadence=='weekly' and earlier.filter(shift__shift_date__gte=date-timedelta(days=date.weekday())).exists(): continue
        if a.cadence=='monthly' and earlier.filter(shift__shift_date__gte=date.replace(day=1)).exists(): continue
        version=a.duty.versions.order_by('-created_at').first()
        if version:
            ShiftDuty.objects.get_or_create(shift=shift,assignment=a,defaults={'version':version,'deadline':shift.start+timedelta(minutes=a.deadline_minutes)})

def shift_data(s):
    data={'id':str(s.id),'employee_id':str(s.employee_id),'employee':str(s.employee),'date':s.shift_date.isoformat(),'start_utc':s.start.isoformat(),'end_utc':s.end.isoformat() if s.end else None,'start_denver':s.start.astimezone(DENVER).isoformat(),'end_denver':s.end.astimezone(DENVER).isoformat() if s.end else None,'start_offset_minutes':int(s.start.astimezone(DENVER).utcoffset().total_seconds()/60),'end_offset_minutes':int(s.end.astimezone(DENVER).utcoffset().total_seconds()/60) if s.end else None,'status':shift_status(s),'warnings':attendance_warnings(s),'original_start_utc':s.original_start.isoformat(),'original_end_utc':s.original_end.isoformat() if s.original_end else None,'review':s.review,'manager_comments':s.manager_comments}
    data.update(metrics(s))
    data['schedule']=state(s.schedule) if s.schedule else None
    data['breaks']=[dict(state(b),start_denver=b.start.astimezone(DENVER).isoformat(),end_denver=b.end.astimezone(DENVER).isoformat() if b.end else None,minutes=round((b.end-b.start).total_seconds()/60,4) if b.end else None) for b in s.breaks.all()]
    data['events']=[dict(state(e),timestamp=e.created_at.isoformat()) for e in s.events.all()]
    data['corrections']=[dict(state(c),timestamp=c.created_at.isoformat()) for c in s.corrections.all()]
    data['handoffs']=[dict(state(h),submitted_utc=h.created_at.isoformat(),submitted_denver=h.created_at.astimezone(DENVER).isoformat(),acknowledged_denver=h.acknowledged_at.astimezone(DENVER).isoformat() if h.acknowledged_at else None) for h in s.handoffs.all()]
    return data

def issue_snapshot(query):
    return [{'id':str(i.id),'description':i.description,'status':i.status,'owner':str(i.owner),'deadline':i.deadline.isoformat(),'next_action':i.next_action,'priority':i.priority,'management_attention':i.management_attention,'handoff':i.handoff} for i in query]

def duty_status(d,now=None):
    if d.version.guidance_only: return 'Operating Guidance'
    if d.status in ['Verified','Blocked']: return d.status
    if d.deadline<(now or timezone.now()): return 'Overdue'
    return d.status

def summary_snapshot(s):
    sends=Outreach.objects.filter(shift=s)
    return clean_json({'attendance':shift_data(s),'unresolved_exceptions':issue_snapshot(Issue.objects.filter(status__in=UNRESOLVED)),'handoff_items':issue_snapshot(Issue.objects.filter(status__in=UNRESOLVED,handoff=True)),'verification':[dict(state(v),employee=str(v.employee)) for v in Verification.objects.filter(shift=s)],'researched_prospects':Prospect.objects.filter(shift=s).count(),'emails_sent':sends.count(),'unique_contacts_reached':sends.values('prospect_id').distinct().count(),'responses_requiring_follow_up':[state(p) for p in Prospect.objects.filter(employee=s.employee,response='Follow-Up Required').exclude(response='Do Not Contact')],'duties':[{'id':str(d.id),'code':d.version.duty.code,'description':d.version.description,'status':duty_status(d),'deadline':d.deadline.isoformat(),'evidence':d.evidence} for d in s.duties.select_related('version__duty')]})

@transaction.atomic
def attendance_action(user,action,key):
    previous_version=user.session_version
    user=User.objects.select_for_update().get(pk=user.pk)
    if user.session_version!=previous_version: raise WorkflowError('Your session has been revoked. Sign in again.')
    if user.role!='dispatcher' or not user.is_active: raise WorkflowError('Active dispatcher account required.')
    try: key=uuid.UUID(str(key))
    except (ValueError,TypeError): raise WorkflowError('A valid request ID is required.')
    existing=Idempotency.objects.filter(user=user,key=key).first()
    if existing:
        if existing.action!=action: raise WorkflowError('Request ID was already used for a different action.')
        return existing.result
    now=timezone.now(); s=Shift.objects.select_for_update().filter(employee=user,end=None).first()
    if action=='start':
        if s: raise WorkflowError('A shift is already active.')
        schedule=Schedule.objects.filter(employee=user,start__lte=now+timedelta(hours=4),end__gte=now-timedelta(hours=4)).order_by('start').first()
        if schedule and Leave.objects.filter(employee=user,start__lt=schedule.end,end__gt=schedule.start).exists(): raise WorkflowError('This scheduled shift has approved leave. Contact management.')
        s=Shift.objects.create(employee=user,start=now,original_start=now,shift_date=now.astimezone(DENVER).date(),schedule=schedule)
        populate_duties(s)
    elif not s: raise WorkflowError('Start a shift before using this action.')
    elif action=='break_start':
        if s.breaks.filter(end=None).exists(): raise WorkflowError('A break is already open.')
        Break.objects.create(shift=s,employee=user,start=now)
    elif action=='break_end':
        b=s.breaks.select_for_update().filter(end=None).first()
        if not b: raise WorkflowError('No open break to end.')
        b.end=now; b.save()
    elif action=='end':
        if s.breaks.filter(end=None).exists(): raise WorkflowError('Return to work before ending the shift.')
        if now<s.start: raise WorkflowError('Shift end cannot precede its start.')
        s.end=s.original_end=now; s.save()
    else: raise WorkflowError('Unknown shift action.')
    ShiftEvent.objects.create(shift=s,actor=user,action=action)
    audit(user,f'shift.{action}',s)
    result={'saved':True,'shift':shift_data(s),'server_time':now.isoformat(),'action':action}
    Idempotency.objects.create(user=user,key=key,action=action,fingerprint=action,result=result)
    return result

def verify_link(user,shift,duty,kind,evidence):
    if duty:
        for d in ShiftDuty.objects.filter(shift=shift,version__duty=duty,version__mapping=kind):
            before=state(d); d.status='Verified'; d.evidence=evidence; d.save(); audit(user,'duty.evidence',d,before)

@transaction.atomic
def correct_shift(manager,shift,start,end,reason):
    s=Shift.objects.select_for_update().get(pk=shift.pk)
    if not reason.strip(): raise WorkflowError('A correction reason is required.')
    if end and end<start: raise WorkflowError('End must be after start.')
    if bool(s.end)!=bool(end): raise WorkflowError('Corrections cannot create or remove the actual shift-end event.')
    if start>timezone.now() or (end and end>timezone.now()): raise WorkflowError('Attendance timestamps cannot be in the future.')
    for b in s.breaks.all():
        if b.start<start or (end and (not b.end or b.end>end)): raise WorkflowError('Correction would put a break outside the shift.')
    before=state(s)
    Correction.objects.create(shift=s,manager=manager,reason=reason,previous_start=s.start,previous_end=s.end,corrected_start=start,corrected_end=end)
    s.start=start; s.end=end; s.save(); audit(manager,'attendance.corrected',s,before)
    return s

def invalidate_link(user,shift,duty,kind,source_id):
    if duty:
        for d in ShiftDuty.objects.filter(shift=shift,version__duty=duty,version__mapping=kind,status='Verified'):
            if str(source_id) in d.evidence:
                before=state(d);d.status='Completion Not Verified';d.evidence=f'Prior source {source_id} changed; management re-verification required.';d.save();audit(user,'duty.evidence_invalidated',d,before)
