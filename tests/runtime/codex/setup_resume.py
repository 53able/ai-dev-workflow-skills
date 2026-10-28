#!/usr/bin/env python3
from runtime import *
from workflow import Live,W
import shutil
r=W/'setup live absent consumer project';base(r,False);shutil.copytree(W/'copy consumer project/.agents',r/'.agents',symlinks=True)
live=Live(r,'setup-live')
try:
 live.turn('01-pause','$ains-setup Set up this disposable fixture. Discover existing checks. Ask for missing judgments and wait. Do not assume approval, commit or perform external actions. Use one plain-text question when the structured question tool is unavailable. Do not delegate.','ains-setup')
 live.turn('02-approval','SYNTHETIC FIXTURE USER-ROLE REPLY: I approve python3 -m unittest discover -s tests -v as the check, docs/changes/ as the change location, and preservation of the existing auth/** human-review rule. Use fixture user as contact. Allow local edits and local checks only; commits and all external actions are prohibited. No time/cost cap beyond the existing harness turn limit, no current-spec directory. Record these settings in this disposable project only. This is synthetic test consent, not production approval.')
 save('setup-live-final-artifacts',{n:(r/n).read_text() for n in ['AGENTS.md','CLAUDE.md','docs/ains/human-review-rules'] if (r/n).exists()})
finally:live.close()
