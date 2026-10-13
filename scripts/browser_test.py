"""Actual Chromium frontend/backend/PostgreSQL integration; isolated rocky_e2e DB only."""
import os,sys,secrets,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','rocky.settings')
import django
django.setup()
from operations.models import *
from operations.services import DENVER
from django.utils import timezone
from datetime import timedelta
from playwright.sync_api import sync_playwright
if not os.environ.get('DATABASE_URL','').endswith('/rocky_e2e'):raise RuntimeError('Browser tests must run only against rocky_e2e.')
# Playwright's synchronous test API runs an event loop on this test thread.
# Database assertions are sequential; this override is confined to this test process.
os.environ['DJANGO_ALLOW_ASYNC_UNSAFE']='true'
password=secrets.token_urlsafe(24)
users={}
for name,role in [('Noah','dispatcher'),('Umer','dispatcher'),('Teddy','management')]:
    u,_=User.objects.get_or_create(email=f'{name.lower()}@example.test',defaults={'username':f'{name.lower()}@example.test','first_name':name,'role':role})
    u.set_password(password);u.must_change_password=False;u.save();users[name]=u
p,_=Policy.objects.get_or_create(pk=1)
p.verification_criteria='Browser test: insurance, license, service references';p.marketing_template='Browser test approved template';p.targeting='Browser test hotels';p.save()
root=Path('test-results');root.mkdir(exist_ok=True)
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    context=browser.new_context(viewport={'width':1440,'height':1024})
    page=context.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    base='http://127.0.0.1:8001'
    def sign_in(name):
        page.goto(base+'/login/');page.locator('[name=username]').fill(users[name].email);page.locator('[name=password]').fill(password);page.get_by_role('button',name='Sign in').click();page.wait_for_url(base+('/management/' if name=='Teddy' else '/'))
    def save():
        current=page.url
        page.get_by_role('button',name='Save to backend').click();page.wait_for_url(lambda url: str(url)!=current);page.wait_for_load_state('networkidle')
        assert not page.locator('.errorlist').count(),page.locator('.errorlist').all_text_contents()
    sign_in('Noah');page.wait_for_function("document.querySelector('#sync-status').textContent.includes('Synced')")
    if '--verify-restart' not in sys.argv:
        page.get_by_role('button',name='Start Shift / Working').click();page.wait_for_load_state('networkidle');assert Shift.objects.filter(employee=users['Noah'],end=None).count()==1
        assert not page.get_by_role('button',name='Start Shift / Working',include_hidden=True).is_visible()
        assert not page.get_by_role('button',name='End Break / Return to Work',include_hidden=True).is_visible()
        for _ in range(2):
            page.get_by_role('button',name='Start Break',exact=True).click();page.wait_for_load_state('networkidle')
            page.get_by_role('button',name='End Break / Return to Work').click();page.wait_for_load_state('networkidle')
        page.goto(base+'/exceptions/new/')
        for name,value in [('description','Browser-test airport delay'),('booking','0000742'),('next_action','Check revised arrival'),('deadline',(timezone.now()+timedelta(hours=1)).isoformat())]:page.locator(f'[name={name}]').fill(value)
        page.locator('[name=owner]').select_option(str(users['Noah'].pk));page.locator('[name=priority]').select_option('High');page.locator('[name=handoff]').check();save();assert Issue.objects.filter(booking='0000742').exists()
        page.goto(base+'/verification/new/')
        for name,value in [('subject','Browser-test affiliate'),('market','Denver'),('checks','Insurance and license checked')]:page.locator(f'[name={name}]').fill(value)
        page.locator('[name=kind]').select_option('Affiliate');page.locator('[name=research_status]').select_option('Research Complete');save();assert Verification.objects.count()==1
        page.goto(base+'/prospects/new/')
        for name,value in [('company','Browser-test hotel'),('contact','Test contact'),('email','contact@example.test'),('market','Hotels')]:page.locator(f'[name={name}]').fill(value)
        save();prospect=Prospect.objects.get(email='contact@example.test');assert Outreach.objects.count()==0
        page.goto(base+f'/prospects/{prospect.id}/send/');page.locator('[name=confirmation]').fill('Confirmed real send in test mailbox reference: test-message-1');page.locator('[name=sent]').check();save();assert Outreach.objects.count()==1
        page.goto(base+'/');page.screenshot(path=str(root/'dispatcher-desktop.png'),full_page=True)
        page.get_by_role('button',name='End Shift',exact=True).click();page.wait_for_load_state('networkidle');s=Shift.objects.get(employee=users['Noah']);assert s.end and s.breaks.count()==2
        page.goto(base+f'/shifts/{s.id}/summary/');page.locator('[name=comments]').fill('Browser closeout test');page.get_by_role('button',name='Submit Daily Summary').click();page.wait_for_load_state('networkidle');assert SummaryRevision.objects.filter(summary__shift=s).count()==1
        page.goto(base+f'/shifts/{s.id}/handoff/');page.locator('[name=recipient]').select_option(str(users['Umer'].pk));page.locator('[name=notes]').fill('Check the airport issue.');save();assert Handoff.objects.count()==1
        page.get_by_role('button',name='Sign out').click();sign_in('Umer');page.goto(base+'/handoffs/');page.get_by_role('button',name='Acknowledge Handoff').click();page.wait_for_load_state('networkidle');assert Handoff.objects.get().acknowledged_by==users['Umer']
        denied=page.request.get(base+f'/api/shifts/{s.id}/');assert denied.status==404
        page.get_by_role('button',name='Sign out').click();sign_in('Teddy')
        v=Verification.objects.get();page.goto(base+f'/verification/{v.id}/approve/');page.locator('[name=outcome]').select_option('Approved');page.locator('[name=notes]').fill('Evidence checked by management.');save();v.refresh_from_db();assert v.outcome=='Approved'
        page.goto(base+'/management/');page.wait_for_function("document.querySelector('#sync-status').textContent.includes('Synced')");page.screenshot(path=str(root/'management-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(root/'management-mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile document overflows'
        page.set_viewport_size({'width':1440,'height':1024})
        page.route('**/api/sync/',lambda route:route.abort());page.wait_for_timeout(16000);assert 'Connection failed' in page.locator('#sync-status').inner_text();page.unroute('**/api/sync/')
        print('Browser integration PASS: login/roles, shift, 2 breaks, exceptions, research, confirmed send, summary, handoff, acknowledgment, approval, mobile layout, synchronization failure.')
    else:
        page.goto(base+'/attendance/');assert 'Ended' in page.locator('main').inner_text();assert Shift.objects.filter(employee=users['Noah'],end__isnull=False).exists();assert SummaryRevision.objects.count()==1;assert Handoff.objects.get().acknowledged_at
        print('Browser restart persistence PASS: attendance, summary snapshot, and acknowledgment retained after application restart.')
    assert not errors,errors
    browser.close()
