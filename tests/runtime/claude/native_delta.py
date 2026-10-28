#!/usr/bin/env python3
"""Native AC4 delta adapter. Default/--prepare is model-free; no legacy driver import.

--prepare freezes a concrete recipe, not runtime acceptance. --collect-one is an
implemented single-session primitive for AFTER explicit parent release/acceptance;
it requires a materialized consumer and a reviewed row, never fabricates fixtures
or replies. Fixture/chain steps are explicit in the prepared recipe.
"""
import argparse
import ast
import hashlib
import json
import os
import pathlib
import re
import subprocess
import tempfile
import time
import types
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve()
PREP = ROOT / '.omx/ultragoal/evidence/g004/claude/native-v1/prepare'
RELEASE = ROOT / '.omx/ultragoal/evidence/source-repair-r5/manifest.json'
USER_REPLY_WAIT_SECONDS = 600
AMENDMENT = ROOT / '.omx/plans/ac4-native-invocation-amendment.md'
COVERAGE = ROOT / '.omx/ultragoal/evidence/ac4-native-amendment/coverage.json'
AMENDMENT_SHA = 'c51eb2459621d9acac9cb02aae13e7769801e5bdf85854d462dbd5a8ce64a2c9'
COVERAGE_SHA = '82456af43cd5b4844e49199f78b9a8d1871261e24c713ea7b2b81648ce43483c'
MANUAL = frozenset(['ains','ains-build','ains-harness','ains-retro','ains-setup','ains-ship','ains-spec','ains-tasks','ains-team-canvas','ains-tool-access'])
AUTO = frozenset(['ains-context-care','ains-grilling','ains-release-safety','ains-review','ains-review-gate','ains-tdd'])
ORIGINALS = [
 'ains-spec/new-feature-stops-at-spec-gate',
 'ains-build/bugfix-reproduces-first-and-stays-in-scope',
 'ains-build/build-stops-when-plan-is-draft',
 'ains-build/build-stops-when-plan-has-no-status',
 'ains-review-gate/merge-request-with-migration-goes-to-human',
]
STANDARD = frozenset(['hashlib','json','os','pathlib','re','signal','subprocess','tempfile','time','selectors','shutil','concurrent.futures','difflib','sys'])


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def dump(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def read(path):
    return json.loads(pathlib.Path(path).read_text())


def load_definitions(path, out, constants=False, bindings=None):
    """Use unchanged helper definitions, excluding fixed OUT/mkdir/main/imports.

    SOURCE and fresh OUT exist in the execution namespace BEFORE any function is
    compiled. No normal import of r3_runtime/suite or fixed-output driver occurs.
    """
    path = pathlib.Path(path)
    tree = ast.parse(path.read_text(), filename=str(path))
    chosen = []
    excluded = []
    literals = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            if all(a.name in STANDARD for a in node.names):
                chosen.append(node)
            else:
                excluded.append({'line':node.lineno,'kind':'non-stdlib import'})
        elif isinstance(node, ast.FunctionDef):
            chosen.append(node)
        elif constants and isinstance(node, ast.Assign):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                excluded.append({'line':node.lineno,'kind':'nonliteral assignment'})
            else:
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id not in ('OUT','SOURCE'):
                        literals[target.id] = value
        else:
            excluded.append({'line':getattr(node,'lineno',None),'kind':type(node).__name__})
    ns = {'__file__':str(path),'__name__':'native_delta_bound_helper','SOURCE':ROOT,'OUT':pathlib.Path(out)}
    ns.update(literals)
    ns.update(bindings or {})
    exec(compile(ast.Module(body=chosen, type_ignores=[]), str(path), 'exec'), ns)
    return types.SimpleNamespace(**ns), {
        'path':str(path),'sha256':sha(path),'normal_import_executed':False,
        'top_level_fixed_OUT_and_mkdir_and_main_excluded':True,
        'excluded_nodes':excluded,'fresh_OUT_bound_before_use':str(out),
        'definitions':[n.name for n in chosen if isinstance(n,ast.FunctionDef)],
    }


def helper(out):
    return load_definitions(HERE.parent/'r3_runtime.py', out)


def source_files():
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'skills').glob('ains*/**/*')) if p.is_file()}


def verify_release(path):
    value = read(path)
    expected = value.get('suite_skill_metadata_sha256')
    if not isinstance(expected,dict) or not expected:
        raise ValueError('Release lacks real suite_skill_metadata_sha256 mapping')
    mismatches = [p for p,h in expected.items() if sha(ROOT/p)!=h]
    for p,v in value.get('suite_files',{}).items():
        if p.startswith('skills/ains') and sha(ROOT/p)!=v['sha256']:
            mismatches.append(p)
    if mismatches:
        raise ValueError('Release source drift: '+', '.join(mismatches))
    return {'path':str(pathlib.Path(path).resolve()),'sha256':sha(path),'release':value.get('release'),
            'skill_metadata':expected,'suite_source_files':source_files()}


