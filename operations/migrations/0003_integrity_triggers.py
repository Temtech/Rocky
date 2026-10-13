from django.db import migrations
SQL=r'''
ALTER TABLE operations_dutyassignment ADD CONSTRAINT assignment_recipient CHECK ((employee_id IS NOT NULL AND "group"='') OR (employee_id IS NULL AND "group"='dispatchers'));
ALTER TABLE operations_dutyassignment ADD CONSTRAINT assignment_dates CHECK (effective_end IS NULL OR effective_end>=effective_start);
CREATE FUNCTION rocky_record_integrity() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s operations_shift; role_name text;
BEGIN
 IF TG_TABLE_NAME='operations_shift' THEN
  IF NEW.schedule_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM operations_schedule WHERE id=NEW.schedule_id AND employee_id=NEW.employee_id) THEN RAISE EXCEPTION 'Schedule belongs to a different employee'; END IF;
  IF TG_OP='UPDATE' THEN
   IF NEW.original_start IS DISTINCT FROM OLD.original_start OR (OLD.original_end IS NOT NULL AND NEW.original_end IS DISTINCT FROM OLD.original_end) THEN RAISE EXCEPTION 'Original timestamps are immutable'; END IF;
  END IF;
  IF NEW."end" IS NOT NULL AND EXISTS(SELECT 1 FROM operations_break WHERE shift_id=NEW.id AND ("end" IS NULL OR "end">NEW."end" OR start<NEW.start)) THEN RAISE EXCEPTION 'Close breaks before shift end and preserve break boundaries'; END IF;
 ELSIF TG_TABLE_NAME='operations_break' THEN
  SELECT * INTO s FROM operations_shift WHERE id=NEW.shift_id FOR UPDATE;
  IF s.employee_id!=NEW.employee_id OR NEW.start<s.start OR (s."end" IS NOT NULL AND (NEW."end" IS NULL OR NEW."end">s."end")) THEN RAISE EXCEPTION 'Break employee or timestamp is outside its shift'; END IF;
  IF EXISTS(SELECT 1 FROM operations_break b WHERE b.shift_id=NEW.shift_id AND b.id!=NEW.id AND tstzrange(b.start,b."end",'[)') && tstzrange(NEW.start,NEW."end",'[)')) THEN RAISE EXCEPTION 'Breaks cannot overlap'; END IF;
 ELSIF TG_TABLE_NAME IN ('operations_verification','operations_prospect','operations_outreach') THEN
  SELECT * INTO s FROM operations_shift WHERE id=NEW.shift_id;
  IF s.employee_id!=NEW.employee_id THEN RAISE EXCEPTION 'Employee must own originating shift'; END IF;
  IF TG_TABLE_NAME='operations_outreach' AND EXISTS(SELECT 1 FROM operations_prospect WHERE id=NEW.prospect_id AND response='Do Not Contact') THEN RAISE EXCEPTION 'Do Not Contact'; END IF;
 ELSIF TG_TABLE_NAME='operations_handoff' THEN
  SELECT * INTO s FROM operations_shift WHERE id=NEW.shift_id;
  IF NEW.sender_id!=s.employee_id THEN RAISE EXCEPTION 'Sender must own shift'; END IF;
  IF NEW.acknowledged_by_id IS NOT NULL AND NEW.acknowledged_by_id!=NEW.recipient_id THEN RAISE EXCEPTION 'Only recipient may acknowledge'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER shift_integrity BEFORE INSERT OR UPDATE ON operations_shift FOR EACH ROW EXECUTE FUNCTION rocky_record_integrity();
CREATE TRIGGER break_integrity BEFORE INSERT OR UPDATE ON operations_break FOR EACH ROW EXECUTE FUNCTION rocky_record_integrity();
CREATE TRIGGER verification_integrity BEFORE INSERT OR UPDATE ON operations_verification FOR EACH ROW EXECUTE FUNCTION rocky_record_integrity();
CREATE TRIGGER prospect_integrity BEFORE INSERT OR UPDATE ON operations_prospect FOR EACH ROW EXECUTE FUNCTION rocky_record_integrity();
CREATE TRIGGER outreach_integrity BEFORE INSERT OR UPDATE ON operations_outreach FOR EACH ROW EXECUTE FUNCTION rocky_record_integrity();
CREATE TRIGGER handoff_integrity BEFORE INSERT OR UPDATE ON operations_handoff FOR EACH ROW EXECUTE FUNCTION rocky_record_integrity();
CREATE FUNCTION rocky_append_only() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Historical records are append-only'; END $$;
CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON operations_audit FOR EACH ROW EXECUTE FUNCTION rocky_append_only();
CREATE TRIGGER shift_events_immutable BEFORE UPDATE OR DELETE ON operations_shiftevent FOR EACH ROW EXECUTE FUNCTION rocky_append_only();
CREATE TRIGGER duty_versions_immutable BEFORE UPDATE OR DELETE ON operations_dutyversion FOR EACH ROW EXECUTE FUNCTION rocky_append_only();
CREATE TRIGGER summaries_immutable BEFORE UPDATE OR DELETE ON operations_summaryrevision FOR EACH ROW EXECUTE FUNCTION rocky_append_only();
CREATE TRIGGER corrections_immutable BEFORE UPDATE OR DELETE ON operations_correction FOR EACH ROW EXECUTE FUNCTION rocky_append_only();
CREATE TRIGGER outreach_immutable BEFORE UPDATE OR DELETE ON operations_outreach FOR EACH ROW EXECUTE FUNCTION rocky_append_only();
'''
REVERSE='''
DROP FUNCTION rocky_append_only() CASCADE;
DROP FUNCTION rocky_record_integrity() CASCADE;
ALTER TABLE operations_dutyassignment DROP CONSTRAINT assignment_recipient;
ALTER TABLE operations_dutyassignment DROP CONSTRAINT assignment_dates;
'''
class Migration(migrations.Migration):
    dependencies=[('operations','0002_user_must_change_password')]
    operations=[migrations.RunSQL(SQL,REVERSE)]
