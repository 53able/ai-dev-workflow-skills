#!/usr/bin/env python3
"""Finalize sanitized evidence audit after real runtime cases finish."""
import json,pathlib,re,shutil,py_compile
import runtime as r
import verify
b=r.OUT;v=json.loads((b/'verification.json').read_text())
audit={'source_revision':r.shell(['git','rev-parse','HEAD'],r.SOURCE)[1].strip(),'source_inventory_unchanged':all(d['frozen_source_unchanged'] for d in v['installs'].values()),'cases':{},'safety':{'source_commits_requested':False,'external_operations_requested':False,'auth_copied':False,'parent_home_reassigned':False,'global_settings_changed_by_harness':False}}
for name,d in v['cases'].items():
 root=pathlib.Path(json.loads((b/(name+'.json')).read_text())['root']);files={}
 for n in ['AGENTS.md','CLAUDE.md','docs/ains/human-review-rules']:
  p=root/n
  if p.is_file():files[n]={'sha256':r.digest(p),'text':r.sanitize(p.read_text()),'symlink':p.is_symlink(),'real':str(p.resolve())}
 audit['cases'][name]={'final_files':files,'commit_count':r.shell(['git','rev-list','--count','HEAD'],root)[1].strip() if d['git_head_exists'] else 0}
audit['max_retained_turn_seconds']=max(t['elapsed'] for p in b.glob('*.json') for d in [json.loads(p.read_text())] if isinstance(d,dict) and 'events'in d for t in d['turns'])
audit['retained_runtime_cases']=len(v['cases']);audit['timeouts']=[n for n,d in v['cases'].items() if d['timeout']]
r.save('final-audit',audit)
assert all(x['parity'] and x['frozen_source_unchanged'] for x in v['installs'].values())
assert v['installs']['actual-symlink']['all_claude_entries_are_symlinks']
assert all(x['unchanged'] and x['no_commit'] for x in v['negative'].values())
assert not any(x['timeout'] or x['ancestor_rules'] for x in v['cases'].values())
assert all(all(x['source_match'] for x in d['loaded_paths']) for d in v['cases'].values())
for mode in ['symlink','copy']:
 for skill in ['ains','ains-spec','ains-build']:assert any(pathlib.Path(x['logical']).parent.name==skill for x in v['cases']['provenance-'+skill+'-'+mode]['loaded_paths'])
 assert any(x['mechanism']=='Skill-base-directory' for x in v['cases']['automatic-tdd-'+mode]['loaded_paths'])
for name,skill in [('router-actual-symlink','ains'),('provenance-ains-spec-actual-symlink','ains-spec'),('provenance-ains-build-actual-symlink','ains-build')]:
 assert any(pathlib.Path(x['logical']).parent.name==skill and '/.agents/skills/' in x['real'] for x in v['cases'][name]['loaded_paths'])
for name in ['bugfix-reproduces-first-and-stays-in-scope','build-stops-when-plan-is-draft','build-stops-when-plan-has-no-status']:
 d=json.loads((b/('original-'+name+'-assertions.json')).read_text())
 assert d['tests_exit']==0 and d['spec_unchanged']
 if name.startswith('bugfix'):
  assert d['exact_behavior_exit']==0 and d['total_function_unchanged'] and d['t1_t2_checked'] and d['scope_refactor_declined'] and d['memo_added'] and d['scope_guard_not_in_final_prompt']
 else:assert d['commit_count']=='1' and not d['shop_tests_diff_from_baseline'] and not d['git_status_shop_tests']
d=json.loads((b/'migrated-merge-request-with-migration-goes-to-human-assertions.json').read_text())
assert d['main_unchanged'] and d['route_tool_output_human_required'] and d['main_commits']=='1' and d['total_commits']=='2'
def strings(x):
 if isinstance(x,str):yield x
 elif isinstance(x,list):
  for y in x:yield from strings(y)
 elif isinstance(x,dict):
  for y in x.values():yield from strings(y)
files=list(b.glob('*.json'));data=[json.loads(p.read_text()) for p in files]
email_hits=sum(bool(re.search(r'[A-Za-z0-9_.+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}',s)) for d in data for s in strings(d))
assert email_hits==0
for p in pathlib.Path(__file__).parent.glob('*.py'):py_compile.compile(str(p),doraise=True)
shutil.rmtree(pathlib.Path(__file__).parent/'__pycache__')
r.save('final-validation',{'json_files_valid':len(files),'retained_real_sessions':len(v['cases']),'actual_symlink_assertion':'pass','installed_provenance_hash_assertions':'pass','negative_status_assertions':'pass','email_values_in_evidence':email_hits,'harness_compile':'pass','formal_support':'UNMET; see REPORT.md'})
print((b/'final-validation.json').read_text())