def metadata_check():
    manual=set();automatic=set();records={}
    for path in sorted((ROOT/'skills').glob('ains*/SKILL.md')):
        front=path.read_text().split('---',2)[1]
        names=re.findall(r'^name:\s*(\S+)\s*$',front,re.M)
        flags=re.findall(r'^disable-model-invocation:\s*(true|false)\s*$',front,re.M)
        if len(names)!=1 or len(flags)>1 or names[0]!=path.parent.name:
            raise ValueError('Ambiguous skill frontmatter '+str(path))
        name=names[0];disabled=flags==['true']
        (manual if disabled else automatic).add(name)
        adapter=path.parent/'agents/openai.yaml';implicit=None
        if adapter.exists():
            lines=adapter.read_text().splitlines();in_policy=False
            for line in lines:
                if line.strip()=='policy:':in_policy=True;continue
                if line and not line.startswith((' ','#')):in_policy=False
                if in_policy:
                    match=re.fullmatch(r' +allow_implicit_invocation: (true|false)',line)
                    if match:
                        if implicit is not None:raise ValueError('Duplicate implicit policy')
                        implicit=match[1]=='true'
        if disabled and implicit is not False:raise ValueError('Manual adapter mismatch '+name)
        if not disabled and implicit is False:raise ValueError('Automatic adapter disabled '+name)
        records[name]={'manual':disabled,'allow_implicit_invocation':implicit,'body_sha256':sha(path)}
    if manual!=MANUAL or automatic!=AUTO:raise ValueError('Exact 10/6 inventory mismatch')
    return {'manual_names':sorted(manual),'automatic_names':sorted(automatic),'records':records,'kind':'mechanical source metadata only; no runtime PASS'}


def base_argv(write, debug='<private temp logdir>/debug.log'):
    tools='Read,Glob,Grep,Skill,Bash'+(',Edit,Write' if write else '')
    return ['claude','-p','--model','claude-sonnet-5-5','--permission-mode','dontAsk',
            '--permission-prompts','none','--tools',tools,'--allowedTools',tools,
            '--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--setting-sources',
            'project,local','--no-session-persistence','--input-format','stream-json',
            '--output-format','stream-json','--verbose','--replay-user-messages','--debug-file',debug]


def text(content):
    if isinstance(content,str):
        return content
    if isinstance(content,list):
        return '\n'.join(text(x.get('text',x.get('content',''))) for x in content if isinstance(x,dict))
    return ''


def canonical_skill(value):
    if not isinstance(value,str):
        return None
    name=value.strip().lstrip('/').split(':')[-1]
    return name if name in MANUAL|AUTO else None


