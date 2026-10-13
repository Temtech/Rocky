import uuid, json, tempfile, csv, re
from datetime import datetime, timedelta, timezone as dtz
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from django.test import TestCase,TransactionTestCase,Client,override_settings
from django.db import transaction, IntegrityError, DatabaseError, close_old_connections, connections
from django.core import mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.utils import timezone
from django.urls import reverse
from .models import *
from .services import *
from .forms import DenverInput
from .workbook import import_workbook
PASSWORD='Test-only-secure-passphrase-728!'

class WorkflowTests(TestCase):
    def setUp(self):
        self.noah=User.objects.create_user(username='noah@example.test',email='noah@example.test',first_name='Noah',password=PASSWORD)
        self.umer=User.objects.create_user(username='umer@example.test',email='umer@example.test',first_name='Umer',password=PASSWORD)
        self.manager=User.objects.create_user(username='teddy@example.test',email='teddy@example.test',first_name='Teddy',role='management',password=PASSWORD)
        self.client.force_login(self.noah)
        self.policy=Policy.objects.create(verification_criteria='License, insurance and references',marketing_template='Approved template',targeting='Approved hotels')
    def post(self,name,data=None,pk=None):
        return self.client.post(reverse(name,kwargs={'pk':pk} if pk else None),{'request_id':str(uuid.uuid4()),**(data or {})})
    def act(self,action,key=None): return attendance_action(self.noah,action,key or uuid.uuid4())
    def ended(self):
        self.act('start'); self.act('end'); return self.noah.shifts.first()
    def test_case_insensitive_login_and_email_uniqueness(self):
        c=Client();r=c.post('/login/',{'username':self.noah.email.upper(),'password':PASSWORD})
        self.assertEqual(r.status_code,302)
        with self.assertRaises(IntegrityError),transaction.atomic():
            User.objects.create_user(username='different',email=self.noah.email.upper(),password=PASSWORD)
    def test_login_roles_and_private_attendance(self):
        c=Client();self.assertTrue(c.login(username=self.noah.email,password=PASSWORD));self.assertEqual(c.get('/').status_code,200)
        self.assertEqual(c.get('/management/').status_code,403)
        self.client.force_login(self.manager);self.assertRedirects(self.client.get('/'),'/management/',fetch_redirect_response=False)
        s=self.ended();self.client.force_login(self.umer);self.assertEqual(self.client.get(reverse('shift-api',args=[s.pk])).status_code,404)
        self.assertNotContains(self.client.get('/attendance/'),str(s.id)[:8].upper())
    def test_shift_break_transitions_and_idempotency(self):
        with self.assertRaises(WorkflowError):self.act('break_start')
        key=uuid.uuid4(); first=self.act('start',key);self.assertEqual(first,self.act('start',key));self.assertEqual(Shift.objects.count(),1)
        with self.assertRaises(WorkflowError):self.act('start')
        with self.assertRaises(WorkflowError):self.act('break_end')
        self.act('break_start')
        with self.assertRaises(WorkflowError):self.act('break_start')
        with self.assertRaises(WorkflowError):self.act('end')
        self.act('break_end');self.act('break_start');self.act('break_end');self.act('end')
        s=self.noah.shifts.first();self.assertEqual(s.breaks.count(),2);self.assertEqual(s.events.count(),6)
        self.assertIsNotNone(metrics(s)['net_hours']);self.assertEqual(s.end,s.original_end)
    def test_live_final_values_remain_incomplete(self):
        self.act('start');s=self.noah.shifts.first();m=metrics(s)
        self.assertIsNone(m['elapsed_hours']);self.assertIsNone(m['net_hours']);self.assertGreaterEqual(m['live_elapsed_hours'],0)
    def test_reused_action_key_is_rejected(self):
        key=uuid.uuid4();self.act('start',key)
        with self.assertRaises(WorkflowError):self.act('end',key)
    def test_server_time_ignores_browser_timestamp(self):
        r=self.post('shift-action',{'action':'start','start':'1999-01-01T00:00Z'})
        self.assertEqual(r.status_code,200);self.assertGreater(self.noah.shifts.first().start,timezone.now()-timedelta(minutes=1))
    def test_database_blocks_duplicate_active_and_foreign_break(self):
        self.act('start');s=self.noah.shifts.first()
        with self.assertRaises(IntegrityError),transaction.atomic():Shift.objects.create(employee=self.noah,shift_date=s.shift_date,original_start=s.start)
        with self.assertRaises(DatabaseError),transaction.atomic():Break.objects.create(shift=s,employee=self.umer)
    def test_both_dst_transitions_and_overnight(self):
        for start,end,elapsed,offset_a,offset_b in [(datetime(2026,3,8,8,30,tzinfo=dtz.utc),datetime(2026,3,8,10,30,tzinfo=dtz.utc),2,-420,-360),(datetime(2026,11,1,7,30,tzinfo=dtz.utc),datetime(2026,11,1,10,30,tzinfo=dtz.utc),3,-360,-420),(datetime(2026,10,13,4,tzinfo=dtz.utc),datetime(2026,10,13,12,tzinfo=dtz.utc),8,-360,-360)]:
            s=Shift.objects.create(employee=self.noah,start=start,end=end,original_start=start,original_end=end,shift_date=start.astimezone(DENVER).date())
            Break.objects.create(shift=s,employee=self.noah,start=start+timedelta(minutes=10),end=start+timedelta(minutes=40))
            d=shift_data(s);self.assertEqual(d['elapsed_hours'],elapsed);self.assertEqual(d['net_hours'],elapsed-.5);self.assertEqual(d['start_offset_minutes'],offset_a);self.assertEqual(d['end_offset_minutes'],offset_b)
    def test_ambiguous_denver_input_requires_offset(self):
        from django.core.exceptions import ValidationError
        field=DenverInput()
        with self.assertRaises(ValidationError):field.clean('2026-11-01T01:30:00')
        with self.assertRaises(ValidationError):field.clean('2026-03-08T02:30:00')
        self.assertIsNotNone(field.clean('2026-11-01T01:30:00-06:00'))
    def test_summary_snapshot_revisions_and_late_closeout(self):
        s=self.ended();original_end=s.end
        self.assertEqual(self.post('summary',{'comments':'All clear'},s.pk).status_code,302)
        first=SummaryRevision.objects.get();before=first.snapshot.copy()
        self.assertEqual(self.post('summary',{'comments':'Additional note'},s.pk).status_code,302)
        first.refresh_from_db();s.refresh_from_db();self.assertEqual(first.snapshot,before);self.assertEqual(s.end,original_end);self.assertEqual(SummaryRevision.objects.count(),2)
    def test_summary_before_end_rejected(self):
        self.act('start');s=self.noah.shifts.first();self.post('summary',{},s.pk);self.assertEqual(Summary.objects.count(),0)
    def test_summary_retry_is_exactly_once(self):
        s=self.ended();data={'request_id':str(uuid.uuid4()),'comments':'Done'}
        for _ in range(2):self.client.post(reverse('summary',args=[s.pk]),data)
        self.assertEqual(SummaryRevision.objects.count(),1)
    def test_handoff_authorized_acknowledgment(self):
        s=self.ended();end=s.end;self.post('handoff',{'recipient':self.umer.pk,'notes':'Next shift'},s.pk);h=Handoff.objects.get()
        self.assertEqual(self.post('acknowledge',pk=h.pk).status_code,403)
        self.client.force_login(self.umer);self.assertEqual(self.post('acknowledge',pk=h.pk).status_code,302)
        h.refresh_from_db();s.refresh_from_db();self.assertEqual(h.acknowledged_by,self.umer);self.assertEqual(s.end,end)
    def issue_payload(self):return {'description':'Flight diversion','booking':'0000123','status':'Open','owner':self.noah.pk,'next_action':'Confirm arrival','deadline':(timezone.now()+timedelta(hours=1)).isoformat(),'priority':'High','handoff':'on','management_attention':'on'}
    def test_exception_owner_deadline_resolution_reopening_history(self):
        self.act('start');payload=self.issue_payload();self.post('issue-new',payload);i=Issue.objects.get();self.assertEqual(i.booking,'0000123')
        payload['status']='Resolved';self.post('issue-edit',payload,i.pk);i.refresh_from_db();self.assertIsNotNone(i.resolved_at)
        payload['status']='In Progress';payload['owner']=self.umer.pk;self.post('issue-edit',payload,i.pk);i.refresh_from_db();self.assertIsNone(i.resolved_at);self.assertEqual(i.owner,self.umer);self.assertEqual(Issue.objects.count(),1);self.assertEqual(Audit.objects.filter(action='exception.updated').count(),2)
    def test_exception_missing_next_action_rejected(self):
        data=self.issue_payload();data['next_action']='';self.post('issue-new',data);self.assertEqual(Issue.objects.count(),0)
    def test_duplicate_business_form_and_conflicting_retry(self):
        payload={**self.issue_payload(),'request_id':str(uuid.uuid4())}
        url=reverse('issue-new');self.client.post(url,payload);self.client.post(url,payload);self.assertEqual(Issue.objects.count(),1)
        payload['description']='Different';self.assertEqual(self.client.post(url,payload).status_code,409)
    def verification(self,s):return Verification.objects.create(employee=self.noah,shift=s,subject='Acme',kind='Affiliate',market='Denver',criteria='License',checks='Checked',research_status='Research Complete')
    def test_verification_approval_management_only(self):
        self.act('start');s=self.noah.shifts.first();v=self.verification(s)
        self.assertEqual(self.post('approval',{'outcome':'Approved'},v.pk).status_code,403)
        self.client.force_login(self.manager);self.post('approval',{'outcome':'Approved','notes':'Evidence reviewed'},v.pk);v.refresh_from_db();self.assertEqual(v.approved_by,self.manager);self.assertEqual(v.outcome,'Approved')
    def prospect(self,s,response='No Response'):return Prospect.objects.create(employee=self.noah,shift=s,company='Hotel',contact='Jane',email='jane@example.test',market='Hotels',template='Approved',targeting='Hotels',response=response)
    def test_outreach_counts_explicit_sends_and_dnc(self):
        self.act('start');s=self.noah.shifts.first();p=self.prospect(s)
        self.assertEqual(Outreach.objects.count(),0)
        key=uuid.uuid4();data={'request_id':str(key),'confirmation':'Sent in approved mailbox, ref msg-1','sent':'on'}
        self.client.post(reverse('outreach',args=[p.pk]),data);self.client.post(reverse('outreach',args=[p.pk]),data)
        self.post('outreach',{'confirmation':'Second real send, msg-2','sent':'on'},p.pk)
        snapshot=summary_snapshot(s);self.assertEqual(snapshot['emails_sent'],2);self.assertEqual(snapshot['unique_contacts_reached'],1)
        p.response='Do Not Contact';p.save();self.post('outreach',{'confirmation':'Never allowed','sent':'on'},p.pk);self.assertEqual(Outreach.objects.count(),2)
        with self.assertRaises(DatabaseError),transaction.atomic():Outreach.objects.create(prospect=p,employee=self.noah,shift=s,confirmation='Bad',template_snapshot='Bad')
    def make_duty(self,cadence='shift',effective=None,active=True):
        d=Duty.objects.create(code='X01',active=active);v=DutyVersion.objects.create(duty=d,description='Actual test duty',instructions='Evidence required',frequency='Original frequency',section='Exceptions and Follow-Ups',author=self.manager)
        a=DutyAssignment.objects.create(duty=d,employee=self.noah,effective_start=effective or timezone.now().astimezone(DENVER).date(),cadence=cadence)
        return d,v,a
    def test_automatic_duties_and_historical_version(self):
        d,v,a=self.make_duty();self.act('start');sd=ShiftDuty.objects.get();self.assertEqual(sd.version,v);self.assertEqual(sd.status,'Completion Not Verified')
        DutyVersion.objects.create(duty=d,description='Changed later',instructions='New instructions',frequency='Weekly',section='Exceptions and Follow-Ups',author=self.manager)
        sd.refresh_from_db();self.assertEqual(sd.version.description,'Actual test duty')
    def test_named_group_applicability_and_inactive_group(self):
        d,v,a=self.make_duty();a.active=False;a.save()
        team=DutyGroup.objects.create(name='Airport coverage');team.members.add(self.noah)
        DutyAssignment.objects.create(duty=d,team=team,effective_start=timezone.now().astimezone(DENVER).date(),cadence='shift')
        self.act('start');self.assertEqual(ShiftDuty.objects.count(),1);self.act('end')
        team.active=False;team.save();self.act('start');self.assertEqual(ShiftDuty.objects.count(),1)
    def test_private_productivity_not_leaked_into_summary(self):
        own=self.ended()
        start=timezone.now()-timedelta(hours=2)
        other=Shift.objects.create(employee=self.umer,start=start,end=timezone.now(),original_start=start,original_end=timezone.now(),shift_date=start.astimezone(DENVER).date())
        Prospect.objects.create(employee=self.umer,shift=other,company='Private company',contact='Private contact',email='private@example.test',market='Private',template='Approved',targeting='Approved',response='Follow-Up Required')
        self.assertEqual(summary_snapshot(own)['responses_requiring_follow_up'],[])
    def test_approval_evidence_invalidated_on_research_change(self):
        d,version,a=self.make_duty();version.mapping='verification'
        # Immutable definitions are replaced by a new version instead of updated.
        version=DutyVersion.objects.create(duty=d,description='Verify affiliate',instructions='Check evidence',frequency='Per shift',section='Affiliate/Driver Verification',author=self.manager,mapping='verification')
        self.act('start');s=self.noah.shifts.first();v=self.verification(s);v.duty=d;v.save()
        self.client.force_login(self.manager);self.post('approval',{'outcome':'Approved'},v.pk)
        sd=ShiftDuty.objects.get();self.assertEqual(sd.status,'Verified')
        self.client.force_login(self.noah);self.post('verification-edit',{'subject':v.subject,'kind':v.kind,'market':v.market,'checks':'New research facts','research_status':'Research Complete','duty':d.pk},v.pk)
        sd.refresh_from_db();v.refresh_from_db();self.assertEqual(sd.status,'Completion Not Verified');self.assertEqual(v.outcome,'Pending')
    def test_future_inactive_unassigned_do_not_alert(self):
        self.make_duty(effective=timezone.now().date()+timedelta(days=5));self.act('start');self.assertEqual(ShiftDuty.objects.count(),0)
    def test_conditional_and_daily_duties(self):
        d,v,a=self.make_duty(cadence='conditional');a.condition='snow';a.save();self.act('start');self.assertEqual(ShiftDuty.objects.count(),0);self.act('end')
        Condition.objects.create(employee=self.noah,name='snow',applicable_date=timezone.now().astimezone(DENVER).date(),recorded_by=self.manager,evidence='Forecast')
        self.act('start');self.assertEqual(ShiftDuty.objects.count(),1)
    def test_duty_assignment_revision_keeps_old(self):
        d,v,a=self.make_duty();self.act('start');self.client.force_login(self.manager)
        self.post('assignment-edit',{'duty':d.pk,'employee':self.noah.pk,'group':'','effective_start':a.effective_start,'cadence':'weekly','weekdays':'[]','deadline_minutes':100,'active':'on'},a.pk)
        a.refresh_from_db();self.assertFalse(a.active);self.assertEqual(a.cadence,'shift');self.assertEqual(ShiftDuty.objects.get().assignment,a);self.assertEqual(DutyAssignment.objects.filter(active=True).count(),1)
    def test_correction_preserves_original_and_recalculates(self):
        start=timezone.now()-timedelta(hours=8);end=timezone.now()-timedelta(hours=1)
        s=Shift.objects.create(employee=self.noah,start=start,end=end,original_start=start,original_end=end,shift_date=start.astimezone(DENVER).date())
        self.client.force_login(self.manager);self.post('correction',{'start':(start-timedelta(hours=1)).isoformat(),'end':end.isoformat(),'reason':'Verified against dispatch sign-in'},s.pk)
        s.refresh_from_db();self.assertEqual(s.original_start,start);self.assertEqual(metrics(s)['elapsed_hours'],8);self.assertEqual(Correction.objects.count(),1)
        with self.assertRaises(DatabaseError),transaction.atomic():Shift.objects.filter(pk=s.pk).update(original_start=timezone.now())
    def test_immutable_audit_and_summary(self):
        s=self.ended();self.post('summary',{},s.pk)
        with self.assertRaises(DatabaseError),transaction.atomic():SummaryRevision.objects.all().update(comments='Tamper')
        with self.assertRaises(DatabaseError),transaction.atomic():Audit.objects.all().update(action='Tamper')
    def test_deactivation_revokes_sessions_closes_shift_and_reassigns(self):
        self.act('start');self.act('break_start');s=self.noah.shifts.first();self.post('issue-new',self.issue_payload());h=Handoff.objects.create(shift=s,sender=self.noah,recipient=self.umer,snapshot={})
        uclient=Client();uclient.force_login(self.umer);uclient.get('/')
        self.client.force_login(self.manager);self.post('deactivate',{'recipient':self.manager.pk,'reason':'Offboarding'},self.umer.pk)
        h.refresh_from_db();self.assertEqual(h.recipient,self.manager);self.assertRedirects(uclient.get('/'),'/login/?next=/',fetch_redirect_response=False)
        self.post('deactivate',{'recipient':self.manager.pk,'reason':'Offboarding','close_active_shift':'on'},self.noah.pk)
        s.refresh_from_db();self.assertIsNotNone(s.end);self.assertFalse(s.breaks.filter(end=None).exists());self.assertEqual(Issue.objects.get().owner,self.manager)
    @override_settings(EMAIL_HOST='smtp.test',EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_invite_and_reset_email_single_use(self):
        self.client.force_login(self.manager);self.post('invite',{'name':'New dispatcher','email':'new@example.test','role':'dispatcher'})
        u=User.objects.get(email='new@example.test');self.assertFalse(u.has_usable_password());self.assertEqual(len(mail.outbox),1)
        link=re.search(r'http://testserver(/reset/[^\s]+)',mail.outbox[0].body).group(1)
        c=Client();new='Another-secure-passphrase-429!';self.assertEqual(c.post(link,{'new_password1':new,'new_password2':new}).status_code,302)
        self.assertEqual(c.get(link).status_code,400);self.assertTrue(c.login(username=u.email,password=new))
    @override_settings(EMAIL_HOST='smtp.test',EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_forgot_password_neutral_and_expired(self):
        c=Client();r1=c.post('/forgot-password/',{'email':self.noah.email});r2=c.post('/forgot-password/',{'email':'unknown@example.test'});self.assertEqual(r1.content,r2.content);self.assertEqual(len(mail.outbox),1)
        uid=urlsafe_base64_encode(force_bytes(self.noah.pk));token=default_token_generator.make_token(self.noah)
        with override_settings(PASSWORD_RESET_TIMEOUT=0),patch.object(default_token_generator,'_now',return_value=datetime.now()+timedelta(seconds=10)):
            self.assertEqual(c.get(reverse('reset-confirm',args=[uid,token])).status_code,400)
    def test_password_change_and_revoke_sessions(self):
        other=Client();other.force_login(self.noah);other.get('/')
        self.post('revoke-sessions');self.assertEqual(other.get('/').status_code,302)
        new='Strong-new-passphrase-823!';self.assertEqual(self.client.post('/account/password/',{'old_password':PASSWORD,'new_password1':new,'new_password2':new}).status_code,302)
        self.noah.refresh_from_db();self.assertTrue(self.noah.check_password(new))
    def test_initial_password_requires_change(self):
        self.noah.must_change_password=True;self.noah.save();self.assertRedirects(self.client.get('/'),'/account/password/',fetch_redirect_response=False)
        self.assertEqual(self.client.get('/api/sync/').status_code,403)
    def test_login_rate_limit(self):
        c=Client()
        for _ in range(8):c.post('/login/',{'username':self.noah.email,'password':'wrong'})
        self.assertEqual(c.post('/login/',{'username':self.noah.email,'password':'wrong'}).status_code,429)
    def test_all_dashboard_pages_render_and_no_private_sync(self):
        self.act('start');s=self.noah.shifts.first()
        for path in ['/','/attendance/','/exceptions/','/duties/','/productivity/','/handoffs/','/account/',reverse('shift-detail',args=[s.pk])]:self.assertEqual(self.client.get(path).status_code,200,path)
        self.client.force_login(self.umer);self.assertIsNone(self.client.get('/api/sync/').json()['shift'])
        self.client.force_login(self.manager)
        for path in ['/management/','/management/employees/','/management/schedules/','/management/settings/','/management/audit/','/duties/','/productivity/']:
            self.assertEqual(self.client.get(path).status_code,200,path)
    def test_missed_schedule_excludes_leave_and_future(self):
        now=timezone.now();Schedule.objects.create(employee=self.noah,start=now-timedelta(hours=2),end=now+timedelta(hours=6));Schedule.objects.create(employee=self.umer,start=now+timedelta(days=1),end=now+timedelta(days=1,hours=8))
        Leave.objects.create(employee=self.noah,start=now-timedelta(hours=3),end=now+timedelta(hours=7),reason='Approved leave',approved_by=self.manager)
        self.client.force_login(self.manager);r=self.client.get('/management/');self.assertEqual(len(r.context['missed']),0)
    def test_unresolved_backlog_survives_period_filters(self):
        self.post('issue-new',self.issue_payload());self.client.force_login(self.manager)
        r=self.client.get('/management/?from=2099-01-01');self.assertEqual(len(r.context['backlog']),1);self.assertEqual(len(r.context['rows']),0)
    def test_csrf_enforced(self):
        c=Client(enforce_csrf_checks=True);c.force_login(self.noah);self.assertEqual(c.post('/api/shift-action/',{'action':'start','request_id':str(uuid.uuid4())}).status_code,403)
    def test_workbook_exact_import_repeat_and_atomic_rejection(self):
        with tempfile.NamedTemporaryFile(suffix='.csv',mode='w+',newline='') as f:
            w=csv.writer(f);w.writerow(['code','description','instructions','frequency'])
            for i in range(1,61):w.writerow([f'D{i:02}',f'Original full source description {i}',f'Original instructions {i}','Original frequency unchanged'])
            f.flush();self.assertEqual(import_workbook(f.name,self.manager),60);self.assertEqual(import_workbook(f.name,self.manager),0);self.assertEqual(Duty.objects.count(),60)
            self.assertEqual(DutyVersion.objects.get(duty__code='D60').instructions,'Original instructions 60')
        with tempfile.NamedTemporaryFile(suffix='.csv',mode='w+',newline='') as f:
            f.write('code,description,instructions,frequency\nD01,Changed,Instruction,Daily\n');f.flush()
            with self.assertRaises(WorkflowError):import_workbook(f.name,self.manager)
            self.assertEqual(Duty.objects.count(),60)

class ConcurrencyTests(TransactionTestCase):
    def test_simultaneous_start_and_retry(self):
        u=User.objects.create_user(username='parallel@example.test',email='parallel@example.test',password=PASSWORD)
        def action(key):
            close_old_connections()
            try:return attendance_action(User.objects.get(pk=u.pk),'start',key)['saved']
            except WorkflowError:return False
            finally:connections.close_all()
        key=uuid.uuid4()
        with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(action,[key,key,uuid.uuid4()]))
        self.assertEqual(Shift.objects.count(),1);self.assertEqual(ShiftEvent.objects.count(),1);self.assertEqual(sum(results),2)

class ResendBackendTests(TestCase):
    @override_settings(EMAIL_BACKEND='operations.resend_backend.EmailBackend',RESEND_API_KEY='test-only-placeholder',DEFAULT_FROM_EMAIL='accounts@example.test')
    def test_acceptance_checks_and_request_payload(self):
        from django.core.mail import send_mail
        from unittest.mock import MagicMock
        response=MagicMock();response.__enter__.return_value=response;response.status=200;response.read.return_value=b'{"id":"test-email-id"}'
        with patch('operations.resend_backend.urllib.request.urlopen',return_value=response) as transport:
            self.assertEqual(send_mail('Test subject','Test body','accounts@example.test',['noah@example.test']),1)
            request=transport.call_args.args[0]
            self.assertEqual(request.full_url,'https://api.resend.com/emails')
            self.assertEqual(json.loads(request.data)['to'],['noah@example.test'])
            self.assertEqual(request.get_header('Authorization'),'Bearer test-only-placeholder')
    @override_settings(EMAIL_BACKEND='operations.resend_backend.EmailBackend',RESEND_API_KEY='')
    def test_missing_key_fails_without_logging_credentials(self):
        from django.core.mail import send_mail
        with self.assertRaises(RuntimeError):send_mail('Subject','Body','a@example.test',['b@example.test'])
    @override_settings(EMAIL_BACKEND='operations.resend_backend.EmailBackend',RESEND_API_KEY='test-only-placeholder')
    def test_unconfirmed_provider_response_is_failure(self):
        from django.core.mail import send_mail
        from unittest.mock import MagicMock
        response=MagicMock();response.__enter__.return_value=response;response.status=200;response.read.return_value=b'{}'
        with patch('operations.resend_backend.urllib.request.urlopen',return_value=response):
            with self.assertRaises(RuntimeError):send_mail('Subject','Body','a@example.test',['b@example.test'])
    @override_settings(EMAIL_BACKEND='operations.resend_backend.EmailBackend',RESEND_API_KEY='test-only-placeholder')
    def test_provider_errors_are_sanitized(self):
        from django.core.mail import send_mail
        with patch('operations.resend_backend.urllib.request.urlopen',side_effect=RuntimeError('Sensitive token and provider body')):
            with self.assertRaises(RuntimeError) as caught:send_mail('Subject','Body','a@example.test',['b@example.test'])
            self.assertNotIn('Sensitive token',str(caught.exception))
            self.assertEqual(send_mail('Subject','Body','a@example.test',['b@example.test'],fail_silently=True),0)
