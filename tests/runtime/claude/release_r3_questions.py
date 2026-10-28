#!/usr/bin/env python3
import concurrent.futures,json,pathlib,shutil
import r3_runtime as r
from suite import fixture
base=pathlib.Path(json.loads((r.OUT/'roots.json').read_text())['copy']);R2=r.OUT.parent/'release-r2'
def setup():
 old=json.loads((R2/'setup-absent-same-input.json').read_text());root=fixture(base,'r3-question-setup',False)
 r.save('question-setup-fixture',{'original_run':'release-r2/setup-absent-same-input.json','original_first_input':old['prompts'][0],'initial_artifacts':r.snapshot(root)})
 r.run('question-setup',root,[old['prompts'][0]],True,reply_file=r.OUT/'question-setup-reply.json')
def spec():
 old=json.loads((R2/'spec-original-save-io.json').read_text());root=fixture(base,'r3-question-spec',False,False)
 src=r.SOURCE/'tests/evals/ains-spec/new-feature-stops-at-spec-gate/files';shutil.copytree(src,root,dirs_exist_ok=True)
 # Materialize the same app/rules after scaffold, without running setup.sh or creating a new commit.
 (root/'setup.sh').unlink();(root/'.gitignore').write_text('.claude/\n.agents/\n__pycache__/\n')
 r.save('question-spec-fixture',{'original_run':'release-r2/spec-original-save-io.json','original_business_input':old['prompts'][1],'initial_artifacts':r.snapshot(root),'scaffold_commit':'not replayed; no new fixture commits authorized/needed for focused question check','fixture_source_hashes':{str(p.relative_to(src)):r.digest(p) for p in src.rglob('*') if p.is_file()}})
 r.run('question-spec',root,[old['prompts'][1]],True,reply_file=r.OUT/'question-spec-reply.json')
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as p:
 fs=[p.submit(setup),p.submit(spec)]
 for f in fs:f.result()