def native_projection(result, installed, expected_stage=None, negative=False, paired_surface=False):
    """Finite configured CLI oracle; does not classify ordinary reads as native.

    installed[name] binds logical/real/path/hash/text captured from verified trees.
    Only actual assistant Skill tool calls + actual correlated user results/body,
    or CLI replay USER command markers bound to controlled USER input, count N4.
    Rejected attempts and ambiguous/missing outcomes remain separate.
    """
    raw=result.get('all_sanitized_stream_events',[])
    controlled=[x.get('input',{}).get('message',{}).get('content','') for x in result.get('controlled_stdin',[])]
    calls=[];answers={};injections=[];markers=[];reads=[]
    for index,event in enumerate(raw):
        if not isinstance(event,dict):
            continue
        msg=event.get('message',{})
        if not isinstance(msg,dict):
            continue
        content=msg.get('content')
        if event.get('type')=='user' and event.get('isReplay') is True and msg.get('role')=='user' and isinstance(content,str):
            match=re.match(r'^<command-message>([^<]+)</command-message>\s*<command-name>(/[^<]+)</command-name>',content)
            if match:
                name=canonical_skill(match.group(2))
                supplied=any(isinstance(s,str) and re.match(r'^/'+re.escape(name or 'INVALID')+r'(?:\s|$)',s) for s in controlled)
                if name:
                    markers.append({'name':name,'event_index':index,'controlled_literal_match':supplied,
                                    'origin':'actual CLI replay USER command marker'})
        if not isinstance(content,list):
            continue
        for block in content:
            if not isinstance(block,dict):
                continue
            kind=block.get('type')
            if event.get('type')=='assistant' and msg.get('role')=='assistant' and kind=='tool_use':
                if block.get('name')=='Skill':
                    calls.append({'id':block.get('id'),'name':canonical_skill(block.get('input',{}).get('skill')),
                                  'input':block.get('input'),'event_index':index})
                elif block.get('name') in ('Read','Bash'):
                    reads.append({'id':block.get('id'),'tool':block.get('name'),'input':block.get('input',{}),'event_index':index})
            elif event.get('type')=='user' and kind=='tool_result':
                answers[block.get('tool_use_id')]={'error':block.get('is_error') is True,'text':text(block.get('content')),'event_index':index}
            elif event.get('type')=='user' and kind=='text':
                value=block.get('text','')
                if value.startswith('Base directory for this skill: '):
                    line,_,body=value.partition('\n')
                    injections.append({'directory':line.split(': ',1)[1],'body':body.strip(),'event_index':index})
    native=[];provenance=[]
    for call in calls:
        answer=answers.get(call['id']);name=call['name'];bound=installed.get(name)
        record={**call,'outcome':'UNVERIFIED missing native result'}
        if answer and answer['error']:
            record['outcome']='REJECTED_ATTEMPT'
        elif answer:
            candidates=[x for x in injections if x['event_index']>answer['event_index'] and
                        pathlib.Path(x['directory']).name==name]
            if len(candidates)==1 and bound:
                injected=candidates[0]
                expected=bound['text'].split('---',2)[-1].strip()
                logical=pathlib.Path(injected['directory'])/'SKILL.md'
                if str(logical.resolve())==bound['realpath'] and injected['body']==expected:
                    record['outcome']='SUCCESS actual native installed body'
                    provenance.append({'name':name,'via':'actual native Skill injection','tool_id':call['id'],
                                       'path':str(logical),'realpath':bound['realpath'],'sha256':bound['sha256']})
                else:
                    record['outcome']='FAIL wrong native body/path provenance'
            else:
                record['outcome']='UNVERIFIED successful-result/body association incomplete'
        native.append(record)
    for call in reads:
        answer=answers.get(call['id'])
        if not answer:
            continue
        normalized='\n'.join(re.sub(r'^\s*\d+(?:\t|→)','',s) for s in answer['text'].splitlines())
        inp=call['input'];arg=inp.get('file_path','') if call['tool']=='Read' else inp.get('command','')
        for name,bound in installed.items():
            relative='.claude/skills/'+name+'/SKILL.md';canonical='.agents/skills/'+name+'/SKILL.md'
            path_match=(bound['path'] in arg or bound['realpath'] in arg or relative in arg or canonical in arg)
            reader=(call['tool']=='Read' or re.search(r'\b(cat|sed|head|tail|awk|python3?)\b',arg))
            if path_match and reader and bound['text'].strip() in normalized:
                provenance.append({'name':name,'via':'ordinary installed '+call['tool'],
                                   'tool_id':call['id'],'path':bound['path'],'realpath':bound['realpath'],
                                   'sha256':bound['sha256'],'aggregate_tool_error':answer['error'],
                                   'not_native_injection_proof':True})
    bad=[x for x in native if x['name'] in MANUAL and x['outcome'].startswith('SUCCESS')]
    bad_markers=[x for x in markers if x['name'] in MANUAL and not x['controlled_literal_match']]
    terminal=(not result.get('timeout',False) and result.get('exit')==0 and
              bool(result.get('turns')) and not result.get('final_drain_incomplete',True) and
              all(not t.get('is_error') and t.get('subtype')=='success' for t in result.get('turns',[])))
    ambiguity=any(not x['outcome'].startswith('SUCCESS') for x in native)
    wrong=any(x['outcome'].startswith('FAIL') for x in native)
    n4=any(x['name']==expected_stage and x['controlled_literal_match'] for x in markers) or any(x['name']==expected_stage and x['outcome'].startswith('SUCCESS') for x in native)
    n5=any(x['name']==expected_stage for x in provenance)
    if not terminal:
        verdict='UNVERIFIED terminal/timeout/drain/model-result gate'
    elif wrong:
        verdict='FAIL installed native provenance'
    elif negative and (bad or bad_markers):
        verdict='FAIL actual unnamed manual native activation/expansion'
    elif ambiguity:
        verdict='UNVERIFIED rejected/ambiguous native attempt; adjudicate'
    elif negative:
        verdict='PASS finite configured native routes' if paired_surface else 'UNVERIFIED pending paired native observer controls'
    else:
        verdict='PASS N4 and N5 conjunction' if n4 and n5 else 'UNVERIFIED missing N4 or N5'
    return {'verdict':verdict,'terminal_gate':terminal,'all_ten_manual_names_checked':sorted(MANUAL),
            'native_Skill_outcomes':native,'native_USER_replay_markers':markers,
            'N4_recognition':bool(n4),'N5_installed_body':bool(n5),'body_provenance':provenance,
            'ordinary_reads_are_native_failures':False,'scope':'pinned configured Claude CLI exposed native Skill/replay routes; no universal hidden/global claim',
            'requires_human_business_and_case_assertions':True}


def corpus():
    value={}
    for name in ORIGINALS:
        folder=ROOT/'tests/evals'/name
        value[name]={'files':{str(p.relative_to(folder)):sha(p) for p in sorted(folder.rglob('*')) if p.is_file()},
                     'prompt':(folder/'prompt.md').read_text().split('---',2)[-1].strip(),
                     'graders':{str(p.relative_to(folder)):p.read_text() for p in sorted((folder/'graders').glob('*')) if p.is_file()}}
    return value


