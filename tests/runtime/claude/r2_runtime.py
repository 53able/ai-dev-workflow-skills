#!/usr/bin/env python3
"""Real Claude fixtures. Raw streams/debug remain memory/temp only; no auth handling."""
import hashlib,json,os,pathlib,re,signal,subprocess,tempfile,time,selectors,shutil
SOURCE=pathlib.Path(__file__).resolve().parents[3]
OUT=SOURCE/'.omx/ultragoal/evidence/g004/claude/release-r2'
OUT.mkdir(parents=True,exist_ok=True)
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,obj): (OUT/(name+'.json')).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def shell(argv,cwd,timeout=180):
 p=subprocess.Popen(argv,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
 try: a,b=p.communicate(timeout=timeout)
 except subprocess.TimeoutExpired:
  os.killpg(p.pid,signal.SIGTERM)
  try:a,b=p.communicate(timeout=3)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);a,b=p.communicate()
 return p.returncode,(a+b).decode(errors='replace')
def inventory(root):
 return {str(p.relative_to(root)):digest(p) for p in sorted(root.glob('*/SKILL.md'))+sorted(root.glob('*/agents/openai.yaml'))}
def install(mode):
 root=pathlib.Path(tempfile.mkdtemp(prefix='ains claude '+mode+' consumer ',dir='/private/tmp'))
 shell(['git','init','-q'],root)
 cmd=['npx','--yes','skills@1.7.4','add',str(SOURCE),'--skill','*','-a','claude-code','codex','-y']+(['--copy'] if mode=='copy' else [])
 code,output=shell(cmd,root)
 expected=inventory(SOURCE/'skills'); actual=inventory(root/'.claude/skills')
 save('install-'+mode,{'root':str(root),'argv':cmd,'exit':code,'source':expected,'installed':actual,'parity':expected==actual,'claude_entries_are_symlinks':all(p.is_symlink() for p in (root/'.claude/skills').iterdir()),'paths':{p.parent.name:{'logical':str(p),'real':str(p.resolve()),'sha256':digest(p)} for p in (root/'.claude/skills').glob('*/SKILL.md')}})
 assert code==0 and actual==expected
 return root

def sanitize(s):
 s=re.sub(r'[A-Za-z0-9_.+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', '[REDACTED_EMAIL]',s)
 s=re.sub(r'(?i)(bearer\s+|sk-ant-)[A-Za-z0-9_.\-]+','[REDACTED_SECRET]',s)
 return s

def snapshot(root):
 return {str(p.relative_to(root)):{'sha256':digest(p),'text':p.read_text(errors='replace')} for p in root.rglob('*') if p.is_file() and not any(x.startswith('.') for x in p.relative_to(root).parts) and (p.suffix in ('.md','.py','.txt','.json') or p.name=='human-review-rules') and p.stat().st_size<50000}

def clean_tree(value):
 if isinstance(value,str):return sanitize(value)
 if isinstance(value,list):return [clean_tree(v) for v in value]
 if isinstance(value,dict):return {k:clean_tree(v) for k,v in value.items()}
 return value

def secure(value,key=''):
 if re.search(r'(?i)(api.?key|authorization|access.?token|refresh.?token|credential|secret|email)',key):return '[REDACTED_FIELD]'
 if isinstance(value,dict):return {k:secure(v,k) for k,v in value.items()}
 if isinstance(value,list):return [secure(v) for v in value]
 if isinstance(value,str):
  if key in ('session_id','uuid','parent_tool_use_id'):return 'sha256:'+hashlib.sha256(value.encode()).hexdigest()
  return sanitize(value)
 return value

def contributors(root):
 project={}
 for n in ['AGENTS.md','CLAUDE.md','.claude/settings.json','.claude/settings.local.json']:
  p=root/n
  if p.is_file():project[n]={'sha256':digest(p),'text':p.read_text() if n.endswith('.md') else '[settings contents excluded]'}
 globals=[]
 for base in [pathlib.Path.home()/'.claude/skills',pathlib.Path.home()/'.claude/plugins/cache',pathlib.Path('/Library/Application Support/ClaudeCode/.claude/skills')]:
  if base.exists():
   for p in base.rglob('SKILL.md'):
    try:
     m=re.search(r'^name:\s*[\"\']?([a-zA-Z0-9_-]+)',p.read_text(errors='replace')[:12000],re.M)
     n=m.group(1) if m else p.parent.name
     globals.append({'name':n,'path':str(p),'sha256':digest(p)})
    except OSError:pass
 return {'project_rules':project,'ancestor_rules':[str(a/n) for a in root.parents for n in ['AGENTS.md','CLAUDE.md'] if (a/n).exists()],'installed_inventory':inventory(root/'.claude/skills'),'host_skill_inventory_names_paths_hashes_only':globals,'host_ains_homonyms':[g for g in globals if g['name']=='ains' or g['name'].startswith('ains-')],'settings_sources':'project,local','strict_empty_MCP':True,'sterile_host':False,'full_effective_model_prompt_observed':False}

