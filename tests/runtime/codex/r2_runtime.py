#!/usr/bin/env python3
"""R2 runtime lane, separate artifacts, real installed suite and model sessions."""
import concurrent.futures,json,os,pathlib,select,shutil,signal,subprocess,tempfile,time,hashlib
import runtime as rt
import activation_recheck as ar
SOURCE=rt.SOURCE;OUT=rt.OUT/'r2';OUT.mkdir(exist_ok=True)
FREEZE=json.loads((SOURCE/'.omx/ultragoal/evidence/source-repair-r2/source-sha256.json').read_text())
def freeze():assert all(rt.digest(SOURCE/k)==v for k,v in FREEZE.items()),'r2 released hashes differ'
def save(n,v):ar.write(OUT/(n+'.json'),v)
def install(root,label,copy=True):
 freeze();args=['npx','--yes','skills@1.7.4','add',str(SOURCE),'--skill','*','-a','codex','-y']+(['--copy'] if copy else [])
 start=time.monotonic();p=subprocess.run(args,cwd=root,stdin=subprocess.DEVNULL,capture_output=True,timeout=180);assert p.returncode==0,'Pinned installer failed'
 inv=[]
 for f in sorted((root/'.agents/skills').glob('*/SKILL.md')):
  src=SOURCE/'skills'/f.parent.name/'SKILL.md';meta=f.parent/'agents/openai.yaml';sm=src.parent/'agents/openai.yaml'
  inv.append({'name':f.parent.name,'path':str(f),'realpath':str(f.resolve()),'sha256':rt.digest(f),'source_sha256':rt.digest(src),'metadata_sha256':rt.digest(meta) if meta.exists() else None,'source_metadata_sha256':rt.digest(sm) if sm.exists() else None})
 assert len(inv)==len(list((SOURCE/'skills').glob('*/SKILL.md'))) and all(x['sha256']==x['source_sha256'] and x['metadata_sha256']==x['source_metadata_sha256'] for x in inv)
 save(label+'-install',{'argv':args,'exit':p.returncode,'seconds':round(time.monotonic()-start,2),'inventory':inv,'freeze':FREEZE})
 return inv
class Live(rt.RPC):
 def __init__(self,root,label):
  # Live JSONRPC input uses a pipe intentionally; CLI controls use DEVNULL.
  super().__init__(root);self.root=root;self.label=label
  self.thread=self.call('thread/start',{'cwd':str(root),'model':'gpt-6.1-sol','approvalPolicy':'never','sandbox':'workspace-write','ephemeral':True})['thread']['id']
  save(label+'-session',{'threadId':self.thread,'ephemeral':True,'transport':'app-server stdio','stdin':'JSONRPC pipe; user inputs explicitly recorded per turn','note':'App-server has no --ignore-user-config; supported live fallback. CLI activation controls are separate.'})
 def turn(self,label,text):
  freeze();before=rt.snapshot(self.root);inputs=[{'type':'text','text':text}];start=time.monotonic();events=[]
  result={'role':'user','input':inputs,'threadId':self.thread,'before':before,'label':label}
  try:
   self.events=[];self.call('turn/start',{'threadId':self.thread,'input':inputs},timeout=30);events.extend(self.events);deadline=start+180
   while True:
    e=self.next(deadline);events.append(e)
    if 'id' in e and 'method' in e:result['pending_request']=e;break
    if e.get('method')=='turn/completed':result['completed']=e.get('params',{}).get('turn',{}).get('status');break
  except Exception as e:result['error']=str(e)
  result.update(seconds=round(time.monotonic()-start,2),events=events,after=rt.snapshot(self.root))
  save(self.label+'-'+label,result);print(self.label,label,result.get('completed',result.get('error','pending')),result['seconds'],flush=True);return result
 def text(self,result):
  return '\n'.join(e.get('params',{}).get('item',{}).get('text','') for e in result['events'] if e.get('method')=='item/completed' and e.get('params',{}).get('item',{}).get('type')=='agentMessage')
def state():
 p=OUT/'run-state.json'
 if p.exists():return pathlib.Path(json.loads(p.read_text())['workspace'])
 freeze();w=pathlib.Path(tempfile.mkdtemp(prefix='ains Codex r2 runtime '));save('run-state',{'workspace':str(w),'freeze':FREEZE,'version':subprocess.check_output(['codex','--version'],text=True).strip(),'model':'gpt-6.1-sol'});return w
