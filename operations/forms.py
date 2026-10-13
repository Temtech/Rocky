from django import forms
from django.contrib.auth import password_validation
from .models import *
from .services import DENVER
from datetime import datetime

class DenverInput(forms.DateTimeField):
    def clean(self,value):
        if isinstance(value,str) and value:
            try:
                dt=datetime.fromisoformat(value)
                if dt.tzinfo is None:
                    a=dt.replace(tzinfo=DENVER,fold=0); b=dt.replace(tzinfo=DENVER,fold=1)
                    if a.utcoffset()!=b.utcoffset():
                        raise forms.ValidationError('Ambiguous or nonexistent Denver time. Supply an explicit UTC offset, such as -06:00 or -07:00.')
            except ValueError: pass
        return super().clean(value)

def model_form(model,fields):
    cls=forms.modelform_factory(model,fields=fields)
    for name,field in cls.base_fields.items():
        if isinstance(field,forms.DateTimeField):
            cls.base_fields[name]=DenverInput(required=field.required,help_text='Denver time. Use ISO date/time; add an offset for daylight-saving transitions.',widget=forms.TextInput(attrs={'placeholder':'2026-10-13T08:00:00-06:00'}))
        if isinstance(field,forms.ModelChoiceField) and field.queryset.model==User:
            field.queryset=User.objects.filter(is_active=True)
    return cls

IssueForm=model_form(Issue,['booking','description','action_taken','status','owner','next_action','deadline','priority','management_attention','handoff','duty'])
VerificationForm=model_form(Verification,['subject','kind','market','checks','research_status','notes','duty'])
ProspectForm=model_form(Prospect,['company','contact','email','market','response','follow_up','notes','duty'])
ScheduleForm=model_form(Schedule,['employee','start','end'])
LeaveForm=model_form(Leave,['employee','start','end','reason'])
PolicyForm=model_form(Policy,['grace_minutes','break_minutes','warning_minutes','instructions','verification_criteria','marketing_template','targeting','payroll_policy'])
AssignmentForm=model_form(DutyAssignment,['duty','employee','group','team','effective_start','effective_end','cadence','weekdays','deadline_minutes','condition','active'])
ConditionForm=model_form(Condition,['employee','name','applicable_date','evidence'])
class ValidAssignmentForm(AssignmentForm):
    def clean(self):
        d=super().clean()
        if sum(bool(d.get(x)) for x in ['employee','group','team'])!=1: self.add_error(None,'Choose exactly one employee, all dispatchers or a named group.')
        if d.get('effective_end') and d.get('effective_start') and d['effective_end']<d['effective_start']: self.add_error('effective_end','Must be on or after the effective start.')
        if d.get('cadence')=='conditional' and not d.get('condition'): self.add_error('condition','A recorded condition name is required.')
        days=d.get('weekdays')
        if not isinstance(days,list) or any(not isinstance(x,int) or isinstance(x,bool) or x<0 or x>6 for x in days): self.add_error('weekdays','Enter a JSON list of weekday numbers 0 (Monday) through 6.')
        return d
AssignmentForm=ValidAssignmentForm

class InviteForm(forms.Form):
    name=forms.CharField(max_length=150)
    email=forms.EmailField()
    role=forms.ChoiceField(choices=User._meta.get_field('role').choices)
    def clean_email(self):
        email=self.cleaned_data['email'].lower()
        if User.objects.filter(email__iexact=email).exists(): raise forms.ValidationError('An account already uses this email.')
        return email
class DutyForm(forms.Form):
    code=forms.CharField(max_length=30)
    description=forms.CharField(widget=forms.Textarea)
    instructions=forms.CharField(widget=forms.Textarea,required=False)
    frequency=forms.CharField(widget=forms.Textarea)
    section=forms.ChoiceField(choices=DutyVersion._meta.get_field('section').choices)
    mapping=forms.ChoiceField(choices=DutyVersion._meta.get_field('mapping').choices,required=False)
    guidance_only=forms.BooleanField(required=False)
    active=forms.BooleanField(required=False,initial=True)
class CloseoutForm(forms.Form):
    comments=forms.CharField(widget=forms.Textarea,required=False)
class HandoffForm(forms.Form):
    recipient=forms.ModelChoiceField(queryset=User.objects.filter(is_active=True))
    notes=forms.CharField(widget=forms.Textarea,required=False)
class CorrectionForm(forms.Form):
    start=DenverInput()
    end=DenverInput(required=False)
    reason=forms.CharField(widget=forms.Textarea)
class ReviewForm(forms.Form):
    review=forms.ChoiceField(choices=Shift._meta.get_field('review').choices)
    manager_comments=forms.CharField(widget=forms.Textarea,required=False)
class ApprovalForm(forms.Form):
    outcome=forms.ChoiceField(choices=Verification._meta.get_field('outcome').choices)
    notes=forms.CharField(widget=forms.Textarea,required=False)
class OutreachForm(forms.Form):
    confirmation=forms.CharField(widget=forms.Textarea,help_text='Confirm that you personally sent the email in the approved email system. Enter the sending account, subject and message reference. This records your confirmation; this app does not send marketing email.')
    sent=forms.BooleanField(label='I confirm this email was actually sent')
class DeactivateForm(forms.Form):
    recipient=forms.ModelChoiceField(queryset=User.objects.filter(is_active=True),help_text='Pending handoffs and unresolved owned issues will be reassigned.')
    reason=forms.CharField(widget=forms.Textarea)
    close_active_shift=forms.BooleanField(required=False,label='Close any active shift now using server time')
class EvidenceForm(forms.Form):
    status=forms.ChoiceField(choices=ShiftDuty._meta.get_field('status').choices)
    evidence=forms.CharField(widget=forms.Textarea,required=False)
    def clean(self):
        d=super().clean()
        if d.get('status')=='Verified' and not d.get('evidence','').strip(): self.add_error('evidence','Management must record sufficient source evidence to verify completion.')
        return d

GroupForm=model_form(DutyGroup,['name','members','active'])
GroupForm.base_fields['members'].queryset=User.objects.filter(is_active=True,role='dispatcher')
