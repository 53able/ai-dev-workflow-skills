#!/usr/bin/env python3
"""R3 corrected paired collector: fail closed before any unbound model launch."""
import copy,datetime,hashlib,importlib.util,json,os,pathlib,re,subprocess,tempfile
import runtime as rt
import activation_recheck as ar
from activation_closure_probe import mdm_forced,structural
ROOT=rt.OUT/'activation-r3'/'attempt-2'
MANIFEST=rt.SOURCE/'.omx/ultragoal/evidence/source-repair-r3/manifest.json'
CANONICAL=['hooks','plugins','remote_plugin','apps','memories','external_agent_memory_import','token_budget','goals','agent_message_board','multi_agent_v2','guardian_approval']
def save(name,value):ar.write(ROOT/(name+'.json'),value)
def h(b):return hashlib.sha256(b).hexdigest()
def freeze():
 m=json.loads(MANIFEST.read_text());assert all(rt.digest(rt.SOURCE/k)==v for k,v in m['suite_skill_metadata_sha256'].items()),'Released r3 source hash mismatch';return m


PROJECTION_VERSION='ignored-user-identities-v1'
PINNED_CODEX_SOURCE='83086188ae0614bd882818ff1aa23f3194962012'
PROJECTION_REASON='Pinned Exec ignore_user_config retains the exact User root with an empty table before reading user bytes; only its ignored content version and exact file digest are excluded.'

def launch_receipt(root,prompt,overrides):
 # Same argv layout as collect(); post-run comparison validates its actual receipt.
 argv=['codex','--no-daemon','-a','never','exec','--ignore-user-config','--ephemeral','--strict-config']
 for option in overrides:argv.extend(['-c',option])
 argv+=['-s','workspace-write','-m','gpt-6.1-sol','--json','-C',str(root),prompt]
 env=os.environ
 return {'argv':argv,'stdin':'DEVNULL','stdin_appended_bytes':0,'fresh_process':True,'no_daemon':True,'ignore_user_config':True,'ephemeral':True,'typed_skill_inputs':False,'typed_mention_inputs':False,'env_names':sorted(env),'env_nonempty':{k:bool(v) for k,v in sorted(env.items())},'environment_identity_sha256':{k:h(env[k].encode()) for k in ['HOME','CODEX_HOME'] if k in env}}

def comparison_input(structural_receipt,applied,installed,source_manifest_sha256):
 return {'structural':structural_receipt,'applied':applied,'installed_provenance':installed,'source_manifest_sha256':source_manifest_sha256}

def differences(left,right,path=''):
 # Structural inputs only: never load configuration content to explain a change.
 if type(left) is not type(right):return [{'path':path,'before':left,'after':right}]
 if isinstance(left,dict):
  out=[]
  for key in sorted(set(left)|set(right)):
   pointer=path+'/'+str(key).replace('~','~0').replace('/','~1')
   if key not in left or key not in right:out.append({'path':pointer,'before_present':key in left,'after_present':key in right,'before':left.get(key),'after':right.get(key)})
   else:out.extend(differences(left[key],right[key],pointer))
  return out
 if isinstance(left,list):
  if len(left)!=len(right):return [{'path':path,'before':left,'after':right}]
  return [d for i,(a,b) in enumerate(zip(left,right)) for d in differences(a,b,path+'/'+str(i))]
 return [] if left==right else [{'path':path,'before':left,'after':right}]

