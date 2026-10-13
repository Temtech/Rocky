from django.core.management.base import BaseCommand,CommandError
from operations.models import User
from operations.workbook import import_workbook
from operations.services import WorkflowError
class Command(BaseCommand):
    help='Import source workbook D01–D60 exactly once; descriptions, instructions and frequency preserved.'
    def add_arguments(self,p): p.add_argument('workbook');p.add_argument('--manager-email',required=True)
    def handle(self,*args,**opts):
        try:
            actor=User.objects.get(email=opts['manager_email'],role='management',is_active=True)
            count=import_workbook(opts['workbook'],actor)
        except (User.DoesNotExist,WorkflowError) as e: raise CommandError(str(e))
        self.stdout.write(f'{count} duties imported. 0 means an identical source was already imported.')
