from django.urls import path
from django.contrib.auth.views import LogoutView
from operations import views as v, auth_views as a
from operations.idempotency import protected_write,rechecked_write
for name in ['issue_edit','verification_edit','prospect_edit','invite','reset_invite','deactivate','reactivate','employee_role','settings_view','schedule_edit','duty_edit','assignment_edit','condition_create','duty_evidence','approval','correction','review','revoke_sessions','revoke_employee_sessions','acknowledge','duty_import','group_edit']:
    setattr(v,name,protected_write(getattr(v,name)))
for name in ['summary','handoff','outreach']:
    setattr(v,name,rechecked_write(getattr(v,name)))
urlpatterns=[
 path('',v.dashboard,name='dashboard'),path('login/',a.LoginView.as_view(),name='login'),path('logout/',LogoutView.as_view(),name='logout'),
 path('forgot-password/',a.forgot,name='forgot'),path('reset/<str:uid>/<str:token>/',a.reset_confirm,name='reset-confirm'),path('account/',v.account,name='account'),path('account/password/',a.PasswordChangeView.as_view(),name='password-change'),path('account/revoke/',v.revoke_sessions,name='revoke-sessions'),
 path('api/shift-action/',v.shift_action,name='shift-action'),path('api/sync/',v.sync,name='sync'),path('api/shifts/<uuid:pk>/',v.shift_api,name='shift-api'),
 path('attendance/',v.attendance,name='attendance'),path('shifts/<uuid:pk>/',v.shift_detail,name='shift-detail'),path('shifts/<uuid:pk>/summary/',v.summary,name='summary'),path('shifts/<uuid:pk>/handoff/',v.handoff,name='handoff'),path('shifts/<uuid:pk>/correct/',v.correction,name='correction'),path('shifts/<uuid:pk>/review/',v.review,name='review'),
 path('exceptions/',v.issues,name='issues'),path('exceptions/new/',v.issue_edit,name='issue-new'),path('exceptions/<uuid:pk>/',v.issue_edit,name='issue-edit'),
 path('productivity/',v.productivity,name='productivity'),path('verification/new/',v.verification_edit,name='verification-new'),path('verification/<uuid:pk>/',v.verification_edit,name='verification-edit'),path('verification/<uuid:pk>/approve/',v.approval,name='approval'),path('prospects/new/',v.prospect_edit,name='prospect-new'),path('prospects/<uuid:pk>/',v.prospect_edit,name='prospect-edit'),path('prospects/<uuid:pk>/send/',v.outreach,name='outreach'),
 path('handoffs/',v.handoffs,name='handoffs'),path('handoffs/<uuid:pk>/acknowledge/',v.acknowledge,name='acknowledge'),
 path('duties/',v.duties,name='duties'),path('duties/new/',v.duty_edit,name='duty-new'),path('duties/<uuid:pk>/edit/',v.duty_edit,name='duty-edit'),path('assignments/new/',v.assignment_edit,name='assignment-new'),path('assignments/<uuid:pk>/',v.assignment_edit,name='assignment-edit'),path('conditions/new/',v.condition_create,name='condition-new'),path('duty-evidence/<uuid:pk>/',v.duty_evidence,name='duty-evidence'),
 path('management/',v.management,name='management'),path('management/employees/',v.employees,name='employees'),path('management/invite/',v.invite,name='invite'),path('management/employees/<uuid:pk>/reset/',v.reset_invite,name='reset-invite'),path('management/employees/<uuid:pk>/deactivate/',v.deactivate,name='deactivate'),path('management/employees/<uuid:pk>/reactivate/',v.reactivate,name='reactivate'),path('management/employees/<uuid:pk>/role/',v.employee_role,name='employee-role'),path('management/employees/<uuid:pk>/revoke/',v.revoke_employee_sessions,name='revoke-employee'),
 path('management/settings/',v.settings_view,name='settings'),path('management/schedules/',v.schedules,name='schedules'),path('management/schedules/new/',v.schedule_edit,name='schedule-new'),path('management/schedules/<uuid:pk>/',v.schedule_edit,name='schedule-edit'),path('management/leave/new/',v.schedule_edit,{'leave':True},name='leave-new'),path('management/audit/',v.audit_history,name='audit'),
]
urlpatterns += [path('management/duties/import/',v.duty_import,name='duty-import')]

urlpatterns += [path('management/groups/new/',v.group_edit,name='group-new'),path('management/groups/<uuid:pk>/',v.group_edit,name='group-edit')]
