"""Browser checks for first-login change, failed form preservation and privacy."""
import os,sys,secrets
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','rocky.settings')
import django
django.setup()
from operations.models import User
from playwright.sync_api import sync_playwright
if not os.environ.get('DATABASE_URL','').endswith('/rocky_e2e'):raise RuntimeError('Test database only.')
password=secrets.token_urlsafe(24);new_password=secrets.token_urlsafe(24)
u=User.objects.get(email='noah@example.test');u.set_password(password);u.must_change_password=True;u.save()
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':390,'height':844});base='http://127.0.0.1:8001'
    page.goto(base+'/login/');page.locator('[name=username]').fill(u.email);page.locator('[name=password]').fill(password);page.get_by_role('button',name='Sign in').click();page.wait_for_url(base+'/account/password/')
    assert page.request.get(base+'/api/sync/').status==403
    page.locator('[name=old_password]').fill(password);page.locator('[name=new_password1]').fill(new_password);page.locator('[name=new_password2]').fill(new_password);page.get_by_role('button',name='Save new password').click();page.wait_for_url(base+'/account/')
    page.goto(base+'/exceptions/new/');page.locator('[name=description]').fill('Keep this unsaved issue after failure')
    page.locator('[name=next_action]').fill('Preserve this next action')
    page.locator('[name=deadline]').fill('2099-01-01T12:00:00-07:00');page.locator('[name=owner]').select_option(str(u.pk))
    page.route('**/exceptions/new/',lambda route: route.abort() if route.request.method=='POST' else route.continue_())
    page.get_by_role('button',name='Save to backend').click();page.wait_for_function("document.querySelector('#action-feedback')?.textContent.length > 0")
    assert page.locator('[name=description]').input_value()=='Keep this unsaved issue after failure'
    assert page.locator('[name=next_action]').input_value()=='Preserve this next action'
    assert not page.get_by_role('button',name='Save to backend').is_disabled()
    assert page.get_by_role('button',name='Sign out').is_visible()
    page.unroute('**/exceptions/new/')
    page.get_by_role('button',name='Sign out').click();page.wait_for_url(base+'/login/')
    browser.close()
print('Browser security PASS: mandatory initial password change, API lockout, successful password change, failed-submit field preservation and mobile sign-out.')
