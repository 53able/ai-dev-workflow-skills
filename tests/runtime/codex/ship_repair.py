#!/usr/bin/env python3
"""Fresh fixture baseline authorized by parent user; no source commits or remotes."""
from runtime import *
from workflow import Live,W
import difflib
r=W/'ship repair consumer project';base(r)
(r/'.gitignore').write_text('__pycache__/\n.agents/\n.claude/\nskills-lock.json\npackage-lock.json\n')
# Parent's explicit user-role authorization covers this baseline fixture setup only.
args=['git','add','--','calc.py','tests/test_calc.py','AGENTS.md','.gitignore','docs/ains/human-review-rules']
meta,stdout,stderr=run(args,r,15);assert meta['exit']==0
args=['git','-c','user.name=Synthetic Fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','commit','--quiet','-m','Disposable fixture baseline']
meta,stdout,stderr=run(args,r,15);assert meta['exit']==0
baseline=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()
subprocess.run(['git','branch','fixture-baseline',baseline],cwd=r,check=True)
save('ship-repair-baseline',{'authorization':'Parent user explicitly authorized local baseline fixture creation and commit, before approved build. Runtime agent commits remain prohibited.','command':meta,'baseline':baseline,'baseline_files':subprocess.check_output(['git','ls-tree','-r','--name-only',baseline],cwd=r,text=True).splitlines(),'remotes':subprocess.check_output(['git','remote'],cwd=r,text=True).splitlines()})
args=['npx','--yes','skills@1.7.4','add',str(SOURCE),'--skill','*','-a','codex','-y','--copy']
meta,stdout,stderr=run(args,r);assert meta['exit']==0
save('ship-repair-install',{'command':meta,'skills':[{'name':p.parent.name,'path':str(p),'realpath':str(p.resolve()),'sha256':digest(p),'source_sha256':digest(SOURCE/'skills'/p.parent.name/'SKILL.md')} for p in sorted((r/'.agents/skills').glob('*/SKILL.md'))]})
approved(r,'draft');d=r/'docs/changes/discount-cap'
# The cap-50 spec scope is unchanged from earlier observed approval, but ask fresh plan approval.
(d/'spec.md').write_text((d/'spec.md').read_text().replace('status: approved','status: draft'))
live=Live(r,'ship-repair')
try:
 live.turn('01-review','$ains-spec Review the supplied draft spec.md and tasks.md for the exact same cap-50 fixture scope: discount(80)=50 and discount(10)=10. Present them for my approval and stop; I have not approved these new fixture documents yet. No code edits, commits, external actions or delegation. Baseline fixture-baseline exists only to evaluate the local diff.','ains-spec')
 live.turn('02-spec-approval','SYNTHETIC FIXTURE USER-ROLE: I approve the specification as presented for this disposable cap-50 fixture only. Record spec approval; leave the plan draft and do not implement. This is test input, not production consent.')
 live.turn('03-plan-review','$ains-tasks Review the separate draft plan for the now approved specification. Present the plan and pause for approval. Do not implement, commit, perform external actions or delegate.','ains-tasks')
 live.turn('04-plan-approval','SYNTHETIC FIXTURE USER-ROLE: I approve the presented plan for cap 50, local edits and unittest checks only. Record tasks.md approval and stop before implementation. Runtime commits and external actions remain prohibited; the pre-existing fixture baseline was separately authorized by the parent user.')
 live.turn('05-build','$ains-build Implement only the approved cap-50 plan. Run a real failing regression test before production changes, then the minimal fix and passing tests. Baseline: fixture-baseline. Do not commit, stage changes, perform external actions or delegate.','ains-build')
 diff=subprocess.check_output(['git','diff','--no-ext-diff','--no-textconv',baseline,'--','calc.py','tests/test_calc.py'],cwd=r,text=True)
 save('ship-repair-actual-diff',{'baseline':baseline,'diff':diff,'sha256':hashlib.sha256(diff.encode()).hexdigest()})
 reviewer=W/'ship repair independent reviewer project';reviewer.mkdir();subprocess.run(['git','init','--quiet',str(reviewer)],check=True)
 (reviewer/'diff.patch').write_text(diff);(reviewer/'spec.md').write_text((d/'spec.md').read_text());(reviewer/'tests.py').write_text((r/'tests/test_calc.py').read_text())
 meta,stdout,stderr=run(['python3','-m','unittest','discover','-s','tests','-v'],r,30);assert meta['exit']==0
 (reviewer/'checks.txt').write_text(clean(stdout+stderr))
 (reviewer/'review-prompt.md').write_text((r/'.agents/skills/ains-review/review-prompt.md').read_text())
 save('ship-repair-review-inputs',{p.name:digest(p) for p in reviewer.iterdir() if p.is_file()})
 rev=cli(reviewer,'ship-repair-independent-review','In this separate real reviewer context, follow review-prompt.md. Review actual diff.patch against spec.md, tests.py and checks.txt. Report concrete findings or none and gaps. Do not edit, delegate, commit or perform external actions.')
 (d/'independent-review.md').write_text('\n\n'.join(e['item']['text'] for e in rev['events'] if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message'))
 live.turn('06-ship','$ains-ship Prepare the local pr.md. The actual independent reviewer result is docs/changes/discount-cap/independent-review.md; read it and preserve gaps. Run all available checks and the installed route-review.sh with explicit base-ref fixture-baseline (the real pre-build baseline). Evaluate risk. No commits, push, PR, merge, deployment, external actions or delegation. Pause for any remaining human judgment.','ains-ship')
 save('ship-repair-artifacts',{str(p.relative_to(r)):p.read_text() for p in d.iterdir() if p.is_file()})
 meta,stdout,stderr=run([str(r/'.agents/skills/ains-review-gate/scripts/route-review.sh'),'docs/ains/human-review-rules','fixture-baseline'],r,30)
 save('ship-repair-final-gate',{'command':meta,'output':clean(stdout+stderr),'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),'baseline':baseline,'remotes':subprocess.check_output(['git','remote'],cwd=r,text=True).splitlines()})
finally:live.close()
