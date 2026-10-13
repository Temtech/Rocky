from django import template
from operations.services import metrics,shift_status,duty_status,attendance_warnings
import json
register=template.Library()
@register.filter
def status(s): return shift_status(s)
@register.filter
def duty_state(d): return duty_status(d)
@register.filter
def hours(s):
    m=metrics(s)
    return f"{m['net_hours']:.2f}" if m['net_hours'] is not None else 'Incomplete'
@register.filter
def pretty(value): return json.dumps(value,indent=2,ensure_ascii=False)
@register.filter
def short_id(value): return str(value)[:8].upper()
@register.filter
def tone(value):
    if str(value) in ['Resolved','Closed','Verified','Approved','Reviewed','Ended','Working']: return 'good'
    if str(value) in ['Overdue','Urgent','High','Rejected','Follow-Up Required','Do Not Contact']: return 'danger'
    if str(value) in ['Pending','Open','In Progress','On Break','Awaiting Response','Blocked']: return 'warn'
    return 'neutral'
