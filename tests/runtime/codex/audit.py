#!/usr/bin/env python3
"""Summarize real event/artifact evidence; absence of reads never proves suppression."""
from runtime import *
W=pathlib.Path(json.loads((OUT/'run-state.json').read_text())['workspace'])
def items(record):
 for e in record.get('events',[]):
  if e.get('type')=='item.completed': yield e.get('item',{})
  elif e.get('method')=='item/completed': yield e.get('params',{}).get('item',{})
def reads(record):
 found=[]
 for i in items(record):
  if i.get('type') not in ['command_execution','commandExecution']:continue
  output=i.get('aggregated_output',i.get('aggregatedOutput','')) or ''
  cmd=i.get('command','')
  for s in (SOURCE/'skills').glob('*/SKILL.md'):
   if s.read_text() in output and s.parent.name+'/SKILL.md' in cmd:
    found.append({'name':s.parent.name,'source_body_sha256':digest(s),'command':cmd,'exit':i.get('exit_code',i.get('exitCode'))})
 return found
result={'observer':'Successful completed command read with installed skill path in command and entire frozen source SKILL.md body in output. Does not observe every possible injection path.','runs':{},'source_unchanged':True,'installs':{},'fixture_git':{},'ancestor_rules':[],'homonyms':{}}
for f in sorted(OUT.glob('*.json')):
 if f.name=='audit.json':continue
 d=json.loads(f.read_text())
 if not isinstance(d,dict) or 'events' not in d:continue
 changed=[k for k in set(d.get('before',{}))|set(d.get('after',{})) if d.get('before',{}).get(k)!=d.get('after',{}).get(k)]
 result['runs'][f.stem]={'exit':d.get('exit'),'completed':d.get('completed'),'timeout':d.get('timeout',False),'error':d.get('error'),'seconds':d.get('seconds'),'observed_full_body_reads':reads(d),'changed_files':changed}
for mode in ['symlink','copy']:
 inv=json.loads((OUT/('inventory-'+mode+'.json')).read_text());disc=json.loads((OUT/('discovery-'+mode+'.json')).read_text())
 for row in inv:
  p=SOURCE/'skills'/row['name']/'SKILL.md';meta=p.parent/'agents/openai.yaml'
  result['source_unchanged'] &= digest(p)==row['source_sha256'] and (digest(meta) if meta.exists() else None)==row['source_metadata_sha256']
 result['installs'][mode]={'count':len(inv),'discovered_count':len(disc),'names_equal':{x['name'] for x in inv}=={x['name'] for x in disc},'all_body_hashes_match':all(x['sha256']==x['source_sha256'] for x in inv),'all_metadata_hashes_match':all(x['metadata_sha256']==x['source_metadata_sha256'] for x in inv),'codex_entry_symlink_count':sum(x['entry_symlink'] for x in inv),'discovery_matches_installed_realpaths':all(pathlib.Path(x['path']).resolve()==pathlib.Path(next(y['path'] for y in inv if y['name']==x['name'])).resolve() for x in disc)}
for root in W.iterdir():
 if (root/'.git').exists():
  x=subprocess.run(['git','rev-parse','--verify','HEAD'],cwd=root,capture_output=True)
  result['fixture_git'][root.name]={'head_exists':x.returncode==0,'git_root_matches':pathlib.Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=root,text=True).strip()).resolve()==root.resolve()}
for a in set([W,*W.parents,W.resolve(),*W.resolve().parents]):
 for n in ['AGENTS.md','CLAUDE.md']:
  if (a/n).exists():result['ancestor_rules'].append(str(a/n))
for label,root in [('agents-global',pathlib.Path.home()/'.agents/skills'),('codex-global',pathlib.Path.home()/'.codex/skills'),('codex-plugin-cache',pathlib.Path.home()/'.codex/plugins/cache')]:
 count=0;hits=[]
 if root.exists():
  for p in root.rglob('SKILL.md'):
   count+=1
   try:
    text=p.read_text(errors='replace')[:12000];m=re.search(r'^name:\s*[\'"]?([a-zA-Z0-9_-]+)',text,re.M);name=m.group(1) if m else p.parent.name
    if name=='ains' or name.startswith('ains-'):hits.append({'name':name,'entry':str(p.relative_to(root))})
   except OSError:pass
 result['homonyms'][label]={'scanned':count,'ains_entries':hits}
# Installed source bodies and metadata only: moves of evals/docs are outside this freeze.
save('audit',result)
print(json.dumps({k:v for k,v in result.items() if k not in ['runs','fixture_git']},indent=2))
