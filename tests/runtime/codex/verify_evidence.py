#!/usr/bin/env python3
"""Checks the bounded claims made in REPORT.md against recorded actual evidence."""
from runtime import *
from audit import items
A=json.loads((OUT/'audit.json').read_text())
def load(n):return json.loads((OUT/(n+'.json')).read_text())
def events(n):return list(items(load(n)))
assert A['source_unchanged']
assert not A['ancestor_rules']
assert all(not x['ains_entries'] for x in A['homonyms'].values())
assert all(x['git_root_matches'] and (not x['head_exists'] or name=='ship repair consumer project') for name,x in A['fixture_git'].items())
for mode in ['symlink','copy']:
 x=A['installs'][mode];assert x['count']==x['discovered_count']==len(list((SOURCE/'skills').glob('*/SKILL.md'))) and all(x[k] for k in ['names_equal','all_body_hashes_match','all_metadata_hashes_match','discovery_matches_installed_realpaths'])
 for label,name in [('router','ains'),('spec','ains-spec'),('build','ains-build')]:
  r=A['runs'][mode+'-explicit-'+label];assert r['exit']==0 and not r['changed_files'];assert name in [x['name'] for x in r['observed_full_body_reads']]
for label in ['draft','missing','malformed']:
 r=A['runs']['negative-'+label];assert r['exit']==0 and not r['changed_files']
assert 'ains-tdd' in [x['name'] for x in A['runs']['automatic-tdd']['observed_full_body_reads']]
# Actual red command precedes production edit; green command follows it.
e=events('workflow-05-build')
red=next(i for i,x in enumerate(e) if x.get('type')=='commandExecution' and x.get('exitCode')==1 and '80 != 50' in (x.get('aggregatedOutput') or ''))
edit=next(i for i,x in enumerate(e) if x.get('type')=='fileChange' and any(y['path'].endswith('/calc.py') for y in x['changes']))
green=next(i for i,x in enumerate(e) if i>edit and x.get('type')=='commandExecution' and x.get('exitCode')==0 and 'Ran 3 tests' in (x.get('aggregatedOutput') or '') and '\nOK\n' in x['aggregatedOutput'])
assert red<edit<green
for label in ['01-spec-draft','02-spec-approval','03-tasks-draft','04-plan-approval','05-build','06-ship','07-scope-change']:
 r=load('workflow-'+label);assert r.get('completed')=='completed'
 if label in ['01-spec-draft','02-spec-approval','03-tasks-draft','04-plan-approval','07-scope-change']:
  assert r['before']['calc.py']==r['after']['calc.py'] and r['before']['tests/test_calc.py']==r['after']['tests/test_calc.py']
assert 'status: draft' in load('workflow-draft-artifact')['content']
for name in ['02-spec-approval','04-plan-approval']:
 assert load('workflow-'+name)['role']=='user' and 'SYNTHETIC FIXTURE USER-ROLE' in load('workflow-'+name)['input'][0]['text']
review=load('workflow-independent-review');assert review['exit']==0
review_thread=next(e['thread_id'] for e in review['events'] if e.get('type')=='thread.started')
assert review_thread!=load('workflow-session')['threadId']
ship=load('workflow-ship-artifacts');assert any(k.endswith('/pr.md') for k in ship)
scope=load('workflow-scope-change-artifacts');assert all(v.startswith('---\nstatus: draft\n') for k,v in scope.items() if k.endswith(('/spec.md','/tasks.md')))
for label in ['agents-only','claude-only','duplicate','existing-import']:
 r=load('setup-valid-'+label+'-artifacts');assert r['AGENTS.md']['content'].count('## Agent skills')==1;assert r['CLAUDE.md']['content'].count('@AGENTS.md')==1 and '## Agent skills' not in r['CLAUDE.md']['content']
assert not [x for x in A['runs']['setup-valid-conflict']['changed_files'] if '__pycache__' not in x]
assert not A['runs']['setup-valid-idempotence']['changed_files']
for label in ['samefile','symlink']:
 r=load('setup-valid-'+label+'-artifacts');assert r['AGENTS.md']['inode']==r['CLAUDE.md']['inode'];assert r['AGENTS.md']['content'].count('## Agent skills')==1 and '@AGENTS.md' not in r['AGENTS.md']['content']
assert load('setup-valid-symlink-artifacts')['CLAUDE.md']['symlink']
live=load('setup-live-final-artifacts');assert '## Agent skills' in live['AGENTS.md'] and '@AGENTS.md' in live['CLAUDE.md']
if (OUT/'ship-repair-final-gate.json').exists():
 gate=load('ship-repair-final-gate');assert gate['command']['exit']==0 and gate['head']==gate['baseline'] and not gate['remotes']
 assert any(k.endswith('/pr.md') for k in load('ship-repair-artifacts'))
 assert load('ship-repair-independent-review')['exit']==0
 repair_review=load('ship-repair-independent-review')
 repair_thread=next(e['thread_id'] for e in repair_review['events'] if e.get('type')=='thread.started')
 assert repair_thread!=load('ship-repair-session')['threadId']
 revents=events('ship-repair-05-build')
 red=next(i for i,x in enumerate(revents) if x.get('type')=='commandExecution' and x.get('exitCode')==1 and '80 != 50' in (x.get('aggregatedOutput') or ''))
 edit=next(i for i,x in enumerate(revents) if x.get('type')=='fileChange' and any(y['path'].endswith('/calc.py') for y in x['changes']))
 green=next(i for i,x in enumerate(revents) if i>edit and x.get('type')=='commandExecution' and x.get('exitCode')==0 and 'Ran 2 tests' in (x.get('aggregatedOutput') or ''))
 assert red<edit<green
 assert all(x['sha256']==x['source_sha256'] for x in load('ship-repair-install')['skills'])
 for mode in ['symlink','copy']:
  r=load(mode+'-router-valid');assert r['exit']==0 and r['before']==r['after']
  assert any('ains-build' in x.get('text','') for x in items(r) if x.get('type')=='agent_message')
result={'assertions':'pass','recorded_runtime_runs':len(A['runs']),'full_body_load_observer':'positive reads proven; complete injection/suppression observer unavailable','formal_support':'UNVERIFIED','ship_gate':('PASS: explicit fixture baseline' if (OUT/'ship-repair-final-gate.json').exists() and load('ship-repair-final-gate')['command']['exit']==0 else 'UNVERIFIED: no Git comparison base'),'setup_live_initial_discovery':'failed then recovered on subsequent real user turn','all_model_turns_within_180_seconds':all(r.get('seconds',0)<=180 for r in A['runs'].values())}
save('verification',result);print(json.dumps(result,indent=2))
