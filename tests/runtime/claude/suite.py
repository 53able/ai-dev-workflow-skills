#!/usr/bin/env python3
import concurrent.futures,difflib,json,os,pathlib,shutil,sys
import runtime as r
SCOPE='This is a disposable local Git consumer test fixture. Work only in this fixture and installed .claude/skills references. No network, global settings, auth access, delegation, edits to the original distribution source repository outside this fixture, commits, push, PR, merge or deploy. Fixture user approvals are synthetic test inputs, not production consent. '
SECTION='''## Agent skills

- 検査：`python3 -m unittest discover -s tests -t .`
- 変更の置き場所：`docs/changes/`
- 人の確認が必須の変更：`docs/ains/human-review-rules`
- AIに任せる操作：編集、ローカル検査のみ。コミットは禁止
- 外向き操作：禁止。push、PR、merge、deploy は行わない
- 止まったときの相談先：fixture user
- 次に何をするか迷ったら Claude Code では `/ains`、Codex では `$ains`
'''
def fixture(base,name,contract=True,bug=True):
 root=pathlib.Path(__import__('tempfile').mkdtemp(prefix=base.name+' '+name+' ',dir='/private/tmp'))
 r.shell(['git','init','-q'],root)
 # Install tree already copied by pinned installer; preserve symlink mode entries.
 shutil.copytree(base/'.claude',root/'.claude',symlinks=True)
 if (base/'.agents').exists():shutil.copytree(base/'.agents',root/'.agents',symlinks=True)
 if contract:(root/'AGENTS.md').write_text('# Fixture rules\n\n'+SECTION);(root/'CLAUDE.md').write_text('@AGENTS.md\n')
 if bug:
  (root/'shop').mkdir();(root/'shop/__init__.py').write_text('');(root/'shop/pricing.py').write_text('def total_after_discount(subtotal, discount):\n    return subtotal - discount\n')
  (root/'tests').mkdir();(root/'tests/__init__.py').write_text('');(root/'tests/test_pricing.py').write_text('import unittest\nfrom shop.pricing import total_after_discount\n\nclass PricingTests(unittest.TestCase):\n    def test_normal_discount(self):\n        self.assertEqual(total_after_discount(100, 20), 80)\n')
  (root/'docs/ains').mkdir(parents=True);(root/'docs/ains/human-review-rules').write_text('auth/**\nbilling/**\nmigrations/**\n.github/**\n')
 return root
SPEC='''---
status: approved
---
# Discount cap
## Goal
Discount may not make a total negative. Integer inputs only.
## Acceptance criteria
- AC1: total_after_discount(100, 120) returns 0; verify unittest regression.
- AC2: total_after_discount(100, 20) remains 80; verify existing unittest.
## Out of scope
No tax, network, dependencies, interface changes, commits or external actions.
## 未決事項
None.
'''
TASK='''---
status: approved
---
# Tasks
## 方針
Clamp subtraction at zero; standard library unittest.
## 任せる範囲
Only shop/pricing.py, tests/test_pricing.py and task checkboxes. No commit or external actions.
## 停止条件
Any scope change.
## タスク
- [ ] T1 discount cap. Done when: regression test reproduced red before fix and all tests pass. AC: AC1, AC2. 依存: なし.
## メモ
'''
def plan(root,status='approved'):
 d=root/'docs/changes/discount-cap';d.mkdir(parents=True,exist_ok=True);(d/'spec.md').write_text(SPEC)
 text=TASK if status=='approved' else TASK.replace('status: approved\n','' if status=='missing' else 'status: '+status+'\n');(d/'tasks.md').write_text(text)

def controls(base,mode):
 root=fixture(base,'router');r.run('router-'+mode+'-granted',root,['/ains '+SCOPE+'Inspect current state, run installed status script and recommend next stage. Do not edit.'])
 root=fixture(base,'explicit-spec');r.run('explicit-spec-'+mode,root,['/ains-spec '+SCOPE+'Create a specification for discount cap behavior. Ask missing decisions before approving. Do not implement.'],True)
 root=fixture(base,'explicit-build');plan(root);r.run('explicit-build-'+mode,root,['/ains-build '+SCOPE+'Implement only the approved discount cap plan with test-first evidence.'],True)
 root=fixture(base,'unnamed-spec');r.run('unnamed-spec-'+mode,root,[SCOPE+'Create a specification for the requested discount cap behavior; ask about missing decisions before approving it. Do not implement.'],True)
 root=fixture(base,'unnamed-build');plan(root);r.run('unnamed-build-'+mode,root,[SCOPE+'Implement the approved discount cap plan and verify it.'],True)
 root=fixture(base,'automatic-tdd');r.run('automatic-tdd-'+mode,root,[SCOPE+'Fix the bug where total_after_discount(100,120) yields -20 instead of zero. Write and run a reproducing failing regression test before the minimal fix, preserve ordinary discounts, then run the tests.'],True)

