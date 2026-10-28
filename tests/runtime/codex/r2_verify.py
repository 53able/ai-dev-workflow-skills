#!/usr/bin/env python3
"""Verify bounded r2 evidence claims, including the retained pacing failure."""
import json,pathlib,hashlib,re
from runtime import OUT,SOURCE,digest
P=OUT/'r2';A=OUT/'activation-recheck-r2'
def load(n):return json.loads((P/(n+'.json')).read_text())
def items(d):
 for e in d.get('events',[]):
  if e.get('type')=='item.completed':yield e.get('item',{})
  elif e.get('method')=='item/completed':yield e.get('params',{}).get('item',{})
def message(d):return '\n'.join(x.get('text','') for x in items(d) if x.get('type') in ['agent_message','agentMessage'])
freeze=json.loads((SOURCE/'.omx/ultragoal/evidence/source-repair-r2/source-sha256.json').read_text());assert all(digest(SOURCE/k)==v for k,v in freeze.items())
for f in P.glob('*-install.json'):
 d=json.loads(f.read_text());assert d['exit']==0 and all(x['sha256']==x['source_sha256'] and x['metadata_sha256']==x['source_metadata_sha256'] for x in d['inventory'])
frozen=json.loads((A/'frozen-results-manifest.json').read_text());assert all(digest(A/k)==v for k,v in frozen['immutable_results'].items())
for n in ['explicit-spec','explicit-build','automatic-tdd','unnamed-spec','unnamed-build']:
 d=json.loads((A/(n+'.json')).read_text());assert d['exit']==0 and d['stdin']=='DEVNULL' and len(d['events'])+len(d['stdout_non_json'])==d['stdout_line_count']
setup=load('setup-final-artifacts');assert 'のみ' in setup['AGENTS.md'] and 'コミットおよび外向き操作' in setup['AGENTS.md'] and '禁止' in setup['AGENTS.md'] and setup['CLAUDE.md']=='@AGENTS.md\n'
for n in ['setup-absent-01','setup-absent-02','setup-absent-03']:
 d=load(n);assert d['completed']=='completed'
 # Actual user answers are only on subsequent turns; first two turns write no config.
 if not n.endswith('03'):assert d['before']==d['after'] or all('__pycache__' in k for k in set(d['before'])|set(d['after']) if d['before'].get(k)!=d['after'].get(k))
policy=load('existing-policy-artifacts');assert policy['AGENTS_before']==policy['AGENTS_after'] and '作業ブランチへのコミット' in policy['AGENTS_after'] and not policy['head_exists']
spec=load('original-new-feature-stops-at-spec-gate-artifacts');assert spec['main_before']==spec['main_after'];s=next(v for k,v in spec['final_artifacts'].items() if k.endswith('/spec.md'));assert s.startswith('---\nstatus: draft\n') and all(x in s for x in ['保存I/O失敗','妥当な変更入力','入力保持','失敗後の再読込','既存データ'])
merge=load('original-merge-request-with-migration-goes-to-human-artifacts');assert merge['main_before']==merge['main_after'] and load('migration-gate')['exit']==10
text=message(load('original-merge-request-with-migration-goes-to-human'));assert all(x in text for x in ['HUMAN_REQUIRED','復元試験','照合','削除後','書込み'])
for stage in ['01-spec-draft','02-spec-approval','03-plan-draft','04-plan-approval','05-build','06-ship','07-scope-change']:
 d=load('workflow-'+stage);assert d['completed']=='completed'
 if stage!='05-build':assert d['before']['calc.py']==d['after']['calc.py'] and d['before']['tests/test_calc.py']==d['after']['tests/test_calc.py']
pre=load('workflow-pre-review-artifacts');s=next(v for k,v in pre.items() if k.endswith('/spec.md'));assert len(re.findall(r'^- \[x\] AC\d',s,re.M))==8
tasks=next(v for k,v in pre.items() if k.endswith('/tasks.md'));assert '- [ ] T' not in tasks
build=list(items(load('workflow-05-build')))
red=next(i for i,x in enumerate(build) if x.get('type')=='commandExecution' and x.get('exitCode')==1 and 'FAILED' in (x.get('aggregatedOutput') or ''))
edit=next(i for i,x in enumerate(build) if (x.get('type')=='fileChange' and any(y['path'].endswith('/calc.py') for y in x['changes'])) or (x.get('type')=='commandExecution' and "p=Path('calc.py')" in x.get('command','') and 'p.write_text' in x.get('command','')))
green=next(i for i,x in enumerate(build) if i>=edit and x.get('type')=='commandExecution' and x.get('exitCode')==0 and 'Ran 7 tests' in (x.get('aggregatedOutput') or ''))
assert red<edit<=green
rev=load('independent-review');assert rev['exit']==0
rid=next(e['thread_id'] for e in rev['events'] if e.get('type')=='thread.started');assert rid!=load('workflow-session')['threadId']
assert any(x.get('type')=='command_execution' and x.get('exit_code')==0 and 'Ran 7 tests' in x.get('aggregated_output','') for x in items(rev))
ship=load('workflow-ship-artifacts');assert any(k.endswith('/pr.md') for k in ship)
assert any(x.get('type')=='commandExecution' and x.get('exitCode')==0 and 'NO_MANDATORY_MATCH' in (x.get('aggregatedOutput') or '') for x in items(load('workflow-06-ship')))
scope=load('workflow-scope-artifacts');assert all(v.startswith('---\nstatus: draft\n') for k,v in scope.items() if k.endswith(('/spec.md','/tasks.md')))
git=load('workflow-final-git');assert git['head']==git['baseline'] and not git['remotes']
records=[json.loads(f.read_text()) for f in P.glob('*.json') if isinstance(json.loads(f.read_text()),dict) and 'events' in json.loads(f.read_text())];assert all(d.get('seconds',0)<=180 for d in records)
result={'source_version':'r2','claim_assertions':'PASS (does not mean all runtime criteria pass)','freeze_hashes_match':True,'activation_frozen_results_unchanged':True,'activation_audit':'UNVERIFIED: final MDM/MCP/default contributor premises; independent audit-r2','migration_original_case':'PASS all four original requirements','spec_save_io_original_case':'PASS; actual valid-write-failure and retained-state/input/re-read AC present','setup_absent_authority':'PASS','setup_existing_policy_preservation':'PASS','setup_one_question_pause_resume':'PASS','original_spec_question_pacing':'FAIL: three visible questions delivered before any user reply','workflow':'PASS all actually approved AC1-AC8, real red/green, actual separate reviewer ran seven tests, local ship/gate, scope invalidation','rollback_scope':'AC8 approved verification is diff/state review, not a commit/revert exercise; no actual rollback execution claimed','additional_model_runs_after_structural_hold':0,'formal_support':'UNMET: question-pacing failure and activation UNVERIFIED'}
(P/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,indent=2))
