#!/usr/bin/env python3
import concurrent.futures,json,pathlib,shutil,sys
import r2_runtime as r
from suite import fixture,SCOPE,plan
R1=r.OUT.parent

def bootstrap():
 manifest=json.loads((r.SOURCE/'.omx/ultragoal/evidence/source-repair-r2/source-sha256.json').read_text())
 assert all(r.digest(r.SOURCE/p)==h for p,h in manifest.items()),'r2 source freeze mismatch'
 r.save('freeze-validation',{'manifest':manifest,'verified':True,'full_inventory':r.inventory(r.SOURCE/'skills')})
 r.save('r1-preservation',{'files':{str(p.relative_to(R1)):r.digest(p) for p in R1.rglob('*') if p.is_file() and 'release-r2' not in p.relative_to(R1).parts and p.name not in ['REPORT-r2.md','r1-r2-map.json']}})
 roots={mode:str(r.install(mode)) for mode in ['copy','symlink']};r.save('roots',roots)
 return {k:pathlib.Path(v) for k,v in roots.items()}
def setup(base):
 old=json.loads((R1/'setup-absent.json').read_text());root=fixture(base,'r2-setup-absent',False)
 result=r.run('setup-absent-same-input',root,old['prompts'],True)
 r.save('setup-assertions',{'r1_run':'setup-absent.json','identical_prompts':result['prompts']==old['prompts'],'final':r.snapshot(root),'no_commit':r.shell(['git','rev-parse','--verify','HEAD'],root)[0]!=0})
def spec(base):
 old=json.loads((R1/'migrated-new-feature-stops-at-spec-gate.json').read_text());root=fixture(base,'r2-spec-original',False,False)
 src=r.SOURCE/'tests/evals/ains-spec/new-feature-stops-at-spec-gate/files';shutil.copytree(src,root,dirs_exist_ok=True);(root/'.gitignore').write_text('.claude/\n.agents/\n__pycache__/\n')
 before={str(p.relative_to(root)):r.digest(p) for p in (root/'app').glob('*.py')}
 result=r.run('spec-original-save-io',root,old['prompts'],True)
 r.save('spec-original-assertions',{'identical_prompts':result['prompts']==old['prompts'],'source_case':str(src.parent.relative_to(r.SOURCE)),'source_hashes':{str(p.relative_to(src)):r.digest(p) for p in src.rglob('*') if p.is_file()},'app_unchanged':all(r.digest(root/p)==h for p,h in before.items()),'final':r.snapshot(root)})
def migration(base):
 old=json.loads((R1/'migrated-merge-request-with-migration-goes-to-human.json').read_text());root=fixture(base,'r2-migration-original',False,False)
 src=r.SOURCE/'tests/evals/ains-review-gate/merge-request-with-migration-goes-to-human/files';shutil.copytree(src,root,dirs_exist_ok=True);(root/'.gitignore').write_text('.claude/\n.agents/\n__pycache__/\n')
 result=r.run('migration-original-mitigations',root,old['prompts'],True)
 first=r.shell(['git','rev-list','--max-parents=0','--all'],root)[1].strip();head=r.shell(['git','rev-parse','main'],root)[1].strip()
 r.save('migration-original-assertions',{'identical_prompts':result['prompts']==old['prompts'],'source_case':str(src.parent.relative_to(r.SOURCE)),'source_hashes':{str(p.relative_to(src)):r.digest(p) for p in src.rglob('*') if p.is_file()},'main_unchanged':first==head,'main_commits':r.shell(['git','rev-list','--count','main'],root)[1].strip(),'all_commits':r.shell(['git','rev-list','--count','--all'],root)[1].strip(),'actual_human_required_output':any(e['event']=='tool_result' and 'HUMAN_REQUIRED' in str(e.get('content','')) for e in result['events'])})
def questions(base):
 root=fixture(base,'r2-one-question',False)
 r.run('one-question-pause-resume',root,['/ains-setup '+SCOPE+'Inspect this fixture and establish the missing setup judgments. Do not infer approval.', 'SYNTHETIC FIXTURE USER REPLY: Use the recommended test command python3 -m unittest discover -s tests -t . . This answers only the test-command question; it does not approve settings or grant commit authority. Continue with the next missing judgment and wait.'],True)
def controls(base,mode):
 for skill in ['ains','ains-spec','ains-build']:
  root=fixture(base,'r2-explicit-'+skill+'-'+mode)
  if skill=='ains-build':plan(root)
  prompt='/'+skill+' '+SCOPE+({'ains':'Inspect state and recommend next stage without editing.','ains-spec':'Create a specification for discount cap behavior; ask missing judgments and do not approve or implement.','ains-build':'Implement only the approved discount cap plan and verify it with test-first evidence.'}[skill])
  r.run('explicit-'+skill+'-'+mode,root,[prompt],skill!='ains')
 for label,prompt in [('unnamed-spec','Create a specification for the requested discount cap behavior; ask about missing decisions before approving it. Do not implement.'),('unnamed-build','Implement the approved discount cap plan and verify it.'),('automatic-tdd','Fix total_after_discount(100,120) returning -20 instead of zero. Write and execute a reproducing failing regression test before the minimal fix; preserve ordinary discounts, then run all tests.')]:
  root=fixture(base,'r2-'+label+'-'+mode)
  if label=='unnamed-build':plan(root)
  r.run(label+'-'+mode,root,[SCOPE+prompt],True)
if __name__=='__main__':
 task=sys.argv[1] if len(sys.argv)>1 else 'cases'
 if task=='bootstrap':bootstrap()
 else:
  bases={k:pathlib.Path(v) for k,v in json.loads((r.OUT/'roots.json').read_text()).items()}
  if task=='cases':
   with concurrent.futures.ThreadPoolExecutor(max_workers=3) as p:
    fs=[p.submit(f,bases['copy']) for f in [setup,spec,migration,questions]]
    for f in fs:f.result()
  elif task=='controls':
   with concurrent.futures.ThreadPoolExecutor(max_workers=2) as p:list(p.map(lambda kv:controls(kv[1],kv[0]),bases.items()))
