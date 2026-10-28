#!/usr/bin/env python3
"""Mechanical audit of real captured cases, not a model-output simulator."""
import hashlib,json,pathlib,re
import runtime as r
b=r.OUT;report={'source_now':r.inventory(r.SOURCE/'skills'),'installs':{},'cases':{},'setup':{},'negative':{}}
for mode in ['symlink','copy','actual-symlink']:
 if not (b/('install-'+mode+'.json')).exists():continue
 d=json.loads((b/('install-'+mode+'.json')).read_text());report['installs'][mode]={'parity':d['parity'],'frozen_source_unchanged':d['source']==report['source_now'],'source_skill_count':sum(x.endswith('SKILL.md') for x in d['source']),'metadata_count':sum(x.endswith('.yaml') for x in d['source']),'all_claude_entries_are_symlinks':all(p.is_symlink() for p in (pathlib.Path(d['root'])/'.claude/skills').iterdir())}
for p in sorted(b.glob('*.json')):
 d=json.loads(p.read_text())
 if not isinstance(d,dict) or 'events' not in d:continue
 root=pathlib.Path(d['root']);loads=[]
 for e in d['events']:
  if e['event']=='tool_use' and e['name']=='Read':
   path=pathlib.Path(e['input'].get('file_path',''))
   if path.name=='SKILL.md' and path.is_file():loads.append({'mechanism':'Read','logical':str(path),'real':str(path.resolve()),'sha256':r.digest(path),'source_match':r.digest(path)==r.digest(r.SOURCE/'skills'/path.parent.name/'SKILL.md')})
  if e['event']=='text' and e.get('text','').startswith('Base directory for this skill: '):
   path=pathlib.Path(e['text'].split('\n')[0].split(': ',1)[1])/'SKILL.md'
   if path.is_file():loads.append({'mechanism':'Skill-base-directory','logical':str(path),'real':str(path.resolve()),'sha256':r.digest(path),'source_match':r.digest(path)==r.digest(r.SOURCE/'skills'/path.parent.name/'SKILL.md')})
 report['cases'][p.stem]={'turns':len(d['turns']),'timeout':d['timeout'],'model':d['models'],'exit':d['exit'],'permission_denials':sum(len(t['permission_denials']) for t in d['turns']),'loaded_paths':loads,'inventory_parity':r.inventory(root/'.claude/skills')==report['source_now'] if (root/'.claude/skills').exists() else None,'ancestor_rules':[str(a/n) for a in root.parents for n in ['AGENTS.md','CLAUDE.md'] if (a/n).exists()],'git_head_exists':r.shell(['git','rev-parse','--verify','HEAD'],root)[0]==0}
 if p.stem.startswith('setup-') and not p.stem.endswith(('artifacts','checkpoints')):
  last=d['turns'][-1]['artifacts'] if d['turns'] else {};a=last.get('AGENTS.md',{}).get('text','');c=last.get('CLAUDE.md',{}).get('text','')
  first=d['turns'][0]['artifacts'] if d['turns'] else {}
  report['setup'][p.stem]={'agent_sections':len(re.findall(r'^## Agent skills$',a,re.M)),'claude_sections':len(re.findall(r'^## Agent skills$',c,re.M)),'imports':len(re.findall(r'^@AGENTS.md$',c,re.M)),'repeat_artifacts_unchanged':first==last if len(d['turns'])>1 else None,'final_artifacts':sorted(last)}
for state in ['draft','missing','malformed']:
 d=json.loads((b/('negative-build-'+state+'-assertions.json')).read_text());report['negative'][state]={'unchanged':d['unchanged'],'no_commit':d['git_head']!=0}
r.save('verification',report)
print(json.dumps({'installs':report['installs'],'cases':len(report['cases']),'negative':report['negative'],'setup':report['setup']},ensure_ascii=False,indent=2))
