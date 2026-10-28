#!/usr/bin/env python3
"""Prepared collector. No run occurs without --run and a parent-supplied freeze ID.

This retains all JSON event/item types, closes stdin, and records structural
launch facts. Structural snapshots are not mislabeled runtime effective state.
"""
import argparse,hashlib,json,os,pathlib,re,signal,subprocess,tempfile,time,tomllib
from runtime import SOURCE,OUT,base,approved,digest,clean,snapshot
FLAGS=['hooks','codex_hooks','plugin_hooks','plugins','remote_plugin','apps','connectors','memories','memory_tool','external_agent_memory_import']
SENSITIVE=re.compile(r'api.?key|access.?token|secret|password|authorization|cookie',re.I)
def sha(b):return hashlib.sha256(b).hexdigest()
def sanitized(v):
 if isinstance(v,str):return clean(v)
 if isinstance(v,list):return [sanitized(x) for x in v]
 if isinstance(v,dict):return {k:('<REDACTED>' if SENSITIVE.search(k) else sanitized(x)) for k,x in v.items()}
 return v
def write(p,value):p.write_text(json.dumps(sanitized(value),ensure_ascii=False,indent=2)+'\n')
def file_structure(p):
 r={'path':clean(str(p)),'exists':p.exists()}
 if not p.exists():return r
 b=p.read_bytes();r['sha256']=sha(b)
 try:
  obj=json.loads(b) if p.suffix=='.json' else tomllib.loads(b.decode())
  r['top_level_keys']=sorted(obj)
  r['relevant_key_presence']={k:k in obj for k in ['hooks','plugins','mcp_servers','skills','features','instructions','developer_instructions','model_instructions_file']}
  for k in ['hooks','plugins','mcp_servers','skills']:
   v=obj.get(k,{})
   r[k+'_structure']={'type':type(v).__name__,'count':len(v) if isinstance(v,(dict,list)) else None}
   if k=='hooks' and isinstance(v,dict):r[k+'_structure']['event_counts']={n:len(x) for n,x in v.items() if isinstance(x,list)}
  r['feature_bools']={k:v for k,v in obj.get('features',{}).items() if k in FLAGS and isinstance(v,bool)}
 except Exception as e:r['parse_error_type']=type(e).__name__
 return r
def receipt(root,env,argv,prompt):
 home=pathlib.Path(env.get('CODEX_HOME',str(pathlib.Path.home()/'.codex')))
 configs=[pathlib.Path('/etc/codex/config.toml'),pathlib.Path('/etc/codex/requirements.toml'),home/'config.toml',home/'hooks.json',pathlib.Path('/etc/codex/managed_config.toml'),home/'managed_config.toml']
 for a in [root,*root.parents]:configs.extend([a/'.codex/config.toml',a/'.codex/hooks.json'])
 return {'argv':argv,'prompt':prompt,'prompt_sha256':sha(prompt.encode()),'stdin':'DEVNULL','stdin_appended_bytes':0,'fresh_process':True,'no_daemon':True,'ignore_user_config':True,'ephemeral':True,'typed_skill_inputs':False,'typed_mention_inputs':False,'env_names':sorted(env),'env_names_sha256':sha('\n'.join(sorted(env)).encode()),'env_nonempty':{k:bool(v) for k,v in sorted(env.items())},'relevant_nonsecret_env_digests':{k:sha(v.encode()) for k,v in env.items() if re.match(r'^(CODEX|T3|OPENAI|RUST|XDG|HOME|TMUX)',k) and not SENSITIVE.search(k)},'config_structural_snapshots':[file_structure(p) for p in dict.fromkeys(configs)],'instruction_files':[{'path':str(p),'sha256':digest(p)} for a in [root,*root.parents] for n in ['AGENTS.md','CLAUDE.md'] if (p:=a/n).is_file()],'effective_state_claim':'Launch overrides and structural input snapshots only. Parent must source-bind loader/contributor/required-skill closure; this receipt does not claim a runtime effective-state API exists.'}
