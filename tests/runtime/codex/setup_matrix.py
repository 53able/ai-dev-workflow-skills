#!/usr/bin/env python3
"""Setup matrix with valid existing rules. Failed first probe retained separately."""
from cases import fixture,W
from runtime import *
import concurrent.futures

def one(label):
 r=fixture('setup-valid-'+label);(r/'AGENTS.md').unlink()
 if label in ['agents-only','duplicate','conflict','existing-import','samefile','symlink']:(r/'AGENTS.md').write_text(CONTRACT)
 if label in ['claude-only','duplicate']:(r/'CLAUDE.md').write_text(CONTRACT+'\n## Other\nCLAUDE_PRESERVE_ME\n')
 if label=='conflict':(r/'CLAUDE.md').write_text(CONTRACT.replace('docs/changes/','other/changes/')+'\n## Other\nCLAUDE_PRESERVE_ME\n')
 if label=='existing-import':(r/'CLAUDE.md').write_text('CLAUDE_PRESERVE_ME\n@AGENTS.md\n')
 if label=='samefile':os.link(r/'AGENTS.md',r/'CLAUDE.md')
 if label=='symlink':(r/'CLAUDE.md').symlink_to('AGENTS.md')
 cli(r,'setup-valid-'+label,'$ains-setup Set up or migrate this disposable project using the installed procedure. Preserve unrelated text and existing settings. No commits or external actions. Ask missing judgments and wait.',True)
 save('setup-valid-'+label+'-artifacts',{n: {'content':(r/n).read_text(),'symlink':(r/n).is_symlink(),'inode':(r/n).stat().st_ino} for n in ['AGENTS.md','CLAUDE.md'] if (r/n).exists()})
 if label=='agents-only':cli(r,'setup-valid-idempotence','$ains-setup Repeat setup for this configured fixture. Preserve approved values and do not rewrite identical content. No commits or external actions.',True)
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:list(ex.map(one,['absent','agents-only','claude-only','duplicate','conflict','existing-import','samefile','symlink']))
