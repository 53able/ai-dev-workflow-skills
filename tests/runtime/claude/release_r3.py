#!/usr/bin/env python3
import json,pathlib,re,shlex,sys
MANUAL=['ains','ains-setup','ains-spec','ains-tasks','ains-build','ains-ship','ains-retro','ains-team-canvas','ains-harness','ains-tool-access']
def bootstrap():
 import r3_runtime as r
 manifest=json.loads((r.SOURCE/'.omx/ultragoal/evidence/source-repair-r3/manifest.json').read_text())
 assert all(r.digest(r.SOURCE/p)==h for p,h in manifest['suite_skill_metadata_sha256'].items())
 r.save('freeze-validation',manifest)
 r.save('prior-preservation',{'files':{str(p.relative_to(r.OUT.parent)):r.digest(p) for p in r.OUT.parent.rglob('*') if p.is_file() and 'release-r3' not in p.relative_to(r.OUT.parent).parts and p.name!='REPORT-r3.md'}})
 roots={mode:str(r.install(mode)) for mode in ['copy','symlink']};r.save('roots',roots)
def installed_manual_sources(root):
 """Current installed procedure resources only; no historical transcript reads."""
 sources={}
 for alias in ('.claude','.agents'):
  for stage in MANUAL:
   base=root/alias/'skills'/stage
   for path in base.rglob('*'):
    relative=path.relative_to(base)
    if path.is_file() and not any(p.startswith('.') or p=='__pycache__' for p in relative.parts) and str(relative)!='agents/openai.yaml':
     sources[stage+'/'+str(relative)]=path.read_text(errors='replace')
 return sources

def content_text(content):
 if isinstance(content,list):return '\n'.join(str(b.get('text','')) for b in content if isinstance(b,dict))
 return content if isinstance(content,str) else ''

def content_lines(content):
 lines=[]
 for line in content_text(content).splitlines():
  # Grep path/line prefixes, Read line numbers and nl output are presentation.
  line=re.sub(r'^(?:.*?:)?\s*\d+(?:[:→\t|\-]|\s{2,})\s*','',line.strip())
  line=' '.join(line.split())
  if len(line)>=24 and not re.fullmatch(r'\S*/skills/\S+',line):lines.append(line)
 return lines

def returned_content(content,sources,stages):
 # A substantive returned snippet must occur in the identified installed source.
 # Aggregate status and generic headings/line-number shapes are not attribution.
 observed=set(content_lines(content));matched=[]
 for resource,body in sources.items():
  stage=resource.split('/',1)[0]
  if stage in stages and any(snippet in line for snippet in observed for line in content_lines(body)):matched.append(stage)
 return sorted(set(matched))

def resource_refs(text):
 return re.findall(r"(?:\.claude|\.agents)/skills/("+'|'.join(re.escape(n) for n in MANUAL)+r")/([^\s'\";|&<>)]*)",text)

def successful_helper(command,result,sources):
 # Keep raw command separators visible before shlex treats them as whitespace.
 if '\n' in command or '\r' in command:return []
 # Only literal single-command forms are supported, not shell interpretation.
 if result.get('is_error') or re.search(r'[\x00-\x08\x0b-\x1f\x7f;&|<>()`$\\{}\[\]*?!~#]',command):return []
 try:
  lexer=shlex.shlex(command,posix=True,punctuation_chars=';&|<>()')
  lexer.whitespace_split=True;tokens=list(lexer)
 except ValueError:return []
 if not tokens or any(re.fullmatch(r'[;&|<>()]+',t) for t in tokens):return []
 if re.search(r'(?im)^(?:(?:bash|sh|python\d*):.*(?:no such file|not found|permission denied|error)|(?:permission denied|access denied|command failed|<tool_use_error>))',content_text(result.get('content',''))):return []
 interpreters=('bash','sh','python','python3','/bin/bash','/bin/sh',
               '/usr/bin/bash','/usr/bin/sh','/usr/bin/python','/usr/bin/python3')
 interpreted=tokens[0] in interpreters
 if interpreted:
  # No option is skipped: help/version/stdin/syntax-only modes need not run it.
  if len(tokens)<2 or tokens[1].startswith('-'):return []
  target=tokens[1]
 else:target=tokens[0]
 if not re.fullmatch(r'(?:/|\./|\.\./|\.claude/|\.agents/)[A-Za-z0-9_./ -]+',target):return []
 # Unlike free-text resource_refs, decoded operand identity must not truncate
 # at whitespace or discard any trailing filename characters.
 parts=target.split('/')
 anchors=[i for i in range(len(parts)-2) if parts[i] in ('.claude','.agents') and parts[i+1]=='skills']
 if len(anchors)!=1:return []
 index=anchors[0];stage=parts[index+2];relative_parts=parts[index+3:]
 if stage not in MANUAL or not relative_parts or any(p in ('','.','..') for p in relative_parts):return []
 relative='/'.join(relative_parts);key=stage+'/'+relative
 if key not in sources:return []
 return [stage] if interpreted or relative.endswith(('.sh','.py')) or sources[key].startswith('#!') else []

