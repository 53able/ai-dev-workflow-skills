"""Model-free synthetic oracle/collector tests. Never product-runtime evidence."""
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PATH=pathlib.Path(__file__).with_name('native_delta.py')
spec=importlib.util.spec_from_file_location('native_delta',PATH)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class NativeOracle(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='native oracle synthetic ')
        self.root=pathlib.Path(self.temp.name)
        self.installed={}
        for name in m.MANUAL|m.AUTO:
            p=self.root/'.claude/skills'/name/'SKILL.md';p.parent.mkdir(parents=True)
            body='---\nname: '+name+'\n---\n\n# Synthetic procedure\nWait for the requested fixture judgment.\n'
            p.write_text(body)
            self.installed[name]={'path':str(p),'realpath':str(p.resolve()),'sha256':m.sha(p),'text':body}
    def tearDown(self):self.temp.cleanup()
    def result(self,prompt='Create a specification for discount cap.',events=None):
        return {'exit':0,'timeout':False,'final_drain_incomplete':False,
                'turns':[{'subtype':'success','is_error':False}],
                'controlled_stdin':[{'input':{'type':'user','message':{'role':'user','content':prompt}}}],
                'all_sanitized_stream_events':events or []}
    def event(self,type,blocks,**kw):
        return {'type':type,'message':{'role':'assistant' if type=='assistant' else 'user','content':blocks},**kw}
    def skill(self,name,error=False,body=True,wrong=False):
        x=[self.event('assistant',[{'type':'tool_use','name':'Skill','id':'call','input':{'skill':name}}]),
           self.event('user',[{'type':'tool_result','tool_use_id':'call','is_error':error,'content':'denied' if error else 'Launching skill: '+name}])]
        if body and not error:
            entry=self.installed[name];text='Base directory for this skill: '+str(pathlib.Path(entry['path']).parent)+'\n\n'+entry['text'].split('---',2)[-1].strip()
            if wrong:text+='\nWRONG BODY'
            x.append(self.event('user',[{'type':'text','text':text}]))
        return x
    def read_body(self,name,error=False):
        return [self.event('assistant',[{'type':'tool_use','name':'Read','id':'read','input':{'file_path':self.installed[name]['path']}}]),self.event('user',[{'type':'tool_result','tool_use_id':'read','is_error':error,'content':self.installed[name]['text']}])]
    def marker(self,name,type='user',replay=True):
        return self.event(type,'<command-message>'+name+'</command-message>\n<command-name>/'+name+'</command-name>\n<command-args>fixture</command-args>',isReplay=replay)
    def test_all_ten_successful_manual_native_calls_fail_unnamed(self):
        for name in m.MANUAL:
            with self.subTest(name=name):
                r=m.native_projection(self.result(events=self.skill(name)),self.installed,negative=True,paired_surface=True)
                self.assertTrue(r['verdict'].startswith('FAIL actual unnamed'))
    def test_rejected_attempt_is_not_success_or_native_fail(self):
        r=m.native_projection(self.result(events=self.skill('ains-spec',error=True)),self.installed,negative=True,paired_surface=True)
        self.assertTrue(r['verdict'].startswith('UNVERIFIED'))
        self.assertEqual(r['native_Skill_outcomes'][0]['outcome'],'REJECTED_ATTEMPT')
    def test_missing_result_or_body_is_unverified(self):
        for events in [self.skill('ains-spec')[:1],self.skill('ains-spec',body=False)]:
            self.assertTrue(m.native_projection(self.result(events=events),self.installed,negative=True,paired_surface=True)['verdict'].startswith('UNVERIFIED'))
    def test_ordinary_reads_never_native_failure(self):
        r=m.native_projection(self.result(events=self.read_body('ains-spec')),self.installed,negative=True,paired_surface=True)
        self.assertEqual(r['verdict'],'PASS finite configured native routes')
        self.assertEqual(r['native_Skill_outcomes'],[])
    def test_n4_n5_conjunction_independent_read_not_injection(self):
        events=[self.marker('ains-spec')]+self.read_body('ains-spec')
        r=m.native_projection(self.result('/ains-spec fixture',events),self.installed,'ains-spec')
        self.assertTrue(r['N4_recognition'] and r['N5_installed_body'])
        self.assertEqual(r['verdict'],'PASS N4 and N5 conjunction')
        self.assertTrue(r['body_provenance'][0]['not_native_injection_proof'])
    def test_read_alone_and_assistant_markup_do_not_prove_n4(self):
        for marker in [[],[self.marker('ains-spec','assistant')],[self.marker('ains-spec',replay=False)]]:
            r=m.native_projection(self.result('/ains-spec fixture',marker+self.read_body('ains-spec')),self.installed,'ains-spec')
            self.assertFalse(r['N4_recognition']);self.assertTrue(r['N5_installed_body'])
    def test_actual_unrequested_replay_expansion_fails(self):
        r=m.native_projection(self.result(events=[self.marker('ains-setup')]),self.installed,negative=True,paired_surface=True)
        self.assertTrue(r['verdict'].startswith('FAIL actual unnamed'))
    def test_native_wrong_provenance_fails(self):
        r=m.native_projection(self.result('/ains-spec fixture',self.skill('ains-spec',wrong=True)),self.installed,'ains-spec')
        self.assertEqual(r['verdict'],'FAIL installed native provenance')
    def test_no_native_events_without_pairs_stays_unverified(self):
        self.assertTrue(m.native_projection(self.result(),self.installed,negative=True)['verdict'].startswith('UNVERIFIED'))
    def test_missing_terminal_timeout_and_incomplete_drain_stop(self):
        for key,value in [('turns',[]),('timeout',True),('final_drain_incomplete',True),('exit',1)]:
            d=self.result();d[key]=value
            self.assertFalse(m.native_projection(d,self.installed,negative=True)['terminal_gate'])


