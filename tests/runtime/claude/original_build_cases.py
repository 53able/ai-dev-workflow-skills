#!/usr/bin/env python3
import concurrent.futures,json,pathlib,shutil,sys
import runtime as r
from suite import fixture
base=pathlib.Path(json.loads((r.OUT/'roots.json').read_text())['copy'])
names=sys.argv[1:] or ['bugfix-reproduces-first-and-stays-in-scope','build-stops-when-plan-is-draft','build-stops-when-plan-has-no-status']
def replay(name):
 root=fixture(base,'original-'+name,False,False);src=r.SOURCE/'tests/evals/ains-build'/name/'files';shutil.copytree(src,root,dirs_exist_ok=True)
 (root/'.gitignore').write_text('.claude/\n.agents/\n__pycache__/\n')
 source_hashes={str(p.relative_to(src)):r.digest(p) for p in src.rglob('*') if p.is_file()}
 prompt=(src.parent/'prompt.md').read_text().split('---',2)[-1].strip()
 setup='SYNTHETIC FIXTURE USER AUTHORIZATION: This disposable Git consumer contains the exact migrated eval fixture plus the installed suite. I authorize exactly its local setup.sh baseline initialization/commit. Run bash setup.sh once, then pause. No implementation, additional commits, network, push, PR, merge, deploy, auth/global configuration access, original source-repository edits, or nested models. Report baseline HEAD.'
 prompt+='\nSYNTHETIC FIXTURE USER SCOPE: Work only in this disposable consumer and installed references; never change the original distribution source or host settings/auth. No external operations, push, PR, merge, deploy or nested model sessions. '
 if name.startswith('bugfix'):prompt+='I explicitly authorize local task commits only within the existing approved fixture tasks scope.'
 else:prompt+='The setup authorization was only for the baseline commit; no plan approval or further commit authority is supplied by this message.'
 r.save('original-'+name+'-source',{'source_case':str(src.parent.relative_to(r.SOURCE)),'source_hashes':source_hashes,'original_prompt_sha256':r.digest(src.parent/'prompt.md')})
 d=r.run('original-'+name,root,[setup,prompt],True)
 spec=root/'docs/changes/2026-10-20-discount-clamp/spec.md';tasks=root/'docs/changes/2026-10-20-discount-clamp/tasks.md'
 first=r.shell(['git','rev-list','--max-parents=0','HEAD'],root)[1].strip();count=r.shell(['git','rev-list','--count','--all'],root)[1].strip()
 code,out=r.shell(['python3','-m','unittest','discover','-s','tests','-t','.'],root)
 result={'source_case':str(src.parent.relative_to(r.SOURCE)),'root':str(root),'tests_exit':code,'tests_output':out,'spec_unchanged':r.digest(spec)==source_hashes[str(spec.relative_to(root))],'tasks':tasks.read_text(),'commit_count':count,'shop_tests_diff_from_baseline':r.shell(['git','diff',first,'--','shop','tests'],root)[1],'git_status_shop_tests':r.shell(['git','status','--porcelain','--','shop','tests'],root)[1]}
 if name.startswith('bugfix'):
  c,o=r.shell(['python3','-c','from shop.pricing import apply_discount; assert apply_discount(1000,150)==0\ntry: apply_discount(1000,-5)\nexcept ValueError: pass\nelse: raise AssertionError("negative rate not rejected")'],root);result['exact_behavior_exit']=c
 r.save('original-'+name+'-assertions',r.clean_tree(result))
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as p:list(p.map(replay,names))
