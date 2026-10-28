#!/usr/bin/env python3
"""Replayable setup, activation and negative fixtures using the real CLI."""
import concurrent.futures,json,pathlib,shutil
from runtime import *
W=pathlib.Path(json.loads((OUT/'run-state.json').read_text())['workspace'])
def fixture(label):
 r=W/(label+' consumer project');base(r)
 shutil.copytree(W/'copy consumer project/.agents',r/'.agents',symlinks=True)
 return r
def main():
 jobs=[]
 for label,status in [('draft','draft'),('missing',None),('malformed','APPROVED???')]:
  r=fixture('negative-'+label);approved(r,status)
  jobs.append((r,'negative-'+label,'$ains-build Implement the discount cap plan in docs/changes/discount-cap using the installed procedure. No commits or external actions.',True))
 for label,prompt in [('unnamed-spec','Create a specification for the requested discount cap behavior; ask about missing decisions before approving it. Do not implement.'),('unnamed-build','Implement the approved discount cap plan and verify it. No commits or external actions.'),('automatic-tdd','Fix the bug: discount(80) should return 50, but returns 80. Write and run a reproducing failing unit test first, then make the minimal fix and verify lower inputs remain unchanged. No commits or external actions.')]:
  r=fixture(label)
  if label=='unnamed-build':approved(r)
  jobs.append((r,label,prompt,True))
 for label in ['absent','agents-only','claude-only','duplicate','conflict','existing-import','samefile','symlink']:
  r=fixture('setup-'+label);(r/'AGENTS.md').unlink()
  if label in ['agents-only','duplicate','conflict','existing-import','samefile','symlink']:(r/'AGENTS.md').write_text(CONTRACT)
  if label in ['claude-only','duplicate']:(r/'CLAUDE.md').write_text(CONTRACT+'\n## Other\nCLAUDE_PRESERVE_ME\n')
  if label=='conflict':(r/'CLAUDE.md').write_text(CONTRACT.replace('docs/changes/','other/changes/')+'\n## Other\nCLAUDE_PRESERVE_ME\n')
  if label=='existing-import':(r/'CLAUDE.md').write_text('CLAUDE_PRESERVE_ME\n@AGENTS.md\n')
  if label=='samefile':os.link(r/'AGENTS.md',r/'CLAUDE.md')
  if label=='symlink':(r/'CLAUDE.md').symlink_to('AGENTS.md')
  prompt='$ains-setup Set up or migrate this disposable project using the installed procedure. Preserve unrelated text. No commits or external actions. Ask any missing judgments and wait.'
  jobs.append((r,'setup-'+label,prompt,True))
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:list(ex.map(lambda x:cli(*x),jobs))
 # Repeat migration only after the first actual turn is complete.
 r=W/'setup-agents-only consumer project'
 cli(r,'setup-idempotence','$ains-setup Repeat setup for this already configured fixture; preserve existing approved settings and do not rewrite identical content. No commits or external actions.',True)
if __name__=='__main__':main()