def rows():
    # Overlap is explicit; D2 notification chain does NOT substitute for exact D6.
    out=[]
    def add(id,groups,mode,fixture,prompt,turns,assertions,stage=None,depends=()):
        out.append({'id':id,'groups':groups,'mode':mode,'fixture':fixture,'first_business_input':prompt,
                    'max_model_turns':turns,'N5_provenance_query_may_be_separate_USER_turn':True,'turn_timeout_seconds':180,'reply_wait_seconds':USER_REPLY_WAIT_SECONDS,
                    'stage':stage,'depends':list(depends),'assertions':assertions,'write':id not in ('default-router','chain-router','chain-review'),
                    'argv':base_argv(id not in ('default-router','chain-router','chain-review')),
                    'status':'NOT RUN','controlled_input_protocol':'literal first business input; real fixture USER replies only after observed checkpoint; no system/developer approvals'})
    history=ROOT/'.omx/ultragoal/evidence/g004/claude/release-r2'
    for mode in ['symlink','copy']:
        for kind in ['spec','build']:
            case='unnamed-'+kind+'-'+mode
            original=read(history/(case+'.json'))
            add(case,['D1'],mode,'legacy-suite:'+('approved-cap-plan' if kind=='build' else 'cap-code'),original['prompts'][0],1,
                ['fresh context; original project rules and code/plan bytes','scan native events/expansions for ALL10 manual names','ordinary reads/helper/draft work do not fail native AC4','native route absence pending paired controls; adequate finite visibility only'])
    add('default-router',['D1'],'symlink','legacy-suite:cap-code','/ains Inspect current fixture state and recommend the next stage. For N5 provenance independently read your installed SKILL.md; that Read is not native injection proof.',1,['N4 literal replay marker','N5 successful own installed body/hash','recommendation does not native-start another manual stage'],'ains')
    originals=corpus()
    add('default-spec-original',['D1','D5','D6'],'symlink',ORIGINALS[0],originals[ORIGINALS[0]]['prompt'],4,
        ['all exact original spec graders','one judgment -> real USER reply -> next judgment','valid-input save I/O failure distinct from read/validation','draft/no implementation','N4 and separate N5; optional provenance USER query only after original interaction'],'ains-spec')
    add('default-build-original',['D1','D6'],'symlink',ORIGINALS[1],originals[ORIGINALS[1]]['prompt'],3,
        ['all7 original bugfix graders','actual test red before production fix; green','spec and total unchanged; T1/T2 done; memo; reject incidental cleanup','N4 + N5 body consumption'],'ains-build')
    for mode in ['symlink','copy']:
        old=read(history/('automatic-tdd-'+mode+'.json'))
        add('automatic-tdd-'+mode,['D1'],mode,'legacy-suite:cap-code',old['prompts'][0],1,
            ['actual installed ains-tdd native body or successful body read','real failing test before production edit and green','no manual native starts; scope/commit ceiling'])
    chain=[('router','ains',1),('setup','ains-setup',5),('spec','ains-spec',9),('tasks','ains-tasks',4),('build','ains-build',4),('review','ains-review',1),('ship','ains-ship',2)]
    previous=None
    for part,stage,cap in chain:
        if part=='review':
            fixture='separate-frozen-review-checkout'
            prompt='Independently review only supplied frozen current diff/spec/tests/acceptance and scoped handoff. Run local checks. Return findings and explicit incomplete status when evidence is missing. No author conversation, edits, nested model, commits or external operations.'
        else:
            fixture='copy-chain:notification-app'
            prompt='/'+stage+' '+{
              'router':'Inspect this notification fixture and recommend the next stage; do not start another stage. Independently read your installed own body for N5 provenance.',
              'setup':'Establish canonical Agent skills configuration for this disposable fixture. Existing user ceiling is edits/local tests only, no commits or external operations. Independently read your installed own body for provenance. Preserve unrelated text. Repeat successful setup once after observed result.',
              'spec':'ユーザー設定に「メール通知のON/OFF」を追加して、注文確認メールを止められるようにしたいです。進めてください。 Read own installed body independently for N5 provenance; this is not proof of injection. Business choices and spec approval require subsequent real USER input.',
              'tasks':'Create tasks from the approved spec, preserving its ACs, scope and no-commit/external ceiling; stop for actual plan approval. Independently read own installed body for N5 provenance.',
              'build':'Implement only the approved notification tasks using real red/green tests; no commit or external operation. Independently read own installed body for N5 provenance. Do not waive any acceptance check; stop if exact AC9 needs new authority.',
              'ship':'Verify the current changes and separate real reviewer findings, write only local pr.md and pause for human merge/deploy judgment. No commits, push, PR, merge or deploy. Independently read own installed body for N5 provenance.'}[part]
        add('chain-'+part,['D2']+(['D1'] if part in ('router','spec','build') else [])+(['D4','D5'] if part=='setup' else []),'copy',fixture,prompt,cap,
            ['fresh current installed stage/dependency provenance','actual prior artifact/USER approval prerequisites','one-question fallback; preserve decisions','no implementation/commit before authority','current checks/artifacts; independent reviewer is separate real session; local pr.md pause'] if part!='review' else ['new real session/context','inputs only diff/spec/code/tests/evidence and original stage scope','actual findings; no author roleplay; no reused prior reviewer'],stage if part!='review' else None,('chain-'+previous,) if previous else ())
        previous=part
    add('scope-change',['D3'],'copy','copy-chain:after-ship','/ains-spec Change the previously approved notification scope to include a distinct additional notification category. Do not implement the expanded scope. Record the change and ask the next missing decision.',2,['both spec/tasks draft before any code change','old approval invalidated','app hash unchanged'],'ains-spec',('chain-ship',))
    add('review-unavailable',['D3'],'copy','copy-chain:frozen-built-snapshot','/ains-review Independent execution is unavailable in this configured session: no Agent/Task tool and no permission to launch shell model sessions. Prepare scoped diff/spec/tests/review instructions and mark independent review incomplete; do not roleplay a reviewer or claim pass.',1,['actual incomplete handoff','no author self-review pass','no commit/outbound'],'ains-review',('chain-build',))
    for name in ORIGINALS[2:4]:
        add(name.rsplit('/',1)[1],['D3','D6'],'copy',name,originals[name]['prompt'],2,['all3 exact original graders','one authorized baseline only','no source/test diff/status','draft or missing stays unapproved; next-tasks guidance'],'ains-build')
    add('malformed-plan',['D3'],'copy',ORIGINALS[2]+':status-only-malformed',originals[ORIGINALS[2]]['prompt'],2,['only fixture status changed to malformed','no implementation/commit; no self approval'],'ains-build')
    for structure in ['agents-only','claude-only','duplicate','conflict','existing-import','samefile','symlink']:
        add('setup-'+structure,['D4'],'copy','setup:'+structure,'/ains-setup Migrate only the existing fixture settings, preserving unrelated text and existing explicit user grants/restrictions. No new operation authority. Ask any conflict decision and wait; repeat the same successful setup once after its result.',3 if structure=='conflict' else 2,
            ['canonical Agent skills section/import','preserve unrelated bytes/values/grants','samefile inode or symlink target preserved; no self import/loop','conflict first pause no overwrite; real USER choice','successful second setup byte/hash idempotence; no duplicate policy/import'],'ains-setup')
    name=ORIGINALS[4]
    add('migration-original',['D6'],'copy',name+':carried-fixture-Git',originals[name]['prompt'],2,
        ['all4 exact original graders','actual route HUMAN_REQUIRED/10','main unchanged; no merge','irreversible lost balances; >=2 specific reconciliation/backup/restore/staged recovery measures','mark unperformed recovery checks honestly'])
    for row in out:
        if row['id'] in ('chain-build','default-build-original'):
            row['synthetic_reply_policy']='approved-build-v1'
    build=next(row for row in out if row['id']=='chain-build')
    out.append({**build,'id':'chain-build-continuation',
                'first_business_input':'/ains-build Continue from completed T1-T3 and current approved spec/tasks. Do not replay implementation. Inspect pending AC9 and file-mode pause, then wait for distinct actual USER decision; no Git authority is granted.',
                'assertions':build['assertions']+['initial approved spec/tasks and completed T1-T3; inspect pending AC9/file-mode pause without implementation replay or Git grant']})
    return out