def cli(root,label,prompt):
 ar.collect(root,label,prompt,OUT,[])
 rec=json.loads((OUT/(label+'.json')).read_text());print(label,rec['exit'],rec['seconds'],flush=True);return rec
def original_cases():
 w=state()
 for skill,name in [('ains-spec','new-feature-stops-at-spec-gate'),('ains-review-gate','merge-request-with-migration-goes-to-human')]:
  src=SOURCE/'tests/evals'/skill/name;r=w/('original '+name+' consumer project');r.mkdir();p=subprocess.run(['bash',str(src/'place-files.sh')],cwd=r,stdin=subprocess.DEVNULL,capture_output=True,timeout=30);assert p.returncode==0
  before_main=subprocess.check_output(['git','rev-parse','main'],cwd=r,text=True).strip()
  if skill=='ains-review-gate':subprocess.run(['git','checkout','--quiet','feature/cleanup'],cwd=r,check=True)
  with (r/'.gitignore').open('a') as f:f.write('\n.agents/\n.claude/\nskills-lock.json\n__pycache__/\n')
  install(r,name)
  prompt=(src/'prompt.md').read_text().split('---',2)[2].strip().replace('/ains-spec','$ains-spec')
  prompt+='\n\n使い捨てfixtureのテストです。コミット、push、PR作成、デプロイ、外部送信は禁止です。'
  rec=cli(r,'original-'+name,prompt)
  save('original-'+name+'-artifacts',{'source_case':str(src.relative_to(SOURCE)),'main_before':before_main,'main_after':subprocess.check_output(['git','rev-parse','main'],cwd=r,text=True).strip(),'final_artifacts':{str(p.relative_to(r)):p.read_text() for p in r.rglob('*.md') if '.agents' not in p.parts and '.git' not in p.parts}})
  if skill=='ains-review-gate':
   p=subprocess.run([str(r/'.agents/skills/ains-review-gate/scripts/route-review.sh'),'docs/ains/human-review-rules','main'],cwd=r,stdin=subprocess.DEVNULL,capture_output=True,timeout=30)
   save('migration-gate',{'exit':p.returncode,'output':(p.stdout+p.stderr).decode(errors='replace')})
def setup():
 w=state();r=w/'absent setup consumer project';rt.base(r,False);install(r,'setup-absent')
 live=Live(r,'setup-absent')
 try:
  for i in range(1,7):
   text='$ains-setup Set up this disposable project. Inspect existing checks, ask missing judgments and wait using plain text if needed. Only local edits and local checks are authorized; commits and all external actions are prohibited. Do not delegate.' if i==1 else 'SYNTHETIC FIXTURE USER-ROLE REPLY: I accept the recommended answer to the single question you just asked, only for this disposable project. I continue to authorize local edits and local checks only; do not grant or perform commits or external operations. If another judgment is missing, ask only that next question and wait.'
   result=live.turn('%02d'%i,text)
   if (r/'AGENTS.md').exists() and (r/'CLAUDE.md').exists():break
   if result.get('error') or result.get('pending_request'):break
  save('setup-final-artifacts',{n:(r/n).read_text() for n in ['AGENTS.md','CLAUDE.md','docs/ains/human-review-rules'] if (r/n).exists()})
 finally:live.close()
