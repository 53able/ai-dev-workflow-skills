#!/usr/bin/env python3
import difflib,json,pathlib,shutil
import runtime as r
from suite import fixture,SCOPE
base=pathlib.Path(json.loads((r.OUT/'roots.json').read_text())['copy'])
root=fixture(base,'workflow')
initial=r.snapshot(root)
prompts=[
 '/ains-spec '+SCOPE+'Create a draft specification for discount-cap: total_after_discount(100,120) must return 0, ordinary 100,20 remains 80, integers only. No taxes/API changes. Require a separate tasks.md planning stage for this fixture; omit inline spec tasks. Read the installed skill file for provenance, write draft and pause for user approval; do not implement.',
 'SYNTHETIC FIXTURE USER APPROVAL: I approve only the specification and its stated ACs/non-goals in this disposable fixture. Set spec status approved. Do not start implementation or approve a plan.',
 '/ains-tasks '+SCOPE+'Create the plan for the approved specification. Scope shop/pricing.py and tests/test_pricing.py only, no commits/external actions. Include Done when and AC links. Write draft and pause for user approval.',
 'SYNTHETIC FIXTURE USER APPROVAL: I approve only the displayed tasks plan, method, sequence, and scope. Set tasks status approved. No implementation until the next user input.',
 '/ains-build '+SCOPE+'Implement the approved plan only. Read installed build and TDD procedures for provenance. Demonstrate actual red regression before the minimal green fix. No commits.'
]
res=r.run('workflow-spec-tasks-build',root,prompts,True)
r.save('workflow-root',{'root':str(root)})
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
(materials/'test-results.txt').write_text(output)
for name in ['shop/pricing.py','tests/test_pricing.py']:
 dest=materials/name;dest.parent.mkdir(exist_ok=True);dest.write_text(current[name]['text'])
r.save('review-inputs',{'root':str(materials),'files':{str(p.relative_to(materials)):r.digest(p) for p in materials.rglob('*') if p.is_file() and '.git' not in p.parts},'test_exit':code})
review=r.run('independent-review',materials,['You are a separate real reviewer session. Review only change.diff, spec.md, tasks.md, test-results.txt, shop/pricing.py, tests/test_pricing.py. Read only; no edits, no other context or delegation. Identify concrete defects, missing acceptance evidence, or scope drift. Return severity and exact locations; if none, state no findings. Do not infer production approval.'])
review_text=review['turns'][-1]['result'] if review['turns'] else 'INCOMPLETE reviewer timed out'
(root/'independent-review.md').write_text(review_text)
r.run('workflow-ship',root,['/ains-ship '+SCOPE+'Use independent-review.md from a separate actual reviewer session, verify tests and acceptance evidence. Read the installed ship procedure for provenance. Produce only local docs/changes/<change>/pr.md, no external actions. Human merge/deploy judgment is not granted: pause with the local artifact.'],True)
r.save('workflow-final-artifacts',r.snapshot(root))
