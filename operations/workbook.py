import csv, hashlib, json
from pathlib import Path
from django.db import transaction
from .models import Duty,DutyVersion
from .services import audit,WorkflowError
HEADERS=['code','description','instructions','frequency']

def read_workbook(path):
    path=Path(path)
    if path.suffix.lower()=='.csv':
        with path.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.reader(f))
    else:
        from openpyxl import load_workbook
        wb=load_workbook(path,read_only=True,data_only=True)
        sheets=[list(s.values) for s in wb.worksheets]
        candidates=[s for s in sheets if s and all(h in [str(x or '').strip().lower() for x in s[0]] for h in HEADERS)]
        wb.close()
        if len(candidates)!=1: raise WorkflowError('Expected exactly one sheet with code, description, instructions and frequency headers. No source data has been changed.')
        rows=candidates[0]
    if not rows: raise WorkflowError('Workbook is empty.')
    headers=[str(x or '').strip().lower() for x in rows[0]]
    if not all(h in headers for h in HEADERS): raise WorkflowError('Required headers: code, description, instructions, frequency. Optional: section.')
    parsed=[]
    for row in rows[1:]:
        if not any(x is not None and str(x) for x in row): continue
        data={h:str(row[headers.index(h)] or '') for h in HEADERS}
        data['code']=data['code'].strip()
        if not data['description'].strip() or not data['frequency'].strip(): raise WorkflowError(f'{data["code"]}: description and original frequency are required.')
        data['section']=str(row[headers.index('section')] or '') if 'section' in headers else 'Active Dispatch'
        if data['section'] not in dict(DutyVersion._meta.get_field('section').choices): raise WorkflowError(f'{data["code"]}: unknown operational section.')
        parsed.append(data)
    expected={f'D{i:02}' for i in range(1,61)}
    if len(parsed)!=60 or {d['code'] for d in parsed}!=expected: raise WorkflowError('Reconciliation failed: expected D01–D60 exactly once, with no additional or duplicate rows.')
    return parsed

@transaction.atomic
def import_workbook(path,actor):
    from .models import User
    User.objects.select_for_update().get(pk=actor.pk)
    rows=read_workbook(path)
    digest=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
    present=Duty.objects.filter(code__in=[d['code'] for d in rows])
    if present.count()==60 and all(d.source_hash==digest for d in present): return 0
    if present.exists(): raise WorkflowError('Source duties already exist with different or incomplete provenance. Import refused; review the register instead of duplicating or overwriting duties.')
    for data in rows:
        values=data.copy(); code=values.pop('code')
        duty=Duty.objects.create(code=code,source_hash=digest,source=Path(path).name)
        v=DutyVersion.objects.create(duty=duty,author=actor,guidance_only=values['section']=='Active Dispatch',**values)
        audit(actor,'duty.source_imported',v)
    return 60