def compare_activation_inputs(before,after,launch,user_config_file):
 """Pure, fail-closed two-field projection; raw evidence is never modified."""
 result={'projection_version':PROJECTION_VERSION,'pinned_codex_source':PINNED_CODEX_SOURCE,'reason':PROJECTION_REASON,'raw_stable':before==after,'projected_stable':False,'excluded_field_paths':[],'raw_differences':differences(before,after),'premise_errors':[]}
 try:
  file=str(pathlib.Path(user_config_file));home=pathlib.Path(file).parent.parent
  if file!=str(home/'.codex/config.toml') or not pathlib.Path(file).is_absolute():raise ValueError('User config must be the exact default absolute home/.codex/config.toml')
  expected_source={'type':'user','file':file,'profile':None}
  names=before['structural']['all_layer_mcp_names']
  if names!=sorted(set(names)) or any(not re.fullmatch(r'[A-Za-z0-9_-]+',n) for n in names):raise ValueError('Unbound MCP name union')
  overrides=['features.'+n+'=false' for n in CANONICAL]
  for n in names:overrides.extend(['mcp_servers.'+n+'.enabled=false','mcp_servers.'+n+'.command="/usr/bin/false"'])
  argv=launch['argv'];prefix=['codex','--no-daemon','-a','never','exec','--ignore-user-config','--ephemeral','--strict-config']
  for option in overrides:prefix.extend(['-c',option])
  tail=['-s','workspace-write','-m','gpt-6.1-sol','--json','-C']
  if argv[:len(prefix)]!=prefix or argv[len(prefix):len(prefix)+len(tail)]!=tail or len(argv)!=len(prefix)+len(tail)+2:raise ValueError('Actual argv does not select the exact audited local fresh Exec loader/overrides')
  if not pathlib.Path(argv[-2]).is_absolute():raise ValueError('Unbound consumer cwd')
  for k,v in {'stdin':'DEVNULL','stdin_appended_bytes':0,'fresh_process':True,'no_daemon':True,'ignore_user_config':True,'ephemeral':True,'typed_skill_inputs':False,'typed_mention_inputs':False}.items():
   if type(launch[k]) is not type(v) or launch[k]!=v:raise ValueError('Unbound launch premise: '+k)
  env_names=launch['env_names'];nonempty=launch['env_nonempty'];digests=launch['environment_identity_sha256']
  if env_names!=sorted(set(env_names)) or set(env_names)!=set(nonempty) or any(type(v) is not bool for v in nonempty.values()):raise ValueError('Incomplete environment structure')
  if any(n.startswith('CODEX_EXEC_SERVER') for n in env_names):raise ValueError('Remote/noise environment selector present')
  if not nonempty.get('HOME') or digests.get('HOME')!=h(str(home).encode()):raise ValueError('HOME identity differs from exact selected user root')
  if 'CODEX_HOME' in env_names and (not nonempty['CODEX_HOME'] or digests.get('CODEX_HOME')!=h(str(home/'.codex').encode())):raise ValueError('Nondefault or unbound CODEX_HOME')
  for value in [before,after]:
   structural=value['structural'];layers=structural['layers'];files=structural['files'];applied=value['applied']
   if len(layers)!=2 or [x['source']['type'] for x in layers]!=['user','system']:raise ValueError('Unrecognized or reordered layers')
   if layers[0]['source']!=expected_source or layers[1]['source']!={'type':'system','file':'/etc/codex/config.toml'}:raise ValueError('Layer source/path/profile identity changed or unbound')
   if any(x['disabled_reason'] is not None for x in layers):raise ValueError('Disabled/error layer premise')
   if not all(isinstance(x['version'],str) and re.fullmatch(r'sha256:[0-9a-f]{64}',x['version']) for x in layers):raise ValueError('Unbound layer version')
   if layers[1]['structure']['top_level_keys']:raise ValueError('Nonempty relevant system layer')
   if any(set(structural[k])!={'config_toml_base64','requirements_toml_base64'} or any(v is not False for v in structural[k].values()) for k in ['mdm_before','mdm_after']):raise ValueError('Forced/error/unknown MDM state')
   if structural['all_layer_mcp_names']!=names:raise ValueError('MCP name union changed')
   if file not in files:raise ValueError('Exact user config file missing from receipt')
   if files[file].get('exists') is not True or not re.fullmatch(r'[0-9a-f]{64}',files[file].get('sha256','')):raise ValueError('Unbound user file identity')
   if any(v.get('exists') is not False or v.get('sha256') is not None for k,v in files.items() if k not in [file,str(home/'.codex/hooks.json')]):raise ValueError('Relevant system/project/legacy contributor file present')
   if applied['mcp_names']!=names or set(applied['mcp_enabled'])!=set(names) or any(v is not False for v in applied['mcp_enabled'].values()):raise ValueError('Effective MCP closure not established')
   if set(applied['canonical_features'])!=set(CANONICAL) or any(v is not False for v in applied['canonical_features'].values()):raise ValueError('Effective contributor flags not all false')
   if not value['installed_provenance'] or not re.fullmatch(r'[0-9a-f]{64}',value['source_manifest_sha256']):raise ValueError('Missing source/install provenance')
  left=copy.deepcopy(before);right=copy.deepcopy(after)
  for value in [left,right]:
   value['structural']['layers'][0]['version']='<IGNORED_USER_CONTENT_VERSION>'
   value['structural']['files'][file]['sha256']='<IGNORED_USER_CONTENT_SHA256>'
  result['excluded_field_paths']=['/structural/layers/0/version','/structural/files/'+file.replace('~','~0').replace('/','~1')+'/sha256']
  result['projected_stable']=left==right
 except (KeyError,TypeError,ValueError,IndexError,AttributeError) as e:result['premise_errors'].append(str(e))
 return result

