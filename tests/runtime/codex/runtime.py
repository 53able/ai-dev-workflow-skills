#!/usr/bin/env python3
"""Bounded real Codex runtime evidence. No dependencies; no auth/config copying."""
import argparse, concurrent.futures, hashlib, json, os, pathlib, re, select, signal, subprocess, tempfile, time
SOURCE=pathlib.Path(__file__).resolve().parents[3]
OUT=SOURCE/'.omx/ultragoal/evidence/g004/codex'
OUT.mkdir(parents=True,exist_ok=True)
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,value): (OUT/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def clean(s):
 s=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '<EMAIL>',s)
 # Targeted credential shapes only; this is not universal secret detection.
 s=re.sub(r'(?i)\bbearer[ \t]+[A-Za-z0-9._~+/=-]+','<REDACTED_SECRET>',s)
 s=re.sub(r'\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{16,}','<REDACTED_SECRET>',s)
 s=re.sub(r'''(?i)(["']?(?:[a-z0-9]+_)?api[_-]?key["']?\s*[:=]\s*)["']?[A-Za-z0-9._~+/=-]{16,}["']?''',r'\1<REDACTED_SECRET>',s)
 return s.replace(str(pathlib.Path.home()),'<HOST_HOME>')
def sanitized(value):
 if isinstance(value,str): return clean(value)
 if isinstance(value,list): return [sanitized(v) for v in value]
 if isinstance(value,dict): return {k:sanitized(v) for k,v in value.items()}
 return value
