#!/usr/bin/env python3
"""Read-only final evidence audit; does not launch models or mutate Git."""
import json,pathlib,re,hashlib
import r3_runtime as r
b=r.OUT;manifest=json.loads((r.SOURCE/'.omx/ultragoal/evidence/source-repair-r3/manifest.json').read_text());assert all(r.digest(r.SOURCE/p)==h for p,h in manifest['suite_skill_metadata_sha256'].items())
old=json.loads((b/'prior-preservation.json').read_text())['files'];changed=[p for p,h in old.items() if r.digest(b.parent/p)!=h]
result={'source_freeze_match':True,'prior_artifacts_changed':changed,'installations':{},'cases':{},'model_sessions_after_stop':['question-setup','question-spec'],'additional_runs_authority':'Parent explicitly authorized at most two independent question regression sessions after negative FAIL; no positive/protocol/duplicate-negative runs'}
for mode in ['copy','symlink']:
 d=json.loads((b/('install-'+mode+'.json')).read_text());root=pathlib.Path(d['root']);result['installations'][mode]={'source_match':r.inventory(root/'.claude/skills')==d['source']==d['installed']==r.inventory(r.SOURCE/'skills'),'all_entries_symlinks':all(p.is_symlink() for p in (root/'.claude/skills').iterdir()),'skill_count':sum(p.endswith('SKILL.md') for p in d['source']),'metadata_count':sum(p.endswith('.yaml') for p in d['source']),'paths':d['paths']}
for p in b.glob('*.json'):
 d=json.loads(p.read_text())
 if not isinstance(d,dict) or 'events' not in d:continue
 root=pathlib.Path(d['root']);result['cases'][p.stem]={'turns':len(d['turns']),'timeout':d['timeout'],'models':d['models'],'max_turn_seconds':max(t['elapsed'] for t in d['turns']),'permission_denials':sum(len(t['permission_denials']) for t in d['turns']),'stdin_count':len(d['controlled_stdin']),'all_sanitized_JSON_events':len(d['all_sanitized_stream_events']),'installed_source_match':r.inventory(root/'.claude/skills')==r.inventory(r.SOURCE/'skills'),'host_ains_homonyms':d['input_contributor_state']['host_ains_homonyms'],'ancestor_rules':d['input_contributor_state']['ancestor_rules'],'fixture_has_commit':r.shell(['git','rev-parse','--verify','HEAD'],root)[0]==0,'current_artifacts':r.snapshot(root)}
r.save('audit',result)
print(json.dumps({'source_freeze':True,'prior_changed':changed,'cases':len(result['cases']),'timeouts':[n for n,v in result['cases'].items() if v['timeout']],'commits':[n for n,v in result['cases'].items() if v['fixture_has_commit']],'max_turn_seconds':max(v['max_turn_seconds'] for v in result['cases'].values())},ensure_ascii=False))