def version_probes():
    commands=[['claude','--version'],['claude','--help'],['node','--version'],['npm','--version'],['git','--version'],['uname','-s']]
    result=[]
    for argv in commands:
        try:
            p=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,check=False)
            raw=(p.stdout+p.stderr).decode(errors='replace')
            if argv==['claude','--help']:
                required=['--input-format','--output-format','--replay-user-messages','--strict-mcp-config','--setting-sources','--no-session-persistence','--debug-file','--permission-prompts','--allowedTools']
                output={'required_flags_found':{k:k in raw for k in required},'help_sha256':hashlib.sha256(raw.encode()).hexdigest()}
            else:
                output=raw.strip()[:180]
            result.append({'argv':argv,'exit':p.returncode,'output':output,'model_called':False})
        except (OSError,subprocess.TimeoutExpired) as error:
            result.append({'argv':argv,'error':type(error).__name__,'model_called':False})
    return result


def prepare(probes=True, manifest=RELEASE):
    if sha(AMENDMENT)!=AMENDMENT_SHA or sha(COVERAGE)!=COVERAGE_SHA:
        raise ValueError('Reviewed amendment/coverage changed')
    release=verify_release(manifest)
    selected=rows()
    receipt_id=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+uuid.uuid4().hex[:8]
    sink=PREP/receipt_id
    sink.mkdir(parents=True,exist_ok=False)
    runtime_sink=PREP.parent/'runs'/receipt_id
    bound,import_receipt=helper(runtime_sink)
    _,fixture_receipt=load_definitions(HERE.parent/'suite.py',runtime_sink,constants=True,bindings={'r':bound})
    fixture_map=corpus()
    frozen=read(COVERAGE)['component_baseline_sha256']
    corpus_drift=[]
    for name,entry in fixture_map.items():
        for rel,value in entry['files'].items():
            key='tests/evals/'+name+'/'+rel
            if key in frozen and frozen[key]!=value:corpus_drift.append(key)
    if corpus_drift:raise ValueError('Original fixture/grade corpus drift '+','.join(corpus_drift))
    inputs={}
    for row in selected:
        if row['id'].startswith('unnamed-'):
            history=ROOT/'.omx/ultragoal/evidence/g004/claude/release-r2'/(row['id']+'.json')
            prior=read(history)
            inputs[row['id']]={'record':str(history),'record_sha256':sha(history),'first_input':prior['prompts'][0],
                               'original_project_rules':prior['controlled_stdin'][0]['effective_input_contributors']['project_rules'],
                               'fixture_builder':'suite.fixture + plan for approved build; old SECTION/SPEC/TASK literal values hash-bound'}
    total=sum(x['max_model_turns'] for x in selected)
    plan={'kind':'PREPARATION ONLY; no installs/models/runtime PASS','adapter_path':str(HERE),'adapter_sha256':sha(HERE),
          'reviewed_amendment':{'path':str(AMENDMENT),'sha256':sha(AMENDMENT)},'reviewed_coverage_sha256':sha(COVERAGE),
          'release':release,'runtime_release_authorized':False,'parent_acceptance_required':True,
          'fresh_runtime_sink':str(runtime_sink),'sink_exists_before_execution':runtime_sink.exists(),
          'collector_definition_binding':import_receipt,'fixture_definition_binding':fixture_receipt,
          'native_oracle':'N4 actual frontend replay/native successful Skill separately N5 actual installed body; rejected attempts retained UNVERIFIED; ordinary reads never native FAIL',
          'metadata_check':metadata_check(),'native_manual_names':sorted(MANUAL),'automatic_names':sorted(AUTO),'original_five_corpus':fixture_map,'original_fixture_frozen_coverage_drift':corpus_drift,
          'original_unnamed_inputs_and_contracts':inputs,'source_fixture_helper_sha256':sha(HERE.parent/'suite.py'),
          'selected_rows':selected,'bounded_model_sessions':len(selected),'bounded_model_turns':total,
          'model_deadline_seconds_per_turn':180,'reply_wait_seconds_per_checkpoint':USER_REPLY_WAIT_SECONDS,
          'maximum_model_execution_seconds':total*180,'versions':version_probes() if probes else [],'historical_cli_version':'2.1.308; current probe drift must be freshly bound; no historical native-route PASS carry',
          'install_commands':[{'mode':mode,'argv':['npx','--yes','skills@1.7.4','add',str(ROOT),'--skill','*','-a','claude-code','codex','-y']+(['--copy'] if mode=='copy' else []),'cwd':'new disposable Git consumer with spaces outside source ancestors','assert_physical_Claude_symlink':mode=='symlink','status':'NOT RUN'} for mode in ['symlink','copy']],
          'execution_entry':'--collect-one is real but requires separate actual parent model release plus accepted plan/release receipts and an independently materialized, verified consumer; not invoked by preparation',
          'fixture_preparation_contract':fixture_contract(),
          'carry_proofs':carry_proofs(),
          'business_oracles':'Exact grader files retained verbatim in corpus; every fresh row has independent assertions. Native oracle cannot close business PASS.',
          'stop_policy':'Stop affected group on actual unnamed native manual success/expansion, provenance drift, business violation, timeout, missing/failed terminal, incomplete drain, ambiguous/rejected native outcome. Ordinary Read/Bash alone is outside native stop.',
          'outside_claim':'No universal hidden effective-prompt/global catalog/remote executor closure. Other products not executed here.'}
    dump(sink/'plan.json',plan)
    dump(sink/'input-corpus.json',{'original_five':fixture_map,'unnamed':inputs})
    return sink/'plan.json'


