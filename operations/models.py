import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q, F
from django.utils import timezone

class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=[('dispatcher','Dispatcher'),('management','Management')], default='dispatcher')
    session_version = models.PositiveIntegerField(default=0)
    must_change_password = models.BooleanField(default=False)
    def __str__(self): return self.first_name or self.username

class Record(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    class Meta: abstract = True

class Policy(models.Model):
    id = models.PositiveIntegerField(primary_key=True, default=1)
    grace_minutes = models.PositiveIntegerField(default=5)
    break_minutes = models.PositiveIntegerField(default=30)
    warning_minutes = models.PositiveIntegerField(default=60)
    instructions = models.TextField(default='Active Dispatch → Exceptions and Follow-Ups → Affiliate/Driver Verification → Cold Email Marketing. Stop downtime work immediately when operations require attention.')
    verification_criteria = models.TextField(blank=True)
    marketing_template = models.TextField(blank=True)
    targeting = models.TextField(blank=True)
    payroll_policy = models.TextField(blank=True)

class Schedule(Record):
    employee = models.ForeignKey(User, on_delete=models.PROTECT)
    start = models.DateTimeField()
    end = models.DateTimeField()
    class Meta:
        ordering = ['start']
        constraints = [models.CheckConstraint(condition=Q(end__gt=F('start')),name='schedule_positive')]

class Leave(Record):
    employee = models.ForeignKey(User, on_delete=models.PROTECT)
    start = models.DateTimeField()
    end = models.DateTimeField()
    reason = models.TextField()
    approved_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='approved_leaves')
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(end__gt=F('start')),name='leave_positive')]

class Shift(Record):
    employee = models.ForeignKey(User, on_delete=models.PROTECT, related_name='shifts')
    schedule = models.ForeignKey(Schedule, null=True, blank=True, on_delete=models.PROTECT)
    shift_date = models.DateField()
    start = models.DateTimeField(default=timezone.now)
    end = models.DateTimeField(null=True, blank=True)
    original_start = models.DateTimeField()
    original_end = models.DateTimeField(null=True, blank=True)
    review = models.CharField(max_length=30,default='Pending',choices=[(x,x) for x in ['Pending','Reviewed','Follow-Up Required']])
    manager_comments = models.TextField(blank=True)
    class Meta:
        ordering = ['-start']
        constraints = [models.UniqueConstraint(fields=['employee'],condition=Q(end__isnull=True),name='one_active_shift'),models.CheckConstraint(condition=Q(end__isnull=True)|Q(end__gte=F('start')),name='shift_positive')]

class Break(Record):
    shift = models.ForeignKey(Shift,on_delete=models.PROTECT,related_name='breaks')
    employee = models.ForeignKey(User,on_delete=models.PROTECT)
    start = models.DateTimeField(default=timezone.now)
    end = models.DateTimeField(null=True,blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['shift'],condition=Q(end__isnull=True),name='one_open_break'),models.CheckConstraint(condition=Q(end__isnull=True)|Q(end__gte=F('start')),name='break_positive')]

class ShiftEvent(Record):
    shift = models.ForeignKey(Shift,on_delete=models.PROTECT,related_name='events')
    actor = models.ForeignKey(User,on_delete=models.PROTECT)
    action = models.CharField(max_length=40)

class Idempotency(Record):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    key = models.UUIDField()
    action = models.CharField(max_length=100)
    fingerprint = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    class Meta: constraints = [models.UniqueConstraint(fields=['user','key'],name='unique_request')]

class Duty(Record):
    code = models.CharField(max_length=30,unique=True)
    active = models.BooleanField(default=True)
    source_hash = models.CharField(max_length=64,blank=True)
    source = models.CharField(max_length=200,blank=True)
    def __str__(self): return self.code

