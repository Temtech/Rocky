import getpass
from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from operations.models import User
from operations.services import audit
class Command(BaseCommand):
    help='Create one initial named employee with an operator-chosen password. No default passwords. Repeat for Noah, Umer, Teddy and Betty using their real emails.'
    def add_arguments(self,p):
        p.add_argument('--name',required=True);p.add_argument('--email',required=True);p.add_argument('--role',choices=['dispatcher','management'],required=True)
    def handle(self,*a,**o):
        from django.core.validators import validate_email
        try: validate_email(o['email'])
        except ValidationError: raise CommandError('Valid email required.')
        if User.objects.filter(email__iexact=o['email']).exists(): raise CommandError('Account already exists. Use the management dashboard.')
        u=User(username=o['email'].lower(),email=o['email'].lower(),first_name=o['name'],role=o['role'])
        password=getpass.getpass('Choose a secure password (hidden): ')
        if password!=getpass.getpass('Confirm password (hidden): '): raise CommandError('Passwords do not match.')
        try: validate_password(password,u)
        except ValidationError as e: raise CommandError('; '.join(e.messages))
        u.set_password(password);u.save();audit(None,'account.bootstrapped',u)
        self.stdout.write(f'Created {u} ({u.role}). Password has not been printed or logged.')
