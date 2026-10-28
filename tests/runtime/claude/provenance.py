#!/usr/bin/env python3
import concurrent.futures,json,pathlib
import runtime as r
from suite import fixture,plan,SCOPE
bases=json.loads((r.OUT/'roots.json').read_text())
def check(pair):
 mode,base=pair;base=pathlib.Path(base)
 for skill in ['ains','ains-spec','ains-build']:
  root=fixture(base,'provenance-'+skill)
  if skill=='ains-build':plan(root)
  r.run('provenance-'+skill+'-'+mode,root,['/'+skill+' '+SCOPE+'First read .claude/skills/'+skill+'/SKILL.md to verify the installed procedure path; this explicit provenance read is part of the test. '+('Inspect state and recommend next stage without edits.' if skill=='ains' else 'Read relevant state and describe the next checkpoint. Do not approve, implement, or edit files.')])
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(check,bases.items()))
