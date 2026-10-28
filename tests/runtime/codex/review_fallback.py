#!/usr/bin/env python3
"""Real reviewer-unavailable graceful stop by explicit fixture capability constraint."""
from runtime import *
from workflow import W
import shutil
r=W/'review unavailable consumer project';r.mkdir();subprocess.run(['git','init','--quiet',str(r)],check=True)
shutil.copytree(W/'copy consumer project/.agents',r/'.agents',symlinks=True)
for n in ['diff.patch','spec.md','tests.py','checks.txt']:(r/n).write_text((W/'ship repair independent reviewer project'/n).read_text())
cli(r,'review-unavailable','$ains-review Review this supplied change using spec.md, diff.patch, tests.py and checks.txt. Fixture capability constraint: independent reviewer execution is unavailable for this run; you may not spawn agents, launch another model/CLI/API session, or pretend to be a separate reviewer. Prepare a concrete handoff and explicitly report independent review incomplete; stop before claiming review passed or advancing ship. Local handoff writing is allowed. No commits or external actions.',True)
save('review-unavailable-artifacts',{str(p.relative_to(r)):p.read_text() for p in r.rglob('*.md') if '.agents' not in p.parts and '.git' not in p.parts})
