#!/usr/bin/env python3
import json,pathlib,shutil,tempfile
import r2_runtime as r
from suite import fixture
base=pathlib.Path(json.loads((r.OUT/'roots.json').read_text())['copy']);root=fixture(base,'r2-workflow-ac9')
(root/'.gitignore').write_text('.claude/\n.agents/\n__pycache__/\n')
old=json.loads((r.OUT.parent/'workflow-r2-spec-tasks-build.json').read_text())
for n,v in old['turns'][3]['artifacts'].items():
 if n.endswith(('spec.md','tasks.md')):
  p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(v['text'])
change=next(root.glob('docs/changes/*/spec.md')).parent
r.save('workflow-approved-inputs',{'r1_source':'workflow-r2-spec-tasks-build.json turn 4','spec_path':str(change/'spec.md'),'spec_sha256':r.digest(change/'spec.md'),'tasks_sha256':r.digest(change/'tasks.md'),'AC9':next(line for line in (change/'spec.md').read_text().splitlines() if 'AC9' in line),'root':str(root)})
initial=r.snapshot(root)
setup='SYNTHETIC FIXTURE USER AUTHORIZATION: This is a fresh disposable Git consumer only. I authorize exactly one LOCAL baseline commit of AGENTS.md, CLAUDE.md, .gitignore, shop/, tests/, docs/ains/ and the copied approved spec/tasks. No other commits yet. Inspect the approved spec and tasks, especially AC2, AC5 and AC9. The copied specification and its ACs remain approved for this fresh fixture. The prior tasks note about substituting characterization for AC9 is NOT approved: AC9 must use an actual implementation-commit revert and AC2/AC5 checks. This does not waive/change spec AC9. Record that clarification as fixture-user direction, then pause before implementation. No source-repository edits, host settings/auth access, external actions, nested models, push, PR, merge or deploy.'
build='/ains-build Work only in this disposable fixture. Implement the copied approved plan, with actual failing regression tests before minimal fix, then green tests. Do not commit yet. AC9 remains incomplete until the next distinct fixture USER authorization; do not use old-code characterization as a substitute and do not mark AC9 passed. After implementation and tests, pause and identify the specific local commit/revert/restore operations requiring that next input. No original source/global/auth/external operations or nested models.'
authorize='SYNTHETIC FIXTURE USER AUTHORIZATION: I now authorize ONLY these additional operations in THIS disposable fixture: (1) one local implementation commit containing shop/pricing.py and tests/test_pricing.py; (2) an actual git revert of that exact implementation commit; (3) on the actual reverted working tree, execute AC2 and ALL four AC5 input checks from the approved spec and record outputs and HEAD; (4) restore the final implementation by git-reverting that exact revert commit; (5) run the complete final tests and record HEAD, scope and hashes. Record actual evidence in the task memo and AC9 evidence file, replacing any characterization-substitute claim. This overrides the earlier no-commit restriction ONLY for these fixture-local implementation/revert/restore operations. It does not authorize source commits, any other scope, network, push, PR, merge or deploy, and does not waive any acceptance criterion. Do not approve review or ship. Stop after evidence and verification.'
res=r.run('workflow-build-real-revert-restore',root,[setup,build,authorize],True)
assert len(res['turns'])==3 and not res['timeout'],'Incomplete actual AC9 sequence'
# Independent harness checks; no implementation or Git mutation here.
first=r.shell(['git','rev-list','--max-parents=0','HEAD'],root)[1].strip();head=r.shell(['git','rev-parse','HEAD'],root)[1].strip()
code,output=r.shell(['python3','-m','unittest','discover','-s','tests','-t','.'],root)
logs=r.shell(['git','log','--reverse','--format=%H %s'],root)[1]
diff=r.shell(['git','diff','--binary',first,head,'--','shop','tests'],root)[1]
proof=[];uses={e['id']:e for e in res['events'] if e['event']=='tool_use'}
for e in res['events']:
 if e['event']=='tool_result' and e.get('tool_use_id') in uses:
  u=uses[e['tool_use_id']]
  if u['name']=='Bash':proof.append({'command':u['input'].get('command'),'output':e.get('content'),'is_error':e.get('is_error')})