class DutyVersion(Record):
    duty = models.ForeignKey(Duty,on_delete=models.PROTECT,related_name='versions')
    description = models.TextField()
    instructions = models.TextField(blank=True)
    frequency = models.TextField()
    section = models.CharField(max_length=40,choices=[(x,x) for x in ['Active Dispatch','Exceptions and Follow-Ups','Affiliate/Driver Verification','Cold Email Marketing']])
    mapping = models.CharField(max_length=20,blank=True,choices=[('','Unmapped'),('exception','Exception'),('verification','Approved verification'),('outreach','Confirmed send')])
    guidance_only = models.BooleanField(default=False)
    author = models.ForeignKey(User,on_delete=models.PROTECT)

class DutyGroup(Record):
    name=models.CharField(max_length=150,unique=True)
    members=models.ManyToManyField(User,related_name='duty_groups',blank=True)
    active=models.BooleanField(default=True)
    def __str__(self): return self.name

class DutyAssignment(Record):
    duty = models.ForeignKey(Duty,on_delete=models.PROTECT,related_name='assignments')
    employee = models.ForeignKey(User,null=True,blank=True,on_delete=models.PROTECT)
    group = models.CharField(max_length=20,blank=True,choices=[('','Individual or named group'),('dispatchers','All dispatchers')])
    team = models.ForeignKey(DutyGroup,null=True,blank=True,on_delete=models.PROTECT)
    effective_start = models.DateField()
    effective_end = models.DateField(null=True,blank=True)
    cadence = models.CharField(max_length=20,choices=[(x,x) for x in ['shift','daily','weekly','monthly','conditional']])
    weekdays = models.JSONField(default=list,blank=True)
    deadline_minutes = models.PositiveIntegerField(default=480)
    condition = models.CharField(max_length=100,blank=True)
    active = models.BooleanField(default=True)

class Condition(Record):
    employee = models.ForeignKey(User,on_delete=models.PROTECT)
    name = models.CharField(max_length=100)
    applicable_date = models.DateField()
    recorded_by = models.ForeignKey(User,on_delete=models.PROTECT,related_name='recorded_conditions')
    evidence = models.TextField()

class ShiftDuty(Record):
    shift = models.ForeignKey(Shift,on_delete=models.PROTECT,related_name='duties')
    assignment = models.ForeignKey(DutyAssignment,on_delete=models.PROTECT)
    version = models.ForeignKey(DutyVersion,on_delete=models.PROTECT)
    deadline = models.DateTimeField()
    status = models.CharField(max_length=30,default='Completion Not Verified',choices=[(x,x) for x in ['Completion Not Verified','Pending','Blocked','Verified']])
    evidence = models.TextField(blank=True)
    class Meta: constraints = [models.UniqueConstraint(fields=['shift','assignment'],name='one_shift_assignment')]

class Issue(Record):
    reporter = models.ForeignKey(User,on_delete=models.PROTECT,related_name='reported_issues')
    shift = models.ForeignKey(Shift,null=True,blank=True,on_delete=models.PROTECT)
    booking = models.CharField(max_length=100,blank=True)
    description = models.TextField()
    action_taken = models.TextField(blank=True)
    status = models.CharField(max_length=30,default='Open',choices=[(x,x) for x in ['Open','In Progress','Awaiting Response','Resolved','Closed']])
    owner = models.ForeignKey(User,on_delete=models.PROTECT,related_name='owned_issues')
    next_action = models.TextField()
    deadline = models.DateTimeField()
    priority = models.CharField(max_length=20,default='Normal',choices=[(x,x) for x in ['Urgent','High','Normal','Low']])
    management_attention = models.BooleanField(default=False)
    handoff = models.BooleanField(default=False)
    duty = models.ForeignKey(Duty,null=True,blank=True,on_delete=models.PROTECT)
    resolved_at = models.DateTimeField(null=True,blank=True)
    class Meta: indexes = [models.Index(fields=['status','deadline'])]