def run(name,root,prompts,write=False,timeout=180):
 """Each prompt is a distinct actual user-role message; next follows result pause."""
 debugdir=pathlib.Path(tempfile.mkdtemp(prefix='ains-claude-log-',dir='/private/tmp'))
 debug=debugdir/'debug.log'
 tools='Read,Glob,Grep,Skill,Bash'+(',Edit,Write' if write else '')
 allowed='Read,Glob,Grep,Skill,Bash'+(',Edit,Write' if write else '')
 argv=['claude','-p','--model','claude-sonnet-5-5','--permission-mode','dontAsk','--permission-prompts','none','--tools',tools,'--allowedTools',allowed,'--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--setting-sources','project,local','--no-session-persistence','--input-format','stream-json','--output-format','stream-json','--verbose','--replay-user-messages','--debug-file',str(debug)]
 child_env=os.environ.copy()
 child_env.update(GIT_AUTHOR_NAME='Synthetic Fixture User',GIT_AUTHOR_EMAIL='fixture@example.invalid',GIT_COMMITTER_NAME='Synthetic Fixture User',GIT_COMMITTER_EMAIL='fixture@example.invalid')
 p=subprocess.Popen(argv,cwd=root,env=child_env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1,start_new_session=True)
 sel=selectors.DefaultSelector();sel.register(p.stdout,selectors.EVENT_READ);sel.register(p.stderr,selectors.EVENT_READ)
 events=[];turns=[];models=set();allraw=[];stream_records=[];stdin_records=[];timed=False;started=time.monotonic();initial_artifacts=snapshot(root);input_gates=[];gate_blocked=False
 def send(prompt):
  item={'type':'user','message':{'role':'user','content':prompt}}
  stdin_records.append({'index':len(stdin_records),'monotonic':round(time.monotonic()-started,3),'input':item,'effective_input_contributors':contributors(root)});p.stdin.write(json.dumps(item)+'\n');p.stdin.flush()
 send(prompts[0]);index=0;turnstart=time.monotonic()
 try:
  while True:
   if time.monotonic()-turnstart>timeout: timed=True;break
   ready=sel.select(0.5)
   for key,_ in ready:
    line=key.fileobj.readline()
    if not line: sel.unregister(key.fileobj);continue
    allraw.append(line)
    try:x=json.loads(line)
    except ValueError:continue
    stream_records.append(x)
    typ=x.get('type'); msg=x.get('message',{})
    if typ=='system' and x.get('subtype')=='init':
     events.append({'event':'init','session_id_sha256':hashlib.sha256(x.get('session_id','').encode()).hexdigest(),'cwd':x.get('cwd'),'model':x.get('model'),'skills':x.get('skills'),'slash_commands':[s for s in x.get('slash_commands',[]) if s.startswith('ains')]})
    if isinstance(msg,dict):
     if msg.get('model'):models.add(msg['model'])
     for b in msg.get('content',[]) if isinstance(msg.get('content'),list) else []:
      if b.get('type')=='tool_use':events.append({'event':'tool_use','name':b.get('name'),'input':b.get('input'),'id':b.get('id')})
      elif b.get('type')=='tool_result':events.append({'event':'tool_result','tool_use_id':b.get('tool_use_id'),'is_error':b.get('is_error'), 'content':b.get('content')})
      elif b.get('type')=='text':events.append({'event':'text','role':msg.get('role'),'transport_type':typ,'text':b.get('text')})
    if typ=='result':
     turns.append({'user_input':prompts[index],'result':x.get('result'),'subtype':x.get('subtype'),'is_error':x.get('is_error'),'elapsed':round(time.monotonic()-turnstart,2),'permission_denials':x.get('permission_denials',[]),'artifacts':snapshot(root)})
     save(name+'-checkpoints',clean_tree({'turns':turns}))
     if index+1<len(prompts):
      next_prompt=prompts[index+1]
      if next_prompt.startswith('SYNTHETIC FIXTURE USER APPROVAL') or next_prompt.startswith('SYNTHETIC FIXTURE USER REPLY'):
       paused=bool(re.search(r'回答|承認|どちら|待|approval|approve|wait',x.get('result',''),re.I))
       code_unchanged=all(snapshot(root).get(k,{}).get('sha256')==v['sha256'] for k,v in initial_artifacts.items() if k.endswith('.py'))
       draft_present=any('status: draft' in v['text'] for k,v in snapshot(root).items() if k.endswith(('spec.md','tasks.md')))
       allowed=paused and code_unchanged and (draft_present if next_prompt.startswith('SYNTHETIC FIXTURE USER APPROVAL') else True)
       input_gates.append({'next_user_input_index':index+1,'observed_pause':paused,'implementation_unchanged':code_unchanged,'draft_present':draft_present,'sent':allowed})
       if not allowed:gate_blocked=True;break
      index+=1;send(prompts[index]);turnstart=time.monotonic()
     else:p.stdin.close();break
   if len(turns)==len(prompts) or not sel.get_map() or p.poll() is not None:break
 finally:
  if not timed and len(turns)==len(prompts):
   try:p.wait(timeout=5)
   except subprocess.TimeoutExpired:pass
  if p.poll() is None:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=3)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
  debugfacts=[];debug_inventory=[]
  if debug.exists():
   for line in debug.read_text(errors='replace').splitlines():
    if re.search(r'\[DEBUG\].*(skill|Skill|slash|Slash|command|Command|memory|Memory|CLAUDE\.md)',line):
     debug_inventory.append({'event_prefix':sanitize(line.split(': ',1)[0][:200]),'ains_names':sorted(set(re.findall(r'ains(?:-[a-z-]+)?',line))),'installed_paths':[str(p) for p in root.glob('.claude/skills/*/SKILL.md') if str(p) in line],'sha256':hashlib.sha256(line.encode()).hexdigest()})
    if re.search(r'skill|command',line,re.I) and re.search(r'ains',line):
     # Whitelist path and loader operation names only, never debug payload/context.
     paths=[str(p) for p in [root,root/'.claude/skills',*[root/'.claude/skills'/n for n in inventory(root/'.claude/skills') if n.endswith('SKILL.md')]] if str(p) in line]
     ops=[v for v in ['Executing','Loading','Loaded','load','skill','command','Skill','baseDir','Base directory','expand','processSlashCommand'] if v in line]
     loader_line=sanitize(line) if re.search(r'\[DEBUG\].*(Loading skills from:|Executing command|command.*loaded|skill.*loaded|Skill.*base|processSlashCommand)',line) and not re.search(r'Bash|tool_use|tool_result',line) else None
     debugfacts.append({'loader_record':loader_line,'event_prefix':line.split('ains')[0][:220],'paths':paths,'operations':ops,'line_sha256':hashlib.sha256(line.encode()).hexdigest()})
   debug.unlink()
  shutil.rmtree(debugdir)
  result={'name':name,'root':str(root),'argv':argv,'prompts':prompts,'exit':p.returncode,'timeout':timed,'elapsed':round(time.monotonic()-started,2),'models':sorted(models),'turns':turns,'events':events,'debug_facts':debugfacts,'debug_loader_inventory':debug_inventory,'raw_persisted':False,'all_sanitized_stream_events':secure(stream_records),'controlled_stdin':secure(stdin_records),'input_contributor_state':contributors(root),'synthetic_input_gates':input_gates,'input_gate_blocked':gate_blocked,'intentional_harness_stop_after_result':bool(len(turns)==len(prompts) and p.returncode in (143,-15))}
  result=clean_tree(result)
  save(name,result)
  print(json.dumps({'name':name,'timeout':timed,'turns':len(turns),'elapsed':result['elapsed'],'tools':[e['name'] for e in events if e['event']=='tool_use']},ensure_ascii=False),flush=True)
 return result
if __name__=='__main__':
 root=install('symlink');save('roots',{'symlink':str(root)})
 run('router-bootstrap',root,['/ains Inspect this disposable fixture and recommend the next stage. Do not edit files.'])
