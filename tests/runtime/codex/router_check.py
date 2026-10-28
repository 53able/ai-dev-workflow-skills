#!/usr/bin/env python3
from runtime import *
import concurrent.futures
W=pathlib.Path(json.loads((OUT/'run-state.json').read_text())['workspace'])
def one(mode):
 root=W/(mode+' consumer project');p=root/'docs/changes/discount-cap/tasks.md';p.write_text(p.read_text().replace('T1 Correct cap.', 'T1: Correct cap.'))
 cli(root,mode+'-router-valid','$ains Inspect this disposable fixture and recommend the next stage from its actual state. Do not edit files, commit or perform external actions.')
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:list(ex.map(one,['symlink','copy']))