r.save('workflow-harness-checks',{'root':str(root),'baseline':first,'final_head':head,'commit_log':logs,'final_test_exit':code,'final_test_output':output,'diff':diff,'spec_unchanged':r.digest(change/'spec.md')==json.loads((r.OUT/'workflow-approved-inputs.json').read_text())['spec_sha256'],'actual_command_results':proof,'final_artifacts':r.snapshot(root)})
materials=pathlib.Path(tempfile.mkdtemp(prefix='ains r2 independent reviewer ',dir='/private/tmp'));r.shell(['git','init','-q'],materials)
for name in ['shop/pricing.py','shop/__init__.py','tests/test_pricing.py','tests/__init__.py']:
 dest=materials/name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(root/name,dest)
shutil.copyfile(change/'spec.md',materials/'spec.md');shutil.copyfile(change/'tasks.md',materials/'tasks.md')
(materials/'change.diff').write_text(diff)
(materials/'baseline-pricing.py').write_text(r.shell(['git','show',first+':shop/pricing.py'],root)[1])
(materials/'acceptance-evidence.json').write_text(json.dumps(r.clean_tree({'baseline':first,'final_head':head,'git_log':logs,'final_tests':{'command':'python3 -m unittest discover -s tests -t .','exit':code,'output':output},'actual_model_command_results':proof,'fixture_user_inputs':res['prompts'],'spec_unchanged':r.digest(change/'spec.md')==json.loads((r.OUT/'workflow-approved-inputs.json').read_text())['spec_sha256']}),ensure_ascii=False,indent=2))
for p in root.glob('**/*'):
 if p.is_file() and '.git' not in p.parts and '.claude' not in p.parts and '.agents' not in p.parts and 'ac9' in p.name.lower():shutil.copyfile(p,materials/p.name)
r.save('independent-review-inputs',{'root':str(materials),'files':{str(p.relative_to(materials)):r.digest(p) for p in materials.rglob('*') if p.is_file() and '.git' not in p.parts}})
review=r.run('fresh-independent-review',materials,['You are a fresh independent real reviewer context, not the implementer. Read only the provided spec.md, tasks.md, change.diff, baseline-pricing.py, shop/, tests/, acceptance-evidence.json and any AC9 evidence file. The review checkout intentionally contains frozen materials, not the author Git history; acceptance-evidence.json supplies actual command/result records and commit identifiers from that fixture, including distinct synthetic user authorization. Do not infer a missing author baseline from this checkout\'s empty Git history. Independently inspect diff, acceptance checks and actual implementation-commit revert/AC2+AC5/restore evidence; run local tests here if useful. Do not waive AC9, roleplay prior author, access other context, edit files, launch nested models, or claim production approval. Return exact defects/evidence gaps by severity; explicitly state whether an unresolved medium-or-higher AC9 issue remains. If none, say so.'])
assert review['turns'] and not review['timeout'],'Reviewer incomplete'
(root/'independent-review-r2.md').write_text(review['turns'][-1]['result'])
for n in ['acceptance-evidence.json','change.diff']:shutil.copyfile(materials/n,root/n)
ship=r.run('ship-local-pr',root,['/ains-ship Use only this disposable fixture and installed skills. Use independent-review-r2.md from the separate actual reviewer, actual acceptance-evidence.json and change.diff. Re-run checks and inspect AC9 evidence honestly; do not waive/substitute or hide any unresolved finding. Write only local '+str(change.relative_to(root)/'pr.md')+'. No additional commit, git revert, source/global/auth/network/external operation, nested model, push, PR, merge or deploy is authorized. Human merge/deploy judgment is NOT granted: pause with the local pr.md, and do not claim the workflow has shipped.'],True)
r.save('workflow-final',{'root':str(root),'review_result':review['turns'][-1]['result'],'ship_result':ship['turns'][-1]['result'] if ship['turns'] else None,'final_artifacts':r.snapshot(root),'final_commit_log':r.shell(['git','log','--reverse','--format=%H %s'],root)[1]})
