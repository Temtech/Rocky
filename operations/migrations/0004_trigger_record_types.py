from django.db import migrations
from importlib import import_module
old=import_module('operations.migrations.0003_integrity_triggers').SQL
function=old[old.index('CREATE FUNCTION rocky_record_integrity'):old.index('CREATE TRIGGER shift_integrity')]
function=function.replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1)
function=function.replace("IF TG_TABLE_NAME='operations_outreach' AND EXISTS(SELECT 1 FROM operations_prospect WHERE id=NEW.prospect_id AND response='Do Not Contact') THEN RAISE EXCEPTION 'Do Not Contact'; END IF;", "IF TG_TABLE_NAME='operations_outreach' THEN\n   IF EXISTS(SELECT 1 FROM operations_prospect WHERE id=NEW.prospect_id AND response='Do Not Contact') THEN RAISE EXCEPTION 'Do Not Contact'; END IF;\n  END IF;")
class Migration(migrations.Migration):
    dependencies=[('operations','0003_integrity_triggers')]
    operations=[migrations.RunSQL(function,migrations.RunSQL.noop)]