def collect(root,label,prompt,out,overrides):
 env=os.environ.copy()
 argv=['codex','--no-daemon','-a','never','exec','--ignore-user-config','--ephemeral','--strict-config']
 for option in overrides:argv.extend(['-c',option])
 argv+=['-s','workspace-write','-m','gpt-6.1-sol','--json','-C',str(root),prompt]
 rec=receipt(root,env,argv,prompt);rec['before']=snapshot(root);start=time.monotonic()
 p=subprocess.Popen(argv,cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
 try:stdout,stderr=p.communicate(timeout=180);rec['timeout']=False
 except subprocess.TimeoutExpired:
  rec['timeout']=True;os.killpg(p.pid,signal.SIGTERM)
  try:stdout,stderr=p.communicate(timeout=5)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate()
 events=[];other=[]
 for line in stdout.decode(errors='replace').splitlines():
  try:events.append(json.loads(line))
  except ValueError:other.append(line)
 rec.update(exit=p.returncode,seconds=round(time.monotonic()-start,2),events=events,stdout_non_json_count=len(other),stdout_non_json_sha256=[sha(line.encode()) for line in other],stdout_sha256=sha(stdout),stdout_bytes=len(stdout),stderr_bytes=len(stderr),stderr_sha256=sha(stderr),stderr_line_count=len(stderr.decode(errors='replace').splitlines()),stdout_line_count=len(stdout.decode(errors='replace').splitlines()),retained_json_event_count=len(events),stderr_categories=[x for x in ['error','auth','sandbox','rate limit','config'] if x in stderr.decode(errors='replace').lower()],after=snapshot(root),event_types=sorted({str(e.get('type')) for e in events if isinstance(e,dict)}),item_types=sorted({str(e.get('item',{}).get('type')) for e in events if isinstance(e,dict) and isinstance(e.get('item'),dict)}))
 write(out/(label+'.json'),rec)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--run',action='store_true');ap.add_argument('--freeze-id');a=ap.parse_args()
 schema=OUT/'activation-recheck-source/codex-rs__core__config.schema.json'
 d=json.loads(schema.read_text());known=d['properties']['features']['properties'];assert all(x in known for x in FLAGS)
 overrides=['features.'+x+'=false' for x in FLAGS]+['mcp_servers={}']
 if not a.run:
  print('PREPARED ONLY; no installation or model run. Waiting for parent source-r2 freeze.');return
 if not a.freeze_id:ap.error('--run requires the parent-announced --freeze-id')
 freeze=json.loads((SOURCE/'.omx/ultragoal/evidence/source-repair-r2/source-sha256.json').read_text())
 assert all(digest(SOURCE/k)==v for k,v in freeze.items()), 'Source differs from released r2 freeze'
 out=OUT/('activation-recheck-'+re.sub(r'[^a-zA-Z0-9_.-]','_',a.freeze_id));out.mkdir(exist_ok=False)
 workspace=pathlib.Path(tempfile.mkdtemp(prefix='ains activation recheck '+a.freeze_id+' '))
 controls=[('explicit-spec','$ains-spec Create a specification for a discount cap of 50. Preserve lower inputs; draft only, no implementation or approval.'),('explicit-build','$ains-build Inspect the approved cap-50 plan; describe its next task without implementing or editing.'),('automatic-tdd','Fix the bug: discount(80) should return 50 but returns 80. Write and run a failing regression test before the minimal fix; preserve lower inputs.'),('unnamed-spec','Create a specification for the requested discount cap behavior; ask about missing decisions before approving it. Do not implement.'),('unnamed-build','Implement the approved discount cap plan and verify it.')]
 write(out/'launch-plan.json',{'freeze_id':a.freeze_id,'workspace':str(workspace),'overrides':overrides,'schema_sha256':digest(schema),'source_inventory':{str(p.relative_to(SOURCE)):digest(p) for p in (SOURCE/'skills').rglob('*') if p.is_file() and (p.name=='SKILL.md' or p.name=='openai.yaml')},'closure_status':'For parent source-bound review; no universal injection-observer claim.'})
 for label,prompt in controls:
  root=workspace/(label+' consumer project');base(root)
  if 'build' in label:approved(root)
  install=['npx','--yes','skills@1.7.4','add',str(SOURCE),'--skill','*','-a','codex','-y','--copy']
  p=subprocess.run(install,cwd=root,stdin=subprocess.DEVNULL,capture_output=True,timeout=180)
  if p.returncode:raise RuntimeError('Pinned install failed; raw output not persisted')
  write(out/(label+'-inventory.json'),[{'name':p.parent.name,'path':str(p),'realpath':str(p.resolve()),'sha256':digest(p),'metadata_sha256':digest(p.parent/'agents/openai.yaml') if (p.parent/'agents/openai.yaml').exists() else None} for p in sorted((root/'.agents/skills').glob('*/SKILL.md'))])
  collect(root,label,prompt+' No commits, external actions, delegation, or inspection of host auth/config/environment.',out,overrides)
if __name__=='__main__':main()
