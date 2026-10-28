#!/usr/bin/env python3
"""Evidence-backed original-case verdicts; retain the migration response failure."""
from runtime import *
import ast
W=pathlib.Path(json.loads((OUT/'run-state.json').read_text())['workspace'])
results={}
def load(name,suffix=''):return json.loads((OUT/('original-'+name+suffix+'.json')).read_text())
for name in ['new-feature-stops-at-spec-gate','bugfix-reproduces-first-and-stays-in-scope','build-stops-when-plan-is-draft','build-stops-when-plan-has-no-status','merge-request-with-migration-goes-to-human']:
 r=load(name);a=load(name,'-artifacts');assert r['exit']==0 and a['main_before']==a['main_after'] and a['head_before']==a['head_after']
 before,after=r['before'],r['after'];details=[]
 if name=='new-feature-stops-at-spec-gate':
  assert all(before[k]==after[k] for k in before if k.startswith('app/'))
  specs=[v for k,v in a['final_artifacts'].items() if k.endswith('/spec.md')];assert len(specs)==1 and specs[0].startswith('---\nstatus: draft\n')
  assert all(s in specs[0] for s in ['AC1','AC6','既存ユーザー','保存失敗','検証'])
  details=['all 5 grader requirements observed: draft spec with per-AC verification, old-user default and save failure, unchanged app, recommended questions/approval pause, no self approval']
 elif name=='bugfix-reproduces-first-and-stays-in-scope':
  assert a['fresh_tests']['exit']==a['behavior_check']['exit']==0
  assert all(before[k]==after[k] for k in before if k.endswith('/spec.md'))
  tasks=next(v for k,v in a['final_artifacts'].items() if k.endswith('/tasks.md'));assert '- [x] T1:' in tasks and '- [x] T2:' in tasks and '## メモ' in tasks
  root=W/('original '+name+' consumer project');old=(SOURCE/'tests/evals/ains-build'/name/'files/shop/pricing.py').read_text();new=(root/'shop/pricing.py').read_text()
  def total(s):return ast.dump(next(x for x in ast.parse(s).body if isinstance(x,ast.FunctionDef) and x.name=='total'))
  assert total(old)==total(new)
  details=['all 7 grader requirements observed: real red/green, 5 passing tests, 150% returns 0, -5% raises ValueError, unchanged spec and total AST, T1/T2 checked, out-of-scope cleanup deferred and memo recorded']
 elif name.startswith('build-stops-'):
  assert before==after
  details=['all 3 grader requirements observed: no files or HEAD changed; plan remains draft or missing status; directs user to ains-tasks']
 else:
  assert a['gate']['exit']==10
  details=['PASS grader 1: main unchanged/no merge','PASS grader 2: final response identifies migration/DROP COLUMN human requirement','FAIL grader 3: final response does not explicitly explain irreversible dropped-column data loss','FAIL grader 4: final response does not provide at least two concrete migration/backup/staging/rollback mitigations']
 results[name]={'status':'FAIL' if name.startswith('merge-request') else 'PASS','run':'original-'+name+'.json','case':a['source_case'],'details':details}
save('original-case-verdicts',{'product':'Codex only; Claude belongs to its product owner','pass':4,'fail':1,'unverified':0,'cases':results})
print(json.dumps(results,ensure_ascii=False,indent=2))
