#!/usr/bin/env python3
"""Create a fresh public validation workspace from pinned Git objects."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

REPOSITORY = 'https://github.com/53able/next.js'
COMMIT = 'ec8ddcd7a52fb7b3508fa1cf467abc85dea3a0b8'
BASELINE = '3b2525c1f96609962dadf7e41dae3afea47faf97'
SOURCE_FILES = ['packages/next/src/shared/lib/htmlescape.ts', 'test/unit/htmlescape.test.ts', 'package.json', 'pnpm-lock.yaml', 'jest.config.js']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('workspace', type=Path)
    parser.add_argument('--baseline-ref', default=BASELINE)
    parser.add_argument('--image-source', action='store_true', help='Fetch all Next.js blobs and create rebuild tarball (large).')
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[2]
    root = args.workspace.resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    inputs = root/'input'
    checkout = root/'sample-checkout'
    subprocess.run(['git','clone','--depth','1','--filter=blob:none','--no-checkout',REPOSITORY,str(checkout)],check=True)
    subprocess.run(['git','-C',str(checkout),'fetch','--depth','1','origin',COMMIT],check=True)
    actual = subprocess.check_output(['git','-C',str(checkout),'rev-parse','FETCH_HEAD'],text=True).strip()
    if actual != COMMIT: raise RuntimeError('sample commit mismatch')
    hashes = {}
    for relative in SOURCE_FILES:
        data = subprocess.check_output(['git','-C',str(checkout),'show',COMMIT+':'+relative])
        target = inputs/'pinned'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
        hashes[relative] = hashlib.sha256(data).hexdigest()
    baseline = subprocess.check_output(['git','-C',str(project),'ls-tree','-r',args.baseline_ref,'skills'],text=True)
    for line in baseline.splitlines():
        metadata, relative = line.split('\t',1)
        mode, kind, _ = metadata.split()
        if kind != 'blob' or mode not in ('100644','100755'): raise RuntimeError('unsupported baseline entry')
        target = inputs/'baseline'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(subprocess.check_output(['git','-C',str(project),'show',args.baseline_ref+':'+relative]))
        target.chmod(0o755 if mode == '100755' else 0o644)
    shutil.copytree(project/'skills',inputs/'candidate/skills')
    (inputs/'source-provenance.json').write_text(json.dumps({'repository':REPOSITORY,'commit':COMMIT,'baselineSkillRef':args.baseline_ref,'sha256':hashes},indent=2)+'\n')
    shutil.copyfile(Path(__file__).with_name('container_case.py'),inputs/'container_case.py')
    shutil.copytree(inputs,root/'input-live-v4')
    if args.image_source:
        image = root/'image-rebuild'
        image.mkdir()
        archive = subprocess.Popen(['git','-C',str(checkout),'archive',COMMIT],stdout=subprocess.PIPE)
        with gzip.open(image/'nextjs.tar.gz','wb') as output:
            shutil.copyfileobj(archive.stdout,output)
        if archive.wait() != 0: raise RuntimeError('sample archive failed')
        shutil.copyfile(Path(__file__).with_name('Containerfile'),image/'Containerfile')
    subprocess.run(['python3',str(Path(__file__).with_name('prepare.py')),str(root),'--image','nextjs-document-baseline:20261108'],check=True)
    print(json.dumps({'workspace':str(root),'sampleCommit':COMMIT,'baselineSkillRef':args.baseline_ref}))


if __name__ == '__main__': main()
