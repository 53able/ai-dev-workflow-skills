#!/usr/bin/env python3
"""Live ephemeral app-server conversation: distinct fixture user turns."""
import json,pathlib,shutil,time
from runtime import *
class Live(RPC):
 def __init__(self,root,label):
  super().__init__(root);self.root=root;self.label=label
  self.thread=self.call('thread/start',{'cwd':str(root),'model':'gpt-6.1-sol','approvalPolicy':'never','sandbox':'workspace-write','ephemeral':True})['thread']['id']
  save(label+'-session',{'threadId':self.thread,'ephemeral':True,'transport':'app-server stdio','note':'App-server has no --ignore-user-config option; explicit model/sandbox/approvalPolicy set per thread. Existing host auth, no config mutations.'})
 def turn(self,label,text,skill=None):
  before=snapshot(self.root);inputs=[{'type':'text','text':text}]
  if skill:inputs.append({'type':'skill','name':skill,'path':str(self.root/'.agents/skills'/skill/'SKILL.md')})
  start=time.monotonic();self.events=[];events=[]
  result={'label':label,'role':'user','input':inputs,'before':before,'threadId':self.thread}
  try:
   res=self.call('turn/start',{'threadId':self.thread,'input':inputs},timeout=30);deadline=start+180
   while True:
    e=self.next(deadline);method=e.get('method','')
    if 'id' in e and method:
     # Structured questions receive no fabricated answers; report and stop.
     result['pending_request']={'id':e['id'],'method':method,'params':e.get('params')};break
    if method in ['item/completed','turn/completed','error','turn/started']:events.append(e)
    if method=='turn/completed':result['completed']=e.get('params',{}).get('turn',{}).get('status');break
  except Exception as e:result['error']=str(e)
  result.update(seconds=round(time.monotonic()-start,2),events=sanitized(events),after=snapshot(self.root))
  save(self.label+'-'+label,result);print(self.label,label,result.get('completed',result.get('error','pending question')),result['seconds'],flush=True)
  return result
W=pathlib.Path(json.loads((OUT/'run-state.json').read_text())['workspace'])
def main():
 r=W/'workflow consumer project';base(r);shutil.copytree(W/'copy consumer project/.agents',r/'.agents',symlinks=True)
 live=Live(r,'workflow')
 try:
  live.turn('01-spec-draft','$ains-spec Create the specification for a tiny pure function bugfix: discount(value) must cap at 50 instead of 100, preserving inputs below 50. AC1 discount(80)=50; AC2 discount(10)=10; AC3 discount(50)=50. Use unittest. No dependencies, network, commits or external actions. Use a separate tasks.md even though small so the planning checkpoint can be tested. Draft only; I have not approved this specification. Pause for approval with a plain-text question if structured questions are unavailable. Do not delegate.', 'ains-spec')
  specs=list((r/'docs/changes').glob('*/spec.md'))
  if not specs:save('workflow-blocker',{'reason':'No spec artifact after draft turn'});return
  d=specs[0].parent
  save('workflow-draft-artifact',{'path':str(specs[0]),'content':specs[0].read_text(),'sha256':digest(specs[0])})
  live.turn('02-spec-approval','SYNTHETIC FIXTURE USER-ROLE REPLY, scoped only to this disposable consumer: I approve the specification just presented, with exactly the cap-50 scope and AC1–AC3. Record its approval. Do not implement yet. This is test input, not production consent.')
  live.turn('03-tasks-draft','$ains-tasks Create the separate implementation plan for the approved specification. Include AC-linked tasks and Done when. Local edits and local checks only; commits and external actions prohibited. I have not approved the plan yet; pause for my review. Do not delegate.','ains-tasks')
  live.turn('04-plan-approval','SYNTHETIC FIXTURE USER-ROLE REPLY: I approve this displayed plan and its scoped local edits/checks. No commits, external actions or scope expansion. Record tasks.md approval and stop before implementation. This approves only this disposable fixture plan.')
  live.turn('05-build','$ains-build Implement only the approved cap-50 task, with actual failing test execution before the minimal production edit and passing tests afterward. No commits, external actions or delegation.','ains-build')
  save('workflow-final-artifacts',{str(p.relative_to(r)):p.read_text() for p in r.rglob('*') if p.is_file() and p.suffix in ['.py','.md'] and not any(x in p.relative_to(r).parts for x in ['.agents','.git'])})
  # A separate real CLI/model session sees only copied spec/tests and diff, not author conversation.
  reviewer=W/'independent reviewer project';reviewer.mkdir();subprocess.run(['git','init','--quiet',str(reviewer)],check=True)
  (reviewer/'spec.md').write_text(specs[0].read_text())
  (reviewer/'tests.py').write_text((r/'tests/test_calc.py').read_text())
  import difflib
  diff=''.join(difflib.unified_diff(['def discount(value):\n','    return min(value, 100)\n'],(r/'calc.py').read_text().splitlines(True),fromfile='a/calc.py',tofile='b/calc.py'))
  (reviewer/'diff.patch').write_text(diff)
  rr,stdout,stderr=run(['python3','-m','unittest','discover','-s','tests','-v'],r,30)
  (reviewer/'checks.txt').write_text(clean(stdout+stderr))
  rev=cli(reviewer,'workflow-independent-review','Review only diff.patch against spec.md and tests.py with checks.txt. This is an independent real reviewer context. Report concrete findings or explicitly none, and gaps. Do not edit files, run external actions, or delegate.')
  messages=[e['item']['text'] for e in rev['events'] if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
  (d/'independent-review.md').write_text('\n\n'.join(messages))
  live.turn('06-ship','$ains-ship Prepare local pr.md for the completed fixture change. The separate reviewer result is independent-review.md in the change directory; read it and preserve any gaps. Re-run required local checks and review-gate. No recursive review/delegation, commits, push, PR, merge, deployment or external actions. Stop for any required human judgment.','ains-ship')
  save('workflow-ship-artifacts',{str(p.relative_to(r)):p.read_text() for p in d.glob('*') if p.is_file()})
  live.turn('07-scope-change','$ains-spec Change the requirement: the cap should now be 40, with discount(80)=40. This is a new request, not approval. Invalidate the old specification and plan approvals before any implementation. Draft the changed specification and pause; do not change implementation, commit or delegate.','ains-spec')
  save('workflow-scope-change-artifacts',{str(p.relative_to(r)):p.read_text() for p in d.glob('*') if p.is_file()})
 finally:live.close()
if __name__=='__main__':main()