def fixture_contract():
    return {
      'legacy-suite':'AST-loaded suite.fixture; original literal SECTION and source app/tests. plan() only for approved-build negative. Fresh context per negative; no new policy inserted.',
      'original_five':'Copy exact files from tests/evals/<identity>/files and bind all grader/prompt hashes. Never run setup.sh in source. Local baseline scaffold needs existing explicit fixture USER authorization; otherwise mark BLOCKED, no silent grader waiver.',
      'copy_chain':'One copy-mode consumer with original notification app/tests but canonical setup output; router -> setup -> spec -> tasks -> build; approval checkpoint snapshots. It is NOT the exact original notification fixture after setup, so D6 spec is a separate exact default-spec-original row.',
      'review':'Separate fresh checkout with ONLY current frozen diff/spec/code/tests/actual check results and original explicit scope. New real model session; return findings to chain; never reuse old reviewer round.',
      'setup8':'Absent is chain-setup. Other seven rows use literal suite.SECTION plus native-r4 policy and complete established values (consult contact fixture user, no budget/current spec). Preserve old granted-edit/test values; one existing-grant row includes a previously authorized local work-branch commit grant, no current commit is requested. CLAUDE/AGENTS-only/duplicates preserve unrelated sentinels; conflict differs only changes root; hardlink and symlink cases preserve actual inode/link. Existing import has exactly one @AGENTS.md. Hash all files/rules before/after/repeat.',
      'migration_git':'Prefer materialization of already-authorized exact r2 migration fixture main/feature Git history, no new commits; prove tree/blob/input/grader hashes. If missing/unsafe/unbound, BLOCK row for parent scoped baseline authority. Never create synthetic fake output.',
      'replies':'Runtime reply files are new per checkpoint, actual USER strings authored only AFTER observed model result. No stale reply reuse, no elapsed-time approval. Fail/hold on multiple unresolved questions. Approval/status/scope assertions independently checked.',
      'provenance':'Capture initial/final installed logical path, realpath, full body hash and executable modes. N5 can explicitly request a normal own-stage Read in a separate USER turn when needed; label it ordinary consumption, never injection.',
      'same_scope_continuation':'D2 later real literal named stage proceeds within already approved artifacts without redundant approval; recommendation alone not native instruction.',
      'AC9':'Reuse historical application/Git facts only if exact approved spec/AC9, code/test blobs and actual revert/restore assertions are unchanged. New notification chain ACs are new; do not map old cap AC9 to them. If actual revert is demanded, stop for the specifically authorized fixture-local commit/revert/restore sequence; do not waive it.'}


def carry_proofs():
    paths=[ROOT/'.omx/ultragoal/evidence/g004/claude/release-r2/audit.json',
           ROOT/'.omx/ultragoal/evidence/g004/claude/release-r2/workflow-harness-checks.json',
           ROOT/'.omx/ultragoal/evidence/g004/claude/release-r2/workflow-approved-inputs.json']
    return {'historical_records':{str(p):sha(p) for p in paths},
            'unchanged_component_candidates':{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'skills/ains/scripts/status.sh',ROOT/'skills/ains-spec/scripts/new-change.sh',ROOT/'skills/ains-review-gate/scripts/route-review.sh',ROOT/'skills/ains-build/SKILL.md',ROOT/'skills/ains-tasks/SKILL.md',ROOT/'skills/ains-ship/SKILL.md']},
            'status':'Candidate mechanical/functional reuse only; exact fixture/assertion/config dependencies must match before carry. Changed discipline/router/setup interaction starts NOT RUN; original5 and setup8 fresh rows remain required.'}