def workflow():
 w=state();r=w/'approved workflow consumer project';rt.base(r)
 (r/'.gitignore').write_text('__pycache__/\n.agents/\n.claude/\nskills-lock.json\n')
 subprocess.run(['git','add','--','calc.py','tests/test_calc.py','AGENTS.md','.gitignore','docs/ains/human-review-rules'],cwd=r,check=True)
 p=subprocess.run(['git','-c','user.name=Synthetic Fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','commit','--quiet','-m','Disposable baseline'],cwd=r,stdin=subprocess.DEVNULL,capture_output=True);assert p.returncode==0
 baseline=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip();subprocess.run(['git','branch','fixture-baseline',baseline],cwd=r,check=True)
 save('workflow-baseline',{'authorization':'Parent USER explicitly authorized local fixture baseline/test commits, no source commits','baseline':baseline,'files':subprocess.check_output(['git','ls-tree','-r','--name-only',baseline],cwd=r,text=True).splitlines()})
 install(r,'workflow');live=Live(r,'workflow')
 try:
  live.turn('01-spec-draft','$ains-spec Draft a tiny pure-function bugfix specification: discount caps at 50 instead of 100. Exact required AC1: discount(80)=50; AC2: discount(10)=10; AC3: discount(50)=50. Preserve other behavior. No storage, deployments, network, dependencies, commits or external actions. Use separate tasks.md even though small. I have not approved it; present the draft and pause. Do not delegate.')
  specs=list((r/'docs/changes').glob('*/spec.md'))
  if not specs:save('workflow-blocker',{'reason':'No spec artifact after draft turn'});return
  d=specs[0].parent;save('workflow-draft-artifacts',{str(p.relative_to(r)):p.read_text() for p in d.iterdir() if p.is_file()})
  live.turn('02-spec-approval','SYNTHETIC FIXTURE USER-ROLE: I approve the presented specification for this disposable cap-50 fixture only, including its actual acceptance criteria. Record spec approval, leave planning approval separate, and do not implement yet. If the specification added any unsupported business decision, stop and explain instead of treating it as approved production work.')
  live.turn('03-plan-draft','$ains-tasks Create or review the separate plan from the approved spec. Include all approved ACs and Done when, including plan completion bookkeeping. Only local implementation/tests and document tracking are allowed. Commits and external operations remain prohibited. Present and pause before approval; do not implement or delegate.')
  live.turn('04-plan-approval','SYNTHETIC FIXTURE USER-ROLE: I approve the presented same-scope implementation plan and its completion bookkeeping for this disposable fixture. Record tasks approval and stop before implementation. No commits or external actions.')
  live.turn('05-build','$ains-build Implement the approved plan, reproducing failure with actual tests before production edits, then minimal fix and actual passing tests. Verify every approved AC and mark tasks complete with evidence. No scope expansion, commits, staging, external actions or delegation.')
  save('workflow-pre-review-artifacts',{str(p.relative_to(r)):p.read_text() for p in d.iterdir() if p.is_file()})
  review=w/'separate real reviewer consumer project';review.mkdir();subprocess.run(['git','init','--quiet',str(review)],check=True)
  diff=subprocess.check_output(['git','diff','--no-ext-diff','--no-textconv',baseline,'--','calc.py','tests/test_calc.py'],cwd=r,text=True)
  (review/'diff.patch').write_text(diff);(review/'spec.md').write_text(specs[0].read_text());(review/'calc.py').write_text((r/'calc.py').read_text());(review/'tests').mkdir();(review/'tests/test_calc.py').write_text((r/'tests/test_calc.py').read_text());(review/'review-prompt.md').write_text((r/'.agents/skills/ains-review/review-prompt.md').read_text())
  p=subprocess.run(['python3','-B','-m','unittest','discover','-s','tests','-v'],cwd=r,capture_output=True,stdin=subprocess.DEVNULL,timeout=30);(review/'checks.txt').write_text((p.stdout+p.stderr).decode(errors='replace'))
  save('review-inputs',{str(p.relative_to(review)):rt.digest(p) for p in review.rglob('*') if p.is_file() and '.git' not in p.parts})
  rec=cli(review,'independent-review','Follow review-prompt.md. Independently review diff.patch against spec.md, surrounding code calc.py and actual tests. Run python3 -B -m unittest discover -s tests -v to independently verify the supplied check results. Report findings and remaining gaps. No author conversation is provided. No edits, commits, external actions or delegation.')
  messages=[e['item']['text'] for e in rec['events'] if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message'];(d/'independent-review.md').write_text('\n\n'.join(messages))
  live.turn('06-ship','$ains-ship Read the actual separate independent-review.md, run all existing checks and route-review.sh docs/ains/human-review-rules fixture-baseline, verify every actual approved AC against tests, and create local pr.md. Preserve any unverified evidence. No new reviewer delegation, commits, staging, push, PR, merge, deploy or external actions. Pause for remaining human judgment.')
  save('workflow-ship-artifacts',{str(p.relative_to(r)):p.read_text() for p in d.iterdir() if p.is_file()})
  live.turn('07-scope-change','$ains-spec The cap requirement changes to 40, not yet approved. Invalidate both old approvals before any implementation. Draft the changed spec/plan and pause; keep implementation and tests unchanged, and do not commit or delegate.')
  save('workflow-scope-artifacts',{str(p.relative_to(r)):p.read_text() for p in d.iterdir() if p.is_file()})
  save('workflow-final-git',{'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),'baseline':baseline,'remotes':subprocess.check_output(['git','remote'],cwd=r,text=True).splitlines()})
 finally:live.close()
if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('action',choices=['originals','setup','workflow']);a=ap.parse_args();{'originals':original_cases,'setup':setup,'workflow':workflow}[a.action]()
