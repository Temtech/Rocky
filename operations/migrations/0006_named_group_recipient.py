from django.db import migrations
class Migration(migrations.Migration):
    dependencies=[('operations','0005_alter_dutyassignment_group_dutygroup_and_more')]
    operations=[migrations.RunSQL('''ALTER TABLE operations_dutyassignment DROP CONSTRAINT assignment_recipient;
ALTER TABLE operations_dutyassignment ADD CONSTRAINT assignment_recipient CHECK (((employee_id IS NOT NULL)::int+("group"='dispatchers')::int+(team_id IS NOT NULL)::int)=1 AND "group" IN ('','dispatchers'));''',migrations.RunSQL.noop)]