def probe(root):
 before=mdm_forced()
 if any(before.values()):raise RuntimeError('Forced managed preference present; no model launch')
 rpc=rt.RPC(root)
 try:data=rpc.call('config/read',{'includeLayers':True,'cwd':str(root)},timeout=30)
 finally:rpc.close()
 layers=[]
 for layer in data.get('layers') or []:
  source=layer.get('name',layer.get('source'));s=structural(layer.get('config',{}))
  if not isinstance(source,dict) or source.get('type') not in ['user','system']:raise RuntimeError('Unbound config layer type; no model launch')
  if source['type']=='system' and s['top_level_keys']:raise RuntimeError('Nonempty system layer outside accepted empty-system premise')
  layers.append({'source':source,'version':layer.get('version'),'disabled_reason':layer.get('disabledReason'),'structure':s})
 if not layers:raise RuntimeError('No source layers returned; cannot bind loader')
 merged=structural(data.get('config',{}));names=sorted(set(merged['mcp_server_names'])|{n for x in layers for n in x['structure']['mcp_server_names']})
 if any(not re.fullmatch(r'[A-Za-z0-9_-]+',n) for n in names):raise RuntimeError('MCP name outside safe exact quoting grammar')
 home=pathlib.Path.home()/'.codex';files={}
 checks=[pathlib.Path('/etc/codex/config.toml'),pathlib.Path('/etc/codex/requirements.toml'),pathlib.Path('/etc/codex/managed_config.toml'),home/'managed_config.toml',home/'config.toml',home/'hooks.json']
 for a in set([root,*root.parents,root.resolve(),*root.resolve().parents]):checks.extend([a/'.codex/config.toml',a/'.codex/hooks.json'])
 for p in sorted(set(checks)):
  files[str(p)]={'exists':p.exists(),'sha256':rt.digest(p) if p.is_file() else None}
  if p.exists() and p not in [home/'config.toml',home/'hooks.json']:raise RuntimeError('System/legacy/project contributor file outside accepted absent-file premise: '+str(p))
 after=mdm_forced()
 if any(after.values()) or before!=after:raise RuntimeError('Managed state changed during structural probe')
 # No raw config values/credentials are serialized.
 return {'mdm_before':before,'mdm_after':after,'layers':layers,'all_layer_mcp_names':names,'files':files,'cli_loader_relation':'config/read only user+empty-system; CLI --ignore-user-config retains the exact User root with an empty table before reading its bytes; project/system/legacy files absent; forced MDM absent. Per-name false entries cover conservative all-layer union; canonical false scalars have no later managed override under these premises.','current_structural_only':True}


