#!/usr/bin/env python3
import difflib,json,pathlib,shutil
import runtime as r
from suite import fixture,SCOPE
base=pathlib.Path(json.loads((r.OUT/'roots.json').read_text())['copy'])
root=fixture(base,'workflow-r2')
(root/'.gitignore').write_text('.claude/\n.agents/\n__pycache__/\n')
initial=r.snapshot(root)
prompts=[
 '/ains-spec '+SCOPE+'SYNTHETIC FIXTURE USER AUTHORIZATION: Before spec work, make exactly one LOCAL baseline commit of AGENTS.md, CLAUDE.md, .gitignore, shop/, tests/, docs/ains/ only. This is the sole commit authorized; no further commits or external operations. Then create a draft specification for discount-cap: total_after_discount(100,120) must return 0, ordinary 100,20 remains 80, integers only. No taxes/API changes. For verification boundaries: zero subtotal (0,5) and equal subtotal/discount must return 0; negative subtotal/discount behavior must remain unchanged. Write all AC preconditions explicitly in the AC text and do not leave scope assumptions unanswered. Require a separate tasks.md planning stage for this fixture; omit inline spec tasks. Read the installed skill file for provenance, write draft and pause for user approval; do not implement.',
 'SYNTHETIC FIXTURE USER APPROVAL: I approve only the specification and its stated ACs/non-goals in this disposable fixture. Set spec status approved. Do not start implementation or approve a plan.',
 '/ains-tasks '+SCOPE+'Create the plan for the approved specification. Scope shop/pricing.py and tests/test_pricing.py only, no commits/external actions. Include Done when and AC links. Make red criterion at least one regression fails due to negative output, then all tests green; do not require exactly one failure. Keep behavioral tasks vertical. Write draft and pause for user approval.',
 'SYNTHETIC FIXTURE USER APPROVAL: I approve only the displayed tasks plan, method, sequence, and scope. Set tasks status approved. No implementation until the next user input.',
 '/ains-build '+SCOPE+'Implement the approved plan only. Read installed build and TDD procedures for provenance. Demonstrate actual red regression before the minimal green fix. No commits.'
]
res=r.run('workflow-r2-spec-tasks-build',root,prompts,True)
r.save('workflow-r2-root',{'root':str(root)})
assert len(res['turns'])==5 and not res['timeout'], 'Workflow checkpoint incomplete; do not run dependent review/ship'
# Only frozen review material is passed to a separate actual model context.
materials=pathlib.Path(__import__('tempfile').mkdtemp(prefix='ains independent reviewer ',dir='/private/tmp'))
r.shell(['git','init','-q'],materials)
current=r.snapshot(root);diff=''
for name in ['shop/pricing.py','tests/test_pricing.py']:
 diff+=''.join(difflib.unified_diff(initial[name]['text'].splitlines(True),current[name]['text'].splitlines(True),fromfile='a/'+name,tofile='b/'+name))
(materials/'change.diff').write_text(diff)
for p in root.glob('docs/changes/*/spec.md'):shutil.copyfile(p,materials/'spec.md')
for p in root.glob('docs/changes/*/tasks.md'):shutil.copyfile(p,materials/'tasks.md')
code,output=r.shell(['python3','-m','unittest','discover','-s','tests','-t','.'],root)
toolmap={e['id']:e for e in res['events'] if e['event']=='tool_use'}
proof=[]
for e in res['events']:
 if e['event']=='tool_result' and e.get('tool_use_id') in toolmap:
  t=toolmap[e['tool_use_id']]
  if t['name']=='Bash' and 'unittest' in t['input'].get('command',''):proof.append({'command':t['input']['command'],'output':e['content']})
(materials/'test-results.txt').write_text(json.dumps({'fresh_exit':code,'fresh_output':output,'observed_runtime_tests':proof},ensure_ascii=False,indent=2))
(materials/'fixture-user-approvals.txt').write_text('\n\n'.join(t['user_input'] for t in res['turns']))
for name in ['shop/pricing.py','tests/test_pricing.py']:
 dest=materials/name;dest.parent.mkdir(exist_ok=True);dest.write_text(current[name]['text'])
r.save('review-r2-inputs',{'root':str(materials),'files':{str(p.relative_to(materials)):r.digest(p) for p in materials.rglob('*') if p.is_file() and '.git' not in p.parts},'test_exit':code})
review=r.run('independent-review-r2',materials,['You are a separate real reviewer session. Review only change.diff, spec.md, tasks.md, test-results.txt, shop/pricing.py, tests/test_pricing.py. fixture-user-approvals.txt contains the actual synthetic user inputs after observed pauses; use it to assess approval evidence. Read only; no edits, no other context or delegation. Identify concrete defects, missing acceptance evidence, or scope drift. Return severity and exact locations; if none, state no findings. Do not infer production approval.'])
review_text=review['turns'][-1]['result'] if review['turns'] else 'INCOMPLETE reviewer timed out'
(root/'independent-review.md').write_text(review_text)
for n in ['change.diff','test-results.txt','fixture-user-approvals.txt']:shutil.copyfile(materials/n,root/n)
r.run('workflow-r2-ship',root,['/ains-ship '+SCOPE+'Use independent-review.md, change.diff, test-results.txt and fixture-user-approvals.txt from a separate actual reviewer session, verify tests and acceptance evidence. Read the installed ship procedure for provenance. Produce only local docs/changes/<change>/pr.md, no external actions. Human merge/deploy judgment is not granted: pause with the local artifact.'],True)
r.save('workflow-r2-final-artifacts',r.snapshot(root))