class BuildReplyGate(unittest.TestCase):
    decision = ('SYNTHETIC FIXTURE USER REPLY: For this disposable fixture, mode 0600 '
                'is acceptable. This is not commit/revert authority. Show the exact app/test paths.')

    def artifacts(self):
        return {'app/settings.py': {'sha256':'before', 'text':'old implementation'},
                'docs/changes/notification/spec.md': {'sha256':'spec', 'text':'---\nstatus: approved\n---\n# Spec'},
                'docs/changes/notification/tasks.md': {'sha256':'tasks', 'text':'---\nstatus: approved\n---\n- [ ] T1: implement'}}

    def gate(self, initial=None, current=None, result=None, policy=None, prompt=None):
        bound,_=m.helper(self.root/'unused')
        return bound.synthetic_reply_gate(self.decision if prompt is None else prompt,
            {'subtype':'success','is_error':False,'result':'Waiting for your permission decision.'} if result is None else result,
            self.artifacts() if initial is None else initial,
            self.artifacts() if current is None else current, policy)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name)
        self.row=next(r for r in m.rows() if r['id']=='chain-build')
        self.policy=m.build_reply_policy(self.row,self.artifacts())

    def tearDown(self):self.temp.cleanup()

    def test_approved_build_changed_code_accepts_exact_reply_and_unprefixed_decision(self):
        current=self.artifacts();current['app/settings.py']={'sha256':'after','text':'implemented'}
        current['docs/changes/notification/tasks.md']['text']+='\n## メモ\nT1 verified green.'
        for prompt in (self.decision,'Please show the exact app/test paths. No commit permission.'):
            with self.subTest(prompt=prompt):
                gate=self.gate(current=current,policy=self.policy,prompt=prompt)
                self.assertTrue(gate['sent']);self.assertFalse(gate['implementation_unchanged'])
                self.assertTrue(gate['approved_build_context'])

    def test_initial_and_current_draft_missing_malformed_approvals_denied(self):
        for filename in ('spec.md','tasks.md'):
            path='docs/changes/notification/'+filename
            for body in (None,'---\nstatus: draft\n---','---\n---\nstatus: approved',
                         '---\nstatus: approved-ish\n---','status: approved',
                         '---\nstatus: approved\nstatus: draft\n---','---\nstatus: approved'):
                artifacts=self.artifacts()
                if body is None:artifacts.pop(path)
                else:artifacts[path]['text']=body
                with self.subTest(path=path,body=body):
                    with self.assertRaises(ValueError):m.build_reply_policy(self.row,artifacts)
                    self.assertFalse(self.gate(initial=artifacts,policy=self.policy)['sent'])
                    self.assertFalse(self.gate(current=artifacts,policy=self.policy)['sent'])

    def test_changed_spec_and_ambiguous_changes_denied(self):
        current=self.artifacts();current['docs/changes/notification/spec.md']['text']+='\nExpanded scope'
        self.assertFalse(self.gate(current=current,policy=self.policy)['sent'])
        current=self.artifacts();current['docs/changes/other/spec.md']=current['docs/changes/notification/spec.md']
        self.assertFalse(self.gate(current=current,policy=self.policy)['sent'])

    def test_missing_pause_or_unhealthy_checkpoint_denied(self):
        for result in ({'subtype':'success','is_error':False,'result':'15 tests passed. Done.'},
                       {'subtype':'success','is_error':False,'result':'Implementation complete; no authority required.'},
                       {'subtype':'error','is_error':False,'result':'Waiting for approval'},
                       {'subtype':'success','is_error':True,'result':'Waiting for approval'},
                       {'subtype':'success','result':'Waiting for approval'},{}):
            with self.subTest(result=result):self.assertFalse(self.gate(result=result,policy=self.policy)['sent'])

    def test_legacy_spec_gate_retains_draft_unchanged_and_pause_requirements(self):
        initial=self.artifacts();current=self.artifacts()
        current['docs/changes/notification/spec.md']['text']='---\nstatus: draft\n---'
        prompt='SYNTHETIC FIXTURE USER APPROVAL: Approve this spec only.'
        self.assertTrue(self.gate(initial=initial,current=current,prompt=prompt)['sent'])
        current['app/settings.py']['sha256']='changed'
        self.assertFalse(self.gate(initial=initial,current=current,prompt=prompt)['sent'])
        self.assertFalse(self.gate(initial=initial,current=current)['sent'])
        self.assertFalse(self.gate(prompt=prompt)['sent'])  # no draft
        self.assertTrue(self.gate()['sent'])  # legacy reply does not require draft
        self.assertFalse(self.gate(result={'result':'Done.'})['sent'])
        self.assertIsNone(self.gate(prompt='Ordinary legacy USER string'))

    def test_policy_only_explicit_canonical_positive_build_rows(self):
        for row in m.rows():
            artifacts=self.completed_artifacts() if row['id']=='chain-build-continuation' else self.artifacts()
            policy=m.build_reply_policy(row,artifacts)
            self.assertEqual(policy is not None,row['id'] in ('chain-build','default-build-original','chain-build-continuation'))
        for field,value in (('stage','ains-spec'),('id','arbitrary-manual-stage'),
                            ('fixture','other'),('first_business_input','/ains-build arbitrary'),
                            ('synthetic_reply_policy','unknown')):
            row=dict(self.row);row[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):m.build_reply_policy(row,self.artifacts())
        row=dict(self.row);row.pop('synthetic_reply_policy')
        with self.assertRaises(ValueError):m.build_reply_policy(row,self.artifacts())
        for policy in ({},'approved-build-v1',{'name':'unknown','stage':'ains-build','change':self.policy['change']},
                       {**self.policy,'stage':'ains-spec'},{**self.policy,'change':'other'}):
            self.assertFalse(self.gate(policy=policy)['sent'])

    def test_collect_one_selects_build_policy_before_dispatch_without_model(self):
        self.assert_collect_dispatch(self.row,self.artifacts())

    def assert_collect_dispatch(self,row,artifacts):
        import types
        sink=self.root/'run';dependency=sink/'chain-tasks/case-assertions.json'
        dependency.parent.mkdir(parents=True);dependency.write_text('{"result":"PASS"}')
        bound,receipt=m.helper(self.root/'bound');receipt['sha256']='hash'
        bound.snapshot=lambda root:artifacts
        bound.contributors=lambda root:{'host_ains_homonyms':[],'ancestor_rules':[]}
        result={'models':['claude-sonnet-5-5']}
        bound.run=mock.Mock(return_value=result)
        bound.run.__globals__={'save':lambda *args:None}
        plan={'adapter_sha256':'hash','release':{'sha256':'hash'},'selected_rows':[row],
              'fresh_runtime_sink':str(sink),'collector_definition_binding':{'sha256':'hash'},
              'versions':[{'argv':['claude','--version'],'output':'synthetic'}]}
        acceptance={'adapter_sha256':'hash','plan_sha256':'hash','release_manifest_sha256':'hash',
                    'explicit_parent_model_release':True}
        args=types.SimpleNamespace(plan='plan',acceptance='acceptance',manifest='manifest',
              row=row['id'],consumer=str(self.root),inputs='inputs',replies=str(self.root/'replies'))
        original_read=m.read
        def read(path):
            values={'plan':plan,'acceptance':acceptance,'inputs':[row['first_business_input']]}
            return values[str(path)] if str(path) in values else original_read(path)
        projection={'terminal_gate':True,'verdict':'UNVERIFIED synthetic test only','native_Skill_outcomes':[]}
        with mock.patch.object(m,'read',side_effect=read),mock.patch.object(m,'sha',return_value='hash'), \
             mock.patch.object(m,'verify_release',return_value={'sha256':'hash'}), \
             mock.patch.object(m,'helper',return_value=(bound,receipt)), \
             mock.patch.object(m,'installed_receipt',return_value={}), \
             mock.patch.object(m,'native_projection',return_value=projection), \
             mock.patch.object(m.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=b'synthetic',stderr=b'')):
            m.collect_one(args)
        self.assertEqual(bound.run.call_args.kwargs['synthetic_reply_policy'],self.policy)
        self.assertEqual(bound.run.call_args.kwargs['timeout'],180)
        self.assertEqual(bound.run.call_args.args[2],[row['first_business_input']])

    def completed_artifacts(self):
        artifacts=self.artifacts()
        artifacts['docs/changes/notification/tasks.md']['text']=('---\nstatus: approved\n---\n'
            '- [x] T1: settings implemented\n- [X] T2: atomic write implemented\n'
            '- [x] T3: notification implemented\n- [ ] T4: pending AC9 authority\n')
        return artifacts

    def continuation_row(self):
        rows=[r for r in m.rows() if r['id']=='chain-build-continuation']
        self.assertEqual(len(rows),1,'dedicated canonical continuation row is required')
        return rows[0]

    def test_continuation_canonical_dispatch_preserves_completed_work_and_gate(self):
        row=self.continuation_row();artifacts=self.completed_artifacts()
        self.assertEqual(row['first_business_input'],
            '/ains-build Continue from completed T1-T3 and current approved spec/tasks. Do not replay implementation. '
            'Inspect pending AC9 and file-mode pause, then wait for distinct actual USER decision; no Git authority is granted.')
        for field in ('stage','fixture','write','depends','synthetic_reply_policy'):
            self.assertEqual(row[field],self.row[field])
        self.assert_collect_dispatch(row,artifacts)
        policy=m.build_reply_policy(row,artifacts)
        self.assertTrue(self.gate(initial=artifacts,current=artifacts,policy=policy)['sent'])
        changed=json.loads(json.dumps(artifacts));changed['docs/changes/notification/spec.md']['text']+='\nchanged'
        self.assertFalse(self.gate(initial=artifacts,current=changed,policy=policy)['sent'])
        self.assertFalse(self.gate(initial=artifacts,current=artifacts,policy=policy,result={
            'subtype':'success','is_error':False,'result':'Done.'})['sent'])

    def test_continuation_requires_each_completed_t1_t3_marker(self):
        row=self.continuation_row();path='docs/changes/notification/tasks.md'
        for task in ('T1','T2','T3'):
            for replacement in ('missing','incomplete','duplicate','wrong-number'):
                artifacts=self.completed_artifacts();body=artifacts[path]['text']
                lines=body.splitlines(True);line=next(x for x in lines if '] '+task+':' in x)
                if replacement=='missing':body=body.replace(line,'')
                elif replacement=='incomplete':body=body.replace(line,line.replace('[x]','[ ]').replace('[X]','[ ]'))
                elif replacement=='duplicate':body+=line
                else:body=body.replace(line,line.replace(task+':',task+'0:'))
                artifacts[path]['text']=body
                with self.subTest(task=task,replacement=replacement),self.assertRaises(ValueError):
                    m.build_reply_policy(row,artifacts)

    def test_continuation_rejects_unapproved_or_missing_artifacts_and_custom_contract(self):
        row=self.continuation_row()
        for name in ('spec.md','tasks.md'):
            path='docs/changes/notification/'+name
            for status in (None,'draft','missing','malformed'):
                artifacts=self.completed_artifacts()
                if status is None:artifacts.pop(path)
                else:artifacts[path]['text']=artifacts[path]['text'].replace('status: approved',
                    '' if status=='missing' else 'status: '+status)
                with self.subTest(name=name,status=status),self.assertRaises(ValueError):
                    m.build_reply_policy(row,artifacts)
        for field,value in (('stage','ains-spec'),('first_business_input','/ains-build custom continuation'),
                            ('id','unknown-continuation'),('synthetic_reply_policy','unknown'),
                            ('fixture','other'),('write',False),('depends',[])):
            custom=dict(row);custom[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                m.build_reply_policy(custom,self.completed_artifacts())

    actual_choice_pause = (
        'A と B のどちらにしますか。\n\n'
        '**保留中(今は回答不要)**\n\n'
        '- T4 の許可:fixture ローカルでのコミット、`git revert`、revert の revert です。'
        '上の判断が決まってから、操作・対象・影響・戻し方を示して別途お聞きします。\n'
        '- 現時点では、Git 操作の権限は付与されていません。\n\n'
        '実際の回答があるまで、実装も T4 も進めません。')

    def test_actual_japanese_choice_and_answer_wait_are_observed_pauses(self):
        for phrase in ('A と B のどちらにしますか。',
                       '実際の回答があるまで、実装も T4 も進めません。',self.actual_choice_pause):
            with self.subTest(phrase=phrase):
                gate=self.gate(policy=self.policy,result={'subtype':'success','is_error':False,'result':phrase})
                self.assertTrue(gate['observed_pause'])
                self.assertTrue(gate['sent'])

    def test_japanese_completed_or_no_answer_text_does_not_create_pause(self):
        for phrase in ('どちらでも承認済み/許可不要/完了',
                       '回答不要。実装も T4 も進めます。',
                       '回答があるまで、待たずに進めます。',
                       '回答があるまで、待たずに進みます。',
                       'どちらにするかは決定済み。完了。'):
            with self.subTest(phrase=phrase):
                gate=self.gate(policy=self.policy,result={'subtype':'success','is_error':False,'result':phrase})
                self.assertFalse(gate['observed_pause'])
                self.assertFalse(gate['sent'])

    def test_actual_japanese_pause_callback_transmits_external_mode_only_user(self):
        self.assert_callback_reply(self.actual_choice_pause,continuation=True,reply=(
            'SYNTHETIC FIXTURE USER REPLY: Choose (a): mode 0600 is acceptable for this disposable fixture settings file; '
            'no cross-user filesystem access is required. This is only the file-mode decision and grants no Git operation. '
            'Keep the existing T1-T3 implementation unchanged. Independently read the complete already-selected installed '
            'ains-build/SKILL.md without truncation for ordinary body provenance, not native injection. Then retain the '
            'pending AC9 execution-authority checkpoint with the exact four app/test paths.'))

    actual_copy_pause = (
        'T1〜T3 は完了しています。15 件のテストが通りました。T4(AC9)は未実施で、次の2点が保留です。\n'
        '\n'
        '- **ファイルモード(技術判断・先に解決):** `save` が使う `tempfile.mkstemp` は、保存ファイルのモードを 0600 にします。従来の `write_text` は umask 依存で、通常は 0644 でした。仕様に権限の定めはありません。\n'
        '- **Git 権限(上のモード判断が解決してから別途確認):** AC9 の fixture ローカルのコミットと `git revert` は、現時点で権限がありません。権限が得られるまで T4 は止めたままで、AC9 は未検証です。\n'
        '\n'
        '質問は次の1つです。保存ファイルのモードをどうしますか。\n'
        '\n'
        '1. 従来どおり umask 依存に戻す。`os.replace` の前に、既存ファイルのモードか、`0o666 & ~umask` を適用します。\n'
        '2. 0600 を許容する。他プロセスが保存ファイルを読む前提が無いなら、0600 でも問題ありません。\n'
        '\n'
        '私の推奨は 1 です。理由は、本変更の目的外で、既存の権限が変わるためです。\n'
        '\n'
        '回答があるまで、実装と T4 には進みません。'
    )

    def test_copy_pause_variant_exact_full_result_is_observed(self):
        for phrase in ('回答があるまで、実装と T4 には進みません。',self.actual_copy_pause):
            with self.subTest(phrase=phrase):
                gate=self.gate(policy=self.policy,result={'subtype':'success','is_error':False,'result':phrase})
                self.assertTrue(gate['observed_pause'])
                self.assertTrue(gate['sent'])

    def test_copy_pause_variant_child_callback_transmits_exact_queued_user(self):
        self.assert_callback_reply(self.actual_copy_pause,continuation=True,reply='SYNTHETIC FIXTURE USER REPLY: Choose option 2: mode 0600 is acceptable for this disposable fixture settings file; no cross-user filesystem access is required. This is only the file-mode decision and grants no Git operation. Keep the existing T1-T3 implementation unchanged. Independently read the complete already-selected installed ains-build/SKILL.md without truncation for ordinary body provenance, not native injection. Then retain the pending AC9 execution-authority checkpoint with the exact four app/test paths.')

    def test_copy_pause_variant_preserves_health_context_spec_and_policy_gates(self):
        result={'subtype':'success','is_error':False,'result':self.actual_copy_pause}
        for unhealthy in ({**result,'subtype':'error'},{**result,'is_error':True},
                          {'subtype':'success','result':self.actual_copy_pause}):
            self.assertFalse(self.gate(policy=self.policy,result=unhealthy)['sent'])
        for which in ('initial','current'):
            artifacts=self.artifacts()
            artifacts['docs/changes/notification/tasks.md']['text']='---\nstatus: draft\n---'
            self.assertFalse(self.gate(policy=self.policy,result=result,**{which:artifacts})['sent'])
        current=self.artifacts();current['docs/changes/notification/spec.md']['text']+='\nchanged scope'
        self.assertFalse(self.gate(policy=self.policy,result=result,current=current)['sent'])
        for policy in ({**self.policy,'stage':'ains-spec'},{**self.policy,'name':'unknown'}):
            self.assertFalse(self.gate(policy=policy,result=result)['sent'])

    def test_actual_checkpoint_callback_forwards_approved_build_codechanged_decision(self):
        self.assert_callback_reply('T1–T3 implemented, 15 tests pass. 停止: AC9 requires authority. 許可をください。')

    def assert_callback_reply(self,result_text,continuation=False,reply=None):
        reply=self.decision if reply is None else reply
        # Exercise the real collector callback ordering without launching a model.
        with tempfile.TemporaryDirectory() as tmp:
            bound,_=m.helper(pathlib.Path(tmp)/'sink');bound.OUT.mkdir()
            initial=self.completed_artifacts() if continuation else self.artifacts()
            current=json.loads(json.dumps(initial))
            if not continuation:current['app/settings.py']={'sha256':'after','text':'approved implementation'}
            ns=bound.run.__globals__;ns['contributors']=lambda root:{}
            ns['snapshot']=lambda root:initial if not changed else current
            row=self.continuation_row() if continuation else self.row
            changed=False;prompts=[row['first_business_input']]
            original_save=ns['save']
            def checkpoint(name,value):
                nonlocal changed
                original_save(name,value)
                if name.endswith('-checkpoints') and len(value['turns'])==1:
                    self.assertEqual(value['turns'][0]['result'],result_text)
                    self.assertEqual(value['turns'][0]['subtype'],'success')
                    self.assertIs(value['turns'][0]['is_error'],False)
                    changed=True
                    reply_file=pathlib.Path(tmp)/'turn-1.json';reply_file.write_text(json.dumps(reply))
                    m.checkpoint_reply(reply_file,prompts,value['turns'],original_save)
            ns['save']=checkpoint
            event={'type':'result','subtype':'success','is_error':False,
                   'result':result_text}
            payload=(json.dumps(event)+'\n').encode();original=subprocess.Popen
            script=('import sys,os,json; sys.stdin.readline(); os.write(1,'+repr(payload)+'); '
                    'reply=sys.stdin.readline(); '
                    'print(json.dumps({"type":"result","subtype":"success","is_error":False,"result":json.loads(reply)["message"]["content"]})) if reply else None')
            def child(*a,**kw):return original([sys.executable,'-c',script],**kw)
            # Old collector runs its existing gate for the RED reproduction.
            kwargs={}
            if hasattr(m,'build_reply_policy'):
                kwargs['synthetic_reply_policy']=m.build_reply_policy(row,initial)
            with mock.patch.object(subprocess,'Popen',side_effect=child),contextlib.redirect_stdout(io.StringIO()):
                result=bound.run('synthetic-build-gate',pathlib.Path(tmp),prompts,timeout=1,**kwargs)
            self.assertFalse(result['input_gate_blocked'])
            self.assertEqual(len(result['controlled_stdin']),2)
            self.assertEqual(result['controlled_stdin'][1]['input']['message']['content'],reply)
            self.assertEqual(len(result['turns']),2)
            self.assertEqual(result['turns'][1]['result'],reply)


class Preparation(unittest.TestCase):
    def test_checkpoint_wait_uses_bounded_600_seconds_and_never_silence_consent(self):
        with tempfile.TemporaryDirectory() as tmp:
            reply=pathlib.Path(tmp)/'turn-1.json';prompts=['first'];saved=[]
            def arrive(_):reply.write_text(json.dumps('actual USER answer'))
            with mock.patch.object(m.time,'monotonic',side_effect=[10,10,609]),mock.patch.object(m.time,'sleep',side_effect=arrive):
                m.checkpoint_reply(reply,prompts,[{'subtype':'success','is_error':False}],lambda *x:saved.append(x))
            self.assertEqual(prompts,['first','actual USER answer']);self.assertFalse(saved)
            reply.unlink();prompts=['first']
            with mock.patch.object(m.time,'monotonic',side_effect=[10,610]):
                m.checkpoint_reply(reply,prompts,[{'subtype':'success'}],lambda *x:saved.append(x))
            self.assertEqual(prompts,['first']);self.assertIn('UNVERIFIED',saved[-1][1]['status'])
            reply.write_text(json.dumps('too late'))
            with mock.patch.object(m.time,'monotonic',side_effect=[10,611]):
                m.checkpoint_reply(reply,prompts,[{'subtype':'success'}],lambda *x:saved.append(x))
            self.assertEqual(prompts,['first'])
            reply.write_text(json.dumps({'stop':True}))
            with mock.patch.object(m.time,'monotonic',side_effect=[10,10]):
                self.assertTrue(m.checkpoint_reply(reply,prompts,[{'subtype':'success'}],lambda *x:saved.append(x)))
            self.assertEqual(prompts,['first'])
            reply.write_text(json.dumps({'approve':True}))
            with mock.patch.object(m.time,'monotonic',side_effect=[10,10]):
                with self.assertRaises(ValueError):m.checkpoint_reply(reply,prompts,[{'subtype':'success'}],lambda *x:saved.append(x))
            self.assertEqual(prompts,['first'])
            self.assertTrue(all(r['reply_wait_seconds']==600 and r['turn_timeout_seconds']==180 for r in m.rows()))

    def test_failed_checkpoint_never_consumes_next_user_reply(self):
        with tempfile.TemporaryDirectory() as tmp:
            reply=pathlib.Path(tmp)/'turn-1.json';reply.write_text(json.dumps('actual USER reply'))
            for turns in [[],[{'subtype':'error','is_error':True}],[{'subtype':'success'},{'subtype':'error'}]]:
                prompts=['first'];saved=[]
                with mock.patch.object(m.time,'sleep',side_effect=AssertionError('must not wait')):
                    m.checkpoint_reply(reply,prompts,turns,lambda *x:saved.append(x))
                self.assertEqual(prompts,['first']);self.assertIn('UNVERIFIED',saved[0][1]['status'])

    def test_import_is_side_effect_free_and_bound_helper_skips_fixed_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=pathlib.Path(tmp)/'never-created'
            with mock.patch.object(pathlib.Path,'mkdir',side_effect=AssertionError('unexpected mkdir')):
                bound,receipt=m.helper(target)
            self.assertEqual(bound.run.__globals__['OUT'],target)
            self.assertFalse(target.exists());self.assertFalse(receipt['normal_import_executed'])
            self.assertTrue(receipt['top_level_fixed_OUT_and_mkdir_and_main_excluded'])
    def test_no_legacy_driver_imports_in_fixture_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=pathlib.Path(tmp)/'fresh';bound,_=m.helper(out)
            fixture,receipt=m.load_definitions(PATH.with_name('suite.py'),out,True,{'r':bound})
            self.assertIs(fixture.fixture.__globals__['r'],bound)
            self.assertTrue(any(x['kind']=='non-stdlib import' for x in receipt['excluded_nodes']))
            self.assertFalse(out.exists())
    def test_recipe_exact_originals_and_all_groups(self):
        rows=m.rows();ids=[x['id'] for x in rows]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(set(g for r in rows for g in r['groups']),{'D1','D2','D3','D4','D5','D6'})
        originals=m.corpus()
        mapped={r['fixture']:r for r in rows if r['fixture'] in originals}
        self.assertEqual(set(mapped),set(m.ORIGINALS[:-1]))
        self.assertTrue(any(r['fixture']==m.ORIGINALS[-1]+':carried-fixture-Git' for r in rows))
        for name,row in mapped.items():self.assertEqual(row['first_business_input'],originals[name]['prompt'])
        self.assertEqual(sum('D4' in r['groups'] for r in rows),8)
    def test_exact_metadata_inventory(self):
        x=m.metadata_check();self.assertEqual(len(x['manual_names']),10);self.assertEqual(len(x['automatic_names']),6)
    def test_collector_partial_line_deadline_is_retained_without_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            bound,_=m.helper(pathlib.Path(tmp)/'sink');bound.OUT.mkdir()
            ns=bound.run.__globals__;ns['contributors']=lambda root:{};ns['snapshot']=lambda root:{}
            original=subprocess.Popen
            def python_child(*args,**kw):
                return original([sys.executable,'-c','import os,time; os.write(1,b"partial"); time.sleep(.8)'],**kw)
            with mock.patch.object(subprocess,'Popen',side_effect=python_child),contextlib.redirect_stdout(io.StringIO()):
                result=bound.run('synthetic-only',pathlib.Path(tmp),['synthetic fixture input'],timeout=.08)
            self.assertTrue(result['timeout']);self.assertLess(result['elapsed'],.7)
            self.assertEqual(result['stream_accounting']['stdout']['partial_lines'],1)
    def test_collector_retains_post_terminal_json_and_redacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            bound,_=m.helper(pathlib.Path(tmp)/'sink');bound.OUT.mkdir();ns=bound.run.__globals__;ns['contributors']=lambda root:{};ns['snapshot']=lambda root:{}
            secret='SYNTHETIC_ONLY_0123456789abcdef'
            events=[{'type':'result','subtype':'success','is_error':False,'result':'done'},
                    {'type':'assistant','message':{'role':'assistant','content':[{'type':'text','text':'Bearer '+secret}]}}]
            payload=('\n'.join(map(json.dumps,events))+'\n').encode();original=subprocess.Popen
            def child(*a,**kw):return original([sys.executable,'-c','import os; os.write(1,'+repr(payload)+')'],**kw)
            with mock.patch.object(subprocess,'Popen',side_effect=child),contextlib.redirect_stdout(io.StringIO()):
                result=bound.run('synthetic-only',pathlib.Path(tmp),['synthetic fixture input'],timeout=1)
            self.assertEqual(len(result['all_sanitized_stream_events']),2)
            self.assertNotIn(secret,json.dumps(result));self.assertFalse(result['final_drain_incomplete'])


if __name__=='__main__':unittest.main()