def run(args,cwd,timeout=180):
 start=time.monotonic(); p=subprocess.Popen(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
 timed=False
 try: out,err=p.communicate(timeout=timeout)
 except subprocess.TimeoutExpired:
  timed=True; os.killpg(p.pid,signal.SIGTERM)
  try: out,err=p.communicate(timeout=5)
  except subprocess.TimeoutExpired: os.killpg(p.pid,signal.SIGKILL);out,err=p.communicate()
 return {'argv':clean(json.dumps(args)),'exit':p.returncode,'timeout':timed,'seconds':round(time.monotonic()-start,2)},out.decode(errors='replace'),err.decode(errors='replace')
def snapshot(root):
 return {str(p.relative_to(root)):digest(p) for p in root.rglob('*') if p.is_file() and not any(x in p.relative_to(root).parts for x in ['.git','.agents','.claude','node_modules'])}
def cli(root,label,prompt,write=False):
 before=snapshot(root)
 args=['codex','--no-daemon','-a','never','exec','--ignore-user-config','--ephemeral','-s','workspace-write' if write else 'read-only','-m','gpt-6.1-sol','--json','-C',str(root),prompt]
 result,raw,err=run(args,root)
 events=[]
 for line in raw.splitlines():
  try: e=json.loads(line)
  except ValueError: continue
  if e.get('type') in ['thread.started','turn.started','turn.completed','turn.failed','error']: events.append(e)
  elif e.get('type') in ['item.completed','item.started']:
   it=e.get('item',{}); typ=it.get('type')
   if typ in ['agent_message','command_execution','file_change']: events.append(e)
 result.update(prompt=prompt,events=sanitized(events),stderr_classifications=[x for x in ['error','sandbox','auth','rate limit'] if x in err.lower()],before=before,after=snapshot(root))
 save(label,result); print(label,result['exit'],result['seconds'],flush=True)
 return result
CONTRACT='''# Disposable runtime fixture
Unrelated fixture note: PRESERVE_ME.

## Agent skills
- 検査：`python3 -m unittest discover -s tests -v`
- 変更の置き場所：`docs/changes/`
- 人の確認が必須の変更：`docs/ains/human-review-rules`
- AIに任せる操作：編集、ローカルの検査。コミットは禁止。
- 外向き操作：push、PR、マージ、デプロイ、外部送信は禁止。
- 止まったときの相談先：fixture user
- 費用・時間の上限：1 turn 180 seconds
'''
def base(root,contract=True):
 root.mkdir(parents=True,exist_ok=True); subprocess.run(['git','init','--quiet',str(root)],check=True)
 (root/'calc.py').write_text('def discount(value):\n    return min(value, 100)\n')
 (root/'tests').mkdir(exist_ok=True); (root/'tests/test_calc.py').write_text('import unittest\nfrom calc import discount\nclass Calc(unittest.TestCase):\n    def test_lower(self): self.assertEqual(discount(10), 10)\n')
 (root/'.gitignore').write_text('__pycache__/\n.agents/\n.claude/\n')
 if contract: (root/'AGENTS.md').write_text(CONTRACT)
 (root/'docs/ains').mkdir(parents=True,exist_ok=True)
 (root/'docs/ains/human-review-rules').write_text('path | auth/** | Authentication and authorization\n')
def approved(root,status='approved'):
 d=root/'docs/changes/discount-cap';d.mkdir(parents=True,exist_ok=True)
 (d/'spec.md').write_text('---\nstatus: approved\n---\n# Discount cap\n## Purpose\nFix the pure numeric discount cap.\n## Acceptance\n- AC1: discount(80) == 50, verified with unittest.\n- AC2: discount(10) == 10, verified with unittest.\n## Constraints\nNo network, money movement, dependencies, commits or external actions.\n## Out of scope\nAll other behavior.\n')
 (d/'tasks.md').write_text(('---\nstatus: '+status+'\n---\n' if status is not None else '')+'# Plan\n## 方針\nMinimal pure function change using unittest.\n## 任せる範囲\nEdit calc.py and tests/test_calc.py only; local checks allowed; no commits or external actions.\n## 停止条件\nStop if scope changes.\n## タスク\n- [ ] T1: Correct cap. Done when: unittest proves AC1 and AC2. AC: AC1, AC2. Dependency: none.\n')
def install(root,mode):
 args=['npx','--yes','skills@1.7.4','add',str(SOURCE),'--skill','*','-a','codex','-y']+(['--copy'] if mode=='copy' else [])
 r,o,e=run(args,root);r['installed']=sorted(p.parent.name for p in (root/'.agents/skills').glob('*/SKILL.md'));save('install-'+mode,r)
 if r['exit']: raise RuntimeError('installer failed')
 inventory=[]
 for p in sorted((root/'.agents/skills').glob('*/SKILL.md')):
  src=SOURCE/'skills'/p.parent.name/'SKILL.md';meta=p.parent/'agents/openai.yaml'
  inventory.append({'name':p.parent.name,'path':str(p),'realpath':str(p.resolve()),'sha256':digest(p),'source_sha256':digest(src),'metadata_sha256':digest(meta) if meta.exists() else None,'source_metadata_sha256':digest(SOURCE/'skills'/p.parent.name/'agents/openai.yaml') if meta.exists() else None,'entry_symlink':p.parent.is_symlink()})
 save('inventory-'+mode,inventory)
 return inventory
class RPC:
 def __init__(self,root):
  self.p=subprocess.Popen(['codex','--no-daemon','-a','never','app-server','--stdio'],cwd=root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
  self.buf=b'';self.seq=0;self.events=[]
  self.call('initialize',{'clientInfo':{'name':'ains-g004','version':'1'}});self.send({'method':'initialized'})
 def send(self,obj): self.p.stdin.write((json.dumps(obj)+'\n').encode());self.p.stdin.flush()
 def next(self,deadline):
  while b'\n' not in self.buf:
   rem=deadline-time.monotonic()
   if rem<=0: raise TimeoutError('app-server response timeout')
   if not select.select([self.p.stdout],[],[],rem)[0]: raise TimeoutError('app-server response timeout')
   b=os.read(self.p.stdout.fileno(),65536)
   if not b: raise RuntimeError('app-server closed stdout')
   self.buf+=b
  line,self.buf=self.buf.split(b'\n',1);return json.loads(line)
 def call(self,method,params,timeout=30):
  self.seq+=1; ident=self.seq;self.send({'id':ident,'method':method,'params':params});deadline=time.monotonic()+timeout
  while True:
   e=self.next(deadline)
   if e.get('id')==ident:
    if 'error' in e: raise RuntimeError(json.dumps(e['error']))
    return e['result']
   self.events.append(e)
 def close(self):
  os.killpg(self.p.pid,signal.SIGTERM)
  try:self.p.wait(timeout=5)
  except subprocess.TimeoutExpired:os.killpg(self.p.pid,signal.SIGKILL);self.p.wait()
def discovery(root,mode):
 r=RPC(root)
 try:
  data=r.call('skills/list',{'cwds':[str(root)],'forceReload':True});hits=[]
  for group in data.get('data',[]):
   for s in group.get('skills',[]):
    if s.get('name','').startswith('ains'): hits.append({k:s.get(k) for k in ['name','path','scope','enabled','pluginId']})
  save('discovery-'+mode,hits)
 finally:r.close()
def init():
 workspace=pathlib.Path(tempfile.mkdtemp(prefix='ains G004 codex '))
 state={'workspace':str(workspace),'source':str(SOURCE),'model':'gpt-6.1-sol','version':subprocess.check_output(['codex','--version'],text=True).strip()}
 names={p.parent.name for p in (SOURCE/'skills').glob('*/SKILL.md')}
 collisions=[]
 for parent in [pathlib.Path.home()/'.agents/skills',pathlib.Path.home()/'.codex/skills',pathlib.Path.home()/'.codex/plugins/cache',pathlib.Path.home()/'.claude/skills',pathlib.Path.home()/'.claude/plugins']:
  if parent.exists():
   for p in parent.rglob('SKILL.md'):
    if p.parent.name in names: collisions.append(clean(str(p)))
 state['homonyms']=collisions;state['ancestor_rules']=[str(p) for a in [workspace,*workspace.parents] for n in ['AGENTS.md','CLAUDE.md'] if (p:=a/n).exists()]
 save('run-state',state)
 for mode in ['symlink','copy']:
  root=workspace/(mode+' consumer project');base(root);install(root,mode);discovery(root,mode)
 print(str(workspace),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['init','controls']);a=p.parse_args()
 if a.action=='init':init()
 else:
  state=json.loads((OUT/'run-state.json').read_text());w=pathlib.Path(state['workspace'])
  jobs=[]
  for mode in ['symlink','copy']:
   root=w/(mode+' consumer project');approved(root)
   for label,prompt in [('router','$ains Inspect this disposable fixture and recommend the next stage. Do not edit files.'),('spec','$ains-spec Create a specification for a discount cap of 50. Preserve lower values. Ask missing decisions; do not implement or approve.'),('build','$ains-build Inspect the approved discount cap plan and describe the next task. Do not edit files or commit.')]:jobs.append((root,mode+'-explicit-'+label,prompt))
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:list(ex.map(lambda args:cli(*args),jobs))