class ConfiguredRPC(rt.RPC):
 def __init__(self,root,overrides):
  args=['codex','--no-daemon','-a','never','app-server','--strict-config','--stdio']
  for value in overrides:args.extend(['-c',value])
  self.p=subprocess.Popen(args,cwd=root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
  self.buf=b'';self.seq=0;self.events=[]
  self.call('initialize',{'clientInfo':{'name':'ains-r3-structural-check','version':'1'}});self.send({'method':'initialized'})
def applied_probe(root,overrides,expected_names=None):
 rpc=ConfiguredRPC(root,overrides)
 try:data=rpc.call('config/read',{'includeLayers':True,'cwd':str(root)},timeout=30)
 finally:rpc.close()
 cfg=data['config'];servers=cfg.get('mcp_servers',{});features=cfg.get('features',{})
 if expected_names is not None and set(servers)!=set(expected_names):raise RuntimeError('Applied MCP names differ from exact all-layer union')
 if any(v.get('enabled') is not False for v in servers.values()):raise RuntimeError('Applied structural config contains an enabled or unknown-state MCP entry')
 if any(features.get(n) is not False for n in CANONICAL):raise RuntimeError('Canonical feature false override not reflected in applied config')
 return {'request':'config/read with same runtime overrides; no model/thread start','mcp_names':sorted(servers),'mcp_enabled':{n:v.get('enabled') for n,v in servers.items()},'canonical_features':{n:features.get(n) for n in CANONICAL},'note':'App-server includes user layer; all-layer union conservatively disabled. Actual exec ignores user and has only the bound empty-system/absent-project/absent-managed inputs.'}

def inventory(root):
 out=[]
 for p in sorted((root/'.agents/skills').glob('*/SKILL.md')):
  src=rt.SOURCE/'skills'/p.parent.name/'SKILL.md';meta=p.parent/'agents/openai.yaml';sm=src.parent/'agents/openai.yaml'
  out.append({'name':p.parent.name,'path':str(p),'realpath':str(p.resolve()),'sha256':rt.digest(p),'source_sha256':rt.digest(src),'metadata_sha256':rt.digest(meta) if meta.exists() else None,'source_metadata_sha256':rt.digest(sm) if sm.exists() else None})
 assert len(out)==len(list((rt.SOURCE/'skills').glob('*/SKILL.md'))) and all(x['sha256']==x['source_sha256'] and x['metadata_sha256']==x['source_metadata_sha256'] for x in out)
 return out

def manual_classifier():
 # This sibling is import-safe: runtime drivers are imported only in entrypoints.
 path=pathlib.Path(__file__).resolve().parents[1]/'claude/release_r3.py'
 spec=importlib.util.spec_from_file_location('ains_manual_evidence',path)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module

def manual_access(record,sources):
 """Pair command starts/completions without changing retained actual records."""
 events=[];starts={};originals={}
 for event in record.get('events',[]):
  if not isinstance(event,dict):continue
  item=event.get('item',{})
  if not isinstance(item,dict) or item.get('type')!='command_execution':continue
  ident=item.get('id')
  if event.get('type')=='item.started':
   if ident is not None:starts[ident]=event
   continue
  if event.get('type')!='item.completed':continue
  start=starts.get(ident,{}) if ident is not None else {}
  command=item.get('command') or start.get('item',{}).get('command')
  if not command:continue
  key=str(len(originals));originals[key]={'command_start':start or None,'command_result':event}
  events.extend([{'event':'tool_use','id':key,'name':'Bash','input':{'command':command}},
                 {'event':'tool_result','tool_use_id':key,'content':item.get('aggregated_output',''),
                  'is_error':item.get('exit_code')!=0 or item.get('status')!='completed'}])
 classifier=manual_classifier();attempts=[]
 found=classifier.loads({'events':events},attempts,sources)
 # Adapter records are derived; exact original event pairs remain attached.
 for result in found+attempts:result['paired_events']=originals[result['tool_use']['id']]
 return {'loads':found,'attempts':attempts}

def continuation_ready(record):
 if record.get('exit')!=0 or record.get('timeout') is not False or record.get('structural_closure',{}).get('projected_stable') is not True:return False
 terminal=False;open_turn=False
 for event in record.get('events',[]):
  if not isinstance(event,dict):continue
  typ=event.get('type','')
  if typ in ('error','turn.failed','turn.cancelled','turn.aborted') or (typ.startswith('turn.') and (event.get('error') is not None or event.get('is_error') or event.get('status') in ('failed','error','cancelled','aborted'))):return False
  if typ=='turn.started':open_turn=True
  if typ=='turn.completed':
   if event.get('status') not in (None,'completed','success','succeeded'):return False
   terminal=True;open_turn=False
 return terminal and not open_turn

def main():
 ROOT.mkdir(exist_ok=False);m=freeze();schema_path=rt.OUT/'activation-recheck-source/codex-rs__core__config.schema.json';schema=json.loads(schema_path.read_text());assert all(n in schema['properties']['features']['properties'] for n in CANONICAL);assert 'enabled' in schema['definitions']['RawMcpServerConfig']['properties']
 workspace=pathlib.Path(tempfile.mkdtemp(prefix='ains activation r3 '))
 save('launch-plan',{'source_release':'r3','workspace':str(workspace),'source_manifest_sha256':rt.digest(MANIFEST),'source_manifest':m,'canonical_false_flags':CANONICAL,'schema_sha256':rt.digest(schema_path),'premises_reference':'../r2/closure-plan/REGISTRY-MAP.md','modes':['default','copy'],'no_discovery_disable':True})
 controls=[('explicit-spec','$ains-spec Create a specification for a discount cap of 50. Preserve lower inputs; draft only, no implementation or approval. No commits, external actions, delegation, or inspection of host auth/config/environment.'),('explicit-build','$ains-build Inspect the approved cap-50 plan; describe its next task without implementing or editing. No commits, external actions, delegation, or inspection of host auth/config/environment.')]
 old=rt.OUT/'activation-recheck-r2'
 controls += [(n,json.loads((old/(n+'.json')).read_text())['prompt']) for n in ['automatic-tdd','unnamed-spec','unnamed-build']]
 for mode in ['default','copy']:
  for label,prompt in controls:
   root=workspace/(mode+' '+label+' consumer project');rt.base(root)
   if 'build' in label:rt.approved(root)
   args=['npx','--yes','skills@1.7.4','add',str(rt.SOURCE),'--skill','*','-a','codex','-y']+(['--copy'] if mode=='copy' else [])
   install=subprocess.run(args,cwd=root,stdin=subprocess.DEVNULL,capture_output=True,timeout=180);assert install.returncode==0
   name=mode+'-'+label;inv=inventory(root);save(name+'-inventory',{'installer_argv':args,'installer_exit':install.returncode,'skills':inv})
   freeze()
   try:
    first=probe(root);second=probe(root)
    overrides=['features.'+n+'=false' for n in CANONICAL]
    for n in second['all_layer_mcp_names']:
     prefix='mcp_servers.'+n
     overrides.extend([prefix+'.enabled=false',prefix+'.command="/usr/bin/false"'])
    applied_first=applied_probe(root,overrides,first['all_layer_mcp_names'])
    applied=applied_probe(root,overrides,second['all_layer_mcp_names'])
    launch=launch_receipt(root,prompt,overrides)
    bound_before=comparison_input(second,applied,inv,rt.digest(MANIFEST))
    precomparison=compare_activation_inputs(comparison_input(first,applied_first,inv,rt.digest(MANIFEST)),bound_before,launch,pathlib.Path.home()/'.codex/config.toml')
    save(name+'-precomparison',precomparison)
    if not precomparison['projected_stable']:raise RuntimeError('Structural preflight projected guard failed; no launch')
    save(name+'-preflight',{'first':first,'second':second,'stable':precomparison['raw_stable'],'projection_comparison':precomparison,'launch_premises':launch,'applied_model_free_check':applied,'overrides':overrides,'prompt_source':'frozen r2 exact prompt' if label in ['automatic-tdd','unnamed-spec','unnamed-build'] else 'same-stage positive','ready_before_model_launch':True})
   except Exception as e:save(name+'-BLOCKER',{'phase':'before model launch','error':str(e),'model_launched':False});return
   ar.collect(root,name,prompt,ROOT,overrides)
   record=json.loads((ROOT/(name+'.json')).read_text())
   try:
    after=probe(root);after_applied=applied_probe(root,overrides,after['all_layer_mcp_names']);after_inventory=inventory(root)
    visible_keys=[k for k in launch if k!='environment_identity_sha256']
    launch_binding={'actual_receipt_fields_match':all(record.get(k)==launch[k] for k in visible_keys),'parent_environment_receipt_stable':launch_receipt(root,prompt,overrides)==launch,'environment_identity_sha256':launch['environment_identity_sha256'],'reason':'Identity digests captured immediately before collect from the same parent environment copied by collect; actual argv/input/env names and booleans must match, and parent identity is rechecked afterward.'}
    record['projection_launch_binding']=launch_binding
    if not launch_binding['actual_receipt_fields_match'] or not launch_binding['parent_environment_receipt_stable']:raise RuntimeError('Actual launch/environment does not match bound prelaunch receipt')
    comparison=compare_activation_inputs(bound_before,comparison_input(after,after_applied,after_inventory,rt.digest(MANIFEST)),launch,pathlib.Path.home()/'.codex/config.toml')
    record['structural_closure']={'before':second,'after':after,'stable':comparison['raw_stable'],'projected_stable':comparison['projected_stable'],'projection_comparison':comparison,'post_applied_model_free_check':after_applied,'installed_bytes_unchanged':after_inventory==inv}
   except Exception as e:record['structural_closure']={'stable':False,'projected_stable':False,'error':str(e)}
   ar.write(ROOT/(name+'.json'),record);print(name,record['exit'],record['seconds'],'raw_closure',record['structural_closure']['stable'],'projected_closure',record['structural_closure']['projected_stable'],flush=True)
   if label in ['unnamed-spec','unnamed-build']:
    classifier=manual_classifier()
    access=manual_access(record,classifier.installed_manual_sources(root))
    save(name+'-manual-access',access)
    if access['loads']:
     save(name+'-manual-body-FAIL',{'reason':'Actual manual source content or successful helper execution observed; stopping duplicate controls','evidence':access['loads'],'repeat':False});return
   if not continuation_ready(record):
    save(name+'-continuation-BLOCKER',{'reason':'No healthy successful turn terminal with exit0, timeout false and projected closure; next launch held','record':name+'.json','repeat':False});return
   freeze()
 manifest={f.name:rt.digest(f) for f in ROOT.glob('*.json')};save('frozen-results-manifest',{'source_version':'r3','immutable_results':manifest,'observer_status':'Ready for fresh independent audit; no historical verdict changed'})
 print('FROZEN OBSERVER HANDOFF READY',str(ROOT),flush=True)
if __name__=='__main__':
 raise SystemExit('Runtime launch held after terminal r3 handoff. Import for model-free structural checks only; a separately authorized future run must use a fresh output directory.')
