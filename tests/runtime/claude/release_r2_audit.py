#!/usr/bin/env python3
import json,pathlib,re,hashlib,ast
import r2_runtime as r
b=r.OUT
manifest=json.loads((r.SOURCE/'.omx/ultragoal/evidence/source-repair-r2/source-sha256.json').read_text());assert all(r.digest(r.SOURCE/p)==h for p,h in manifest.items())
preserved=json.loads((b/'r1-preservation.json').read_text())['files'];changed=[p for p,h in preserved.items() if r.digest(b.parent/p)!=h]
result={'source_freeze_matches':True,'r1_artifact_changes':changed,'installations':{},'cases':{},'global_rule_and_auto_memory_postrun_hash_audit':[]}
for mode in ['copy','symlink']:
 d=json.loads((b/('install-'+mode+'.json')).read_text());root=pathlib.Path(d['root']);inv=r.inventory(root/'.claude/skills')
 result['installations'][mode]={'source_match':inv==d['source']==r.inventory(r.SOURCE/'skills'),'all_claude_entries_symlinks':all(p.is_symlink() for p in (root/'.claude/skills').iterdir()),'skill_count':sum(k.endswith('SKILL.md') for k in inv),'metadata_count':sum(k.endswith('.yaml') for k in inv),'paths':d['paths']}
for p in b.glob('*.json'):
 d=json.loads(p.read_text())
 if not isinstance(d,dict) or 'events' not in d:continue
 root=pathlib.Path(d['root']);loads=[];toolmap={e['id']:e for e in d['events'] if e['event']=='tool_use'}
 for e in d['events']:
  if e['event']=='tool_use' and e['name']=='Read':
   path=pathlib.Path(e['input'].get('file_path',''))
   if path.name=='SKILL.md' and path.exists():loads.append({'mechanism':'Read','logical':str(path),'real':str(path.resolve()),'sha256':r.digest(path),'source_match':r.digest(path)==r.digest(r.SOURCE/'skills'/path.parent.name/'SKILL.md'),'tool_use_id':e['id']})
  if e['event']=='text' and e.get('text','').startswith('Base directory for this skill: '):
   path=pathlib.Path(e['text'].split('\n')[0].split(': ',1)[1])/'SKILL.md'
   if path.exists():
    injected=e['text'].split('\n',1)[1].strip();expected=path.read_text().split('---',2)[-1].strip()
    loads.append({'mechanism':'Skill-body-injection','logical':str(path),'real':str(path.resolve()),'sha256':r.digest(path),'source_match':r.digest(path)==r.digest(r.SOURCE/'skills'/path.parent.name/'SKILL.md'),'injected_body_matches_source_after_frontmatter':injected==expected,'injected_body_sha256':hashlib.sha256(injected.encode()).hexdigest()})
 full=d['all_sanitized_stream_events'];markers=[]
 for x in full:
  c=x.get('message',{}).get('content') if isinstance(x.get('message'),dict) else None
  if x.get('type')=='user' and isinstance(c,str):markers+=re.findall(r'<command-name>([^<]+)</command-name>',c)
 auto_paths=[]
 for x in full:
  if x.get('type')=='system' and x.get('subtype')=='init':auto_paths+=list(x.get('memory_paths',{}).values())
 for path in sorted(set(auto_paths)):
  path=pathlib.Path(path)
  result['global_rule_and_auto_memory_postrun_hash_audit'].append({'case':p.stem,'path':str(path),'exists_postrun':path.exists(),'files_sha256_postrun':{str(f.relative_to(path)):r.digest(f) for f in path.rglob('*.md') if f.is_file()} if path.exists() else {}})
 result['cases'][p.stem]={'turns':len(d['turns']),'models':d['models'],'timeout':d['timeout'],'max_turn_seconds':max((t['elapsed'] for t in d['turns']),default=0),'model_errors':sum(bool(t['is_error']) for t in d['turns']),'permission_denials':sum(len(t['permission_denials']) for t in d['turns']),'stdin_events':len(d['controlled_stdin']),'all_sanitized_event_count':len(full),'slash_expansion_command_markers':markers,'actual_loads':loads,'installed_source_match':r.inventory(root/'.claude/skills')==r.inventory(r.SOURCE/'skills') if (root/'.claude/skills').exists() else None,'host_ains_homonyms':d['input_contributor_state']['host_ains_homonyms'],'ancestor_rules':d['input_contributor_state']['ancestor_rules'],'effective_prompt_complete':False}
for p in [pathlib.Path.home()/'.claude/CLAUDE.md',pathlib.Path.home()/'CLAUDE.md',pathlib.Path('/Library/Application Support/ClaudeCode/CLAUDE.md')]:
 result['global_rule_and_auto_memory_postrun_hash_audit'].append({'path':str(p),'exists_postrun':p.is_file(),'sha256_postrun':r.digest(p) if p.is_file() else None,'contents_logged':False})
# Independent Git proof for the actual AC9 commit/revert/restore sequence.
if (b/'workflow-harness-checks.json').exists():
 d=json.loads((b/'workflow-harness-checks.json').read_text());root=pathlib.Path(d['root']);commits=r.shell(['git','rev-list','--reverse','HEAD'],root)[1].splitlines();messages=r.shell(['git','log','--reverse','--format=%s'],root)[1].splitlines()
 result['AC9_git_audit']={'commit_ids':commits,'messages':messages,'exact_four_commits':len(commits)==4,'spec_unchanged':d['spec_unchanged'],'final_tests_exit':d['final_test_exit']}
 if len(commits)==4:
  result['AC9_git_audit'].update(reverted_tree_matches_baseline=not r.shell(['git','diff',commits[0],commits[2],'--','shop','tests'],root)[1],restored_tree_matches_implementation=not r.shell(['git','diff',commits[1],commits[3],'--','shop','tests'],root)[1],implementation_paths=r.shell(['git','diff-tree','--no-commit-id','--name-only','-r',commits[1]],root)[1].splitlines(),revert_commit_body=r.shell(['git','show','-s','--format=%B',commits[2]],root)[1],restore_commit_body=r.shell(['git','show','-s','--format=%B',commits[3]],root)[1])
r.save('audit',r.clean_tree(result))
print(json.dumps({'r1_artifact_changes':changed,'installations':{k:{x:y for x,y in v.items() if x!='paths'} for k,v in result['installations'].items()},'cases':len(result['cases']),'timeouts':[k for k,v in result['cases'].items() if v['timeout']],'AC9':result.get('AC9_git_audit')},ensure_ascii=False,indent=2))