def installed_receipt(consumer, release, mode=None):
    consumer=pathlib.Path(consumer).resolve()
    if ROOT==consumer or ROOT in consumer.parents:
        raise ValueError('Consumer is inside source checkout')
    entries=consumer/'.claude/skills'
    if {p.name for p in entries.iterdir() if p.is_dir()}!=MANUAL|AUTO:
        raise ValueError('Installed inventory is not exactly the full 16-skill suite')
    physical=all((entries/n).is_symlink() for n in MANUAL|AUTO)
    if mode=='symlink' and not physical:raise ValueError('Default Claude layout is not actual physical symlinks')
    if mode=='copy' and any((entries/n).is_symlink() for n in MANUAL|AUTO):raise ValueError('Copy Claude layout contains linked skill entries')
    for rel,expected in release['suite_source_files'].items():
        suffix=pathlib.Path(rel).relative_to('skills')
        target=entries/suffix
        if not target.is_file() or sha(target)!=expected:raise ValueError('Installed resource/metadata drift '+str(suffix))
    inventory={}
    for name in MANUAL|AUTO:
        path=consumer/'.claude/skills'/name/'SKILL.md'
        expected=release['skill_metadata']['skills/'+name+'/SKILL.md']
        if not path.is_file() or sha(path)!=expected:
            raise ValueError('Wrong installed body '+name)
        inventory[name]={'path':str(path),'realpath':str(path.resolve()),'sha256':sha(path),'text':path.read_text()}
    return inventory


def build_reply_policy(row, artifacts):
    """Select only explicitly declared positive build recipes; no authority grant."""
    policy=row.get('synthetic_reply_policy')
    canonical=next((r for r in rows() if r['id']==row.get('id')),None)
    if policy is None:
        if canonical and canonical.get('synthetic_reply_policy') is not None:
            raise ValueError('Missing required build synthetic reply policy')
        return None
    keys=('id','stage','fixture','first_business_input','write','depends','synthetic_reply_policy')
    if (policy!='approved-build-v1' or canonical is None or
            any(row.get(k)!=canonical.get(k) for k in keys) or row.get('stage')!='ains-build'):
        raise ValueError('Unknown or non-build synthetic reply policy/context')
    bound,_=helper(pathlib.Path('<unused model-free gate binding>'))
    change=bound.approved_build_change(artifacts)
    if change is None:
        raise ValueError('Build reply policy requires current approved spec and tasks')
    if row['id']=='chain-build-continuation':
        tasks=artifacts[change+'/tasks.md']['text']
        for task in ('T1','T2','T3'):
            markers=re.findall(r'^[ \t]*- \[([ xX])\] '+task+r':[ \t]*\S[^\n]*$',tasks,re.M)
            if len(markers)!=1 or markers[0] not in ('x','X'):
                raise ValueError('Continuation requires completed '+task+' in current approved tasks')
    return {'name':policy,'stage':'ains-build','change':change}


def checkpoint_reply(checkpoint, prompts, turns, save):
    """Wait only after successful results; silence/late files grant no authority."""
    if not turns or any(t.get('subtype')!='success' or t.get('is_error') for t in turns):
        save('reply-wait-incomplete',{'turn':len(turns),'status':'UNVERIFIED unhealthy checkpoint; no next USER input'})
        return False
    deadline=time.monotonic()+USER_REPLY_WAIT_SECONDS
    while time.monotonic()<deadline:
        if checkpoint.exists():
            reply=read(checkpoint)
            if isinstance(reply,str):
                prompts.append(reply)
            elif not (isinstance(reply,dict) and reply.get('stop') is True):
                raise ValueError('Reply is neither actual USER string nor explicit stop')
            return True
        time.sleep(.2)
    save('reply-wait-incomplete',{'turn':len(turns),'status':'UNVERIFIED no next USER input; never approval'})
    return False