def loads(d,attempts=None,sources=None):
 sources={} if sources is None else sources
 found=[];uses={e['id']:e for e in d['events'] if e['event']=='tool_use'}
 for e in d['events']:
  if e['event']!='tool_result' or e.get('tool_use_id') not in uses:continue
  u=uses[e['tool_use_id']];inputs=u['input'];s=str(inputs);text=content_text(e.get('content',''))
  installed=('.claude/skills' in s or '.agents/skills' in s)
  direct=u['name']=='Read' and installed
  grep=u['name']=='Grep' and inputs.get('output_mode')=='content'
  shell=u['name']=='Bash' and installed
  if not (direct or shell or (grep and (installed or resource_refs(text)))):continue
  names=sorted({stage for stage,_ in resource_refs(s)})
  # A stage directory itself is a valid targeted Grep path.
  names=sorted(set(names)|{stage for stage in MANUAL if re.search(r'/skills/'+re.escape(stage)+r"(?:/|['\"\s}]|$)",s)})
  if grep:names=sorted(set(names)|{stage for stage,_ in resource_refs(text)})
  explicit_stages=re.findall(r"(?:\.claude|\.agents)/skills/([^/\s'\";|&<>}]+)",s)
  if not names and installed and not explicit_stages:names=list(MANUAL)
  if not names:continue
  actual=returned_content(text,sources,names)
  helper=successful_helper(inputs.get('command',''),e,sources) if shell else []
  item={'stages':actual or helper or names,'tool_use':u,'tool_result':e}
  if actual or helper:
   item['classification']='observed source-correlated returned content' if actual else 'observed successful simple helper execution'
   found.append(item)
  elif attempts is not None:
   item['classification']='access attempt; content/helper execution UNVERIFIED (failed, empty or insufficiently attributable aggregate)'
   attempts.append(item)
 return found
def negatives():
 import r3_runtime as r
 from suite import fixture,plan
 R2=r.OUT.parent/'release-r2'
 roots={k:pathlib.Path(v) for k,v in json.loads((r.OUT/'roots.json').read_text()).items()}
 summary=[]
 for name in ['unnamed-spec-symlink','unnamed-spec-copy','unnamed-build-symlink','unnamed-build-copy']:
  old=json.loads((R2/(name+'.json')).read_text());mode=name.rsplit('-',1)[1];root=fixture(roots[mode],'r3-'+name)
  if 'build' in name:plan(root)
  expected=old['controlled_stdin'][0]['effective_input_contributors']['project_rules']
  assert all((root/p).read_text()==v['text'] for p,v in expected.items() if p.endswith('.md')),'Original project contract mismatch'
  r.save(name+'-fixture',{'r2_run':str(R2/(name+'.json')),'unchanged_user_inputs':old['prompts'],'original_project_contract_hashes':{p:v['sha256'] for p,v in expected.items()},'actual_initial_project_contract_hashes':{p:r.digest(root/p) for p in expected if (root/p).exists()},'initial_artifacts':r.snapshot(root)})
  d=r.run(name,root,old['prompts'],True);attempts=[];observed=loads(d,attempts,installed_manual_sources(root))
  item={'case':name,'user_inputs_identical':d['prompts']==old['prompts'],'verdict':'FAIL' if observed else 'NO_OBSERVED_MANUAL_LOAD; complete suppression UNVERIFIED','manual_load_evidence':observed,'manual_access_attempts':attempts}
  summary.append(item);r.save('negative-results',summary)
  if observed:
   r.save('STOP-FAIL',{'case':name,'reason':'Unsolicited installed manual content read/execution observed; stop duplicate negative model runs','evidence':observed});print('STOP: '+name+' manual content load observed',flush=True);return
if __name__=='__main__':
 {'bootstrap':bootstrap,'negatives':negatives}[sys.argv[1]]()
