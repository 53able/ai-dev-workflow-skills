#!/usr/bin/env python3
"""Native-v1 preparation and bounded turn adapter. Default is model-free.

--prepare creates a fresh recipe/templates only; no install, Git, or model.
--run executes ONE reviewed recipe row after a separate parent release. Live
rows accept real USER JSON lines on stdin, one after each completed turn. The
adapter never invents answers/approvals and never runs a legacy recipe/main.
"""
import argparse
import ast
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import types
import copy
import tomllib
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

SOURCE = Path(__file__).resolve().parents[3]
EVIDENCE = SOURCE / '.omx/ultragoal/evidence/g004/codex/native-v1'
RELEASE = SOURCE / '.omx/ultragoal/evidence/source-repair-r5/manifest.json'
MANUAL = {'ains','ains-build','ains-harness','ains-retro','ains-setup','ains-ship',
          'ains-spec','ains-tasks','ains-team-canvas','ains-tool-access'}
AUTO = {'ains-context-care','ains-grilling','ains-release-safety','ains-review','ains-review-gate','ains-tdd'}
HELPERS = ['runtime','activation_recheck','activation_closure_probe','activation_r3']
CASES = [('ains-spec','new-feature-stops-at-spec-gate'),
         ('ains-build','bugfix-reproduces-first-and-stays-in-scope'),
         ('ains-build','build-stops-when-plan-is-draft'),
         ('ains-build','build-stops-when-plan-has-no-status'),
         ('ains-review-gate','merge-request-with-migration-goes-to-human')]
NEGATIVE_SPEC = 'Create a specification for the requested discount cap behavior; ask about missing decisions before approving it. Do not implement.'
NEGATIVE_BUILD = 'Implement the approved discount cap plan and verify it.'
TDD = 'Fix the bug: discount(80) should return 50 but returns 80. Write and run a failing regression test before the minimal fix; preserve lower inputs.'
SETUP = '$ains-setup Set up or migrate this disposable project using the installed procedure. Preserve unrelated text and existing settings.'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


@contextlib.contextmanager
def bound_helpers(sink):
    """Rebind only runtime's OUT assignment BEFORE its import-time mkdir.

    All function bodies are the real current helper bytes. No legacy main is
    called. The other helpers import that exact rebound module. The source AST
    and the one replaced assignment are recorded; old sys.modules are restored.
    """
    sink = Path(sink).resolve()
    old = {name: sys.modules.get(name) for name in HELPERS}
    modules = {}; receipt = []
    try:
        for name in HELPERS:
            path = SOURCE / 'tests/runtime/codex' / (name + '.py')
            tree = ast.parse(path.read_text(), str(path))
            rewrites = 0
            for node in tree.body:
                if name == 'runtime' and isinstance(node, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == 'OUT' for t in node.targets):
                    node.value = ast.Call(ast.Attribute(ast.Name('pathlib', ast.Load()),
                        'Path', ast.Load()), [ast.Constant(str(sink))], [])
                    rewrites += 1
                # No module-level expression may launch a process or call a main.
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                    if ast.unparse(node.value.func) != 'OUT.mkdir':
                        raise RuntimeError('Unreviewed import expression: ' + str(path))
            if name == 'runtime' and rewrites != 1:
                raise RuntimeError('Expected exactly one runtime OUT assignment')
            module = types.ModuleType(name); module.__file__ = str(path)
            sys.modules[name] = module
            exec(compile(ast.fix_missing_locations(tree), str(path), 'exec'), module.__dict__)
            modules[name] = module
            receipt.append({'path': str(path.relative_to(SOURCE)), 'sha256': sha(path),
                            'OUT_assignment_rebound': bool(rewrites),
                            'function_bodies_changed': False})
        assert modules['runtime'].OUT == sink
        assert modules['activation_recheck'].OUT == sink
        assert modules['activation_r3'].rt.OUT == sink
        yield modules, receipt
    finally:
        for name, previous in old.items():
            if previous is None: sys.modules.pop(name, None)
            else: sys.modules[name] = previous


def released_source(manifest=RELEASE):
    data = json.loads(Path(manifest).read_text())
    if not isinstance(data.get('release'),str) or not data['release']: raise RuntimeError('Missing source release')
    for path, digest in data['suite_skill_metadata_sha256'].items():
        if sha(SOURCE / path) != digest: raise RuntimeError('Released source drift: ' + path)
    expected={p:v for p,v in data['suite_files'].items() if len(Path(p).parts)>1 and Path(p).parts[1] in MANUAL|AUTO}
    actual={str(p.relative_to(SOURCE)) for name in MANUAL|AUTO for p in (SOURCE/'skills'/name).rglob('*') if p.is_file()}
    if actual!=set(expected):raise RuntimeError('Released skill resource inventory drift')
    for path,receipt in expected.items():
        file=SOURCE/path
        if sha(file)!=receipt['sha256'] or oct(file.stat().st_mode & 0o777)!=receipt['mode']:raise RuntimeError('Released resource/hash/mode drift: '+path)
    return data


def original_prompt(skill, case):
    text = (SOURCE / 'tests/evals' / skill / case / 'prompt.md').read_text()
    return text.split('---', 2)[2].strip().replace('/ains-spec', '$ains-spec').replace('/ains-build', '$ains-build')


AUDIT = SOURCE/'.omx/ultragoal/evidence/codex-0164-native-binding'
SEMANTIC_COMMIT = '6aaac694803004a63c6f393d153c96d22521a6b9'
CANONICAL_FEATURES = ('hooks','plugins','remote_plugin','apps','memories','external_agent_memory_import','token_budget','goals','agent_message_board','multi_agent_v2','guardian_approval')
DISCOVERY_KEYS = ('executor_capability_discovery','executor_capability_discovery_v2','skip_host_skill_discovery')


RECEIPT_VERSION = 'codex-poststart-v3'
DEFAULT_SOURCE_PROOFS = (
    ('codex-rs__core__src__config__mod.rs','b9786bf33ed36546b100578ce26f6884033c404d11c72ed1e234c1b519605c04',4173,4177),
    ('codex-rs__features__src__lib.rs','53c99aa1176c0f4f8763cbf960f11eb574f63fb33214f2bcd3bf699ebb361337',1681,1698))
THREAD_FIELDS = ('model','modelProvider','serviceTier','reasoningEffort','cwd',
                 'runtimeWorkspaceRoots','instructionSources','approvalPolicy',
                 'approvalsReviewer','sandbox','activePermissionProfile',
                 'disabledPluginIds','multiAgentMode')


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def redacted_config(value, key=''):
    """Redact credential containers BEFORE hashing; auth stability is excluded.

    Unknown nonsecret values remain in the identity. Environment literals and
    arbitrary headers are unclassified and excluded rather than secret-digested.
    """
    if re.search(r'(?i)(secret|password|credential|api[_-]?key|authorization|(?:^|_)token$|^auth$)',key) or key.lower() in ('env','environment','headers','http_headers'):
        # Feature names containing token are booleans, not credential values.
        if isinstance(value,bool) or value is None:return value
        return {'redacted':True,'type':type(value).__name__}
    if isinstance(value,dict):return {k:redacted_config(v,k) for k,v in value.items()}
    if isinstance(value,list):
        result=[];redact_next=False
        for item in value:
            if redact_next:
                result.append('<REDACTED>');redact_next=False;continue
            result.append(redacted_config(item,key))
            if isinstance(item,str) and re.fullmatch(r'(?i)--(?:api[-_]key|token|password|secret|header|authorization)',item):redact_next=True
        return result
    if isinstance(value,str):
        value=re.sub(r'(?i)((?:api[_-]?key|token|password|secret)\s*[:=]\s*)[^\s,;]+',r'\1<REDACTED>',value)
        value=re.sub(r'(?i)bearer\s+[^\s]+|sk-(?:ant-|proj-)?[A-Za-z0-9_-]{16,}','<REDACTED>',value)
        # Strip userinfo/auth fragments; redact credential query values while
        # retaining nonsecret query routing values, including unknown ones.
        def url(match):
            parsed=urlsplit(match.group(0))
            query=[(k,redacted_config(v,k)) for k,v in parse_qsl(parsed.query,keep_blank_values=True)]
            return urlunsplit((parsed.scheme,parsed.netloc.rsplit('@',1)[-1],parsed.path,urlencode(query),''))
        value=re.sub(r'https?://[^\s\"\']+',url,value)
        if 'instruction' in key.lower() and not key.lower().endswith(('_file','_path')) and key.lower()!='instructionsources':
            return {'private_text_sha256':canonical_hash(value)}
    return value


class _SafeConfigIdentity(dict):
    """In-memory provenance for locally computed, already-redacted identities."""
    def __init__(self, value):
        super().__init__(value)
        self._retention_binding=canonical_hash(dict(self))


def safe_config_identity(config):
    safe=redacted_config(config)
    def schema(value):
        if isinstance(value,dict):return {k:schema(v) for k,v in value.items()}
        if isinstance(value,list):return [schema(v) for v in value]
        return type(value).__name__
    return _SafeConfigIdentity({'schema_version':RECEIPT_VERSION,'sha256':canonical_hash(safe),
            'schema':schema(safe),'fields':{k:canonical_hash(v) for k,v in safe.items()},
            'auth_stability_claim':False})


STARTUP_LOOKUP_SOURCES = {'.omx/ultragoal/evidence/unchanged-startup-classifier-fix/pinned-source/config_toml.rs': '52b56c820904559a79f515e444c4bd4dd5c2729531600fcf0edff81496b66f83',
 '.omx/ultragoal/evidence/unchanged-startup-classifier-fix/pinned-source/project_trust.rs': 'ed577aa57d3281b5047ed51b42aa04da96800c6e1184dcde1b8b644bbae7a001',
 '.omx/ultragoal/evidence/unchanged-startup-classifier-fix/pinned-source/path.rs': 'd28635da53b5f435d91105ac7099d9d9c06fb043370ea0bcddd589916fd1edad',
 '.omx/ultragoal/evidence/unchanged-startup-classifier-fix/pinned-source/trust.rs': '62a1a258814e3f215e5632eaea1f8b83b8f0bc2529a921aea05760bb194d9d31',
 '.omx/ultragoal/evidence/unchanged-startup-classifier-fix/pinned-source/project_root_markers.rs': '21d3a86eea7a34f39b1ebc82037d78dd9c1c46fef0c4c74de584bae7cab17f53',
 '.omx/ultragoal/evidence/codex-0164-native-binding/sources/codex-rs__config__src__loader__mod.rs': '4d08c03dbf82013e85c62e65837838baefbb0199685b2bb10c5f242b513a49d0',
 '.omx/ultragoal/evidence/codex-0164-native-binding/sources/codex-rs__app-server__src__request_processors__thread_processor.rs': '0c806ff3aaf348f7373032171d55ff110dfd30bcbb5cfabded89330b5b4375b6',
 '.omx/ultragoal/evidence/codex-0164-native-binding/sources/codex-rs__core__src__config__mod.rs': 'b9786bf33ed36546b100578ce26f6884033c404d11c72ed1e234c1b519605c04'}


def startup_lookup(data, cwd, trust_root):
    """Finite local POSIX get_active_project classification; no config RPC/write.

    Mirror pinned cwd/repo lookup, not loader marker-root trust inheritance.
    Pointer/worktree Git metadata and non-macOS normalization stay unsupported.
    Output contains only requested candidates, enums and redacted identities.
    """
    if sys.platform!='darwin':raise RuntimeError('HELD unsupported native trust path convention')
    for name,digest in STARTUP_LOOKUP_SOURCES.items():
        if sha(SOURCE/name)!=digest:raise RuntimeError('HELD unbound startup lookup source')
    cwd=Path(cwd);bound=Path(trust_root)
    if not cwd.is_absolute() or '..' in cwd.parts or not cwd.is_dir():raise RuntimeError('HELD unknown startup cwd metadata')
    real=cwd.resolve(strict=True);bound_real=bound.resolve(strict=True)
    if not bound.is_absolute() or not bound.is_dir() or not real.is_relative_to(bound_real):raise RuntimeError('HELD startup bound root mismatch')
    cfg=data['config'];layers=data.get('layers')
    if not isinstance(layers,list) or not layers:raise RuntimeError('HELD unknown startup layers')
    layer_ids=[];project_layers=0;raw_markers=[]
    for layer in layers:
        source=layer.get('name',layer.get('source'))
        if (not isinstance(source,dict) or source.get('type') not in ('user','system','sessionFlags','project') or
            not isinstance(layer.get('version'),str) or not isinstance(layer.get('config'),dict)):
            raise RuntimeError('HELD unsupported startup layer identity')
        project_layers+=source['type']=='project'
        layer_ids.append(canonical_hash(redacted_config({k:v for k,v in layer.items() if k!='config'})))
        if 'project_root_markers' in layer['config']:
            value=layer['config']['project_root_markers']
            if not isinstance(value,list) or any(not isinstance(x,str) for x in value):raise RuntimeError('HELD unknown startup marker configuration')
            raw_markers.append(value)
    markers=cfg.get('project_root_markers')
    if markers is None:
        if raw_markers:raise RuntimeError('HELD missing effective startup markers')
        markers=['.git'] # pinned default only when absent in every raw layer
    if not raw_markers and markers!=['.git']:raise RuntimeError('HELD marker value lacks an observed raw source')
    if (not isinstance(markers,list) or any(not isinstance(x,str) or not x or Path(x).name!=x or x in ('.','..') for x in markers) or
        any(x!=markers for x in raw_markers)):
        raise RuntimeError('HELD unsupported startup marker precedence/shape')
    # Source discover_project_root and checkout/root helpers traverse cwd's
    # lexical ancestors. Absence is proved by metadata, never inferred from cwd.
    marker_root=None;checkout=None
    for ancestor in (cwd,*cwd.parents):
        for marker in set(markers)|{'.git'}:
            target=ancestor/marker
            try:meta=target.lstat()
            except FileNotFoundError:continue
            except OSError as error:raise RuntimeError('HELD unknown startup marker metadata') from error
            if stat.S_ISLNK(meta.st_mode):raise RuntimeError('HELD unsupported startup marker symlink')
            valid=True
            if marker=='.git':
                if not stat.S_ISDIR(meta.st_mode):raise RuntimeError('HELD unsupported Git pointer/worktree metadata')
                try:(target/'HEAD').stat()
                except FileNotFoundError:valid=False
                except OSError as error:raise RuntimeError('HELD unknown Git HEAD metadata') from error
                if valid and checkout is None:checkout=ancestor
            if valid and marker in markers and marker_root is None:marker_root=ancestor
        if checkout is not None and (marker_root is not None or not markers):break
    repo=checkout # only ordinary .git-directory roots are supported here
    if repo is not None and repo.resolve(strict=True)!=bound_real:raise RuntimeError('HELD startup repository/trust root mismatch')
    def identity(path):
        meta=path.stat()
        return {'path':str(path),'realpath':str(path.resolve(strict=True)),'device':meta.st_dev,'inode':meta.st_ino,'mode':stat.S_IMODE(meta.st_mode)}
    candidates=[]
    for label,path in [('cwd',cwd)]+([('repo',repo)] if repo is not None else []):
        canonical=str(path.resolve(strict=True));original=str(path)
        if canonical!=original:candidates.append((label+'-canonical',canonical))
        candidates.append((label+'-original',original))
    projects=cfg.get('projects')
    if projects is None:projects={}
    if not isinstance(projects,dict):raise RuntimeError('HELD unknown startup projects type')
    selected=None;observed=[];origins=data.get('origins',{})
    if not isinstance(origins,dict):raise RuntimeError('HELD unknown startup origin identity')
    for category,key in candidates:
        present=key in projects;trust=None
        if present:
            entry=projects[key]
            if not isinstance(entry,dict) or entry.get('trust_level') not in (None,'trusted','untrusted'):raise RuntimeError('HELD unknown candidate trust enum')
            trust=entry.get('trust_level')
        value={'category':category,'path':key,'present':present,'trust':trust,
            'origin_identity':canonical_hash(redacted_config(origins.get('projects.'+key+'.trust_level')))}
        observed.append(value)
        if present and selected is None:selected=copy.deepcopy(value)
    projectless=marker_root is None and checkout is None and project_layers==0
    skip='existing-active-project' if selected is not None and selected['trust'] is not None else 'projectless' if projectless else 'UNKNOWN'
    return {'schema':'startup-trust-lookup-v1','commit':SEMANTIC_COMMIT,'sources':STARTUP_LOOKUP_SOURCES,
        'cwd':identity(cwd),'trust_root':identity(bound),'repo':identity(repo) if repo is not None else None,
        'marker_root':str(marker_root) if marker_root is not None else None,'checkout_root':str(checkout) if checkout is not None else None,
        'project_layer_count':project_layers,'layer_identities':layer_ids,'candidates':observed,'active_project':selected,
        'skip_predicate':skip,'config_identity':canonical_hash(redacted_config(data)),
        'auth_stability_claim':False,'historical_cause':'UNKNOWN'}


# This contract is finite DATA, never a runtime grant or a general override API.
FINITE_POLICY_SCHEMA = 'owned-fixture-session-trust-policy-v1'
FINITE_PRODUCER_SCHEMA = 'owned-fixture-session-trust-producer-v1'
FINITE_LOGICAL_ROOT = '/var/folders/tw/ch14ckzj5916kh8zgkjs2ct80000gn/T/ains S closure codex-default-authentic-preanswer t6_nohgj'
FINITE_CANONICAL_ROOT = '/private'+FINITE_LOGICAL_ROOT
FINITE_CHOICE_SHA256 = '5dcadaccb7ff83c289be0c6c17d5b51599f19ff1eb721b6397ec5a334ba5f16c'
FINITE_MCP_NAMES = ('agent-browser','computer-use','node_repl')


FINITE_SCOPES = {
    '/var/folders/tw/ch14ckzj5916kh8zgkjs2ct80000gn/T/ains S closure codex-default-authentic-preanswer t6_nohgj': {
        'root': '/var/folders/tw/ch14ckzj5916kh8zgkjs2ct80000gn/T/ains S closure codex-default-authentic-preanswer t6_nohgj',
        'canonical_root': '/private/var/folders/tw/ch14ckzj5916kh8zgkjs2ct80000gn/T/ains S closure codex-default-authentic-preanswer t6_nohgj',
        'row_id': 'codex-default-authentic-preanswer',
        'mode': 'default',
        'base_recipe': {'path': '/Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/g004/codex/native-v68/preparation/spec-closure-default-sourcee0-exact-history18-usage71/recipe.json', 'sha256': 'e0dbf2496ac647f6ed2691c0429d14ed72337fb3969d35958aa3389697afc046'},
        'checkpoint': {'path': '/Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/r7-parent-verification/closure-actual-installer-lock-relation-reviews-v1/codex-default-authentic-preanswer/checkpoint-DATA.json', 'sha256': '2fd384eda716a93e6b5c3719c6e81dd462b9a4929348be7cce6937a1e0bf7cb6'},
        'operator_choice': {'path': '/Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/r7-parent-verification/closure-session-trust-implementation-scope/operator-choice.json', 'sha256': '5dcadaccb7ff83c289be0c6c17d5b51599f19ff1eb721b6397ec5a334ba5f16c'},
        'state_count': 127,
    },
    '/var/folders/tw/ch14ckzj5916kh8zgkjs2ct80000gn/T/ains S closure codex-copy-equivalent-preanswer wfojmzy2': {
        'root': '/var/folders/tw/ch14ckzj5916kh8zgkjs2ct80000gn/T/ains S closure codex-copy-equivalent-preanswer wfojmzy2',
        'canonical_root': '/private/var/folders/tw/ch14ckzj5916kh8zgkjs2ct80000gn/T/ains S closure codex-copy-equivalent-preanswer wfojmzy2',
        'row_id': 'codex-copy-equivalent-preanswer',
        'mode': 'copy',
        'base_recipe': {'path': '/Users/<user>/.t3/projects/ai-native-software-engineering/.omx/continuations/resume-20261027-j56k2v96/copy-equivalent-preparation/base-recipe-v2.json', 'sha256': '2f1d8c27d0c00513bff79cbe5a1fc6e5649e7624786bed660119e9b2c09805c1'},
        'checkpoint': {'path': '/Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/r7-parent-verification/closure-actual-installer-lock-relation-reviews-v1/codex-copy-equivalent-preanswer/checkpoint-DATA.json', 'sha256': '2e0f3167e3cb9c27be004595ed0ac592e171257d0ac1c7b2eb5790aa77e42f45'},
        'operator_choice': {'path': '/Users/<user>/.t3/projects/ai-native-software-engineering/.omx/continuations/resume-20261027-j56k2v96/copy-equivalent-preparation/operator-choice-v2.json', 'sha256': 'ab078cc62037d3371fc41ea239e0fd0467e881d95e4831c72508f40a43c56007'},
        'state_count': 127,
    },
    '/var/folders/tw/ch14ckzj5916kh8zgkjs2ct80000gn/T/ains S closure codex-copy-D2-authentic-pre-v57-answer wtt8nbz0': {
        'root': '/var/folders/tw/ch14ckzj5916kh8zgkjs2ct80000gn/T/ains S closure codex-copy-D2-authentic-pre-v57-answer wtt8nbz0',
        'canonical_root': '/private/var/folders/tw/ch14ckzj5916kh8zgkjs2ct80000gn/T/ains S closure codex-copy-D2-authentic-pre-v57-answer wtt8nbz0',
        'row_id': 'codex-copy-D2-authentic-pre-v57-answer',
        'mode': 'copy',
        'base_recipe': {'path': '/Users/<user>/.t3/projects/ai-native-software-engineering/.omx/continuations/resume-20261027-j56k2v96/D2-preparation/base-recipe.json', 'sha256': '94de180c1517aee6ddfcbba142f606cbeec537b0af1fc864d2088cca2425a36c'},
        'checkpoint': {'path': '/Users/<user>/.t3/projects/ai-native-software-engineering/.omx/ultragoal/evidence/r7-parent-verification/closure-actual-installer-lock-relation-reviews-v1/codex-copy-D2-authentic-pre-v57-answer/checkpoint-DATA.json', 'sha256': '00c88b9ad7614b4d265cb7863a3322a97a9728d50c5d8a0c2b554de1d68c1b0b'},
        'state_count': 151,
        'operator_choice': {'path': '/Users/<user>/.t3/projects/ai-native-software-engineering/.omx/continuations/resume-20261027-j56k2v96/D2-preparation/operator-choice.json', 'sha256': 'b19f4d765e19c8747e0948a451c4ec7af284358d67a8c290a8ca1f8e0f35ef31'},
    },
}


def finite_scope(value):
    """Resolve only the three pinned fixture tuples; no I/O or runtime authority."""
    root=value.get("root") if isinstance(value,dict) else value
    scope=FINITE_SCOPES.get(root)
    if scope is None:raise RuntimeError("HELD finite exact fixture scope")
    if isinstance(value,dict) and any(value.get(k)!=v for k,v in {"canonical_root":scope["canonical_root"],"row_id":scope["row_id"],"operator_choice_sha256":scope["operator_choice"]["sha256"]}.items()):raise RuntimeError("HELD finite policy tuple")
    return scope


SPEC_CLOSURE_ZERO_DISPOSITION = {'path':str(SOURCE/'.omx/continuations/resume-20261027-j56k2v96/zero-recovery/disposition.json'),'sha256':'86fa632d52e0753ffe3a45df554cd668ecdabd1307123c1a91bb8793a904f070'}
SPEC_CLOSURE_ZERO_CONTEXT = {'path':'/private/tmp/ains-resume-codex-closure-prep-v2-_yj6p6_e/actual-closure-result/workflow-context.json','sha256':'3d1a370d7da9a8b1747774911ad26483025174d1af7b07179698dce3d2295d78'}


def spec_closure_zero_provenance():
    """Validate the one Root-pinned historical zero; never touch its live claim."""
    d=checked_json(SPEC_CLOSURE_ZERO_DISPOSITION)
    if (d.get('schema')!='ROOT_SPEC_CLOSURE_ZERO_DISPOSITION_V1' or d.get('decision')!='ACCOUNT_EXACT_FAILED_PRE_USER_ZERO_AND_CONDITIONALLY_ALLOW_ONE_REPLACEMENT' or
        d.get('original_context')!=SPEC_CLOSURE_ZERO_CONTEXT):raise RuntimeError('HELD exact known-zero Root disposition')
    audit=checked_json(d['audit'])
    required=('source_root_release_common','root_and_source_exact_approval','zero_turn_start','actual13_equals_bound_expected','B1_pair_equal','lookup_policy_finite_serialization_only','checkpoint_state127_equal')
    if (audit.get('schema')!='INDEPENDENT_KNOWN_ZERO_AUDIT_V1' or audit.get('verdict')!='PASS_KNOWN_ZERO_ONLY' or audit.get('failed_checks')!=[] or
        audit.get('business_PASS') is not False or audit.get('business_turn_start_count')!=0 or audit.get('report')!=d['audit_report'] or
        any(audit.get('checks',{}).get(k) is not True for k in required)):raise RuntimeError('HELD known-zero independent audit')
    refs=[SPEC_CLOSURE_ZERO_DISPOSITION]+[v for v in d.values() if isinstance(v,dict) and set(v)=={'path','sha256'}]
    refs += [d['producer']['collector'],d['producer']['tests'],*d['producer']['helpers'],d['claim']['snapshot']]
    for ref in audit['refs']:
        if ref['path']==d['claim']['original_path']:
            if ref['sha256']!=d['claim']['snapshot']['sha256'] or ref['sha256']!=d['claim']['sha256']:raise RuntimeError('HELD known-zero claim snapshot')
            refs.append(d['claim']['snapshot'])
        else:refs.append({'path':ref['path'],'sha256':ref['sha256']})
    for ref in refs:
        if not Path(ref['path']).is_absolute() or sha(ref['path'])!=ref['sha256']:raise RuntimeError('HELD known-zero provenance bytes')
    record=checked_json(SPEC_CLOSURE_ZERO_CONTEXT);recipe=checked_json(d['original_recipe']);cp=checked_json(d['checkpoint']);declaration=checked_json(d['declaration'])
    base=checked_json(checked_json(declaration['operator_choice'])['base_recipe'])
    scope=d['scope'];identity=d['identity']
    if (record.get('recipe')!=d['original_recipe'] or record.get('wire')!=d['wire'] or record.get('finite_policy_declaration')!=d['declaration'] or
        record.get('facts',{}).get('live-rpc/closed.json')!=d['backend_closed'] or recipe.get('workflow_checkpoint')!=d['checkpoint'] or
        declaration.get('producer')!=d['producer'] or any(record.get(k)!=v for k,v in identity.items() if k!='tests_sha256') or
        identity.get('tests_sha256')!=d['producer']['tests']['sha256'] or record.get('collector_sha256')!='4803e44e3ba98fd55910e9b5d32368f523222712a7263dbc12cc2ff3374c5d93'):
        raise RuntimeError('HELD known-zero exact producer and context')
    if (record.get('healthy') is not False or record.get('failure') is not None or record.get('business_PASS') is not False or
        record.get('closed') is not True or record.get('server_returncode')!=0 or record.get('state_error') is not None or record.get('close_error') is not None or
        record.get('state')!=cp['state'] or len(cp['state'])!=127 or canonical_hash(cp['state'])!=d['state_sha256']):raise RuntimeError('HELD known-zero closed state')
    for ref in (d['wire'],d['catalog_wire']):
        if any(e.get('direction')=='request' and (e.get('payload',{}).get('method') not in ('initialize','initialized','config/read','skills/list','thread/start') or 'result' in e.get('payload',{})) for e in checked_json(ref)):
            raise RuntimeError('HELD known-zero actual USER or foreign request')
    if (scope.get('actual_model_USER_count')!=0 or scope.get('replacement_contexts_max')!=1 or scope.get('replacement_model_USER_max')!=1 or scope.get('seconds')!=180 or
        scope.get('automatic_retry') is not False or scope.get('second_zero_recovery') is not False or
        (scope.get('actual_before'),scope.get('held_before'),scope.get('whole'),scope.get('BUILD'))!=(71,35,106,[3,3])):raise RuntimeError('HELD known-zero finite allowance')
    if (recipe.get('usage')!=base['usage'] or len(base['usage'])!=43 or canonical_hash(base['usage'])!=d['usage']['base_prefix_sha256'] or
        record.get('prior_usage_sha256')!=canonical_hash(base['usage']) or canonical_hash(base['usage']+[SPEC_CLOSURE_ZERO_CONTEXT])!=d['usage']['prefix_plus_original_zero_sha256']):raise RuntimeError('HELD known-zero exact chronology')
    return {'sidecar':d,'record':record,'recipe':recipe,'base':base,'references':refs}


def finite_recipe_usage(base, recipe):
    """Exact default43/44, copy45 or D2copy46; never grow a dynamic retry suffix."""
    rows=base.get('rows',[])
    if len(rows)!=1:raise RuntimeError('HELD finite recipe row')
    if rows[0].get('mode')=='copy':
        scope=next((v for v in FINITE_SCOPES.values() if v['mode']=='copy' and v['row_id']==rows[0].get('id')),None)
        if scope is None or base!=checked_json(scope['base_recipe']):raise RuntimeError('HELD finite exact copy base')
        return list(base['usage'])
    proof=spec_closure_zero_provenance()
    if base!=proof['base']:raise RuntimeError('HELD finite recovery original base')
    return list(base['usage']) if recipe==proof['recipe'] else list(base['usage'])+[dict(SPEC_CLOSURE_ZERO_CONTEXT)]


def finite_session_policy(choice, recipe):
    """Pure constructor for either exact Root-selected fixture, not authority."""
    scope=finite_scope(choice['root'])
    logical_root=scope['root'];canonical_root=scope['canonical_root']
    rows=recipe.get('rows',[])
    if any(choice.get(k)!=scope[k] for k in ('base_recipe','checkpoint')):raise RuntimeError('HELD finite pinned choice base/checkpoint')
    if (choice.get('schema')!='ROOT_EXACT_DISPOSABLE_FIXTURE_PROCESS_TRUST_CHOICE_V1' or
        choice.get('decision')!='SELECT_EXACT_PROCESS_ONLY_TRUSTED_FIXTURE_FOR_FINITE_SOURCE_IMPLEMENTATION' or
        choice.get('root')!=logical_root or choice.get('canonical_root')!=canonical_root or
        choice.get('row_id')!=scope['row_id'] or choice.get('mode')!=scope['mode'] or len(rows)!=1 or
        any(rows[0].get(k)!=v for k,v in {'id':choice['row_id'],'mode':scope['mode'],'transport':'live'}.items()) or
        any(recipe.get(k)!=v for k,v in {'purpose':'spec-closure-regression','phase':'closure','unit':'changed-spec'}.items())):
        raise RuntimeError('HELD finite policy scope')
    session={'features':{k:False for k in (*CANONICAL_FEATURES,*DISCOVERY_KEYS)},
        'mcp_servers':{n:{'enabled':False,'command':'/usr/bin/false'} for n in FINITE_MCP_NAMES},
        'projects':{canonical_root:{'trust_level':'trusted'}}}
    overrides=['features.'+k+'=false' for k in (*CANONICAL_FEATURES,*DISCOVERY_KEYS)]
    for name in FINITE_MCP_NAMES:overrides+=['mcp_servers.'+name+'.enabled=false','mcp_servers.'+name+'.command="/usr/bin/false"']
    pair=['-c','projects.'+canonical_root+'.trust_level="trusted"']
    if choice.get('argv_pair')!=pair:raise RuntimeError('HELD finite policy argv choice')
    overrides.append(pair[1])
    return {'schema':FINITE_POLICY_SCHEMA,'producer_schema':FINITE_PRODUCER_SCHEMA,
        'root':logical_root,'canonical_root':canonical_root,'row_id':choice['row_id'],
        'session':session,'session_version':'sha256:'+canonical_hash(session),'overrides':overrides,
        'operator_choice_sha256':scope['operator_choice']['sha256']}


def validate_finite_policy_argv(argv, policy):
    """Validate the actual argument vector before version/config subprocesses."""
    scope=finite_scope(policy)
    logical_root=scope['root'];canonical_root=scope['canonical_root']
    fixed=['features.'+k+'=false' for k in (*CANONICAL_FEATURES,*DISCOVERY_KEYS)]
    for name in FINITE_MCP_NAMES:fixed+=['mcp_servers.'+name+'.enabled=false','mcp_servers.'+name+'.command="/usr/bin/false"']
    fixed+=['projects.'+canonical_root+'.trust_level="trusted"']
    if policy.get('overrides')!=fixed:raise RuntimeError('HELD finite policy argv whitelist')
    expected=[argv[0] if argv else None,'--no-daemon','-a','never','app-server','--strict-config','--stdio']
    for value in policy['overrides']:expected+=['-c',value]
    if argv!=expected or not argv or argv[0]!='/opt/homebrew/bin/codex':raise RuntimeError('HELD finite policy actual argv')
    return argv


def finite_policy_projection(data, policy):
    """Observe exact native SessionFlags and origin; no missing-value synthesis."""
    scope=finite_scope(policy)
    logical_root=scope['root'];canonical_root=scope['canonical_root']
    cfg=data.get('config');layers=data.get('layers');origins=data.get('origins')
    if not isinstance(cfg,dict) or not isinstance(layers,list) or not isinstance(origins,dict):raise RuntimeError('HELD finite policy missing config/layers/origin')
    expected=policy['session'];version='sha256:'+canonical_hash(expected)
    if policy.get('schema')!=FINITE_POLICY_SCHEMA or policy.get('session_version')!=version:raise RuntimeError('HELD finite policy fingerprint')
    # Rebuild the whitelist rather than trusting caller-supplied overrides/maps.
    canonical={'features':{k:False for k in (*CANONICAL_FEATURES,*DISCOVERY_KEYS)},'mcp_servers':{n:{'enabled':False,'command':'/usr/bin/false'} for n in FINITE_MCP_NAMES},'projects':{canonical_root:{'trust_level':'trusted'}}}
    if expected!=canonical or policy.get('root')!=logical_root or policy.get('canonical_root')!=canonical_root:raise RuntimeError('HELD finite policy singleton scope')
    sessions=[];persistent=[];names=set();seen=[]
    positions=[('cwd-canonical',canonical_root),('cwd-original',logical_root),('repo-canonical',canonical_root),('repo-original',logical_root)]
    for layer in layers:
        source=layer.get('name',layer.get('source'));raw=layer.get('config')
        if (not isinstance(source,dict) or source.get('type') not in ('system','user','sessionFlags') or
            not isinstance(raw,dict) or not isinstance(layer.get('version'),str) or layer.get('disabledReason') is not None or
            layer['version']!='sha256:'+canonical_hash(raw)):
            raise RuntimeError('HELD finite policy layer/version/disabled')
        kind=source['type'];seen.append(kind);servers=raw.get('mcp_servers',{})
        if not isinstance(servers,dict):raise RuntimeError('HELD finite policy MCP map')
        names.update(servers)
        if kind=='sessionFlags':
            if source!={'type':'sessionFlags'} or raw!=expected or layer['version']!=version:raise RuntimeError('HELD finite policy full SessionFlags')
            sessions.append({'name':source,'version':layer['version']})
        else:
            projects=raw.get('projects',{})
            if not isinstance(projects,dict) or any(path in projects for _,path in positions):raise RuntimeError('HELD finite policy persistent candidate')
            if kind=='system' and raw:raise RuntimeError('HELD finite policy nonempty system layer')
            persistent.append({'metadata':{'name':source,'version':layer['version']},'identity':safe_config_identity(raw),
                'candidates':[{'category':label,'path':path,'present':False} for label,path in positions]})
    if len(sessions)!=1 or not persistent or seen not in (['sessionFlags','user'],['sessionFlags','user','system']):raise RuntimeError('HELD finite policy layer cardinality/order')
    key='projects.'+canonical_root+'.trust_level';origin=origins.get(key)
    if origin!=sessions[0]:raise RuntimeError('HELD finite policy observed origin/version')
    features=cfg.get('features',{});servers=cfg.get('mcp_servers',{});projects=cfg.get('projects',{})
    skills=cfg.get('skills')
    if skills is None:skills={}
    if not isinstance(skills,dict):raise RuntimeError('HELD finite policy skills structure')
    include=skills.get('include_instructions')
    if include is None:
        # The pinned loader defaults both absent/null optional skills and an
        # absent/null include flag to true; preserve their raw identities.
        for name,digest,_,_ in DEFAULT_SOURCE_PROOFS:
            if sha(AUDIT/'sources'/name)!=digest:raise RuntimeError('HELD finite policy unbound default source')
    if (any(features.get(k) is not False for k in expected['features']) or
        not isinstance(servers,dict) or set(servers)!=set(FINITE_MCP_NAMES) or names!=set(FINITE_MCP_NAMES) or
        any(not isinstance(v,dict) or v.get('enabled') is not False or v.get('command')!='/usr/bin/false' for v in servers.values()) or
        not isinstance(projects,dict) or projects.get(canonical_root)!={'trust_level':'trusted'} or logical_root in projects or
        (include is not None and include is not True)):raise RuntimeError('HELD finite policy effective features/MCP/projects/instructions')
    return {'schema':FINITE_POLICY_SCHEMA,'session':copy.deepcopy(expected),'session_version':version,'session_metadata':sessions[0],
        'origin_path':key,'origin':copy.deepcopy(origin),'persistent_layers':persistent,'project_layer_count':0,
        'config_identity':safe_config_identity(cfg),'response_identity':safe_config_identity(data)}


def finite_metadata_sample(policy, observed):
    """Pure check of an explicitly sampled, complete metadata/MDM frame."""
    paths=policy.get('metadata_paths')
    if not isinstance(paths,dict) or not paths:raise RuntimeError('HELD finite metadata read scope missing')
    if (not observed.get('mdm_before') or any(observed['mdm_before'].values()) or
        observed.get('mdm_after')!=observed['mdm_before'] or observed.get('files')!=paths):raise RuntimeError('HELD finite metadata/raw/managed drift')
    return {'schema':FINITE_POLICY_SCHEMA,**copy.deepcopy(observed),
        'all_layer_mcp_names':list(FINITE_MCP_NAMES),'loader_relation':'Actual live config; metadata-only sample; no ignored-user claim'}




def finite_receipt(value):
    """Retain locally computed safe identities and typed nonsecret env facts."""
    safe=redacted_config(value)
    def identity(raw):
        def schema(value):
            if type(value) is dict:return all(type(k) is str and schema(v) for k,v in value.items())
            if type(value) is list:return all(schema(v) for v in value)
            return type(value) is str and value in {'str','bool','int','float','NoneType'}
        def digest(value):
            return type(value) is str and re.fullmatch(r'[0-9a-f]{64}',value) is not None
        if (set(raw)!={'schema_version','sha256','schema','fields','auth_stability_claim'} or
            raw.get('schema_version')!=RECEIPT_VERSION or raw.get('auth_stability_claim') is not False or
            not digest(raw.get('sha256')) or type(raw.get('schema')) is not dict or
            type(raw.get('fields')) is not dict or not schema(raw['schema']) or
            set(raw['schema'])!=set(raw['fields']) or
            any(type(k) is not str or not digest(v) for k,v in raw['fields'].items()) or
            getattr(raw,'_retention_binding',None)!=canonical_hash(dict(raw))):
            raise RuntimeError('HELD finite locally computed identity serialization')
        return copy.deepcopy(raw)
    def restore(raw,retained):
        # Never reopen a container the generic privacy rule excluded wholesale.
        if isinstance(retained,dict) and set(retained)=={'redacted','type'} and retained['redacted'] is True:
            return retained
        if type(raw) is _SafeConfigIdentity:return identity(raw)
        if isinstance(raw,dict) and isinstance(retained,dict):
            for key,item in raw.items():
                if key=='environment' and isinstance(item,dict):
                    facts={'selector_names','identity_sha256','default_home','default_codex_home','selected_environment_file','legacy_selection'}
                    local={'selected_environment_kind','required_skills','proof','native_tools_unavailable_claim'}
                    if set(item)==facts:
                        if (set(item['identity_sha256'])-{'HOME','CODEX_HOME'} or any(not isinstance(v,str) or len(v)!=64 for v in item['identity_sha256'].values()) or
                            set(item['selected_environment_file'])!={'path','realpath','exists','sha256'} or any(type(item[k]) is not bool for k in ('default_home','default_codex_home'))):raise RuntimeError('HELD finite typed environment serialization')
                        retained[key]=redacted_config(item)
                    elif set(item)==local and item['selected_environment_kind']=='local' and item['required_skills']==[] and item['native_tools_unavailable_claim'] is False:
                        retained[key]=redacted_config(item)
                elif key in retained:retained[key]=restore(item,retained[key])
        elif isinstance(raw,list) and isinstance(retained,list):
            for index,(left,right) in enumerate(zip(raw,retained)):retained[index]=restore(left,right)
        return retained
    return restore(value,safe)


def validate_finite_producer(declaration, helpers):
    """Hash inert archives at admission and replay; never import their contents."""
    archived=declaration.get('producer')
    if not isinstance(archived,dict) or set(archived)!={'collector','tests','helpers'}:raise RuntimeError('HELD finite producer archives required')
    for role,key in (('collector','collector_sha256'),('tests','tests_sha256')):
        ref=archived.get(role,{})
        if set(ref)!={'path','sha256'} or ref.get('sha256')!=declaration.get(key) or not Path(ref['path']).is_absolute() or sha(ref['path'])!=ref['sha256']:raise RuntimeError('HELD finite retained producer pair')
    refs=archived.get('helpers')
    if not isinstance(refs,list) or len(refs)!=4 or [v.get('sha256') for v in refs]!=[v['sha256'] for v in helpers] or declaration.get('helpers')!=helpers:raise RuntimeError('HELD finite retained producer helpers')
    for ref in refs:
        if set(ref)!={'path','sha256'} or not Path(ref['path']).is_absolute() or sha(ref['path'])!=ref['sha256']:raise RuntimeError('HELD finite retained helper bytes')


def validate_finite_metadata(declaration, recipe, instructions, choice):
    """One retained-facts predicate for admission and replay; no host path lookup."""
    scope=finite_scope(choice['root'])
    logical_root=scope['root'];canonical_root=scope['canonical_root']
    paths=declaration.get('metadata_paths')
    if not isinstance(paths,dict) or not paths:raise RuntimeError('HELD finite complete metadata read scope')
    root=Path(logical_root);canonical=Path(canonical_root)
    ancestors={root,*root.parents,canonical,*canonical.parents}
    contributors={Path('/etc/codex/config.toml'),Path('/etc/codex/requirements.toml'),Path('/etc/codex/managed_config.toml')}
    for ancestor in ancestors:contributors.update((ancestor/'.codex/config.toml',ancestor/'.codex/hooks.json'))
    # Exactly one default user directory is retained, distinct from ancestor layers.
    homes={str(Path(p).parent) for p in paths if p.endswith('/.codex/environments.toml') and Path(p).parent.parent not in ancestors}
    if len(homes)!=1:raise RuntimeError('HELD finite retained user directory identity')
    home=Path(next(iter(homes)))
    user={home/'config.toml',home/'hooks.json',home/'environments.toml'}
    contributors.add(home/'managed_config.toml');contributors.update(user)
    absent=contributors-user|{root/'.codex',canonical/'.codex'}
    agents=str(root/'AGENTS.md')
    if not isinstance(instructions,list) or agents not in instructions:raise RuntimeError('HELD finite AGENTS instructionSources')
    required=set(map(str,contributors|absent))|set(instructions)|{v['path'] for v in recipe['protected_files']}
    if not required<=set(paths):raise RuntimeError('HELD finite incomplete contributor/protected/instruction scope')
    for path,entry in paths.items():
        if (not isinstance(path,str) or not Path(path).is_absolute() or not isinstance(entry,dict) or set(entry)!={'exists','sha256','realpath'} or
            type(entry.get('exists')) is not bool or not isinstance(entry.get('realpath'),str) or not Path(entry['realpath']).is_absolute() or
            (entry['exists'] and (not isinstance(entry['sha256'],str) or len(entry['sha256'])!=64)) or not entry['exists'] and entry['sha256'] is not None):raise RuntimeError('HELD finite declaration metadata identity/presence')
    for path in absent:
        if paths[str(path)]['exists'] is not False:raise RuntimeError('HELD finite system/managed/project contributor')
    if recipe.get('producer_schema')==FINITE_PRODUCER_SCHEMA and recipe!=spec_closure_zero_provenance()['recipe']:
        for reference in (SPEC_CLOSURE_ZERO_DISPOSITION,SPEC_CLOSURE_ZERO_CONTEXT):
            entry=paths.get(reference['path'],{})
            if entry.get('exists') is not True or entry.get('sha256')!=reference['sha256'] or entry.get('realpath')!=reference['path']:raise RuntimeError('HELD finite recovery metadata pins')
    for value in recipe['protected_files']:
        entry=paths[value['path']]
        if entry['exists'] is not True or entry['sha256']!=value['sha256']:raise RuntimeError('HELD finite protected declaration identity')
    for path in instructions:
        if paths[path]['exists'] is not True:raise RuntimeError('HELD finite instruction presence')
    if paths[agents]['sha256']!=choice['AGENTS_sha256'] or paths[agents]['realpath']!=str(canonical/'AGENTS.md'):raise RuntimeError('HELD finite original AGENTS identity')
    return str(home)


def validate_finite_lookup(reference, policy, collector, recipe, manifest, binary, observed=None):
    """Validate an original v2 input from retained facts, without rerunning lookup."""
    scope=finite_scope(policy)
    logical_root=scope['root'];canonical_root=scope['canonical_root']
    receipt=checked_json(reference);classification=receipt.get('classification');projection=receipt.get('policy')
    if (receipt.get('schema')!='startup-no-write-owned-fixture-policy-v2' or
        any(receipt.get(k)!=v for k,v in {'collector_sha256':collector,'recipe_sha256':recipe,'manifest_sha256':manifest,'binary_sha256':binary,'declaration':policy['declaration'],'mode':'existing-active-project'}.items()) or
        not isinstance(classification,dict) or not isinstance(projection,dict) or not isinstance(classification.get('active_project'),dict) or
        classification.get('skip_predicate')!='existing-active-project' or classification.get('active_project',{}).get('trust')!='trusted' or
        classification.get('project_layer_count')!=0 or classification.get('marker_root')!=logical_root or classification.get('checkout_root')!=logical_root or
        classification.get('commit')!=SEMANTIC_COMMIT or classification.get('sources')!=STARTUP_LOOKUP_SOURCES or
        classification.get('config_identity')!=projection.get('response_identity',{}).get('sha256') or
        projection.get('schema')!=FINITE_POLICY_SCHEMA or projection.get('session')!=policy['session'] or projection.get('session_version')!=policy['session_version'] or
        projection.get('session_metadata')!={'name':{'type':'sessionFlags'},'version':policy['session_version']} or projection.get('origin')!=projection.get('session_metadata') or
        projection.get('origin_path')!='projects.'+canonical_root+'.trust_level' or observed is not None and projection!=observed):raise RuntimeError('HELD finite retained v2 lookup certificate/pins/classification/origin')
    candidates=[{'category':label,'path':path,'present':path==canonical_root,'trust':'trusted' if path==canonical_root else None,
        'origin_identity':canonical_hash(projection['origin'] if path==canonical_root else None)} for label,path in
        [('cwd-canonical',canonical_root),('cwd-original',logical_root),('repo-canonical',canonical_root),('repo-original',logical_root)]]
    if (classification.get('schema')!='startup-trust-lookup-v1' or classification.get('candidates')!=candidates or classification.get('active_project')!=candidates[0] or
        not isinstance(classification.get('layer_identities'),list) or len(classification['layer_identities'])!=len(projection.get('persistent_layers',[]))+1):raise RuntimeError('HELD finite retained lookup candidates/layers')
    for role,path in (('cwd',logical_root),('trust_root',canonical_root),('repo',logical_root)):
        identity=classification.get(role,{})
        if (not isinstance(identity,dict) or identity.get('path')!=path or identity.get('realpath')!=canonical_root or
            any(type(identity.get(k)) is not int for k in ('device','inode','mode'))):raise RuntimeError('HELD finite retained lookup topology identities')
    return receipt


def finite_rpc_range(wire, start, end, methods):
    """Successful ordered calls, unique IDs, and no detached response projection."""
    if type(start) is not int or type(end) is not int or not 0<=start<end<=len(wire):raise RuntimeError('HELD finite RPC range')
    requests=[(i,wire[i]['payload']) for i in range(start,end) if wire[i]['direction']=='request']
    if [v.get('method') for _,v in requests]!=methods:raise RuntimeError('HELD finite actual RPC sequence')
    ids=[v.get('id') for _,v in requests]
    if any(e.get('direction')=='response_or_event' and 'id' in e['payload'] and 'method' not in e['payload'] and e['payload']['id'] not in ids for e in wire[start:end]):raise RuntimeError('HELD finite foreign RPC response')
    calls=[]
    for number,(index,request) in enumerate(requests):
        ident=request.get('id');replies=[i for i in range(index+1,end) if wire[i]['direction']=='response_or_event' and wire[i]['payload'].get('id')==ident and 'method' not in wire[i]['payload']]
        if ident is None or len(replies)!=1 or sum(e.get('direction')=='request' and e['payload'].get('id')==ident for e in wire)!=1 or number+1<len(requests) and replies[0]>=requests[number+1][0]:raise RuntimeError('HELD finite indexed request/response ID')
        response=wire[replies[0]]['payload']
        if request['method']=='config/read':
            if response.get('status')!='ok' or response.get('receipt_schema')!=RECEIPT_VERSION or not isinstance(response.get('structural_result'),dict):raise RuntimeError('HELD finite successful config response')
            value=response['structural_result']
        else:
            if 'result' not in response or 'error' in response:raise RuntimeError('HELD finite successful RPC response')
            value=response['result']
        calls.append((request.get('params'),value))
    return calls


def bind_startup_no_write(reference, data, cwd, trust_root, recipe_path, manifest, binding):
    """A separately reviewed current lookup proposes one unchanged skip branch."""
    receipt=checked_json(reference);classification=startup_lookup(data,cwd,trust_root)
    policy=binding.get('finite_session_policy')
    if policy:
        projection=finite_policy_projection(data,policy)
        validate_finite_lookup(reference,policy,sha(__file__),sha(recipe_path),sha(manifest),binding['executable_identity']['sha256'],projection)
        if (receipt.get('schema')!='startup-no-write-owned-fixture-policy-v2' or
            receipt.get('collector_sha256')!=sha(__file__) or receipt.get('recipe_sha256')!=sha(recipe_path) or
            receipt.get('manifest_sha256')!=sha(manifest) or receipt.get('binary_sha256')!=binding['executable_identity']['sha256'] or
            receipt.get('classification')!=classification or receipt.get('policy')!=projection or receipt.get('declaration')!=policy['declaration'] or
            classification['skip_predicate']!='existing-active-project' or classification['active_project']['trust']!='trusted' or
            classification['project_layer_count']!=0 or classification['marker_root']!=str(cwd) or classification['checkout_root']!=str(cwd)):
            raise RuntimeError('HELD finite observed no-write certificate')
        return {'schema':'startup-no-write-owned-fixture-policy-v2','mode':'existing-active-project','before':classification,
            'policy':projection,'declaration':policy['declaration'],'current_receipt':reference}

    if (receipt.get('schema')!='startup-no-write-current-v1' or receipt.get('collector_sha256')!=sha(__file__) or
        receipt.get('recipe_sha256')!=sha(recipe_path) or receipt.get('manifest_sha256')!=sha(manifest) or
        receipt.get('binary_sha256')!=binding['executable_identity']['sha256'] or
        receipt.get('classification')!=classification or receipt.get('mode')!=classification['skip_predicate'] or
        receipt.get('mode') not in ('existing-active-project','projectless')):
        raise RuntimeError('HELD unbound proposed unchanged startup lookup')
    return {'mode':receipt['mode'],'before':classification,'current_receipt':reference}


def startup_relation(before, after, trust_root):
    """Only an exact, source-established persisted trust transition is allowed."""
    left=copy.deepcopy(before);right=copy.deepcopy(after)
    a=left.get('projects') or {};b=right.get('projects') or {}
    if not isinstance(a,dict) or not isinstance(b,dict):raise RuntimeError('Unknown startup project structure')
    old=a.get(trust_root);new=b.get(trust_root)
    if old is not None and (not isinstance(old,dict) or old.get('trust_level') is not None):
        raise RuntimeError('Unexpected startup trust premise')
    if new!=dict(old or {},trust_level='trusted'):raise RuntimeError('Unbound persisted trust/in-memory fallback')
    a.pop(trust_root,None);b.pop(trust_root,None)
    if a:left['projects']=a
    else:left.pop('projects',None)
    if b:right['projects']=b
    else:right.pop('projects',None)
    if left!=right:raise RuntimeError('Unknown startup delta or project activation')
    return 'persisted-trust-only'


def validate_no_write_startup(pre, post, pre_files, post_files, trust_root, user_path, user_before, user_after, no_write):
    before=no_write['before'];after=no_write['after'];mode=no_write.get('mode')
    if no_write.get('schema')=='startup-no-write-owned-fixture-policy-v2':
        declaration=checked_json(no_write['declaration']);choice=checked_json(declaration['operator_choice'])
        scope=finite_scope(choice['root'])
        policy=finite_session_policy(choice,{'purpose':'spec-closure-regression','phase':'closure','unit':'changed-spec','rows':[{'id':scope['row_id'],'mode':scope['mode'],'transport':'live'}]})
        if finite_policy_projection(pre,policy)!=no_write['policy'] or finite_policy_projection(post,policy)!=no_write['policy']:
            raise RuntimeError('HELD finite no-write policy drift')

    if (pre!=post or pre_files!=post_files or user_before!=user_after or before!=after or
        before.get('config_identity')!=canonical_hash(redacted_config(pre)) or
        before.get('sources')!=STARTUP_LOOKUP_SOURCES or before.get('commit')!=SEMANTIC_COMMIT or
        mode not in ('existing-active-project','projectless') or before.get('skip_predicate')!=mode):
        raise RuntimeError('HELD changed/unknown proposed no-write startup')
    if mode=='existing-active-project' and (not before.get('active_project') or before['active_project'].get('trust') not in ('trusted','untrusted')):
        raise RuntimeError('HELD missing existing active-project decision')
    if mode=='projectless' and (before.get('marker_root') is not None or before.get('checkout_root') is not None or before.get('project_layer_count')!=0):
        raise RuntimeError('HELD incomplete projectless startup premise')
    return 'unchanged-source-bound-no-write'


def validate_startup(pre, post, pre_files, post_files, trust_root, user_path, user_before, user_after):
    if pre==post and pre_files==post_files:
        if (post.get('config',{}).get('projects') or {}).get(trust_root,{}).get('trust_level')!='trusted':
            raise RuntimeError('Unbound project trust or in-memory fallback')
        return 'unchanged-persisted-trust'
    startup_relation(user_before,user_after,trust_root)
    startup_relation(pre['config'],post['config'],trust_root)
    left=copy.deepcopy(pre);right=copy.deepcopy(post)
    left.pop('config');right.pop('config')
    if len(left['layers'])!=len(right['layers']):raise RuntimeError('Unexpected project activation/layer count')
    user_layers=[]
    for a,b in zip(left['layers'],right['layers']):
        if a.get('name',a.get('source'))!=b.get('name',b.get('source')):raise RuntimeError('Startup layer source mismatch')
        source=a.get('name',a.get('source')) or {}
        if source.get('type')=='user':
            startup_relation(a['config'],b['config'],trust_root)
            user_layers.append((source,a.get('version'),b.get('version')))
            a.pop('config');b.pop('config');a.pop('version',None);b.pop('version',None)
    if 'origins' in left or 'origins' in right:
        # ConfigManagerService returns path -> {name, version} from the same
        # layers. Only that exact user's version propagation and the newly
        # validated trust leaf origin follow from this persisted trust write.
        if len(user_layers)!=1:raise RuntimeError('Unbound startup user origin layer')
        source,old_version,new_version=user_layers[0]
        if (source.get('file')!=user_path or not isinstance(old_version,str) or
            not isinstance(new_version,str) or old_version==new_version):
            raise RuntimeError('Unbound startup user origin source/version')
        origins=left.get('origins');after_origins=right.get('origins')
        if not isinstance(origins,dict) or not isinstance(after_origins,dict):
            raise RuntimeError('Unsupported startup origins shape')
        trust_key='projects.'+trust_root+'.trust_level'
        if trust_key in origins:raise RuntimeError('Unexpected preexisting trust origin')
        expected=copy.deepcopy(origins)
        for key,metadata in expected.items():
            if (not isinstance(metadata,dict) or not isinstance(metadata.get('name'),dict) or
                not isinstance(metadata.get('version'),str) or
                metadata['name'].get('type') not in ('user','system','sessionFlags')):
                raise RuntimeError('Unsupported startup origin metadata shape')
            if metadata['name'].get('type')=='user':
                if metadata['name']!=source or metadata['version']!=old_version:
                    raise RuntimeError('Unbound existing user origin source/version')
                metadata['version']=new_version
        expected[trust_key]={'name':source,'version':new_version}
        if after_origins!=expected:raise RuntimeError('Unknown startup origin delta')
        # Normalize only the classified version/leaf propagation. All original
        # keys, non-user origins and additional metadata remain in comparison.
        right['origins']=copy.deepcopy(origins)
    if left!=right:raise RuntimeError('Unknown startup layer/metadata delta')
    a=copy.deepcopy(pre_files);b=copy.deepcopy(post_files)
    if user_path not in a or user_path not in b:raise RuntimeError('Missing persisted user trust source')
    a[user_path]['sha256']=None;b[user_path]['sha256']=None
    if a!=b:raise RuntimeError('Unknown startup file/source/body delta')
    return 'persisted-trust-only'


def reconcile_thread(actual, request, expected, config=None):
    if set(expected)!=set(THREAD_FIELDS) or any(k not in actual for k in THREAD_FIELDS):
        raise RuntimeError('Missing parent-bound actual thread snapshot observable')
    if any(actual[k]!=expected[k] for k in THREAD_FIELDS):raise RuntimeError('Actual thread snapshot mismatch')
    if (actual['model']!=request['model'] or actual['cwd']!=request['cwd'] or
        actual['approvalPolicy']!=request['approvalPolicy'] or request['sandbox']!='workspace-write' or
        not isinstance(actual['sandbox'],dict) or actual['sandbox'].get('type')!='workspaceWrite' or
        actual['sandbox'].get('networkAccess') is not False or actual['multiAgentMode']!='explicitRequestOnly'):
        raise RuntimeError('Actual thread does not match explicit typed overlays/authority')
    # Typed request overrides model/approval/sandbox/cwd. Other explicitly
    # returned defaults must agree; null/absent unresolved defaults are covered
    # only by the separate parent expectation, never fabricated here.
    for configured,reported in [('model_provider','modelProvider'),('service_tier','serviceTier'),
                                ('model_reasoning_effort','reasoningEffort'),('approvals_reviewer','approvalsReviewer')]:
        if config is not None and config.get(configured) is not None and config[configured]!=actual[reported]:
            raise RuntimeError('Actual thread disagrees with observed unoverridden default: '+configured)
    thread=actual.get('thread',{})
    if not thread.get('id') or any(thread.get(k)!=actual[k] for k in ('cwd','model','modelProvider','reasoningEffort')):
        raise RuntimeError('Actual nested thread snapshot mismatch')
    return {'thread_id':thread['id'],'snapshot':{k:actual[k] for k in THREAD_FIELDS},
            'request_overlays':request,'expected_provenance':'explicit parent binding; no ApiConfig defaults synthesized'}


class PostStartBaseline:
    """One immutable serialized baseline; any drift permanently closes this gate."""
    def __init__(self, first, second):
        self._identity=json.dumps(first,sort_keys=True);self.failed=False
        self.check(second)
    def check(self, current):
        if self.failed or json.dumps(current,sort_keys=True)!=self._identity:
            self.failed=True
            raise RuntimeError('Post-thread-start baseline drift; baseline cannot reset')


def native_premises(data, names):
    if not isinstance(data.get('layers'),list) or not data['layers']:
        raise RuntimeError('Missing applicable source layers')
    for layer in data['layers']:
        source=layer.get('name',layer.get('source'))
        if not isinstance(source,dict) or 'version' not in layer:
            raise RuntimeError('Missing source identity/version observable')
        if source.get('type')=='user' and not isinstance(layer['version'],str):
            raise RuntimeError('Missing raw user version observable')
    cfg=data['config'];features=cfg.get('features',{});skills=cfg.get('skills')
    if skills is not None and not isinstance(skills,dict):raise RuntimeError('Unknown skills structure')
    if not isinstance(features,dict):raise RuntimeError('Unknown features structure')
    if any(features.get(k) is not False for k in CANONICAL_FEATURES+DISCOVERY_KEYS[:2]):
        raise RuntimeError('Missing/changed explicit native contributor/discovery flags')
    # The pinned loader explicitly maps absent/null Option<SkillsConfig> and
    # include_instructions=None to true; SkipHostSkillDiscovery is default false.
    # Raw absence/null remains in safe_config_identity, never normalized away.
    for name,digest,_,_ in DEFAULT_SOURCE_PROOFS:
        if sha(AUDIT/'sources'/name)!=digest:raise RuntimeError('Unbound native default source')
    include=(skills or {}).get('include_instructions')
    if include is not None and include is not True:raise RuntimeError('Skill instructions disabled/unknown')
    skip=features.get('skip_host_skill_discovery',False)
    if skip is not False:raise RuntimeError('Host discovery skipped/unknown')
    servers=cfg.get('mcp_servers',{})
    union=set(servers)
    for layer in data['layers']:union.update((layer.get('config',{}).get('mcp_servers') or {}).keys())
    if union!=set(names) or set(servers)!=set(names):raise RuntimeError('MCP name union drift; no expanding overrides')
    if any(v.get('enabled') is not False or v.get('command')!='/usr/bin/false' for v in servers.values()):
        raise RuntimeError('MCP disabled command replacement premise missing')
    return {'include_instructions':True,'skip_host_skill_discovery':False,
            'defaults_source':{'commit':SEMANTIC_COMMIT,'proofs':DEFAULT_SOURCE_PROOFS}}


def live_bundle(rpc, root, installed, raw_paths, manifest, helpers, binding, instruction_paths, business_edit=None):
    """Two reads bracket a same-process catalog refresh and file/env sampling."""
    a=helpers['activation_r3'];structural=helpers['activation_closure_probe'].structural
    def files():
        released_source(manifest)
        paths=set(map(Path,raw_paths))|set(map(Path,instruction_paths))
        if binding.get('finite_session_policy'):
            paths.add(Path(binding['finite_session_policy']['declaration']['path']))
        paths.update(SOURCE/'tests/runtime/codex'/(name+'.py') for name in HELPERS)
        paths.update([Path(__file__),Path(manifest),Path(binding['proof_path'])])
        paths.update(AUDIT/'sources'/name for name,_,_,_ in DEFAULT_SOURCE_PROOFS)
        for item in installed:
            paths.update(p for p in Path(item['path']).parent.rglob('*') if p.is_file())
        if business_edit:notification_business_sample(business_edit,paths)
        return {str(p):{'realpath':str(p.resolve()),'exists':p.exists(),
                        'sha256':sha(p) if p.is_file() else None} for p in sorted(paths)}
    policy=binding.get('finite_session_policy')
    policy_metadata=binding['_metadata_sample']() if policy else None
    start=files();env=environment_facts(rpc.env);require_environment(env,binding)
    if any(a.mdm_forced().values()):raise RuntimeError('Managed state outside native premise')
    first=rpc.call('config/read',{'includeLayers':True,'cwd':str(root)},timeout=30)
    defaults=native_premises(first,binding['_mcp_names'])
    facts=config_facts(first,structural)
    catalog=rpc.call('skills/list',{'cwds':[str(root)],'forceReload':True},timeout=30)
    proof=validate_catalog(catalog,installed,facts,'live')
    second=rpc.call('config/read',{'includeLayers':True,'cwd':str(root)},timeout=30)
    native_premises(second,binding['_mcp_names'])
    policy_proof=finite_policy_projection(first,policy) if policy else None
    if policy and (finite_policy_projection(second,policy)!=policy_proof or first!=second or binding['_metadata_sample']()!=policy_metadata):raise RuntimeError('HELD finite bundle policy/raw drift')
    end=files();actual_inventory=a.inventory(root)
    if (facts!=config_facts(second,structural) or start!=end or actual_inventory!=installed or
        environment_facts(rpc.env)!=env or any(a.mdm_forced().values())):
        raise RuntimeError('Unstable post-start probe bundle; no first turn')
    return {**({'finite_policy':policy_proof,'policy_metadata':policy_metadata} if policy else {}),'schema_version':RECEIPT_VERSION,'config':facts,'catalog':redacted_config(catalog),
            'files':end,'environment':env,'installed':actual_inventory,'manifest_sha256':sha(manifest),
            'binary_sha256':sha(Path(rpc.args[0]).resolve()),'process_id':rpc.p.pid,
            'thread_id':rpc.bound_thread,'catalog_proof':proof,'source_bound_defaults':defaults},first


def config_facts(data, structural):
    """Only nonsecret structural fields; never persist raw config/read data."""
    def one(cfg):
        features=cfg.get('features') or {};skills=cfg.get('skills') or {}
        if not isinstance(features,dict) or not isinstance(skills,dict):raise ValueError('Unknown feature/skill config structure')
        return {'structure':structural(cfg),'canonical_features':{k:features.get(k) for k in CANONICAL_FEATURES},'discovery':{k:features.get(k,False) for k in DISCOVERY_KEYS},
                'skill_setting_keys':sorted(skills),'skill_settings':[{k:x.get(k) for k in ['name','path','enabled'] if k in x} for x in (skills.get('config') or [])],
                'include_instructions':True if skills.get('include_instructions') is None else skills['include_instructions'],'bundled_setting_keys':sorted(skills.get('bundled') or {})}
    return {'effective':one(data.get('config',{})),'safe_identity':safe_config_identity(data.get('config',{})),'response_identity':safe_config_identity(data),
            'layers':[{'source':x.get('name',x.get('source')),'version':x.get('version'),'disabled_reason':x.get('disabledReason'),'facts':one(x.get('config',{})),'safe_identity':safe_config_identity(x.get('config',{}))} for x in data.get('layers',[])],
            'source_semantics':SEMANTIC_COMMIT}


def environment_facts(env):
    home=Path.home();selected=Path(env.get('CODEX_HOME',str(home/'.codex')))
    path=selected/'environments.toml'
    return {'selector_names':[k for k in sorted(env) if k.startswith('CODEX_EXEC_SERVER')],
            'identity_sha256':{k:hashlib.sha256(env[k].encode()).hexdigest() for k in ['HOME','CODEX_HOME'] if k in env},
            'default_home':env.get('HOME')==str(home),'default_codex_home':selected==home/'.codex',
            'selected_environment_file':{'path':str(path),'realpath':str(path.resolve()),'exists':path.exists(),'sha256':sha(path) if path.is_file() else None},
            'legacy_selection':'CODEX_EXEC_SERVER* environment selectors; presence only, no values read or persisted'}


def require_environment(facts, binding):
    if facts['selector_names'] or not facts['default_home'] or not facts['default_codex_home']:
        raise RuntimeError('Unbound remote/noise or nondefault HOME/CODEX_HOME environment')
    file=facts['selected_environment_file']
    if not file['exists']:
        return {'selected_environment_kind':'local','required_skills':[],'proof':'0.164 from_codex_home absent environments.toml + absent legacy/noise selectors; local default constructor','native_tools_unavailable_claim':False}
    external=binding.get('environment_receipt',{})
    if (external.get('file_sha256')!=file['sha256'] or external.get('file_path')!=file['path'] or
        external.get('parent_release_id')!=binding.get('parent_release_id') or
        external.get('selected_environment_kind')!='local' or external.get('required_skills')!=[] or
        not external.get('proof_path') or sha(Path(external['proof_path']))!=external.get('proof_sha256')):
        raise RuntimeError('Selected environments.toml exists: supported config/read does not expose resolved EnvironmentManager required skills; parent-bound structural environment_receipt required')
    return external


def validate_catalog(catalog, installed, facts, transport):
    groups=catalog.get('data')
    if not isinstance(groups,list) or len(groups)!=1 or not isinstance(groups[0].get('skills'),list) or not isinstance(groups[0].get('errors'),list):raise RuntimeError('Missing complete applicable catalog/errors')
    root=Path(installed[0]['path']).parents[3]
    if not groups[0].get('cwd') or Path(groups[0]['cwd']).resolve()!=root.resolve():raise RuntimeError('Catalog cwd does not match installed consumer')
    if catalog.get('errors') or any(g.get('errors') for g in groups):raise RuntimeError('Catalog contains load errors')
    if any(value is not False for value in facts['effective']['canonical_features'].values()):raise RuntimeError('Actual effective contributor flags not all false')
    entries=[x for g in groups for x in g.get('skills',[])]
    targets=[x for x in entries if x.get('name') in MANUAL|AUTO]
    if len(targets)!=16 or {x['name'] for x in targets}!=MANUAL|AUTO:raise RuntimeError('Missing or ambiguous declared target name')
    expected={x['name']:x for x in installed}
    for x in targets:
        if x.get('enabled') is not True:raise RuntimeError('Applicable target is disabled/unknown')
        if x.get('path') not in [expected[x['name']]['path'],expected[x['name']]['realpath']] or Path(x['path']).resolve()!=Path(expected[x['name']]['realpath']):raise RuntimeError('Wrong exact target logical/real path')
    for layer in facts['layers']:
        if not isinstance(layer.get('source'),dict) or layer['source'].get('type') not in ['user','system','sessionFlags']:raise RuntimeError('Unrecognized actual configuration layer')
        if layer.get('disabled_reason'):raise RuntimeError('Configuration layer error')
        f=layer['facts']
        if f['discovery']['skip_host_skill_discovery'] is not False or f['include_instructions'] is not True:
            raise RuntimeError('Discovery disabled or unknown')
        for setting in f['skill_settings']:
            if setting.get('enabled') is False and (setting.get('name') in MANUAL|AUTO or setting.get('path') in {x['path'] for x in installed}):
                raise RuntimeError('Applicable target disabled setting contradicts catalog/loader equivalence')
        if transport=='cli' and f['bundled_setting_keys']:raise RuntimeError('Ignored-user bundled root setting needs parent-bound catalog equivalence')
    return {'enabled_unique_targets':16,'applicable_catalog_entries':len(entries),'load_errors':0,
            'target_paths':[x['path'] for x in targets],'layer_root_sources':[x['source'] for x in facts['layers']],
            'loader_relation':'CLI retains exact User root but ignores user content; current complete target catalog is enabled/unique, no applicable target disable setting or root-policy contradiction' if transport=='cli' else 'Actual live RPC active config/catalog; no ignored-user projection',
            'semantic_source':SEMANTIC_COMMIT,'universal_global_catalog_claim':False}


def healthy_terminal(events,transport):
    if transport not in ('cli','live'):return False
    # Execute only the existing, independently tested pure terminal utility.
    path=SOURCE/'tests/runtime/codex/activation_r3.py'
    tree=ast.parse(path.read_text(),str(path))
    definition=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='continuation_ready')
    namespace={}
    exec(compile(ast.Module(body=[definition],type_ignores=[]),str(path),'exec'),namespace)
    normalized=[]
    for event in events:
        if not isinstance(event,dict):continue
        if transport=='cli':normalized.append(event);continue
        method=event.get('method','')
        if method=='error' or method.startswith('turn/'):
            turn=event.get('params',{}).get('turn',{})
            normalized.append({'type':method.replace('/','.'),
                'status':turn.get('status') if turn.get('status') is not None else 'unknown',
                'error':turn.get('error',event.get('params',{}).get('error')),
                'is_error':event.get('is_error',False)})
    return namespace['continuation_ready']({'exit':0,'timeout':False,
        'structural_closure':{'projected_stable':True},'events':normalized})


def native_selection_receipt(binding,catalog_proof,environment_proof,transport):
    if binding.get('official_commit')!=SEMANTIC_COMMIT or not binding.get('parent_release_id') or transport not in binding.get('transports',[]):raise RuntimeError('Unreviewed current semantic binding')
    if catalog_proof.get('enabled_unique_targets')!=16 or catalog_proof.get('load_errors')!=0:raise RuntimeError('Incomplete native catalog proof')
    if environment_proof.get('selected_environment_kind')!='local' or environment_proof.get('required_skills')!=[]:raise RuntimeError('Unbound required-skill/environment state')
    if binding.get('finite_session_policy'):
        observed=binding.get('_finite_policy_observation');policy=binding['finite_session_policy'];metadata={'name':{'type':'sessionFlags'},'version':policy['session_version']}
        if not isinstance(observed,dict) or observed.get('session')!=policy['session'] or observed.get('session_version')!=policy['session_version'] or observed.get('origin')!=metadata or observed.get('session_metadata')!=metadata:raise RuntimeError('HELD native receipt requires observed finite policy/origin')
    return {**({'producer_schema':FINITE_PRODUCER_SCHEMA,'finite_policy':binding['finite_session_policy'],'observed_policy':binding['_finite_policy_observation'],'policy_declaration':binding['finite_session_policy']['declaration']} if binding.get('finite_session_policy') else {}),'status':'BOUND_ACTUAL_RECEIPTS','semantic_source':SEMANTIC_COMMIT,'source_proof_sha256':binding['proof_sha256'],'parent_release_id':binding['parent_release_id'],'catalog':catalog_proof,'environment':environment_proof,'transport':transport,'selector':'Actual literal-dollar Text; no body injection success inferred'}


def recorded_rpc(rt, ar, root, overrides, sink, binding):
    """Small local subclass: actual wire/launch receipts; old helpers untouched."""
    policy=binding.get('finite_session_policy')
    retain=(lambda path,value:write(path,finite_receipt(value))) if policy else ar.write
    if policy:
        proposed=['/opt/homebrew/bin/codex','--no-daemon','-a','never','app-server','--strict-config','--stdio']
        for value in overrides:proposed+=['-c',value]
        validate_finite_policy_argv(proposed,policy)
    class RecordedRPC(rt.RPC):
        def __init__(self):
            self.log=[];self.methods={};self.sink=Path(sink);self.sink.mkdir(parents=True,exist_ok=False)
            invoked=shutil.which('codex');resolved=Path(invoked).resolve()
            if policy:
                proposed=[invoked,'--no-daemon','-a','never','app-server','--strict-config','--stdio']
                for value in overrides:proposed+=['-c',value]
                validate_finite_policy_argv(proposed,policy)
                self.policy_metadata_before=binding['_metadata_sample']()
            version=subprocess.run([invoked,'--version'],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=20).stdout.strip()
            self.env=os.environ.copy();environment=environment_facts(self.env);selected=require_environment(environment,binding)
            if policy and (not isinstance(binding.get('_finite_home_identity'),str) or len(binding['_finite_home_identity'])!=64 or binding['_finite_home_identity']!=environment.get('identity_sha256',{}).get('HOME')):raise RuntimeError('HELD finite actual HOME identity')
            self.environment_before=environment;self.selected_environment=selected
            self.args=[invoked,'--no-daemon','-a','never','app-server','--strict-config','--stdio']
            for value in overrides:self.args+=['-c',value]
            if any('cloud-skills-snapshot' in x for x in self.args):raise RuntimeError('Unexpected cloud snapshot')
            identity={'invoked_path':invoked,'resolved_path':str(resolved),'version':version,'sha256':sha(resolved)}
            expected=binding['executable_identity']
            if version!=binding['codex_version'] or identity['sha256']!=expected['sha256'] or str(resolved)!=expected['symlink_target']:raise RuntimeError('Current executable identity changed')
            launch={'producer_schema':FINITE_PRODUCER_SCHEMA if policy else None,'finite_policy':policy,'policy_metadata':getattr(self,'policy_metadata_before',None),'actual_argv':self.args,'identity':identity,'environment':environment,'selected_environment':selected,'cloud_snapshot_supplied':False,'fresh_history_and_roots':'Only recorded fresh thread/start fields; no resume/roots/snapshot writes permitted','semantic_source':SEMANTIC_COMMIT}
            retain(self.sink/'launch.json',launch)
            if policy:validate_finite_policy_argv(self.args,policy)
            self.stderr=tempfile.TemporaryFile()
            self.p=subprocess.Popen(self.args,cwd=root,env=self.env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,start_new_session=True)
            if policy:
                launch.update(process_id=self.p.pid,cwd=str(root));retain(self.sink/'launch.json',launch)
            self.buf=b'';self.seq=0;self.events=[]
            try:self.call('initialize',{'clientInfo':{'name':'ains-native-v1-receipts-v2','version':'2'}});self.send({'method':'initialized'})
            except BaseException:self.close();raise
        def flush(self):retain(self.sink/'rpc.json',self.log)
        def send(self,obj):
            if 'method' in obj:
                if obj['method'] not in ['initialize','initialized','config/read','skills/list','thread/start','turn/start']:raise RuntimeError('Unexpected RPC write')
                if obj['method']=='thread/start' and (set(obj['params'])!={'cwd','model','approvalPolicy','sandbox','ephemeral'} or obj['params'].get('ephemeral') is not True):raise RuntimeError('Unexpected history/root/thread-start input')
                if 'id' in obj:self.methods[obj['id']]=obj['method']
            self.log.append({'direction':'request','payload':obj,'wire_index':len(self.log),'monotonic_ns':time.monotonic_ns()});self.flush();return super().send(obj)
        def next(self,deadline):
            try:obj=super().next(deadline)
            except BaseException as error:
                self.log.append({'direction':'transport_error','exception_type':type(error).__name__});self.flush();raise
            method=self.methods.get(obj.get('id'))
            if method=='config/read':
                payload={'id':obj.get('id'),'status':'error' if 'error' in obj else 'ok','receipt_schema':RECEIPT_VERSION}
                if 'result' in obj:
                    try:
                        payload['structural_result']=config_facts(obj['result'],rt_structural)
                        if policy:payload['policy']=finite_policy_projection(obj['result'],policy)
                    except (TypeError,ValueError,KeyError) as error:
                        payload['status']='structural_projection_error';payload['exception_type']=type(error).__name__
                        self.log.append({'direction':'response_or_event','payload':payload,'wire_index':len(self.log),'monotonic_ns':time.monotonic_ns()});self.flush();raise
                if 'error' in obj:payload['error_code']=obj['error'].get('code')
            else:payload=redacted_config(obj)
            self.log.append({'direction':'response_or_event','payload':payload,'wire_index':len(self.log),'monotonic_ns':time.monotonic_ns()});self.flush();return obj
        def close(self):
            try:super().close()
            finally:
                self.stderr.seek(0);diagnostic=self.stderr.read();self.stderr.close()
                after=environment_facts(self.env)
                policy_after=binding['_metadata_sample']() if policy else None
                if policy and policy_after!=self.policy_metadata_before:raise RuntimeError('HELD finite process-close metadata drift')
                retain(self.sink/'closed.json',{'policy_metadata':policy_after,'stderr_bytes':len(diagnostic),'stderr_sha256':hashlib.sha256(diagnostic).hexdigest(),'environment_after':after,'stable':after==self.environment_before})
                self.flush()
                if after!=self.environment_before:raise RuntimeError('Selected environment file/selector identity changed')
    # Reuse existing nonsecret projection, with three audited v2 keys added above.
    from activation_closure_probe import structural as rt_structural
    return RecordedRPC()


def rows():
    result = []
    def add(name, mode, fixture, prompt, turns=1, groups=None, live=False):
        result.append(dict(id=name, mode=mode, fixture=fixture, initial_user_text=prompt,
            max_user_turns=turns, transport='live' if live else 'cli', groups=groups or ['D1'],
            status='NOT RUN', terminal_deadline_seconds=180))
    add('default-router','default','base','$ains Inspect this disposable project and recommend the next stage.')
    add('default-original-spec','default',CASES[0][1],original_prompt(*CASES[0]),4,['D1','D5','D6'],True)
    add('default-original-build','default',CASES[1][1],original_prompt(*CASES[1]),groups=['D1','D6'])
    for mode in ['default','copy']:
        add(mode+'-automatic-tdd',mode,'base',TDD)
        add(mode+'-unnamed-spec',mode,'base',NEGATIVE_SPEC)
        add(mode+'-unnamed-build',mode,'approved',NEGATIVE_BUILD)
    add('copy-workflow','copy','absent','$ains Inspect this disposable project and recommend the next stage.',20,['D1','D2','D3','D4'],True)
    add('copy-independent-review','copy','review-packet',
        'Review diff.patch against spec.md, surrounding source and tests. Independently run the supplied test command. Report findings, evidence and remaining gaps. No author conversation is supplied.',groups=['D2'])
    for structure in ['agents-only','claude-only','duplicate','conflict','existing-import','samefile','symlink']:
        add('copy-setup-'+structure,'copy',structure,SETUP,6,['D4'],True)
    for skill, case in CASES[2:]:
        add('copy-original-'+case,'copy',case,original_prompt(skill,case),groups=['D3','D6'])
    add('copy-malformed-plan','copy','malformed','$ains-build Implement the plan in docs/changes/discount-cap.',groups=['D3'])
    add('copy-review-unavailable','copy','review-unavailable',
        '$ains-ship Prepare a local handoff from the fixture evidence. Independent review is unavailable in this fixture: do not simulate it or use author self-review as independent approval. Record the incomplete review and pause.',groups=['D3'])
    return result


def native_oracle(events, user_text, bodies, installed, selector_bound=False, native_outcomes=()):
    """Separate native recognition, successful body consumption and attempts.

    Ordinary command/Read/helper use is N5 evidence only. A generic model text
    message cannot prove N4. The caller must bind the pinned selector and actual
    configured catalog before selector_bound can be true. Negative absence is
    deliberately an observation, not a universal PASS.
    """
    explicit = sorted(set(re.findall(r'\$(ains(?:-[a-z-]+)?)\b', user_text)) & MANUAL)
    loads = []; attempts = []; successes = []; ambiguous = []
    for index, event in enumerate(events):
        item = event.get('item', event.get('params', {}).get('item', {}))
        kind = item.get('type')
        if kind in ['agent_message','agentMessage']: continue
        output = item.get('aggregated_output', item.get('aggregatedOutput', ''))
        if not isinstance(output,str):continue
        command = item.get('command', '')
        if not isinstance(command,str):command=''
        for name, body in bodies.items():
            path = installed.get(name)
            if path and body and body in output and (str(path) in command or '.agents/skills/'+name+'/SKILL.md' in command or item.get('path')==str(path)):
                loads.append({'skill':name,'event_index':index,'path':path,
                              'body_sha256':hashlib.sha256(body.encode()).hexdigest(),
                              'proof':'Actual installed complete body in tool output; NOT injection proof'})
    # A source-bound decoder/reviewer may supply actual supported native outcomes.
    # No fictional native event type is inferred from Codex JSON or agent prose.
    for entry in native_outcomes:
        if entry.get('skill') not in MANUAL: continue
        if not entry.get('schema_source_sha256') or not entry.get('retained_event_indexes'):
            ambiguous.append(entry)
        elif entry.get('status') in ['rejected','denied','failed']:attempts.append(entry)
        elif entry.get('status')=='succeeded':successes.append(entry)
        else:ambiguous.append(entry)
    return {'N4': {'explicit_names':explicit,
                   'recognition':'SOURCE_BOUND_NATIVE_SELECTOR' if explicit and isinstance(selector_bound,dict) and selector_bound.get('status')=='BOUND_ACTUAL_RECEIPTS' and selector_bound.get('semantic_source')==SEMANTIC_COMMIT and selector_bound.get('catalog',{}).get('enabled_unique_targets')==16 else 'UNVERIFIED',
                   'not_model_prose':True},
            'N5_installed_body_consumption':loads,
            'native_successes':successes,'rejected_native_attempts':attempts,
            'ambiguous_native_outcomes':ambiguous,
            'negative_observation':'NATIVE_MANUAL_ACTIVATION' if successes and not explicit else
                'UNVERIFIED' if ambiguous or attempts else 'NO_NATIVE_MANUAL_EVENT_OBSERVED',
            'ordinary_reads_are_native_failure':False}


def base_template(root, rt, fixture):
    root.mkdir(parents=True)
    (root/'calc.py').write_text('def discount(value):\n    return min(value, 100)\n')
    (root/'tests').mkdir(); (root/'tests/test_calc.py').write_text('import unittest\nfrom calc import discount\nclass Calc(unittest.TestCase):\n    def test_lower(self): self.assertEqual(discount(10), 10)\n')
    (root/'.gitignore').write_text('.agents/\n.claude/\nskills-lock.json\n__pycache__/\n')
    (root/'docs/ains').mkdir(parents=True)
    (root/'docs/ains/human-review-rules').write_text('path | auth/** | Authentication and authorization\n')
    policy = rt.CONTRACT
    if fixture not in ['absent','claude-only']:
        (root/'AGENTS.md').write_text(policy)
    if fixture == 'agents-only':
        (root/'AGENTS.md').write_text(policy.replace('コミットは禁止。','work branch のコミットは利用者が個別に指示した場合のみ許可。'))
    if fixture in ['claude-only','duplicate','conflict']:
        (root/'CLAUDE.md').write_text(policy.replace('docs/changes/','other/changes/') if fixture=='conflict' else policy)
        with (root/'CLAUDE.md').open('a') as stream: stream.write('\n## Other\nCLAUDE_PRESERVE_ME\n')
    if fixture == 'existing-import': (root/'CLAUDE.md').write_text('CLAUDE_PRESERVE_ME\n@AGENTS.md\n')
    if fixture == 'samefile': os.link(root/'AGENTS.md',root/'CLAUDE.md')
    if fixture == 'symlink': (root/'CLAUDE.md').symlink_to('AGENTS.md')
    if fixture in ['approved','malformed','review-unavailable']: rt.approved(root)
    if fixture == 'malformed':
        tasks=root/'docs/changes/discount-cap/tasks.md'; tasks.write_text(tasks.read_text().replace('status: approved','status: [approved'))


SETUP_SLOTS = ('AGENTS.md','CLAUDE.md')
SETUP_EDGE_SCHEMA = 'setup-artifact-edge-v1'


def setup_slots(root, protected):
    """Exact fixture slots only; never follow a slot outside this pair/root."""
    root=Path(root);logical={root/name for name in SETUP_SLOTS};result={}
    protected_paths=[Path(p) for p in protected]
    for path in logical:
        try:resolved=path.resolve(strict=path.exists() or path.is_symlink())
        except (OSError,RuntimeError):raise RuntimeError('UNVERIFIED setup slot broken/cyclic link')
        if not resolved.is_relative_to(root.resolve()) or resolved not in {p.resolve() for p in logical if not p.is_symlink()}:
            if path.exists() or path.is_symlink():raise RuntimeError('UNVERIFIED setup slot external/unknown alias')
        exists=path.exists() or path.is_symlink()
        record={'path':str(path),'realpath':str(resolved),'kind':'absent','sha256':None,'bytes_hex':None,
                'link_text':None,'lstat_identity':None,'target_identity':None}
        if exists:
            ls=path.lstat();target=path.stat()
            if not stat.S_ISREG(target.st_mode) or not (stat.S_ISREG(ls.st_mode) or stat.S_ISLNK(ls.st_mode)):
                raise RuntimeError('UNVERIFIED setup slot type')
            record.update(kind='symlink' if path.is_symlink() else 'regular',
                link_text=os.readlink(path) if path.is_symlink() else None,
                lstat_identity=[ls.st_dev,ls.st_ino],target_identity=[target.st_dev,target.st_ino])
        for other in protected_paths:
            if (path==other or resolved==other.resolve() or
                (exists and other.exists() and record['target_identity']==[other.stat().st_dev,other.stat().st_ino])):
                raise RuntimeError('UNVERIFIED protected setup slot/alias overlap')
        if exists:record.update(sha256=sha(path),bytes_hex=path.read_bytes().hex())
        result[path.name]=record
    # Unlisted internal hardlink names cannot join this finite artifact edge.
    identities={tuple(x['target_identity']) for x in result.values() if x['target_identity']}
    for other in root.rglob('*'):
        if other not in logical and other.is_file() and (other.stat().st_dev,other.stat().st_ino) in identities:
            raise RuntimeError('UNVERIFIED unknown internal setup alias')
    return {name:result[name] for name in SETUP_SLOTS}


def setup_scope(root):
    return {str(p.relative_to(root)):{'sha256':sha(p),'realpath':str(p.resolve())}
            for p in sorted(Path(root).rglob('*')) if p.is_file() and p not in {Path(root)/name for name in SETUP_SLOTS}}


def setup_write_provenance(before, after, scope, events, contract):
    """Observe producer records; never infer shell execution scope from text."""
    changed={name for name in SETUP_SLOTS if before[name]!=after[name]}
    records=[];covered=set();issues=[];structured=False;commands=[]
    for index,event in enumerate(events):
        if not isinstance(event,dict):continue
        params=event.get('params')
        item=params.get('item') if isinstance(params,dict) else None
        if event.get('method')!='item/completed' or not isinstance(item,dict):continue
        if item.get('type')=='commandExecution':
            complete=(item.get('status')=='completed' and isinstance(item.get('command'),str) and bool(item['command']) and
                      type(item.get('exitCode')) is int and item['exitCode']==0 and isinstance(item.get('aggregatedOutput'),str))
            records.append({'event_index':index,'item':copy.deepcopy(item),'completed_command_result':complete})
            if complete:commands.append(index)
        if item.get('type')!='fileChange':continue
        structured=True
        record={'event_index':index,'item':copy.deepcopy(item),'candidate_postimages':[]};records.append(record)
        changes=item.get('changes')
        if item.get('status')!='completed' or not isinstance(changes,list) or not changes:
            issues.append('incomplete_file_change');continue
        for change in changes:
            if (not isinstance(change,dict) or not isinstance(change.get('path'),str) or
                not Path(change['path']).is_absolute() or '..' in Path(change['path']).parts or
                not isinstance(change.get('diff'),str) or not isinstance(change.get('kind'),dict) or
                change['kind'].get('type') not in ('add','update','delete')):
                issues.append('unsupported_file_change_shape');continue
            if any(value is not None for key,value in change['kind'].items() if key!='type'):
                issues.append('unsupported_file_change_kind_metadata');continue
            path=change['path']
            names={name for name in SETUP_SLOTS if path in (after[name]['path'],after[name]['realpath'])}
            if names:
                # A known internal samefile/symlink target can cover both names.
                identities={tuple(after[name]['target_identity']) for name in names if after[name]['target_identity']}
                names|={name for name in SETUP_SLOTS if after[name]['target_identity'] and tuple(after[name]['target_identity']) in identities}
                for name in sorted(names):
                    record['candidate_postimages'].append({'slot':name,'path':after[name]['path'],
                        'sha256':after[name]['sha256'],'bytes_hex':after[name]['bytes_hex']})
                exact=next((name for name in SETUP_SLOTS if after[name]['path']==path),sorted(names)[0])
                if change['kind']['type']=='add' and (before[exact]['kind']!='absent' or change['diff'].encode().hex()!=after[exact]['bytes_hex']):
                    issues.append('add_diff_preimage_or_postimage_mismatch')
                elif change['kind']['type']=='delete' or not names.intersection(changed):
                    issues.append('file_change_without_matching_artifact_delta')
                else:covered.update(names.intersection(changed))
            elif path in {str(Path(contract['root'])/name) for name in contract['allowed_outputs']}:
                relative=str(Path(path).relative_to(contract['root']))
                record['candidate_postimages'].append({'path':path,'sampled_output':scope.get(relative)})
                if relative not in scope:issues.append('missing_declared_output_postimage')
            else:issues.append('foreign_file_change_path')
    if structured and covered!=changed:issues.append('unmatched_instruction_delta')
    if not structured and commands:issues.append('command_execution_scope_unverified')
    complete=not issues and bool(structured)
    mode='structured_file_change' if structured else 'command_requires_parent_scope_review' if commands else 'missing_or_incomplete'
    return {'schema':'setup-write-observation-v1','mode':mode,'complete_for_parent_review':complete,
            'issues':sorted(set(issues or ([] if complete else ['missing_complete_write_observation']))),
            'records':records,'completed_command_event_indexes':commands,'covered_slots':sorted(covered),
            'execution_scope_parser_claim':False}


class SetupArtifactEdge:
    """Terminal observation only. Original B0 never changes or grants dispatch."""
    authorizes_dispatch=False
    def __init__(self, baseline, contract, root, row_id, strict=None):
        if (not isinstance(contract,dict) or contract.get('schema')!=SETUP_EDGE_SCHEMA or
            contract.get('stage') not in ('setup','setup-repeat') or contract.get('row_id')!=row_id or
            not (row_id.startswith('copy-setup-') or row_id=='copy-workflow') or
            contract.get('root')!=str(root) or contract.get('realroot')!=str(Path(root).resolve()) or
            not isinstance(baseline.get('setup_slots'),dict)):
            raise RuntimeError('UNVERIFIED missing exact setup artifact contract')
        contract=copy.deepcopy(contract)
        actual=baseline['setup_slots']
        if contract.get('initial_slots')!=actual:
            images={name:{k:actual[name][k] for k in ('kind','sha256','link_text')} for name in SETUP_SLOTS}
            topology=('symlink' if any(x['kind']=='symlink' for x in actual.values()) else
                      'samefile' if actual['AGENTS.md']['target_identity'] is not None and actual['AGENTS.md']['target_identity']==actual['CLAUDE.md']['target_identity'] else 'distinct')
            if contract.get('initial_images')!=images or contract.get('initial_topology')!=topology:
                raise RuntimeError('UNVERIFIED original fixture image/topology contract')
            # Fresh-copy inode numbers cannot be known at recipe preparation.
            # Bind their actual identities now, before readiness/first USER.
            contract['initial_slots']=copy.deepcopy(actual)
        if not contract.get('setup_input_sha256'):
            raise RuntimeError('UNVERIFIED setup input scope contract')
        if set(contract.get('preserve',{}))!=set(SETUP_SLOTS) or contract.get('allowed_outputs') not in ([],['docs/ains/human-review-rules']):
            raise RuntimeError('UNVERIFIED setup preservation/output contract')
        for name,spans in contract['preserve'].items():
            before=bytes.fromhex(baseline['setup_slots'][name]['bytes_hex'] or '')
            if not isinstance(spans,list) or any(not isinstance(span,str) or span.encode() not in before for span in spans):
                raise RuntimeError('UNVERIFIED fixture preservation span')
        self._baseline=json.dumps(baseline,sort_keys=True);self.contract=copy.deepcopy(contract)
        self.strict=strict or PostStartBaseline(baseline,baseline);self.closed=False
    @property
    def baseline(self):return json.loads(self._baseline)
    def unchanged(self, current):
        return json.dumps(current,sort_keys=True)==self._baseline
    def terminal(self, terminal, events, history):
        if self.closed or self.strict.failed:raise RuntimeError('Setup edge closed/failed; cannot retry')
        self.closed=True
        if not healthy_terminal(events,'live'):raise RuntimeError('UNVERIFIED unhealthy drained setup terminal')
        if not history or any(x.get('role')!='user' for x in history) or not any(n.get('text') and canonical_hash(n['text'])==self.contract['setup_input_sha256'] for n in history):
            raise RuntimeError('UNVERIFIED actual setup USER provenance')
        before=self.baseline;after=copy.deepcopy(terminal)
        if set(before)!=set(after):raise RuntimeError('Protected setup bundle schema drift')
        old=before['setup_slots'];new=after.get('setup_slots')
        if not isinstance(new,dict) or set(new)!=set(SETUP_SLOTS) or new==old:raise RuntimeError('UNVERIFIED missing exact setup delta')
        shared=old['AGENTS.md']['target_identity'] is not None and old['AGENTS.md']['target_identity']==old['CLAUDE.md']['target_identity']
        for name in SETUP_SLOTS:
            a,b=old[name],new[name]
            if a['path']!=b['path'] or a['realpath']!=b['realpath']:raise RuntimeError('Setup slot retarget')
            if a['kind']!='absent' and a['kind']!=b['kind']:raise RuntimeError('Setup slot kind changed')
            if b['kind']=='absent' and a['kind']=='absent':continue
            if b['kind'] not in ('regular','symlink'):raise RuntimeError('Setup output slot missing/unknown')
            if a['kind']=='symlink' and any(a[k]!=b[k] for k in ('link_text','lstat_identity','target_identity')):raise RuntimeError('Setup symlink identity changed')
            if shared and a['target_identity']!=b['target_identity']:raise RuntimeError('Setup samefile inode split/replacement')
            body=bytes.fromhex(b['bytes_hex'])
            if hashlib.sha256(body).hexdigest()!=b['sha256']:raise RuntimeError('Setup postimage bytes/hash mismatch')
            previous=bytes.fromhex(a['bytes_hex'] or '')
            if any(body.count(span.encode())!=previous.count(span.encode()) for span in self.contract['preserve'][name]):raise RuntimeError('Setup fixture bytes/grants lost or duplicated')
        left=copy.deepcopy(before);right=copy.deepcopy(after)
        for view in (left,right):
            view['setup_slots']={'contract':canonical_hash(self.contract)}
            for name in SETUP_SLOTS:
                path=str(Path(self.contract['root'])/name)
                if path not in view['files']:raise RuntimeError('Missing sampled setup slot')
                view['files'][path]={'setup_artifact_slot':name}
        for output in self.contract['allowed_outputs']:
            if output in left['setup_scope']:
                if left['setup_scope'][output]!=right['setup_scope'].get(output):raise RuntimeError('Existing setup rules changed')
            else:
                output_record=right['setup_scope'].get(output)
                if output_record and not Path(output_record['realpath']).is_relative_to(Path(self.contract['root']).resolve()):raise RuntimeError('Setup rules output escapes consumer')
                right['setup_scope'].pop(output,None)
        if left!=right:raise RuntimeError('Protected/nonartifact setup drift')
        provenance=setup_write_provenance(old,new,after['setup_scope'],events,self.contract)
        return {'schema':'setup-artifact-checkpoint-v1','status':('OBSERVED_SETUP_OUTPUT_CHECKPOINT_REQUIRES_PARENT_REVIEW'
                if provenance['complete_for_parent_review'] else 'HELD_UNVERIFIED_SETUP_OUTPUT_PROVENANCE'),
            'closed':False,'raw_stable':False,'root':self.contract['root'],'contract':self.contract,
            'baseline':before,'terminal':after,'post_slots':new,'events':events,'write_evidence':provenance['records'],'provenance':provenance,'user_history':history,
            'original_setup_user_text':next(x['text'] for x in history if x.get('text') and canonical_hash(x['text'])==self.contract['setup_input_sha256']),
            'preservation':'Bound spans/counts checked; exact grants/imports/sections/policy require concrete parent review',
            'idempotence':('CHANGED_AFTER_DECLARED_ACTUAL_USER_DECISION_REQUIRES_PARENT_REVIEW'
                if self.contract.get('intervening_decision_user_sha256') and any(x.get('text') and canonical_hash(x['text'])==self.contract['intervening_decision_user_sha256'] for x in history)
                else 'FAIL_CHANGED_REPEAT_REQUIRES_PARENT_ADJUDICATION') if self.contract['stage']=='setup-repeat' else 'NOT_YET_TESTED'}


DERIVATIVE_SCHEMA = 'codex-c0-derivative-observation-v1'
C0_GENERATED = ('__pycache__/calc.cpython-314.pyc','tests/__pycache__/test_calc.cpython-314.pyc')


def checked_json(reference):
    path=Path(reference['path'])
    if sha(path)!=reference['sha256']:raise RuntimeError('HELD evidence reference hash mismatch: '+str(path))
    return json.loads(path.read_text())


def recover_frozen_c0(request):
    """Read-only deterministic observation; no program execution or live inspection."""
    if request.get('schema')!='frozen-c0-recovery-request-v1':raise RuntimeError('HELD unsupported recovery request')
    design=checked_json(request['design_index']);disposition=checked_json(request['disposition'])
    if (sha(request['design_report']['path'])!=request['design_report']['sha256'] or
        disposition.get('design_report_sha256')!=request['design_report']['sha256'] or
        design.get('report_sha256')!=request['design_report']['sha256']):raise RuntimeError('HELD design/disposition mismatch')
    manifest=checked_json(request['manifest']);base=Path(request['manifest']['path']).parent
    pinned=design['pinned_inputs']
    if not any(Path(path).resolve()==Path(request['manifest']['path']).resolve() and receipt['sha256']==request['manifest']['sha256'] for path,receipt in pinned.items()):
        raise RuntimeError('HELD frozen manifest not pinned by accepted design')
    frozen={}
    for relative,digest in manifest['files'].items():
        path=base/relative
        if not path.resolve().is_relative_to(base.resolve()) or sha(path)!=digest:raise RuntimeError('HELD altered frozen input: '+relative)
        if path.suffix=='.json':frozen[relative]=json.loads(path.read_text())
    def get(name):return frozen['C0/'+name+'.json']
    recipe=checked_json(request['recipe']);binding=checked_json(request['native_binding'])
    release=checked_json(request['runtime_release']);checked_json(request['product_manifest'])
    auth=frozen['C0-authorization-receipt.json'];run=get('release');contract=get('setup-artifact-contract-v1')['contract']
    if (auth['receipt_sha256']!=request['runtime_release']['sha256'] or auth['actual_parent_release']!=release or
        release['recipe_sha256']!=request['recipe']['sha256'] or release['native_binding_sha256']!=request['native_binding']['sha256'] or
        recipe['adapter_sha256']!=request['predecessor_collector']['sha256'] or sha(request['predecessor_collector']['path'])!=recipe['adapter_sha256'] or
        recipe['release_manifest_sha256']!=request['product_manifest']['sha256'] or run['release_sha256']!=request['product_manifest']['sha256'] or
        run['imports']!=recipe['helper_imports'] or run['actual_parent_release_id']!=release['release_id'] or
        contract['recipe_sha256']!=request['recipe']['sha256'] or contract['manifest_sha256']!=request['product_manifest']['sha256'] or
        contract['release_id']!=release['release_id'] or contract['proof_sha256']!=binding['proof_sha256']):
        raise RuntimeError('HELD predecessor source/recipe/release/helper binding')
    b0=get('poststart-baseline-v3');config=get('config-01');turn=get('turn-01');before=b0['first'];after=config['after']
    if not (before==b0['second']==config['before']==get('before-config-01-v3')) or contract['initial_slots']!=before['setup_slots']:
        raise RuntimeError('HELD immutable B0/before/contract mismatch')
    B0_identity={'sealed_original_sha256':get('setup-artifact-contract-v1')['B0_sha256'],'archived_redacted_sha256':canonical_hash(before),
                 'archived_before_bundles_equal':True,'raw_preimage_equality':'NOT_RECONSTRUCTED_FROM_REDACTED_ARCHIVE'}
    root=contract['root'];realroot=contract['realroot'];wire=get('live-rpc/rpc');start=turn['wire_start_index'];end=turn['wire_end_index']
    if end!=len(wire) or not 0<=start<end:raise RuntimeError('HELD incomplete final wire/drain')
    request_turn=wire[start]['payload']
    if (request_turn.get('method')!='turn/start' or request_turn['params']!={'threadId':before['thread_id'],'input':[{'type':'text','text':turn['text']}]} or
        turn['role']!='user' or turn['thread']!=before['thread_id'] or canonical_hash(turn['text'])!=contract['setup_input_sha256'] or
        [x['payload'] for x in wire[start:end] if x['direction']=='response_or_event']!=turn['events'] or
        not healthy_terminal(turn['events'],'live') or not healthy_terminal([x['payload'] for x in wire if x['direction']=='response_or_event'],'live')):
        raise RuntimeError('HELD actual USER/wire/turn/terminal mismatch')
    commands=[]
    for index,event in enumerate(turn['events']):
        item=event.get('params',{}).get('item',{})
        if event.get('method')=='item/completed' and item.get('type')=='commandExecution':
            matches=[i for i,x in enumerate(wire) if x['direction']=='response_or_event' and x['payload']==event]
            if len(matches)!=1:raise RuntimeError('HELD ambiguous command wire event')
            commands.append({'event_index':index,'wire_index':matches[0],'event':event})
    selected=[]
    for role in ('writer','verifier'):
        match=next((x for x in commands if x['event_index']==request[role]['event_index'] and x['wire_index']==request[role]['wire_index']),None)
        if match is None:raise RuntimeError('HELD wrong program event/wire selection')
        item=match['event']['params']['item']
        if item['cwd']!=root or item['status']!='completed' or type(item.get('exitCode')) is not int or item['exitCode']!=0 or not isinstance(item.get('aggregatedOutput'),str):
            raise RuntimeError('HELD incomplete program context/results')
        selected.append(match)
    writer,verifier=selected
    facts=checked_json(request['parent_facts'])
    if (writer['event']!=design['actual_writer_event'] or verifier['event']!=design['actual_verification_event'] or
        [{'event_index':x['event_index'],'event':x['event']} for x in commands]!=design['all_completed_command_events'] or
        facts['actual_completed_item']!=writer['event']['params']['item'] or facts['writer_event_sha256_canonical']!=canonical_hash(writer['event'])):
        raise RuntimeError('HELD exact externally described program/fact binding mismatch')
    for path,digest in facts['raw_bindings'].items():
        relative=str(Path(path).resolve().relative_to(base.resolve()))
        if manifest['files'].get(relative)!=digest:raise RuntimeError('HELD root fact raw binding mismatch')
    sources={}
    for name,reference in request['sources'].items():
        if name not in ('calc.py','tests/test_calc.py') or sha(reference['path'])!=reference['sha256'] or before['setup_scope'][name]['sha256']!=reference['sha256']:
            raise RuntimeError('HELD imported app/test source mismatch')
        if facts['pinned_sources'][name]['sha256']!=reference['sha256']:raise RuntimeError('HELD parent imported source mismatch')
        sources[name]={'reference':reference,'bytes_hex':Path(reference['path']).read_bytes().hex()}
    if set(sources)!= {'calc.py','tests/test_calc.py'} or set(request['generated_expected'])!=set(C0_GENERATED):raise RuntimeError('HELD exact generated/source inventory required')
    generated=[]
    for name in C0_GENERATED:
        observed=after['setup_scope'].get(name)
        if (name in before['setup_scope'] or not observed or observed['sha256']!=request['generated_expected'][name] or
            observed['realpath']!=str(Path(realroot)/name) or any(observed['realpath']==x['realpath'] for x in before['files'].values())):
            raise RuntimeError('HELD generated path/hash/absence/protected-alias mismatch')
        fact=facts['generated_artifacts'][name]
        if fact['realpath']!=observed['realpath'] or fact['sha256']!=observed['sha256'] or fact['path']!=str(Path(root)/name):raise RuntimeError('HELD external artifact fact mismatch')
        generated.append({'relative_path':name,'logical_path':str(Path(root)/name),'realpath':observed['realpath'],
                          'before':'ABSENT_IN_B0_SCOPE','sha256':observed['sha256'],'external_header_fact':fact['header_hex']})
    left=copy.deepcopy(before);right=copy.deepcopy(after)
    for view in (left,right):
        for name in SETUP_SLOTS:
            slot=view['setup_slots'][name];record=view['files'][str(Path(root)/name)]
            if record!={'exists':slot['kind']!='absent','realpath':slot['realpath'],'sha256':slot['sha256']}:raise RuntimeError('HELD instruction sample mismatch')
            view['files'][str(Path(root)/name)]={'exact_instruction_slot':name}
        view['setup_slots']={'exact_instruction_slots':True}
    for name in C0_GENERATED:right['setup_scope'].pop(name)
    if left!=right:raise RuntimeError('HELD unexplained nonartifact/source/config/native/environment delta')
    if (before['setup_slots']['AGENTS.md']!=after['setup_slots']['AGENTS.md'] or before['setup_slots']['CLAUDE.md']['kind']!='absent' or
        after['setup_slots']['CLAUDE.md']['kind']!='regular' or after['setup_slots']['CLAUDE.md']['bytes_hex']!=b'@AGENTS.md\n'.hex()):
        raise RuntimeError('HELD unsupported C0 instruction transition')
    for key,bundle in [('before',before),('after',after)]:
        observed={name:record['sha256'] for name,record in bundle['setup_scope'].items() if not any(x in Path(name).parts for x in ['.git','.agents','.claude','node_modules'])}
        observed.update({name:x['sha256'] for name,x in bundle['setup_slots'].items() if x['kind']!='absent'})
        if turn[key]!=observed:raise RuntimeError('HELD raw turn/scope delta mismatch')
    handoff=frozen['C0-terminal-handoff.json'];operator=frozen['C0-operator-result.json'];closed=get('live-rpc/closed');launch=get('live-rpc/launch')
    if (manifest.get('actual_turns')!=1 or manifest.get('active_owned_processes')!=0 or handoff['actual_model_USER_turns']!=1 or
        handoff['RPC_process_still_active'] is not False or handoff['actual_RPC_process_id']!=before['process_id'] or
        operator['owned_adapter_active'] is not False or operator['exit']!=handoff['adapter_exit'] or not closed['stable'] or
        closed['environment_after']!=launch['environment'] or closed['environment_after']!=after['environment'] or
        handoff['full_closed_rpc_wire_health']['rpc_sha256']!=manifest['files']['C0/live-rpc/rpc.json'] or
        disposition['frozen_C0_report_sha256']!=manifest['files']['REPORT-C0.md']):
        raise RuntimeError('HELD unsupported frozen closure/authority facts')
    for name,source in facts['pinned_sources'].items():
        digest=hashlib.sha256(source['text'].encode()).hexdigest()
        expected=before['setup_slots'][name]['sha256'] if name in SETUP_SLOTS else before['setup_scope'][name]['sha256']
        if digest!=source['sha256'] or digest!=expected:raise RuntimeError('HELD concrete policy/test source bytes mismatch')
    scratch=handoff['unmodeled_external_scratch']
    context={'process_id':before['process_id'],'thread_id':before['thread_id'],
             'turn_id':writer['event']['params']['turnId'],'wire_start_index':start,'wire_end_index':end,
             'wire_sha256':manifest['files']['C0/live-rpc/rpc.json']}
    return {'schema':DERIVATIVE_SCHEMA,'status':'HELD_DERIVATIVE_REQUIRES_ROOT_REVIEW','original_status':manifest['status'],
        'original_failure':{'handoff_status':handoff['status'],'structural_stability':handoff['structural_stability'],'raw_stable':False},
        'request':copy.deepcopy(request),'frozen_files':manifest['files'],'root':root,'contract':contract,
        'baseline':before,'B0_identity':B0_identity,'terminal':after,'post_slots':after['setup_slots'],'events':turn['events'],
        'user_history':[{'role':'user','text':turn['text']}],'original_setup_user_text':turn['text'],'context':context,
        'commands':commands,'writer':writer,'verifier':verifier,'sources':sources,
        'external_parent_facts':request['parent_facts'],'program_inventory':facts['read_import_subprocess_inventory'],'policy_sources':facts['pinned_sources'],
        'generated_artifacts':{'schema':'exact-observed-test-artifacts-v1','items':generated,'generating_context':context,
            'writer_event_sha256':canonical_hash(writer),'sources_sha256':canonical_hash(sources),
            'authority':{'USER_sha256':canonical_hash(turn['text']),'AGENTS_sha256':before['setup_slots']['AGENTS.md']['sha256'],
                         'release_sha256':request['runtime_release']['sha256'],'test_command':'python3 -m unittest discover -s tests -v'},
            'causality_and_inode_ownership':'External semantic review premise; not inferred from pyc suffix or exit zero'},
        'scratch':{'observation':scratch,'historical_preimage':'UNVERIFIED','exclusive_ownership':'UNVERIFIED',
                   'disposition':request['disposition'],'authority_to_repeat_external_write':False},
        'closure':{'schema':'frozen-rpc-operator-closure-v1','app_server_pid':before['process_id'],'app_server_exit_code':None,
            'app_server_exit_code_status':'NOT_RECORDED','closed_rpc_sha256':manifest['files']['C0/live-rpc/closed.json'],
            'whole_wire_sha256':manifest['files']['C0/live-rpc/rpc.json'],'operator_pid':operator['process_id'],'operator_exit':operator['exit'],
            'RPC_active_at_handoff':False,'operator_active_at_result':False,'basis':'Frozen RPC environment/whole wire + operator result + terminal handoff; no invented server returncode'},
        'source_bridge':{'predecessor_collector_sha256':recipe['adapter_sha256'],'predecessor_recipe_sha256':request['recipe']['sha256'],
            'helper_imports':recipe['helper_imports'],'product_manifest_sha256':request['product_manifest']['sha256'],
            'native_binding_sha256':request['native_binding']['sha256'],'recovery_collector_sha256':sha(__file__)},
        'authorizes_dispatch':False,'business_acceptance':False}


def pinned_source_ast(reference, names):
    """Read only explicitly hash-bound source; never import/execute archived code."""
    if sha(reference['path'])!=reference['sha256']:raise RuntimeError('HELD classifier/producer source hash')
    old=ast.parse(Path(reference['path']).read_text());current=ast.parse(Path(__file__).read_text())
    for name in names:
        nodes=[[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name==name] for tree in (old,current)]
        if any(len(x)!=1 for x in nodes) or ast.dump(nodes[0][0])!=ast.dump(nodes[1][0]):raise RuntimeError('HELD changed source-bound classifier/producer: '+name)


def retained_trust_edge(before, after, root):
    """Finite retained schema/hash relation; raw leaf preservation is NOT replayed."""
    a=copy.deepcopy(before);b=copy.deepcopy(after)
    users=[i for i,x in enumerate(a['layers']) if x['source'].get('type')=='user']
    if len(users)!=1:raise RuntimeError('HELD unknown user layer')
    i=users[0]
    if b['layers'][i]['source']!=a['layers'][i]['source'] or a['layers'][i]['version']==b['layers'][i]['version']:
        raise RuntimeError('HELD source/version trust edge mismatch')
    for left,right in [(a['safe_identity'],b['safe_identity']),(a['layers'][i]['safe_identity'],b['layers'][i]['safe_identity'])]:
        old=left['schema']['projects'];new=right['schema']['projects']
        if root in old or new.get(root)!={'trust_level':'str'}:raise RuntimeError('HELD unknown/new trust schema root')
        new.pop(root);right['fields']['projects']=left['fields']['projects'];right['sha256']=left['sha256']
    ri=b['response_identity'];li=a['response_identity']
    for path in [ri['schema']['config']['projects'],ri['schema']['layers'][i]['config']['projects']]:
        if path.pop(root,None)!={'trust_level':'str'}:raise RuntimeError('HELD response project schema mismatch')
    origin='projects.'+root+'.trust_level'
    if ri['schema']['origins'].pop(origin,None)!={'name':{'type':'str','file':'str','profile':'NoneType'},'version':'str'}:
        raise RuntimeError('HELD unknown origin schema')
    for name in ('config','layers','origins'):ri['fields'][name]=li['fields'][name]
    ri['sha256']=li['sha256'];b['layers'][i]['version']=a['layers'][i]['version']
    if a!=b:raise RuntimeError('HELD unknown retained config/model/MCP/source/origin difference')


def inspect_intercontext_bridge(d, reference):
    receipt=checked_json(reference)
    if (receipt.get('schema')!='C1_INTERCONTEXT_TRUST_BRIDGE_V1' or checked_json(receipt['derivative'])!=d or
        receipt.get('derivative_canonical_sha256')!=canonical_hash(d) or receipt.get('validator_sha256')!=sha(__file__) or
        receipt.get('evidence_boundary')!='RECORDED_RAW_COMPARATOR_UNDER_EXPLICIT_ROOT_TRUST_NOT_INDEPENDENT_RAW_REPLAY'):
        raise RuntimeError('HELD exact immutable derivative/validator/observer boundary')
    audit=checked_json(receipt['audit']);plan=checked_json(receipt['plan_review']);disposition=checked_json(receipt['disposition'])
    if (plan.get('verdict')!='APPROVE_BOUNDED_INTERCONTEXT_BRIDGE_PLAN' or
        not plan.get('finite_recorded_comparator_reliance_accepted') or
        sha(receipt['plan_report']['path'])!=plan['report_sha256'] or receipt['plan_report']['sha256']!=plan['report_sha256'] or
        sha(receipt['audit_report']['path'])!=audit['report_sha256'] or receipt['audit_report']['sha256']!=audit['report_sha256'] or
        disposition.get('audit_report_sha256')!=audit['report_sha256']):raise RuntimeError('HELD plan/disposition evidence')
    for key in ('audit','audit_report','disposition'):
        if not any(Path(x['path']).resolve()==Path(receipt[key]['path']).resolve() and x['sha256']==receipt[key]['sha256'] for x in plan['inputs']):
            raise RuntimeError('HELD unreviewed plan dependency')
    producer=receipt['producer'];producer_review=checked_json(receipt['producer_review'])
    if (producer['sha256']!=d['source_bridge']['recovery_collector_sha256'] or producer['sha256']!=audit['source_contract']['current_collector_sha256'] or
        producer_review.get('collector_sha256')!=producer['sha256'] or producer_review.get('verdict')!='APPROVE_BOUNDED_DERIVATIVE_RECOVERY' or
        sha(producer_review['report']['path'])!=producer_review['report']['sha256']):raise RuntimeError('HELD producer identity/prior approval')
    for pin in audit['frozen_named_snapshots']+audit['supporting_inputs']:
        actual=producer['sha256'] if Path(pin['path']).resolve()==Path(__file__).resolve() else sha(pin['path'])
        if actual!=pin['sha256_start'] or pin['sha256_start']!=pin['sha256_end']:raise RuntimeError('HELD changed captured audit/source input')
    prior_report=next(x for x in audit['supporting_inputs'] if x['path'].endswith('codex-c0-derivative-recovery-review-r1/REPORT.md'))
    if producer_review['report']['sha256']!=prior_report['sha256_start']:raise RuntimeError('HELD wrong actual producer approval')
    pinned_source_ast(producer,['recover_frozen_c0','checked_json','canonical_hash','sha','healthy_terminal','startup_relation','validate_startup'])
    frames=receipt.get('contexts',[])
    if len(frames)!=4 or len(audit['contexts'])!=4:raise RuntimeError('HELD exact four-context chain required')
    pins={str(Path(x['path']).resolve()):x['sha256_start'] for x in audit['frozen_named_snapshots']}
    previous=None;user_path=receipt['config_path'];outcomes=[]
    for i,(frame,known,edge) in enumerate(zip(frames,audit['contexts'],audit['startup_edges'])):
        for key,named in [('baseline','baseline_path'),('startup','startup_path')]:
            if Path(frame[key]['path']).resolve()!=Path(known[named]).resolve():raise RuntimeError('HELD reordered/cross-context frame')
        for key in ('baseline','startup','thread'):
            if pins.get(str(Path(frame[key]['path']).resolve()))!=frame[key]['sha256']:raise RuntimeError('HELD unpinned startup/native frame')
        baseline=checked_json(frame['baseline']);startup=checked_json(frame['startup']);thread=checked_json(frame['thread'])
        first=baseline['first'];pre=startup['preflight'];post=startup['post_start'];native=checked_json(frame['native'])
        if not first==baseline['second']==post or startup.get('classified_relation')!='persisted-trust-only':raise RuntimeError('HELD unstable/unclassified poststart pair')
        if baseline['snapshot']!=known['thread'] or thread['request']!=baseline['snapshot']['request_overlays'] or any(thread['response'].get(k)!=baseline['snapshot']['snapshot'][k] for k in THREAD_FIELDS):
            raise RuntimeError('HELD actual native snapshot/request mismatch')
        if thread['response']['thread']['id']!=first['thread_id'] or thread['process_id']!=first['process_id'] or frame['trust_root']!=edge['added_schema_roots'][0]:raise RuntimeError('HELD unknown root/thread/process')
        if {k:v for k,v in pre['files'][user_path].items() if k!='sha256'}!={k:v for k,v in first['files'][user_path].items() if k!='sha256'}:raise RuntimeError('HELD startup user file identity changed')
        if first['files'][user_path]!=known['user_file'] or pre['files'][user_path]['sha256']!=edge['user_raw_before'] or first['files'][user_path]['sha256']!=edge['user_raw_after']:
            raise RuntimeError('HELD raw file endpoint mismatch')
        if previous and (pre['config']!=previous['config'] or pre['files'][user_path]!=previous['files'][user_path]):raise RuntimeError('HELD discontinuous intercontext chain')
        retained_trust_edge(pre['config'],first['config'],frame['trust_root'])
        if (any(v is not False for v in first['config']['effective']['canonical_features'].values()) or
            any(v is not False for v in first['config']['effective']['discovery'].values()) or not first['config']['effective']['include_instructions'] or
            native.get('status')!='BOUND_ACTUAL_RECEIPTS' or native['catalog']!=first['catalog_proof'] or native['catalog']['enabled_unique_targets']!=16 or native['catalog']['load_errors']!=0):
            raise RuntimeError('HELD native/catalog/contributor premise')
        run=checked_json(frame['recorded_release']);release=checked_json(frame['release']);auth=checked_json(frame['authorization']);binding=checked_json(frame['binding'])
        authority=auth.get('actual_parent_release',auth.get('release',auth.get('actual_release')))
        release_hash=auth.get('receipt_sha256',auth.get('release_sha256'))
        selected_binding=({'path':release['native_binding_path'],'sha256':release['native_binding_sha256']} if i==0 else release['native_bindings'][Path(frame['baseline']['path']).parent.name])
        if (authority!=release or release_hash!=frame['release']['sha256'] or release.get('explicit_parent_model_release') is not True or
            run['actual_parent_release_id']!=release['release_id'] or run['root']!=baseline['snapshot']['snapshot']['cwd'] or
            binding['parent_release_id']!=release['release_id'] or selected_binding['sha256']!=frame['binding']['sha256'] or
            binding['forward_trust_root']!=frame['trust_root'] or run['reviewed_native_binding']['forward_trust_root']!=frame['trust_root'] or
            run['reviewed_native_binding']['forward_thread_expectation']!=baseline['snapshot']['snapshot'] or
            frame['source']['sha256']!=release['adapter_sha256'] or release['source_manifest_sha256']!=d['source_bridge']['product_manifest_sha256']):
            raise RuntimeError('HELD existing actual parent root/source/release binding')
        pinned_source_ast(frame['source'],['startup_relation','validate_startup'])
        closed=checked_json(frame['closed_rpc']);wire=checked_json(frame['wire']);operator=checked_json(frame['operator']);fact=checked_json(frame['closure'])
        if not closed['stable'] or closed['environment_after']!=first['environment']:raise RuntimeError('HELD closed environment receipt')
        if i==0:
            closed_ok=fact.get('RPC_process_still_active') is False and operator.get('owned_adapter_active') is False and fact['actual_RPC_process_id']==first['process_id'] and fact['adapter_exit']==operator['exit'] and fact['full_closed_rpc_wire_health']['rpc_sha256']==frame['wire']['sha256']
        elif i==1:
            closed_ok=operator.get('adapter_closed') is True and fact==operator and not any(x['payload'].get('method')=='turn/start' for x in wire)
        else:
            wire_sha=fact.get('wire_sha256',fact.get('whole_wire_sha256'))
            closed_ok=operator.get('adapter_closed') is True and fact.get('server_active') is False and fact['actual_server_pid']==first['process_id'] and fact['adapter_exit']==operator['exit'] and wire_sha==frame['wire']['sha256']
        if not closed_ok:raise RuntimeError('HELD actual context closure/whole-wire facts')
        # Sidecars are bound to these exact known context directories, never
        # substituted from another context just because fields look similar.
        folder=Path(frame['baseline']['path']).parent
        operator_path=folder.parent/('C0-operator-result.json' if i==0 else folder.name+'-operator-result.json')
        closure_path=folder.parent/'C0-terminal-handoff.json' if i==0 else operator_path if i==1 else folder.parent/('default-r7-build-questions-closure-inspection.json' if i==2 else 'copy-timeout-handoff.json')
        auth_path=folder.parent/('C0-authorization-receipt.json' if i==0 else 'authorization-receipt.json')
        if any(Path(frame[key]['path']).resolve()!=path.resolve() for key,path in [('operator',operator_path),('closure',closure_path),('authorization',auth_path)]):raise RuntimeError('HELD wrong actual context closure/release receipt')
        for key,suffix in [('startup','startup-diagnostic-v3.json'),('thread','thread-start-v3.json'),('native','live-native-selection-receipt.json'),('recorded_release','release.json'),('closed_rpc','live-rpc/closed.json'),('wire','live-rpc/rpc.json')]:
            if Path(frame[key]['path']).resolve()!=(folder/suffix).resolve():raise RuntimeError('HELD cross-context sidecar')
        previous=first;outcomes.append({'thread_id':first['thread_id'],'closure':frame['closure'],'operator':frame['operator'],'source':frame['source']})
    if (receipt['old_user_file']!=d['terminal']['files'][user_path] or receipt['old_user_file']!=audit['contexts'][0]['user_file'] or
        receipt['endpoint_user_file']!=previous['files'][user_path] or {k:v for k,v in receipt['old_user_file'].items() if k!='sha256'}!={k:v for k,v in receipt['endpoint_user_file'].items() if k!='sha256'}):
        raise RuntimeError('HELD exact one-file old/endpoint identity')
    witness=checked_json(receipt['endpoint_witness'])
    if (witness.get('status')!='ENDPOINT_MATCH_AFTER_CLOSED_QUESTION_CONTEXTS' or witness['actual_path']!=user_path or
        witness['actual_current_config_sha256']!=receipt['endpoint_user_file']['sha256'] or witness['captured_endpoint_sha256']!=receipt['endpoint_user_file']['sha256'] or
        witness['actual_realpath']!=user_path or witness['captured_realpath']!=receipt['endpoint_user_file']['realpath'] or
        witness['endpoint_frame']!=frames[-1]['baseline'] or sha(witness['closed_actor_report']['path'])!=witness['closed_actor_report']['sha256']):
        raise RuntimeError('HELD after-close endpoint witness')
    return receipt


def verify_derivative_producer(d, recipe):
    recomputed=recover_frozen_c0(d['request']);current=sha(__file__)
    if recomputed==d and not recipe.get('intercontext_bridge'):return None
    reference=recipe.get('intercontext_bridge')
    if not reference:raise RuntimeError('HELD immutable derivative producer change requires explicit bridge')
    receipt=inspect_intercontext_bridge(d,reference)
    # No old code runs and no derivative changes. Exactly one known producer
    # field may differ in the CURRENT recomputation; all other data is equal.
    if (recomputed['source_bridge']!={**d['source_bridge'],'recovery_collector_sha256':current} or
        {k:v for k,v in recomputed.items() if k!='source_bridge'}!={k:v for k,v in d.items() if k!='source_bridge'}):
        raise RuntimeError('HELD derivative recomputation differs beyond producer identity')
    return receipt


def validate_derivative_current(derivative, recipe):
    """Current C1 check only. Offline derivation never calls this live reader."""
    intercontext=inspect_intercontext_bridge(derivative,recipe['intercontext_bridge']) if recipe.get('intercontext_bridge') else None
    root=Path(derivative['root']);terminal=derivative['terminal'];bridge=derivative['source_bridge']
    protected=[path for path in terminal['files'] if path not in {str(root/name) for name in SETUP_SLOTS}]
    if setup_slots(root,protected)!=derivative['post_slots'] or setup_scope(root)!=terminal['setup_scope']:
        raise RuntimeError('HELD stale derivative consumer/postimage/topology/scope')
    protected_ids={(st.st_dev,st.st_ino) for st in [p.stat() for p in map(Path,protected) if p.is_file()]}
    for item in derivative['generated_artifacts']['items']:
        p=Path(item['logical_path']);st=p.lstat()
        if not stat.S_ISREG(st.st_mode) or (st.st_dev,st.st_ino) in protected_ids or str(p.resolve())!=item['realpath'] or sha(p)!=item['sha256']:
            raise RuntimeError('HELD current generated artifact/protected alias mismatch')
    for path,record in terminal['files'].items():
        p=Path(path);expected=record['sha256']
        if p.resolve()==Path(__file__).resolve():
            if expected!=bridge['predecessor_collector_sha256']:raise RuntimeError('HELD unbound old collector identity')
            expected=intercontext['validator_sha256'] if intercontext else bridge['recovery_collector_sha256']
        if intercontext and path==intercontext['config_path']:
            if record!=intercontext['old_user_file']:raise RuntimeError('HELD wrong C0 config starting identity')
            expected=intercontext['endpoint_user_file']['sha256']
        realpath=str(p.resolve()).replace(str(Path.home()),'<HOST_HOME>') if '<HOST_HOME>' in record['realpath'] else str(p.resolve())
        if p.exists()!=record['exists'] or realpath!=record['realpath'] or (sha(p) if p.is_file() else None)!=expected:
            raise RuntimeError('HELD stale derivative protected/source file')


PENDING_ACK_RECEIPT = {'path':str(SOURCE/'.omx/ultragoal/evidence/g004/codex/native-v9/runs-C1-source62-operatorfix-RELEASE-REQUIRED/FROZEN-MANIFEST.json'),
    'sha256':'9f20bb6421b29d2c09f15ff258840d9896b1ad72cd3dd6804e6d11dcd97bfa5b'}


def pending_repeat_ack_facts(d, recipe, intercontext):
    """One frozen source62 acknowledgement, never a generic history waiver."""
    reference=recipe.get('pending_repeat_ack')
    if reference!=PENDING_ACK_RECEIPT or not intercontext:raise RuntimeError('HELD exact frozen pending acknowledgement/bridge required')
    manifest=checked_json(reference);base=Path(reference['path']).parent
    for rel,digest in manifest['files'].items():
        if sha(base/rel)!=digest:raise RuntimeError('HELD pending acknowledgement frozen input changed')
    def load(name):return json.loads((base/name).read_text())
    held=load('setup-terminal-held-facts-v2.json');turn=load('turn-01.json');wire=load('live-rpc/rpc.json')
    pair=load('poststart-baseline-v3.json');config=load('config-01.json');before=load('before-config-01-v3.json')
    launch=load('operator-launch.json');operator=load('operator-result.json');delivered=load('operator-stdin-deliveries.json')
    run=load('release.json');continuation=load('setup-continuation-input-v1.json');results=load('RESULTS.json')
    argv=launch['argv'];old_recipe_path=Path(argv[argv.index('--prepared')+1])/'recipe.json'
    old_recipe=json.loads(old_recipe_path.read_text());old_release=continuation['derivative_relation']['release']
    root_records=Path(argv[argv.index('--derivative-release')+1]).parent
    for name,digest in results['root_record_hashes'].items():
        if sha(root_records/name)!=digest:raise RuntimeError('HELD pending acknowledgement original authority record changed')
    source62='62c268d75834d76026639cf5b585c3c289d8da8afd14c7ae38129e0d8423676e'
    ack=recipe.get('setup_content_ack_text');repeat=recipe.get('setup_repeat_text');root=d['root'];terminal=held['terminal']
    if (old_recipe['adapter_sha256']!=source62 or sha(old_recipe_path)!=old_release['recipe_sha256'] or
        run['root']!=root or old_release['same_consumer']!=root or run['actual_parent_release_id']!=old_release['release_id'] or
        continuation['predecessor_derivative_sha256']!=canonical_hash(d) or
        ack!=old_recipe['setup_content_ack_text'] or repeat!=old_recipe['setup_repeat_text'] or repeat!=d['original_setup_user_text'] or
        old_recipe['helper_imports']!=recipe['helper_imports'] or old_recipe['release_manifest_sha256']!=d['source_bridge']['product_manifest_sha256'] or
        old_recipe['checkpoint_installed']!=d['terminal']['installed'] or old_release['max_new_model_USER_turns']!=2):
        raise RuntimeError('HELD original acknowledgement recipe/root/source/dependency relation')
    rows=recipe.get('rows',[])
    if (len(rows)!=1 or rows[0].get('id')!=run['row']['id'] or rows[0].get('transport')!='live' or rows[0].get('mode')!='copy' or
        type(rows[0].get('max_user_turns')) is not int or rows[0]['max_user_turns']!=1 or rows[0].get('initial_user_text')!=repeat):
        raise RuntimeError('HELD one pending original repeat row required')
    requests=[e['payload'] for e in wire if e['direction']=='request' and e['payload'].get('method')=='turn/start']
    start=held['wire_start_index'];end=held['wire_end_index']
    events=[e['payload'] for e in wire[start:end] if e['direction']=='response_or_event']
    if (len(delivered)!=2 or delivered[0]['object']!=continuation['actual_USER_approval'] or delivered[1]['object']!={'text':ack} or
        len(requests)!=1 or requests[0]['params']!={'threadId':held['thread_id'],'input':[{'type':'text','text':ack}]} or
        held['user_history']!=[{'role':'user','text':ack}] or turn['text']!=ack or turn['thread']!=held['thread_id'] or
        turn['wire_start_index']!=start or turn['wire_end_index']!=end or end!=len(wire) or
        turn['events']!=events or not healthy_terminal(events,'live') or
        sum(e.get('method')=='turn/completed' for e in events)!=1 or
        any(('id' in e and 'method' in e) or (e.get('method')=='item/completed' and e.get('params',{}).get('item',{}).get('type') not in ('userMessage','agentMessage')) for e in events)):
        raise RuntimeError('HELD exact single actual acknowledgement/full drained wire/provenance')
    # Direct held facts and ar.write receipts have distinct redaction forms.
    # Check equality within each actual channel, and their retained config
    # identity digests; never reconstruct lost raw preimages or in-memory types.
    identity=json.dumps(terminal,sort_keys=True);sampled=json.dumps(pair['first'],sort_keys=True)
    if (json.dumps(held['baseline'],sort_keys=True)!=identity or
        any(json.dumps(x,sort_keys=True)!=sampled for x in (pair['second'],before,config['before'],config['after'])) or
        any(terminal['config'][key]['sha256']!=pair['first']['config'][key]['sha256'] for key in ('safe_identity','response_identity')) or
        any(terminal[k]!=pair['first'][k] for k in ('setup_slots','setup_scope','process_id','thread_id')) or
        config.get('raw_stable') is not True or config.get('baseline_reset_allowed') is not False or turn['before']!=turn['after']):
        raise RuntimeError('HELD acknowledgement raw baseline/config drift')
    if (held.get('closed') is not True or type(held.get('closed_process_returncode')) is not int or held['closed_process_returncode']!=0 or
        held.get('reason')!='UNVERIFIED actual setup USER provenance' or held.get('authorizes_dispatch') is not False or
        held['closure_receipt_path']!=str(base/'live-rpc/closed.json') or sha(held['closure_receipt_path'])!=held['closure_receipt_sha256'] or
        operator.get('adapter_exit')!=1 or operator.get('server_exit_code') is not None or operator.get('model_USER_inputs_delivered')!=1 or
        load('live-rpc/closed.json').get('stable') is not True or load('live-rpc/closed.json')['environment_after']!=pair['first']['environment'] or
        results.get('repeat_delivered') is not False or results.get('actual_MODEL_USER_turns')!=1 or results.get('no_owned_live') is not True):
        raise RuntimeError('HELD actual closed acknowledgement with unused repeat missing')
    if (terminal['setup_slots']!=d['post_slots'] or terminal['setup_scope']!=d['terminal']['setup_scope'] or len(terminal['setup_scope'])!=67 or
        launch['consumer_before']!=terminal['setup_scope'] or operator['consumer_after']!=terminal['setup_scope'] or
        terminal['installed']!=d['terminal']['installed'] or run['imports']!=recipe['helper_imports']):
        raise RuntimeError('HELD unchanged acknowledgement consumer/slot/cache/install scope')
    expected=copy.deepcopy(d['terminal']['files']);observed=copy.deepcopy(terminal['files'])
    config_path=intercontext['config_path']
    if expected[config_path]!=intercontext['old_user_file']:raise RuntimeError('HELD wrong original config identity')
    expected[config_path]=copy.deepcopy(intercontext['endpoint_user_file'])
    collector_path=str(Path(__file__).resolve())
    expected[collector_path]['sha256']=source62
    for path,record in expected.items():
        if path in observed and '<HOST_HOME>' in record['realpath']:
            observed[path]['realpath']=observed[path]['realpath'].replace(str(Path.home()),'<HOST_HOME>')
    if observed!=expected:raise RuntimeError('HELD acknowledgement protected/source/fixed config relation')
    thread=load('thread-start-v3.json');native=load('live-native-selection-receipt.json');snapshot=pair['snapshot']['snapshot']
    binding=run['reviewed_native_binding']
    if (binding['adapter_sha256']!=source62 or binding['forward_thread_expectation']!=snapshot or snapshot['cwd']!=root or
        set(snapshot)!=set(THREAD_FIELDS) or any(thread['response'].get(k)!=snapshot[k] for k in THREAD_FIELDS) or
        thread['process_id']!=held['process_id'] or thread['response']['thread']['id']!=held['thread_id'] or
        terminal['process_id']!=held['process_id'] or terminal['thread_id']!=held['thread_id'] or
        native.get('status')!='BOUND_ACTUAL_RECEIPTS' or native['catalog']!=pair['first']['catalog_proof'] or
        native['catalog']['enabled_unique_targets']!=16 or native['catalog']['load_errors']!=0 or
        native['environment']['selected_environment_kind']!='local' or native['environment']['required_skills']!=[] or
        any(v is not False for v in terminal['config']['effective']['canonical_features'].values()) or
        any(v is not False for v in terminal['config']['effective']['discovery'].values()) or not terminal['config']['effective']['include_instructions']):
        raise RuntimeError('HELD acknowledgement actual native13/catalog/environment/settings')
    reconcile_thread(thread['response'],thread['request'],snapshot)
    component_ref={'path':str(SOURCE/'.omx/ultragoal/evidence/r7-parent-verification/C1-source62-acknowledgement-component-review.json'),
        'sha256':'bac6b59fcf5d32b1b4a194a15a9f7f358c0ca5f6d6a0bd0b5b265d01c596f48c'}
    component=checked_json(component_ref)
    for ref in component['references']:
        if sha(ref['path'])!=ref['sha256']:raise RuntimeError('HELD ROOT acknowledgement component input changed')
    replies=[e['params']['item']['text'] for e in events if e.get('method')=='item/completed' and e.get('params',{}).get('item',{}).get('type')=='agentMessage']
    if (component.get('status')!='ACTUAL_ACKNOWLEDGEMENT_ACCEPTED_AS_COMPLETED_COMPONENT_ONLY' or
        component.get('actual_USER_text_sha256')!=hashlib.sha256(ack.encode()).hexdigest() or replies!=[component['actual_model_response']] or
        component.get('context_turns')!=1 or component.get('authorizes_model_dispatch') is not False):
        raise RuntimeError('HELD exact ROOT acknowledgement semantic component missing')
    return {'receipt':reference,'root_ack_component':component_ref,'root':root,'derivative_sha256':canonical_hash(d),'predecessor_collector_sha256':source62,
        'predecessor_recipe_sha256':sha(old_recipe_path),'predecessor_release_sha256':canonical_hash(old_release),'predecessor_release_id':old_release['release_id'],
        'acknowledgment_sha256':canonical_hash(ack),'pending_repeat_sha256':canonical_hash(repeat),
        'whole_wire_sha256':sha(base/'live-rpc/rpc.json'),'terminal_bundle_sha256':canonical_hash(terminal),
        'consumer_scope_sha256':canonical_hash(terminal['setup_scope']),'slots_sha256':canonical_hash(terminal['setup_slots']),
        'native_snapshot_sha256':canonical_hash(snapshot),'closure_sha256':canonical_hash({k:held[k] for k in ('closed','closed_process_returncode','closure_receipt_path','closure_receipt_sha256')})}


def validate_derivative_continuation(d, review, approval, root, recipe, manifest_sha256, release):
    """External PROGRAM semantics are a declared parent trust boundary, not a parser."""
    if d.get('schema')!=DERIVATIVE_SCHEMA:raise RuntimeError('HELD altered/unverifiable derivative')
    intercontext=verify_derivative_producer(d,recipe)
    digest=canonical_hash(d);collector=sha(__file__);bridge=d['source_bridge']
    expected_bridge={'predecessor_collector_sha256':bridge['predecessor_collector_sha256'],
        'predecessor_recipe_sha256':bridge['predecessor_recipe_sha256'],'collector_sha256':collector,
        'product_manifest_sha256':bridge['product_manifest_sha256'],'helper_imports_sha256':canonical_hash(bridge['helper_imports'])}
    if intercontext:
        expected_bridge.update(producer_collector_sha256=bridge['recovery_collector_sha256'],intercontext_bridge_sha256=recipe['intercontext_bridge']['sha256'])
    if (str(root)!=d['root'] or recipe.get('derivative_source_bridge')!=expected_bridge or recipe.get('adapter_sha256')!=collector or
        (collector!=bridge['recovery_collector_sha256'] and intercontext is None) or manifest_sha256!=bridge['product_manifest_sha256'] or
        recipe.get('helper_imports')!=bridge['helper_imports'] or recipe.get('checkpoint_installed')!=d['terminal']['installed'] or
        recipe.get('predecessor_user_history')!=d['user_history'] or recipe.get('predecessor_recipe_sha256')!=bridge['predecessor_recipe_sha256']):
        raise RuntimeError('HELD explicit old/new collector/source/recipe/history bridge mismatch')
    program=review.get('program',{});generated=review.get('generated',{});content=review.get('content',{});scratch=review.get('scratch',{})
    expected_program={'schema':'EXTERNALLY_REVIEWED_PROGRAM_V1','derivative_sha256':digest,'context':d['context'],
        'commands_sha256':canonical_hash(d['commands']),'writer':d['writer'],'verifier':d['verifier'],
        'inventory':d['program_inventory'],'post_slots_sha256':canonical_hash(d['post_slots']),
        'full_scope_delta_sha256':canonical_hash({'before':d['baseline']['setup_scope'],'after':d['terminal']['setup_scope']}),
        'policy_sources_sha256':canonical_hash(d['policy_sources']),'parent_facts':d['external_parent_facts']}
    if {k:v for k,v in program.items() if k!='evidence'}!=expected_program:
        raise RuntimeError('HELD exact program/target/inventory/policy review binding')
    topics={'outer_quoting','imports','reads','writes','subprocesses','authority','scratch','limitations'}
    if not isinstance(program.get('evidence'),dict) or set(program['evidence'])!=topics or any(not isinstance(v,str) or not v.strip() for v in program['evidence'].values()):
        raise RuntimeError('HELD concrete external program semantics missing')
    if (generated.get('receipt_sha256')!=canonical_hash(d['generated_artifacts']) or generated.get('items')!=d['generated_artifacts']['items'] or
        not isinstance(generated.get('evidence'),dict) or set(generated['evidence'])!=set(C0_GENERATED) or any(not isinstance(v,str) or not v.strip() for v in generated['evidence'].values())):
        raise RuntimeError('HELD exact generated artifact classification review missing')
    if (content.get('post_slots_sha256')!=canonical_hash(d['post_slots']) or content.get('policy_sources_sha256')!=canonical_hash(d['policy_sources']) or
        not isinstance(content.get('evidence'),str) or not content['evidence'].strip()):raise RuntimeError('HELD actual root content/preservation review missing')
    expected_scratch={'disposition':d['request']['disposition'],'observation':d['scratch']['observation'],'historical_preimage':'UNVERIFIED',
        'exclusive_ownership':'UNVERIFIED','decision':'ACCEPT_FINITE_OBSERVATION_WITH_UNVERIFIED_HISTORICAL_OWNERSHIP','authority_to_repeat_external_write':False}
    if {k:v for k,v in scratch.items() if k!='evidence'}!=expected_scratch or not isinstance(scratch.get('evidence'),str) or not scratch['evidence'].strip():
        raise RuntimeError('HELD scratch policy/uncertainty adjudication missing')
    if intercontext:
        trust=review.get('intercontext_bridge_review',{})
        expected={'receipt':recipe['intercontext_bridge'],'producer':intercontext['producer'],
            'decision':'ACCEPT_RECORDED_CLASSIFIER_UNDER_EXPLICIT_ROOT_TRUST',
            'limits':{'raw_projects_origins_reconstructed':False,'independent_raw_replay':False,
                      'raw_file_hash_equality_claim':False,'exclusive_historical_causality':False}}
        if {k:v for k,v in trust.items() if k!='evidence'}!=expected or not isinstance(trust.get('evidence'),str) or not trust['evidence'].strip():
            raise RuntimeError('HELD explicit root trust/classification-limit review missing')
    source_review=checked_json(review['independent_source_review'])
    report_ref=source_review.get('report',{})
    if (source_review.get('collector_sha256')!=collector or source_review.get('verdict')!=('APPROVE_BOUNDED_INTERCONTEXT_BRIDGE_IMPLEMENTATION' if intercontext else 'APPROVE_BOUNDED_DERIVATIVE_RECOVERY') or
        not report_ref.get('path') or not report_ref.get('sha256') or sha(report_ref['path'])!=report_ref['sha256']):
        raise RuntimeError('HELD new independent collector review missing')
    root_review=checked_json(review['root_review'])
    expected_root={'schema':'ROOT_C0_DERIVATIVE_ADJUDICATION_V1','derivative_sha256':digest,
        'program_review_sha256':canonical_hash(program),'generated_review_sha256':canonical_hash(generated),
        'content_review_sha256':canonical_hash(content),'scratch_review_sha256':canonical_hash(scratch),
        'closure_sha256':canonical_hash(d['closure']),'B0_identity_sha256':canonical_hash(d['B0_identity']),
        'independent_source_review':review['independent_source_review'],'decision':'ELIGIBLE_FOR_BOUNDED_C1_AFTER_NEW_RELEASE_AND_USER'}
    if intercontext:expected_root['intercontext_bridge_review_sha256']=canonical_hash(review['intercontext_bridge_review'])
    pending=None
    if recipe.get('pending_repeat_ack'):
        pending=pending_repeat_ack_facts(d,recipe,intercontext)
        ack_review=checked_json(review['pending_repeat_ack_review'])
        expected_ack={'schema':'ROOT_C1_PENDING_REPEAT_ACK_REVIEW_V1','facts':pending,
            'independent_source_review':review['independent_source_review'],
            'decision':'ACCEPT_EXACT_OBSERVED_ACK_NO_EDITS_NO_UNRESOLVED_JUDGMENT_FOR_ONE_PENDING_REPEAT'}
        if ({k:v for k,v in ack_review.items() if k!='report'}!=expected_ack or
            sha(ack_review['report']['path'])!=ack_review['report']['sha256']):
            raise RuntimeError('HELD concrete ROOT acknowledgement/content/no-judgment review missing')
        expected_root['pending_repeat_ack_review']=review['pending_repeat_ack_review']
        bindings={'pending_repeat_ack_sha256':recipe['pending_repeat_ack']['sha256'],
                  'pending_repeat_ack_review_sha256':review['pending_repeat_ack_review']['sha256']}
        if (any(release.get(k)!=v or approval.get(k)!=v for k,v in bindings.items()) or
            release.get('release_id')==pending['predecessor_release_id'] or
            any(type(release.get(k)) is not int or release[k]!=v for k,v in {'actual_before':20,'held_before':86,'whole_ceiling':106}.items())):
            raise RuntimeError('HELD exact pending acknowledgement/new release/actual USER/quota binding')
    if root_review!=expected_root:raise RuntimeError('HELD actual root derivative/closure/redaction-boundary review missing')
    if intercontext and (release.get('intercontext_bridge_sha256')!=recipe['intercontext_bridge']['sha256'] or release.get('producer_collector_sha256')!=bridge['recovery_collector_sha256']):raise RuntimeError('HELD exact bridge/new release binding')
    if (release.get('scope')!='C1_FROM_REVIEWED_DERIVATIVE' or release.get('explicit_parent_model_release') is not True or
        not isinstance(release.get('release_id'),str) or not release['release_id'] or release['release_id']==d['contract']['release_id'] or release.get('derivative_sha256')!=digest or
        release.get('collector_sha256')!=collector or type(release.get('max_new_contexts')) is not int or release['max_new_contexts']!=1 or type(release.get('max_new_model_USER_turns')) is not int or release['max_new_model_USER_turns']!=(1 if pending else 2) or
        release.get('recipe_sha256')!=recipe.get('_verified_recipe_sha256') or not recipe.get('_verified_recipe_sha256') or
        release.get('review_sha256')!=canonical_hash(review)):
        raise RuntimeError('HELD separate exact derivative C1 release missing')
    if intercontext and approval.get('intercontext_bridge_sha256')!=recipe['intercontext_bridge']['sha256']:raise RuntimeError('HELD actual USER has not bound the intercontext receipt')
    if (approval.get('role')!='user' or approval.get('action')!='approve_C1_from_derivative' or approval.get('new_context') is not True or
        approval.get('derivative_sha256')!=digest or approval.get('review_sha256')!=canonical_hash(review) or
        approval.get('release_sha256')!=canonical_hash(release) or not isinstance(approval.get('text'),str) or not approval['text'].strip()):
        raise RuntimeError('HELD separate actual external USER derivative approval missing')
    if recipe.get('setup_repeat_text')!=d['original_setup_user_text'] or not recipe.get('setup_content_ack_text'):
        raise RuntimeError('HELD new content acknowledgment/original repeat input contract')
    validate_derivative_current(d,recipe)
    return {'explicit_new_context':True,'predecessor_derivative_sha256':digest,'actual_USER_approval':approval,'review':review,
            **({'pending_repeat_ack':pending} if pending else {}),
            'derivative_relation':{'schema':DERIVATIVE_SCHEMA,'closure':d['closure'],'source_bridge':expected_bridge,'release':release}}


def reviewed_literal_setup_commands(checkpoint, review):
    """Finite printf data relation, not a shell executor or host-security proof."""
    if checkpoint.get('closed') is not True:raise RuntimeError('HELD command predecessor not closed')
    context={k:checkpoint.get(k) for k in ('process_id','thread_id','wire_start_index','wire_end_index')}
    turns={e.get('params',{}).get('turn',{}).get('id') for e in checkpoint['events']
           if isinstance(e,dict) and e.get('method')=='turn/completed'}
    if (not healthy_terminal(checkpoint['events'],'live') or len(turns)!=1 or not isinstance(next(iter(turns),None),str) or not next(iter(turns),None) or
        type(context['process_id']) is not int or context['process_id']<=0 or not isinstance(context['thread_id'],str) or not context['thread_id'] or
        type(context['wire_start_index']) is not int or type(context['wire_end_index']) is not int or
        not 0<=context['wire_start_index']<context['wire_end_index']):
        raise RuntimeError('HELD missing command context/turn/wire identity')
    context['turn_id']=next(iter(turns))
    if review.get('context')!=context:raise RuntimeError('HELD wrong command review context')
    before=checkpoint['baseline'];after=checkpoint['terminal'];slots=checkpoint['post_slots']
    if before['setup_slots']!=checkpoint['contract']['initial_slots'] or after['setup_slots']!=slots:
        raise RuntimeError('HELD command pre/postimage does not match immutable checkpoint')
    delta={'before_slots':before['setup_slots'],'after_slots':slots,
           'before_scope':before['setup_scope'],'after_scope':after['setup_scope']}
    if review.get('scoped_delta_sha256')!=canonical_hash(delta):raise RuntimeError('HELD wrong full command artifact delta')
    left=copy.deepcopy(before);right=copy.deepcopy(after)
    for view in (left,right):
        view['setup_slots']={'exact_command_artifacts':True}
        for name in SETUP_SLOTS:
            path=str(Path(checkpoint['root'])/name);slot=(before if view is left else after)['setup_slots'][name]
            record=view['files'].get(path)
            if (not isinstance(record,dict) or record.get('exists')!=(slot['kind']!='absent') or
                record.get('sha256')!=slot['sha256'] or record.get('realpath')!=slot['realpath']):
                raise RuntimeError('HELD missing/inconsistent sampled command artifact')
            view['files'][path]={'exact_command_artifact':name}
    if left!=right:raise RuntimeError('HELD unexplained nonartifact command delta')
    selections=review.get('selections')
    if not isinstance(selections,list) or not selections:raise RuntimeError('HELD missing selected actual command items')
    covered=set();indexes=set();ids=set();targets=[]
    for selected in selections:
        index=selected.get('event_index')
        if type(index) is not int or index in indexes or index not in checkpoint['provenance']['completed_command_event_indexes']:
            raise RuntimeError('HELD wrong/duplicate command event index')
        event=checkpoint['events'][index];params=event['params'];item=params['item'];identity=item.get('id')
        if (not isinstance(identity,str) or not identity or identity in ids or selected.get('item')!=item or
            not isinstance(item.get('cwd'),str) or not Path(item['cwd']).is_absolute() or
            Path(item['cwd']).resolve()!=Path(checkpoint['root']).resolve() or
            params.get('threadId',context['thread_id'])!=context['thread_id'] or params.get('turnId',context['turn_id'])!=context['turn_id']):
            raise RuntimeError('HELD wrong command item/id/cwd/turn')
        if sum(e.get('params',{}).get('item',{}).get('id')==identity for e in checkpoint['events']
               if isinstance(e,dict) and e.get('method')=='item/completed')!=1:
            raise RuntimeError('HELD ambiguous completed command identity')
        match=re.fullmatch(r"printf '%s\\n' '([^'\x00]*)' > (AGENTS\.md|CLAUDE\.md)",item['command'])
        if not match:raise RuntimeError('HELD unsupported dynamic/indirect command syntax')
        name=match[2];target=str(Path(checkpoint['root'])/name);expected=(match[1]+'\n').encode().hex()
        old=before['setup_slots'][name];new=slots[name]
        if (selected.get('target_path')!=target or selected.get('expected_bytes_hex')!=expected or new['bytes_hex']!=expected or
            new['kind'] not in ('regular','symlink') or (old['kind']=='absent' and new['kind']!='regular') or
            (old['kind']!='absent' and any(old[k]!=new[k] for k in ('kind','realpath','link_text','lstat_identity','target_identity')))):
            raise RuntimeError('HELD command target/postimage/topology mismatch')
        evidence=selected.get('evidence')
        if not isinstance(evidence,dict) or set(evidence)!= {'target','bytes','scope'} or any(not isinstance(v,str) or not v.strip() for v in evidence.values()):
            raise RuntimeError('HELD missing concrete parent target/bytes/scope review')
        aliases={n for n in SETUP_SLOTS if slots[n]['target_identity']==new['target_identity']}
        if any(slots[n]['bytes_hex']!=expected for n in aliases):raise RuntimeError('HELD unexplained command alias bytes')
        covered.update(aliases);indexes.add(index);ids.add(identity);targets.append(target)
    changed={name for name in SETUP_SLOTS if before['setup_slots'][name]!=slots[name]}
    if not changed or covered!=changed:raise RuntimeError('HELD unexplained/unmatched command artifact delta')
    return {'schema':'reviewed-literal-setup-command-v1','context':context,'event_indexes':sorted(indexes),
            'targets':targets,'scoped_delta_sha256':canonical_hash(delta),
            'basis':'Exact literal data relation plus concrete external parent review; no general shell-scope/security proof'}


def validate_setup_continuation(checkpoint, review, approval, root, recipe, manifest_sha256, release_id):
    """A review file alone is insufficient: require a separate actual USER input."""
    digest=canonical_hash(checkpoint)
    provenance=checkpoint.get('provenance',{})
    command_review=(checkpoint.get('status')=='HELD_UNVERIFIED_SETUP_OUTPUT_PROVENANCE' and
        provenance.get('mode')=='command_requires_parent_scope_review' and
        provenance.get('issues')==['command_execution_scope_unverified'] and
        review.get('write_provenance',{}).get('mode')=='CONCRETE_PARENT_LITERAL_COMMAND_REVIEW_V1')
    if not command_review and (not provenance.get('complete_for_parent_review') or checkpoint.get('status')!='OBSERVED_SETUP_OUTPUT_CHECKPOINT_REQUIRES_PARENT_REVIEW'):
        raise RuntimeError('HELD/UNVERIFIED setup write provenance cannot authorize C1')
    observed=setup_write_provenance(checkpoint['baseline']['setup_slots'],checkpoint['post_slots'],
        checkpoint['terminal']['setup_scope'],checkpoint['events'],checkpoint['contract'])
    if provenance!=observed:raise RuntimeError('UNVERIFIED checkpoint provenance does not match retained events/delta')
    write_review=review.get('write_provenance',{})
    expected_mode='CONCRETE_PARENT_LITERAL_COMMAND_REVIEW_V1' if command_review else 'CONCRETE_PARENT_STRUCTURED_CHANGE_REVIEW'
    if (write_review.get('mode')!=expected_mode or write_review.get('observations_sha256')!=canonical_hash(provenance) or
        write_review.get('artifact_delta_sha256')!=canonical_hash({'before':checkpoint['baseline']['setup_slots'],'after':checkpoint['post_slots']}) or
        not isinstance(write_review.get('evidence'),str) or not write_review['evidence'].strip()):
        raise RuntimeError('UNVERIFIED concrete parent write provenance/scope review missing')
    command_relation=reviewed_literal_setup_commands(checkpoint,write_review) if command_review else None
    if checkpoint.get('schema')!='setup-artifact-checkpoint-v1' or checkpoint.get('closed') is not True:
        raise RuntimeError('UNVERIFIED predecessor context not closed')
    if checkpoint.get('root')!=str(root) or checkpoint.get('post_slots')!=setup_slots(root,checkpoint.get('protected_paths',[])):
        raise RuntimeError('UNVERIFIED stale checkpoint postimage/topology')
    closure=checkpoint.get('closure_receipt_path')
    if (not closure or not Path(closure).is_file() or sha(closure)!=checkpoint.get('closure_receipt_sha256') or
        type(checkpoint.get('closed_process_returncode')) is not int):
        raise RuntimeError('UNVERIFIED concrete predecessor closure receipt')
    if setup_scope(root)!=checkpoint.get('terminal',{}).get('setup_scope'):
        raise RuntimeError('UNVERIFIED stale checkpoint consumer scope')
    for path,record in checkpoint['terminal']['files'].items():
        p=Path(path)
        if (p.exists()!=record['exists'] or str(p.resolve())!=record['realpath'] or
            (sha(p) if p.is_file() else None)!=record['sha256']):
            raise RuntimeError('UNVERIFIED stale checkpoint protected/source input')
    contract=checkpoint['contract']
    if (contract.get('manifest_sha256')!=manifest_sha256 or contract.get('release_id')!=release_id or
        checkpoint.get('source_recipe_sha256')!=recipe.get('predecessor_recipe_sha256') or
        checkpoint.get('user_history')!=recipe.get('predecessor_user_history') or not checkpoint.get('user_history') or
        checkpoint.get('terminal',{}).get('installed')!=recipe.get('checkpoint_installed')):
        raise RuntimeError('UNVERIFIED checkpoint source/release/history binding')
    required_checks=('existing_values','grants','unrelated_bytes','one_import','topology','source_bound_policy','scope')
    setup_body=next((x['source_sha256'] for x in checkpoint['terminal']['installed'] if x['name']=='ains-setup'),None)
    if (not setup_body or review.get('fixture_slots_sha256')!=canonical_hash(contract['initial_slots']) or
        review.get('terminal_scope_sha256')!=canonical_hash(checkpoint['terminal']['setup_scope']) or
        review.get('setup_body_sha256')!=setup_body or
        not isinstance(review.get('evidence'),dict) or set(review['evidence'])!=set(required_checks) or
        any(not isinstance(v,str) or not v.strip() for v in review['evidence'].values())):
        raise RuntimeError('UNVERIFIED concrete fixture/policy preservation evidence missing')
    if (review.get('checkpoint_sha256')!=digest or review.get('post_slots_sha256')!=canonical_hash(checkpoint['post_slots']) or
        review.get('decision')!='APPROVED_SETUP_CHECKPOINT' or
        review.get('preservation_checks')!={k:True for k in required_checks}):
        raise RuntimeError('UNVERIFIED concrete checkpoint preservation review missing')
    if (approval.get('role')!='user' or approval.get('action')!='approve_setup_checkpoint_new_context' or
        approval.get('checkpoint_sha256')!=digest or approval.get('review_sha256')!=canonical_hash(review) or
        not isinstance(approval.get('text'),str) or not approval['text'].strip() or approval.get('new_context') is not True):
        raise RuntimeError('UNVERIFIED separate actual USER checkpoint approval missing/forged')
    if (not isinstance(recipe.get('setup_content_ack_text'),str) or not recipe['setup_content_ack_text'].strip() or
        not checkpoint.get('original_setup_user_text') or recipe.get('setup_repeat_text')!=checkpoint['original_setup_user_text']):
        raise RuntimeError('UNVERIFIED new actual content acknowledgment/exact original repeat contract')
    if checkpoint.get('idempotence','').startswith('FAIL'):raise RuntimeError('Changed setup repeat failed idempotence; continuation held')
    return {'explicit_new_context':True,'predecessor_checkpoint_sha256':digest,'actual_USER_approval':approval,'review':review,
            **({'command_artifact_relation':command_relation} if command_relation else {})}


def close_setup_checkpoint(rpc, checkpoint, path):
    rpc.close()
    code=rpc.p.poll()
    if code is None:raise RuntimeError('UNVERIFIED predecessor still active')
    closure=rpc.sink/'closed.json'
    if not closure.is_file():raise RuntimeError('UNVERIFIED missing process closure receipt')
    checkpoint.update(closed=True,closed_process_returncode=code,
        closure_receipt_path=str(closure),closure_receipt_sha256=sha(closure))
    write(path,checkpoint)


def layout(root):
    result={}
    for name in ['AGENTS.md','CLAUDE.md']:
        path=Path(root)/name
        if path.exists() or path.is_symlink():
            st=path.lstat();result[name]={'sha256':sha(path) if path.is_file() else None,'symlink':path.is_symlink(),'link_target':os.readlink(path) if path.is_symlink() else None,'inode':st.st_ino,'resolved_inode':path.stat().st_ino if path.exists() else None,'realpath':str(path.resolve())}
    return result


def prepare(out, manifest=RELEASE):
    manifest=Path(manifest).resolve()
    out.mkdir(parents=True,exist_ok=False)
    release = released_source(manifest); templates = Path(tempfile.mkdtemp(prefix='ains native-v1 prepared fixtures ')); consumers=Path(tempfile.mkdtemp(prefix='ains native-v1 consumers '))
    with bound_helpers(out/'helper-sink') as (helpers, imports):
        rt = helpers['runtime']; ar = helpers['activation_recheck']
        for fixture in sorted({r['fixture'] for r in rows()}):
            root=templates/fixture
            source_case=next(((s,c) for s,c in CASES if c==fixture),None)
            if source_case: shutil.copytree(SOURCE/'tests/evals'/source_case[0]/source_case[1]/'files',root)
            elif fixture=='review-packet':
                root.mkdir();(root/'AGENTS.md').write_text(rt.CONTRACT);(root/'.gitignore').write_text('.agents/\n.claude/\nskills-lock.json\n__pycache__/\n')
            else: base_template(root,rt,fixture)
        versions={}
        for label,argv in [('codex-version',['codex','--version']),('codex-help',['codex','exec','--help']),('app-server-help',['codex','app-server','--help'])]:
            p=subprocess.run(argv,stdin=subprocess.DEVNULL,capture_output=True,timeout=20)
            versions[label]={'argv':argv,'exit':p.returncode,'output':rt.clean((p.stdout+p.stderr).decode(errors='replace'))}
        source_binding=json.loads((AUDIT/'binding.json').read_text())
        features=SOURCE/'.omx/ultragoal/evidence/codex-0164-native-binding/sources/codex-rs__features__src__lib.rs'
        if any('key: "'+key+'"' not in features.read_text() for key in DISCOVERY_KEYS):raise RuntimeError('Discovery key not in audited 0.164 source')
        environment=environment_facts(os.environ)
        write(out/'environment-snapshot.json',environment)
        try:
            diagnostic=recorded_rpc(rt,ar,templates/'base',['features.'+k+'=false' for k in CANONICAL_FEATURES],out/'model-free-config-rpc',source_binding)
            try:
                response=diagnostic.call('config/read',{'includeLayers':True,'cwd':str(templates/'base')},timeout=30)
                facts=config_facts(response,helpers['activation_closure_probe'].structural)
                ar.write(out/'current-config-facts.json',facts)
            finally:diagnostic.close()
        except (RuntimeError,KeyError,ValueError) as error:
            ar.write(out/'current-config-UNVERIFIED.json',{'status':'UNVERIFIED','error':str(error),'model_runs':0,'external_receipt_shape':{'environment_receipt':{'file_path':'exact selected environments.toml path','file_sha256':'current SHA256','selected_environment_kind':'local','required_skills':[],'parent_release_id':'actual release','proof_path':'reviewed nonsecret structural proof','proof_sha256':'proof SHA256'}}})
        manual_metadata={p.parent.parent.name for p in (SOURCE/'skills').glob('*/agents/openai.yaml') if p.read_text().strip()=='policy:\n  allow_implicit_invocation: false'}
        manual_frontmatter={p.parent.name for p in (SOURCE/'skills').glob('*/SKILL.md') if re.search(r'^disable-model-invocation: true$',p.read_text().split('---',2)[1],re.M)}
        if manual_metadata!=MANUAL or manual_frontmatter!=MANUAL:raise RuntimeError('Exact10 manual adapter/frontmatter set mismatch')
        recipe={'metadata_N1_mechanical':{'manual':sorted(manual_metadata),'automatic':sorted((MANUAL|AUTO)-manual_metadata),'runtime_verdict':'NOT RUN'},'version':'native-v1-prepare','source_release':release['release'],'release_manifest':str(manifest),'release_manifest_sha256':sha(manifest),
            'source_skill_metadata':release['suite_skill_metadata_sha256'],'helper_imports':imports,
            'adapter_sha256':sha(__file__),'fixture_root':str(templates),'consumer_root':str(consumers),'rows':rows(),
            'row_count':len(rows()),'maximum_model_user_turns':sum(r['max_user_turns'] for r in rows()),
            'fixture_layouts':{p.name:layout(p) for p in templates.iterdir()},
            'fixture_hashes':{str(p.relative_to(templates)):sha(p) for p in templates.rglob('*') if p.is_file()},
            'prepare_operations':{'models':0,'installs':0,'git_operations':0,'remote_operations':0},
            'source_selector_proof':{'path':'.omx/ultragoal/evidence/activation-audit-final/REPORT.md','sha256':sha(SOURCE/'.omx/ultragoal/evidence/activation-audit-final/REPORT.md'),'scope':'Historical finite configured native subset only; fresh current bodies/catalog/input still required'},
            'native_selector_binding':{'status':'SOURCE_0164_ACCEPTED_RUNTIME_FACTUAL_PREMISES_PENDING','semantic_source':SEMANTIC_COMMIT,'source_proof_sha256':sha(AUDIT/'REPORT.md'),'historical_codex_version':'codex-cli 0.163.0','observed_codex_version':versions['codex-version']['output'].strip(),'required_before_run':'Reviewed --native-binding plus enabled complete catalog, actual RPC/environment/config facts; no boolean-only binding'},
            'native_oracle_policy':'Literal frontend input and installed consumption are separate; source selector proof is retained for reviewer binding. Runtime adapter emits UNVERIFIED N4 until that binding is adjudicated; no invented native event schemas.',
            'source_corpus_sha256':{str(p.relative_to(SOURCE)):sha(p) for p in (SOURCE/'tests/evals').rglob('*') if p.is_file()},
            'future_sink_rule':'--run requires fresh --out; no old fixed driver/main is called',
            'live_input_protocol':'One JSON object {text: actual USER text} per stdin line, after previous turn completes; EOF stops. No approvals generated or preloaded.',
            'versions':versions}
        write(out/'recipe.json',ar.sanitized(recipe))
        # Exact future argv, not invented legacy selectors. Paths are real fresh prepare templates.
        commands=[]
        for row in rows():
            root=consumers/row['id']
            cli=['codex','--no-daemon','-a','never','exec','--ignore-user-config','--ephemeral','--strict-config','-s','workspace-write','-m','gpt-6.1-sol','--json','-C',str(root),row['initial_user_text']]
            commands.append({'required_packet':str(EVIDENCE/'RUN_RELEASE_REQUIRED'/'actual-workflow-review-packet') if row['fixture'] in ['review-packet','review-unavailable'] else None,'row':row['id'],'adapter_argv':['python3',str(Path(__file__).resolve()),'--run','--manifest',str(manifest),'--prepared',str(out),'--row',row['id'],'--out',str(EVIDENCE/'RUN_RELEASE_REQUIRED'/row['id']),'--release-id','PARENT_RELEASE_REQUIRED','--native-binding',str(EVIDENCE/'RUN_RELEASE_REQUIRED'/'reviewed-native-binding.json')],
                             'product_argv_base':cli if row['transport']=='cli' else ['codex','--no-daemon','-a','never','app-server','--strict-config','--stdio'],
                             'overrides':'Canonical11 and exact all-layer MCP-name overrides computed/saved in preflight, no discovery disabling',
                             'initial_user_text':row['initial_user_text'],'max_user_turns':row['max_user_turns']})
        for command in commands:
            if command['required_packet']:command['adapter_argv']+=['--packet',command['required_packet']]
        write(out/'planned-commands.json',commands)
        write(out/'import-receipt.json',{'helper_imports':imports,'fresh_bound_OUT':str(out/'helper-sink'),'legacy_mains_called':False,'import_time_effect':'Only runtime OUT.mkdir redirected before execution; function bodies unchanged; all imported OUT references asserted fresh','no_runtime_models':True})
    print(json.dumps({'status':'PREPARED ONLY','recipe':str(out/'recipe.json'),'rows':len(rows()),'max_user_turns':sum(r['max_user_turns'] for r in rows())}))


WORKFLOW_LIMITS = {
    'workflow-router':{'router':1}, 'setup-observe':{'setup-observe':4},
    'setup-ack-repeat':{'setup-ack-repeat':2},
    'workflow-after-setup':{'spec':10,'tasks':6,'build':3,'AC9-handoff':5},
    'workflow-review-unavailable':{'unavailable':1},
    'workflow-independent-review':{'reviewer':1},
    'workflow-after-review':{'localship':5,'scope-invalidation':2},
    'original-notification-draft':{'original-draft':14},
    'spec-closure-regression':{'closure':3}}
# Closed after audited v19 initial (1) and v22 ack/repeat (2); no new CLAUDE-only context.
WORKFLOW_UNIT_LIMITS = {('setup-observe','setup-observe','setup-claude-only'):1,
                        ('setup-ack-repeat','setup-ack-repeat','setup-claude-only'):2,
                        # Closed after audited v29 initial (1) and v30 ack/repeat (2).
                        ('setup-observe','setup-observe','setup-existing-import'):1,
                        ('setup-ack-repeat','setup-ack-repeat','setup-existing-import'):2,
                        ('setup-observe','setup-observe','setup-samefile'):1,
                        ('setup-observe','setup-observe','setup-symlink'):2,
                        ('setup-observe','setup-observe','notification-workflow'):6}


def workflow_ceiling(purpose, phase, unit):
    return WORKFLOW_UNIT_LIMITS.get((purpose,phase,unit),WORKFLOW_LIMITS[purpose][phase])


WORKFLOW_SETUP_UNITS = {'setup-'+name for name in ('claude-only','duplicate','conflict','existing-import','samefile','symlink')}


SPEC_CLOSURE_ROWS = {
    'codex-default-authentic-preanswer':('default','original-pre-v39'),
    'codex-copy-equivalent-preanswer':('copy','original-pre-v39'),
    'codex-copy-D2-authentic-pre-v57-answer':('copy','D2-pre-v57')}


def spec_closure_installer_lock(recipe, row, material, records, products, product, program):
    """Only the proven finite skills1.7.4 lock relation; no live producer paths."""
    import posixpath
    def held(message):raise RuntimeError('HELD spec closure installer lock '+message)
    def blob(ref):
        if not isinstance(ref,dict) or set(ref)!={'path','sha256'} or not isinstance(ref['path'],str) or not Path(ref['path']).is_absolute() or str(Path(ref['path']))!=ref['path'] or '..' in Path(ref['path']).parts or sha(ref['path'])!=ref['sha256']:held('Ref/hash')
        return Path(ref['path']).read_bytes()
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:held('duplicate JSON key')
            result[key]=value
        return result
    def doc(ref):return json.loads(blob(ref),object_pairs_hook=pairs)
    E=SOURCE/'.omx/ultragoal/evidence'
    P=E/'g004/codex/native-v66/preparation/spec-closure-three-row-S-source9bb-usage71'
    lock=doc(program['lock'])
    if set(lock)!=set('schema row_id root realroot old_lock new_lock manifest cli command source_root report'.split()) or lock['schema']!='spec-closure-installer-lock-v1':held('closed receipt')
    for key,value in {'row_id':row['id'],'root':material['root'],'realroot':material['realroot'],'manifest':product['new_manifest']}.items():
        if lock[key]!=value:held('row/root/manifest')
    original=next(r for r in records if r['relative_path']=='skills-lock.json')
    if lock['old_lock']!=original['retained_byte_ref']:held('historical Ref')
    oldraw=blob(lock['old_lock']);old=doc(lock['old_lock'])
    if set(old)!={'version','skills'} or type(old['version']) is not int or old['version']!=1 or not isinstance(old['skills'],dict) or set(old['skills'])!=MANUAL|AUTO:held('version/full16')
    # These exact ASCII orders were independently exhausted against all 5,127
    # permutations and the retained hashes. This is no general locale comparator.
    orders={'ains': ['agents/openai.yaml', 'scripts/status.sh', 'SKILL.md'],
     'ains-build': ['agents/openai.yaml', 'SKILL.md'],
     'ains-context-care': ['rules-audit.md', 'SKILL.md'],
     'ains-grilling': ['SKILL.md'],
     'ains-harness': ['agents/openai.yaml', 'gate-menu.md', 'SKILL.md'],
     'ains-release-safety': ['SKILL.md'],
     'ains-retro': ['agents/openai.yaml', 'SKILL.md'],
     'ains-review': ['review-prompt.md', 'SKILL.md'],
     'ains-review-gate': ['assets/human-review-rules.example',
                          'risk-scorer.md',
                          'scripts/route-review.sh',
                          'SKILL.md'],
     'ains-setup': ['agents/openai.yaml', 'SKILL.md'],
     'ains-ship': ['agents/openai.yaml', 'assets/pr-body.md', 'SKILL.md'],
     'ains-spec': ['agents/openai.yaml',
                   'assets/spec.md',
                   'existing-system.md',
                   'prototype.md',
                   'scripts/new-change.sh',
                   'sdd-tools.md',
                   'SKILL.md'],
     'ains-tasks': ['agents/openai.yaml', 'assets/tasks.md', 'parallel.md', 'SKILL.md'],
     'ains-tdd': ['SKILL.md'],
     'ains-team-canvas': ['agents/openai.yaml', 'assets/team-canvas.template.md', 'SKILL.md'],
     'ains-tool-access': ['agents/openai.yaml', 'SKILL.md']}
    groups={name:{} for name in orders}
    for item in products:
        name,filename=item['relative_path'].removeprefix('skills/').split('/',1)
        if name not in orders or filename not in orders[name] or filename in groups[name] or not filename.isascii():held('finite filename set')
        groups[name][filename]=item
    if any(set(groups[name])!=set(order) for name,order in orders.items()):held('finite filename inventory')
    source=lock['source_root']
    if not isinstance(source,str) or source!=str(SOURCE):held('source repository')
    historical_parent=posixpath.dirname(original['expected']['realpath'])
    expected={'version':1,'skills':{}}
    for name in sorted(orders):
        entry=old['skills'][name]
        if set(entry)!=set('source sourceType computedHash'.split()) or entry['sourceType']!='local' or entry['source']!=posixpath.relpath(source,historical_parent) or posixpath.normpath(posixpath.join(historical_parent,entry['source']))!=source:held('historical portable source')
        before=hashlib.sha256();after=hashlib.sha256()
        for filename in orders[name]:
            item=groups[name][filename];raw=blob(item['old_retained_ref'])
            for digest,body in ((before,raw),(after,blob(product['new_body']) if name=='ains-spec' and filename=='SKILL.md' else raw)):
                digest.update(filename.encode('ascii'));digest.update(body)
        if entry['computedHash']!=before.hexdigest() or (name!='ains-spec' and before.digest()!=after.digest()):held('retained folder hash')
        updated=dict(entry);updated['source']=posixpath.relpath(source,material['realroot']);updated['computedHash']=after.hexdigest();expected['skills'][name]=updated
    def serialized(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
    if oldraw!=serialized(old):held('historical serialization')
    newraw=blob(lock['new_lock']);doc(lock['new_lock'])
    archive=Path(lock['new_lock']['path']);info=archive.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or any(archive.resolve().is_relative_to(Path(material[k])) for k in ('root','realroot')):held('immutable archive topology')
    if lock['new_lock']==lock['old_lock'] or any(Path(lock['new_lock']['path']).is_relative_to(Path(material[k])) for k in ('root','realroot')) or newraw!=serialized(expected):held('immutable exact output/serialization')
    digest=hashlib.sha256(newraw).hexdigest()
    if recipe.get('protected_files',[]).count({'path':str(Path(material['root'])/'skills-lock.json'),'sha256':digest})!=1:held('immutable predispatch protection')
    cli=doc(lock['cli'])
    if set(cli)!=set('schema version identities pins version_receipt historical_collector excerpt'.split()) or cli['schema']!='spec-closure-installer-cli-v1' or cli['version']!='1.7.4':held('closed CLI identity')
    pins={'path':str(P/'inputs-start.json'),'sha256':'18138d71970131e0bd4fee3632342773b5ba86dc456b6003ccc86c8510b3f4a8'}
    if cli['pins']!=pins:held('actual CLI pin source')
    retained=doc(pins);identities={k:v for k,v in retained.items() if '/node_modules/skills/' in k}
    if len(identities)!=3 or cli['identities']!=identities:held('actual CLI source identity')
    # Frozen identities are evidence, never cache paths to dereference in history.
    historical={'path':str(E/'r7-parent-verification/closure-installer-lock-implementation-scope/archive/native_delta.py'),'sha256':'9bb6b0acd29d55d4c0a576f00e8df975e133635c4ee88605754f1669538505e0'}
    excerpt={'path':str(E/'workflow-closure-installer-lock-relation-plan/pinned-installer-functions.txt'),'sha256':'c4205bb6efea1a742ee8c473a805c71c454ab4a4336f6a8b068725db2015c297'}
    version={'path':str(P/'installer-version-command.json'),'sha256':'3d13ea8b991cf9a8c7b7533d6acaa09b00d33df58427c21507136ed9f594dd39'}
    if cli['historical_collector']!=historical or cli['excerpt']!=excerpt or cli['version_receipt']!=version:held('historical/CLI source binding')
    blob(historical);blob(excerpt);observed=doc(version)
    if type(observed['returncode']) is not int or observed['returncode']!=0 or blob(observed['stdout']).strip()!=b'1.7.4':held('actual CLI version')
    command=doc(lock['command'])
    if set(command)!=set('argv cwd returncode elapsed_seconds stdout stderr guard_log child_environment_overrides'.split()) or command['argv']!=observed['argv'][:4]+['add',source,'--skill','*','-a','codex','-y']+(['--copy'] if row['mode']=='copy' else []) or command['cwd']!=material['root'] or type(command['returncode']) is not int or command['returncode']!=0 or type(command['elapsed_seconds']) not in (int,float) or not 0<=command['elapsed_seconds']<=180:held('actual command/cwd/mode/result')
    if command['child_environment_overrides']!={**observed['child_environment_overrides'],'AINS_INSTALL_GUARD_LOG':command['guard_log']['path']} or blob(command['stderr']) or blob(command['guard_log']):held('command environment/denials')
    blob(command['stdout'])
    report=doc(lock['report']);fields={k:v for k,v in lock.items() if k not in ('schema','report')}
    if set(report)!=set(fields)|{'schema','decision','report'} or {k:v for k,v in report.items() if k not in ('schema','decision','report')}!=fields or report['schema']!='ROOT_SPEC_CLOSURE_INSTALLER_LOCK_REVIEW_V1' or report['decision']!='APPROVE_EXACT_INSTALLER_LOCK_RELATION' or not blob(report['report']).strip():held('concrete Root relation report')
    return digest


def spec_closure_component(recipe, row, material, usage, review=None):
    """Finite retained preanswer relation; current inventory is checked by caller."""
    import difflib
    def held(message):raise RuntimeError('HELD spec closure '+message)
    def unique_pairs(items):
        result={}
        for key,value in items:
            if key in result:held('duplicate JSON key')
            result[key]=value
        return result
    def document(reference):return json.loads(blob(reference),object_pairs_hook=unique_pairs)
    def blob(reference):
        if set(reference)!={'path','sha256'} or sha(reference['path'])!=reference['sha256']:held('artifact Ref/hash')
        return Path(reference['path']).read_bytes()
    E=SOURCE/'.omx/ultragoal/evidence'
    supplement={'path':str(E/'r7-parent-verification/original-preanswer-eleven-byte-archive/MAP-supplement.json'),'sha256':'70a38e716733579fc25fd8dd63d1397d365dbc531fb16a9291778d95bea431e8'}
    # The supplement pins its immutable predecessor; no arbitrary map is admitted.
    mapping=document(supplement);blueprint=mapping['prior_map'];document(blueprint)
    pair=SPEC_CLOSURE_ROWS.get(row.get('id'))
    if recipe.get('execution_kind')!='bounded-workflow-v1' or recipe.get('rows')!=[row] or pair is None or (recipe.get('purpose'),recipe.get('phase'),recipe.get('unit'))!=('spec-closure-regression','closure','changed-spec') or (row.get('mode'),material.get('lineage'))!=pair:held('fixed row/mode/lineage')
    if set(material)!=set('schema row_id mode lineage root realroot state origin business_map product install'.split()) or material['schema']!='spec-closure-materialization-v1' or material['row_id']!=row['id'] or material['mode']!=row['mode']:held('closed materialization fields')
    root=Path(material['root']);canonical=Path(material['realroot']);state=material['state'];lin='original' if pair[1]=='original-pre-v39' else 'D2';line=mapping['lineages'][lin]
    for value in (material['root'],material['realroot']):
        path=Path(value)
        if not path.is_absolute() or str(path)!=value or '..' in path.parts or value.startswith('//') or path==SOURCE or path in SOURCE.parents or SOURCE in path.parents:held('root containment')
    for original in mapping['lineages'].values():
        for relation in ('preceding_question','actual_final_USER_and_historical_response'):
            old=document(original[relation]['context'])
            if {material['root'],material['realroot']}&{old['root'],old['realroot']}:held('historical consumer reused')
    for reference in usage:
        previous=document(reference)
        if previous.get('purpose')!='spec-closure-regression':continue
        if previous.get('row_id')==row['id']:
            if any(e.get('direction')=='request' and e.get('payload',{}).get('method')=='turn/start' for e in document(previous['wire'])):held('row lifetime dispatched')
        elif {material['root'],material['realroot']}&{previous['root'],previous['realroot']}:held('distinct row roots')
    origin=material['origin']
    expected={'oracle':{'path':str(E/('spec-closure-oracle-root-adoption/adoption.json' if lin=='original' else 'spec-closure-D2-oracle-addendum-critic-r1/REPORT.md')),'sha256':'7a351bcd784a7a2324fd58c8a8fffd8f0443dd911fb758ed16cef841581b531d' if lin=='original' else '9099464d35558a2267a43f4971f0a4cd6137d7c5bc716525a531276969a94bd8'},
        'carry':{'path':str(E/('spec-closure-oracle-carry-budget-review/REPORT.md' if lin=='original' else 'spec-closure-D2-frontier-oracle-addendum-r2/REPORT.md')),'sha256':'06e6b7db763a5e85496292b65781cbebc9b53fa9079b423e030b03b1b88f3e03' if lin=='original' else '66665e7a4f3781769aa21dd003b33fc3c44428a4f9b387389c9ad41c867f03ea'},
        'witness':line['witness'],'blueprint':blueprint,'supplement':supplement,'question_context':line['preceding_question']['context'],'question_wire':line['preceding_question']['wire'],'preanswer_draft':line['authentic_preanswer_draft'],
        'decision_lineage':line.get('history_attestation',line.get('prior_decision_lineage_attestation')),
        'initial_request':line['thin_prompt']['attestation'] if lin=='original' else line['prior_decision_lineage_attestation']}
    if set(origin)!=set(expected)|{'actual_USER'} or any(origin[k]!=v for k,v in expected.items()):held('authentic origin refs')
    for reference in expected.values():blob(reference)
    actual=workflow_user_evidence(origin['actual_USER'],usage,Path(line['actual_final_USER_and_historical_response']['historical_root']))
    old=line['actual_final_USER_and_historical_response'];wire=document(old['wire']);payload=wire[36]['payload'];record=document(old['context'])
    if actual.get('context')!=old['context'] or actual.get('wire_index')!=36 or actual.get('payload_sha256')!=canonical_hash(payload) or payload.get('method')!='turn/start' or payload['params'].get('threadId')!=record['thread_id'] or payload['params']['input']!=[{'type':'text','text':row['initial_user_text']}] or actual.get('text')!=row['initial_user_text']:held('exact original actual USER')
    product=document(material['product'])
    if set(product)!=set('old_manifest new_manifest diff source_review old_body new_body'.split()) or product['old_manifest'].get('sha256')!='dd34b9557642f70f8cce8e8e3585519667b3673156a64376b2e3f7c46754d0bc':held('product fields/old manifest')
    document(product['old_manifest']);manifest=document(product['new_manifest']);products=mapping['product_identity_map'];name='skills/ains-spec/SKILL.md';oldbody=next(item['old_retained_ref'] for item in products if item['relative_path']==name)
    if product['old_body']!=oldbody or product['new_manifest']['sha256']!=recipe['release_manifest_sha256'] or product['new_manifest']['path']!=recipe['release_manifest']:held('current product identity')
    design={'path':str(E/'spec-approval-closure-repair-design/PLAN.md'),'sha256':'e44d32e14d8a0e838209ceb3e016cd3fa76474b23b5bc664dde411368ffc8bc7'}
    paragraph=next(line[2:] for line in blob(design).decode().splitlines() if line.startswith('> '));oldtext=blob(oldbody).decode();head,tail=oldtext.split('## 5. 承認を得る\n\n');unused,rest=tail.split('未決の業務判断をこの要約に混ぜて',1)
    expected_body=head+'## 5. 承認を得る\n\n'+paragraph+'未決の業務判断をこの要約に混ぜて'+rest;newtext=blob(product['new_body']).decode()
    if newtext!=expected_body or blob(product['diff']).decode()!=''.join(difflib.unified_diff(oldtext.splitlines(True),newtext.splitlines(True),fromfile='a/'+name,tofile='b/'+name)):held('exact section5-only diff')
    expected_suite={item['relative_path']:{'sha256':product['new_body']['sha256'] if item['relative_path']==name else item['old_retained_ref']['sha256'],'mode':item['old_mode']} for item in products}
    if manifest.get('suite_files')!=expected_suite:held('new42/unchanged41')
    source=document(product['source_review'])
    if (source.get('schema')!='spec-closure-product-review-v1' or source.get('decision')!='APPROVE_EXACT_SECTION5_ONLY' or
        any(source.get(k)!=product[k] for k in ('old_manifest','new_manifest','diff')) or source.get('design')!=design):held('concrete product review')
    blob(source['report'])
    business=document(material['business_map']);records=[entry for entry in mapping['records'] if entry['lineage']==lin];expected_names={r['relative_path'] for r in records}
    if (set(business)!=set('schema lineage witness blueprint supplement records absence_assertions relocations draft_path'.split()) or business['schema']!='spec-closure-business-map-v1' or
        business['lineage']!=pair[1] or business['witness']!=line['witness'] or business['blueprint']!=blueprint or business['supplement']!=supplement or
        business['absence_assertions']!=mapping['absence_assertions'][lin] or business['relocations']!={'root':str(root),'realroot':str(canonical),'product':material['product']} or
        set(state)!=expected_names or len(business['records'])!=len(records)):held('complete namespace/map')
    installed=document(material['install']);program=document(installed['program'])
    if set(program)!=set('row_id root mode manifest files_sha256 report lock'.split()) or any(program[k]!=v for k,v in {'row_id':row['id'],'root':str(root),'mode':row['mode'],'manifest':product['new_manifest']}.items()):held('concrete install program binding')
    blob(program['report'])
    lock_digest=spec_closure_installer_lock(recipe,row,material,records,products,product,program)
    names=set();identities=set();draft=None
    for bound,original in zip(business['records'],records):
        path=original['relative_path'];expected=original['expected'];target=state[path]
        if set(bound)!=set('path source historical target parent alias_group'.split()) or bound!={'path':path,'source':original['retained_byte_ref'],'historical':expected,'target':target,'parent':original['parent_relative'],'alias_group':original['alias_group']}:held('exact historical/target map record')
        if path in names or Path(path).is_absolute() or '..' in Path(path).parts or str(Path(path))!=path:held('normalized unique target')
        names.add(path)
        if target.get('kind')!=expected['kind'] or target.get('mode')!=expected['mode'] or target.get('realpath')!=str(canonical/path) or target.get('link_text') is not None or not isinstance(target.get('identity'),list) or len(target['identity'])!=2 or any(type(x) is not int for x in target['identity']):held('target topology')
        identity=tuple(target['identity'])
        if identity in identities:held('target hardlink/alias')
        identities.add(identity)
        if expected['kind']=='file':
            digest=product['new_body']['sha256'] if path=='.agents/'+name else lock_digest if path=='skills-lock.json' else expected['sha256']
            blob(bound['source'])
            if target.get('sha256')!=digest or bound['source']['sha256']!=expected['sha256']:held('retained bytes/install exception')
            if expected['sha256']==line['authentic_preanswer_draft']['sha256']:draft=path
    if business['draft_path']!=draft or not blob(line['authentic_preanswer_draft']).startswith(b'---\nstatus: draft\n---'):held('authentic unapproved draft')
    if any(path in state for path in business['absence_assertions']['selected_absent_paths']):held('absence changed')
    installed=document(material['install']);files={item['relative_path']:{'path':str(root/'.agents'/item['relative_path']),**{key:state['.agents/'+item['relative_path']][key] for key in ('realpath','identity','kind','sha256','mode')}} for item in products}
    if set(installed)!=set('schema row_id mode root realroot manifest files bodies metadata program'.split()) or installed['schema']!='spec-closure-install-v1' or any(installed.get(k)!=v for k,v in {'row_id':row['id'],'mode':row['mode'],'root':str(root),'realroot':str(canonical),'manifest':product['new_manifest'],'files':files,'bodies':{k:files['skills/'+k+'/SKILL.md'] for k in MANUAL|AUTO},'metadata':{k:v for k,v in files.items() if k.endswith('/agents/openai.yaml')}}.items()):held('actual full16/new42 install relation')
    if program['files_sha256']!=canonical_hash(files):held('concrete install program full42 binding')
    if review is not None:
        if review.get('business')!={'closure_materialization':checked_json(recipe['workflow_checkpoint'])['materialization']}:held('Root exact closure business')
        required=[checked_json(recipe['workflow_checkpoint'])['materialization'],product['source_review'],installed['program'],origin['oracle'],program['lock']]
        required += [ref for ref in usage if checked_json(ref).get('purpose')=='spec-closure-regression' and checked_json(ref).get('row_id')==row['id']]
        if recipe.get('producer_schema')==FINITE_PRODUCER_SCHEMA and recipe!=spec_closure_zero_provenance()['recipe']:required += [SPEC_CLOSURE_ZERO_CONTEXT,SPEC_CLOSURE_ZERO_DISPOSITION]
        if any(ref not in review.get('authority_evidence',[]) for ref in required):held('concrete Root materialization/install/origin/zero correction evidence')
    return {'draft_path':draft,'initial':state,'materialization':checked_json(recipe['workflow_checkpoint'])['materialization']}


def workflow_ref_equal(a, b):
    return a['sha256']==b['sha256'] and Path(a['path']).resolve()==Path(b['path']).resolve()


def workflow_limits(recipe, row, used):
    purpose=recipe.get('purpose');phase=recipe.get('phase');unit=recipe.get('unit')
    if purpose not in WORKFLOW_LIMITS or phase not in WORKFLOW_LIMITS[purpose]:raise RuntimeError('HELD unknown workflow purpose/phase')
    allowed=({'changed-spec'} if purpose=='spec-closure-regression' else {'original-notification'} if purpose=='original-notification-draft' else
             WORKFLOW_SETUP_UNITS|{'notification-workflow'} if purpose in ('setup-observe','setup-ack-repeat') else {'notification-workflow'})
    count=row.get('max_user_turns');duration=row.get('terminal_deadline_seconds')
    if (unit not in allowed or row.get('transport')!='live' or row.get('mode')!=(SPEC_CLOSURE_ROWS.get(row.get('id'),(None,))[0] if purpose=='spec-closure-regression' else 'default' if purpose=='original-notification-draft' else 'copy') or
        (purpose=='spec-closure-regression' and (row.get('id') not in SPEC_CLOSURE_ROWS or count!=1)) or
        type(count) is not int or type(duration) is not int or duration!=180 or
        not 0<count<=workflow_ceiling(purpose,phase,unit)-used.get(unit+'/'+phase,0)):
        raise RuntimeError('HELD workflow phase allocation exhausted or invalid')
    return count


def workflow_inventory(root, protected=(), setup=False):
    if not setup:return current_author_inventory(root)
    root=Path(root);slots=setup_slots(root,protected);result={};pending=[root]
    if root.is_symlink() or not root.is_dir():raise RuntimeError('HELD setup root topology')
    shared=slots['AGENTS.md']['target_identity'] is not None and slots['AGENTS.md']['target_identity']==slots['CLAUDE.md']['target_identity']
    while pending:
        p=pending.pop();st=p.lstat();real=p.resolve(strict=True);name=str(p.relative_to(root))
        if not real.is_relative_to(root.resolve()):raise RuntimeError('HELD setup inventory escape')
        rec={'mode':oct(stat.S_IMODE(st.st_mode)),'identity':[st.st_dev,st.st_ino],
             'realpath':str(real),'link_text':os.readlink(p) if p.is_symlink() else None}
        if p.is_symlink():
            if name not in SETUP_SLOTS:raise RuntimeError('HELD undeclared setup alias')
            rec.update(kind='symlink',target_identity=slots[name]['target_identity'],sha256=sha(p))
        elif stat.S_ISREG(st.st_mode):
            if st.st_nlink!=1 and not (name in SETUP_SLOTS and shared and st.st_nlink==2):raise RuntimeError('HELD undeclared setup hardlink')
            rec.update(kind='file',sha256=sha(p))
        elif stat.S_ISDIR(st.st_mode):rec['kind']='directory';pending.extend(sorted(p.iterdir(),reverse=True))
        else:raise RuntimeError('HELD unsupported setup inventory entry')
        result[name]=rec
    return dict(sorted(result.items()))


TASKS_TIMEOUT_ROW = 'copy-notification-workflow-tasks-closed-timeout-approval'
TASKS_TIMEOUT_PINS = {
    'origin':'7eceeb6f48fe07923b94093dea050cd31e105c03ecff05662b0544b42605e60c',
    'manifest':'5615b38ef31a7b1eecd5b1fed3cdefefbc41f436c73557b32ec87f3632a88d53',
    'collector':'dca60539cfc521b62d5efa7f2ad14ca34b9b558ccdaed65280c2a08705fb0ea2',
    'tests':'43b181460f7cc365824be0f9691e9774a444c10b4964ab093f254c2d4fb446fa',
    'content_review':'44aa4d449268261c6f7b756c9db50c58c885e51b8166c0c74a2436578229ec07',
    'audit':'196189e3a197ad00d5edc1c8ee13aed12e7976f43c8a58ba9ed412d61cbbf7c5',
    'audit_index':'f01a767058c3d7da332e4d268e46ff552472508b53b6a0a28ea9502f236662e9',
    'approval_DATA':'d4a73731ee77dd97eee88a85f041d8dc0e2dbcd5f18dcf0b5ef2c561c78de957',
    'input_DATA':'4cdaa056596e92594f0f8a389f02611b62b6062ef9c5ea194bb4e4198fff6221',
    'program_indices':(113,211,214)}


def workflow_live_source_protection(material, old, recipe, source=None, review=None, current=False):
    """Two reviewed live identities; archived producer and other entries stay exact."""
    proof=material.get('live_source_protection');previous=old['protected_files']
    if proof is None:
        if recipe.get('protected_files')!=previous:raise RuntimeError('HELD TASKS origin source/install/protection identity')
        if source is not None and ('implementation_review' in source or 'live_source_protection' in review):raise RuntimeError('HELD unbound live source certificate')
        return
    if (material.get('schema')!='workflow-tasks-closed-timeout-state-v1' or set(proof)!= {'review_index','files'} or
        not isinstance(proof['files'],list) or len(proof['files'])!=2):raise RuntimeError('HELD finite two-file source protection proof')
    index=checked_json(proof['review_index']);names=('tests/runtime/codex/native_delta.py','tests/runtime/codex/native_delta_test.py')
    if (index.get('verdict')!='APPROVED_SOURCE_ONLY' or index.get('mandatory_findings')!=[] or
        set(index.get('reviewed_source',{}))!=set(names)):raise RuntimeError('HELD exact independent source/test review')
    report=Path(proof['review_index']['path']).parent/'REPORT.md';report_sha=index['files']['REPORT.md']['sha256']
    if sha(report)!=report_sha:raise RuntimeError('HELD independent source review report identity')
    expected=[dict(entry) for entry in previous]
    for name,role,entry in zip(names,('collector','tests'),proof['files']):
        path=SOURCE/name;info=index['reviewed_source'][name];positions=[i for i,value in enumerate(previous) if value['path']==str(path)]
        if (len(positions)!=1 or previous[positions[0]]['sha256']!=TASKS_TIMEOUT_PINS[role] or
            set(entry)!={'path','sha256','mode','realpath','identity'} or entry.get('path')!=str(path) or entry.get('realpath')!=str(path) or
            entry.get('sha256')!=info.get('sha256') or not isinstance(entry.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',entry['sha256']) or
            entry.get('mode')!='0o644' or info.get('mode')!='0o644' or type(info.get('bytes')) is not int or info['bytes']<=0 or
            not isinstance(entry.get('identity'),list) or len(entry['identity'])!=2 or any(type(x) is not int or x<0 for x in entry['identity'])):
            raise RuntimeError('HELD exact reviewed source/test path/hash/mode/identity')
        expected[positions[0]]['sha256']=entry['sha256']
    if recipe.get('protected_files')!=expected:raise RuntimeError('HELD ordered protection list permits only two reviewed SHA updates')
    if recipe.get('adapter_sha256')!=proof['files'][0]['sha256']:raise RuntimeError('HELD reviewed collector and recipe identity differ')
    if source is not None:
        if (source.get('implementation_review')!=proof['review_index'] or source.get('report')!={'path':str(report),'sha256':report_sha} or
            source.get('collector_sha256')!=proof['files'][0]['sha256'] or review.get('collector_sha256')!=proof['files'][0]['sha256'] or
            review.get('live_source_protection')!=proof):raise RuntimeError('HELD concrete source/Root live pair certificate')
    if current:
        if source is None or review is None or sha(__file__)!=proof['files'][0]['sha256']:raise RuntimeError('HELD current executing source review identity')
        for entry,name in zip(proof['files'],names):
            path=SOURCE/name;meta=path.lstat();info=index['reviewed_source'][name]
            if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink!=1 or str(path.resolve(strict=True))!=entry['realpath'] or
                [meta.st_dev,meta.st_ino]!=entry['identity'] or oct(stat.S_IMODE(meta.st_mode))!=entry['mode'] or
                meta.st_size!=info['bytes'] or sha(path)!=entry['sha256']):raise RuntimeError('HELD current live source/test bytes or topology changed')


def workflow_tasks_handoff(material, usage, recipe, row):
    """One pinned failed producer -> reviewed actual state; never turn success."""
    if (material.get('schema')!='workflow-tasks-closed-timeout-state-v1' or row.get('id')!=TASKS_TIMEOUT_ROW or
        recipe.get('execution_kind')!='bounded-workflow-v1' or recipe.get('rows')!=[row] or
        (recipe.get('purpose'),recipe.get('phase'),recipe.get('unit'))!=('workflow-after-setup','tasks','notification-workflow') or
        row.get('mode')!='copy' or row.get('transport')!='live' or type(row.get('max_user_turns')) is not int or row['max_user_turns']!=1 or
        type(row.get('terminal_deadline_seconds')) is not int or row['terminal_deadline_seconds']!=180 or
        recipe.get('usage')!=usage or material.get('usage_sha256')!=canonical_hash(usage)):
        raise RuntimeError('HELD finite TASKS timeout handoff tuple/row/usage')
    for key in ('origin','manifest','content_review','audit','audit_index','approval_DATA','input_DATA'):
        reference=material[key]
        if reference.get('sha256')!=TASKS_TIMEOUT_PINS[key] or sha(reference['path'])!=reference['sha256']:
            raise RuntimeError('HELD exact v59 TASKS handoff evidence: '+key)
    origin=checked_json(material['origin']);manifest=checked_json(material['manifest']);root=Path(material['root'])
    for reference in manifest['files']+manifest.get('external_operator_logs',[]):
        if sha(reference['path'])!=reference['sha256']:raise RuntimeError('HELD frozen TASKS origin file drift')
    if not any(workflow_ref_equal(material['origin'],ref) for ref in manifest['files']):raise RuntimeError('HELD TASKS origin absent from frozen manifest')
    if (origin.get('healthy') is not False or origin.get('closed') is not True or type(origin.get('server_returncode')) is not int or origin['server_returncode']!=0 or
        origin.get('failure')!='Absolute terminal deadline exceeded' or origin.get('state_error') or origin.get('close_error') or
        origin.get('root')!=str(root) or origin.get('realroot')!=str(root.resolve()) or origin.get('state')!=material['state'] or
        (origin.get('purpose'),origin.get('phase'),origin.get('unit'))!=('workflow-after-setup','tasks','notification-workflow') or origin.get('config_facts')!={}):
        raise RuntimeError('HELD exact failedclosed TASKS state, not healthy recovery')
    old=checked_json(origin['recipe']);old_release=checked_json(origin['release']);wire=checked_json(origin['wire'])
    positions=[i for i,ref in enumerate(usage) if workflow_ref_equal(ref,material['origin'])]
    if len(positions)!=1 or usage[:positions[0]]!=old['usage']:raise RuntimeError('HELD complete original TASKS chronology')
    suffix=[ref for ref in usage[positions[0]+1:] if checked_json(ref)['unit']=='notification-workflow']
    if material.get('zero_request_suffix')!=suffix:raise RuntimeError('HELD explicit TASKS zero-request suffix')
    for reference in suffix:
        hold=checked_json(reference);events=checked_json(hold['wire'])
        if (hold.get('root')!=str(root) or hold.get('state')!=material['state'] or hold.get('phase')!='tasks' or hold.get('purpose')!='workflow-after-setup' or
            hold.get('closed') is not True or hold.get('state_error') or hold.get('close_error') or
            any(e.get('direction')=='request' and e.get('payload',{}).get('method')=='turn/start' for e in events)):
            raise RuntimeError('HELD TASKS handoff already dispatched or suffix state changed')
    for key in ('helper_imports','checkpoint_installed','release_manifest','release_manifest_sha256'):
        if recipe.get(key)!=old.get(key):raise RuntimeError('HELD TASKS origin source/install/protection identity')
    workflow_live_source_protection(material,old,recipe)
    producer=material['producer']
    for key in ('collector','tests'):
        if producer[key].get('sha256')!=TASKS_TIMEOUT_PINS[key] or sha(producer[key]['path'])!=TASKS_TIMEOUT_PINS[key]:raise RuntimeError('HELD archived TASKS producer identity')
    if (origin.get('collector_sha256')!=TASKS_TIMEOUT_PINS['collector'] or old.get('adapter_sha256')!=TASKS_TIMEOUT_PINS['collector'] or
        [ref['sha256'] for ref in producer['helpers']]!=[ref['sha256'] for ref in old['helper_imports']]):raise RuntimeError('HELD old/new TASKS producer distinction')
    for ref in producer['helpers']:
        if sha(ref['path'])!=ref['sha256']:raise RuntimeError('HELD archived TASKS helper drift')
    if old_release.get('seconds')!=180 or old_release.get('max_new_model_USER_turns')!=1:raise RuntimeError('HELD original TASKS limit')
    sent=[e for e in wire if e.get('direction')=='request' and e.get('payload',{}).get('method')=='turn/start']
    if (len(sent)!=1 or sent[0]['payload']['params'].get('threadId')!=origin['thread_id'] or
        any(e.get('direction')=='response_or_event' and (e['payload'].get('method')=='turn/completed' or ('id' in e['payload'] and 'method' in e['payload'])) for e in wire)):
        raise RuntimeError('HELD TASKS timeout terminal/request contradiction')
    pair=checked_json(origin['facts']['poststart-baseline-v3.json']);thread=checked_json(origin['facts']['thread-start-v3.json']);native=checked_json(origin['facts']['live-native-selection-receipt.json'])
    if (thread['process_id']!=origin['process_id'] or thread['response']['thread']['id']!=origin['thread_id'] or
        pair['first']!=pair['second'] or set(pair['snapshot']['snapshot'])!=set(THREAD_FIELDS) or
        any(thread['response'].get(k)!=pair['snapshot']['snapshot'][k] for k in THREAD_FIELDS) or
        native.get('status')!='BOUND_ACTUAL_RECEIPTS' or native['catalog']['enabled_unique_targets']!=16 or native['catalog']['load_errors']!=0 or
        checked_json(origin['facts']['live-rpc/closed.json']).get('stable') is not True):raise RuntimeError('HELD TASKS origin actual13/B1/native/closure')
    if material['before_scope']!=origin['scope_facts']['workflow-before-01.json']:raise RuntimeError('HELD actual TASKS before scope')
    before=checked_json(material['before_scope']);tasks=material['tasks'];name=tasks['path']
    if (Path(name).is_absolute() or '..' in Path(name).parts or Path(name).name!='tasks.md' or name in before or
        material['state'].get(name,{}).get('sha256')!=tasks['sha256'] or set(before)|{name}!=set(material['state']) or
        any(value!=material['state'][key] for key,value in before.items())):raise RuntimeError('HELD exact sole TASKS artifact delta')
    program=[]
    for index,kind in zip(TASKS_TIMEOUT_PINS['program_indices'],('commandExecution','fileChange','commandExecution')):
        entry=wire[index];item=entry['payload'].get('params',{}).get('item',{})
        if (entry['direction']!='response_or_event' or entry['payload'].get('method')!='item/completed' or item.get('type')!=kind or item.get('status')!='completed' or
            (kind=='commandExecution' and (type(item.get('exitCode')) is not int or item['exitCode']!=0 or item.get('cwd')!=str(root) or not isinstance(item.get('aggregatedOutput'),str)))):
            raise RuntimeError('HELD actual TASKS creation/readback program')
        program.append({'wire_index':index,'payload_sha256':canonical_hash(entry['payload']),'item_id':item['id']})
    if material.get('program')!=program:raise RuntimeError('HELD TASKS program whole-payload identities')
    content=checked_json(material['content_review']);data=checked_json(material['approval_DATA'])
    targets=[{'path':str(base/name),'sha256':tasks['sha256']} for base in (root,Path(origin['realroot']))]
    if (content.get('actual_context')!=material['origin'] or content.get('frozen_manifest')!=material['manifest'] or
        content.get('current_state_sha256')!=canonical_hash(material['state']) or content.get('current_records')!=len(material['state']) or
        content.get('tasks_draft') not in targets or content.get('actual_plan_approval_delivered') is not False or content.get('runtime_authorized') is not False or
        data.get('context')!=material['origin'] or data.get('content_program_state_review')!=material['content_review'] or data.get('model_input_DATA')!=material['input_DATA'] or
        data.get('draft_artifact')!=content['tasks_draft'] or data.get('status')!='NOT_SENT_NOT_ACTUAL_APPROVAL' or
        row.get('initial_user_text')!=Path(material['input_DATA']['path']).read_bytes().decode('utf-8') or
        sent[0]['payload']['params']['input']==[{'type':'text','text':row['initial_user_text']}]):raise RuntimeError('HELD concrete TASKS content/NOT_SENT input relation')
    return material['origin']


def workflow_usage(references):
    def finite_policy_history(record, producer, wire, release, context_reference=None):
        """Replay retained proof only. Never execute producers or consult host HOME."""
        scope=finite_scope(record.get('root'))
        logical_root=scope['root'];canonical_root=scope['canonical_root']
        if (record.get('producer_schema')!=FINITE_PRODUCER_SCHEMA or producer.get('producer_schema')!=FINITE_PRODUCER_SCHEMA or
            record.get('root')!=logical_root or record.get('realroot')!=canonical_root or
            record.get('finite_policy_declaration')!=producer.get('finite_policy_declaration')):raise RuntimeError('HELD finite producer stripping/downgrade')
        reference=record['finite_policy_declaration'];declaration=checked_json(reference)
        if (declaration.get('schema')!='ROOT_FINITE_SESSION_TRUST_DECLARATION_V1' or declaration.get('decision')!='DECLARE_EXACT_PROCESS_ONLY_POLICY' or
            declaration.get('collector_sha256')!=record.get('collector_sha256') or producer.get('adapter_sha256')!=record.get('collector_sha256') or
            declaration.get('helpers')!=producer.get('helper_imports') or declaration.get('official_commit')!=SEMANTIC_COMMIT or
            declaration.get('operator_choice')!=scope['operator_choice']):raise RuntimeError('HELD finite retained declaration/producer')
        validate_finite_producer(declaration,producer.get('helper_imports',[]))
        choice=checked_json(declaration['operator_choice']);policy=finite_session_policy(choice,producer)
        for key in ('base_recipe','checkpoint','product'):
            if declaration.get(key)!=choice.get(key):raise RuntimeError('HELD finite retained base reference')
            checked_json(declaration[key])
        base=checked_json(declaration['base_recipe'])
        if base['rows'][0]['initial_user_text']!=producer['rows'][0]['initial_user_text']:raise RuntimeError('HELD finite retained original USER')
        expected_producer=dict(base,adapter_sha256=declaration['collector_sha256'],producer_schema=FINITE_PRODUCER_SCHEMA,finite_policy_declaration=reference)
        pair={'native_delta.py':declaration['collector_sha256'],'native_delta_test.py':declaration['tests_sha256']}
        expected_producer['protected_files']=[dict(v,sha256=pair[Path(v['path']).name]) if v['path'].endswith(tuple('/tests/runtime/codex/'+name for name in pair)) else dict(v) for v in base['protected_files']]
        expected_producer['usage']=finite_recipe_usage(base,producer)
        if producer!=expected_producer:raise RuntimeError('HELD finite retained exact recipe/source-only protection delta')

        if not release.get('native_premises'):raise RuntimeError('HELD finite retained native premises required')
        premises=checked_json(release['native_premises'])
        retained_home=validate_finite_metadata(declaration,producer,premises['forward_thread_expectation']['instructionSources'],choice)
        policy.update(declaration=reference,metadata_paths=declaration['metadata_paths'])
        facts=record.get('policy_facts',{})
        required={'finite-lookup-input.json','finite-prelaunch.json','preflight.json','catalog-rpc/launch.json','catalog-rpc/rpc.json','catalog-rpc/closed.json','live-rpc/launch.json'}
        if not required<=set(facts):raise RuntimeError('HELD finite retained launch/bootstrap proof')
        pre=checked_json(facts['finite-prelaunch.json']);preflight=checked_json(facts['preflight.json'])
        if (pre.get('schema')!=FINITE_POLICY_SCHEMA or pre.get('files')!=policy['metadata_paths'] or
            not pre.get('mdm_before') or any(pre['mdm_before'].values()) or pre.get('mdm_after')!=pre['mdm_before'] or
            preflight.get('first')!=pre or preflight.get('second')!=pre or preflight.get('transport')!='live'):
            raise RuntimeError('HELD finite retained metadata/raw equality')
        lookup_input=checked_json(facts['finite-lookup-input.json'])
        if lookup_input.get('failure_stage') not in ('before-catalog','before-live','before-thread','after-thread','predispatch','dispatched','terminal'):raise RuntimeError('HELD finite retained failure stage')
        if lookup_input.get('current_receipt')!=premises.get('unchanged_startup'):raise RuntimeError('HELD finite native input lookup Ref')
        certificate=validate_finite_lookup(lookup_input['current_receipt'],policy,record['collector_sha256'],record['recipe']['sha256'],producer['release_manifest_sha256'],declaration['binary_sha256'])
        catalog_wire=checked_json(facts['catalog-rpc/rpc.json'])
        if [e['payload'].get('method') for e in catalog_wire if e.get('direction')=='request']!=['initialize','initialized','config/read','skills/list','config/read']:raise RuntimeError('HELD finite retained bootstrap sequence')
        catalog_requests=[e['payload'] for e in catalog_wire if e.get('direction')=='request' and e['payload'].get('method')=='skills/list']
        replies=[e['payload'] for e in catalog_wire if e.get('direction')=='response_or_event' and e['payload'].get('id')==catalog_requests[0].get('id')]
        if len(replies)!=1 or 'result' not in replies[0] or 'error' in replies[0]:raise RuntimeError('HELD finite retained bootstrap catalog response')
        catalog=replies[0]['result'];groups=catalog.get('data',[])
        if catalog.get('errors') or len(groups)!=1 or groups[0].get('cwd')!=logical_root or groups[0].get('errors')!=[]:raise RuntimeError('HELD finite retained bootstrap catalog errors/cwd')
        targets=[v for v in groups[0].get('skills',[]) if v.get('name') in MANUAL|AUTO]
        installed={v['name']:v for v in producer.get('checkpoint_installed',[])}
        if len(targets)!=16 or {v.get('name') for v in targets}!=MANUAL|AUTO or set(installed)!=MANUAL|AUTO or any(v.get('enabled') is not True or v.get('path') not in (installed[v['name']]['path'],installed[v['name']]['realpath']) for v in targets):raise RuntimeError('HELD finite retained bootstrap catalog16')
        projections=[]
        for kind,log in (('catalog',catalog_wire),('live',wire)):
            launch=checked_json(facts[kind+'-rpc/launch.json'])
            if (launch.get('producer_schema')!=FINITE_PRODUCER_SCHEMA or launch.get('finite_policy')!=policy or launch.get('policy_metadata')!=pre or
                launch.get('identity',{}).get('sha256')!=declaration.get('binary_sha256')):raise RuntimeError('HELD finite retained launch identity')
            if launch.get('environment',{}).get('identity_sha256',{}).get('HOME')!=hashlib.sha256(str(Path(retained_home).parent).encode()).hexdigest():raise RuntimeError('HELD finite retained HOME identity')
            if type(launch.get('process_id')) is not int or launch.get('cwd')!=logical_root or (kind=='live' and launch['process_id']!=record.get('process_id')):raise RuntimeError('HELD finite retained launch process/cwd')
            indexed=[(i,e) for i,e in enumerate(log) if e.get('direction')!='transport_error']
            if any(e.get('wire_index')!=i or type(e.get('monotonic_ns')) is not int for i,e in indexed) or any(a[1]['monotonic_ns']>b[1]['monotonic_ns'] for a,b in zip(indexed,indexed[1:])):raise RuntimeError('HELD finite retained complete indexed process wire')
            validate_finite_policy_argv(launch.get('actual_argv'),policy)
            closed=checked_json(facts['catalog-rpc/closed.json'] if kind=='catalog' else record['facts']['live-rpc/closed.json'])
            if closed.get('stable') is not True or closed.get('policy_metadata')!=pre:raise RuntimeError('HELD finite retained process close/raw equality')
            requests={e['payload'].get('id'):e['payload'] for e in log if e.get('direction')=='request' and e['payload'].get('method')=='config/read'}
            for entry in log:
                payload=entry.get('payload',{})
                if entry.get('direction')!='response_or_event' or payload.get('id') not in requests:continue
                if payload.get('status')!='ok':continue
                projection=payload.get('policy');structural=payload.get('structural_result',{})
                if not isinstance(projection,dict):raise RuntimeError('HELD finite retained projection stripped')
                meta={'name':{'type':'sessionFlags'},'version':policy['session_version']}
                if (projection.get('schema')!=FINITE_POLICY_SCHEMA or projection.get('session')!=policy['session'] or
                    projection.get('session_version')!=policy['session_version'] or projection.get('session_metadata')!=meta or
                    projection.get('origin')!=meta or projection.get('origin_path')!='projects.'+canonical_root+'.trust_level' or
                    projection.get('project_layer_count')!=0 or projection.get('config_identity')!=structural.get('safe_identity') or
                    projection.get('response_identity')!=structural.get('response_identity')):raise RuntimeError('HELD finite retained origin/fingerprint/identity')
                persistent=projection.get('persistent_layers',[])
                layers=structural.get('layers',[])
                if (len(layers)!=len(persistent)+1 or not persistent or [layer.get('source',{}).get('type') for layer in layers] not in (['sessionFlags','user'],['sessionFlags','user','system'])):raise RuntimeError('HELD finite retained layer coverage')
                candidates=[{'category':label,'path':path,'present':False} for label,path in [('cwd-canonical',canonical_root),('cwd-original',logical_root),('repo-canonical',canonical_root),('repo-original',logical_root)]]
                for retained,layer in zip(persistent,layers[1:]):
                    if (retained.get('candidates')!=candidates or retained.get('metadata')!={'name':layer.get('source'),'version':layer.get('version')} or
                        layer.get('source',{}).get('type') not in ('user','system') or layer.get('disabled_reason') is not None or
                        retained.get('identity')!=layer.get('safe_identity')):raise RuntimeError('HELD finite retained persistent absence/identity')
                session=layers[0]
                if session.get('source')!=meta['name'] or session.get('version')!=meta['version'] or session.get('safe_identity')!=safe_config_identity(policy['session']):raise RuntimeError('HELD finite retained session structural identity')
                effective=structural.get('effective',{})
                if (any(effective.get('canonical_features',{}).get(k) is not False for k in CANONICAL_FEATURES) or
                    any(effective.get('discovery',{}).get(k) is not False for k in DISCOVERY_KEYS) or effective.get('include_instructions') is not True):raise RuntimeError('HELD finite retained features/instructions')
                if projections and projection!=projections[0]:raise RuntimeError('HELD finite retained config/raw drift')
                projections.append(projection)
        if len(projections)<2:raise RuntimeError('HELD finite retained catalog observations')
        if context_reference==SPEC_CLOSURE_ZERO_CONTEXT:
            proof=spec_closure_zero_provenance()
            if record!=proof['record'] or projections[0]!=redacted_config(certificate['policy']):raise RuntimeError('HELD exact historical zero serialization relation')
        else:
            validate_finite_lookup(lookup_input['current_receipt'],policy,record['collector_sha256'],record['recipe']['sha256'],producer['release_manifest_sha256'],declaration['binary_sha256'],projections[0])
        dispatched=any(e.get('direction')=='request' and e.get('payload',{}).get('method')=='turn/start' for e in wire)
        if dispatched:
            if lookup_input['failure_stage'] not in ('dispatched','terminal'):raise RuntimeError('HELD finite dispatched failure stage')
            required_native={'poststart-baseline-v3.json','thread-start-v3.json','live-native-selection-receipt.json'}
            if not required_native<=set(record['facts']) or 'startup-diagnostic-v3.json' not in facts:raise RuntimeError('HELD finite dispatched native/startup proof required')
            retained=record['facts'];baseline=checked_json(retained['poststart-baseline-v3.json']);thread=checked_json(retained['thread-start-v3.json'])
            premises=checked_json(release['native_premises']);expected=premises.get('forward_thread_expectation',{})
            if (set(expected)!=set(THREAD_FIELDS) or baseline.get('snapshot')!=reconcile_thread(thread['response'],thread['request'],expected) or
                thread['response'].get('thread',{}).get('id')!=record.get('thread_id') or thread.get('process_id')!=record.get('process_id') or
                thread['request']!={'cwd':logical_root,'model':'gpt-6.1-sol','approvalPolicy':'never','sandbox':'workspace-write','ephemeral':True} or
                baseline.get('first')!=baseline.get('second')):raise RuntimeError('HELD finite dispatched actual13/B1 including failure')
            native=checked_json(retained['live-native-selection-receipt.json']);selection=native.get('closure_wire',{});start=selection.get('wire_start_index');end=selection.get('wire_end_index')
            if type(start) is not int or type(end) is not int or not 0<=start<end<=len(wire):raise RuntimeError('HELD finite dispatched native wire range')
            requests=[e['payload'] for e in wire[start:end] if e.get('direction')=='request']
            if [v.get('method') for v in requests]!=['config/read','skills/list']:raise RuntimeError('HELD finite dispatched native selection sequence')
            replies=[e['payload'] for e in wire[start:end] if e.get('direction')=='response_or_event' and e['payload'].get('id')==requests[1].get('id')]
            if len(replies)!=1 or 'result' not in replies[0] or 'error' in replies[0]:raise RuntimeError('HELD finite dispatched native catalog response')
            groups=replies[0]['result'].get('data',[])
            if len(groups)!=1 or groups[0].get('cwd')!=logical_root or groups[0].get('errors')!=[] or replies[0]['result'].get('errors'):raise RuntimeError('HELD finite dispatched native catalog errors')
            entries=groups[0].get('skills',[]);targets=[v for v in entries if v.get('name') in MANUAL|AUTO]
            if len(targets)!=16 or {v.get('name') for v in targets}!=MANUAL|AUTO or any(v.get('enabled') is not True or v.get('path') not in (installed[v['name']]['path'],installed[v['name']]['realpath']) for v in targets):raise RuntimeError('HELD finite dispatched catalog16')
            config_replies=[e['payload'] for e in wire[start:end] if e.get('direction')=='response_or_event' and e['payload'].get('id')==requests[0].get('id')]
            if len(config_replies)!=1 or config_replies[0].get('status')!='ok' or config_replies[0].get('policy')!=projections[0]:raise RuntimeError('HELD finite dispatched native observed policy')
            selection_facts=config_replies[0]['structural_result']
            catalog_proof={'enabled_unique_targets':16,'applicable_catalog_entries':len(entries),'load_errors':0,'target_paths':[v['path'] for v in targets],
                'layer_root_sources':[v['source'] for v in selection_facts['layers']],'loader_relation':'Actual live RPC active config/catalog; no ignored-user projection','semantic_source':SEMANTIC_COMMIT,'universal_global_catalog_claim':False}
            native_binding=dict(premises,finite_session_policy=policy,_finite_policy_observation=projections[0])
            expected_native=native_selection_receipt(native_binding,catalog_proof,require_environment(baseline['first']['environment'],premises),'live')
            if {k:v for k,v in native.items() if k!='closure_wire'}!=expected_native:raise RuntimeError('HELD finite dispatched native producer/proof receipt')
            thread_calls=finite_rpc_range(wire,thread.get('wire_start_index'),thread.get('wire_end_index'),['thread/start'])
            if (sum(e.get('direction')=='request' and e['payload'].get('method')=='thread/start' for e in wire)!=1 or thread.get('schema_version')!=RECEIPT_VERSION or thread_calls!=[(thread['request'],thread['response'])] or
                baseline['first'].get('process_id')!=record['process_id'] or baseline['first'].get('thread_id')!=record['thread_id']):raise RuntimeError('HELD finite actual thread wire/B1 identities')
            selected=finite_rpc_range(wire,start,end,['config/read','skills/list'])
            if selected[0][0]!={'includeLayers':True,'cwd':record['root']} or selected[1][0]!={'cwds':[record['root']],'forceReload':True}:raise RuntimeError('HELD finite native selector parameters')
            dispatches=[i for i,e in enumerate(wire) if e.get('direction')=='request' and e['payload'].get('method')=='turn/start']
            if len(dispatches)!=1:raise RuntimeError('HELD finite one actual dispatch')
            ranges=[]
            agents=logical_root+'/AGENTS.md'
            if agents not in expected['instructionSources']:raise RuntimeError('HELD finite dispatched native AGENTS instructionSources')
            for index,phase in enumerate(('preflight','post-start-1','post-start-2','predispatch')):
                frame=checked_json(record['scope_facts']['workflow-closure-bundle-%03d.json'%index]);sample=checked_json(record['scope_facts']['workflow-closure-sample-%03d.json'%index])
                left=sample.get('wire_start_index');right=sample.get('wire_end_index')
                calls=finite_rpc_range(wire,left,right,['config/read','skills/list','config/read'])
                frame_ref=record['scope_facts']['workflow-closure-bundle-%03d.json'%index]
                if (sample.get('schema')!='spec-closure-sample-v2' or sample.get('frame')!=frame_ref or set(frame_ref)!={'path','sha256'} or
                    sample.get('process_id')!=record['process_id'] or sample.get('thread_id')!=(None if index==0 else record['thread_id']) or
                    frame.get('process_id')!=record['process_id'] or frame.get('thread_id')!=sample.get('thread_id') or
                    calls[0][0]!={'includeLayers':True,'cwd':record['root']} or calls[1][0]!={'cwds':[record['root']],'forceReload':True} or calls[2][0]!=calls[0][0] or
                    calls[0][1]!=frame.get('config') or calls[2][1]!=frame.get('config') or calls[1][1]!=frame.get('catalog') or
                    sample.get('before')!=checked_json(declaration['checkpoint'])['state'] or
                    frame.get('schema_version')!=RECEIPT_VERSION or frame.get('installed')!=producer['checkpoint_installed'] or frame.get('environment')!=baseline['first']['environment'] or
                    frame.get('manifest_sha256')!=producer['release_manifest_sha256'] or frame.get('binary_sha256')!=declaration['binary_sha256']):raise RuntimeError('HELD finite predispatch frame/RPC/identity binding')
                if any(frame.get('files',{}).get(path)!=entry for path,entry in policy['metadata_paths'].items()):raise RuntimeError('HELD finite predispatch full raw metadata identities')
                if frame.get('catalog_proof')!=catalog_proof:raise RuntimeError('HELD finite predispatch catalog proof')
                ranges.append((left,right))
                if (sample.get('phase')!=phase or sample.get('bundle_id')!=index or sample.get('stable') is not True or sample.get('before')!=sample.get('after') or
                    frame.get('finite_policy')!=projections[0] or frame.get('policy_metadata')!=pre or
                    frame.get('files',{}).get(agents,{}).get('sha256')!=choice['AGENTS_sha256'] or index>0 and frame!=baseline['first']):raise RuntimeError('HELD finite dispatched predispatch policy/AGENTS/B1 continuity')
            if (ranges[0]!=(end,thread['wire_start_index']) or ranges[1][0]!=thread['wire_end_index'] or ranges[1][1]!=ranges[2][0] or
                ranges[2][1]!=baseline.get('wire_end_index') or ranges[3]!=(ranges[2][1],dispatches[0])):raise RuntimeError('HELD finite four ordered predispatch ranges')
            diagnostic=checked_json(facts['startup-diagnostic-v3.json']);no_write=diagnostic.get('no_write_lookup',{})
            if (no_write.get('schema')!='startup-no-write-owned-fixture-policy-v2' or no_write.get('policy')!=projections[0] or
                no_write.get('before')!=certificate['classification'] or no_write.get('after')!=certificate['classification'] or no_write.get('mode')!=certificate['mode'] or no_write.get('current_receipt')!=lookup_input['current_receipt'] or diagnostic.get('post_bundle_lookup')!=certificate['classification'] or
                no_write.get('declaration')!=reference or diagnostic.get('startup_raw_equal') is not True):raise RuntimeError('HELD finite retained startup no-write proof')
        if record.get('healthy'):
            frames=[checked_json(record['scope_facts']['workflow-closure-bundle-%03d.json'%i]) for i in range(5)]
            for frame in frames:
                if frame.get('finite_policy')!=projections[0] or frame.get('policy_metadata')!=pre:raise RuntimeError('HELD finite retained five policy bundles')
            instructions=checked_json(release['native_premises'])['forward_thread_expectation']['instructionSources']
            agents=logical_root+'/AGENTS.md'
            if agents not in instructions or any(frame.get('files',{}).get(agents,{}).get('sha256')!=choice['AGENTS_sha256'] for frame in frames):raise RuntimeError('HELD finite retained AGENTS bytes/instructionSources')
        return policy
    used={};seen=set();prior=[]
    for ref in references:
        record=checked_json(ref)
        if (record.get('schema')!='workflow-context-v1' or record.get('closed') is not True or
            type(record.get('server_returncode')) is not int or record.get('prior_usage_sha256')!=canonical_hash(prior) or
            not record.get('release_id') or record['release_id'] in seen):raise RuntimeError('HELD missing/reordered/forked workflow usage')
        purpose=record.get('purpose');phase=record.get('phase');unit=record.get('unit')
        if purpose not in WORKFLOW_LIMITS or phase not in WORKFLOW_LIMITS[purpose]:raise RuntimeError('HELD unknown recorded phase')
        allowed=({'changed-spec'} if purpose=='spec-closure-regression' else {'original-notification'} if purpose=='original-notification-draft' else WORKFLOW_SETUP_UNITS|{'notification-workflow'} if purpose in ('setup-observe','setup-ack-repeat') else {'notification-workflow'})
        if unit not in allowed:raise RuntimeError('HELD unknown recorded workflow unit')
        wire=checked_json(record['wire'])
        count=sum(e.get('direction')=='request' and e.get('payload',{}).get('method')=='turn/start' for e in wire)
        release=checked_json(record['release'])
        if any(release.get(k)!=record.get(k) for k in ('purpose','phase','unit','root','release_id')):raise RuntimeError('HELD usage release/context mismatch')
        if type(release.get('max_new_model_USER_turns')) is not int or count>release['max_new_model_USER_turns']:raise RuntimeError('HELD actual dispatch count exceeded release')
        closed=checked_json(record['facts']['live-rpc/closed.json'])
        if closed.get('stable') is not True:raise RuntimeError('HELD usage closed environment drift')
        if count:
            thread=checked_json(record['facts']['thread-start-v3.json'])
            if thread['process_id']!=record['process_id'] or thread['response']['thread']['id']!=record['thread_id']:raise RuntimeError('HELD usage actual process/thread binding')
        if record.get('tasks_timeout_handoff') is not None or release.get('row_id')==TASKS_TIMEOUT_ROW:
            recipe=checked_json(record['recipe']);cp=checked_json(recipe['workflow_checkpoint']);material=checked_json(cp['materialization']);row=recipe['rows'][0]
            origin=workflow_tasks_handoff(material,prior,recipe,row)
            relation={'origin':origin,'materialization':cp['materialization'],'row_id':TASKS_TIMEOUT_ROW}
            review=checked_json(release['root_review']);source=checked_json(release['source_review'])
            common={'checkpoint_sha256':recipe['workflow_checkpoint']['sha256'],'recipe_sha256':record['recipe']['sha256'],
                'collector_sha256':record['collector_sha256'],'helpers':recipe['helper_imports'],'manifest_sha256':recipe['release_manifest_sha256'],
                'native_premises_sha256':release['native_premises']['sha256'],'purpose':purpose,'phase':phase,'unit':unit}
            checked_json(release['native_premises'])
            for doc,schema in ((source,'WORKFLOW_SOURCE_REVIEW_V1'),(review,'WORKFLOW_ROOT_REVIEW_V1'),(release,'WORKFLOW_RELEASE_V1')):
                if doc.get('schema')!=schema or any(doc.get(k)!=v for k,v in common.items()):raise RuntimeError('HELD historical TASKS source/Root/native common bindings')
            for doc in (source,review):
                if sha(doc['report']['path'])!=doc['report']['sha256']:raise RuntimeError('HELD historical TASKS concrete review report')
            workflow_live_source_protection(material,checked_json(checked_json(origin)['recipe']),recipe,source,review)
            if (review.get('source_review')!=release['source_review'] or review.get('state_sha256')!=canonical_hash(cp['state']) or review.get('usage_sha256')!=canonical_hash(prior) or
                any(ref not in review.get('authority_evidence',[]) for ref in (material['content_review'],material['approval_DATA'])) or
                review.get('business')!=checked_json(checked_json(checked_json(origin)['release'])['root_review'])['business'] or
                release.get('initial_USER_sha256')!=canonical_hash(row['initial_user_text'])):raise RuntimeError('HELD historical TASKS concrete review/USER relation')
            for authority in review['authority_evidence']:
                if sha(authority['path'])!=authority['sha256']:raise RuntimeError('HELD historical TASKS authority evidence hash')
            sent=[e for e in wire if e.get('direction')=='request' and e.get('payload',{}).get('method')=='turn/start']
            if (any(e.get('direction')=='request' and 'result' in e.get('payload',{}) for e in wire) or
                (count and sent[0]['payload'].get('params')!={'threadId':record['thread_id'],'input':[{'type':'text','text':row['initial_user_text']}]}) or
                (not count and record.get('state')!=cp['state']) or
                (record.get('healthy') is True and not healthy_terminal([e['payload'] for e in wire if e.get('direction')=='response_or_event'],'live'))):raise RuntimeError('HELD historical TASKS one real USER/full wire relation')
            if (record.get('tasks_timeout_handoff')!=relation or release.get('tasks_timeout_handoff')!=relation or review.get('tasks_timeout_handoff')!=relation or
                (purpose,phase,unit)!=(recipe['purpose'],recipe['phase'],recipe['unit']) or
                record['collector_sha256']!=recipe['adapter_sha256'] or release.get('collector_sha256')!=record['collector_sha256'] or
                release.get('recipe_sha256')!=record['recipe']['sha256'] or release.get('checkpoint_sha256')!=recipe['workflow_checkpoint']['sha256'] or
                cp.get('schema')!='workflow-materialization-v1' or cp.get('state')!=material['state'] or cp.get('root')!=record['root'] or
                release.get('row_id')!=row['id'] or type(release.get('max_new_model_USER_turns')) is not int or release['max_new_model_USER_turns']!=1 or release.get('seconds')!=180 or count>1 or
                any(doc.get('decision')!='APPROVE_EXACT_BOUND_CONTEXT' or doc.get('recipe_sha256')!=record['recipe']['sha256'] for doc in (review,source))):
                raise RuntimeError('HELD historical TASKS handoff receipt/review/release relation')
        if purpose=='spec-closure-regression':
            producer=checked_json(record['recipe']);rows=producer.get('rows',[])
            if len(rows)!=1:raise RuntimeError('HELD closure one-row producer')
            row=rows[0];workflow_limits(producer,row,used);cp=checked_json(producer['workflow_checkpoint'])
            entries=[(i,e) for i,e in enumerate(wire) if e.get('direction')!='transport_error']
            if (len(entries)<3 or any(e.get('direction') not in ('request','response_or_event') or e.get('wire_index')!=i or type(e.get('monotonic_ns')) is not int for i,e in entries) or
                any(a[1]['monotonic_ns']>b[1]['monotonic_ns'] for a,b in zip(entries,entries[1:])) or
                wire[0].get('direction')!='request' or wire[0].get('payload',{}).get('method')!='initialize' or
                not any(e.get('direction')=='response_or_event' and e.get('payload',{}).get('id')==wire[0]['payload'].get('id') and 'result' in e.get('payload',{}) for e in wire[1:]) or
                not any(e.get('direction')=='request' and e.get('payload',{}).get('method')=='initialized' for e in wire[1:])):raise RuntimeError('HELD closure complete indexed startup wire required')
            if record['wire']['path']!=str(Path(release['out'])/'live-rpc/rpc.json') or release.get('realroot')!=record['realroot']:raise RuntimeError('HELD closure actual output/canonical root')
            if cp.get('schema')!='workflow-materialization-v1':raise RuntimeError('HELD closure authentic materialized prestate only')
            material=checked_json(cp['materialization']);source=checked_json(release['source_review']);review=checked_json(release['root_review'])
            relation=spec_closure_component(producer,row,material,prior,review)
            common={'checkpoint_sha256':producer['workflow_checkpoint']['sha256'],'recipe_sha256':record['recipe']['sha256'],'collector_sha256':producer['adapter_sha256'],
                'helpers':producer['helper_imports'],'manifest_sha256':producer['release_manifest_sha256'],'native_premises_sha256':release['native_premises']['sha256'],'purpose':purpose,'phase':phase,'unit':unit}
            premises=checked_json(release['native_premises'])
            if record.get('root') in FINITE_SCOPES or producer.get('producer_schema')==FINITE_PRODUCER_SCHEMA or record.get('producer_schema')==FINITE_PRODUCER_SCHEMA:
                retained_policy=finite_policy_history(record,producer,wire,release,ref)
                if premises.get('finite_policy_declaration')!=producer.get('finite_policy_declaration'):raise RuntimeError('HELD finite native declaration relation')
                live_observations=[e['payload']['policy'] for e in wire if e.get('direction')=='response_or_event' and e.get('payload',{}).get('status')=='ok' and 'policy' in e['payload']]
                # A zero request can fail before any live config reply. Its input
                # certificate is retained provenance, never a poststart observation.
                if not live_observations and count:raise RuntimeError('HELD finite dispatched live observation required')
                observed=live_observations[0] if live_observations else checked_json(premises['unchanged_startup'])['policy']
                premises=dict(premises,finite_session_policy=retained_policy,_finite_policy_observation=observed)
            for doc,schema in ((source,'WORKFLOW_SOURCE_REVIEW_V1'),(review,'WORKFLOW_ROOT_REVIEW_V1'),(release,'WORKFLOW_RELEASE_V1')):
                if doc.get('schema')!=schema or any(doc.get(k)!=v for k,v in common.items()):raise RuntimeError('HELD closure retained producer/source/Root/release identity')
            for doc in (source,review):
                if doc.get('decision')!='APPROVE_EXACT_BOUND_CONTEXT' or sha(doc['report']['path'])!=doc['report']['sha256']:raise RuntimeError('HELD closure concrete review')
            for authority in review.get('authority_evidence',[]):
                if sha(authority['path'])!=authority['sha256']:raise RuntimeError('HELD closure concrete authority evidence')
            if (producer.get('usage')!=prior or record.get('collector_sha256')!=producer['adapter_sha256'] or record.get('row_id')!=row['id'] or record.get('mode')!=row['mode'] or
                any(producer.get(k)!=record.get(k) for k in ('purpose','phase','unit')) or cp.get('root')!=record['root'] or cp.get('realroot')!=record['realroot'] or cp.get('state')!=material['state'] or
                release.get('row_id')!=row['id'] or type(release.get('max_new_contexts')) is not int or release['max_new_contexts']!=1 or release.get('max_new_model_USER_turns')!=1 or type(release.get('seconds')) is not int or release['seconds']!=180 or
                release.get('initial_USER_sha256')!=canonical_hash(row['initial_user_text']) or review.get('source_review')!=release['source_review'] or review.get('state_sha256')!=canonical_hash(cp['state']) or review.get('usage_sha256')!=canonical_hash(prior) or count>1):
                raise RuntimeError('HELD closure retained chronology/row/USER')
            if any(e.get('direction')=='request' and 'result' in e.get('payload',{}) for e in wire):raise RuntimeError('HELD closure no second USER')
            sent=[e['payload']['params'] for e in wire if e.get('direction')=='request' and e.get('payload',{}).get('method')=='turn/start']
            if sent and sent!=[{'threadId':record['thread_id'],'input':[{'type':'text','text':row['initial_user_text']}]}]:raise RuntimeError('HELD closure actual dispatched USER')
            known_zero=(ref==SPEC_CLOSURE_ZERO_CONTEXT and record==spec_closure_zero_provenance()['record'])
            if not count and (record.get('healthy') is not False or (not record.get('failure') and not known_zero) or record.get('state')!=cp['state']):raise RuntimeError('HELD closure incomplete zero-request evidence')
            if record.get('healthy') is True:
                events=[e['payload'] for e in wire if e.get('direction')=='response_or_event'];baseline=checked_json(record['facts']['poststart-baseline-v3.json']);config=checked_json(record['config_facts']['config-01.json']);native=checked_json(record['facts']['live-native-selection-receipt.json']);turn=checked_json(record['facts']['turn-01.json'])
                def rpc_range(start,end,methods):
                    if type(start) is not int or type(end) is not int or not 0<=start<end<=len(wire):raise RuntimeError('HELD closure RPC range')
                    requests=[(i,wire[i]['payload']) for i in range(start,end) if wire[i]['direction']=='request']
                    if [v.get('method') for i,v in requests]!=methods:raise RuntimeError('HELD closure actual RPC sequence')
                    if any(wire[i]['direction']=='response_or_event' and 'id' in wire[i]['payload'] and 'method' not in wire[i]['payload'] and wire[i]['payload']['id'] not in [v.get('id') for _,v in requests] for i in range(start,end)):raise RuntimeError('HELD closure foreign RPC response ID')
                    result=[]
                    for number,(index,request) in enumerate(requests):
                        ident=request.get('id')
                        replies=[i for i in range(index+1,end) if wire[i]['direction']=='response_or_event' and wire[i]['payload'].get('id')==ident and 'method' not in wire[i]['payload']]
                        if ident is None or len(replies)!=1 or sum(e.get('direction')=='request' and e.get('payload',{}).get('id')==ident for e in wire)!=1 or (number+1<len(requests) and replies[0]>=requests[number+1][0]):raise RuntimeError('HELD closure indexed request/response ID')
                        response=wire[replies[0]]['payload']
                        if request['method']=='config/read':
                            if response.get('status')!='ok' or response.get('receipt_schema')!=RECEIPT_VERSION or 'structural_result' not in response:raise RuntimeError('HELD closure config/read projection')
                            value=response['structural_result']
                        else:
                            if 'result' not in response or 'error' in response:raise RuntimeError('HELD closure successful RPC response')
                            value=response['result']
                        result.append((request.get('params'),value))
                    return result
                installed=baseline['first']['installed'];install=checked_json(material['install'])
                if len(installed)!=16 or {v.get('name') for v in installed}!=MANUAL|AUTO:raise RuntimeError('HELD closure retained installed16')
                for value in installed:
                    body=install['bodies'][value['name']];meta=install['metadata'].get('skills/'+value['name']+'/agents/openai.yaml');digest=meta['sha256'] if meta else None
                    if any(value.get(k)!=v for k,v in {'path':body['path'],'realpath':body['realpath'],'sha256':body['sha256'],'source_sha256':body['sha256'],'metadata_sha256':digest,'source_metadata_sha256':digest}.items()):raise RuntimeError('HELD closure installed body/metadata identity')
                def catalog_proof(catalog,facts):
                    groups=catalog.get('data')
                    if not isinstance(groups,list) or len(groups)!=1 or groups[0].get('cwd') not in (record['root'],record['realroot']) or not isinstance(groups[0].get('skills'),list) or groups[0].get('errors')!=[] or catalog.get('errors'):raise RuntimeError('HELD closure complete retained catalog')
                    targets=[v for v in groups[0]['skills'] if v.get('name') in MANUAL|AUTO];expected={v['name']:v for v in installed}
                    if len(targets)!=16 or {v['name'] for v in targets}!=MANUAL|AUTO or any(v.get('enabled') is not True or v.get('path') not in (expected[v['name']]['path'],expected[v['name']]['realpath']) for v in targets):raise RuntimeError('HELD closure exact enabled catalog targets')
                    if facts['effective']['canonical_features']!={name:False for name in CANONICAL_FEATURES} or facts.get('source_semantics')!=SEMANTIC_COMMIT:raise RuntimeError('HELD closure retained config premise')
                    for layer in facts['layers']:
                        if layer['source'].get('type') not in ('user','system','sessionFlags') or layer.get('disabled_reason') or layer['facts']['discovery']['skip_host_skill_discovery'] is not False or layer['facts']['include_instructions'] is not True or any(v.get('enabled') is False and (v.get('name') in MANUAL|AUTO or v.get('path') in {x['path'] for x in installed}) for v in layer['facts']['skill_settings']):raise RuntimeError('HELD closure retained loader/layer premise')
                    return {'enabled_unique_targets':16,'applicable_catalog_entries':len(groups[0]['skills']),'load_errors':0,'target_paths':[v['path'] for v in targets],'layer_root_sources':[v['source'] for v in facts['layers']],'loader_relation':'Actual live RPC active config/catalog; no ignored-user projection','semantic_source':SEMANTIC_COMMIT,'universal_global_catalog_claim':False}
                if thread.get('schema_version')!=RECEIPT_VERSION or thread.get('process_id')!=record['process_id']:raise RuntimeError('HELD closure thread producer identity')
                thread_call=rpc_range(thread['wire_start_index'],thread['wire_end_index'],['thread/start'])[0]
                if thread_call!=(thread.get('request'),thread['response']) or thread['response'].get('thread',{}).get('id')!=record['thread_id'] or thread['request'].get('cwd')!=record['root'] or set(thread['request'])!={'cwd','model','approvalPolicy','sandbox','ephemeral'} or thread['request'].get('ephemeral') is not True:raise RuntimeError('HELD closure exact thread/start wire')
                expected=copy.deepcopy(premises['forward_thread_expectation']);homes=set()
                # Only the persisted display of these13 released fields is compared.
                # Derive historical HOME from paired paths and captured identities,
                # never from today's host; no config/catalog normalization occurs.
                def paired_homes(raw,display):
                    if isinstance(raw,dict) and isinstance(display,dict):
                        for key in raw.keys()&display.keys():paired_homes(raw[key],display[key])
                    elif isinstance(raw,list) and isinstance(display,list):
                        for left,right in zip(raw,display):paired_homes(left,right)
                    elif isinstance(raw,str) and isinstance(display,str):
                        marker='<HOST_HOME>';start=display.find(marker)
                        while start!=-1:
                            if raw.startswith(display[:start]):
                                for end in range(start+1,len(raw)+1):
                                    candidate=raw[start:end]
                                    if candidate.startswith('/') and raw.replace(candidate,marker)==display:homes.add(candidate)
                            start=display.find(marker,start+len(marker))
                for key in THREAD_FIELDS:paired_homes(expected.get(key),thread['response'].get(key))
                if homes:
                    if len(homes)!=1:raise RuntimeError('HELD closure ambiguous historical HOME display')
                    home=next(iter(homes));identity=hashlib.sha256(home.encode()).hexdigest();closed_environment=closed.get('environment_after',{})
                    if not Path(home).is_absolute() or any(env.get('identity_sha256',{}).get('HOME')!=identity or env.get('default_home') is not True or env.get('default_codex_home') is not True for env in (baseline['first']['environment'],baseline['second']['environment'],closed_environment)):raise RuntimeError('HELD closure historical HOME identity')
                    def display13(value):
                        if isinstance(value,str):return value.replace(home,'<HOST_HOME>')
                        if isinstance(value,list):return [display13(v) for v in value]
                        if isinstance(value,dict):return {k:display13(v) for k,v in value.items()}
                        return value
                    expected=display13(expected)
                if baseline['snapshot']!=reconcile_thread(thread['response'],thread['request'],expected):raise RuntimeError('HELD closure released native13/snapshot')
                selection=native.get('closure_wire',{})
                if set(selection)!={'schema','wire_start_index','wire_end_index'} or selection.get('schema')!='spec-closure-native-wire-v1':raise RuntimeError('HELD closure native selection range')
                selected=rpc_range(selection['wire_start_index'],selection['wire_end_index'],['config/read','skills/list'])
                if selected[0][0]!={'includeLayers':True,'cwd':record['root']} or selected[1][0]!={'cwds':[record['root']],'forceReload':True}:raise RuntimeError('HELD closure native selector cwd/reload')
                expected_native=native_selection_receipt(premises,catalog_proof(selected[1][1],selected[0][1]),require_environment(baseline['first']['environment'],premises),'live')
                if {k:v for k,v in native.items() if k!='closure_wire'}!=expected_native or native['parent_release_id']!=record['release_id']:raise RuntimeError('HELD closure native receipt/released proof')
                starts=[i for i,e in enumerate(wire) if e.get('direction')=='request' and e.get('payload',{}).get('method')=='turn/start'];ends=[e for e in wire if e.get('direction')=='response_or_event' and e.get('payload',{}).get('method')=='turn/completed']
                returned=rpc_range(starts[0],next(i for i in range(starts[0]+1,len(wire)) if wire[i]['direction']=='request'),['turn/start'])[0]
                turn_id=returned[1].get('turn',{}).get('id')
                if not isinstance(turn_id,str) or not turn_id:raise RuntimeError('HELD closure returned turn identity')
                for event in events:
                    method=event.get('method','');params=event.get('params',{})
                    if method.startswith(('turn/','item/')):
                        if params.get('threadId')!=record['thread_id']:raise RuntimeError('HELD closure foreign/missing lifecycle thread')
                        observed=params.get('turn',{}).get('id') if method in ('turn/started','turn/completed') else params.get('turnId')
                        if observed!=turn_id:raise RuntimeError('HELD closure contradictory lifecycle turn')
                eligible=[e for e in events if e.get('method')=='item/completed' and e.get('params',{}).get('threadId')==record['thread_id'] and e.get('params',{}).get('item',{}).get('type')=='agentMessage' and e['params']['item'].get('phase')=='final_answer' and isinstance(e['params']['item'].get('text'),str) and e['params']['item']['text'].strip()]
                if (count!=1 or not healthy_terminal(events,'live') or len(ends)!=1 or not eligible or
                    any(type(e.get('monotonic_ns')) is not int for e in (wire[starts[0]],ends[0])) or not 0<=ends[0]['monotonic_ns']-wire[starts[0]]['monotonic_ns']<180_000_000_000 or
                    not any(e['params'].get('turnId')==ends[0]['payload']['params']['turn'].get('id') for e in eligible) or
                    turn.get('wire_start_index')!=starts[0] or turn.get('wire_end_index')!=len(wire) or turn.get('events')!=[e['payload'] for e in wire[starts[0]:] if e['direction']=='response_or_event'] or
                    baseline['first'].get('process_id')!=record['process_id'] or baseline['first'].get('thread_id')!=record['thread_id'] or
                    baseline['first']!=baseline['second'] or config.get('before')!=baseline['first'] or config.get('after')!=config.get('before') or config.get('raw_stable') is not True or config.get('schema_version')!=RECEIPT_VERSION or config.get('projection_used') is not False or config.get('baseline_reset_allowed') is not False or
                    set(baseline['snapshot']['snapshot'])!=set(THREAD_FIELDS) or any(thread['response'].get(k)!=baseline['snapshot']['snapshot'][k] for k in THREAD_FIELDS) or
                    native.get('status')!='BOUND_ACTUAL_RECEIPTS' or native['catalog']['enabled_unique_targets']!=16 or native['catalog']['load_errors']!=0 or
                    turn.get('text')!=row['initial_user_text'] or turn.get('thread')!=record['thread_id'] or type(turn.get('seconds')) not in (int,float) or not 0<=turn['seconds']):raise RuntimeError('HELD closure complete healthy native/config/turn proof')
                before=cp['state'];after=record['state'];draft=relation['draft_path']
                if set(before)!=set(after) or any(before[k]!=after[k] for k in before if k!=draft) or {k:v for k,v in before[draft].items() if k not in ('sha256','identity')}!={k:v for k,v in after[draft].items() if k not in ('sha256','identity')}:raise RuntimeError('HELD closure retained draft-only state')
                identity=after[draft].get('identity')
                if not isinstance(identity,list) or len(identity)!=2 or any(type(v) is not int for v in identity) or any(k!=draft and value.get('identity')==identity for k,value in after.items()):raise RuntimeError('HELD closure draft postimage alias/identity')
                post=checked_json(record['scope_facts']['workflow-closure-postimage.json'])
                if (set(post)!=set('schema draft state_sha256 postimage before after business_PASS'.split()) or post.get('schema')!='spec-closure-postimage-v1' or post.get('before')!=before or post.get('after')!=after or post.get('business_PASS') is not False or
                    post.get('state_sha256')!=canonical_hash(after) or post.get('draft')!=draft or set(post['postimage'])!={'path','sha256'} or post['postimage']['sha256']!=after[draft]['sha256'] or sha(post['postimage']['path'])!=post['postimage']['sha256'] or not Path(post['postimage']['path']).read_bytes().startswith(b'---\nstatus: draft\n---')):raise RuntimeError('HELD closure concrete draft postimage')
                samples=sorted((name,ref) for name,ref in record['scope_facts'].items() if name.startswith('workflow-closure-sample-'))
                if len(samples)!=5 or [name for name,ref in samples]!=['workflow-closure-sample-%03d.json'%i for i in range(5)]:raise RuntimeError('HELD closure complete paired scope samples')
                last=selection['wire_end_index'];frames=[];ranges=[]
                phases=('preflight','post-start-1','post-start-2','predispatch','postterminal')
                for bundle_id,(name,reference) in enumerate(samples):
                    sample=checked_json(reference);observed=sample['after'];start=sample['wire_start_index'];end=sample['wire_end_index']
                    if (set(sample)!=set('schema bundle_id phase frame before after stable process_id thread_id wire_start_index wire_end_index'.split()) or sample['schema']!='spec-closure-sample-v2' or type(sample['bundle_id']) is not int or sample['bundle_id']!=bundle_id or sample['phase']!=phases[bundle_id] or sample['stable'] is not True or sample['before']!=observed or
                        sample['process_id']!=record['process_id'] or sample['thread_id'] not in (None,record['thread_id']) or type(start) is not int or type(end) is not int or not last<=start<=end<=len(wire) or
                        set(observed)!=set(before) or any(observed[k]!=before[k] for k in before if k!=draft) or {k:v for k,v in observed[draft].items() if k not in ('sha256','identity')}!={k:v for k,v in before[draft].items() if k not in ('sha256','identity')}):raise RuntimeError('HELD closure retained scope sampling/continuity')
                    frame_ref=record['scope_facts'].get('workflow-closure-bundle-%03d.json'%bundle_id)
                    if sample['frame']!=frame_ref or set(sample['frame'])!={'path','sha256'}:raise RuntimeError('HELD closure bundle identity/frame Ref')
                    frame=checked_json(frame_ref);calls=rpc_range(start,end,['config/read','skills/list','config/read'])
                    if (calls[0][0]!={'includeLayers':True,'cwd':record['root']} or calls[1][0]!={'cwds':[record['root']],'forceReload':True} or calls[2][0]!=calls[0][0] or
                        calls[0][1]!=frame['config'] or calls[2][1]!=frame['config'] or calls[1][1]!=frame['catalog'] or frame.get('catalog_proof')!=catalog_proof(calls[1][1],calls[0][1]) or
                        frame.get('process_id')!=record['process_id'] or frame.get('thread_id')!=(None if bundle_id==0 else record['thread_id']) or sample['thread_id']!=frame['thread_id'] or
                        frame.get('installed')!=installed or frame.get('environment')!=baseline['first']['environment'] or frame.get('manifest_sha256')!=producer['release_manifest_sha256'] or frame.get('binary_sha256')!=premises['executable_identity']['sha256']):raise RuntimeError('HELD closure bundle/RPC/native frame relation')
                    frames.append(frame);ranges.append((start,end))
                    identity=observed[draft].get('identity')
                    if not isinstance(identity,list) or len(identity)!=2 or any(type(v) is not int for v in identity) or any(k!=draft and value.get('identity')==identity for k,value in observed.items()):raise RuntimeError('HELD closure sampled draft alias/identity')
                    last=end
                if (ranges[0][0]!=selection['wire_end_index'] or ranges[0][1]!=thread['wire_start_index'] or ranges[1][0]!=thread['wire_end_index'] or ranges[1][1]!=ranges[2][0] or
                    ranges[2][1]!=baseline['wire_end_index'] or ranges[3][0]!=ranges[2][1] or ranges[3][1]!=starts[0] or ranges[4][0]!=ends[0]['wire_index']+1 or last!=len(wire) or
                    frames[1]!=baseline['first'] or frames[2]!=baseline['second'] or frames[3]!=config['before'] or frames[4]!=config['after'] or
                    checked_json(record['facts']['before-config-01-v3.json'])!=frames[3] or checked_json(samples[-1][1])['after']!=after or
                    any(checked_json(ref)['before']!=before for name,ref in samples[:4])):raise RuntimeError('HELD closure actual ordered bundle phases/B1/config boundary')
        if record.get('business_edit_contract') is not None or record.get('business_facts') or record.get('business_samples'):
            notification_business_history(record,prior,wire,release)
        key=unit+'/'+phase;used[key]=used.get(key,0)+count
        if used[key]>workflow_ceiling(purpose,phase,unit):raise RuntimeError('HELD recorded phase ceiling exceeded')
        seen.add(record['release_id']);prior.append(ref)
    return used


def workflow_user_evidence(reference, usage, root):
    evidence=checked_json(reference);context=evidence['context']
    if not any(workflow_ref_equal(x,context) for x in usage):raise RuntimeError('HELD actual USER context absent from usage')
    record=checked_json(context);wire=checked_json(record['wire']);index=evidence['wire_index']
    if record['root']!=str(root) or type(index) is not int or not 0<=index<len(wire):raise RuntimeError('HELD foreign actual USER root/index')
    entry=wire[index];payload=entry['payload']
    if entry['direction']!='request' or canonical_hash(payload)!=evidence['payload_sha256']:raise RuntimeError('HELD actual USER payload binding')
    if payload.get('method')=='turn/start':
        if payload['params']['input']!=[{'type':'text','text':evidence['text']}]:raise RuntimeError('HELD actual USER text mismatch')
    elif 'result' in payload and 'id' in payload:
        if not any(e['direction']=='response_or_event' and e['payload'].get('id')==payload['id'] and e['payload'].get('method')=='item/tool/requestUserInput' for e in wire[:index]):raise RuntimeError('HELD unmatched actual USER UI delivery')
    else:raise RuntimeError('HELD unsupported actual USER delivery')
    return evidence


NOTIFICATION_TASK_PATHS = {'app/settings.py':{'T1','T2','T3'},'tests/test_settings.py':{'T1','T2','T3'},
                           'app/notifier.py':{'T4'},'tests/test_notifier.py':{'T4','T5','T6'}}


def notification_business_sample(edit, immutable_paths=()):
    """Full consumer observation, with immutable-role collisions taking precedence."""
    root=Path(edit['data']['root']);state=workflow_inventory(root)
    for name,entry in edit['entries'].items():
        record=state.get(name);path=root/name;canonical=root.resolve()/name
        if path.resolve()!=canonical or (record is not None and (record['kind']!='file' or record['mode']!=entry['mode'])):
            raise RuntimeError('HELD business file topology/mode')
        parent=str(Path(name).parent)
        while parent!='.':
            current=state.get(parent);original=edit['initial'].get(parent)
            if original is not None and current!=original:raise RuntimeError('HELD business parent identity changed')
            if original is None and current is not None and (parent not in edit['directories'] or current['kind']!='directory' or current['mode']!='0o755'):
                raise RuntimeError('HELD undeclared business parent creation')
            parent=str(Path(parent).parent)
        for item in immutable_paths:
            other=Path(item)
            if other.resolve()==canonical or (record is not None and other.exists() and [other.stat().st_dev,other.stat().st_ino]==record['identity']):
                raise RuntimeError('HELD business path also has immutable role')
        if entry.get('progress') and record is not None and not path.read_text().startswith('---\nstatus: approved\n---'):
            raise RuntimeError('HELD progress cannot change approved task status')
    return state


def notification_business_delta(edit, before, after):
    data=edit['data'];changed=[key for key in sorted(set(before)|set(after)) if before.get(key)!=after.get(key)];git=False
    for name in changed:
        if name=='.git' or name.startswith('.git/'):
            if data['phase']!='AC9-handoff' or data.get('git') is not True:raise RuntimeError('HELD Git change outside separately granted AC9 scope')
            git=True;continue
        if name in edit['directories']:
            record=after.get(name)
            if before.get(name) is not None or record is None or record['kind']!='directory' or record['mode']!='0o755':raise RuntimeError('HELD business directory transition')
        elif name in edit['entries']:
            entry=edit['entries'][name]
            if after.get(name) is None and (data['phase']!='AC9-handoff' or entry['action']!='restore'):
                raise RuntimeError('HELD undeclared business deletion')
        else:raise RuntimeError('HELD business scope/cache/immutable consumer drift: '+name)
    off=data.get('off_data')
    if off:
        first=before.get(off['path']);last=after.get(off['path'])
        if (last is not None and last.get('sha256')!=off['sha256']) or ((first is not None or git) and (last is None or last.get('sha256')!=off['sha256'])):
            raise RuntimeError('HELD persistent OFF data changed or absent during AC9')
    elif git:raise RuntimeError('HELD actual AC9 Git requires exact persistent OFF data')
    if not git and any(name in edit['entries'] and after.get(name) is None for name in changed):raise RuntimeError('HELD restore/delete requires an observed granted Git operation')
    return {'schema':'workflow-notification-business-observation-v1','status':'HELD_GIT_SCOPE_REQUIRES_ROOT_REVIEW' if git else 'OBSERVED_BUSINESS_SCOPE_REQUIRES_ROOT_REVIEW',
            'changed':changed,'business_files_equal':before==after,'before':before,'current':after,'git_candidate':git,'business_PASS':False}


BUILD_POSTTIMEOUT_ROW = 'copy-notification-workflow-build-v63-posttimeout-close-flush-verification'
BUILD_POSTTIMEOUT_PINS = {'origin_manifest': '9e7a2d28bb3cb1c8e747d36bd7fdd3a00d97be2a8039a7f0f6ab24ff725af10d', 'origin': '761b78bd5c19bd9b1c0d49d04b6c7c51e63fdbff8017462b7acf8ac6e95eee51', 'audit_report': 'db4a4ed08b7617c2c04d8921071aeac39bcc191bfce491fe69a7b9e50f1a8a37', 'audit_coverage': '80f53bbb21638fa16169df0e3c983512485a0297cfa70e5c9965c4487cb24c14', 'audit_index': '2439fb3d13710000615438e687166cc9a0c22fe92177527d18d3ccd151db7049', 'namespace_fix_review': 'a0a5e3efbd23c7da6c35da63d13338aff596c54bc2d1b6c9ce4ed61978e6455e', 'namespace_fix_adoption': '6c5b191a5641ad26176ba3c274be4c5f1f60791d575fa6c2266f648e6b3887e7', 'owner_decision': '5eae574be91d226922ccfe75902b34f0b628854240e1a6d28f1b232670b5a583', 'input_decision': '09f6a7faeadfc7504b5fc4f83c52db73cb8ed4b9553765915b58dd58ef51bc03', 'progress_record': '40676c0046bc93309419a0ab700e03b8f6651e2245f0a244eaa9786ea2ba9938', 'actual_review': 'b73d2d8b51365bc5c19cd088fa7fe36479938b857527d8f9a5e3a105fb7155ef', 'program': '5b049caeb26c610d6d8ca74bcfb148769ab9a7f52f5e0009c3ed52ab9215701b', 'file_changes': 'fba378917e98166d995a48c94055edfaa35b5cf7847591eb9fec44a28eaf16ed', 'visible_messages': '673d2907785e23f62854ed785e5ab788af3b0868a723b0c7dd7fd69bd973184c', 'accounting': '8ee4169fabed918c1a5c75744d66d4d7b2547b2e9c9840695896b7d62caaaa44', 'history_gap': '8a04d480ac4172a4635f09c97b5d81f6c950292cfccd7f471fa4803bdd5bcb1b'}


def workflow_build_posttimeout(reference, usage, recipe, row, source=None, review=None, release=None):
    """One exact failed origin -> reviewed current state; never retroactive success."""
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise RuntimeError('HELD BUILD handoff duplicate JSON key')
            result[key]=value
        return result
    def blob(ref):
        if (not isinstance(ref,dict) or set(ref)!={'path','sha256'} or not isinstance(ref.get('path'),str) or
            not Path(ref['path']).is_absolute() or str(Path(ref['path']))!=ref['path'] or ref['path'].startswith('//') or '..' in Path(ref['path']).parts or
            not isinstance(ref.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',ref['sha256'])):raise RuntimeError('HELD BUILD handoff exact Ref')
        data=Path(ref['path']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=ref['sha256']:raise RuntimeError('HELD BUILD handoff Ref digest')
        return data
    def read(ref,keys=None):
        value=json.loads(blob(ref),object_pairs_hook=pairs)
        if keys is not None and (not isinstance(value,dict) or set(value)!=set(keys.split())):raise RuntimeError('HELD BUILD handoff closed fields')
        return value
    m=read(reference,'schema root realroot state current_state current_state_sha256 origin_manifest origin wire original_recipe original_release original_contract original_source_review original_root_review original_native_premises audit_report audit_coverage audit_index actual_review program file_changes visible_messages accounting history_gap full_usage namespace_fix_review namespace_fix_adoption current_pair_review owner_decision closure postimages protections plan_progress next_action disposition root_content_review')
    if (m['schema']!='workflow-build-posttimeout-current-state-v1' or m['disposition']!='CURRENT_STATE_ONLY_NOT_V63_PASS' or
        (recipe.get('execution_kind'),recipe.get('purpose'),recipe.get('phase'),recipe.get('unit'))!=('bounded-workflow-v1','workflow-after-setup','build','notification-workflow') or
        recipe.get('rows')!=[row] or row.get('id')!=BUILD_POSTTIMEOUT_ROW or row.get('mode')!='copy' or row.get('transport')!='live' or
        type(row.get('max_user_turns')) is not int or row['max_user_turns']!=1 or type(row.get('terminal_deadline_seconds')) is not int or row['terminal_deadline_seconds']!=180):
        raise RuntimeError('HELD exact BUILD posttimeout subtype/action/row')
    for key in BUILD_POSTTIMEOUT_PINS:
        if key in ('input_decision','progress_record'):continue
        if m[key].get('sha256')!=BUILD_POSTTIMEOUT_PINS[key]:raise RuntimeError('HELD pinned BUILD origin/evidence: '+key)
        blob(m[key])
    origin=read(m['origin']);old=read(m['original_recipe']);oldrelease=read(m['original_release']);oldcontract=read(m['original_contract']);wire=read(m['wire']);state=origin['state']
    if (origin.get('healthy') is not False or origin.get('closed') is not True or type(origin.get('server_returncode')) is not int or origin['server_returncode']!=0 or
        origin.get('failure')!='Absolute terminal deadline exceeded' or origin.get('state_error') or origin.get('close_error') or origin.get('business_facts')!=[] or origin.get('config_facts')!={} or
        (origin.get('purpose'),origin.get('phase'),origin.get('unit'))!=('workflow-after-setup','build','notification-workflow') or
        m['root']!=origin['root'] or m['realroot']!=origin['realroot'] or canonical_hash(m['state'])!=canonical_hash(state) or len(state)!=153 or
        m['wire']!=origin['wire'] or m['original_recipe']!=origin['recipe'] or m['original_release']!=origin['release'] or m['original_contract']!=origin['business_edit_contract'] or
        any(m['original_'+key]!=oldrelease[key] for key in ('source_review','root_review','native_premises'))):raise RuntimeError('HELD truthful failed BUILD origin/source/state')
    sent=[entry for entry in wire if entry.get('direction')=='request' and entry.get('payload',{}).get('method')=='turn/start']
    if (len(sent)!=1 or any(entry['direction']=='response_or_event' and (entry['payload'].get('method')=='turn/completed' or
        (entry['payload'].get('method')=='item/completed' and entry['payload'].get('params',{}).get('item',{}).get('type')=='agentMessage' and entry['payload']['params']['item'].get('phase')=='final_answer')) for entry in wire)):
        raise RuntimeError('HELD original BUILD has no completed terminal/final')
    manifest=read(m['origin_manifest'])
    for path,info in manifest['files'].items():
        if sha(path)!=info['sha256'] or Path(path).stat().st_size!=info['bytes'] or oct(stat.S_IMODE(Path(path).stat().st_mode))!=info['mode']:raise RuntimeError('HELD frozen BUILD artifact drift')
    if manifest['files'].get(m['origin']['path'],{}).get('sha256')!=m['origin']['sha256']:raise RuntimeError('HELD BUILD origin not frozen')
    base=old['usage']+[m['origin']];full=read(m['full_usage'],'contexts postanchor_starts actual held whole build_used build_cap')
    expected={'contexts':base,'postanchor_starts':48,'actual':69,'held':37,'whole':106,'build_used':1,'build_cap':3}
    if canonical_hash(full)!=canonical_hash(expected) or usage[:len(base)]!=base or len(base)!=41:raise RuntimeError('HELD full BUILD chronology/accounting')
    used=workflow_usage(base)
    if sum(used.values())!=48 or used.get('notification-workflow/build')!=1:raise RuntimeError('HELD source-verified BUILD accounting')
    for ref in usage[len(base):]:
        hold=read(ref);events=read(hold['wire']);producer=read(hold['recipe']);checkpoint=read(producer['workflow_checkpoint']);prior_material=read(checkpoint['materialization'])
        if (hold.get('closed') is not True or hold.get('healthy') is not False or hold.get('root')!=m['root'] or hold.get('state')!=state or
            prior_material.get('schema')!=m['schema'] or prior_material.get('origin')!=m['origin'] or producer['rows'][0]['id']!=BUILD_POSTTIMEOUT_ROW or
            any(e.get('direction')=='request' and e.get('payload',{}).get('method')=='turn/start' for e in events)):
            raise RuntimeError('HELD BUILD lifetime already dispatched or zero-hold state changed')
    pair=read(origin['facts']['poststart-baseline-v3.json']);thread=read(origin['facts']['thread-start-v3.json']);native=read(origin['facts']['live-native-selection-receipt.json'])
    if (pair['first']!=pair['second'] or set(pair['snapshot']['snapshot'])!=set(THREAD_FIELDS) or thread['process_id']!=origin['process_id'] or thread['response']['thread']['id']!=origin['thread_id'] or
        any(thread['response'].get(k)!=pair['snapshot']['snapshot'][k] for k in THREAD_FIELDS) or native.get('status')!='BOUND_ACTUAL_RECEIPTS' or
        native['catalog']['enabled_unique_targets']!=16 or native['catalog']['load_errors']!=0):raise RuntimeError('HELD actual BUILD origin 13/B1/native catalog')
    closure=read(m['closure'],'origin wire operator_result closed_receipt process_evidence EOF terminal_count final_count')
    actual=read(m['actual_review']);operator=read(closure['operator_result']);process=read(closure['process_evidence'])
    if (closure['origin']!=m['origin'] or closure['wire']!=m['wire'] or closure['closed_receipt']!=origin['facts']['live-rpc/closed.json'] or closure['process_evidence']!=m['actual_review'] or
        closure['operator_result']!=actual['actual_operator_result'] or closure['EOF'] is not True or type(closure['terminal_count']) is not int or closure['terminal_count']!=0 or
        type(closure['final_count']) is not int or closure['final_count']!=0 or read(closure['closed_receipt']).get('stable') is not True or
        operator.get('stdin_EOF_closed') is not True or type(operator.get('stdin_pending_bytes_not_delivered')) is not int or operator['stdin_pending_bytes_not_delivered']!=0 or
        operator.get('actual_adapter_returncode')!=1 or operator.get('timeout') is not False or set(process.get('owned_PIDs_absent',[]))!={48969,48980,49031}):
        raise RuntimeError('HELD actual BUILD closure/EOF/process evidence')
    P=read(m['current_state'],'origin state postimages protections plan_progress')
    if (m['current_state_sha256']!=canonical_hash(P) or canonical_hash(P)!=canonical_hash({key:m[key] for key in ('origin','state','postimages','protections','plan_progress')})):raise RuntimeError('HELD BUILD acyclic P/current-state binding')
    owner=read(m['owner_decision']);H=m['postimages'];names={'app/settings.py','app/notifier.py','tests/test_settings.py','tests/test_notifier.py','docs/changes/2026-10-25-order-confirmation-email-toggle/tasks.md'}
    if set(H)!=names or H!=owner['postimages']:raise RuntimeError('HELD exact five BUILD postimages')
    for name,ref in H.items():
        blob(ref)
        if state.get(name,{}).get('kind')!='file' or state[name].get('mode')!='0o644' or ref['sha256']!=state[name]['sha256']:raise RuntimeError('HELD BUILD postimage state/mode')
    before=read(origin['scope_facts']['workflow-before-01.json'])
    if len(before)!=152 or {name for name in set(before)|set(state) if before.get(name)!=state.get(name)}!=names:raise RuntimeError('HELD BUILD five-only delta/other148 unchanged')
    if (owner.get('actor')!='Main Root acting only as authorized disposable fixture USER' or owner.get('decision')!='require-targeted-close-flush-verification' or owner.get('reviewed_path')!='app/settings.py' or
        owner.get('T3_limit')!='CONTEXT_MANAGER_CLOSE_FLUSH_NOT_DIRECTLY_INJECTED' or owner.get('implementation_accepted') is not False or
        owner.get('delivered_model_USER') is not False or owner.get('runtime_release') is not False or owner.get('Git_AC9')!='NOT_GRANTED' or
        owner.get('program')!=m['program'] or owner.get('audit')!=m['audit_report']):raise RuntimeError('HELD concrete Root BUILD owner judgment')
    blob(owner['role_authority']);blob(owner['review']);blob(owner['settings_diff']);blob(owner['preimage'])
    progress_ref={'path':str(SOURCE/'.omx/ultragoal/evidence/r7-parent-verification/workflow-build-approved-task-progress-review/tasks_progress-DATA.json'),'sha256':BUILD_POSTTIMEOUT_PINS['progress_record']}
    tp=read(progress_ref,'approved_artifact approved_snapshot context current_artifact wire report');g=read(m['plan_progress'],'before after checkoffs memos body_equal');taskname='docs/changes/2026-10-25-order-confirmation-email-toggle/tasks.md'
    if (g['before']!=tp['approved_snapshot'] or g['after']!=H[taskname] or g['checkoffs']!=['T1','T2','T3','T4','T5','T6'] or g['body_equal'] is not True or
        tp['context']!=m['origin'] or tp['wire']!=m['wire'] or tp['current_artifact']!={'path':str(Path(m['realroot'])/taskname),'sha256':H[taskname]['sha256']} or
        tp['approved_artifact']!=read(oldcontract['tasks_USER'])['approved_artifact']):raise RuntimeError('HELD exact BUILD approved/current task progress')
    approved=blob(g['before']);after=blob(g['after']);memo=g['memos'].encode('utf-8')
    if hashlib.sha256(memo).hexdigest()!='b9c7475c789c28f92042df51b1afe9ec4dbd77f313fe6467527a3546f1059f92' or len(memo)!=3068 or after.count(memo)!=1 or '## メモ\n\n'.encode()+memo+'- 計画作成時：'.encode() not in after:
        raise RuntimeError('HELD BUILD exact added memos/separator')
    restored=after.replace(memo,b'',1)
    for task in g['checkoffs']:
        lines=[line for line in approved.splitlines(keepends=True) if line.startswith(('- [ ] '+task+':').encode())]
        if len(lines)!=1 or restored.count(lines[0].replace(b'[ ]',b'[x]',1))!=1:raise RuntimeError('HELD BUILD six exact checkbox lines')
        restored=restored.replace(lines[0].replace(b'[ ]',b'[x]',1),lines[0],1)
    if restored!=approved or g['before']['sha256']!=tp['approved_artifact']['sha256']:raise RuntimeError('HELD BUILD full approved task bytes/memos retained')
    blob(tp['report'])
    K=read(m['protections'],'historical immutable business_deltas source_pair_review forward');index=read(m['current_pair_review']);source_names=('tests/runtime/codex/native_delta.py','tests/runtime/codex/native_delta_test.py')
    if (K['historical']!=m['original_recipe'] or K['source_pair_review']!=m['current_pair_review'] or index.get('verdict')!='APPROVED_SOURCE_ONLY' or index.get('mandatory_findings')!=[] or
        set(index.get('reviewed_source',{}))!=set(source_names)):raise RuntimeError('HELD exact independently reviewed BUILD source pair')
    pair_report={'path':str(Path(m['current_pair_review']['path']).parent/'REPORT.md'),'sha256':index['files']['REPORT.md']['sha256']};blob(pair_report)
    forward=[dict(item) for item in old['protected_files']];business_paths={str(Path(m['root'])/name):name for name in ('app/settings.py','app/notifier.py','tests/test_settings.py')}
    if len(forward)!=179 or K['immutable']!=[item for item in forward if item['path'] not in business_paths] or len(K['business_deltas'])!=3 or len({item['path'] for item in K['business_deltas']})!=3:
        raise RuntimeError('HELD BUILD original179/176 protection identity/order')
    for item in K['business_deltas']:
        name=business_paths.get(item['path']);oldref=next((x for x in forward if x['path']==item['path']),None)
        if set(item)!={'path','before','after','authorization'} or name is None or item['authorization']!=m['original_contract'] or item['after']!=H[name] or item['before']['sha256']!=oldref['sha256']:
            raise RuntimeError('HELD BUILD three individually authorized pre/post images')
        blob(item['before']);blob(item['after']);oldref['sha256']=H[name]['sha256']
    for name in source_names:
        info=index['reviewed_source'][name];matches=[item for item in forward if item['path']==str(SOURCE/name)]
        if len(matches)!=1 or info.get('mode')!='0o644' or type(info.get('bytes')) is not int or not re.fullmatch('[0-9a-f]{64}',info.get('sha256','')):raise RuntimeError('HELD BUILD exact source epoch metadata')
        matches[0]['sha256']=info['sha256']
    if index['reviewed_source'][source_names[0]]['sha256']!=recipe['adapter_sha256'] or K['forward']!=forward or recipe['protected_files']!=forward:raise RuntimeError('HELD BUILD forward3business+2source-only protections')
    action=m['next_action']
    if set(action)!=set('id purpose phase unit row_id input_decision initial_USER_sha256 contract limits'.split()):raise RuntimeError('HELD BUILD closed next-action fields')
    A=read(action['input_decision'],'actor role_authority owner_decision action row_id initial_user_text')
    if action['input_decision']['sha256']!=BUILD_POSTTIMEOUT_PINS['input_decision'] or A['actor']!=owner['actor'] or A['role_authority']!=owner['role_authority'] or A['owner_decision']!=m['owner_decision'] or A['action']!='verify-close-flush' or A['row_id']!=BUILD_POSTTIMEOUT_ROW or A['initial_user_text']!=row['initial_user_text']:
        raise RuntimeError('HELD actual Root BUILD input choice, not delivered model USER')
    expected_action={'id':'verify-close-flush','purpose':'workflow-after-setup','phase':'build','unit':'notification-workflow','row_id':BUILD_POSTTIMEOUT_ROW,'input_decision':action['input_decision'],
        'initial_USER_sha256':canonical_hash(A['initial_user_text']),'contract':recipe['business_edit_contract'],'limits':{'contexts':1,'model_USER':1,'terminal_seconds':180,'outer_seconds':360}}
    if canonical_hash(action)!=canonical_hash(expected_action):raise RuntimeError('HELD BUILD one initial USER/180/outer360 action')
    C=read(action['contract'],'schema root realroot phase row_id predecessor state_sha256 spec spec_USER tasks tasks_USER grant directories files git implementation_review')
    expected_C={key:oldcontract[key] for key in ('schema','root','realroot','phase','spec','spec_USER','tasks_USER')}
    expected_C.update(row_id=BUILD_POSTTIMEOUT_ROW,predecessor=m['current_state'],state_sha256=canonical_hash(state),tasks=tp['current_artifact'],grant={'initial_USER_sha256':canonical_hash(A['initial_user_text'])},directories=[],git=False,implementation_review=m['current_pair_review'],
        files=[{'path':'tests/test_settings.py','canonical_path':str(Path(m['realroot'])/'tests/test_settings.py'),'action':'edit','preimage':state['tests/test_settings.py'],'mode':'0o644','tasks':['T3'],'parent':state['tests']}])
    if canonical_hash(C)!=canonical_hash(expected_C):raise RuntimeError('HELD BUILD exact tests-only T3/nonempty p predecessor contract')
    Q=read(m['root_content_review'],'payload_sha256 owner_decision input_decision decision report')
    if Q['payload_sha256']!=canonical_hash({key:value for key,value in m.items() if key!='root_content_review'}) or Q['owner_decision']!=m['owner_decision'] or Q['input_decision']!=action['input_decision'] or Q['decision']!='APPROVE_EXACT_CURRENT_STATE_HANDOFF_CONTENT':
        raise RuntimeError('HELD BUILD exact one-field Q self-exclusion/content binding')
    blob(Q['report'])
    if any(doc is not None for doc in (source,review,release)):
        if any(doc is None or doc.get('business_edit_contract')!=action['contract'] for doc in (source,review,release)) or source.get('implementation_review')!=m['current_pair_review'] or source.get('report')!=pair_report:
            raise RuntimeError('HELD BUILD per-recipe source/Root/release contract identity')
        B=review['business']
        if (B.get('tasks_progress')!=tp or B.get('tasks')!=C['tasks'] or B.get('tasks_approval')!=C['tasks_USER'] or B.get('spec')!=C['spec'] or B.get('spec_approval')!=C['spec_USER'] or
            any(ref not in review.get('authority_evidence',[]) for ref in (m['owner_decision'],action['input_decision'],m['plan_progress'],tp['report']))):raise RuntimeError('HELD BUILD genuine tasks progress and distinct owner/input evidence')
    return m


LEGACY_V64_SERIALIZATION_PINS = {
    'context':'a9b07122473f6e2b15f89bd6d4f324641a93f85d85de9d9c54855bbc38e10b30',
    'wire':'736db1723237347fa8c0fe08f2dbf51dca0f0ed44c22d761dda6f8e8e74e33cc',
    'fact':'7bbdf58ab4012fd1cb404fc5fa9a0b9fc89049f5430f1c9a50c90874e048b271',
    'config':'a03258c075b3b2aafd244596b717046c94a31cbd826a4482abcc9194d9ffb487',
    'baseline':'21521f12fc671e9dda8e5799902a26a8bee9d8a3ba44109b6d3ec6626e02408a',
    'manifest':'b50c426c260acd9c6652630720ac39ef4359434433738c17de8c77d79883f0d0',
    'producer':'9665ad265883998052311b04760dd3c4aeacc485c57c09651a4c33f87367f8bf',
    'collector':'5ed7298904262a19ba7ab90988c72e458490acb9dd1f896b8470ed191c006069'}


def legacy_v64_business_serialization(record, fact, events, config=None):
    """Comparison view for ONE immutable old receipt, never a new observation."""
    directory=SOURCE/'.omx/ultragoal/evidence/g004/codex/native-v64/runs-notification-workflow-build-posttimeout-close-flush-source5ed-usage69-RELEASE-REQUIRED'
    def read(path,digest):
        raw=Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('legacy pin mismatch')
        return json.loads(raw)
    def ref(path,key):return {'path':str(path),'sha256':LEGACY_V64_SERIALIZATION_PINS[key]}
    try:
        original=read(directory/'workflow-context.json',LEGACY_V64_SERIALIZATION_PINS['context'])
        if canonical_hash(record)!=canonical_hash(original) or record.get('collector_sha256')!=LEGACY_V64_SERIALIZATION_PINS['collector']:return False
        if (record['wire']!=ref(directory/'live-rpc/rpc.json','wire') or record['business_facts']!=[ref(directory/'business-observation-01.json','fact')] or
            record['config_facts'].get('config-01.json')!=ref(directory/'config-01.json','config') or record['facts'].get('poststart-baseline-v3.json')!=ref(directory/'poststart-baseline-v3.json','baseline') or
            record['recipe']['sha256']!=LEGACY_V64_SERIALIZATION_PINS['producer']):return False
        producer=read(record['recipe']['path'],LEGACY_V64_SERIALIZATION_PINS['producer'])
        hashes=('b4ad4e9dc029d19fe62228f547534f69ade69759a51e64b5341af65fdeaf28dc','1bc197305203015c466ce8f53ad5c6af7dc4aed1bdd963e7a6c2df172c224dfd','291d9efbca6313c93db8bd018d9cc3e1cd1358ae9a7e5437392692acc86a9e67','7556473ee8f6134553292226e30d2ac2ef49968fd873becfdb6629e1ff2b6fea')
        expected=[{'path':'tests/runtime/codex/'+name+'.py','sha256':digest,'OUT_assignment_rebound':name=='runtime','function_bodies_changed':False} for name,digest in zip(HELPERS,hashes)]
        if producer.get('adapter_sha256')!=LEGACY_V64_SERIALIZATION_PINS['collector'] or producer.get('helper_imports')!=expected:return False
        manifest=read(directory/'FROZEN-MANIFEST.json',LEGACY_V64_SERIALIZATION_PINS['manifest'])
        for path,info in manifest['files'].items():
            if sha(path)!=info['sha256'] or Path(path).stat().st_size!=info['bytes'] or oct(stat.S_IMODE(Path(path).stat().st_mode))!=info['mode']:return False
        stored=read(directory/'business-observation-01.json',LEGACY_V64_SERIALIZATION_PINS['fact'])
        stored_config=read(directory/'config-01.json',LEGACY_V64_SERIALIZATION_PINS['config'])
        baseline=read(directory/'poststart-baseline-v3.json',LEGACY_V64_SERIALIZATION_PINS['baseline'])
        wire=read(directory/'live-rpc/rpc.json',LEGACY_V64_SERIALIZATION_PINS['wire'])
        if canonical_hash(fact)!=canonical_hash(stored) or (config is not None and canonical_hash(config)!=canonical_hash(stored_config)):return False
        interval=[entry['payload'] for entry in wire[36:428] if entry['direction']=='response_or_event']
        if fact.get('schema')!='workflow-notification-business-observation-v1' or stored_config.get('schema_version')!='workflow-business-bundle-v1' or fact['wire_start_index']!=36 or fact['wire_end_index']!=428 or len(wire)!=428 or len(events)!=388 or len(fact['events'])!=388 or canonical_hash(events)!=canonical_hash(interval):return False
        for position,ident,method in ((423,18,'config/read'),(425,19,'skills/list'),(427,20,'config/read')):
            if wire[position]['payload'].get('id')!=ident or wire[position-1]['direction']!='request' or wire[position-1]['payload'].get('id')!=ident or wire[position-1]['payload'].get('method')!=method:return False
        # Derive the original HOME privately from paired captured paths, not the current host.
        raw=fact['events'][385]['structural_result']['layers'][1]['source']['file'];display=events[385]['structural_result']['layers'][1]['source']['file']
        if not display.startswith('<HOST_HOME>/'):return False
        suffix=display[len('<HOST_HOME>'):]
        if not raw.endswith(suffix):return False
        home=raw[:-len(suffix)]
        if not home or not Path(home).is_absolute():return False
        launch=read(directory/'live-rpc/launch.json',manifest['files'][str(directory/'live-rpc/launch.json')]['sha256'])
        closed=read(directory/'live-rpc/closed.json',manifest['files'][str(directory/'live-rpc/closed.json')]['sha256'])
        identity=hashlib.sha256(home.encode()).hexdigest()
        if any(env.get('identity_sha256',{}).get('HOME')!=identity or env.get('default_home') is not True or env.get('default_codex_home') is not True for env in (launch['environment'],closed['environment_after'],baseline['first']['environment'],baseline['second']['environment'])):return False
        projected=copy.deepcopy(fact['events'])
        for index in (385,387):
            cfg=projected[index]['structural_result'];source=cfg['layers'][1]['source']
            if not source['file'].startswith(home+'/'):return False
            source['file']=source['file'].replace(home,'<HOST_HOME>')
            for features in (cfg['safe_identity']['schema']['features'],cfg['response_identity']['schema']['config']['features']):
                for key in ('api_key_cyber_access_programs','api_key_model_discovery'):features[key]='<REDACTED>'
        paths=[];icons=[]
        for index,skill in enumerate(projected[386]['result']['data'][0]['skills']):
            if skill['path'].startswith(home+'/'):skill['path']=skill['path'].replace(home,'<HOST_HOME>');paths.append(index)
            for key in ('iconSmall','iconLarge'):
                value=skill.get('interface',{}).get(key)
                if isinstance(value,str) and home in value:skill['interface'][key]=value.replace(home,'<HOST_HOME>');icons.append((index,key))
        if paths!=list(range(16,139))+list(range(140,443)) or set(icons)!={(index,key) for index in (438,439,441,442) for key in ('iconSmall','iconLarge')}:return False
        contract=fact['contract']
        if contract!=producer.get('business_edit_contract') or set(contract)!={'path','sha256'} or not contract['path'].startswith(home+'/'):return False
        display_contract=dict(contract,path=contract['path'].replace(home,'<HOST_HOME>'))
        return canonical_hash(projected)==canonical_hash(events) and display_contract==stored_config['contract']
    except (OSError,KeyError,TypeError,ValueError,IndexError):return False


def notification_business_history(record, prior, wire, release):
    """Retained producer/turn truth only; never rehash historical mutable paths."""
    producer=checked_json(record['recipe']);cp=checked_json(producer['workflow_checkpoint'])
    reference=record.get('business_edit_contract')
    if reference is None:raise RuntimeError('HELD historical business contract missing')
    data=checked_json(reference);source=checked_json(release['source_review']);review=checked_json(release['root_review']);row=producer['rows'][0]
    material=checked_json(cp['materialization']) if cp.get('schema')=='workflow-materialization-v1' else None
    build_material=workflow_build_posttimeout(cp['materialization'],prior,producer,row,source,review,release) if material and material.get('schema')=='workflow-build-posttimeout-current-state-v1' else None
    if build_material and any(entry.get('direction')=='request' and 'result' in entry.get('payload',{}) for entry in wire):raise RuntimeError('HELD BUILD posttimeout no second USER delivery')
    related=[item for item in prior if checked_json(item)['unit']==record['unit']]
    if build_material is None and (not related or related[-1]!=producer['workflow_checkpoint'] or cp.get('schema')!='workflow-context-v1' or cp.get('healthy') is not True or cp.get('closed') is not True or
        cp.get('phase') not in (record['phase'],'tasks' if record['phase']=='build' else 'build') or
        not healthy_terminal([e['payload'] for e in checked_json(cp['wire']) if e['direction']=='response_or_event'],'live')):
        raise RuntimeError('HELD historical latest healthy business predecessor')
    allowed={'schema','root','realroot','phase','row_id','predecessor','state_sha256','spec','spec_USER','tasks','tasks_USER','grant','directories','files','git','off_data','implementation_review'}
    if (set(data)-allowed or not isinstance(data.get('files'),list) or not isinstance(data.get('directories',[]),list) or
        ('git' in data and type(data['git']) is not bool)):raise RuntimeError('HELD historical finite contract fields')
    common={'checkpoint_sha256':producer['workflow_checkpoint']['sha256'],'recipe_sha256':record['recipe']['sha256'],
        'collector_sha256':producer['adapter_sha256'],'helpers':producer['helper_imports'],'manifest_sha256':producer['release_manifest_sha256'],
        'native_premises_sha256':release['native_premises']['sha256'],'purpose':record['purpose'],'phase':record['phase'],'unit':record['unit']}
    checked_json(release['native_premises'])
    for doc,schema in ((source,'WORKFLOW_SOURCE_REVIEW_V1'),(review,'WORKFLOW_ROOT_REVIEW_V1'),(release,'WORKFLOW_RELEASE_V1')):
        if doc.get('schema')!=schema or any(doc.get(k)!=v for k,v in common.items()) or doc.get('business_edit_contract')!=reference:
            raise RuntimeError('HELD historical business producer/source/Root/release binding')
    for doc in (source,review):
        if doc.get('decision')!='APPROVE_EXACT_BOUND_CONTEXT' or sha(doc['report']['path'])!=doc['report']['sha256']:raise RuntimeError('HELD historical concrete business review')
    if (producer.get('execution_kind')!='bounded-workflow-v1' or producer.get('usage')!=prior or producer.get('business_edit_contract')!=reference or
        record.get('collector_sha256')!=producer['adapter_sha256'] or producer.get('rows')!=[row] or
        any(producer.get(k)!=record.get(k) for k in ('purpose','phase','unit')) or
        (record['purpose'],record['unit'])!=('workflow-after-setup','notification-workflow') or record['phase'] not in ('build','AC9-handoff') or
        row.get('mode')!='copy' or row.get('transport')!='live' or type(row.get('terminal_deadline_seconds')) is not int or row['terminal_deadline_seconds']!=180 or
        type(row.get('max_user_turns')) is not int or type(release.get('seconds')) is not int or release['seconds']!=180 or
        type(release.get('max_new_contexts')) is not int or release['max_new_contexts']!=1 or
        release.get('row_id')!=row['id'] or release.get('max_new_model_USER_turns')!=row['max_user_turns'] or
        release.get('initial_USER_sha256')!=canonical_hash(row['initial_user_text']) or release.get('realroot')!=record['realroot'] or
        review.get('source_review')!=release['source_review'] or review.get('state_sha256')!=canonical_hash(cp['state']) or
        review.get('usage_sha256')!=canonical_hash(prior) or not review.get('authority_evidence') or
        cp.get('root')!=record['root'] or cp.get('realroot')!=record['realroot']):raise RuntimeError('HELD historical business chronology/epoch/USER/state')
    for evidence in review['authority_evidence']:
        if sha(evidence['path'])!=evidence['sha256']:raise RuntimeError('HELD historical concrete business authority')
    if (data.get('schema')!='workflow-notification-business-edit-v1' or data.get('root')!=record['root'] or data.get('realroot')!=record['realroot'] or
        data.get('phase')!=record['phase'] or data.get('row_id')!=row['id'] or data.get('predecessor')!=(build_material['current_state'] if build_material else producer['workflow_checkpoint']) or
        data.get('state_sha256')!=canonical_hash(cp['state'])):raise RuntimeError('HELD historical business contract/checkpoint')
    old=checked_json(build_material['original_recipe'] if build_material else cp['recipe']);expected=[dict(item) for item in old['protected_files']]
    previous=checked_json(old['business_edit_contract']) if old.get('business_edit_contract') else None
    for item in expected:
        for entry in previous['files'] if previous else []:
            if item['path'] in (str(Path(record['root'])/entry['path']),str(Path(record['realroot'])/entry['path'])):
                state=cp['state'].get(entry['path'],{})
                if state.get('kind')!='file':raise RuntimeError('HELD historical protected business postimage absent')
                item['sha256']=state['sha256']
    epoch=data.get('implementation_review')
    if epoch:
        index=checked_json(epoch);names=('tests/runtime/codex/native_delta.py','tests/runtime/codex/native_delta_test.py')
        report={'path':str(Path(epoch['path']).parent/'REPORT.md'),'sha256':index['files']['REPORT.md']['sha256']}
        if (index.get('verdict')!='APPROVED_SOURCE_ONLY' or index.get('mandatory_findings')!=[] or set(index.get('reviewed_source',{}))!=set(names) or
            source.get('implementation_review')!=epoch or source.get('report')!=report or sha(report['path'])!=report['sha256']):raise RuntimeError('HELD retained historical source epoch review')
        for name in names:
            matches=[item for item in expected if item['path']==str(SOURCE/name)];info=index['reviewed_source'][name]
            if len(matches)!=1 or info.get('mode')!='0o644' or type(info.get('bytes')) is not int:raise RuntimeError('HELD historical exact reviewed source pair')
            matches[0]['sha256']=info['sha256']
        if index['reviewed_source'][names[0]]['sha256']!=producer['adapter_sha256']:raise RuntimeError('HELD historical producer/index epoch mismatch')
    if expected!=producer['protected_files']:raise RuntimeError('HELD historical ordered immutable/business protections')
    business=review['business']
    for key,target in (('spec','spec'),('spec_USER','spec_approval'),('tasks','tasks'),('tasks_USER','tasks_approval')):
        if data.get(key)!=business.get(target):raise RuntimeError('HELD historical approved business/USER identity')
    grant=data.get('grant',{})
    if set(grant)=={'initial_USER_sha256'}:
        if grant['initial_USER_sha256']!=canonical_hash(row['initial_user_text']):raise RuntimeError('HELD historical business initial grant')
        if any(workflow_user_evidence(business[k],prior,Path(record['root']))['text']==row['initial_user_text'] for k in ('spec_approval','tasks_approval')):
            raise RuntimeError('HELD historical plan approval is not business start')
    elif set(grant)=={'actual_USER'}:
        actual=workflow_user_evidence(grant['actual_USER'],prior,Path(record['root']))
        if any((actual['context'],actual['wire_index'])==(checked_json(business[k])['context'],checked_json(business[k])['wire_index']) for k in ('spec_approval','tasks_approval')):
            raise RuntimeError('HELD historical distinct business grant')
    else:raise RuntimeError('HELD historical business grant missing')
    initial=cp['state'];entries={};directories={item['path'] for item in data.get('directories',[])}
    for item in data.get('directories',[]):
        if (len(directories)!=len(data.get('directories',[])) or set(item)!={'path','preimage','mode'} or Path(item['path']).is_absolute() or '..' in Path(item['path']).parts or str(Path(item['path']))!=item['path'] or
            item['path'] in initial or item['preimage'] is not None or item['mode']!='0o755'):raise RuntimeError('HELD historical new directory preimage')
    # Historical namespace mapping uses only the two bound roots and retained inventory.
    spellings=(record['root'],record['realroot'],business['tasks']['path'])
    roots=tuple(Path(value) for value in spellings[:2]);task_path=Path(spellings[2])
    if any(not Path(value).is_absolute() or str(Path(value))!=value or '..' in Path(value).parts or value.startswith('//') for value in spellings):
        raise RuntimeError('HELD retained tasks absolute normalized namespace')
    suffixes={task_path.relative_to(root).as_posix() for root in roots if task_path.is_relative_to(root)}
    if len(suffixes)!=1 or '.' in suffixes:raise RuntimeError('HELD retained tasks outside/ambiguous root namespace')
    tasks=next(iter(suffixes));canonical=roots[1];task=initial.get(tasks,{})
    if (task.get('kind')!='file' or task.get('mode')!='0o644' or task.get('link_text') is not None or
        task.get('realpath')!=str(canonical/tasks) or task.get('sha256')!=business['tasks']['sha256'] or
        not isinstance(task.get('identity'),list) or len(task['identity'])!=2 or any(type(value) is not int for value in task['identity']) or
        any(name!=tasks and item.get('kind')=='file' and item.get('identity')==task['identity'] for name,item in initial.items())):
        raise RuntimeError('HELD retained tasks file/hash/canonical identity')
    for parent in Path(tasks).parents:
        item=initial.get(parent.as_posix(),{})
        if (item.get('kind')!='directory' or item.get('link_text') is not None or item.get('realpath')!=str(canonical/parent) or
            not isinstance(item.get('identity'),list) or len(item['identity'])!=2 or any(type(value) is not int for value in item['identity'])):
            raise RuntimeError('HELD retained tasks parent/root identity or alias')
    for item in data['files']:
        name=item['path'];ids=set(item.get('tasks',[]));allowed=NOTIFICATION_TASK_PATHS.get(name)
        progress=name==tasks and ids=={'T6'} and item.get('progress') is True
        if (set(item)!={'path','canonical_path','action','preimage','mode','tasks','parent'}|({'progress'} if name==tasks else set()) or
            (not allowed and not progress) or (allowed and (not ids or not ids<=allowed)) or name in entries or
            item.get('canonical_path')!=str(Path(record['realroot'])/name) or item.get('mode')!='0o644' or item.get('preimage')!=initial.get(name) or
            item.get('parent')!=initial.get(str(Path(name).parent)) or (str(Path(name).parent) not in initial and str(Path(name).parent) not in directories) or
            item.get('action') not in ('edit','create','restore') or (item['action']=='edit' and name not in initial) or (item['action']=='create' and name in initial) or
            (item['action']=='restore' and (record['phase']!='AC9-handoff' or name!='tests/test_notifier.py'))):raise RuntimeError('HELD historical finite business scope/preimage')
        entries[name]=item
    if not entries:raise RuntimeError('HELD historical empty business scope')
    off=data.get('off_data')
    if data.get('git') and (record['phase']!='AC9-handoff' or '.git' not in initial or not off):raise RuntimeError('HELD historical granted Git/data relation')
    if off:
        name=off['path']
        if (set(off)!={'path','sha256','preimage','parent'} or record['phase']!='AC9-handoff' or data.get('git') is not True or name in entries or
            Path(name).is_absolute() or '..' in Path(name).parts or str(Path(name))!=name or name.split('/')[0] in ('app','tests','.git','.agents','.claude','.codex','docs') or
            not re.fullmatch('[0-9a-f]{64}',off.get('sha256','')) or off['preimage']!=initial.get(name) or off['parent']!=initial.get(str(Path(name).parent))):raise RuntimeError('HELD historical fixed OFF data')
        entries[name]={'mode':'0o644','action':'create' if name not in initial else 'edit'}
    if not directories<={str(parent) for name in entries for parent in Path(name).parents if str(parent)!='.'}:raise RuntimeError('HELD historical unrelated directory scope')
    edit={'data':data,'entries':entries,'directories':directories}
    for sample_reference in record.get('business_samples',[]):
        sample=checked_json(sample_reference)
        if (sample.get('schema')!='workflow-business-sample-v1' or sample.get('contract')!=reference or
            sample.get('stable') is not (sample.get('before')==sample.get('after')) or
            (record.get('healthy') is True and sample.get('stable') is not True)):raise RuntimeError('HELD historical paired business sample')
    starts=[i for i,e in enumerate(wire) if e.get('direction')=='request' and e.get('payload',{}).get('method')=='turn/start']
    for index,start in enumerate(starts):
        request=wire[start]['payload']['params'];inputs=request.get('input',[])
        if (request.get('threadId')!=record['thread_id'] or len(inputs)!=1 or inputs[0].get('type')!='text' or not isinstance(inputs[0].get('text'),str) or
            (index==0 and inputs[0]['text']!=row['initial_user_text'])):raise RuntimeError('HELD historical dispatched business USER/thread')
    current=initial;history=[];observations=record.get('business_facts',[])
    if len(observations)>len(starts):raise RuntimeError('HELD excess historical business observations')
    for number,observation_reference in enumerate(observations):
        fact=checked_json(observation_reference);start=starts[number];limit=starts[number+1] if number+1<len(starts) else len(wire);end=fact['wire_end_index']
        if (type(fact.get('wire_start_index')) is not int or fact['wire_start_index']!=start or type(end) is not int or not start<end<=limit or
            ((number+1<len(starts) or record.get('healthy') is True) and end!=limit)):
            raise RuntimeError('HELD historical distinct whole business turn interval')
        interval=wire[start:end];events=[e['payload'] for e in interval if e['direction']=='response_or_event']
        request=wire[start]['payload']['params']
        if (request.get('threadId')!=record['thread_id'] or len(request.get('input',[]))!=1 or request['input'][0].get('type')!='text' or
            (number==0 and request['input'][0].get('text')!=row['initial_user_text'])):raise RuntimeError('HELD historical actual business USER/dispatch')
        history.append({'role':'user','text':request['input'][0]['text']});pending=set()
        for event in interval:
            payload=event['payload']
            if event['direction']=='response_or_event' and 'id' in payload and 'method' in payload:pending.add(payload['id'])
            if event['direction']=='request' and 'id' in payload and 'result' in payload:
                if payload['id'] not in pending:raise RuntimeError('HELD historical unmatched business USER response')
                pending.remove(payload['id']);history.append({'role':'user','request_id':payload['id'],'response':{'request_id':payload['id'],'result':payload['result']}})
        version=1 if fact.get('schema')=='workflow-notification-business-observation-v1' else 2 if fact.get('schema')=='workflow-notification-business-observation-v2' else None
        legacy=record['recipe']['sha256']==LEGACY_V64_SERIALIZATION_PINS['producer']
        if legacy and (version!=1 or not legacy_v64_business_serialization(record,fact,events)):raise RuntimeError('HELD exact legacy v64 serialization proof')
        if (pending or any(e['direction']=='transport_error' for e in interval) or not healthy_terminal(events,'live') or
            (build_material and not any(e.get('method')=='item/completed' and e.get('params',{}).get('item',{}).get('type')=='agentMessage' and e['params']['item'].get('phase')=='final_answer' for e in events)) or
            sum(e.get('method')=='turn/completed' for e in events)!=1 or (fact.get('events')!=events and not legacy) or fact.get('user_history')!=history or
            fact.get('contract')!=reference or version is None or fact.get('business_PASS') is not False or
            fact.get('process_id')!=record['process_id'] or fact.get('thread_id')!=record['thread_id'] or fact.get('before')!=current):
            raise RuntimeError('HELD historical complete healthy business turn/provenance')
        after=fact['current']
        for name,entry in entries.items():
            state=after.get(name)
            if state is not None and (state.get('kind')!='file' or state.get('mode')!=entry['mode'] or state.get('realpath')!=str(Path(record['realroot'])/name) or
                any(other!=name and value.get('kind')=='file' and value.get('identity')==state.get('identity') for other,value in after.items())):
                raise RuntimeError('HELD historical business postimage topology')
        computed=notification_business_delta(edit,current,after)
        if version==2:computed['schema']='workflow-notification-business-observation-v2'
        if any(type(fact.get(k)) is not type(v) or fact[k]!=v for k,v in computed.items()):raise RuntimeError('HELD historical recomputed business delta/equality')
        config=checked_json(record['config_facts']['config-%02d.json'%(number+1)]);baseline=checked_json(record['facts']['poststart-baseline-v3.json'])
        if (config.get('schema_version')!='workflow-business-bundle-v'+str(version) or (config.get('contract')!=reference and not legacy) or config.get('business_before')!=current or config.get('business_after')!=after or
            baseline['first']!=baseline['second'] or config.get('immutable_before')!=baseline['first'] or
            config.get('immutable_stable') is not True or config.get('immutable_before')!=config.get('immutable_after') or
            config.get('business_files_equal') is not (current==after) or config.get('full_observed_files_equal') is not (current==after) or config.get('baseline_reset_allowed') is not False):
            raise RuntimeError('HELD historical immutable/business comparison receipt')
        current=after
    if record.get('healthy') is True and (len(observations)!=len(starts) or current!=record.get('state')):
        raise RuntimeError('HELD healthy business context postimage/turn accounting')


def notification_business_transition(recipe, review, cp):
    refs=cp.get('business_facts',[])
    if not refs:return
    relation=review.get('business_transition',{});facts=checked_json(refs[-1]);wire=checked_json(cp['wire'])
    version=1 if facts.get('schema')=='workflow-notification-business-observation-v1' else 2 if facts.get('schema')=='workflow-notification-business-observation-v2' else None
    config=checked_json(cp['config_facts']['config-%02d.json'%len(refs)])
    if version is None or config.get('schema_version')!='workflow-business-bundle-v'+str(version):raise RuntimeError('HELD business transition receipt version pair')
    events=[entry['payload'] for entry in wire[facts['wire_start_index']:facts['wire_end_index']] if entry['direction']=='response_or_event']
    legacy=cp['recipe']['sha256']==LEGACY_V64_SERIALIZATION_PINS['producer']
    if legacy and (version!=1 or not legacy_v64_business_serialization(cp,facts,events,config)):raise RuntimeError('HELD exact legacy v64 transition serialization proof')
    if (relation.get('context')!=recipe['workflow_checkpoint'] or relation.get('facts')!=refs[-1] or
        relation.get('state_sha256')!=canonical_hash(cp['state']) or facts.get('current')!=cp['state'] or
        facts.get('contract')!=checked_json(cp['recipe']).get('business_edit_contract') or
        (facts.get('events')!=events and not legacy) or
        sha(relation['report']['path'])!=relation['report']['sha256']):raise RuntimeError('HELD concrete reviewed business postimage continuity')
    if facts.get('git_candidate'):
        git=checked_json(relation['git_program']);contract=checked_json(facts['contract']);off=contract['off_data']
        if (git.get('context')!=recipe['workflow_checkpoint'] or git.get('wire')!=cp['wire'] or not git.get('completed_items') or
            git.get('off_data')!={'path':off['path'],'sha256':off['sha256']} or
            any(not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}',git.get(key,'')) for key in ('base_oid','commit_oid','revert_oid','restore_oid')) or
            sha(git['report']['path'])!=git['report']['sha256']):raise RuntimeError('HELD actual AC9 OIDs/data/program review')
        for item in git['completed_items']:
            event=wire[item['wire_index']]['payload'];body=event.get('params',{}).get('item',{})
            if (canonical_hash(event)!=item['payload_sha256'] or event.get('method')!='item/completed' or body.get('type')!='commandExecution' or
                body.get('status')!='completed' or type(body.get('exitCode')) is not int or body['exitCode']!=0 or body.get('cwd') not in (cp['root'],cp['realroot'])):
                raise RuntimeError('HELD retained actual Git command/result relation')


def notification_business_contract(recipe, row, source, review, release, cp):
    reference=recipe.get('business_edit_contract')
    if reference is None:return None
    data=checked_json(reference);root=Path(cp['root']);business=review['business']
    material=checked_json(cp['materialization']) if cp.get('schema')=='workflow-materialization-v1' else None
    build_material=workflow_build_posttimeout(cp['materialization'],recipe['usage'],recipe,row,source,review,release) if material and material.get('schema')=='workflow-build-posttimeout-current-state-v1' else None
    allowed={'schema','root','realroot','phase','row_id','predecessor','state_sha256','spec','spec_USER','tasks','tasks_USER','grant','directories','files','git','off_data','implementation_review'}
    if (set(data)-allowed or not isinstance(data.get('files'),list) or not isinstance(data.get('directories',[]),list) or
        ('git' in data and type(data['git']) is not bool)):raise RuntimeError('HELD unknown notification business contract fields')
    if ((recipe.get('execution_kind'),recipe.get('purpose'),recipe.get('unit'))!=('bounded-workflow-v1','workflow-after-setup','notification-workflow') or
        recipe['phase'] not in ('build','AC9-handoff') or row.get('mode')!='copy' or row.get('transport')!='live' or
        data.get('schema')!='workflow-notification-business-edit-v1' or data.get('root')!=str(root) or data.get('realroot')!=str(root.resolve()) or
        data.get('phase')!=recipe['phase'] or data.get('row_id')!=row['id'] or data.get('predecessor')!=(build_material['current_state'] if build_material else recipe['workflow_checkpoint']) or
        data.get('state_sha256')!=canonical_hash(cp['state']) or any(doc.get('business_edit_contract')!=reference for doc in (source,review,release))):
        raise RuntimeError('HELD finite reviewed notification business contract')
    for key,target in (('spec','spec'),('spec_USER','spec_approval'),('tasks','tasks'),('tasks_USER','tasks_approval')):
        if data.get(key)!=business.get(target):raise RuntimeError('HELD exact approved plan/USER business identity')
    grant=data.get('grant',{})
    if set(grant)=={'initial_USER_sha256'}:
        if grant['initial_USER_sha256']!=canonical_hash(row['initial_user_text']):raise RuntimeError('HELD exact future BUILD input grant')
        for key in ('spec_approval','tasks_approval'):
            if workflow_user_evidence(business[key],recipe['usage'],root)['text']==row['initial_user_text']:raise RuntimeError('HELD plan approval is not implementation start')
    elif set(grant)=={'actual_USER'}:
        evidence=workflow_user_evidence(grant['actual_USER'],recipe['usage'],root)
        if any((evidence['context'],evidence['wire_index'])==(checked_json(business[key])['context'],checked_json(business[key])['wire_index']) for key in ('spec_approval','tasks_approval')):
            raise RuntimeError('HELD plan approval cannot supply business start grant')
    else:raise RuntimeError('HELD concrete distinct business grant missing')
    entries={};directories=set();initial=cp['state'];task_path=str(Path(business['tasks']['path']).resolve().relative_to(root.resolve()))
    for directory in data.get('directories',[]):
        name=directory['path']
        if (set(directory)!={'path','preimage','mode'} or Path(name).is_absolute() or '..' in Path(name).parts or str(Path(name))!=name or name in initial or
            directory.get('preimage') is not None or directory.get('mode')!='0o755' or name in directories):raise RuntimeError('HELD exact new business directory absence')
        directories.add(name)
    for item in data.get('files',[]):
        name=item['path'];ids=set(item.get('tasks',[]));allowed=NOTIFICATION_TASK_PATHS.get(name)
        if set(item)!={'path','canonical_path','action','preimage','mode','tasks','parent'}|({'progress'} if name==task_path else set()):raise RuntimeError('HELD exact finite business file fields')
        progress=name==task_path and ids=={'T6'} and item.get('progress') is True
        if (not allowed and not progress) or (allowed and (not ids or not ids<=allowed)):
            raise RuntimeError('HELD task scope does not authorize this business path')
        if name in entries or item.get('canonical_path')!=str(root.resolve()/name) or item.get('mode')!='0o644' or item.get('preimage')!=initial.get(name):raise RuntimeError('HELD exact business path/preimage/mode')
        action=item.get('action')
        if action not in ('edit','create','restore') or (action=='edit' and name not in initial) or (action=='create' and name in initial) or (action=='restore' and (data['phase']!='AC9-handoff' or name!='tests/test_notifier.py')):
            raise RuntimeError('HELD finite business edit/create/restore action')
        parent=str(Path(name).parent)
        if item.get('parent')!=initial.get(parent) or (parent not in initial and parent not in directories):raise RuntimeError('HELD business parent preimage')
        entries[name]=item
    if not entries:raise RuntimeError('HELD no released business task subset')
    if data.get('git') and (data['phase']!='AC9-handoff' or '.git' not in initial):raise RuntimeError('HELD no Git initialization or BUILD Git authority')
    off=data.get('off_data')
    if data.get('git') and off is None:raise RuntimeError('HELD declared AC9 Git needs exact persistent OFF data before dispatch')
    if off:
        name=off['path'];parent=str(Path(name).parent)
        if (set(off)!={'path','sha256','preimage','parent'} or data['phase']!='AC9-handoff' or not data.get('git') or name in entries or Path(name).is_absolute() or '..' in Path(name).parts or str(Path(name))!=name or
            name.split('/')[0] in ('app','tests','.git','.agents','.claude','.codex','docs') or not re.fullmatch('[0-9a-f]{64}',off.get('sha256','')) or
            off.get('preimage')!=initial.get(name) or off.get('parent')!=initial.get(parent) or (parent not in initial and parent not in directories)):
            raise RuntimeError('HELD exact separately granted persistent OFF artifact')
        entries[name]={'path':name,'canonical_path':str(root.resolve()/name),'mode':'0o644','action':'create' if name not in initial else 'edit'}
    if not directories<={str(parent) for name in entries for parent in Path(name).parents if str(parent)!='.'}:raise RuntimeError('HELD directory not required by exact business output')
    # Historical recipe remains immutable; current refs bind only reviewed postimages.
    old=checked_json(build_material['original_recipe'] if build_material else cp['recipe']);expected=[dict(ref) for ref in old['protected_files']]
    previous=checked_json(old['business_edit_contract']) if old.get('business_edit_contract') else None
    previous_names={item['path'] for item in previous['files']} if previous else set()
    for ref in expected:
        for name in previous_names:
            if ref['path'] in (str(root/name),str(root.resolve()/name)):
                if initial.get(name,{}).get('kind')!='file':raise RuntimeError('HELD protected business postimage absent')
                ref['sha256']=initial[name]['sha256']
    epoch=data.get('implementation_review')
    if epoch:
        index=checked_json(epoch);names=('tests/runtime/codex/native_delta.py','tests/runtime/codex/native_delta_test.py');report=Path(epoch['path']).parent/'REPORT.md'
        if (index.get('verdict')!='APPROVED_SOURCE_ONLY' or index.get('mandatory_findings')!=[] or set(index.get('reviewed_source',{}))!=set(names) or
            source.get('implementation_review')!=epoch or source.get('report')!={'path':str(report),'sha256':index['files']['REPORT.md']['sha256']} or sha(report)!=index['files']['REPORT.md']['sha256']):raise RuntimeError('HELD separately reviewed source epoch')
        for name in names:
            path=SOURCE/name;info=index['reviewed_source'][name];matches=[ref for ref in expected if ref['path']==str(path)]
            if len(matches)!=1 or not path.is_file() or path.is_symlink() or path.stat().st_nlink!=1 or info.get('mode')!='0o644' or oct(stat.S_IMODE(path.stat().st_mode))!='0o644' or sha(path)!=info['sha256'] or path.stat().st_size!=info['bytes']:
                raise RuntimeError('HELD immutable current collector/test epoch')
            matches[0]['sha256']=info['sha256']
        if index['reviewed_source'][names[0]]['sha256']!=recipe['adapter_sha256']:raise RuntimeError('HELD source epoch collector mismatch')
    if expected!=recipe['protected_files']:raise RuntimeError('HELD immutable ordered protections or business postimage continuity')
    notification_business_transition(recipe,review,cp)
    edit={'data':data,'reference':reference,'entries':entries,'directories':directories,'initial':initial,
          'paths':{str(base/name) for base in (root,root.resolve()) for name in entries}}
    if notification_business_sample(edit)!=initial:raise RuntimeError('HELD business predispatch state differs from reviewed checkpoint')
    return edit


def workflow_business(recipe, review, root):
    phase=recipe['phase'];business=review.get('business',{})
    if recipe.get('purpose')=='spec-closure-regression':
        cp=checked_json(recipe['workflow_checkpoint']);spec_closure_component(recipe,recipe['rows'][0],checked_json(cp['materialization']),recipe['usage'],review);return
    names=('spec','tasks') if phase in ('build','AC9-handoff','unavailable','reviewer','localship','scope-invalidation') else ('spec',) if phase=='tasks' else ()
    if phase=='reviewer':return  # Exact public packet/approval relation checked below.
    for name in names:
        ref=business[name];path=Path(ref['path'])
        if not path.resolve().is_relative_to(root.resolve()) or sha(path)!=ref['sha256'] or not path.read_text().startswith('---\nstatus: approved\n---'):raise RuntimeError('HELD current approved business artifact')
        approval=workflow_user_evidence(business[name+'_approval'],recipe['usage'],root)
        progress=business.get('tasks_progress') if name=='tasks' else None
        approved=progress['approved_artifact'] if progress else ref
        if progress:
            snapshot=progress['approved_snapshot'];context=progress['context'];record=checked_json(context)
            if (context not in recipe['usage'] or record['root']!=str(root) or progress.get('current_artifact')!=ref or
                snapshot.get('sha256')!=approved['sha256'] or sha(snapshot['path'])!=snapshot['sha256'] or
                not Path(snapshot['path']).read_text().startswith('---\nstatus: approved\n---') or
                record['state'].get(str(path.resolve().relative_to(root.resolve())),{}).get('sha256')!=ref['sha256'] or
                progress.get('wire')!=record['wire'] or sha(progress['report']['path'])!=progress['report']['sha256']):
                raise RuntimeError('HELD concrete progress-only approved-plan continuity')
        if approval.get('approved_artifact')!=approved or not approval.get('draft_artifact'):raise RuntimeError('HELD exact draft/approved-artifact USER relation')
        draft=approval['draft_artifact']
        if sha(draft['path'])!=draft['sha256'] or not Path(draft['path']).read_text().startswith('---\nstatus: draft\n---'):raise RuntimeError('HELD concrete unapproved draft preimage')
    if phase=='AC9-handoff':
        if 'Git_grant' in business:workflow_user_evidence(business['Git_grant'],recipe['usage'],root)
        else:
            grant=business['initial_USER_Git_grant'];context=grant['question_context']
            if context not in recipe['usage'] or checked_json(context)['root']!=str(root) or grant.get('text_sha256')!=canonical_hash(recipe['rows'][0]['initial_user_text']):raise RuntimeError('HELD exact future first USER grant/question relation')
            wire=checked_json(checked_json(context)['wire']);event=wire[grant['question_wire_index']]['payload']
            if canonical_hash(event)!=grant['question_payload_sha256']:raise RuntimeError('HELD actual preceding operation question')
            # This is only a proposed first USER until run_row receives the
            # separately delivered exact text; metadata grants no operation.
    if phase=='scope-invalidation':
        ship=checked_json(business['local_ship']);context=ship['context']
        if context not in recipe['usage'] or checked_json(context)['phase']!='localship' or checked_json(context)['root']!=str(root):raise RuntimeError('HELD actual local ship predecessor')
        wire=checked_json(checked_json(context)['wire']);event=wire[ship['route_wire_index']]['payload'];item=event.get('params',{}).get('item',{})
        if (canonical_hash(event)!=ship['route_payload_sha256'] or event.get('method')!='item/completed' or item.get('type')!='commandExecution' or
            item.get('status')!='completed' or type(item.get('exitCode')) is not int or item['exitCode']!=10 or
            not isinstance(item.get('aggregatedOutput'),str) or 'HUMAN_REQUIRED' not in item['aggregatedOutput']):raise RuntimeError('HELD observed installed route HUMAN_REQUIRED10 required')
        if (sha(root/'.agents/skills/ains-review-gate/scripts/route-review.sh')!=ship['installed_helper_sha256'] or
            not Path(ship['localpr']['path']).resolve().is_relative_to(root.resolve()) or Path(ship['localpr']['path']).name not in ('localpr.md','pr.md') or sha(ship['localpr']['path'])!=ship['localpr']['sha256'] or
            sha(ship['program_review']['path'])!=ship['program_review']['sha256']):raise RuntimeError('HELD concrete localpr/installed-route/program evidence')
        program=checked_json(ship['program_review']);rule=program['rules']
        if (program.get('route_event_sha256')!=ship['route_payload_sha256'] or program.get('context')!=context or
            program.get('decision')!='ACCEPT_ACTUAL_INSTALLED_ROUTE_BASE_WORK_RULE_RELATION' or
            Path(rule['path']).resolve()!=root.resolve()/'docs/ains/human-review-rules' or sha(rule['path'])!=rule['sha256'] or
            any(not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',program.get(k,'')) for k in ('base_oid','head_oid')) or
            program.get('resolved_argv')!=[str(root/'.agents/skills/ains-review-gate/scripts/route-review.sh'),rule['path'],program['base_oid'],program['head_oid']] or
            sha(program['report']['path'])!=program['report']['sha256']):raise RuntimeError('HELD actual installed route base/work/correct-rule relation')
    if phase=='original-draft':
        ref=business['draft'];path=Path(ref['path'])
        if (not path.resolve().is_relative_to(root.resolve()) or sha(path)!=ref['sha256'] or
            not path.read_text().startswith('---\nstatus: draft\n---')):raise RuntimeError('HELD faithful original unapproved draft')
        original=business.get('original_draft',ref)
        if original['sha256']!='a017831f061fea8da5923558e2a5aa58ffb3b1fadfe8fdc3140e02d026bba92b' or sha(original['path'])!=original['sha256']:raise RuntimeError('HELD original actual draft provenance')
        first=not any(checked_json(x)['unit']=='original-notification' for x in recipe['usage'])
        if first and (ref['sha256']!=original['sha256'] or path.read_bytes()!=Path(original['path']).read_bytes()):raise RuntimeError('HELD original first context must start from actual draft bytes')
        old=business['defaultON_only']
        if old['sha256']!='be1bb5cca54da515f3e25e6cd6eada77563883b8c2fd7a20191c2144b5b8f86c' or sha(old['path'])!=old['sha256']:raise RuntimeError('HELD original single settled choice provenance')
        for name in ('app/settings.py','app/notifier.py','app/__init__.py','tests/test_settings.py','tests/__init__.py','AGENTS.md'):
            original=SOURCE/'tests/evals/ains-spec/new-feature-stops-at-spec-gate/files'/name
            if sha(root/name)!=sha(original):raise RuntimeError('HELD original business/context source mismatch')


def workflow_setup_observation(baseline, terminal, initial, final, events, history, contract):
    if not healthy_terminal(events,'live'):raise RuntimeError('HELD unhealthy prospective setup terminal')
    if not any(x.get('role')=='user' and x.get('text')==contract['setup_user_text'] for x in history):
        if not contract.get('setup_USER_provenance'):raise RuntimeError('HELD actual prospective setup USER provenance missing')
        original=workflow_user_evidence(contract['setup_USER_provenance'],contract['prior_usage'],Path(contract['root']))
        if original.get('text')!=contract['setup_user_text'] or not original['text'].startswith('$ains-setup '):raise RuntimeError('HELD exact prior actual setup USER missing')
    left=copy.deepcopy(baseline);right=copy.deepcopy(terminal)
    for value in (left,right):
        value.pop('setup_slots',None);value.pop('setup_scope',None)
        for name in SETUP_SLOTS:value['files'].pop(str(Path(contract['root'])/name),None)
    if json.dumps(left,sort_keys=True)!=json.dumps(right,sort_keys=True):raise RuntimeError('HELD protected prospective setup bundle drift')
    for name in SETUP_SLOTS:
        a=baseline['setup_slots'][name];b=terminal['setup_slots'][name]
        old=bytes.fromhex(a['bytes_hex'] or '');new=bytes.fromhex(b['bytes_hex'] or '')
        if any(old.count(span.encode())!=new.count(span.encode()) for span in contract['preserve'][name]):raise RuntimeError('HELD existing setup values/grants changed')
        if a['kind']=='symlink' and any(a[k]!=b[k] for k in ('kind','link_text','lstat_identity','target_identity')):raise RuntimeError('HELD setup symlink retarget')
    old=baseline['setup_slots']
    if old['AGENTS.md']['target_identity'] and old['AGENTS.md']['target_identity']==old['CLAUDE.md']['target_identity']:
        if any(terminal['setup_slots'][n]['target_identity']!=old[n]['target_identity'] for n in SETUP_SLOTS):raise RuntimeError('HELD setup samefile split')
    changed=sorted(k for k in set(initial)|set(final) if initial.get(k)!=final.get(k))
    images={k:(Path(contract['root'])/k).read_bytes().hex() for k in changed if k in final and final[k]['kind']=='file'}
    return copy.deepcopy({'schema':'prospective-setup-observation-v1','status':'HELD_PROSPECTIVE_SETUP_REQUIRES_ROOT_REVIEW','authorizes_dispatch':False,
        'baseline':baseline,'terminal':terminal,'initial_state':initial,'state':final,'changed':changed,'postimages':images,
        'events':events,'user_history':history,'contract':contract,'execution_scope_parser_claim':False})


def validate_workflow_checkpoint(args, recipe, row, binding):
    """Finite external semantic review, not inferred business permission."""
    if (not getattr(args,'current_author_checkpoint',None) or not getattr(args,'current_author_release',None) or
        any(getattr(args,k,None) for k in ('setup_checkpoint','setup_checkpoint_review','derivative_release','packet')) or
        binding.get('setup_artifact_contract') or recipe.get('rows')!=[row]):raise RuntimeError('HELD separate bounded workflow entry required')
    cp=checked_json(recipe['workflow_checkpoint'])
    if Path(recipe['workflow_checkpoint']['path']).resolve()!=Path(args.current_author_checkpoint).resolve():raise RuntimeError('HELD wrong workflow checkpoint')
    release=json.loads(Path(args.current_author_release).read_text());root=Path(cp['root'])
    if root.resolve()==SOURCE or root.resolve() in SOURCE.parents or SOURCE in root.resolve().parents:raise RuntimeError('HELD workflow consumer overlaps source')
    if cp.get('schema') not in ('workflow-materialization-v1','workflow-context-v1'):raise RuntimeError('HELD unsupported workflow checkpoint')
    if cp.get('realroot')!=str(root.resolve()) or not root.is_absolute():raise RuntimeError('HELD workflow canonical root')
    used=workflow_usage(recipe['usage']);limit=workflow_limits(recipe,row,used);handoff=None;build_handoff=None;closure=None
    related=[checked_json(ref) for ref in recipe['usage'] if checked_json(ref)['unit']==recipe['unit']]
    previous=related[-1] if related else None
    predecessors={'spec':'setup-ack-repeat','tasks':'spec','build':'tasks','AC9-handoff':'build','unavailable':'AC9-handoff',
                  'reviewer':'unavailable','localship':'reviewer','scope-invalidation':'localship','setup-ack-repeat':'setup-observe'}
    phase=recipe['phase']
    if phase in predecessors and (not previous or previous['phase'] not in (phase,predecessors[phase])):raise RuntimeError('HELD actual workflow phase predecessor missing')
    if phase=='spec' and previous and previous['phase']=='setup-ack-repeat' and used.get(recipe['unit']+'/setup-ack-repeat')!=2:raise RuntimeError('HELD actual content ack plus identical repeat not complete')
    if previous and previous.get('setup_observation') and recipe['purpose'] not in ('setup-observe','setup-ack-repeat'):raise RuntimeError('HELD setup output requires concrete content acknowledgement/repeat')
    allocation=checked_json(release['allocation'])
    if (allocation.get('actual_anchor')!=21 or allocation.get('held_anchor')!=85 or allocation.get('whole')!=106 or
        allocation.get('required')!=84 or allocation.get('reserve')!=1):raise RuntimeError('HELD exact remaining allocation anchor required')
    if sha(allocation['evidence']['path'])!=allocation['evidence']['sha256']:raise RuntimeError('HELD allocation evidence')
    if cp['schema']=='workflow-context-v1':
        if previous!=cp or cp.get('healthy') is not True:raise RuntimeError('HELD latest healthy closed workflow context required')
        wire=checked_json(cp['wire']);events=[x['payload'] for x in wire if x['direction']=='response_or_event']
        if not healthy_terminal(events,'live'):raise RuntimeError('HELD predecessor full wire unhealthy')
        pair=checked_json(cp['facts']['poststart-baseline-v3.json']);thread=checked_json(cp['facts']['thread-start-v3.json']);native=checked_json(cp['facts']['live-native-selection-receipt.json'])
        if (pair['first']!=pair['second'] or set(pair['snapshot']['snapshot'])!=set(THREAD_FIELDS) or
            any(thread['response'].get(k)!=pair['snapshot']['snapshot'][k] for k in THREAD_FIELDS) or
            native.get('status')!='BOUND_ACTUAL_RECEIPTS' or native['catalog']['enabled_unique_targets']!=16 or native['catalog']['load_errors']!=0):raise RuntimeError('HELD predecessor actual13/B1/native catalog evidence')
    else:
        material=checked_json(cp['materialization'])
        if material.get('root')!=str(root) or material.get('state')!=cp['state']:raise RuntimeError('HELD exact materialization relation required')
        if material.get('schema')=='spec-closure-materialization-v1':
            closure=spec_closure_component(recipe,row,material,recipe['usage'])
        elif material.get('schema')=='workflow-tasks-closed-timeout-state-v1':
            origin=workflow_tasks_handoff(material,recipe['usage'],recipe,row)
            handoff={'origin':origin,'materialization':cp['materialization'],'row_id':TASKS_TIMEOUT_ROW}
        elif material.get('schema')=='workflow-build-posttimeout-current-state-v1':
            build_handoff=workflow_build_posttimeout(cp['materialization'],recipe['usage'],recipe,row)
        elif material.get('schema')=='notification-review-handoff-v1':
            parent=checked_json(material['author']);reviewer=checked_json(material['reviewer'])
            if (not recipe['usage'] or not workflow_ref_equal(material['reviewer'],recipe['usage'][-1]) or parent['state']!=material['before'] or parent['root']!=str(root) or
                parent.get('purpose')!='workflow-review-unavailable' or reviewer.get('purpose')!='workflow-independent-review' or
                recipe['purpose']!='workflow-after-review'):raise RuntimeError('HELD latest fallback/reviewer materialization lineage')
            destination='docs/ains/reviews/notification-review.md'
            if material['destination']!=destination or destination in material['before']:raise RuntimeError('HELD report materialization overwrite/target')
            for k in set(material['before'])|set(cp['state']):
                if material['before'].get(k)==cp['state'].get(k) or k==destination:continue
                if k not in material['before'] and cp['state'].get(k,{}).get('kind')=='directory' and Path(k) in Path(destination).parents:continue
                raise RuntimeError('HELD unexplained postreview materialization delta')
            if cp['state'].get(material['destination'],{}).get('sha256')!=material['report_sha256']:raise RuntimeError('HELD actual review report postimage')
        elif material.get('schema')=='workflow-baseline-materialization-v1':
            if (phase!='spec' or not previous or previous['phase']!='setup-ack-repeat' or
                material.get('parent')!=recipe['usage'][-1] or material.get('before')!=previous['state']):raise RuntimeError('HELD baseline after actual setup/ack/repeat only')
            for name in set(material['before'])|set(cp['state']):
                if name.split('/')[0]!='.git' and material['before'].get(name)!=cp['state'].get(name):raise RuntimeError('HELD non-Git baseline materialization drift')
            facts=checked_json(material['object_evidence'])
            if (facts.get('root')!=str(root) or facts.get('main_oid')!=material.get('base_oid') or
                not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',facts.get('main_oid','')) or not facts.get('work_branch') or
                not facts.get('tree_files') or sha(facts['report']['path'])!=facts['report']['sha256']):raise RuntimeError('HELD actual baseline objects/content facts')
            for name,digest in facts['tree_files'].items():
                if cp['state'].get(name,{}).get('sha256')!=digest:raise RuntimeError('HELD actual baseline object content')
            rule='docs/ains/human-review-rules'
            if rule not in facts['tree_files'] or facts.get('mandatory_review_path')!='app/settings.py':raise RuntimeError('HELD genuine mandatory rule in true baseline')
            workflow_user_evidence(facts['human_rule_USER'],recipe['usage'],root)
            workflow_user_evidence(facts['contact_USER'],recipe['usage'],root)
        elif material.get('schema')=='notification-reviewer-materialization-v1':
            if recipe['purpose']!='workflow-independent-review' or (root/'.git').exists():raise RuntimeError('HELD reviewer materialization is not author Git baseline')
            packet=Path(material['packet']['path']).parent;public=notification_packet_manifest(packet)
            if sha(material['packet']['path'])!=material['packet']['sha256'] or recipe.get('review_packet')!=material['packet']:raise RuntimeError('HELD current reviewer packet')
            for name,digest in public['files'].items():
                if cp['state'].get(name,{}).get('sha256')!=digest:raise RuntimeError('HELD reviewer packet materialization bytes')
        else:
            if material.get('schema')!='workflow-file-materialization-v1' or not material.get('sources'):raise RuntimeError('HELD finite file materialization required')
            if previous:raise RuntimeError('HELD initial file materialization cannot reset an existing workflow')
            for ref in material['sources']:
                if sha(ref['path'])!=ref['sha256'] or cp['state'].get(ref['destination'],{}).get('sha256')!=ref['sha256']:raise RuntimeError('HELD exact materialized source/postimage drift')
    if recipe['purpose']=='spec-closure-regression' and closure is None:raise RuntimeError('HELD closure reserved rows require materialization')
    if row.get('id')==BUILD_POSTTIMEOUT_ROW and build_handoff is None:raise RuntimeError('HELD reserved BUILD posttimeout row requires exact subtype')
    if row.get('id')==TASKS_TIMEOUT_ROW and handoff is None:raise RuntimeError('HELD reserved TASKS handoff row requires exact subtype')
    setup=recipe['purpose'] in ('setup-observe','setup-ack-repeat')
    protected=[x['path'] for x in recipe['protected_files']]
    if workflow_inventory(root,protected,setup)!=cp['state']:raise RuntimeError('HELD workflow boundary state/cache/topology drift')
    if recipe['purpose']=='workflow-router':
        if any((root/name).exists() or (root/name).is_symlink() for name in (*SETUP_SLOTS,'docs/ains/human-review-rules')) or any((root/'docs/changes').rglob('spec.md')) or any((root/'docs/changes').rglob('tasks.md')):raise RuntimeError('HELD workflow router requires actual absent setup/drafts')
        original=SOURCE/'tests/evals/ains-spec/new-feature-stops-at-spec-gate/files'
        if any(sha(root/name)!=sha(original/name) for name in ('app/settings.py','app/notifier.py','app/__init__.py','tests/test_settings.py','tests/__init__.py')):raise RuntimeError('HELD original notification workflow seed')
    if recipe['purpose']=='setup-observe' and not related and recipe['unit'] in WORKFLOW_SETUP_UNITS:
        slots=setup_slots(root,protected);shape=recipe['unit'].removeprefix('setup-')
        expected=('absent','regular') if shape=='claude-only' else ('regular','symlink') if shape=='symlink' else ('regular','regular')
        if tuple(slots[k]['kind'] for k in SETUP_SLOTS)!=expected:raise RuntimeError('HELD exact standalone setup topology')
        shared=slots['AGENTS.md']['target_identity'] is not None and slots['AGENTS.md']['target_identity']==slots['CLAUDE.md']['target_identity']
        if shape=='samefile' and not shared or shape in ('duplicate','conflict','existing-import') and shared:raise RuntimeError('HELD exact standalone inode relation')
    for ref in recipe['protected_files']:
        if sha(ref['path'])!=ref['sha256']:raise RuntimeError('HELD protected workflow source/instruction collision')
    if Path(args.out).resolve().is_relative_to(root.resolve()):raise RuntimeError('HELD workflow output inside consumer')
    common={'checkpoint_sha256':recipe['workflow_checkpoint']['sha256'],'recipe_sha256':sha(Path(args.prepared)/'recipe.json'),
        'collector_sha256':sha(__file__),'helpers':recipe['helper_imports'],'manifest_sha256':recipe['release_manifest_sha256'],
        'native_premises_sha256':binding['workflow_native_premises_sha256'],'purpose':recipe['purpose'],'phase':recipe['phase'],'unit':recipe['unit']}
    native=checked_json(release['native_premises']);source=checked_json(release['source_review']);review=checked_json(release['root_review'])
    if (release['native_premises']['sha256']!=binding['workflow_native_premises_sha256'] or
        native!={k:v for k,v in binding.items() if k not in ('workflow_native_premises_sha256','workflow_release_sha256')} or
        binding.get('workflow_release_sha256')!=sha(args.current_author_release)):raise RuntimeError('HELD exact workflow native/release binding')
    for doc,schema in ((source,'WORKFLOW_SOURCE_REVIEW_V1'),(review,'WORKFLOW_ROOT_REVIEW_V1'),(release,'WORKFLOW_RELEASE_V1')):
        if doc.get('schema')!=schema or any(doc.get(k)!=v for k,v in common.items()):raise RuntimeError('HELD workflow source/Root/release common bindings')
    for doc in (source,review):
        if doc.get('decision')!='APPROVE_EXACT_BOUND_CONTEXT' or sha(doc['report']['path'])!=doc['report']['sha256']:raise RuntimeError('HELD concrete workflow review report')
    if (review.get('source_review')!=release['source_review'] or review.get('state_sha256')!=canonical_hash(cp['state']) or
        review.get('usage_sha256')!=canonical_hash(recipe['usage']) or not review.get('authority_evidence')):raise RuntimeError('HELD concrete state/phase/authority review missing')
    for ref in review['authority_evidence']:
        if sha(ref['path'])!=ref['sha256']:raise RuntimeError('HELD actual business/approval/grant evidence reference')
    if handoff is not None:
        workflow_live_source_protection(material,checked_json(checked_json(handoff['origin'])['recipe']),recipe,source,review,current=True)
        if (review.get('tasks_timeout_handoff')!=handoff or release.get('tasks_timeout_handoff')!=handoff or
            review.get('business')!=checked_json(checked_json(checked_json(handoff['origin'])['release'])['root_review'])['business'] or
            any(ref not in review['authority_evidence'] for ref in (material['content_review'],material['approval_DATA']))):
            raise RuntimeError('HELD source-bound TASKS Root/release/data certification')
    workflow_business(recipe,review,root)
    business_edit=notification_business_contract(recipe,row,source,review,release,cp)
    if cp.get('business_facts') and business_edit is None:notification_business_transition(recipe,review,cp)
    exact={'release_id':args.release_id,'root':str(root),'realroot':str(root.resolve()),'row_id':row['id'],'out':str(Path(args.out).resolve()),
        'max_new_contexts':1,'max_new_model_USER_turns':limit,'seconds':180,'actual_before':21+sum(used.values()),
        'held_before':85-sum(used.values()),'whole':106,'initial_USER_sha256':canonical_hash(row['initial_user_text'])}
    if any(type(release.get(k)) is not type(v) or release[k]!=v for k,v in exact.items()):raise RuntimeError('HELD exact workflow USER/limit/quota/output release')
    if any(checked_json(ref)['release_id']==args.release_id for ref in recipe['usage']):raise RuntimeError('HELD workflow release already used')
    if cp.get('setup_observation') or recipe['purpose']=='setup-ack-repeat':
        candidate=cp.get('setup_observation');checks=review.get('setup',{})
        if not candidate or candidate.get('status')!='HELD_PROSPECTIVE_SETUP_REQUIRES_ROOT_REVIEW':raise RuntimeError('HELD missing actual prospective setup output')
        expected={'candidate_sha256':canonical_hash(candidate),'program_sha256':canonical_hash(candidate['events']),
                  'postimages_sha256':canonical_hash(candidate['postimages']),'delta_sha256':canonical_hash([candidate['initial_state'],candidate['state']])}
        if any(checks.get(k)!=v for k,v in expected.items()) or sha(checks['report']['path'])!=checks['report']['sha256']:raise RuntimeError('HELD concrete setup program/content/grants review')
        generated=checks.get('generated',[]);allowed=set(SETUP_SLOTS)
        rule='docs/ains/human-review-rules'
        if rule not in candidate['initial_state']:allowed.add(rule)
        for artifact in generated:
            name=artifact['path'];rec=candidate['state'].get(name)
            if (name in candidate['initial_state'] or not rec or rec['kind']!='file' or not name.endswith('.pyc') or
                artifact.get('sha256')!=rec['sha256'] or not artifact.get('sources') or not artifact.get('command_events')):raise RuntimeError('HELD exact new generated cache provenance')
            for ref in artifact['sources']:
                if (not ref['path'].endswith('.py') or candidate['state'].get(ref['path'],{}).get('sha256')!=ref['sha256'] or
                    candidate['initial_state'].get(ref['path'],{}).get('sha256')!=ref['sha256']):raise RuntimeError('HELD generated pinned source identity')
            for index in artifact['command_events']:
                if type(index) is not int or not 0<=index<len(candidate['events']):raise RuntimeError('HELD generating command index')
                item=candidate['events'][index].get('params',{}).get('item',{})
                if (item.get('type')!='commandExecution' or item.get('status')!='completed' or type(item.get('exitCode')) is not int or
                    not isinstance(item.get('command'),str) or not item['command'] or item.get('cwd')!=str(root) or
                    not isinstance(item.get('aggregatedOutput'),str)):raise RuntimeError('HELD completed generating program evidence')
            allowed.add(name)
        for name in candidate['changed']:
            if name in allowed:continue
            if name not in candidate['initial_state'] and candidate['state'].get(name,{}).get('kind')=='directory' and any(Path(name) in Path(p).parents for p in allowed):continue
            raise RuntimeError('HELD unexplained prospective setup scope')
        if recipe['purpose']=='setup-ack-repeat':
            repeat_text=candidate['contract']['setup_user_text']
            if recipe.get('setup_repeat_text')!=repeat_text:
                reference=recipe.get('original_setup_USER_provenance')
                if not reference:raise RuntimeError('HELD actual original setup USER provenance required')
                original=workflow_user_evidence(reference,recipe['usage'],root)
                first=next((ref for ref in recipe['usage'] if checked_json(ref)['unit']==recipe['unit'] and
                    checked_json(ref)['purpose']=='setup-observe' and checked_json(ref)['phase']=='setup-observe'),None)
                if first is None or not workflow_ref_equal(original['context'],first):raise RuntimeError('HELD first same-unit setup context required')
                context=checked_json(first);wire=checked_json(context['wire']);named=[]
                for index,entry in enumerate(wire):
                    payload=entry.get('payload',{});inputs=payload.get('params',{}).get('input')
                    if (entry.get('direction')=='request' and payload.get('method')=='turn/start' and
                        isinstance(inputs,list) and len(inputs)==1 and isinstance(inputs[0],dict) and
                        inputs[0].get('type')=='text' and isinstance(inputs[0].get('text'),str) and inputs[0]['text'].startswith('$ains-setup ')):
                        named.append(index)
                if (not named or original['wire_index']!=named[0] or
                    wire[named[0]]['payload']['params'].get('threadId')!=context['thread_id'] or
                    recipe.get('setup_repeat_text')!=original['text']):raise RuntimeError('HELD exact first named setup USER repeat required')
                repeat_text=original['text']
            if limit!=2 or recipe.get('setup_repeat_text')!=repeat_text or row['initial_user_text']!=recipe.get('setup_content_ack_text'):raise RuntimeError('HELD exact new setup acknowledgement/repeat pair')
    return {'checkpoint':cp,'release':release,'review':review,'root':str(root),'used':used,'protected':protected,'setup':setup,**({'tasks_timeout_handoff':handoff} if handoff is not None else {}),**({'business_edit':business_edit} if business_edit else {}),**({'build_posttimeout_handoff':True} if build_handoff else {}),**({'spec_closure':closure} if closure else {})}


def close_workflow_context(rpc, out, recipe, args, flow, observation, healthy):
    """Close first; retain failed dispatches as charged facts, never eligibility."""
    failure=redacted_config(str(sys.exc_info()[1])) if sys.exc_info()[1] is not None else None
    state=None;error=None;close_error=None
    try:rpc.close()
    except (OSError,RuntimeError) as caught:close_error=redacted_config(str(caught))
    try:state=workflow_inventory(Path(flow['root']),flow['protected'],flow['setup'])
    except (OSError,RuntimeError) as caught:error=str(caught)
    wire=out/'live-rpc/rpc.json';closed=out/'live-rpc/closed.json'
    receipt={'schema':'workflow-context-v1','purpose':recipe['purpose'],'phase':recipe['phase'],'unit':recipe['unit'],
        'status':'HELD_WORKFLOW_CONTEXT_REQUIRES_ROOT_REVIEW','business_PASS':False,
        'root':flow['root'],'realroot':str(Path(flow['root']).resolve()),'state':state,'state_error':error,
        'closed':rpc.p.poll() is not None and closed.is_file(),'server_returncode':rpc.p.poll(),
        'healthy':bool(healthy and not error and not close_error),'failure':failure,'close_error':close_error,'process_id':rpc.p.pid,'thread_id':getattr(rpc,'bound_thread',None),
        'release_id':args.release_id,'release':{'path':str(Path(args.current_author_release).resolve()),'sha256':sha(args.current_author_release)},
        'prior_usage_sha256':canonical_hash(recipe['usage']),'collector_sha256':sha(__file__),
        'wire':{'path':str(wire),'sha256':sha(wire) if wire.is_file() else None},'setup_observation':observation,
        'recipe':{'path':str(Path(args.prepared)/'recipe.json'),'sha256':sha(Path(args.prepared)/'recipe.json')},
        'scope_facts':{p.name:{'path':str(p),'sha256':sha(p)} for pattern in ('workflow-state-*.json','workflow-before-*.json') for p in sorted(out.glob(pattern))},
        'facts':{name:{'path':str(out/name),'sha256':sha(out/name)} for name in
                 ('thread-start-v3.json','poststart-baseline-v3.json','live-native-selection-receipt.json','live-rpc/closed.json') if (out/name).is_file()},
        'config_facts':{p.name:{'path':str(p),'sha256':sha(p)} for p in sorted(out.glob('config-*.json'))}}
    if recipe.get('producer_schema')==FINITE_PRODUCER_SCHEMA:
        if any(e.get('direction')=='request' and e.get('payload',{}).get('method')=='turn/start' for e in rpc.log):flow['finite_lookup_input']['failure_stage']='terminal' if receipt['healthy'] else 'dispatched'
        write(out/'finite-lookup-input.json',flow['finite_lookup_input'])
        receipt['producer_schema']=FINITE_PRODUCER_SCHEMA
        receipt['finite_policy_declaration']=recipe['finite_policy_declaration']
        receipt['policy_facts']={name:{'path':str(out/name),'sha256':sha(out/name)} for name in
            ('finite-lookup-input.json','finite-prelaunch.json','preflight.json','catalog-rpc/launch.json','catalog-rpc/rpc.json','catalog-rpc/closed.json','live-rpc/launch.json','startup-diagnostic-v3.json') if (out/name).is_file()}
    if flow.get('spec_closure'):
        receipt.update(row_id=recipe['rows'][0]['id'],mode=recipe['rows'][0]['mode'])
        for name in ('turn-01.json','before-config-01-v3.json'):
            if (out/name).is_file():receipt['facts'][name]={'path':str(out/name),'sha256':sha(out/name)}
        receipt['scope_facts'].update({p.name:{'path':str(p),'sha256':sha(p)} for p in sorted(out.glob('workflow-closure-*.json'))})
    if flow.get('tasks_timeout_handoff') is not None:receipt['tasks_timeout_handoff']=flow['tasks_timeout_handoff']
    if flow.get('business_edit'):
        receipt.update(business_edit_contract=flow['business_edit']['reference'],business_samples=flow.get('business_samples',[]),business_facts=flow.get('business_facts',[]))
    write(out/'workflow-context.json',receipt)
    if not receipt['closed'] or error or close_error:raise RuntimeError('HELD workflow closure/state incomplete: '+str(error or close_error))


def notification_packet_manifest(packet):
    packet=Path(packet);record=json.loads((packet/'notification-packet.json').read_text())
    if record.get('schema')!='notification-review-packet-v1' or record.get('author_conversation_included') is not False:raise RuntimeError('HELD notification packet schema')
    # Export outputs exist before Root reviews them. The packet's mutable index
    # cannot authorize itself: retain the pre-review identity outside the packet
    # and bind it through a concrete, separately hash-bound output review.
    if 'export_review' not in record:raise RuntimeError('HELD notification candidate requires post-export Root review')
    output_review=checked_json(record['export_review'])
    if (output_review.get('schema')!='notification-packet-output-review-v1' or
        output_review.get('decision')!='ACCEPT_EXACT_NOTIFICATION_PACKET_OUTPUTS'):
        raise RuntimeError('HELD concrete notification output review')
    for ref in (record['export_review'],output_review['candidate'],output_review['report']):
        if Path(ref['path']).resolve().is_relative_to(packet.resolve()) or sha(ref['path'])!=ref['sha256']:
            raise RuntimeError('HELD independent notification output identity/report')
    if checked_json(output_review['candidate'])!={k:v for k,v in record.items() if k!='export_review'}:
        raise RuntimeError('HELD notification packet differs from reviewed export identity')
    producer=checked_json(record['producer']);recipe=checked_json(producer['recipe']);contract=checked_json(record['contract'])
    review=checked_json(contract['root_review'])
    if (contract.get('schema')!='notification-packet-contract-v1' or
        review.get('data_sha256')!=canonical_hash({k:v for k,v in contract.items() if k!='root_review'}) or
        review.get('decision')!='ACCEPT_EXACT_NOTIFICATION_PACKET_INPUTS' or sha(review['report']['path'])!=review['report']['sha256']):raise RuntimeError('HELD concrete packet input adjudication')
    if (producer.get('closed') is not True or producer.get('healthy') is not True or producer.get('phase') not in ('AC9-handoff','unavailable') or
        producer.get('collector_sha256')!=sha(__file__) or recipe.get('adapter_sha256')!=sha(__file__) or
        (contract['producer']['sha256']!=record['producer']['sha256'] or Path(contract['producer']['path']).resolve()!=Path(record['producer']['path']).resolve()) or
        any(contract.get(k)!=record.get(k) for k in ('base_oid','head_oid','check_argv'))):raise RuntimeError('HELD actual notification producer/source/base relation')
    workflow_usage([*recipe['usage'],record['producer']])
    events=[e['payload'] for e in checked_json(producer['wire']) if e['direction']=='response_or_event']
    if not healthy_terminal(events,'live'):raise RuntimeError('HELD producer closed whole-wire terminal')
    required={'diff.patch','spec.md','tasks.md','review-prompt.md','checks.json','AC9.json','approvals.json','author-base.json',
              'app/settings.py','app/notifier.py','app/__init__.py','tests/__init__.py','tests/test_settings.py'}
    if not required<=set(record['files']):raise RuntimeError('HELD notification packet required input missing')
    actual={str(p.relative_to(packet)) for p in packet.rglob('*') if p.is_file()}
    if actual!=set(record['files'])|{'notification-packet.json'}:raise RuntimeError('HELD unlisted reviewer input')
    for p in packet.rglob('*'):
        relative=str(p.relative_to(packet))
        if p.is_symlink() or (p.is_dir() and not any(Path(relative) in Path(name).parents for name in record['files'])):raise RuntimeError('HELD reviewer namespace alias/unlisted directory')
    for name,digest in record['files'].items():
        p=packet/name;parts=Path(name).parts
        allowed=name in required or (parts[0] in ('app','tests') and p.suffix=='.py') or (parts[0]=='base' and len(parts)>2 and parts[1] in ('app','tests') and p.suffix=='.py')
        if not allowed or Path(name).is_absolute() or '..' in parts or p.is_symlink() or not p.resolve().is_relative_to(packet.resolve()) or sha(p)!=digest:
            raise RuntimeError('HELD packet path/content/author-chat boundary')
    target={name:digest for name,digest in record['files'].items() if Path(name).parts[0] in ('app','tests') and name.endswith('.py')}
    produced={name:entry.get('sha256') for name,entry in producer['state'].items() if (Path(name).parts or ('',))[0] in ('app','tests') and name.endswith('.py')}
    if target!=produced:raise RuntimeError('HELD packet target namespace differs from actual author state')
    for name in ('spec','tasks'):
        source=Path(contract[name]['path']);relative=str(source.resolve().relative_to(Path(producer['root']).resolve()))
        if producer['state'].get(relative,{}).get('sha256')!=contract[name]['sha256'] or record['files'][name+'.md']!=contract[name]['sha256']:raise RuntimeError('HELD packet approved artifact differs from producer')
    return record


def make_notification_review_packet(context_path, packet_out, manifest, contract_path):
    """Actual author objects and tests, never reviewer-created baseline history."""
    context_path=Path(context_path);cp=json.loads(context_path.read_text());root=Path(cp['root'])
    if (cp.get('schema')!='workflow-context-v1' or cp.get('purpose') not in ('workflow-after-setup','workflow-review-unavailable') or
        cp.get('phase') not in ('AC9-handoff','unavailable') or cp.get('closed') is not True or cp.get('healthy') is not True or
        workflow_inventory(root)!=cp['state']):raise RuntimeError('HELD actual latest notification producer state required')
    recipe=checked_json(cp['recipe']);contract_path=Path(contract_path);contract=json.loads(contract_path.read_text())
    producer={'path':str(context_path.resolve()),'sha256':sha(context_path)}
    review=checked_json(contract['root_review'])
    if (contract.get('schema')!='notification-packet-contract-v1' or contract['producer']['sha256']!=producer['sha256'] or Path(contract['producer']['path']).resolve()!=context_path.resolve() or
        review.get('data_sha256')!=canonical_hash({k:v for k,v in contract.items() if k!='root_review'}) or
        review.get('decision')!='ACCEPT_EXACT_NOTIFICATION_PACKET_INPUTS' or sha(review['report']['path'])!=review['report']['sha256']):raise RuntimeError('HELD actual post-closure notification export contract')
    ac9=checked_json(contract['AC9'])
    def git(*argv,ok=(0,)):
        p=subprocess.run(['git',*argv],cwd=root,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=30)
        if p.returncode not in ok:raise RuntimeError('HELD actual notification Git evidence failed')
        return p
    base=contract['base_oid'];head=contract['head_oid']
    if any(not isinstance(x,str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',x) for x in (base,head)):raise RuntimeError('HELD real full author OIDs required')
    if (git('rev-parse','--verify',base+'^{commit}').stdout.strip()!=base or git('rev-parse','HEAD').stdout.strip()!=head or
        git('rev-parse','main').stdout.strip()!=base or git('status','--porcelain','--untracked-files=no','--','app','tests').stdout.strip()):
        raise RuntimeError('HELD author base/main/target/dirty state mismatch')
    if any(line.endswith('.py') for line in git('ls-files','--others','--exclude-standard','--','app','tests').stdout.splitlines()):raise RuntimeError('HELD unreviewed untracked business source')
    if ac9.get('root')!=str(root) or ac9.get('base_oid')!=base or ac9.get('restore_oid')!=head or ac9.get('main_oid')!=base:raise RuntimeError('HELD AC9 author object relation')
    for child,parent in ((ac9['implementation_oid'],base),(ac9['revert_oid'],ac9['implementation_oid']),(head,ac9['revert_oid'])):
        if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',child) or git('rev-parse',child+'^').stdout.strip()!=parent:raise RuntimeError('HELD actual commit/revert/restoration chain')
    changed=set(git('diff-tree','--no-commit-id','--name-only','-r',ac9['implementation_oid']).stdout.splitlines())
    if not changed or not changed<={'app/settings.py','app/notifier.py','tests/test_settings.py','tests/test_notifier.py'}:raise RuntimeError('HELD implementation commit scope')
    data=ac9['data'];data_path=root/data['path']
    if (Path(data['path']).is_absolute() or '..' in Path(data['path']).parts or not data_path.resolve().is_relative_to(root.resolve()) or
        sha(data_path)!=data['sha256'] or git('ls-files','--error-unmatch','--',data['path'],ok=(0,1)).returncode!=1):raise RuntimeError('HELD persisted OFF data must remain outside commit')
    if json.loads(data_path.read_text()).get('email_notifications') is not False:raise RuntimeError('HELD real persisted notification OFF JSON required')
    if git('diff','--no-ext-diff','--no-textconv',ac9['implementation_oid'],head,'--','app','tests').stdout:raise RuntimeError('HELD restored implementation differs')
    steps=ac9['steps'];kinds=('implementation-commit','revert','baseline-behavior','restore','restored-tests')
    if [x.get('kind') for x in steps]!=list(kinds):raise RuntimeError('HELD actual AC9 step evidence missing')
    for step in steps:
        if (not isinstance(step.get('argv'),list) or not step['argv'] or step.get('cwd')!=str(root) or type(step.get('exit')) is not int or
            step['exit']!=0 or step.get('data_sha256')!=data['sha256'] or not isinstance(step.get('stdout'),str) or
            step.get('actor') not in ('model','authorized-fixture-actor') or
            sha(step['evidence']['path'])!=step['evidence']['sha256']):raise RuntimeError('HELD exact AC9 command/data receipts')
    adjudication=checked_json(ac9['root_review'])
    if (adjudication.get('AC9_sha256')!=canonical_hash({k:v for k,v in ac9.items() if k!='root_review'}) or
        adjudication.get('decision')!='ACCEPT_EXACT_NOTIFICATION_AC9_COMMAND_DATA_RELATION' or
        sha(adjudication['report']['path'])!=adjudication['report']['sha256']):raise RuntimeError('HELD concrete actual OFF-data/baseline/restore semantic review')
    out=Path(packet_out).resolve();export_identity=out.with_name(out.name+'-export.json')
    if export_identity.exists() or export_identity.is_symlink():raise RuntimeError('HELD notification export identity already exists')
    out.mkdir(parents=True,exist_ok=False)
    for name in ('spec','tasks'):
        ref=contract[name];p=Path(ref['path'])
        if not p.resolve().is_relative_to(root.resolve()) or sha(p)!=ref['sha256'] or not p.read_text().startswith('---\nstatus: approved\n---'):raise RuntimeError('HELD current approved notification artifact')
        shutil.copyfile(p,out/(name+'.md'))
    approvals=checked_json(contract['approvals'])
    if approvals.get('root')!=str(root) or approvals.get('spec')!=contract['spec'] or approvals.get('tasks')!=contract['tasks'] or not approvals.get('actual_USER_receipts'):raise RuntimeError('HELD actual spec/tasks/grant provenance')
    refs=[approvals[k] for k in ('spec_approval','tasks_approval','Git_grant')]
    if approvals['actual_USER_receipts']!=refs:raise RuntimeError('HELD exact three actual approval/grant relations')
    users=[workflow_user_evidence(ref,[*recipe['usage'],{'path':str(context_path.resolve()),'sha256':sha(context_path)}],root) for ref in refs]
    if any(users[i].get('approved_artifact')!=contract[name] for i,name in enumerate(('spec','tasks'))):raise RuntimeError('HELD packet actual artifact approval bindings')
    grant=users[2].get('operation_scope',{})
    if grant.get('root')!=str(root) or grant.get('operations')!=['commit','revert','revert-revert'] or set(grant.get('paths',[]))!=changed:raise RuntimeError('HELD exact scoped actual AC9 USER grant')
    if any(step.get('grant_payload_sha256')!=users[2]['payload_sha256'] for step in steps):raise RuntimeError('HELD actor/model AC9 steps not bound to actual scoped USER grant')
    write(out/'approvals.json',{'spec_sha256':contract['spec']['sha256'],'tasks_sha256':contract['tasks']['sha256'],
        'actual_USER_decisions':[{k:v for k,v in x.items() if k in ('text','approved_artifact','draft_artifact','payload_sha256')} for x in users]})
    public_ac9={k:v for k,v in ac9.items() if k!='root_review'}
    public_ac9['steps']=[{**{k:v for k,v in step.items() if k!='evidence'},'evidence_sha256':step['evidence']['sha256']} for step in steps]
    write(out/'AC9.json',public_ac9)
    diff=git('diff','--no-ext-diff','--no-textconv',base,head,'--','app','tests').stdout
    if not diff:raise RuntimeError('HELD actual notification diff missing')
    (out/'diff.patch').write_text(diff)
    baseline_names=git('ls-tree','-r','--name-only',base,'--','app','tests').stdout.splitlines()
    original=SOURCE/'tests/evals/ains-spec/new-feature-stops-at-spec-gate/files'
    expected_names={str(p.relative_to(original)) for folder in ('app','tests') for p in (original/folder).rglob('*.py')}
    if set(baseline_names)!=expected_names:raise RuntimeError('HELD original notification author baseline tree')
    for name in baseline_names:
        parts=Path(name).parts
        if Path(name).is_absolute() or '..' in parts or parts[0] not in ('app','tests') or not name.endswith('.py'):raise RuntimeError('HELD baseline business tree outside scope')
        p=out/'base'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(git('show',base+':'+name).stdout)
        if sha(p)!=sha(original/name):raise RuntimeError('HELD original notification baseline object content')
    for folder in ('app','tests'):
        for p in (root/folder).rglob('*.py'):
            if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):raise RuntimeError('HELD notification source alias')
            q=out/p.relative_to(root);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
    brief=root/'.agents/skills/ains-review/review-prompt.md';shutil.copyfile(brief,out/'review-prompt.md')
    argv=contract['check_argv']
    if argv not in (['python3','-B','-m','unittest','discover','-s','tests','-t','.'],['python3','-B','-m','unittest','discover','-s','tests','-v']):raise RuntimeError('HELD exact notification test command')
    result=subprocess.run(argv,cwd=root,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=180)
    write(out/'checks.json',{'argv':argv,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    write(out/'author-base.json',{'base_oid':base,'target_oid':head,'main_oid':base,'baseline_origin':'actual author Git objects, not reviewer initialization'})
    if sha(data_path)!=data['sha256']:raise RuntimeError('HELD persisted OFF data changed during checks')
    record={'schema':'notification-review-packet-v1','producer':{'path':str(context_path.resolve()),'sha256':sha(context_path)},
        'contract':{'path':str(contract_path.resolve()),'sha256':sha(contract_path)},
        'manifest_sha256':sha(manifest),'base_oid':base,'head_oid':head,'check_argv':argv,'check_exit':result.returncode,
        'source_review_brief_sha256':sha(brief),'author_conversation_included':False,
        'scope_before':cp['state'],'scope_after':workflow_inventory(root),
        'files':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}}
    # This is a candidate, not accepted reviewer input. Root subsequently reviews
    # these exact outputs (including checks) and attaches an external export_review
    # reference to the packet index; no future-output hash or approval is invented.
    write(export_identity,record)
    write(out/'notification-packet.json',record)
    return record


def materialize_notification_packet(packet, destination):
    """File-only preparation; install and execution require later Root release."""
    packet=Path(packet);record=notification_packet_manifest(packet);root=Path(destination).resolve()
    if root.exists():raise RuntimeError('HELD reviewer destination already exists')
    root.mkdir(parents=True)
    for name in record['files']:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(packet/name,p)
    # Do not expose author context/whole-wire paths to the reviewer.
    write(root/'review-input.json',{'packet_sha256':sha(packet/'notification-packet.json'),'base_oid':record['base_oid'],
          'head_oid':record['head_oid'],'check_argv':record['check_argv'],'files':record['files']})
    return {'schema':'notification-reviewer-materialization-v1','root':str(root),'state':workflow_inventory(root),
            'packet':{'path':str(packet/'notification-packet.json'),'sha256':sha(packet/'notification-packet.json')},'Git_initialized':False,'installed':False}


def materialize_notification_review(author_ref, reviewer_ref, packet, review, destination='docs/ains/reviews/notification-review.md'):
    author=checked_json(author_ref);reviewer=checked_json(reviewer_ref);packet=Path(packet);manifest=notification_packet_manifest(packet)
    if (author.get('purpose')!='workflow-review-unavailable' or reviewer.get('purpose')!='workflow-independent-review' or
        any(x.get('closed') is not True or x.get('healthy') is not True for x in (author,reviewer)) or
        author['unit']!=reviewer['unit'] or author['root']==reviewer['root'] or
        workflow_inventory(Path(author['root']))!=author['state']):raise RuntimeError('HELD latest fallback/independent reviewer/current author relation')
    reviewer_recipe=checked_json(reviewer['recipe'])
    author_recipe=checked_json(author['recipe'])
    if not any(workflow_ref_equal(manifest['producer'],x) for x in [author_ref,*author_recipe['usage']]):raise RuntimeError('HELD packet not from actual author lineage')
    if not reviewer_recipe['usage'] or not workflow_ref_equal(reviewer_recipe['usage'][-1],author_ref):raise RuntimeError('HELD reviewer must follow latest unavailable author context')
    workflow_usage([*reviewer_recipe['usage'],reviewer_ref])
    if reviewer_recipe.get('review_packet')!={'path':str(packet/'notification-packet.json'),'sha256':sha(packet/'notification-packet.json')}:raise RuntimeError('HELD reviewer current packet binding')
    wire=checked_json(reviewer['wire']);events=[e['payload'] for e in wire if e['direction']=='response_or_event']
    if sum(e['direction']=='request' and e['payload'].get('method')=='turn/start' for e in wire)!=1 or not healthy_terminal(events,'live'):raise RuntimeError('HELD actual one-turn reviewer wire/terminal')
    text='\n\n'.join(e['params']['item']['text'] for e in events if e.get('method')=='item/completed' and e.get('params',{}).get('item',{}).get('type')=='agentMessage')
    items=[e['params']['item'] for e in events if e.get('method')=='item/completed' and e.get('params',{}).get('item',{}).get('type')=='commandExecution']
    expected={'author':author_ref,'reviewer':reviewer_ref,'packet_sha256':sha(packet/'notification-packet.json'),
        'report_sha256':hashlib.sha256(text.encode()).hexdigest(),'completed_program_items_sha256':canonical_hash(items),'check_argv':manifest['check_argv'],
        'decision':'ACCEPT_ACTUAL_REVIEWER_TEST_AND_CURRENT_PACKET_RELATION'}
    if (not text or not items or any(review.get(k)!=v for k,v in expected.items()) or
        sha(review['report']['path'])!=review['report']['sha256']):raise RuntimeError('HELD concrete independent test/program/report review')
    if destination!='docs/ains/reviews/notification-review.md':raise RuntimeError('HELD exact notification report destination')
    root=Path(author['root']);target=root/destination
    if any(p.is_symlink() for p in target.parents if p.is_relative_to(root)):raise RuntimeError('HELD report parent alias')
    if target.exists() or target.is_symlink():raise RuntimeError('HELD report materialization would overwrite state')
    before=workflow_inventory(root);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
    return {'schema':'notification-review-handoff-v1','root':str(root),'author':author_ref,'reviewer':reviewer_ref,
        'packet_sha256':sha(packet/'notification-packet.json'),'before':before,'state':workflow_inventory(root),
        'destination':destination,'report_sha256':sha(target),'semantic_review_sha256':canonical_hash(review)}


CURRENT_AUTHOR_ROW = 'copy-r7-build-authority-continuation'
CURRENT_AUTHOR_DIAGNOSIS = SOURCE/'.omx/ultragoal/evidence/g004/codex/native-v7/preparation/copy-timeout-current-state'


def current_author_inventory(root):
    """Complete read-only namespace, including empty directories, Git and caches."""
    root=Path(root);canonical=root.resolve(strict=True);result={}
    if root.is_symlink() or not root.is_dir():raise RuntimeError('HELD current-author root topology')
    pending=[root]
    while pending:
        path=pending.pop();info=path.lstat();real=path.resolve(strict=True)
        if not real.is_relative_to(canonical):raise RuntimeError('HELD current-author alias escape')
        record={'mode':oct(stat.S_IMODE(info.st_mode)),'identity':[info.st_dev,info.st_ino],
                'realpath':str(real),'link_text':os.readlink(path) if path.is_symlink() else None}
        if path.is_symlink():
            target=path.stat()
            if stat.S_ISREG(target.st_mode) and target.st_nlink!=1:raise RuntimeError('HELD current-author hardlink target')
            record.update(kind='symlink',target_identity=[target.st_dev,target.st_ino],sha256=sha(path) if path.is_file() else None)
        elif stat.S_ISREG(info.st_mode):
            if info.st_nlink!=1:raise RuntimeError('HELD current-author hardlink')
            record.update(kind='file',sha256=sha(path))
        elif stat.S_ISDIR(info.st_mode):
            record['kind']='directory';pending.extend(sorted(path.iterdir(),reverse=True))
        else:raise RuntimeError('HELD unsupported current-author filesystem entry')
        result[str(path.relative_to(root))]=record
    return dict(sorted(result.items()))


def current_author_seconds(row,enabled):
    if not enabled:return 180
    if (row.get('id')!=CURRENT_AUTHOR_ROW or row.get('mode')!='copy' or row.get('transport')!='live' or
        type(row.get('max_user_turns')) is not int or row['max_user_turns']!=1 or
        type(row.get('terminal_deadline_seconds')) is not int or row['terminal_deadline_seconds']!=360):
        raise RuntimeError('HELD exact current-author live/copy/one-turn/360 row required')
    return 360


def current_author_mode(args,recipe,row,binding):
    checkpoint=getattr(args,'current_author_checkpoint',None);release=getattr(args,'current_author_release',None)
    enabled=bool(checkpoint or release)
    if enabled:
        if (not checkpoint or not release or any(getattr(args,key,None) for key in
            ('setup_checkpoint','setup_checkpoint_review','derivative_release','packet')) or binding.get('setup_artifact_contract') or
            recipe.get('execution_kind')!='current-author-continuation' or row.get('execution_kind')!='current-author-continuation' or
            any(key in recipe for key in ('fixture_root','fixture_hashes','setup_checkpoint_file_sha256','setup_content_ack_text','setup_repeat_text','setup_artifact_contract'))):
            raise RuntimeError('HELD current-author mode is separate from fixture/setup/derivative/packet execution')
        current_author_seconds(row,True)
    elif recipe.get('execution_kind')=='current-author-continuation' or row.get('id')==CURRENT_AUTHOR_ROW:
        raise RuntimeError('HELD jointly required current-author checkpoint and release')
    return enabled


def validate_current_author(checkpoint_path,release_path,recipe_path,row,binding,release_id,out):
    """Finite external-review bindings; never converts timeout history to success."""
    recipe=json.loads(Path(recipe_path).read_text());cp=checked_json(recipe['current_author_checkpoint'])
    if Path(recipe['current_author_checkpoint']['path']).resolve()!=Path(checkpoint_path).resolve():raise RuntimeError('HELD wrong current-author checkpoint')
    release=json.loads(Path(release_path).read_text())
    if binding.get('current_author_release_sha256')!=sha(release_path):raise RuntimeError('HELD current-author release/native binding')
    disposition=checked_json({'path':str(SOURCE/'.omx/ultragoal/evidence/r7-parent-verification/current-author-continuation-design-disposition.json'),
        'sha256':'5c64030d05b3ab93fb77fd0f279d95ebb4dc35795f44841fe432a438c462737f'})
    index=checked_json(cp['diagnosis_index'])
    if cp['diagnosis_index']!={'path':str(CURRENT_AUTHOR_DIAGNOSIS/'index.json'),'sha256':'0795ff449e7c82a517a59e66bbecbdceb580a92112a3b1f1dd6c6b61beb58747'}:raise RuntimeError('HELD different timeout diagnosis')
    plan=checked_json({'path':str(CURRENT_AUTHOR_DIAGNOSIS/'plan.json'),'sha256':index['plan_sha256']})
    for ref in disposition['references'][:2]:
        if sha(ref['path'])!=ref['sha256']:raise RuntimeError('HELD accepted diagnosis changed')
    if (cp.get('schema')!='current-author-checkpoint-v1' or cp.get('predecessor')!=index['pinned_frozen_evidence'] or
        cp.get('root')!=plan['same_consumer']['logical'] or cp.get('realroot')!=plan['same_consumer']['canonical'] or
        cp.get('settled_USER')!=plan['same_consumer']['settled_actual_USER_0600'] or cp.get('memo')!=plan['same_consumer']['actual_recorded_memo'] or
        'server_returncode' not in cp or cp['server_returncode'] is not None or cp.get('successful_terminal3') is not False or
        'postcomparison3' not in cp or cp['postcomparison3'] is not None):raise RuntimeError('HELD immutable closed-timeout/decision contract')
    pinned=cp['predecessor']
    for path,digest in pinned.items():
        if sha(path)!=digest:raise RuntimeError('HELD predecessor changed: '+path)
    base=Path(plan['predecessor_timeout']['whole_wire']['path']).parents[2]
    frozen=json.loads((base/'FROZEN-MANIFEST.json').read_text())
    for name,digest in frozen['files'].items():
        if sha(base/name)!=digest:raise RuntimeError('HELD frozen predecessor file changed')
    old_auth=checked_json(cp['prior_authorization']);old_recipe=checked_json(cp['prior_recipe'])
    auth=json.loads((base/'authorization-receipt.json').read_text())
    if (old_auth!=auth or sha(cp['prior_authorization']['path'])!=frozen['files']['authorization-receipt.json'] or
        sha(cp['prior_recipe']['path'])!=old_auth['actual_release']['recipe_sha256'] or
        sha(cp['prior_collector']['path'])!=cp['prior_collector']['sha256'] or
        cp['prior_collector']['sha256']!=old_auth['actual_release']['adapter_sha256'] or
        release_id==old_auth['actual_release']['release_id']):raise RuntimeError('HELD predecessor producer/recipe/release identity')
    handoff=json.loads((base/'copy-timeout-handoff.json').read_text());operator=json.loads((base/'copy-r7-build-questions-operator-result.json').read_text())
    closed=json.loads((base/'copy-r7-build-questions/live-rpc/closed.json').read_text())
    turn2=json.loads((base/'copy-r7-build-questions/turn-02.json').read_text());turn3=json.loads((base/'copy-r7-build-questions/turn-03.json').read_text())
    if (handoff['server_active'] is not False or handoff['adapter_exit']!=1 or operator['adapter_closed'] is not True or operator['exit']!=1 or
        closed['stable'] is not True or handoff['turn3_completed_terminal_in_turn_record'] is not False or
        turn3['text']!=cp['settled_USER']['exact_text'] or any(e.get('method')=='turn/completed' for e in turn3['events'])):
        raise RuntimeError('HELD missing actual timeout closure or forged success')
    inventory=cp['inventory'];known=index['current_project_before_readonly_hashes_modes_paths']
    # Exact known file set includes installed dependencies and Git namespace.
    # Additional directory topology/inodes and absences are concretely ROOT-reviewed.
    if inventory.get('.',{}).get('realpath')!=cp['realroot']:raise RuntimeError('HELD root canonical topology')
    if {k for k,v in inventory.items() if v['kind']!='directory'}!=set(known):raise RuntimeError('HELD current-author file/cache namespace differs')
    for name,record in known.items():
        if any(inventory[name].get(k)!=record[k] for k in ('sha256','mode','realpath')) or inventory[name]['kind']!='file':raise RuntimeError('HELD diagnosed source/grants/spec/tasks/cache identity')
    if not cp.get('absent') or any(not isinstance(p,str) or Path(p).is_absolute() or '..' in Path(p).parts or p in inventory or any(k.startswith(p+'/') for k in inventory) for p in cp['absent']):raise RuntimeError('HELD current-author absence contract')
    body=turn2['events'][28]['params']['item'];body_path='.agents/skills/ains-build/SKILL.md'
    output=body.get('aggregatedOutput','').split('\n',1)
    if (body.get('type')!='commandExecution' or body.get('status')!='completed' or body.get('exitCode')!=0 or
        body.get('cwd')!=cp['root'] or len(output)!=2 or output[0]!=inventory[body_path]['realpath'] or not output[1].endswith('\n') or
        hashlib.sha256(output[1][:-1].encode()).hexdigest()!=inventory[body_path]['sha256']):
        raise RuntimeError('HELD prior successful installed body observation')
    if (recipe.get('rows')!=[row] or recipe['release_manifest_sha256']!=old_recipe['release_manifest_sha256'] or
        recipe['helper_imports']!=old_recipe['helper_imports'] or recipe['checkpoint_installed']!=json.loads((base/'copy-r7-build-questions/installed.json').read_text())['inventory']):raise RuntimeError('HELD source/install/helper/selected-row continuity')
    premises=plan['proposed_runtime_premises']
    if (binding.get('forward_thread_expectation')!=premises['proposed13fields'] or binding.get('forward_trust_root')!=premises['canonical_trust_root'] or
        binding.get('proof_sha256')!=premises['native_source_proof']['sha256']):raise RuntimeError('HELD current-author original native/model/permission/root premises')
    common={'checkpoint_sha256':sha(checkpoint_path),'recipe_sha256':sha(recipe_path),'collector_sha256':sha(__file__),
        'helpers':recipe['helper_imports'],'manifest_sha256':recipe['release_manifest_sha256'],'native_premises_sha256':binding['native_premises_sha256']}
    source=checked_json(release['source_review']);root_review=checked_json(release['root_review']);native=checked_json(release['native_premises'])
    if native!={k:v for k,v in binding.items() if k not in ('current_author_release_sha256','native_premises_sha256')}:
        raise RuntimeError('HELD native premise document differs from actual selected binding')
    for doc,schema in ((source,'current-author-source-review-v1'),(root_review,'current-author-root-review-v1'),(release,'current-author-release-v1')):
        if doc.get('schema')!=schema or any(doc.get(k)!=v for k,v in common.items()):raise RuntimeError('HELD concrete current-author review/source bindings')
    for review in (source,root_review):
        if review.get('verdict')!='APPROVE' or sha(review['report']['path'])!=review['report']['sha256']:raise RuntimeError('HELD concrete independent/root review report')
    if (root_review.get('source_review_sha256')!=release['source_review']['sha256'] or root_review.get('inventory_sha256')!=canonical_hash(inventory) or
        root_review.get('settled_USER')!=cp['settled_USER'] or root_review.get('memo')!=cp['memo'] or
        root_review.get('scope')!='approved spec/tasks; T1-T3 done; T4/AC9 pending; no Git authority' or
        release['native_premises']['sha256']!=binding['native_premises_sha256'] or native.get('proof_sha256')!=binding['proof_sha256'] or native.get('scope')!='configured-native-selector'):
        raise RuntimeError('HELD concrete ROOT state/scope/native premises review')
    text=row['initial_user_text'];base_text=plan['draft_future_actual_USER_text_UNSENT']
    if (root_review.get('user_sha256')!=hashlib.sha256(text.encode()).hexdigest() or
        root_review.get('input_base_sha256')!=hashlib.sha256(base_text.encode()).hexdigest()):raise RuntimeError('HELD exact ROOT-reviewed actual USER input')
    if root_review.get('input_change')=='none':
        if text!=base_text:raise RuntimeError('HELD changed current-author input')
    elif root_review.get('input_change')=='time-only-360':
        # ROOT reviews concrete wording against the consumer cap. This is
        # external semantic evidence, not an automatic permission classifier.
        if sha(root_review['time_override_review']['path'])!=root_review['time_override_review']['sha256']:raise RuntimeError('HELD time-only input review')
    else:raise RuntimeError('HELD unsupported current-author input change')
    exact={'release_id':release_id,'row_id':CURRENT_AUTHOR_ROW,'root':cp['root'],'realroot':cp['realroot'],
        'user_sha256':hashlib.sha256(row['initial_user_text'].encode()).hexdigest(),'out':str(Path(out).resolve()),
        'new_contexts':1,'new_USER_turns':1,'terminal_deadline_seconds':360,'actual_before':18,'held_before':88,'whole_ceiling':106,'unused_question_turns':1}
    if any(type(release.get(k)) is not type(v) or release.get(k)!=v for k,v in exact.items()):raise RuntimeError('HELD exact new release/USER/quota/output/deadline')
    current_author_seconds(row,True)
    if Path(out).resolve().is_relative_to(Path(cp['realroot'])):raise RuntimeError('HELD evidence output must be outside current consumer')
    if current_author_inventory(Path(cp['root']))!=inventory:raise RuntimeError('HELD current-author complete inventory/topology drift')
    return dict(cp,prior_body_event_index=28,current_release_sha256=sha(release_path))


def run_row(args):
    # This is an implemented execution surface, not a grant of release authority.
    if not args.release_id or args.release_id=='PARENT_RELEASE_REQUIRED': raise RuntimeError('Actual parent release required')
    prepared=Path(args.prepared); recipe=json.loads((prepared/'recipe.json').read_text())
    manifest=Path(getattr(args,'manifest',None) or recipe['release_manifest']).resolve()
    if recipe['release_manifest_sha256']!=sha(manifest): raise RuntimeError('Source release changed after preparation')
    if recipe['adapter_sha256']!=sha(__file__): raise RuntimeError('Adapter differs from reviewed preparation')
    released_source(manifest)
    if not args.native_binding:raise RuntimeError('Reviewed current-version native selector binding required before any runtime launch')
    binding=json.loads(Path(args.native_binding).read_text())
    row=next(r for r in recipe['rows'] if r['id']==args.row)
    workflow=recipe.get('execution_kind')=='bounded-workflow-v1'
    flow=validate_workflow_checkpoint(args,recipe,row,binding) if workflow else None
    current_author=False if workflow else current_author_mode(args,recipe,row,binding)
    author_checkpoint=validate_current_author(args.current_author_checkpoint,args.current_author_release,prepared/'recipe.json',row,binding,args.release_id,args.out) if current_author else None
    def bind_finite_session_policy(reference, recipe, root, binding):
        """A future Root declaration binds an acyclic base, not its new recipe."""
        declaration=checked_json(reference)
        if declaration.get('schema')!='ROOT_FINITE_SESSION_TRUST_DECLARATION_V1' or declaration.get('decision')!='DECLARE_EXACT_PROCESS_ONLY_POLICY':raise RuntimeError('HELD finite Root declaration required')
        choice_ref=declaration['operator_choice']
        choice=checked_json(choice_ref);scope=finite_scope(choice['root'])
        logical_root=scope['root'];canonical_root=scope['canonical_root']
        if choice_ref!=scope['operator_choice']:raise RuntimeError('HELD finite Root choice pin')
        policy=finite_session_policy(choice,recipe)
        for key in ('base_recipe','checkpoint','product'):
            if declaration.get(key)!=choice.get(key):raise RuntimeError('HELD finite base/checkpoint/product relation')
            checked_json(declaration[key])
        base=checked_json(declaration['base_recipe']);checkpoint=checked_json(declaration['checkpoint'])
        expected_recipe=dict(base,adapter_sha256=sha(__file__),producer_schema=FINITE_PRODUCER_SCHEMA,finite_policy_declaration=reference)
        pair={str(Path(__file__)):declaration['collector_sha256'],str(Path(__file__).with_name('native_delta_test.py')):declaration['tests_sha256']}
        expected_recipe['protected_files']=[dict(v,sha256=pair.get(v['path'],v['sha256'])) for v in base['protected_files']]
        expected_recipe['usage']=finite_recipe_usage(base,recipe)
        if recipe!=expected_recipe:raise RuntimeError('HELD finite exact base recipe and two-source-only delta')
        if (str(root)!=logical_root or str(root.resolve())!=canonical_root or
            declaration.get('collector_sha256')!=sha(__file__) or declaration.get('tests_sha256')!=sha(Path(__file__).with_name('native_delta_test.py')) or
            declaration.get('helpers')!=recipe.get('helper_imports') or declaration.get('official_commit')!=SEMANTIC_COMMIT or
            declaration.get('binary_sha256')!=binding['executable_identity']['sha256'] or recipe.get('producer_schema')!=FINITE_PRODUCER_SCHEMA or
            base['rows'][0]['initial_user_text']!=recipe['rows'][0]['initial_user_text'] or
            checkpoint.get('root')!=logical_root or checkpoint.get('realroot')!=canonical_root):raise RuntimeError('HELD finite declaration source/scope/USER')
        validate_finite_producer(declaration,recipe['helper_imports'])
        policy.update(declaration=reference,metadata_paths=declaration.get('metadata_paths'))
        if not policy['metadata_paths']:raise RuntimeError('HELD finite complete metadata read scope')
        # The complete checkpoint and parent-protected inputs must agree before any process.
        protected=[p['path'] for p in recipe['protected_files']]
        if workflow_inventory(root,protected,False)!=checkpoint['state'] or len([k for k in checkpoint['state'] if not k.startswith('@')])!=scope['state_count']:raise RuntimeError('HELD finite exact checkpoint count')
        validate_finite_metadata(declaration,recipe,binding['forward_thread_expectation']['instructionSources'],choice)
        if sha(root/'AGENTS.md')!=choice['AGENTS_sha256']:raise RuntimeError('HELD finite original AGENTS bytes')
        return policy
    policy=None
    if binding.get('finite_policy_declaration') or recipe.get('producer_schema')==FINITE_PRODUCER_SCHEMA or (workflow and flow['root'] in FINITE_SCOPES):
        if not workflow:raise RuntimeError('HELD finite workflow only')
        if recipe.get('finite_policy_declaration')!=binding.get('finite_policy_declaration') or not binding.get('unchanged_startup'):raise RuntimeError('HELD finite recipe/declaration/current lookup relation')
        policy=bind_finite_session_policy(binding['finite_policy_declaration'],recipe,Path(flow['root']),binding)
        retained_home=validate_finite_metadata(checked_json(policy['declaration']),recipe,binding['forward_thread_expectation']['instructionSources'],checked_json(checked_json(policy['declaration'])['operator_choice']))
        binding=dict(binding,finite_session_policy=policy,_finite_home_identity=hashlib.sha256(str(Path(retained_home).parent).encode()).hexdigest())
        validate_finite_lookup(binding['unchanged_startup'],policy,sha(__file__),sha(prepared/'recipe.json'),sha(manifest),binding['executable_identity']['sha256'])
    actual_version=subprocess.run(['codex','--version'],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=20).stdout.strip()
    if binding.get('codex_version')!=actual_version or binding.get('parent_release_id')!=args.release_id or binding.get('scope')!='configured-native-selector' or sha(Path(binding['proof_path']))!=binding.get('proof_sha256'):raise RuntimeError('Unbound current-version native selector proof')
    for entry in recipe['helper_imports']:
        if sha(SOURCE/entry['path'])!=entry['sha256']:raise RuntimeError('Imported helper drift')
    for rel,digest in ({} if current_author or workflow else recipe['fixture_hashes']).items():
        if sha(Path(recipe['fixture_root'])/rel)!=digest:raise RuntimeError('Prepared fixture drift')
    if row['transport'] not in binding.get('transports',[]):raise RuntimeError('Native selector binding does not cover selected transport')
    out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=False)
    root=Path(flow['root']) if workflow else Path(author_checkpoint['root']) if current_author else Path(recipe['consumer_root'])/row['id']
    if policy:
        flow['finite_lookup_input']={'current_receipt':binding['unchanged_startup'],'failure_stage':'before-catalog'}
        write(out/'finite-lookup-input.json',flow['finite_lookup_input'])
    continuation=None
    if workflow:
        print(json.dumps({'actual_USER_workflow_context_approval_required':True,'checkpoint':recipe['workflow_checkpoint'],
                         'release_sha256':sha(args.current_author_release)}),flush=True)
        approval=json.loads(sys.stdin.readline())
        if (approval.get('role')!='user' or approval.get('action')!='approve_bounded_workflow_context' or approval.get('new_context') is not True or
            approval.get('checkpoint_sha256')!=recipe['workflow_checkpoint']['sha256'] or
            approval.get('release_sha256')!=sha(args.current_author_release) or not isinstance(approval.get('text'),str) or not approval['text'].strip()):
            raise RuntimeError('HELD actual separate workflow context USER approval missing')
        write(out/'workflow-context-input.json',{'approval':approval,'checkpoint':recipe['workflow_checkpoint'],'release_sha256':sha(args.current_author_release)})
    if current_author:
        write(out/'current-author-input-binding-v1.json',{'checkpoint':recipe['current_author_checkpoint'],'release':{'path':str(Path(args.current_author_release).resolve()),'sha256':author_checkpoint['current_release_sha256']},'recipe_sha256':sha(prepared/'recipe.json'),'collector_sha256':sha(__file__),'native_binding_sha256':sha(args.native_binding)})
    if getattr(args,'setup_checkpoint_review',None) and not getattr(args,'setup_checkpoint',None):raise RuntimeError('Checkpoint review requires explicit continuation mode')
    if getattr(args,'setup_checkpoint',None):
        if row['transport']!='live' or not getattr(args,'setup_checkpoint_review',None):raise RuntimeError('Setup continuation requires live row and concrete review')
        checkpoint_path=Path(args.setup_checkpoint)
        if sha(checkpoint_path)!=recipe.get('setup_checkpoint_file_sha256'):raise RuntimeError('Checkpoint file not bound by reviewed recipe')
        checkpoint=json.loads(checkpoint_path.read_text());review=json.loads(Path(args.setup_checkpoint_review).read_text())
        print(json.dumps({'actual_USER_checkpoint_approval_required':True,'checkpoint_sha256':canonical_hash(checkpoint),'review_sha256':canonical_hash(review),'new_context':True}),flush=True)
        approval=json.loads(sys.stdin.readline())
        if checkpoint.get('schema')==DERIVATIVE_SCHEMA:
            release_path=getattr(args,'derivative_release',None)
            if not release_path or sha(release_path)!=binding.get('derivative_release_sha256'):raise RuntimeError('HELD exact separate derivative C1 release required')
            derivative_release=json.loads(Path(release_path).read_text())
            if derivative_release.get('release_id')!=args.release_id:raise RuntimeError('HELD wrong derivative C1 release id')
            continuation=validate_derivative_continuation(checkpoint,review,approval,root,dict(recipe,_verified_recipe_sha256=sha(prepared/'recipe.json')),sha(manifest),derivative_release)
        else:
            if recipe.get('pending_repeat_ack'):raise RuntimeError('HELD pending acknowledgement only on derivative route')
            continuation=validate_setup_continuation(checkpoint,review,approval,root,recipe,sha(manifest),args.release_id)
        if binding.get('setup_artifact_contract',{}).get('stage')!='setup-repeat':raise RuntimeError('Continuation requires prebound repeat artifact observation contract')
        first=recipe['setup_repeat_text'] if continuation.get('pending_repeat_ack') else recipe['setup_content_ack_text']
        if row['initial_user_text']!=first:raise RuntimeError('Continuation initial USER differs from exact reviewed acknowledgment/repeat contract')
        write(out/'setup-continuation-input-v1.json',continuation)
    elif root.exists() and not current_author and not workflow:raise RuntimeError('Fresh row consumer already exists; no replay')
    # Copy preserves symlinks; reconstruct the one intentional hardlink.
    if not continuation and not current_author and not workflow:
        shutil.copytree(Path(recipe['fixture_root'])/row['fixture'],root,symlinks=True)
        if row['fixture']=='samefile':(root/'CLAUDE.md').unlink();os.link(root/'AGENTS.md',root/'CLAUDE.md')
    if not current_author and not workflow and row['fixture'] in ['review-packet','review-unavailable']:
        if not args.packet:raise RuntimeError('Actual current workflow packet required; no substitute fixture review')
        packet=Path(args.packet).resolve();copied={}
        for source in packet.rglob('*'):
            if not source.is_file():continue
            relative=source.relative_to(packet)
            allowed=str(relative) in ['diff.patch','spec.md','tasks.md','checks.txt','review-prompt.md','calc.py'] or (relative.parts[0] in ['tests','shop'] and source.suffix=='.py') or (relative.parts[0]=='docs' and source.suffix=='.md')
            if not allowed:continue
            if source.is_symlink() or not source.resolve().is_relative_to(packet):raise RuntimeError('Packet link escapes source boundary')
            target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);copied[str(relative)]=sha(source)
        if row['fixture']=='review-packet' and not all(x in copied for x in ['diff.patch','spec.md','checks.txt']):raise RuntimeError('Incomplete current review packet')
        write(out/'packet-inputs.json',copied)
    with bound_helpers(out/'helper-sink') as (helpers, imports):
        rt,ar,a=[helpers[n] for n in ['runtime','activation_recheck','activation_r3']]
        retain=(lambda path,value:write(path,finite_receipt(value))) if policy else ar.write
        if continuation or current_author or workflow:pass
        elif (root/'setup.sh').exists():
            p=subprocess.run(['bash','setup.sh'],cwd=root,stdin=subprocess.DEVNULL,capture_output=True,timeout=30)
            if p.returncode:raise RuntimeError('Original fixture setup failed')
        else:
            subprocess.run(['git','init','--quiet',str(root)],check=True)
        install=['npx','--yes','skills@1.7.4','add',str(SOURCE),'--skill','*','-a','codex','-y']+(['--copy'] if row['mode']=='copy' else [])
        if not continuation and not current_author and not workflow:
            p=subprocess.run(install,cwd=root,stdin=subprocess.DEVNULL,capture_output=True,timeout=180)
            if p.returncode:raise RuntimeError('Pinned suite install failed')
        retain(out/'layout-before.json',layout(root))
        installed=a.inventory(root)
        if (continuation or current_author or workflow) and installed!=recipe['checkpoint_installed']:raise RuntimeError('Checkpoint installed source/provenance drift')
        retain(out/'installed.json',{'argv':None if current_author or workflow else install,'inventory':installed,'physical_entries':{x['name']:(root/'.agents/skills'/x['name']).is_symlink() for x in installed}})
        if policy:
            def metadata_sample():
                checked_json(policy['declaration'])
                mdm_before=a.mdm_forced()
                files={str(p):{'exists':Path(p).exists(),'sha256':sha(p) if Path(p).is_file() else None,'realpath':str(Path(p).resolve())} for p in policy['metadata_paths']}
                return finite_metadata_sample(policy,{'mdm_before':mdm_before,'mdm_after':a.mdm_forced(),'files':files})
            binding['_metadata_sample']=metadata_sample
            before=metadata_sample();overrides=list(policy['overrides'])
            retain(out/'finite-prelaunch.json',before)
        else:
            before=a.probe(root);overrides=['features.'+n+'=false' for n in a.CANONICAL]
            if row['transport']=='live':overrides+=['features.'+key+'=false' for key in DISCOVERY_KEYS]
            for name in before['all_layer_mcp_names']:overrides+=['mcp_servers.'+name+'.enabled=false','mcp_servers.'+name+'.command="/usr/bin/false"']
        current_catalog_rpc=recorded_rpc(rt,ar,root,overrides,out/'catalog-rpc',binding)
        try:
            config=current_catalog_rpc.call('config/read',{'includeLayers':True,'cwd':str(root)},timeout=30)
            facts=config_facts(config,helpers['activation_closure_probe'].structural)
            catalog=current_catalog_rpc.call('skills/list',{'cwds':[str(root)],'forceReload':True},timeout=30)
            environment_proof=current_catalog_rpc.selected_environment
            if policy:
                again=current_catalog_rpc.call('config/read',{'includeLayers':True,'cwd':str(root)},timeout=30)
                if config!=again or finite_policy_projection(config,policy)!=finite_policy_projection(again,policy):raise RuntimeError('HELD finite catalog raw drift')
                binding['_finite_policy_observation']=finite_policy_projection(config,policy)
        finally:current_catalog_rpc.close()
        retain(out/'catalog.json',{'request':'skills/list','complete_applicable_catalog':catalog,'structural_configuration':facts,'boundary':'Current configured app-server catalog; explicit current semantic binding + loader/root/settings relation required, not catalog alone'})
        catalog_proof=validate_catalog(catalog,installed,facts,row['transport'])
        selector_receipt=native_selection_receipt(binding,catalog_proof,environment_proof,row['transport'])
        retain(out/'native-selection-receipt.json',selector_receipt)
        bodies={x['name']:(root/'.agents/skills'/x['name']/'SKILL.md').read_text() for x in installed}
        installed_paths={x['name']:x['path'] for x in installed}
        retain(out/'release.json',{'actual_parent_release_id':args.release_id,'row':row,'root':str(root),'imports':imports,'release_sha256':sha(manifest),'overrides':overrides,'reviewed_native_binding':{k:v for k,v in binding.items() if k!='_metadata_sample'}})
        second=metadata_sample() if policy else a.probe(root)
        if row['transport']=='cli':
            applied_before=a.applied_probe(root,overrides,before['all_layer_mcp_names'])
            applied_second=a.applied_probe(root,overrides,second['all_layer_mcp_names'])
            launch=a.launch_receipt(root,row['initial_user_text'],overrides)
            initial=a.comparison_input(before,applied_before,installed,sha(manifest))
            bound=a.comparison_input(second,applied_second,installed,sha(manifest))
            precheck=a.compare_activation_inputs(initial,bound,launch,Path.home()/'.codex/config.toml')
            precheck['external_0164_semantic_binding']={'commit':SEMANTIC_COMMIT,'proof_sha256':binding['proof_sha256'],'old_helper_label_preserved':True}
            retain(out/'precomparison.json',precheck)
            if not precheck['projected_stable']:raise RuntimeError('CLI pre/pre source-bound projection failed')
        elif before!=second:raise RuntimeError('Live app-server active user configuration changed; no ignored-user projection applies')
        retain(out/'preflight.json',{'first':before,'second':second,'transport':row['transport'],'live_is_sterile':False,'source_manifest_sha256':sha(manifest)})
        if row['transport']=='cli':
            ar.collect(root,row['id'],row['initial_user_text'],out,overrides)
            rec=json.loads((out/(row['id']+'.json')).read_text())
            if rec['timeout'] or rec['exit']!=0 or not healthy_terminal(rec['events'],'cli') or rec['stdout_line_count']!=rec['retained_json_event_count']:raise RuntimeError('Runtime timeout/failure/missing terminal/incomplete emitted JSON')
            retain(out/'native-oracle.json',native_oracle(rec['events'],row['initial_user_text'],bodies,installed_paths,selector_bound=selector_receipt))
        else:
            if policy:flow['finite_lookup_input']['failure_stage']='before-live'
            rpc=recorded_rpc(rt,ar,root,overrides,out/'live-rpc',binding)
            checkpoint=None
            workflow_observation=None;workflow_healthy=False
            try:
                selection_wire_start=len(rpc.log)
                live_config=rpc.call('config/read',{'includeLayers':True,'cwd':str(root)},timeout=30)
                live_facts=config_facts(live_config,helpers['activation_closure_probe'].structural)
                if policy and finite_policy_projection(live_config,policy)!=binding['_finite_policy_observation']:raise RuntimeError('HELD finite catalog/live policy drift')
                live_catalog=rpc.call('skills/list',{'cwds':[str(root)],'forceReload':True},timeout=30)
                selector_receipt=native_selection_receipt(binding,validate_catalog(live_catalog,installed,live_facts,'live'),rpc.selected_environment,'live')
                if workflow and flow.get('spec_closure'):selector_receipt={**selector_receipt,'closure_wire':{'schema':'spec-closure-native-wire-v1','wire_start_index':selection_wire_start,'wire_end_index':len(rpc.log)}}
                retain(out/'live-native-selection-receipt.json',selector_receipt)
                # New parent binding supplies the finite snapshot contract; no
                # guessed defaults or inferred capture-version identity.
                expected=binding.get('forward_thread_expectation',{})
                if set(expected)!=set(THREAD_FIELDS):raise RuntimeError('Missing forward_thread_expectation; readiness held')
                trust_root=binding.get('forward_trust_root')
                if not trust_root or not root.resolve().is_relative_to(Path(trust_root).resolve()):raise RuntimeError('Missing applicable parent-bound trust root')
                user_path=str(Path.home()/'.codex/config.toml')
                def user_config():
                    return tomllib.loads(Path(user_path).read_text()) if Path(user_path).is_file() else {}
                live_binding=dict(binding,_mcp_names=before['all_layer_mcp_names'])
                rpc.bound_thread=None
                paths=set(second['files'])
                if binding.get('unchanged_startup'):
                    paths.add(binding['unchanged_startup']['path'])
                    paths.update(str(SOURCE/name) for name in STARTUP_LOOKUP_SOURCES)
                closure=flow.get('spec_closure') if workflow else None
                closure_draft=str(root/closure['draft_path']) if closure else None
                closure_paths={closure_draft,str(Path(flow['checkpoint']['realroot'])/closure['draft_path'])} if closure else set()
                if closure and paths&closure_paths:raise RuntimeError('HELD closure draft is a raw immutable config/source role')
                business_edit=flow.get('business_edit') if workflow else None
                if business_edit:
                    paths.update(business_edit['data'][key]['path'] for key in ('spec_USER','tasks_USER'))
                    paths.add(business_edit['reference']['path'])
                    progress=flow['review']['business'].get('tasks_progress')
                    if progress:paths.update(progress[key]['path'] for key in ('approved_snapshot','report'))
                if workflow:paths.update(p for p in flow['protected'] if (not business_edit or p not in business_edit['paths']) and p not in closure_paths)
                if workflow and not flow['setup']:paths.update(str(root/name) for name in (*SETUP_SLOTS,'docs/ains/human-review-rules','docs/ains/reviews/notification-review.md') if (root/name).is_file())
                if workflow and recipe['phase'] not in ('build','AC9-handoff'):
                    paths.update(str(p) for folder in ('app','tests') for p in (root/folder).rglob('*.py'))
                elif business_edit:
                    paths.update(str(p) for folder in ('app','tests') for p in (root/folder).rglob('*.py') if str(p) not in business_edit['paths'])
                    task_file=flow['review']['business']['tasks']['path']
                    if task_file not in business_edit['paths']:paths.add(task_file)
                if workflow and recipe['phase']!='scope-invalidation' and flow['review'].get('business',{}).get('spec'):
                    paths.add(flow['review']['business']['spec']['path'])
                for layer in live_config.get('layers',[]):
                    source=layer.get('name',layer.get('source')) or {}
                    if source.get('file'):paths.add(source['file'])
                for key in ('model_instructions_file','experimental_compact_prompt_file'):
                    if live_config['config'].get(key):paths.add(live_config['config'][key])
                instructions=expected['instructionSources']
                if not isinstance(instructions,list) or any(not Path(p).is_file() for p in instructions):raise RuntimeError('Missing actual instruction file identity')
                contract=binding.get('setup_artifact_contract')
                prospective=binding.get('prospective_setup_contract') if workflow and flow['setup'] else None
                if workflow and flow['setup'] and not prospective:raise RuntimeError('HELD missing prospective setup contract')
                if prospective:
                    if prospective.get('schema')!='prospective-setup-contract-v1':raise RuntimeError('HELD prospective contract version')
                    if prospective.get('setup_USER_provenance'):
                        if prospective.get('prior_usage')!=recipe['usage']:raise RuntimeError('HELD prospective actual USER usage chain')
                        original=workflow_user_evidence(prospective['setup_USER_provenance'],recipe['usage'],root)
                        if original.get('text')!=prospective['setup_user_text'] or not original['text'].startswith('$ains-setup '):raise RuntimeError('HELD original named setup USER provenance')
                protected=[]
                if contract or prospective:
                    selected=contract or prospective
                    if (selected.get('recipe_sha256')!=sha(prepared/'recipe.json') or selected.get('manifest_sha256')!=sha(manifest) or
                        selected.get('proof_sha256')!=binding['proof_sha256'] or selected.get('release_id')!=args.release_id or
                        (prospective and (selected.get('root')!=str(root) or set(selected.get('preserve',{}))!=set(SETUP_SLOTS)))):
                        raise RuntimeError('UNVERIFIED setup contract source/recipe/release binding')
                    slot_paths={str(root/name) for name in SETUP_SLOTS}
                    protected=list(paths)+[p for p in instructions if p not in slot_paths]
                    protected+=[str(Path(__file__)),str(manifest),binding['proof_path']]
                    protected += [str(SOURCE/'tests/runtime/codex'/(name+'.py')) for name in HELPERS]
                    protected += [str(AUDIT/'sources'/name) for name,_,_,_ in DEFAULT_SOURCE_PROOFS]
                    protected += [str(SOURCE/name) for name in json.loads(manifest.read_text())['suite_files']]
                    protected += [str(p) for x in installed for p in Path(x['path']).parent.rglob('*') if p.is_file()]
                    paths.update(slot_paths)
                business_samples=[];business_current=business_edit['initial'] if business_edit else None
                if business_edit:flow.update(business_samples=business_samples,business_facts=[])
                closure_bundle_count=0
                def bundle(closure_phase=None):
                    nonlocal closure_bundle_count
                    if closure and (closure_bundle_count>=5 or closure_phase!=('preflight','post-start-1','post-start-2','predispatch','postterminal')[closure_bundle_count]):raise RuntimeError('HELD closure unexpected bundle phase')
                    closure_before=workflow_inventory(root) if closure else None
                    closure_start=len(rpc.log)
                    if closure:
                        target=(root/closure['draft_path']).resolve();identity=(root/closure['draft_path']).stat()
                        for candidate in paths|set(instructions):
                            p=Path(candidate)
                            if p.resolve()==target or p.is_file() and (p.stat().st_dev,p.stat().st_ino)==(identity.st_dev,identity.st_ino):raise RuntimeError('HELD closure draft immutable instruction/source/alias collision')
                    business_before=notification_business_sample(business_edit,paths|set(instructions)) if business_edit else None
                    slots=setup_slots(root,protected) if contract or prospective else None
                    scope=setup_scope(root) if contract or prospective else None
                    result,config=live_bundle(rpc,root,installed,paths,manifest,helpers,live_binding,instructions,**({'business_edit':business_edit} if business_edit else {}))
                    if closure:
                        closure_after=workflow_inventory(root)
                        if closure_before!=closure_after:raise RuntimeError('HELD unstable closure state within bundle')
                        frame_path=out/('workflow-closure-bundle-%03d.json'%closure_bundle_count);retain(frame_path,result)
                        write(out/('workflow-closure-sample-%03d.json'%closure_bundle_count),{'schema':'spec-closure-sample-v2','bundle_id':closure_bundle_count,'phase':closure_phase,'frame':{'path':str(frame_path),'sha256':sha(frame_path)},'before':closure_before,'after':closure_after,'stable':True,'process_id':rpc.p.pid,'thread_id':rpc.bound_thread,'wire_start_index':closure_start,'wire_end_index':len(rpc.log)})
                        closure_bundle_count+=1
                    if business_edit:
                        business_after=notification_business_sample(business_edit,paths|set(instructions))
                        sample={'schema':'workflow-business-sample-v1','contract':business_edit['reference'],'before':business_before,'after':business_after,'stable':business_before==business_after}
                        sample_path=out/('business-sample-%03d.json'%(len(business_samples)+1));write(sample_path,sample);business_samples.append({'path':str(sample_path),'sha256':sha(sample_path)})
                        if business_before!=business_after:raise RuntimeError('HELD unstable business sampling within bundle')
                    if contract or prospective:
                        after_slots=setup_slots(root,protected);after_scope=setup_scope(root)
                        if slots!=after_slots or scope!=after_scope:raise RuntimeError('Unstable setup artifacts within probe bundle')
                        result.update(setup_slots=after_slots,setup_scope=after_scope)
                    return result,config
                pre_bundle,pre_config=bundle('preflight' if closure else None);user_before=user_config()
                if business_edit:
                    write(out/'business-path-roles-v1.json',{'schema':'workflow-business-path-roles-v1','contract':business_edit['reference'],
                        'business_paths':sorted(business_edit['paths']),'caller_immutable_paths':sorted(paths),'instruction_paths':instructions,
                        'raw_config_paths':sorted(second['files']),'protected_preimage_paths':flow['protected'],
                        'immutable_sample_paths':sorted(pre_bundle['files']),
                        'implicit_immutable_paths':sorted(set(pre_bundle['files'])-set(paths)-set(instructions))})
                if policy:flow['finite_lookup_input']['failure_stage']='before-thread'
                no_write=None
                if binding.get('unchanged_startup'):
                    no_write=bind_startup_no_write(binding['unchanged_startup'],pre_config,root,trust_root,prepared/'recipe.json',manifest,binding)
                request={'cwd':str(root),'model':'gpt-6.1-sol','approvalPolicy':'never','sandbox':'workspace-write','ephemeral':True}
                start_wire=len(rpc.log)
                actual=rpc.call('thread/start',request)
                if policy:flow['finite_lookup_input']['failure_stage']='after-thread'
                thread=actual['thread']['id'];rpc.bound_thread=thread
                retain(out/'thread-start-v3.json',{'schema_version':RECEIPT_VERSION,'process_id':rpc.p.pid,
                    'request':request,'response':redacted_config(actual),'wire_start_index':start_wire,'wire_end_index':len(rpc.log)})
                snapshot=reconcile_thread(actual,request,expected,live_config['config'])
                post_one,post_config=bundle('post-start-1' if closure else None)
                diagnostic={'schema_version':RECEIPT_VERSION,'preflight':pre_bundle,'post_start':post_one,
                            'startup_raw_equal':pre_bundle['files']==post_one['files'] and pre_bundle['config']==post_one['config'],
                            'historical_raw_stability':'UNVERIFIED; no historical reconstruction'}
                retain(out/'startup-diagnostic-v3.json',diagnostic)
                if no_write is not None:
                    no_write['after']=startup_lookup(post_config,root,trust_root)
                    diagnostic['no_write_lookup']=no_write
                    retain(out/'startup-diagnostic-v3.json',diagnostic)
                diagnostic['classified_relation']=(validate_no_write_startup if no_write is not None else validate_startup)(pre_config,post_config,pre_bundle['files'],post_one['files'],trust_root,user_path,user_before,user_config(),**({'no_write':no_write} if no_write is not None else {}))
                retain(out/'startup-diagnostic-v3.json',diagnostic)
                post_two,post_two_config=bundle('post-start-2' if closure else None)
                if no_write is not None:
                    diagnostic['post_bundle_lookup']=startup_lookup(post_two_config,root,trust_root)
                    retain(out/'startup-diagnostic-v3.json',diagnostic)
                    if diagnostic['post_bundle_lookup']!=no_write['before']:raise RuntimeError('HELD post-bundle startup lookup drift')
                if policy:flow['finite_lookup_input']['failure_stage']='predispatch'
                baseline=PostStartBaseline(post_one,post_two)
                if business_edit and any(checked_json(ref)['after']!=business_current for ref in business_samples):raise RuntimeError('HELD business state changed before first USER')
                prospective_state=workflow_inventory(root,protected,True) if prospective else None
                if prospective:
                    for name,spans in prospective['preserve'].items():
                        body=bytes.fromhex(post_one['setup_slots'][name]['bytes_hex'] or '')
                        if not isinstance(spans,list) or any(not isinstance(span,str) or span.encode() not in body for span in spans):raise RuntimeError('HELD prospective prebound preservation span')
                edge=SetupArtifactEdge(post_one,contract,root,row['id'],baseline) if contract else None
                if edge:write(out/'setup-artifact-contract-v1.json',{'contract':edge.contract,'B0_sha256':canonical_hash(post_one),'process_id':rpc.p.pid,'thread_id':thread})
                if business_edit:
                    flow['business_samples']=business_samples
                    for name in business_edit['entries']:
                        if (root/name).is_file():
                            target=out/'business-initial'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((root/name).read_bytes())
                actual_history=[]
                selector_receipt=native_selection_receipt(binding,post_two['catalog_proof'],require_environment(post_two['environment'],binding),'live')
                retain(out/'poststart-baseline-v3.json',{'schema_version':RECEIPT_VERSION,'snapshot':snapshot,
                    'first':post_one,'second':post_two,'wire_end_index':len(rpc.log),
                    'relation':'finite sampled config/catalog/source/environment; not atomic internal turn state'})
                print(json.dumps({'ready_for_real_USER_input':True,'thread':thread,'initial_required':row['initial_user_text']}),flush=True)
                def retain_business_interval():
                    ref=flow['business_facts'][-1];fact=checked_json(ref)
                    fact['wire_end_index']=len(rpc.log)
                    interval=rpc.log[fact['wire_start_index']:]
                    raw_events=[e['payload'] for e in interval if e['direction']=='response_or_event']
                    pending=set()
                    for entry in interval:
                        payload=entry['payload']
                        if entry['direction']=='response_or_event' and 'id' in payload and 'method' in payload:pending.add(payload['id'])
                        if entry['direction']=='request' and 'id' in payload and 'result' in payload:pending.discard(payload['id'])
                    if pending or not healthy_terminal(raw_events,'live'):raise RuntimeError('HELD unhealthy/pending business interval before next USER')
                    fact['events']=ar.sanitized(raw_events)
                    write(ref['path'],fact);ref['sha256']=sha(ref['path'])
                def ordinary_inputs():
                    while True:
                        if business_edit and flow['business_facts']:
                            released_source(manifest)
                            before_input,_=bundle();baseline.check(before_input)
                            if checked_json(business_samples[-1])['after']!=business_current:raise RuntimeError('HELD business state changed before next USER read')
                            prior_events=[e['payload'] for e in rpc.log[wire_start:] if e['direction']=='response_or_event']
                            if not healthy_terminal(prior_events,'live'):raise RuntimeError('Unhealthy prior terminal before next USER read')
                            pending=set()
                            for entry in rpc.log[wire_start:]:
                                payload=entry['payload']
                                if entry['direction']=='response_or_event' and 'id' in payload and 'method' in payload:pending.add(payload['id'])
                                if entry['direction']=='request' and 'id' in payload and 'result' in payload:pending.discard(payload['id'])
                            if pending:raise RuntimeError('HELD business pending request before next USER read')
                            retain_business_interval()
                        try:line=next(sys.stdin)
                        except StopIteration:return
                        yield line
                for number,line in enumerate(ordinary_inputs(),1):
                    if number>row['max_user_turns']:raise RuntimeError('Released row turn bound exhausted')
                    text=json.loads(line)['text']
                    if workflow and recipe['purpose']=='setup-ack-repeat':
                        expected_workflow_inputs=[recipe['setup_content_ack_text'],recipe['setup_repeat_text']]
                        if text!=expected_workflow_inputs[number-1]:raise RuntimeError('HELD exact prospective acknowledgement then original repeat required')
                    if continuation:
                        expected_inputs=[recipe['setup_repeat_text']] if continuation.get('pending_repeat_ack') else [recipe['setup_content_ack_text'],recipe['setup_repeat_text']]
                        if number>len(expected_inputs) or text!=expected_inputs[number-1]:raise RuntimeError('Continuation permits only actual new acknowledgment then exact original setup repeat')
                    if number==1 and text!=row['initial_user_text']:raise RuntimeError('Initial prompt differs from reviewed recipe')
                    actual_history.append({'role':'user','text':text})
                    if current_author and current_author_inventory(root)!=author_checkpoint['inventory']:raise RuntimeError('HELD current-author state changed before dispatch')
                    if workflow and number==1 and workflow_inventory(root,flow['protected'],flow['setup'])!=flow['checkpoint']['state']:raise RuntimeError('HELD workflow state changed before first USER')
                    if workflow:write(out/('workflow-before-%02d.json'%number),workflow_inventory(root,flow['protected'],flow['setup']))
                    released_source(manifest);before_turn=rt.snapshot(root)
                    turn_bundle,_=bundle('predispatch' if closure else None)
                    retain(out/('before-config-%02d-v3.json'%number),turn_bundle)
                    baseline.check(turn_bundle)
                    if business_edit and checked_json(business_samples[-1])['after']!=business_current:raise RuntimeError('HELD business state changed between healthy turns')
                    if current_author and current_author_inventory(root)!=author_checkpoint['inventory']:raise RuntimeError('HELD current-author state changed during predispatch bundle')
                    if workflow and number==1 and workflow_inventory(root,flow['protected'],flow['setup'])!=flow['checkpoint']['state']:raise RuntimeError('HELD workflow state changed within first bundle')
                    if number>1:
                        previous_path=out/('turn-%02d.json'%(number-1))
                        previous=json.loads(previous_path.read_text())
                        drained=[entry['payload'] for entry in rpc.log[wire_start:] if entry['direction']=='response_or_event']
                        previous['events']=drained;previous['wire_end_index']=len(rpc.log)
                        retain(previous_path,previous)
                        if not healthy_terminal(drained,'live'):raise RuntimeError('Unhealthy prior terminal before next USER launch')
                        if business_edit:retain_business_interval()
                    wire_start=len(rpc.log)
                    events=[];start=time.monotonic();deadline=start+current_author_seconds(row,current_author);rpc.events=[]
                    try:
                        if policy:flow['finite_lookup_input']['failure_stage']='dispatched'
                        try:turn_reply=rpc.call('turn/start',{'threadId':thread,'input':[{'type':'text','text':text}]},timeout=30)
                        finally:
                            if workflow and (flow.get('build_posttimeout_handoff') or flow.get('spec_closure')):
                                pending=[entry['payload'] for entry in rpc.log[wire_start:] if entry['direction']=='response_or_event' and 'id' in entry['payload'] and 'method' in entry['payload']]
                                if not pending:pending=[event for event in rpc.events if 'id' in event and 'method' in event]
                                if pending:
                                    retain(out/('pending-%02d.json'%number),pending)
                                    raise RuntimeError('HELD closure queued request; no second USER' if flow.get('spec_closure') else 'HELD BUILD posttimeout queued request; no second USER')
                        events+=rpc.events
                        if time.monotonic()>=deadline:raise TimeoutError('Absolute terminal deadline exceeded during turn/start')
                        if workflow and flow.get('tasks_timeout_handoff') is not None:
                            pending=[event for event in events if 'id' in event and 'method' in event]
                            if pending:
                                retain(out/('pending-%02d.json'%number),pending)
                                raise RuntimeError('HELD TASKS handoff structured request; no second USER')
                        while True:
                            event=rpc.next(deadline);events.append(event)
                            if time.monotonic()>=deadline:raise TimeoutError('Absolute terminal deadline exceeded')
                            if 'id' in event and 'method' in event:
                                retain(out/('pending-%02d.json'%number),event)
                                if workflow and (flow.get('build_posttimeout_handoff') or flow.get('spec_closure')):raise RuntimeError('HELD closure structured request; no second USER' if flow.get('spec_closure') else 'HELD BUILD posttimeout structured request; no second USER')
                                if workflow and flow.get('tasks_timeout_handoff') is not None:raise RuntimeError('HELD TASKS handoff structured request; no second USER')
                                if current_author:
                                    write(out/'current-author-pending-v1.json',{'status':'HELD_UNFINISHED_STRUCTURED_REQUEST','request':event,'authorizes_answer':False,'release_sha256':author_checkpoint['current_release_sha256']})
                                    raise RuntimeError('HELD current-author structured request preserved; no second USER/implicit authority')
                                if event['method']!='item/tool/requestUserInput':raise RuntimeError('Unsupported/approval request: preserved; no implicit authority')
                                questions=event.get('params',{}).get('questions',[])
                                if not questions or len(questions)>5:raise RuntimeError('Question UI capacity/local rule violation')
                                print(json.dumps({'actual_USER_response_required':event['id'],'request_artifact':str(out/('pending-%02d.json'%number))}),flush=True)
                                if not rt.select.select([sys.stdin],[],[],max(0,deadline-time.monotonic()))[0]:raise TimeoutError('Actual USER UI response deadline exceeded')
                                response=json.loads(sys.stdin.readline())
                                if response.get('request_id')!=event['id'] or 'result' not in response:raise RuntimeError('Mismatched actual USER response')
                                retain(out/('user-ui-response-%02d.json'%number),{'role':'user','response':response})
                                actual_history.append({'role':'user','request_id':event['id'],'response':response})
                                rpc.send({'id':event['id'],'result':response['result']})
                            if event.get('method')=='turn/completed':
                                if event.get('params',{}).get('turn',{}).get('status')!='completed':raise RuntimeError('Non-success terminal')
                                break
                    finally:
                        if not events:events.extend(rpc.events)
                        retain(out/('turn-%02d.json'%number),{'role':'user','text':text,'thread':thread,'events':events,'seconds':time.monotonic()-start,'before':before_turn,'after':rt.snapshot(root)})
                    if not healthy_terminal(events,'live'):raise RuntimeError('Incomplete/unhealthy live terminal event set')
                    try:
                        after_bundle,_=bundle('postterminal' if closure else None)
                        if business_edit:
                            after_business=checked_json(business_samples[-1])['after']
                            write(out/('config-%02d.json'%number),{'schema_version':'workflow-business-bundle-v2','immutable_before':ar.sanitized(turn_bundle),'immutable_after':ar.sanitized(after_bundle),
                                'immutable_stable':turn_bundle==after_bundle,'business_before':business_current,'business_after':after_business,
                                'business_files_equal':business_current==after_business,'full_observed_files_equal':turn_bundle==after_bundle and business_current==after_business,
                                'contract':business_edit['reference'],'baseline_reset_allowed':False})
                        else:
                            retain(out/('config-%02d.json'%number),{'schema_version':RECEIPT_VERSION,
                                'before':turn_bundle,'after':after_bundle,'raw_stable':turn_bundle==after_bundle,
                                'projection_used':False,'baseline_reset_allowed':False})
                        if not prospective and (not edge or edge.unchanged(after_bundle)):baseline.check(after_bundle)
                        if prospective and json.dumps(after_bundle,sort_keys=True)==json.dumps(post_one,sort_keys=True):baseline.check(after_bundle)
                    finally:
                        # config/read and skills/list may drain late lifecycle events.
                        # Keep them in both the raw wire and this complete turn view,
                        # even when post-turn validation fails.
                        events=[entry['payload'] for entry in rpc.log[wire_start:] if entry['direction']=='response_or_event']
                        retain(out/('turn-%02d.json'%number),{'role':'user','text':text,'thread':thread,'events':events,'seconds':time.monotonic()-start,'before':before_turn,'after':rt.snapshot(root),'wire_start_index':wire_start,'wire_end_index':len(rpc.log)})
                    if not healthy_terminal(events,'live'):raise RuntimeError('Unhealthy terminal after config/catalog drains; stop before next USER')
                    if workflow:
                        if recipe['phase'] not in ('build','AC9-handoff'):
                            current_state=workflow_inventory(root,flow['protected'],flow['setup'])
                            def business_source(state):return {k:v for k,v in state.items() if (Path(k).parts or ('',))[0] in ('app','tests') and k.endswith('.py')}
                            if business_source(current_state)!=business_source(flow['checkpoint']['state']):raise RuntimeError('HELD business implementation outside approved build/AC9 phase')
                        if recipe['purpose']=='original-notification-draft':
                            draft=Path(flow['review']['business']['draft']['path'])
                            if not draft.read_text().startswith('---\nstatus: draft\n---'):raise RuntimeError('HELD original spec must remain unapproved')
                            original=SOURCE/'tests/evals/ains-spec/new-feature-stops-at-spec-gate/files'
                            if any(sha(root/name)!=sha(original/name) for name in ('app/settings.py','app/notifier.py','app/__init__.py','tests/test_settings.py','tests/__init__.py')):raise RuntimeError('HELD original draft case cannot implement source')
                        pending=set()
                        for entry in rpc.log:
                            payload=entry['payload']
                            if entry['direction']=='response_or_event' and 'id' in payload and 'method' in payload:pending.add(payload['id'])
                            if entry['direction']=='request' and 'id' in payload and 'result' in payload:pending.discard(payload['id'])
                        if pending:
                            if flow.get('build_posttimeout_handoff') or flow.get('spec_closure'):retain(out/('pending-%02d.json'%number),[entry['payload'] for entry in rpc.log if entry['direction']=='response_or_event' and entry['payload'].get('id') in pending])
                            raise RuntimeError('HELD workflow unfinished request after drains')
                        if flow.get('build_posttimeout_handoff') and not any(event.get('method')=='item/completed' and event.get('params',{}).get('item',{}).get('type')=='agentMessage' and event['params']['item'].get('phase')=='final_answer' for event in events):
                            raise RuntimeError('HELD BUILD verification has no completed final report')
                        if business_edit:
                            try:business_observation=notification_business_delta(business_edit,business_current,after_business)
                            except RuntimeError as error:
                                write(out/('business-held-%02d.json'%number),{'contract':business_edit['reference'],'before':business_current,'current':after_business,'events':events,'reason':str(error),'business_PASS':False})
                                raise
                        if closure:
                            returned_turn=turn_reply.get('turn',{}).get('id') if isinstance(turn_reply,dict) else None
                            if not isinstance(returned_turn,str) or not returned_turn:raise RuntimeError('HELD closure returned turn identity')
                            for observed in events:
                                method=observed.get('method','');params=observed.get('params',{})
                                if method.startswith(('turn/','item/')):
                                    observed_turn=params.get('turn',{}).get('id') if method in ('turn/started','turn/completed') else params.get('turnId')
                                    if params.get('threadId')!=thread or observed_turn!=returned_turn:raise RuntimeError('HELD closure foreign lifecycle ownership')
                            if not any(event.get('method')=='item/completed' and event.get('params',{}).get('item',{}).get('type')=='agentMessage' and event['params']['item'].get('phase')=='final_answer' and isinstance(event['params']['item'].get('text'),str) and event['params']['item']['text'].strip() for event in events):raise RuntimeError('HELD closure missing eligible final')
                            state=workflow_inventory(root);before=flow['checkpoint']['state'];draft=closure['draft_path']
                            image=out/'closure-draft-postimage.md';image.write_bytes((root/draft).read_bytes())
                            write(out/'workflow-closure-postimage.json',{'schema':'spec-closure-postimage-v1','draft':draft,'state_sha256':canonical_hash(state),'postimage':{'path':str(image),'sha256':sha(image)},'before':before,'after':state,'business_PASS':False})
                            if (set(state)!=set(before) or any(before[k]!=state[k] for k in before if k!=draft) or
                                {k:v for k,v in before[draft].items() if k not in ('sha256','identity')}!={k:v for k,v in state[draft].items() if k not in ('sha256','identity')} or not image.read_bytes().startswith(b'---\nstatus: draft\n---')):raise RuntimeError('HELD closure draft-only/unapproved state')
                        write(out/('workflow-state-%02d.json'%number),workflow_inventory(root,flow['protected'],flow['setup']))
                        if prospective and json.dumps(after_bundle,sort_keys=True)!=json.dumps(post_one,sort_keys=True):
                            try:
                                workflow_observation=workflow_setup_observation(post_one,after_bundle,prospective_state,workflow_inventory(root,protected,True),events,actual_history,prospective)
                            except RuntimeError as error:
                                workflow_observation={'schema':'prospective-setup-held-facts-v1','reason':str(error),'authorizes_dispatch':False,
                                    'baseline':post_one,'terminal':after_bundle,'initial_state':prospective_state,'state':workflow_inventory(root,protected,True),
                                    'events':events,'user_history':actual_history,'contract':prospective}
                                write(out/'prospective-setup-output.json',workflow_observation)
                                raise
                            write(out/'prospective-setup-output.json',workflow_observation)
                            if recipe['purpose']=='setup-ack-repeat':raise RuntimeError('FAIL changed prospective setup acknowledgement/repeat; idempotence not established')
                            workflow_healthy=True
                            break
                    if current_author and any('id' in e and 'method' in e for e in events):
                        write(out/'current-author-pending-v1.json',{'status':'HELD_UNFINISHED_STRUCTURED_REQUEST_AFTER_DRAIN','events':events,'authorizes_answer':False})
                        raise RuntimeError('HELD current-author unfinished request after drains')
                    retain(out/('native-oracle-%02d.json'%number),native_oracle(events,text,bodies,installed_paths,selector_bound=selector_receipt))
                    if business_edit:
                        images={}
                        for name in business_edit['entries']:
                            if (root/name).is_file():
                                target=out/('business-postimage-%02d'%number)/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((root/name).read_bytes());images[name]={'path':str(target),'sha256':sha(target)}
                        business_observation.update(schema='workflow-notification-business-observation-v2',contract=business_edit['reference'],events=ar.sanitized(events),user_history=actual_history.copy(),postimages=images,
                            wire_start_index=wire_start,wire_end_index=len(rpc.log),process_id=rpc.p.pid,thread_id=thread)
                        path=out/('business-observation-%02d.json'%number);write(path,business_observation);flow['business_facts'].append({'path':str(path),'sha256':sha(path)})
                        business_current=after_business
                        if business_observation['git_candidate']:
                            workflow_healthy=True
                            break
                    if edge and not edge.unchanged(after_bundle):
                        try:
                            checkpoint=edge.terminal(after_bundle,events,actual_history)
                        except RuntimeError as error:
                            # Preserve failed stable terminal facts, not eligibility.
                            # Re-raise after finally closes; never clear a latch/retry.
                            checkpoint={'schema':'setup-terminal-held-facts-v2','status':'HELD_TERMINAL_CLASSIFICATION_FAILED',
                                'reason':str(error),'baseline':edge.baseline,'terminal':after_bundle,'contract':edge.contract,
                                'events':events,'user_history':actual_history,'process_id':rpc.p.pid,'thread_id':thread,
                                'wire_start_index':wire_start,'wire_end_index':len(rpc.log),'raw_stable':False,'authorizes_dispatch':False}
                            write(out/'observed-terminal-held-facts-v2.json',checkpoint)
                            raise
                        checkpoint.update(source_recipe_sha256=sha(prepared/'recipe.json'),protected_paths=protected,
                            process_id=rpc.p.pid,thread_id=thread,wire_start_index=wire_start,wire_end_index=len(rpc.log),
                            predecessor=continuation)
                        write(out/'observed-setup-output-v1.json',checkpoint)
                        retain(out/'layout-after.json',layout(root))
                        # No next input/dispatch in this context. finally closes
                        # the actual process before making a C1 checkpoint.
                        return
                    print(json.dumps({'completed_user_turn':number,'artifact':str(out/('turn-%02d.json'%number))}),flush=True)
                    if workflow:
                        workflow_healthy=True
                        if number==row['max_user_turns']:break
                    if continuation and number==len(expected_inputs):break
                    if current_author:
                        write(out/'current-author-post-inventory-v1.json',current_author_inventory(root))
                        write(out/'current-author-observation-v1.json',{'status':'OBSERVED_CURRENT_AUTHOR_TERMINAL_REQUIRES_PARENT_REVIEW','release_sha256':author_checkpoint['current_release_sha256'],
                            'prior_body_event_index':28,'ordinary_read_is_not_injection':True,'business_PASS':False,'authority_granted':False,'actual_USER_count':1,'process_id':rpc.p.pid,'thread_id':thread})
                        break
            finally:
                if workflow:close_workflow_context(rpc,out,recipe,args,flow,workflow_observation,workflow_healthy and sys.exc_info()[0] is None)
                elif checkpoint is not None:close_setup_checkpoint(rpc,checkpoint,out/('setup-checkpoint-v1.json' if checkpoint['schema']=='setup-artifact-checkpoint-v1' else 'setup-terminal-held-facts-v2.json'))
                else:
                    rpc.close()
                    if current_author:
                        write(out/'current-author-closure-v1.json',{'process_id':rpc.p.pid,'server_returncode':rpc.p.poll(),
                            'closed_receipt':str(out/'live-rpc/closed.json'),'release_sha256':author_checkpoint['current_release_sha256']})
                        if rpc.p.poll() is None or not (out/'live-rpc/closed.json').is_file():raise RuntimeError('HELD current-author process closure unverified')
        released_source(manifest);after=metadata_sample() if policy else a.probe(root);after_inventory=a.inventory(root)
        retain(out/'raw-structural.json',{'before':second,'after':after,'raw_stable':second==after,'ordinary_consumption_is_not_a_native_stop':True})
        if row['transport']=='cli':
            post_rpc=recorded_rpc(rt,ar,root,overrides,out/'post-catalog-rpc',binding)
            try:
                post_cfg=post_rpc.call('config/read',{'includeLayers':True,'cwd':str(root)},timeout=30)
                post_facts=config_facts(post_cfg,helpers['activation_closure_probe'].structural)
                post_catalog=post_rpc.call('skills/list',{'cwds':[str(root)],'forceReload':True},timeout=30)
                post_catalog_proof=validate_catalog(post_catalog,after_inventory,post_facts,'cli')
            finally:post_rpc.close()
            retain(out/'post-native-selection-receipt.json',native_selection_receipt(binding,post_catalog_proof,environment_proof,'cli'))
            visible=[k for k in launch if k!='environment_identity_sha256']
            if not all(rec.get(k)==launch[k] for k in visible) or a.launch_receipt(root,row['initial_user_text'],overrides)!=launch:raise RuntimeError('Actual CLI launch/environment receipt mismatch')
            final=a.comparison_input(after,a.applied_probe(root,overrides,after['all_layer_mcp_names']),after_inventory,sha(manifest))
            comparison=a.compare_activation_inputs(bound,final,launch,Path.home()/'.codex/config.toml')
            comparison['external_0164_semantic_binding']={'commit':SEMANTIC_COMMIT,'proof_sha256':binding['proof_sha256'],'old_helper_label_preserved':True}
            retain(out/'postcomparison.json',comparison)
            if not comparison['projected_stable']:raise RuntimeError('CLI pre/post source-bound projection failed')
        retain(out/'layout-after.json',layout(root))
        if after_inventory!=installed:raise RuntimeError('Installed provenance drift')


def make_review_packet(workflow_out,packet_out,manifest=RELEASE,packet_contract=None):
    """Only usable after an ACTUAL released workflow; no prepared-base substitute."""
    released_source(manifest)
    if (Path(workflow_out)/'workflow-context.json').is_file():
        if not packet_contract:raise RuntimeError('HELD --packet post-closure notification contract required')
        return make_notification_review_packet(Path(workflow_out)/'workflow-context.json',packet_out,manifest,packet_contract)
    if packet_contract:raise RuntimeError('HELD notification contract does not apply to legacy toy exporter')
    workflow_out=Path(workflow_out).resolve();record=json.loads((workflow_out/'release.json').read_text())
    if record['row']['id']!='copy-workflow' or not record.get('actual_parent_release_id'):raise RuntimeError('Actual released copy workflow required')
    root=Path(record['root']).resolve()
    if root==SOURCE or SOURCE in root.parents or root in SOURCE.parents:raise RuntimeError('Consumer must be outside source ancestors')
    if record['release_sha256']!=sha(manifest):raise RuntimeError('Workflow source release mismatch')
    specs=list((root/'docs/changes').glob('*/spec.md'))
    if len(specs)!=1:raise RuntimeError('One actual workflow spec required')
    out=Path(packet_out).resolve();out.mkdir(parents=True,exist_ok=False)
    with bound_helpers(out/'helper-sink') as (helpers,imports):
        rt=helpers['runtime']
        diff=subprocess.run(['git','diff','--no-ext-diff','--no-textconv','fixture-baseline','--','calc.py','tests/test_calc.py'],cwd=root,stdin=subprocess.DEVNULL,capture_output=True,timeout=30)
        if diff.returncode or not diff.stdout:raise RuntimeError('Actual baseline diff missing')
        (out/'diff.patch').write_text(rt.clean(diff.stdout.decode()))
        shutil.copyfile(specs[0],out/'spec.md');shutil.copyfile(root/'calc.py',out/'calc.py')
        shutil.copytree(root/'tests',out/'tests',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        brief=root/'.agents/skills/ains-review/review-prompt.md';shutil.copyfile(brief,out/'review-prompt.md')
        # Preserve actual task completion evidence without the author conversation.
        if (specs[0].parent/'tasks.md').exists():shutil.copyfile(specs[0].parent/'tasks.md',out/'tasks.md')
        command=['python3','-B','-m','unittest','discover','-s','tests','-v']
        check=subprocess.run(command,cwd=root,stdin=subprocess.DEVNULL,capture_output=True,timeout=30)
        (out/'checks.txt').write_text(rt.clean((check.stdout+check.stderr).decode()))
        hashes={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}
        write(out/'review-packet-manifest.json',{'actual_workflow_out':str(workflow_out),'root':str(root),'source_spec_sha256':sha(specs[0]),'source_review_brief_sha256':sha(brief),'check_argv':command,'check_exit':check.returncode,'files':hashes,'author_conversation_included':False,'source_release_sha256':sha(manifest)})
    print(json.dumps({'actual_review_packet':str(out),'files':len(hashes),'checks_exit':check.returncode}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--prepare',action='store_true');mode.add_argument('--run',action='store_true');mode.add_argument('--make-review-packet',action='store_true');mode.add_argument('--recover-c0',metavar='REQUEST_JSON')
    parser.add_argument('--manifest');parser.add_argument('--out');parser.add_argument('--prepared');parser.add_argument('--row');parser.add_argument('--release-id');parser.add_argument('--packet');parser.add_argument('--workflow-out');parser.add_argument('--native-binding');parser.add_argument('--setup-checkpoint');parser.add_argument('--setup-checkpoint-review');parser.add_argument('--derivative-release');parser.add_argument('--current-author-checkpoint');parser.add_argument('--current-author-release')
    args=parser.parse_args()
    if args.recover_c0:
        if not args.out:parser.error('--recover-c0 requires a fresh --out evidence directory')
        out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=False)
        derivative=recover_frozen_c0(json.loads(Path(args.recover_c0).read_text()))
        write(out/'derivative-observation-v1.json',derivative)
        print(json.dumps({'status':derivative['status'],'artifact':str(out/'derivative-observation-v1.json'),'model_calls':0}))
    elif args.make_review_packet:
        if not args.workflow_out or not args.out:parser.error('--make-review-packet requires --workflow-out --out')
        make_review_packet(args.workflow_out,args.out,args.manifest or RELEASE,args.packet)
    elif args.run:
        if not all([args.out,args.prepared,args.row,args.release_id]):parser.error('--run requires --prepared --row --out --release-id')
        run_row(args)
    elif args.prepare:
        prepare(Path(args.out).resolve() if args.out else EVIDENCE/'prepare',args.manifest or RELEASE)
    else: print('PREP ONLY by default; no models or install. Use --prepare --out NEW_PATH.')


if __name__=='__main__':main()
