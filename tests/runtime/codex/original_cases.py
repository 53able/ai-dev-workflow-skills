#!/usr/bin/env python3
"""Replay all five migrated eval fixtures through real installed Codex CLI."""
from runtime import *
from workflow import W
import concurrent.futures
CASES=[('ains-spec','new-feature-stops-at-spec-gate'),('ains-build','bugfix-reproduces-first-and-stays-in-scope'),('ains-build','build-stops-when-plan-is-draft'),('ains-build','build-stops-when-plan-has-no-status'),('ains-review-gate','merge-request-with-migration-goes-to-human')]
def one(pair):
 skill,name=pair;src=SOURCE/'tests/evals'/skill/name;r=W/('original '+name+' consumer project');r.mkdir()
 # Parent USER explicitly requested these original local scaffold scripts; they only run here.
 meta,o,e=run(['bash',str(src/'place-files.sh')],r,30);assert meta['exit']==0
 main=subprocess.check_output(['git','rev-parse','main'],cwd=r,text=True).strip()
 if skill=='ains-review-gate':subprocess.run(['git','checkout','--quiet','feature/cleanup'],cwd=r,check=True)
 with (r/'.gitignore').open('a') as f:f.write('\n.agents/\n.claude/\nskills-lock.json\npackage-lock.json\n__pycache__/\n')
 args=['npx','--yes','skills@1.7.4','add',str(SOURCE),'--skill','*','-a','codex','-y','--copy'];install_meta,o,e=run(args,r);assert install_meta['exit']==0
 prompt=(src/'prompt.md').read_text().split('---',2)[2].strip()
 prompt=prompt.replace('/ains-spec','$ains-spec').replace('/ains-build','$ains-build')
 # Review-gate is an automatic discipline; retain the original unnamed merge request.
 prompt+='\n\nこの実行は使い捨てfixtureの実テストです。コミット、push、PR作成、デプロイ、外部送信は禁止です。スキル本文をプロンプトに貼っていません。'
 initial=snapshot(r)
 record=cli(r,'original-'+name,prompt,True)
 final={str(p.relative_to(r)):p.read_text() for p in r.rglob('*.md') if '.agents' not in p.parts and '.git' not in p.parts}
 extra={}
 if skill=='ains-review-gate':
  gate,o,e=run([str(r/'.agents/skills/ains-review-gate/scripts/route-review.sh'),'docs/ains/human-review-rules','main'],r,30)
  extra={'gate':gate,'gate_output':clean(o+e)}
 if name=='bugfix-reproduces-first-and-stays-in-scope':
  check,o,e=run(['python3','-m','unittest','discover','-s','tests','-t','.'],r,30)
  behavior,bout,berr=run(['python3','-c','from shop.pricing import apply_discount; assert apply_discount(1000,150)==0;\ntry: apply_discount(1000,-5)\nexcept ValueError: print("negative raises ValueError")\nelse: raise AssertionError("negative accepted")'],r,30)
  extra={'fresh_tests':check,'fresh_test_output':clean(o+e),'behavior_check':behavior,'behavior_output':clean(bout+berr),'pricing_diff':subprocess.check_output(['git','diff','main','--','shop/pricing.py'],cwd=r,text=True)}
 save('original-'+name+'-artifacts',{'source_case':str(src.relative_to(SOURCE)),'source_fixture_sha256':{str(p.relative_to(src)):digest(p) for p in src.rglob('*') if p.is_file()},'scaffold':meta,'install':install_meta,'main_before':main,'main_after':subprocess.check_output(['git','rev-parse','main'],cwd=r,text=True).strip(),'head_before':main if skill!='ains-review-gate' else subprocess.check_output(['git','rev-parse','feature/cleanup'],cwd=r,text=True).strip(),'head_after':subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),'prompt_adaptations':['Codex literal dollar stage syntax','no runtime commits/external actions']+(['checkout prepared feature/cleanup before invocation so installed gate sees actual main diff'] if skill=='ains-review-gate' else []),'initial':initial,'final_artifacts':final,**extra})
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:list(ex.map(one,CASES))
