from django.db import migrations
class Migration(migrations.Migration):
    dependencies=[('operations','0006_named_group_recipient')]
    operations=[migrations.RunSQL('CREATE UNIQUE INDEX rocky_user_email_lower ON operations_user(lower(email)); CREATE UNIQUE INDEX rocky_prospect_email_lower ON operations_prospect(lower(email));','DROP INDEX rocky_user_email_lower; DROP INDEX rocky_prospect_email_lower;')]