def setups(base):
 for name in (sys.argv[2:] or ['absent','agents-only','claude-only','duplicate','conflict','samefile','symlink','existing-import']):
  root=fixture(base,'setup-'+name,False)
  agents='# AGENTS unrelated sentinel\n\n'+SECTION+'\n## Keep\nAGENTS tail sentinel\n';claude='# CLAUDE unrelated sentinel\n\n'+SECTION+'\n## Keep\nCLAUDE tail sentinel\n'
  if name in ('agents-only','duplicate','conflict','samefile','symlink','existing-import'):(root/'AGENTS.md').write_text(agents)
  if name in ('claude-only','duplicate','conflict'):(root/'CLAUDE.md').write_text(claude.replace('`docs/changes/`','`other/changes/`') if name=='conflict' else claude)
  if name=='samefile':os.link(root/'AGENTS.md',root/'CLAUDE.md')
  if name=='symlink':(root/'CLAUDE.md').symlink_to('AGENTS.md')
  if name=='existing-import':(root/'CLAUDE.md').write_text('# CLAUDE unrelated sentinel\n\n@AGENTS.md\n')
  initial=r.snapshot(root)
  prompt='/ains-setup '+SCOPE+'Inspect and perform setup migration only. Preserve unrelated text. Existing values are not new approvals. For absent settings, first show missing judgments and wait. For conflicting settings, ask which value and wait without overwriting.'
  if name=='absent':prompts=[prompt,'SYNTHETIC FIXTURE USER REPLY: Use python3 -m unittest discover -s tests -t .; docs/changes/; proposed human review rules for auth, billing, migrations, CI. Approve these setup settings only. Editing/local tests allowed; no commits or external actions. Please write setup.']
  elif name=='conflict':prompts=[prompt]
  else:prompts=[prompt,'/ains-setup '+SCOPE+'Repeat the same setup. Keep identical existing approved settings. Do not duplicate or rewrite unchanged content.']
  result=r.run('setup-'+name,root,prompts,True)
  r.save('setup-'+name+'-artifacts',{'before':initial,'after':r.snapshot(root),'samefile':(root/'CLAUDE.md').exists() and os.path.samefile(root/'AGENTS.md',root/'CLAUDE.md') if (root/'AGENTS.md').exists() else False,'claude_symlink':(root/'CLAUDE.md').is_symlink()})

def negatives(base):
 for status in ['draft','missing','malformed']:
  root=fixture(base,'negative-'+status);plan(root,status);before=r.snapshot(root)
  result=r.run('negative-build-'+status,root,['/ains-build '+SCOPE+'Continue the discount cap task.'],True)
  r.save('negative-build-'+status+'-assertions',{'before':before,'after':r.snapshot(root),'unchanged':before==r.snapshot(root),'git_head':r.shell(['git','rev-parse','--verify','HEAD'],root)[0]})
 root=fixture(base,'scope-change');plan(root)
 r.run('scope-change',root,['/ains-spec '+SCOPE+'Change the previously approved discount-cap scope: discounts greater than subtotal must raise ValueError rather than return zero. Update specification to draft, invalidate plan approval, and ask for approval before any implementation.'],True)

if __name__=='__main__':
 bases=json.loads((r.OUT/'roots.json').read_text());symlink=pathlib.Path(bases['symlink'])
 if 'copy' not in bases:bases['copy']=str(r.install('copy'));r.save('roots',bases)
 task=sys.argv[1] if len(sys.argv)>1 else 'controls'
 if task=='controls':
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda z:controls(pathlib.Path(z[1]),z[0]),bases.items()))
 elif task=='setup':setups(symlink)
 elif task=='negative':negatives(symlink)