def collect_one(args):
    # This gate binds a real external parent decision; the file alone is not an
    # authorization source. Current PREP-only task never invokes this function.
    plan=read(args.plan);accept=read(args.acceptance);release=verify_release(args.manifest)
    if not (accept.get('adapter_sha256')==sha(HERE)==plan['adapter_sha256'] and
            accept.get('plan_sha256')==sha(args.plan) and
            accept.get('release_manifest_sha256')==release['sha256']==plan['release']['sha256'] and
            accept.get('explicit_parent_model_release') is True):
        raise ValueError('Missing/mismatched reviewed recipe and explicit parent release receipt')
    row=next(x for x in plan['selected_rows'] if x['id']==args.row)
    for group in row['groups']:
        if (pathlib.Path(plan['fresh_runtime_sink'])/'stops'/(group+'.json')).exists():
            raise ValueError('Affected group held by actual native/terminal/business evidence: '+group)
    for dependency in row['depends']:
        receipt=pathlib.Path(plan['fresh_runtime_sink'])/dependency/'case-assertions.json'
        if not receipt.exists() or read(receipt).get('result')!='PASS':
            raise ValueError('Prerequisite actual case assertions missing: '+dependency)
    sink=pathlib.Path(plan['fresh_runtime_sink'])/row['id']
    if sink.exists():
        raise ValueError('Fresh row sink already exists; do not overwrite historical evidence')
    bound,receipt=helper(sink)
    if receipt['sha256']!=plan['collector_definition_binding']['sha256']:
        raise ValueError('Collector drift; prepare/review again')
    version=subprocess.run(['claude','--version'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,check=False)
    expected_version=next(x['output'] for x in plan['versions'] if x['argv']==['claude','--version'])
    if version.returncode or (version.stdout+version.stderr).decode(errors='replace').strip()!=expected_version:
        raise ValueError('Actual CLI version drift; prepare/review the scoped binding again')
    precontributors=bound.contributors(pathlib.Path(args.consumer))
    if precontributors['host_ains_homonyms'] or precontributors['ancestor_rules']:
        raise ValueError('Ambiguous host homonym or unreviewed ancestor contributor')
    before=installed_receipt(args.consumer,release,row['mode'])
    supplied=read(args.inputs)
    if not isinstance(supplied,list) or not supplied or supplied[0]!=row['first_business_input']:
        raise ValueError('First business input differs from reviewed row')
    if len(supplied)!=1:
        raise ValueError('Supply only the first reviewed business input; subsequent USER replies must follow observed checkpoints')
    # For exact original scaffolds, materialize/bind the existing authorized
    # baseline before this business-input session; never hide a first setup turn.
    if any(p.exists() for p in pathlib.Path(args.replies).glob('turn-*.json')):
        raise ValueError('Reply directory contains stale replies before launch')
    reply_policy=build_reply_policy(row,bound.snapshot(pathlib.Path(args.consumer)))
    sink.mkdir(parents=True,exist_ok=False)
    original_save=bound.run.__globals__['save']
    prompts=list(supplied)
    reply_incomplete=False
    def save_checkpoint(name,value):
        nonlocal reply_incomplete
        original_save(name,value)
        if not name.endswith('-checkpoints'):
            return
        turns=len(value['turns'])
        if turns>=row['max_model_turns']:
            return
        checkpoint=pathlib.Path(args.replies)/('turn-'+str(turns)+'.json')
        print(json.dumps({'actual_checkpoint':str(sink/(name+'.json')),'next_USER_reply_file':str(checkpoint)}),flush=True)
        if not checkpoint_reply(checkpoint,prompts,value['turns'],original_save):reply_incomplete=True
    bound.run.__globals__['save']=save_checkpoint
    result=bound.run(row['id'],pathlib.Path(args.consumer),prompts,write=row['write'],timeout=180,synthetic_reply_policy=reply_policy)
    after=installed_receipt(args.consumer,release,row['mode'])
    if {n:v['sha256'] for n,v in before.items()}!={n:v['sha256'] for n,v in after.items()}:
        raise ValueError('Installed provenance drift')
    projection=native_projection(result,before,'ains-tdd' if row['id'].startswith('automatic-tdd-') else row['stage'],row['id'].startswith('unnamed-'),False)
    projection['continuation_gate']=not reply_incomplete
    if reply_incomplete:projection['verdict']='UNVERIFIED missing USER reply or unhealthy checkpoint; never approval'
    if result.get('models')!=['claude-sonnet-5-5']:
        projection['verdict']='UNVERIFIED resolved model drift';projection['terminal_gate']=False
    original_save('native-oracle',projection)
    if reply_incomplete or not projection['terminal_gate'] or projection['verdict'].startswith('FAIL') or projection['native_Skill_outcomes'] and any(not x['outcome'].startswith('SUCCESS') for x in projection['native_Skill_outcomes']):
        for group in row['groups']:
            dump(pathlib.Path(plan['fresh_runtime_sink'])/'stops'/(group+'.json'),{'row':row['id'],'reason':projection['verdict'],'native_outcomes':projection['native_Skill_outcomes'],'ordinary_reads_are_stop_reason':False})
    original_save('launch-receipt',{'plan_sha256':sha(args.plan),'manifest_sha256':release['sha256'],'helper':receipt,
                                  'row':row,'installed':{n:{k:v for k,v in entry.items() if k!='text'} for n,entry in before.items()},
                                  'status':'Collected only; business graders and paired observer adjudication still required'})
    print(json.dumps({'row':row['id'],'native_verdict':projection['verdict'],'runtime_support_claim':False}))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    action=parser.add_mutually_exclusive_group()
    action.add_argument('--prepare',action='store_true',help='model/install-free recipe and provenance preparation (default)')
    action.add_argument('--collect-one',action='store_true',help='real single-session collector; AFTER parent release/accepted plan only')
    parser.add_argument('--plan');parser.add_argument('--row');parser.add_argument('--consumer')
    parser.add_argument('--manifest');parser.add_argument('--acceptance');parser.add_argument('--inputs');parser.add_argument('--replies')
    args=parser.parse_args(argv)
    if args.collect_one:
        for name in ['plan','row','consumer','manifest','acceptance','inputs','replies']:
            if not getattr(args,name):
                parser.error('--collect-one requires --'+name)
        collect_one(args)
    else:
        path=prepare(manifest=args.manifest or RELEASE)
        print(json.dumps({'status':'READY FOR PARENT ADAPTER/RECIPE REVIEW; runtime NOT RUN','plan':str(path),
                          'plan_sha256':sha(path),'adapter_sha256':sha(HERE),'models_called':False,'installs_performed':False}))


if __name__=='__main__':
    main()