class Verification(Record):
    employee = models.ForeignKey(User,on_delete=models.PROTECT)
    shift = models.ForeignKey(Shift,on_delete=models.PROTECT)
    subject = models.CharField(max_length=200)
    kind = models.CharField(max_length=20,choices=[('Affiliate','Affiliate'),('Driver','Driver')])
    market = models.CharField(max_length=150)
    criteria = models.TextField()
    checks = models.TextField()
    research_status = models.CharField(max_length=30,choices=[(x,x) for x in ['In Progress','Research Complete']])
    outcome = models.CharField(max_length=30,default='Pending',choices=[(x,x) for x in ['Pending','Approved','Rejected','Follow-Up Required']])
    notes = models.TextField(blank=True)
    duty = models.ForeignKey(Duty,null=True,blank=True,on_delete=models.PROTECT)
    approved_by = models.ForeignKey(User,null=True,blank=True,on_delete=models.PROTECT,related_name='verification_approvals')
    reviewed_at = models.DateTimeField(null=True,blank=True)
    class Meta: constraints = [models.UniqueConstraint(fields=['subject','kind','market'],name='stable_verification_subject')]

class Prospect(Record):
    employee = models.ForeignKey(User,on_delete=models.PROTECT)
    shift = models.ForeignKey(Shift,on_delete=models.PROTECT)
    company = models.CharField(max_length=200)
    contact = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    market = models.CharField(max_length=200)
    template = models.TextField()
    targeting = models.TextField()
    response = models.CharField(max_length=40,default='No Response',choices=[(x,x) for x in ['No Response','Interested','Not Interested','Follow-Up Required','Do Not Contact']])
    follow_up = models.DateTimeField(null=True,blank=True)
    notes = models.TextField(blank=True)
    duty = models.ForeignKey(Duty,null=True,blank=True,on_delete=models.PROTECT)

class Outreach(Record):
    prospect = models.ForeignKey(Prospect,on_delete=models.PROTECT,related_name='sends')
    employee = models.ForeignKey(User,on_delete=models.PROTECT)
    shift = models.ForeignKey(Shift,on_delete=models.PROTECT)
    confirmation = models.TextField()
    template_snapshot = models.TextField()

class Response(Record):
    prospect = models.ForeignKey(Prospect,on_delete=models.PROTECT,related_name='responses')
    employee = models.ForeignKey(User,on_delete=models.PROTECT)
    status = models.CharField(max_length=40)
    notes = models.TextField(blank=True)

class Summary(Record):
    shift = models.OneToOneField(Shift,on_delete=models.PROTECT,related_name='summary')
    review = models.CharField(max_length=30,default='Pending',choices=[(x,x) for x in ['Pending','Reviewed','Follow-Up Required']])
    manager_comments = models.TextField(blank=True)

class SummaryRevision(Record):
    summary = models.ForeignKey(Summary,on_delete=models.PROTECT,related_name='revisions')
    author = models.ForeignKey(User,on_delete=models.PROTECT)
    snapshot = models.JSONField()
    comments = models.TextField(blank=True)

class Handoff(Record):
    shift = models.ForeignKey(Shift,on_delete=models.PROTECT,related_name='handoffs')
    sender = models.ForeignKey(User,on_delete=models.PROTECT,related_name='sent_handoffs')
    recipient = models.ForeignKey(User,on_delete=models.PROTECT,related_name='received_handoffs')
    snapshot = models.JSONField()
    notes = models.TextField(blank=True)
    acknowledged_by = models.ForeignKey(User,null=True,blank=True,on_delete=models.PROTECT,related_name='acknowledgments')
    acknowledged_at = models.DateTimeField(null=True,blank=True)

class Correction(Record):
    shift = models.ForeignKey(Shift,on_delete=models.PROTECT,related_name='corrections')
    manager = models.ForeignKey(User,on_delete=models.PROTECT)
    reason = models.TextField()
    previous_start = models.DateTimeField()
    previous_end = models.DateTimeField(null=True)
    corrected_start = models.DateTimeField()
    corrected_end = models.DateTimeField(null=True)

class Audit(Record):
    actor = models.ForeignKey(User,null=True,on_delete=models.PROTECT)
    action = models.CharField(max_length=100)
    target = models.CharField(max_length=100)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    class Meta: ordering = ['-created_at']

class RateLimit(models.Model):
    key = models.CharField(max_length=64,primary_key=True)
    window = models.DateTimeField(default=timezone.now)
    count = models.PositiveIntegerField(default=0)
