"""Model-free native boundary/oracle/recipe tests; no legacy main is called."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location('native_delta',Path(__file__).with_name('native_delta.py'))
n=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(n)

class NativeDeltaTests(unittest.TestCase):
    def test_nullable_outputs_skip_candidates_but_keep_successful_body(self):
        body='Actual complete body'
        for value in [None,42,{},[],False]:
            with self.subTest(value=value):
                events=[{'params':{'item':{'type':'commandExecution','command':'cat .agents/skills/ains-spec/SKILL.md','aggregatedOutput':value}}},
                        {'params':{'item':{'type':'commandExecution','command':'cat .agents/skills/ains-spec/SKILL.md','aggregatedOutput':body}}}]
                result=n.native_oracle(events,'read',{'ains-spec':body},{'ains-spec':'/fixture/.agents/skills/ains-spec/SKILL.md'})
                self.assertEqual([x['event_index'] for x in result['N5_installed_body_consumption']],[1])
                self.assertFalse(result['native_successes'])

    def test_strict_terminal_checks_entire_cli_and_live_sequence(self):
        for transport in ['cli','live']:
            def event(kind,status=None,error=None):
                if transport=='cli':
                    value={'type':kind.replace('/','.')}
                    if status is not None:value['status']=status
                    if error is not None:value['error']=error
                    return value
                return {'method':kind,'params':{'turn':{'status':status,'error':error}}}
            completed=event('turn/completed','completed')
            self.assertTrue(n.healthy_terminal([completed],transport))
            for tail in [event('turn/started'),event('turn/cancelled'),event('turn/aborted'),event('error'),event('turn/failed')]+[event('turn/completed',status) for status in ['failed','error','cancelled','aborted','inProgress','invalid']]+[event('turn/completed','completed',{'message':'bad'})]:
                with self.subTest(transport=transport,tail=tail):
                    self.assertFalse(n.healthy_terminal([completed,tail],transport))
            self.assertTrue(n.healthy_terminal([completed,event('turn/started'),completed],transport))

    def test_explicit_manifest_binds_actual_release_and_checks_hashes_modes_inventory(self):
        import json
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);files={}
            for name in n.MANUAL|n.AUTO:
                p=root/'skills'/name/'SKILL.md';p.parent.mkdir(parents=True);p.write_text(name)
                files[str(p.relative_to(root))]={'sha256':n.sha(p),'mode':oct(p.stat().st_mode&0o777)}
            manifest=root/'explicit.json';data={'release':'source-native-r5','suite_files':files,'suite_skill_metadata_sha256':{k:v['sha256'] for k,v in files.items()}}
            manifest.write_text(json.dumps(data))
            with mock.patch.object(n,'SOURCE',root):
                self.assertEqual(n.released_source(manifest)['release'],'source-native-r5')
                first=next(iter(files));data['suite_files'][first]['mode']='0o000';manifest.write_text(json.dumps(data))
                with self.assertRaisesRegex(RuntimeError,'mode drift'):n.released_source(manifest)
                data['suite_files'][first]['mode']=oct((root/first).stat().st_mode&0o777);manifest.write_text(json.dumps(data))
                (root/first).write_text('drift')
                with self.assertRaisesRegex(RuntimeError,'drift'):n.released_source(manifest)

    def test_default_import_has_no_runtime_helper_import(self):
        self.assertNotIn('runtime',n.__dict__)
        self.assertNotIn('activation_r3',n.__dict__)

    def test_actual_helpers_bound_before_import_mkdir(self):
        with tempfile.TemporaryDirectory() as directory:
            sink=(Path(directory)/'fresh').resolve()
            with n.bound_helpers(sink) as (helpers,receipt):
                self.assertEqual(helpers['runtime'].OUT,sink)
                self.assertEqual(helpers['activation_recheck'].OUT,sink)
                self.assertTrue(sink.is_dir())
                self.assertEqual(sum(x['OUT_assignment_rebound'] for x in receipt),1)
                self.assertTrue(all(not x['function_bodies_changed'] for x in receipt))
                self.assertEqual(list(sink.iterdir()),[])

    def test_recognition_and_consumption_are_separate(self):
        body='---\nname: ains-spec\n---\nActual fixture body.\n'
        event={'type':'item.completed','item':{'type':'command_execution','command':'cat .agents/skills/ains-spec/SKILL.md','aggregated_output':body,'exit_code':0,'status':'completed'}}
        observed=n.native_oracle([event],'Please read this document',{'ains-spec':body},{'ains-spec':'/fixture/.agents/skills/ains-spec/SKILL.md'})
        self.assertEqual(len(observed['N5_installed_body_consumption']),1)
        self.assertEqual(observed['N4']['recognition'],'UNVERIFIED')
        self.assertFalse(observed['ordinary_reads_are_native_failure'])
        self.assertFalse(observed['native_successes'])
        self.assertEqual(n.native_oracle([], '$ains-spec draft',{}, {},{'status':'BOUND_ACTUAL_RECEIPTS','semantic_source':n.SEMANTIC_COMMIT,'catalog':{'enabled_unique_targets':16}})['N4']['recognition'],'SOURCE_BOUND_NATIVE_SELECTOR')
        self.assertEqual(n.native_oracle([], '$ains-spec draft',{}, {},False)['N4']['recognition'],'UNVERIFIED')

    def test_read_from_wrong_source_does_not_prove_installed_consumption(self):
        body='Original body'
        event={'item':{'type':'command_execution','command':'cat /source/skills/ains-spec/SKILL.md','aggregated_output':body}}
        observed=n.native_oracle([event],'read',{'ains-spec':body},{'ains-spec':'/fixture/.agents/skills/ains-spec/SKILL.md'})
        self.assertFalse(observed['N5_installed_body_consumption'])

    def test_all_ten_native_successes_and_rejections_distinguished(self):
        for name in n.MANUAL:
            with self.subTest(name=name):
                actual={'skill':name,'schema_source_sha256':'a'*64,'retained_event_indexes':[3],'status':'succeeded'}
                good=n.native_oracle([],n.NEGATIVE_SPEC,{}, {},native_outcomes=[actual])
                self.assertEqual(good['negative_observation'],'NATIVE_MANUAL_ACTIVATION')
                rejected=copy.deepcopy(actual);rejected['status']='rejected'
                no=n.native_oracle([],n.NEGATIVE_SPEC,{}, {},native_outcomes=[rejected])
                self.assertFalse(no['native_successes']);self.assertTrue(no['rejected_native_attempts'])
                self.assertEqual(no['negative_observation'],'UNVERIFIED')
                unknown=copy.deepcopy(actual);unknown.pop('schema_source_sha256')
                self.assertEqual(n.native_oracle([],n.NEGATIVE_SPEC,{}, {},native_outcomes=[unknown])['negative_observation'],'UNVERIFIED')

    def test_prose_and_ordinary_helper_do_not_become_native_invocation(self):
        events=[{'item':{'type':'agent_message','text':'I invoked ains-build successfully'}},
                {'item':{'type':'command_execution','command':'bash .agents/skills/ains-spec/scripts/new-change.sh fixture','aggregated_output':'docs/changes/fixture'}}]
        result=n.native_oracle(events,n.NEGATIVE_SPEC,{}, {})
        self.assertFalse(result['native_successes'])
        self.assertEqual(result['N4']['recognition'],'UNVERIFIED')
        self.assertEqual(result['negative_observation'],'NO_NATIVE_MANUAL_EVENT_OBSERVED')

    def test_recipe_keeps_exact_cases_fresh_negatives_and_bounds(self):
        rows=n.rows();ids=[r['id'] for r in rows]
        self.assertEqual(len(ids),len(set(ids)))
        for mode in ['default','copy']:
            self.assertEqual(next(r for r in rows if r['id']==mode+'-unnamed-spec')['initial_user_text'],n.NEGATIVE_SPEC)
            self.assertEqual(next(r for r in rows if r['id']==mode+'-unnamed-build')['initial_user_text'],n.NEGATIVE_BUILD)
        self.assertTrue(all(case in {r['fixture'] for r in rows} for _,case in n.CASES))
        self.assertEqual(next(r for r in rows if r['id']=='default-original-spec')['initial_user_text'],n.original_prompt(*n.CASES[0]))
        self.assertTrue(all(r['terminal_deadline_seconds']==180 for r in rows))
        self.assertEqual(n.MANUAL|n.AUTO,{p.parent.name for p in (n.SOURCE/'skills').glob('*/SKILL.md')})

    def test_run_requires_reviewed_version_binding_before_process_or_fixture_use(self):
        import argparse,json
        from unittest import mock
        with tempfile.TemporaryDirectory() as directory:
            prepared=Path(directory)
            manifest=n.SOURCE/'.omx/ultragoal/evidence/source-native-r4/manifest.json'
            n.write(prepared/'recipe.json',{'release_manifest':str(manifest),'release_manifest_sha256':n.sha(manifest),'adapter_sha256':n.sha(n.__file__)})
            args=argparse.Namespace(release_id='synthetic-unit-only',prepared=str(prepared),native_binding=None)
            with mock.patch.object(n,'released_source'),mock.patch.object(n.subprocess,'run') as child:
                with self.assertRaisesRegex(RuntimeError,'current-version native selector binding'):
                    n.run_row(args)
                child.assert_not_called()

    def test_catalog_rejects_disabled_duplicate_wrong_path_and_errors(self):
        expected=[{'name':name,'path':'/fixture/.agents/skills/'+name+'/SKILL.md','realpath':'/fixture/.agents/skills/'+name+'/SKILL.md'} for name in sorted(n.MANUAL|n.AUTO)]
        entries=[dict(x,enabled=True) for x in expected]
        cfg={'features':dict.fromkeys(n.CANONICAL_FEATURES,False)}
        facts=n.config_facts({'config':cfg,'layers':[{'name':{'type':'user','file':'/fixture-home/.codex/config.toml','profile':None},'config':cfg}]},lambda c:{'top_level_keys':sorted(c)})
        catalog={'data':[{'cwd':'/fixture','skills':entries,'errors':[]}]}
        self.assertEqual(n.validate_catalog(catalog,expected,facts,'cli')['enabled_unique_targets'],16)
        for mutation in ['disabled','duplicate','path','errors']:
            with self.subTest(mutation=mutation):
                bad=copy.deepcopy(catalog)
                if mutation=='disabled':bad['data'][0]['skills'][0]['enabled']=False
                if mutation=='duplicate':bad['data'][0]['skills'].append(entries[0])
                if mutation=='path':bad['data'][0]['skills'][0]['path']='/other/SKILL.md'
                if mutation=='errors':bad['data'][0]['errors']=[{'message':'fixture load error'}]
                with self.assertRaises(RuntimeError):n.validate_catalog(bad,expected,facts,'cli')
        badfacts=copy.deepcopy(facts);badfacts['layers'][0]['facts']['skill_settings']=[{'name':'ains','enabled':False}]
        with self.assertRaisesRegex(RuntimeError,'disabled setting'):n.validate_catalog(catalog,expected,badfacts,'cli')

    def test_config_facts_never_include_raw_config_values(self):
        import json
        raw={'config':{'developer_instructions':'PRIVATE-CONFIG-BODY','mcp_servers':{'sample':{'env':{'TOKEN':'PRIVATE-MCP-VALUE'}}},'features':{'executor_capability_discovery_v2':True}},'layers':[]}
        raw['config']['skills']=None
        facts=n.config_facts(raw,lambda c:{'top_level_keys':sorted(c)})
        serialized=json.dumps(facts)
        self.assertNotIn('PRIVATE-CONFIG-BODY',serialized);self.assertNotIn('PRIVATE-MCP-VALUE',serialized)
        self.assertTrue(facts['effective']['discovery']['executor_capability_discovery_v2'])
        self.assertFalse(facts['effective']['discovery']['executor_capability_discovery'])

    def test_environment_presence_needs_exact_parent_structural_receipt(self):
        facts={'selector_names':[],'default_home':True,'default_codex_home':True,'selected_environment_file':{'path':'/fixture/environments.toml','sha256':'a'*64,'exists':False}}
        self.assertEqual(n.require_environment(facts,{})['required_skills'],[])
        facts['selected_environment_file']['exists']=True
        with self.assertRaisesRegex(RuntimeError,'parent-bound structural'):n.require_environment(facts,{})
        facts['selector_names']=['CODEX_EXEC_SERVER_URL']
        with self.assertRaisesRegex(RuntimeError,'remote/noise'):n.require_environment(facts,{})

    def test_boolean_cannot_supply_native_recognition_or_healthy_terminal(self):
        self.assertEqual(n.native_oracle([],'$ains-spec draft',{}, {},True)['N4']['recognition'],'UNVERIFIED')
        self.assertFalse(n.healthy_terminal([],'cli'))
        self.assertFalse(n.healthy_terminal([{'type':'turn.completed'},{'type':'error'}],'cli'))
        self.assertTrue(n.healthy_terminal([{'type':'item.completed','item':{'type':'command_execution','exit_code':1}},{'type':'turn.completed'}],'cli'))
        self.assertFalse(n.healthy_terminal([{'method':'turn/completed','params':{'turn':{'status':'failed'}}}],'live'))

class PostStartBaselineTests(unittest.TestCase):
    def test_whole_config_identity_preserves_unknown_values_and_private_hashes(self):
        import json
        cfg={'unknown':{'same_key':1},'developer_instructions':'PRIVATE-INSTRUCTION',
             'model_providers':{'custom':{'api_key':'PRIVATE-TOKEN','url':'https://user:password@host/path?token=SECRET','headers':{'X-Custom':'PRIVATE-HEADER'},'args':['--token','PRIVATE-ARG']}}}
        first=n.safe_config_identity(cfg)
        encoded=json.dumps(first)
        for secret in ['PRIVATE-INSTRUCTION','PRIVATE-TOKEN','password','SECRET','PRIVATE-HEADER','PRIVATE-ARG']:
            self.assertNotIn(secret,encoded)
        changed=copy.deepcopy(cfg);changed['unknown']['same_key']=2
        self.assertNotEqual(first,n.safe_config_identity(changed))
        changed=copy.deepcopy(cfg);changed['developer_instructions']='other private instructions'
        self.assertNotEqual(first,n.safe_config_identity(changed))
        changed=copy.deepcopy(cfg);changed['model_providers']['custom']['api_key']='another credential'
        self.assertEqual(first,n.safe_config_identity(changed))
        self.assertNotEqual(n.safe_config_identity({'route':'https://host?api-version=one'}),
                            n.safe_config_identity({'route':'https://host?api-version=two'}))

    def startup_lookup_case(self,work,kind='active'):
        root=work/'repo';cwd=root/'nested';cwd.mkdir(parents=True)
        if kind!='projectless':
            (root/'.git').mkdir();(root/'.git/HEAD').write_text('ref: refs/heads/main')
        user={'type':'user','file':str(work/'user-config'),'profile':None}
        projects={} if kind=='projectless' else {str(root):{'trust_level':'trusted'}}
        cfg={'config':{'projects':projects},'layers':[{'name':user,'version':'fixed','disabledReason':None,'config':{}}], 'origins':{}}
        return root,cwd,cfg

    def test_source_bound_active_lookup_precedence_and_no_trust_promotion(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);root,cwd,cfg=self.startup_lookup_case(work)
            selected=n.startup_lookup(cfg,cwd,root)
            self.assertEqual(selected['active_project']['category'],'repo-original')
            self.assertEqual(selected['skip_predicate'],'existing-active-project')
            cfg['config']['projects'][str(cwd)]={'trust_level':'untrusted'}
            value=n.startup_lookup(cfg,cwd,root)
            self.assertEqual(value['active_project']['trust'],'untrusted')
            self.assertEqual(value['active_project']['category'],'cwd-original')
            cfg['config']['projects'][str(cwd)]={}
            value=n.startup_lookup(cfg,cwd,root)
            self.assertIsNone(value['active_project']['trust']);self.assertEqual(value['skip_predicate'],'UNKNOWN')
            # A configured arbitrary ancestor is not get_active_project.
            cfg['config']['projects']={str(work):{'trust_level':'trusted'}}
            self.assertIsNone(n.startup_lookup(cfg,cwd,root)['active_project'])
            # POSIX canonical wins over a conflicting literal alias.
            alias=work/'alias';alias.symlink_to(root,target_is_directory=True)
            cfg['config']['projects']={str(cwd.resolve()):{'trust_level':'untrusted'},str(alias/'nested'):{'trust_level':'trusted'}}
            value=n.startup_lookup(cfg,alias/'nested',root)
            self.assertEqual(value['active_project']['trust'],'untrusted');self.assertEqual(value['active_project']['category'],'cwd-canonical')
            cfg['config']['projects']['/unrelated-PRIVATE-PATH']={'trust_level':'trusted','token':'SECRET'}
            text=json.dumps(n.startup_lookup(cfg,alias/'nested',root))
            self.assertNotIn('PRIVATE-PATH',text);self.assertNotIn('SECRET',text);self.assertNotIn('projects',text)

    def test_unchanged_no_write_requires_explicit_fresh_classification_and_whole_equality(self):
        for kind in ['active','projectless']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);root,cwd,cfg=self.startup_lookup_case(work,kind)
                if kind=='active':cfg['config']['projects'][str(root)]['trust_level']='untrusted'
                before=n.startup_lookup(cfg,cwd,root);files={str(work/'user'):{'sha256':'unchanged'}}
                contract={'mode':before['skip_predicate'],'before':before,'after':copy.deepcopy(before)}
                with self.assertRaises(RuntimeError):n.validate_startup(cfg,cfg,files,files,str(root),'/user',{}, {})
                self.assertEqual(n.validate_no_write_startup(cfg,cfg,files,files,str(root),'/user',{}, {},contract),'unchanged-source-bound-no-write')
                for mutation in ['config','files','raw-user','classification','mode','origin','project-activation']:
                    post=copy.deepcopy(cfg);after=copy.deepcopy(files);u={};c=copy.deepcopy(contract)
                    if mutation=='config':post['config']['unknown']='different'
                    if mutation=='files':after[str(work/'user')]['sha256']='changed'
                    if mutation=='raw-user':u={'projects':{str(root):{'trust_level':'trusted'}}}
                    if mutation=='classification':c['after']['skip_predicate']='UNKNOWN'
                    if mutation=='mode':c['mode']='trusted-waiver'
                    if mutation=='origin':post['origins']['unknown']={'version':'new'}
                    if mutation=='project-activation':post['layers'].append({'name':{'type':'project'},'version':'new','config':{}})
                    with self.subTest(mutation=mutation),self.assertRaises(RuntimeError):n.validate_no_write_startup(cfg,post,files,after,str(root),'/user',{},u,c)

    def test_proposed_current_lookup_receipt_binds_source_recipe_binary_and_candidate(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);root,cwd,cfg=self.startup_lookup_case(work)
            recipe=work/'recipe.json';manifest=work/'manifest.json';n.write(recipe,{});n.write(manifest,{})
            binding={'executable_identity':{'sha256':'actual-synthetic-binary'}}
            receipt={'schema':'startup-no-write-current-v1','collector_sha256':n.sha(n.__file__),
                'recipe_sha256':n.sha(recipe),'manifest_sha256':n.sha(manifest),'binary_sha256':'actual-synthetic-binary',
                'classification':n.startup_lookup(cfg,cwd,root),'mode':'existing-active-project'}
            path=work/'current.json'
            for field in ['none','schema','collector_sha256','recipe_sha256','manifest_sha256','binary_sha256','classification','mode']:
                bad=copy.deepcopy(receipt)
                if field!='none':bad[field]='wrong'
                n.write(path,bad);ref={'path':str(path),'sha256':n.sha(path)}
                with self.subTest(field=field):
                    if field=='none':self.assertEqual(n.bind_startup_no_write(ref,cfg,cwd,root,recipe,manifest,binding)['before'],receipt['classification'])
                    else:
                        with self.assertRaises(RuntimeError):n.bind_startup_no_write(ref,cfg,cwd,root,recipe,manifest,binding)
            n.write(path,receipt);ref={'path':str(path),'sha256':n.sha(path)}
            (root/'.git/HEAD').unlink()
            with self.assertRaises(RuntimeError):n.bind_startup_no_write(ref,cfg,cwd,root,recipe,manifest,binding)

    def test_projectless_all_three_conditions_unknown_metadata_and_sources_fail_closed(self):
        from unittest import mock
        import contextlib
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);root,cwd,cfg=self.startup_lookup_case(work,'projectless')
            self.assertEqual(n.startup_lookup(cfg,cwd,root)['skip_predicate'],'projectless')
            cfg['layers'].append({'name':{'type':'project','dotCodexFolder':str(root/'.codex')},'version':'fixed','config':{}})
            self.assertEqual(n.startup_lookup(cfg,cwd,root)['skip_predicate'],'UNKNOWN')
            cfg['layers'].pop();(root/'.git').mkdir();(root/'.git/HEAD').write_text('ref: main')
            self.assertEqual(n.startup_lookup(cfg,cwd,root)['skip_predicate'],'UNKNOWN')
            cfg['config']['project_root_markers']=[];cfg['layers'][0]['config']['project_root_markers']=[]
            self.assertEqual(n.startup_lookup(cfg,cwd,root)['skip_predicate'],'UNKNOWN') # checkout still present
            (root/'.git/HEAD').unlink();(root/'.git').rmdir();(root/'MARKER').write_text('')
            cfg['config']['project_root_markers']=['MARKER'];cfg['layers'][0]['config']['project_root_markers']=['MARKER']
            self.assertEqual(n.startup_lookup(cfg,cwd,root)['skip_predicate'],'UNKNOWN')
            for mutation in ['pointer','missing-layer-version','unknown-layer','wrong-root','missing-cwd','marker-unknown','source']:
                bad=copy.deepcopy(cfg);target=cwd;bound=root
                if mutation=='pointer':(root/'.git').write_text('gitdir: unsupported')
                if mutation=='missing-layer-version':bad['layers'][0].pop('version')
                if mutation=='unknown-layer':bad['layers'][0]['name']['type']='unknown'
                if mutation=='wrong-root':bound=work/'other'
                if mutation=='missing-cwd':target=work/'absent'
                if mutation=='marker-unknown':bad['layers'][0]['config']['project_root_markers']=None
                patch=mock.patch.object(n,'sha',return_value='not-pinned') if mutation=='source' else contextlib.nullcontext()
                with self.subTest(mutation=mutation),patch,self.assertRaises((RuntimeError,OSError)):n.startup_lookup(bad,target,bound)
                if mutation=='pointer':(root/'.git').unlink()

    def test_startup_marker_lstat_rejects_dangling_and_live_symlinks_before_receipt_binding(self):
        for marker in ['.git','MARKER']:
            for position in ['cwd','ancestor']:
                for dangling in [True,False]:
                    with self.subTest(marker=marker,position=position,dangling=dangling),tempfile.TemporaryDirectory() as tmp:
                        work=Path(tmp);root,cwd,cfg=self.startup_lookup_case(work,'projectless')
                        if marker=='MARKER':
                            cfg['config']['project_root_markers']=['MARKER']
                            cfg['layers'][0]['config']['project_root_markers']=['MARKER']
                        # Capture the actual ordinary-missing candidate first;
                        # adding unsupported metadata must invalidate it before
                        # any thread/start or accepted no-write relation.
                        classification=n.startup_lookup(cfg,cwd,root)
                        self.assertEqual(classification['skip_predicate'],'projectless')
                        recipe=work/'recipe.json';manifest=work/'manifest.json';n.write(recipe,{});n.write(manifest,{})
                        receipt=work/'current.json';n.write(receipt,{'schema':'startup-no-write-current-v1',
                            'collector_sha256':n.sha(n.__file__),'recipe_sha256':n.sha(recipe),'manifest_sha256':n.sha(manifest),
                            'binary_sha256':'synthetic','mode':'projectless','classification':classification})
                        ref={'path':str(receipt),'sha256':n.sha(receipt)}
                        target=work/'absent'
                        if not dangling:
                            target.mkdir();(target/'HEAD').write_text('synthetic')
                        link=(cwd if position=='cwd' else root)/marker;link.symlink_to(target,target_is_directory=True)
                        self.assertTrue(link.is_symlink());self.assertEqual(link.exists(),not dangling)
                        with self.assertRaisesRegex(RuntimeError,'unsupported startup marker symlink'):n.startup_lookup(cfg,cwd,root)
                        with self.assertRaisesRegex(RuntimeError,'unsupported startup marker symlink'):
                            n.bind_startup_no_write(ref,cfg,cwd,root,recipe,manifest,{'executable_identity':{'sha256':'synthetic'}})

    def test_only_exact_persisted_startup_trust_transition_is_classified(self):
        before={'model':'default','projects':{}}
        after={'model':'default','projects':{'/fixture':{'trust_level':'trusted'}}}
        self.assertEqual(n.startup_relation(before,after,'/fixture'),'persisted-trust-only')
        for mutation in ['unknown','activation','fallback']:
            bad=copy.deepcopy(after)
            if mutation=='unknown':bad['new_setting']=True
            if mutation=='activation':bad['projects']['/other']={'trust_level':'trusted'}
            if mutation=='fallback':bad['projects']={}
            with self.subTest(mutation=mutation):
                with self.assertRaises(RuntimeError):n.startup_relation(before,bad,'/fixture')

    def test_snapshot_matches_explicit_overlays_not_config_defaults(self):
        request={'cwd':'/fixture','model':'typed-model','approvalPolicy':'never','sandbox':'workspace-write','ephemeral':True}
        expected={k:None for k in n.THREAD_FIELDS}
        expected.update(model='typed-model',modelProvider='openai',cwd='/fixture',runtimeWorkspaceRoots=['/fixture'],
            approvalPolicy='never',sandbox={'type':'workspaceWrite','networkAccess':False},instructionSources=[],multiAgentMode='explicitRequestOnly')
        actual=dict(expected,thread={'id':'actual-thread','cwd':'/fixture','model':'typed-model','modelProvider':'openai','reasoningEffort':None})
        self.assertEqual(n.reconcile_thread(actual,request,expected,{'model':'configured-default'})['thread_id'],'actual-thread')
        with self.assertRaisesRegex(RuntimeError,'unoverridden default'):
            n.reconcile_thread(actual,request,expected,{'model_provider':'different-configured-provider'})
        self.assertEqual(n.redacted_config({'instructionSources':['/safe/AGENTS.md']}),{'instructionSources':['/safe/AGENTS.md']})
        for field,value in [('model','wrong'),('modelProvider','wrong'),('runtimeWorkspaceRoots',['/other'])]:
            bad=copy.deepcopy(actual);bad[field]=value
            with self.assertRaises(RuntimeError):n.reconcile_thread(bad,request,expected)
        with self.assertRaises(RuntimeError):n.reconcile_thread(actual,request,{})

    def test_two_equal_bundles_freeze_once_and_drift_latches(self):
        sample={'config':{'unknown':1},'raw':{'version':'post','digest':'post'},'catalog':{},'files':{},'environment':{},'installed':{'body':'fixed','metadata':'fixed'}}
        frozen=n.PostStartBaseline(sample,sample)
        frozen.check(copy.deepcopy(sample))
        for key in sample:
            with self.subTest(key=key):
                gate=n.PostStartBaseline(sample,sample);bad=copy.deepcopy(sample);bad[key]={'changed':True}
                with self.assertRaises(RuntimeError):gate.check(bad)
                with self.assertRaises(RuntimeError):gate.check(sample)
        with self.assertRaises(RuntimeError):n.PostStartBaseline(sample,dict(sample,raw={'version':'different'}))
        # Startup raw inequality is diagnostic and is never the baseline gate.
        self.assertNotEqual({'version':'pre'},sample['raw'])

    def test_all_native_premises_and_same_key_policy_changes_are_checked(self):
        data={'config':{'features':dict.fromkeys(n.CANONICAL_FEATURES+n.DISCOVERY_KEYS,False),
            'skills':{'include_instructions':True},'mcp_servers':{'one':{'enabled':False,'command':'/usr/bin/false','tools':{'tool':{'approval':'never'}}}},
            'sandbox':{'network':False},'token_budget':{'budget':10}},'layers':[{'name':{'type':'user'},'version':'fixed','config':{}}]}
        n.native_premises(data,['one'])
        base=n.safe_config_identity(data)
        for key in n.CANONICAL_FEATURES+n.DISCOVERY_KEYS:
            bad=copy.deepcopy(data);bad['config']['features'][key]=True
            with self.subTest(key=key):
                with self.assertRaises(RuntimeError):n.native_premises(bad,['one'])
        for key,value in [('enabled',True),('command','another')]:
            bad=copy.deepcopy(data);bad['config']['mcp_servers']['one'][key]=value
            with self.assertRaises(RuntimeError):n.native_premises(bad,['one'])
        bad=copy.deepcopy(data);bad['config']['mcp_servers']['new']={'enabled':False,'command':'/usr/bin/false'}
        with self.assertRaises(RuntimeError):n.native_premises(bad,['one'])
        for section,key,value in [('sandbox','network',True),('token_budget','budget',20)]:
            bad=copy.deepcopy(data);bad['config'][section][key]=value
            self.assertNotEqual(base,n.safe_config_identity(bad))
        bad=copy.deepcopy(data);bad['config']['mcp_servers']['one']['tools']['tool']['approval']='always'
        self.assertNotEqual(base,n.safe_config_identity(bad))

    def test_startup_raw_delta_retained_and_unknown_source_changes_rejected(self):
        pre={'config':{'projects':{}},'layers':[{'name':{'type':'user','file':'/user'},'version':'pre','config':{'projects':{}}}]}
        post=copy.deepcopy(pre)
        post['config']['projects']['/fixture']={'trust_level':'trusted'}
        post['layers'][0].update(version='post',config=copy.deepcopy(post['config']))
        files={'/user':{'exists':True,'realpath':'/user','sha256':'pre'}}
        after=copy.deepcopy(files);after['/user']['sha256']='post'
        before_bytes=copy.deepcopy(pre)
        self.assertEqual(n.validate_startup(pre,post,files,after,'/fixture','/user',{},post['config']),'persisted-trust-only')
        self.assertEqual(pre,before_bytes);self.assertNotEqual(files,after)
        bad=copy.deepcopy(post);bad['layers'].append({'name':{'type':'project'}})
        with self.assertRaises(RuntimeError):n.validate_startup(pre,bad,files,after,'/fixture','/user',{},post['config'])
        badfiles=copy.deepcopy(after);badfiles['/new']={'exists':True}
        with self.assertRaises(RuntimeError):n.validate_startup(pre,post,files,badfiles,'/fixture','/user',{},post['config'])

    def test_bundle_uses_same_rpc_and_rejects_second_read_before_any_turn(self):
        from unittest import mock
        import types
        cfg={'config':{'features':dict.fromkeys(n.CANONICAL_FEATURES+n.DISCOVERY_KEYS,False),
             'skills':{'include_instructions':True}},'layers':[{'name':{'type':'user'},'version':'fixed','config':{}}]}
        env={'selector_names':[],'default_home':True,'default_codex_home':True,'selected_environment_file':{'exists':False}}
        class RPC:
            args=[n.__file__];p=types.SimpleNamespace(pid=123);env={};bound_thread='same-thread'
            def __init__(self,drift):self.calls=[];self.drift=drift
            def call(self,method,params,timeout):
                self.calls.append((method,params))
                if method=='skills/list':return {'data':[]}
                result=copy.deepcopy(cfg)
                if len(self.calls)==3 and self.drift:result['config']['unknown']={'same_key':'changed'}
                return result
        helper=types.SimpleNamespace(mdm_forced=lambda:{},inventory=lambda root:[])
        helpers={'activation_r3':helper,'activation_closure_probe':types.SimpleNamespace(structural=lambda c:{'keys':sorted(c)})}
        with mock.patch.object(n,'released_source'),mock.patch.object(n,'environment_facts',return_value=env),mock.patch.object(n,'validate_catalog',return_value={'enabled_unique_targets':16}):
            for drift in [False,True]:
                rpc=RPC(drift)
                if drift:
                    with self.assertRaisesRegex(RuntimeError,'Unstable'):n.live_bundle(rpc,Path('/fixture'),[],[],n.__file__,helpers,{'_mcp_names':[],'proof_path':n.__file__},[])
                else:
                    bundle,_=n.live_bundle(rpc,Path('/fixture'),[],[],n.__file__,helpers,{'_mcp_names':[],'proof_path':n.__file__},[])
                    self.assertEqual(bundle['thread_id'],'same-thread');self.assertEqual(bundle['process_id'],123)
                self.assertEqual([x[0] for x in rpc.calls],['config/read','skills/list','config/read'])
                self.assertIs(rpc.calls[1][1]['forceReload'],True)

    def test_retained_actual_0164_thread_start_response_contract(self):
        import json
        wire=n.SOURCE/'.omx/ultragoal/evidence/g004/codex/native-v2/runs-r5-20261025/copy-setup-agents-only/live-rpc/rpc.json'
        self.assertEqual(n.sha(wire),'f96cc470c5959533a4917cb271459d5ead8c28c92a95de9d9fafa0860065b041')
        entries=json.loads(wire.read_text())
        request=next(e['payload']['params'] for e in entries if e['payload'].get('method')=='thread/start')
        actual=next(e['payload']['result'] for e in entries if isinstance(e['payload'].get('result'),dict) and 'instructionSources' in e['payload']['result'])
        self.assertEqual(set(n.THREAD_FIELDS)-set(actual),set())
        self.assertEqual(actual['model'],'gpt-6.1-sol');self.assertEqual(actual['modelProvider'],'openai')
        self.assertIsNone(actual['reasoningEffort']);self.assertIsNone(actual['thread']['reasoningEffort'])
        expected={k:actual[k] for k in n.THREAD_FIELDS}
        self.assertEqual(n.reconcile_thread(actual,request,expected)['thread_id'],actual['thread']['id'])
        # Optional nested null/absence is not an invented producer obligation.
        nullable=copy.deepcopy(actual);nullable['thread'].pop('reasoningEffort')
        n.reconcile_thread(nullable,request,expected)

    def test_actual_api_null_skills_and_source_bound_defaults(self):
        import json
        receipt=json.loads((n.SOURCE/'.omx/ultragoal/evidence/codex-r6-poststart-baseline-fix/archive/actual-api-schema.json').read_text())
        observed=receipt['safe_presence']
        self.assertEqual(observed['skills']['type'],'NoneType')
        self.assertEqual(observed['projects']['type'],'dict')
        config={'features':dict.fromkeys(n.CANONICAL_FEATURES,False),'skills':None}
        config['features'].update({k:v['bool_or_null'] for k,v in observed['discovery'].items()})
        data={'config':config,'layers':[{'name':{'type':'user'},'version':'retained-type-string','config':{}}]}
        resolved=n.native_premises(data,[])
        self.assertTrue(resolved['include_instructions'])
        for skills in [None,{}, {'include_instructions':None}]:
            data['config']['skills']=skills
            self.assertTrue(n.native_premises(data,[])['include_instructions'])
        data['config'].pop('skills');data['config']['features'].pop('skip_host_skill_discovery')
        self.assertFalse(n.native_premises(data,[])['skip_host_skill_discovery'])
        data['config']['features']['skip_host_skill_discovery']=None
        with self.assertRaises(RuntimeError):n.native_premises(data,[])
        self.assertNotEqual(n.safe_config_identity({}),n.safe_config_identity({'skills':None}))
        self.assertNotEqual(n.safe_config_identity({'skills':None}),n.safe_config_identity({'skills':{}}))

    def test_actual_shaped_startup_trust_origin_propagation_is_exact(self):
        import json
        schema=json.loads((n.SOURCE/'.omx/ultragoal/evidence/codex-r6-poststart-baseline-fix/archive/actual-api-schema.json').read_text())
        observed=next(iter(schema['identity']['schema']['origins'].values()))
        self.assertEqual(set(observed),{'name','version'})
        self.assertEqual(observed['version'],'str')
        self.assertEqual(observed['name'],{'type':'str','file':'str','profile':'NoneType'})
        source={'type':'user','file':'/user','profile':None}
        system={'type':'system','file':'/etc/codex/config.toml'}
        pre={'config':{'model':'configured','projects':{}},
             'layers':[{'name':source,'version':'pre','disabledReason':None,
                        'config':{'model':'configured','projects':{}}}],
             'origins':{'model':{'name':source,'version':'pre'},
                        'unchanged.system':{'name':system,'version':'system-fixed'}}}
        post=copy.deepcopy(pre)
        for cfg in [post['config'],post['layers'][0]['config']]:
            cfg['projects']['/fixture']={'trust_level':'trusted'}
        post['layers'][0]['version']='post'
        post['origins']['model']['version']='post'
        post['origins']['projects./fixture.trust_level']={'name':source,'version':'post'}
        files={'/user':{'exists':True,'realpath':'/user','sha256':'pre'}}
        after_files=copy.deepcopy(files);after_files['/user']['sha256']='post'
        def validate(candidate, before=pre):
            return n.validate_startup(before,candidate,files,after_files,'/fixture','/user',
                                      before['layers'][0]['config'],candidate['layers'][0]['config'])
        saved=copy.deepcopy((pre,post))
        self.assertEqual(validate(post),'persisted-trust-only')
        self.assertEqual((pre,post),saved)
        for mutation in ['other-trust','new-key','wrong-new-source','wrong-new-version',
                         'wrong-existing-source','wrong-existing-version','unrelated-origin-change',
                         'removed-origin','unknown-origin-metadata','unsupported-origin-shape','unsupported-origin-source','disabled-reason','layer-source','new-project-layer']:
            bad=copy.deepcopy(post)
            if mutation=='other-trust':bad['origins']['projects./other.trust_level']=bad['origins'].pop('projects./fixture.trust_level')
            if mutation=='new-key':bad['origins']['unknown']={'name':source,'version':'post'}
            if mutation=='wrong-new-source':bad['origins']['projects./fixture.trust_level']['name']=system
            if mutation=='wrong-new-version':bad['origins']['projects./fixture.trust_level']['version']='wrong'
            if mutation=='wrong-existing-source':bad['origins']['model']['name']=system
            if mutation=='wrong-existing-version':bad['origins']['model']['version']='wrong'
            if mutation=='unrelated-origin-change':bad['origins']['unchanged.system']['version']='changed'
            if mutation=='removed-origin':bad['origins'].pop('model')
            if mutation=='unknown-origin-metadata':bad['origins']['model']['unknown']='new'
            if mutation=='unsupported-origin-shape':bad['origins']['model']=None
            if mutation=='unsupported-origin-source':bad['origins']['model']['name']={'type':'unknown'}
            if mutation=='disabled-reason':bad['layers'][0]['disabledReason']='new'
            if mutation=='layer-source':bad['layers'][0]['name']['file']='/other'
            if mutation=='new-project-layer':bad['layers'].append({'name':{'type':'project'},'version':'new','config':{}})
            with self.subTest(mutation=mutation):
                with self.assertRaises(RuntimeError):validate(bad)
        badpre=copy.deepcopy(pre);badpre['origins']['model']['version']='unbound-before'
        with self.assertRaises(RuntimeError):validate(post,badpre)

class SetupArtifactEdgeTests(unittest.TestCase):
    def fixture(self,root):
        (root/'AGENTS.md').write_text('GRANT sentinel\n')
        return n.setup_slots(root,[])

    def test_terminal_candidate_keeps_baseline_and_requires_write_and_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);slots=self.fixture(root)
            base={'files':{str(root/'AGENTS.md'):{'sha256':'old'},str(root/'CLAUDE.md'):{'sha256':None},'/host/AGENTS.md':{'sha256':'host-protected'}},'setup_slots':slots,'setup_scope':{},'config':{'stable':True}}
            contract={'schema':'setup-artifact-edge-v1','stage':'setup','row_id':'copy-setup-agents-only',
                'root':str(root),'realroot':str(root.resolve()),'initial_slots':slots,
                'preserve':{'AGENTS.md':['GRANT sentinel\n'],'CLAUDE.md':[]},'write_commands':['write fixture'],
                'setup_input_sha256':n.canonical_hash('actual setup'),'allowed_outputs':[],
                'recipe_sha256':'recipe','manifest_sha256':'manifest','proof_sha256':'proof','release_id':'release'}
            edge=n.SetupArtifactEdge(base,contract,root,'copy-setup-agents-only')
            (root/'AGENTS.md').write_text('GRANT sentinel\nmanaged setup\n')
            post=copy.deepcopy(base);post['files'][str(root/'AGENTS.md')]['sha256']='new';post['setup_slots']=n.setup_slots(root,[])
            events=[{'method':'item/completed','params':{'item':{'type':'commandExecution','command':'write fixture','status':'completed','exitCode':0,'aggregatedOutput':'written'}}},
                    {'method':'turn/completed','params':{'turn':{'status':'completed','error':None}}}]
            history=[{'role':'user','text':'actual setup'}]
            result=edge.terminal(post,events,history)
            self.assertEqual(result['status'],'HELD_UNVERIFIED_SETUP_OUTPUT_PROVENANCE')
            self.assertFalse(result['raw_stable']);self.assertEqual(edge.baseline,base)
            self.assertFalse(edge.authorizes_dispatch)
            for bad in [[],events+[{'method':'error','params':{}}]]:
                with self.assertRaises(RuntimeError):n.SetupArtifactEdge(base,contract,root,'copy-setup-agents-only').terminal(post,bad,history)
            held=n.SetupArtifactEdge(base,contract,root,'copy-setup-agents-only').terminal(post,events[1:],history)
            self.assertEqual(held['status'],'HELD_UNVERIFIED_SETUP_OUTPUT_PROVENANCE')
            for key in ['config','environment','catalog','installed','unknown']:
                changed=copy.deepcopy(post);changed[key]={'drift':True}
                with self.assertRaises(RuntimeError):n.SetupArtifactEdge(base,contract,root,'copy-setup-agents-only').terminal(changed,events,history)
            host_change=copy.deepcopy(post);host_change['files']['/host/AGENTS.md']['sha256']='changed'
            with self.assertRaises(RuntimeError):n.SetupArtifactEdge(base,contract,root,'copy-setup-agents-only').terminal(host_change,events,history)
            latched=n.PostStartBaseline(base,base)
            with self.assertRaises(RuntimeError):latched.check(post)
            with self.assertRaises(RuntimeError):n.SetupArtifactEdge(base,contract,root,'copy-setup-agents-only',latched).terminal(post,events,history)
            with self.assertRaises(RuntimeError):n.SetupArtifactEdge(base,None,root,'copy-setup-agents-only')
            with self.assertRaises(RuntimeError):n.SetupArtifactEdge(base,contract,root,'copy-original-spec')

    def test_slots_capture_absence_and_reject_protected_alias_escape_and_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);slots=n.setup_slots(root,[])
            self.assertEqual(slots['AGENTS.md']['kind'],'absent')
            (root/'AGENTS.md').write_text('fixture')
            (root/'CLAUDE.md').symlink_to('AGENTS.md')
            slots=n.setup_slots(root,[]);self.assertEqual(slots['CLAUDE.md']['kind'],'symlink')
            with self.assertRaises(RuntimeError):n.setup_slots(root,[root/'AGENTS.md'])
            (root/'CLAUDE.md').unlink();(root/'CLAUDE.md').symlink_to('/etc/passwd')
            with self.assertRaises(RuntimeError):n.setup_slots(root,[])
            (root/'CLAUDE.md').unlink();(root/'CLAUDE.md').symlink_to('missing')
            with self.assertRaises(RuntimeError):n.setup_slots(root,[])

    def test_continuation_denies_forged_approval_and_open_predecessor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);slots=self.fixture(root)
            checkpoint={'schema':'setup-artifact-checkpoint-v1','closed':False,'root':str(root),'post_slots':slots}
            with self.assertRaises(RuntimeError):n.validate_setup_continuation(checkpoint,{}, {},root,{},'manifest','release')

    def test_closed_checkpoint_requires_exact_images_review_and_actual_approval(self):
        import types
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'consumer';root.mkdir();before_slots=self.fixture(root)
            (root/'CLAUDE.md').write_text('@AGENTS.md\n');slots=n.setup_slots(root,[])
            sink=Path(tmp)/'rpc';sink.mkdir();n.write(sink/'closed.json',{'closed':True})
            cp={'schema':'setup-artifact-checkpoint-v1','closed':False,'root':str(root),'post_slots':slots,
                'protected_paths':[],'terminal':{'setup_scope':n.setup_scope(root),'files':{},'installed':[{'name':'ains-setup','source_sha256':'setup-body'}]},
                'contract':{'manifest_sha256':'manifest','release_id':'release','initial_slots':before_slots,'root':str(root),'allowed_outputs':[]},'source_recipe_sha256':'original-recipe',
                'user_history':[{'role':'user','text':'setup'}],'original_setup_user_text':'setup','idempotence':'NOT_YET_TESTED'}
            cp['baseline']={'setup_slots':before_slots}
            cp['events']=[{'method':'item/completed','params':{'item':{'type':'fileChange','status':'completed',
                          'changes':[{'path':str(root/'CLAUDE.md'),'kind':{'type':'add'},'diff':'@AGENTS.md\n'}]}}}]
            cp['provenance']=n.setup_write_provenance(before_slots,slots,cp['terminal']['setup_scope'],cp['events'],cp['contract'])
            cp['status']='OBSERVED_SETUP_OUTPUT_CHECKPOINT_REQUIRES_PARENT_REVIEW'
            rpc=types.SimpleNamespace(close=mock.Mock(),p=types.SimpleNamespace(poll=lambda:0),sink=sink,call=mock.Mock())
            n.close_setup_checkpoint(rpc,cp,Path(tmp)/'checkpoint.json')
            rpc.close.assert_called_once();rpc.call.assert_not_called();self.assertTrue(cp['closed'])
            recipe={'predecessor_recipe_sha256':'original-recipe','predecessor_user_history':cp['user_history'],'checkpoint_installed':cp['terminal']['installed'],'setup_content_ack_text':'actual content acknowledgment','setup_repeat_text':'setup'}
            review={'decision':'APPROVED_SETUP_CHECKPOINT','checkpoint_sha256':n.canonical_hash(cp),
                    'post_slots_sha256':n.canonical_hash(slots),'fixture_slots_sha256':n.canonical_hash(before_slots),
                    'terminal_scope_sha256':n.canonical_hash(cp['terminal']['setup_scope']),'setup_body_sha256':'setup-body',
                    'evidence':{k:'Synthetic exact fixture/output/source comparison' for k in ('existing_values','grants','unrelated_bytes','one_import','topology','source_bound_policy','scope')},
                    'preservation_checks':{k:True for k in ('existing_values','grants','unrelated_bytes','one_import','topology','source_bound_policy','scope')}}
            review['write_provenance']={'mode':'CONCRETE_PARENT_STRUCTURED_CHANGE_REVIEW',
                'observations_sha256':n.canonical_hash(cp['provenance']),
                'artifact_delta_sha256':n.canonical_hash({'before':before_slots,'after':slots}),
                'evidence':'Synthetic exact add diff/postimage and source event reviewed'}
            approval={'role':'user','action':'approve_setup_checkpoint_new_context','checkpoint_sha256':n.canonical_hash(cp),
                      'review_sha256':n.canonical_hash(review),'new_context':True,'text':'Actual approval of this exact reviewed checkpoint for setup verification only'}
            result=n.validate_setup_continuation(cp,review,approval,root,recipe,'manifest','release')
            self.assertTrue(result['explicit_new_context'])
            no_scope_review=copy.deepcopy(review);no_scope_review.pop('write_provenance')
            with self.assertRaisesRegex(RuntimeError,'scope review missing'):
                n.validate_setup_continuation(cp,no_scope_review,approval,root,recipe,'manifest','release')
            held=copy.deepcopy(cp);held['provenance']['complete_for_parent_review']=False
            with self.assertRaisesRegex(RuntimeError,'cannot authorize C1'):
                n.validate_setup_continuation(held,review,approval,root,recipe,'manifest','release')
            for key,value in [('role','assistant'),('checkpoint_sha256','wrong'),('new_context',False),('review_sha256','forged')]:
                bad=dict(approval,**{key:value})
                with self.assertRaises(RuntimeError):n.validate_setup_continuation(cp,review,bad,root,recipe,'manifest','release')
            with self.assertRaises(RuntimeError):n.validate_setup_continuation(cp,{},approval,root,recipe,'manifest','release')
            with self.assertRaises(RuntimeError):n.validate_setup_continuation(cp,review,approval,root,recipe,'wrong-source','release')
            (root/'AGENTS.md').write_text('stale')
            with self.assertRaises(RuntimeError):n.validate_setup_continuation(cp,review,approval,root,recipe,'manifest','release')

    def test_protected_hardlink_internal_unknown_alias_and_samefile_split(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'consumer';root.mkdir();protected=Path(tmp)/'protected';protected.write_text('protected')
            os.link(protected,root/'AGENTS.md')
            with self.assertRaises(RuntimeError):n.setup_slots(root,[protected])
            (root/'AGENTS.md').unlink();(root/'AGENTS.md').write_text('fixture')
            os.link(root/'AGENTS.md',root/'CLAUDE.md')
            slots=n.setup_slots(root,[]);self.assertEqual(slots['AGENTS.md']['target_identity'],slots['CLAUDE.md']['target_identity'])
            os.link(root/'AGENTS.md',root/'unknown')
            with self.assertRaises(RuntimeError):n.setup_slots(root,[])

    def test_mocked_live_dispatch_closes_at_terminal_edge_without_next_USER(self):
        import argparse,contextlib,io,json,types
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);prepared=work/'prepared';prepared.mkdir();fixtures=work/'fixtures';fixtures.mkdir()
            (fixtures/'agents-only').mkdir();(fixtures/'agents-only'/'AGENTS.md').write_text('GRANT sentinel\n')
            consumers=work/'consumers';consumers.mkdir();root=consumers/'copy-setup-agents-only'
            expected_slots=n.setup_slots(fixtures/'agents-only',[])
            for name,record in expected_slots.items():
                record['path']=str(root/name);record['realpath']=str(root/name)
            # File copy changes inode; contract is bound to the actual fixture
            # after copy, before the model can receive any USER input.
            manifest=work/'manifest.json';n.write(manifest,{'suite_files':{}})
            proof=work/'proof';proof.write_text('synthetic proof')
            row={'id':'copy-setup-agents-only','transport':'live','fixture':'agents-only','mode':'copy','initial_user_text':'actual setup','max_user_turns':3}
            recipe={'release_manifest':str(manifest),'release_manifest_sha256':n.sha(manifest),'adapter_sha256':n.sha(n.__file__),
                    'helper_imports':[],'fixture_hashes':{},'fixture_root':str(fixtures),'consumer_root':str(consumers),'rows':[row]}
            n.write(prepared/'recipe.json',recipe)
            expected={k:None for k in n.THREAD_FIELDS};expected['instructionSources']=[]
            binding={'codex_version':'synthetic','parent_release_id':'release','scope':'configured-native-selector','proof_path':str(proof),'proof_sha256':n.sha(proof),'transports':['live'],
                     'forward_thread_expectation':expected,'forward_trust_root':str(consumers)}
            contract={'schema':n.SETUP_EDGE_SCHEMA,'stage':'setup','row_id':row['id'],'root':str(root),'realroot':str(root.resolve()),
                'initial_images':{name:{k:record[k] for k in ('kind','sha256','link_text')} for name,record in expected_slots.items()},'initial_topology':'distinct','preserve':{'AGENTS.md':['GRANT sentinel\n'],'CLAUDE.md':[]},'write_commands':['write fixture'],
                'setup_input_sha256':n.canonical_hash('actual setup'),'allowed_outputs':[],
                'recipe_sha256':n.sha(prepared/'recipe.json'),'manifest_sha256':n.sha(manifest),'proof_sha256':n.sha(proof),'release_id':'release'}
            binding['setup_artifact_contract']=contract
            binding_path=work/'binding.json';n.write(binding_path,binding)
            calls=[];instances=[]
            write_event={'method':'item/completed','params':{'item':{'type':'commandExecution','command':'write fixture','status':'completed','exitCode':0,'aggregatedOutput':'written'}}}
            class RPC:
                def __init__(self,sink):
                    self.sink=Path(sink);self.sink.mkdir();self.log=[];self.events=[];self.env={};self.selected_environment={};self.closed=False
                    self.p=types.SimpleNamespace(pid=42,poll=lambda:0 if self.closed else None);instances.append(self)
                def call(self,method,params,timeout=30):
                    calls.append(method)
                    if method=='thread/start':return {'thread':{'id':'actual-synthetic-thread'}}
                    if method=='turn/start':self.events=[write_event];self.log.append({'direction':'response_or_event','payload':write_event});return {}
                    return {'config':{},'layers':[]}
                def next(self,deadline):
                    (root/'AGENTS.md').write_text('GRANT sentinel\nmanaged setup\n')
                    event={'method':'turn/completed','params':{'turn':{'status':'completed','error':None}}}
                    self.log.append({'direction':'response_or_event','payload':event});return event
                def close(self):
                    self.closed=True;n.write(self.sink/'closed.json',{'synthetic_closed':True})
            def recorded(rt,ar,r,overrides,sink,b):
                return RPC(sink)
            def bundle(rpc,r,installed,paths,m,h,b,instructions):
                files={str(r/name):{'exists':(r/name).exists(),'realpath':str((r/name).resolve()),'sha256':n.sha(r/name) if (r/name).is_file() else None} for name in n.SETUP_SLOTS}
                return {'files':files,'catalog_proof':{},'environment':{},'installed':installed,'config':{'stable':True}}, {'config':{},'layers':[]}
            a=types.SimpleNamespace(probe=lambda r:{'files':{},'all_layer_mcp_names':[]},inventory=lambda r:[],CANONICAL=n.CANONICAL_FEATURES)
            helpers={'runtime':types.SimpleNamespace(snapshot=lambda r:{}),'activation_recheck':types.SimpleNamespace(write=n.write),
                     'activation_r3':a,'activation_closure_probe':types.SimpleNamespace(structural=lambda c:{})}
            stream=io.StringIO('{"text":"actual setup"}\n{"text":"must not dispatch"}\n')
            args=argparse.Namespace(release_id='release',prepared=str(prepared),manifest=str(manifest),native_binding=str(binding_path),out=str(work/'out'),row=row['id'],packet=None,setup_checkpoint=None)
            with mock.patch.object(n,'released_source'),mock.patch.object(n,'bound_helpers',return_value=contextlib.nullcontext((helpers,[]))),mock.patch.object(n.subprocess,'run',return_value=types.SimpleNamespace(stdout='synthetic',returncode=0)),mock.patch.object(n,'recorded_rpc',side_effect=recorded),mock.patch.object(n,'live_bundle',side_effect=bundle),mock.patch.object(n,'validate_catalog',return_value={}),mock.patch.object(n,'native_selection_receipt',return_value={}),mock.patch.object(n,'reconcile_thread',return_value={}),mock.patch.object(n,'validate_startup',return_value='synthetic-unchanged'),mock.patch.object(n,'require_environment',return_value={}),mock.patch.object(n,'native_oracle',return_value={}),mock.patch.object(n.sys,'stdin',stream),mock.patch.object(Path,'home',return_value=work/'fake-home'),mock.patch('builtins.print'):
                n.run_row(args)
            self.assertEqual(calls.count('turn/start'),1)
            self.assertTrue(all(rpc.closed for rpc in instances))
            cp=json.loads((work/'out/setup-checkpoint-v1.json').read_text())
            self.assertTrue(cp['closed']);self.assertFalse(cp['raw_stable']);self.assertEqual(len(cp['user_history']),1)
            self.assertEqual(stream.readline(),'{"text":"must not dispatch"}\n')

    def test_exact_topology_creation_atomic_replace_and_rejection_matrix(self):
        import os
        def exercise(kind,change,allowed):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                if kind!='absent':(root/'AGENTS.md').write_text('GRANT sentinel\n')
                if kind=='samefile':os.link(root/'AGENTS.md',root/'CLAUDE.md')
                if kind=='symlink':(root/'CLAUDE.md').symlink_to('AGENTS.md')
                slots=n.setup_slots(root,[])
                def bundle():
                    current=n.setup_slots(root,[])
                    files={str(root/name):{'exists':record['kind']!='absent','realpath':record['realpath'],'sha256':record['sha256']} for name,record in current.items()}
                    files['/host/AGENTS.md']={'sha256':'protected-host'}
                    return {'files':files,'setup_slots':current,'setup_scope':n.setup_scope(root),'catalog':{'fixed':True}}
                before=bundle()
                contract={'schema':n.SETUP_EDGE_SCHEMA,'stage':'setup','row_id':'copy-setup-'+kind,'root':str(root),'realroot':str(root.resolve()),
                          'initial_slots':slots,'preserve':{name:['GRANT sentinel\n'] if record['kind']!='absent' else [] for name,record in slots.items()},
                          'setup_input_sha256':n.canonical_hash('setup'),'write_commands':['write fixture'],'allowed_outputs':[]}
                edge=n.SetupArtifactEdge(before,contract,root,contract['row_id'])
                change(root)
                events=[{'method':'item/completed','params':{'item':{'type':'commandExecution','command':'write fixture','status':'completed','exitCode':0,'aggregatedOutput':'written'}}},
                        {'method':'turn/completed','params':{'turn':{'status':'completed'}}}]
                if allowed:
                    self.assertEqual(edge.terminal(bundle(),events,[{'role':'user','text':'setup'}])['status'],'HELD_UNVERIFIED_SETUP_OUTPUT_PROVENANCE')
                else:
                    with self.assertRaises(RuntimeError):edge.terminal(bundle(),events,[{'role':'user','text':'setup'}])
        def write(root): (root/'AGENTS.md').write_text('GRANT sentinel\nmanaged\n')
        def atomic(root):
            (root/'replacement').write_text('GRANT sentinel\nmanaged\n');os.replace(root/'replacement',root/'AGENTS.md')
        def split(root):
            (root/'CLAUDE.md').unlink();(root/'CLAUDE.md').write_text('GRANT sentinel\nmanaged\n')
        def replace_link(root):
            (root/'CLAUDE.md').unlink();(root/'new-link').symlink_to('AGENTS.md');os.replace(root/'new-link',root/'CLAUDE.md');write(root)
        def create(root):
            (root/'AGENTS.md').write_text('new setup\n');(root/'CLAUDE.md').write_text('@AGENTS.md\n')
        for kind,change,allowed in [('distinct',atomic,True),('samefile',write,True),('samefile',split,False),('symlink',write,True),('symlink',replace_link,False),('absent',create,True),('distinct',lambda root:(root/'AGENTS.md').write_text('lost grant'),False),('distinct',lambda root:((root/'nested').mkdir(),(root/'nested/AGENTS.md').write_text('unknown'),write(root)),False)]:
            with self.subTest(kind=kind,change=change.__name__):exercise(kind,change,allowed)

class SetupProvenanceR1Tests(unittest.TestCase):
    def retained_change(self):
        import json
        path=n.SOURCE/'.omx/ultragoal/evidence/g004/codex/native-v2/runs-r5-20261025/copy-setup-agents-only/live-rpc/rpc.json'
        self.assertEqual(n.sha(path),'f96cc470c5959533a4917cb271459d5ead8c28c92a95de9d9fafa0860065b041')
        event=json.loads(path.read_text())[149]['payload']
        self.assertEqual(event['method'],'item/completed');self.assertEqual(event['params']['item']['type'],'fileChange')
        self.assertEqual(event['params']['item']['changes'][0]['diff'],'@AGENTS.md\n')
        return event

    def candidate(self,events):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'AGENTS.md').write_text('GRANT sentinel\n')
            def bundle():
                slots=n.setup_slots(root,[])
                return {'setup_slots':slots,'setup_scope':n.setup_scope(root),'files':{str(root/name):{'exists':x['kind']!='absent','realpath':x['realpath'],'sha256':x['sha256']} for name,x in slots.items()},'config':{'fixed':True}}
            before=bundle()
            contract={'schema':n.SETUP_EDGE_SCHEMA,'stage':'setup','row_id':'copy-setup-agents-only','root':str(root),'realroot':str(root.resolve()),
                      'initial_slots':before['setup_slots'],'preserve':{'AGENTS.md':['GRANT sentinel\n'],'CLAUDE.md':[]},
                      'setup_input_sha256':n.canonical_hash('actual setup'),'allowed_outputs':[]}
            edge=n.SetupArtifactEdge(before,contract,root,contract['row_id'])
            (root/'CLAUDE.md').write_text('@AGENTS.md\n')
            actual=copy.deepcopy(events)
            for event in actual:
                for change in event.get('params',{}).get('item',{}).get('changes',[]) or []:
                    if change.get('path')=='TRANSPLANT_CLAUDE':change['path']=str(root/'CLAUDE.md')
            actual.append({'method':'turn/completed','params':{'turn':{'status':'completed'}}})
            result=edge.terminal(bundle(),actual,[{'role':'user','text':'actual setup'}])
            self.assertFalse(result['raw_stable']);self.assertEqual(edge.baseline,before)
            return result

    def test_retained_structured_change_paths_diff_and_postimage_are_kept(self):
        event=self.retained_change();event['params']['item']['changes'][0]['path']='TRANSPLANT_CLAUDE'
        result=self.candidate([event])
        self.assertEqual(result['status'],'OBSERVED_SETUP_OUTPUT_CHECKPOINT_REQUIRES_PARENT_REVIEW')
        self.assertEqual(result['provenance']['mode'],'structured_file_change')
        self.assertEqual(result['write_evidence'][0]['item']['changes'][0]['diff'],'@AGENTS.md\n')
        self.assertEqual(bytes.fromhex(result['post_slots']['CLAUDE.md']['bytes_hex']),b'@AGENTS.md\n')

    def test_unpredicted_command_is_retained_without_scope_parser_claim(self):
        command="/bin/zsh -lc 'printf updated > AGENTS.md'"
        result=self.candidate([{'method':'item/completed','params':{'item':{'type':'commandExecution','command':command,'status':'completed','exitCode':0,'aggregatedOutput':''}}}])
        self.assertEqual(result['status'],'HELD_UNVERIFIED_SETUP_OUTPUT_PROVENANCE')
        self.assertFalse(result['provenance']['complete_for_parent_review'])
        self.assertEqual(result['provenance']['mode'],'command_requires_parent_scope_review')
        self.assertFalse(result['provenance']['execution_scope_parser_claim'])
        self.assertEqual(result['write_evidence'][0]['item']['command'],command)

    def test_missing_incomplete_and_foreign_provenance_persist_held_candidate(self):
        foreign=self.retained_change()
        incomplete=self.retained_change();incomplete['params']['item']['status']='inProgress'
        for events in [[],[foreign],[incomplete],[{'method':'item/completed','params':{'item':{'type':'fileChange','status':'completed','changes':[{}]}}}],[{'method':'item/completed','params':{'item':{'type':'fileChange','status':'completed','changes':None}}}],[{'method':'item/completed','params':{'item':{'type':'commandExecution','command':'inspect files','status':'completed','exitCode':None,'aggregatedOutput':None}}}]]:
            with self.subTest(events=events):
                result=self.candidate(events)
                self.assertEqual(result['status'],'HELD_UNVERIFIED_SETUP_OUTPUT_PROVENANCE')
                self.assertFalse(result['provenance']['complete_for_parent_review'])
                with self.assertRaisesRegex(RuntimeError,'cannot authorize C1'):n.validate_setup_continuation(dict(result,closed=True),{}, {},Path(result['root']),{},'manifest','release')

    def test_mocked_dispatch_retained_and_unpredicted_and_missing_all_close(self):
        from unittest import mock
        original=n.SetupArtifactEdge.terminal
        retained=self.retained_change()
        command={'method':'item/completed','params':{'item':{'type':'commandExecution','command':"/bin/zsh -lc 'printf updated > AGENTS.md'",'status':'completed','exitCode':0,'aggregatedOutput':''}}}
        for replacement in [retained,command,None]:
            saved=[]
            def terminal(edge,after,events,history):
                replaced=[] if replacement is None else [copy.deepcopy(replacement)]
                if replacement is retained:
                    # Labeled alternative mock runtime outcome: retain AGENTS,
                    # create CLAUDE using the actual retained add diff. No
                    # native runtime evidence is manufactured by this fixture.
                    root=Path(edge.contract['root'])
                    (root/'AGENTS.md').write_bytes(bytes.fromhex(edge.baseline['setup_slots']['AGENTS.md']['bytes_hex']))
                    (root/'CLAUDE.md').write_text('@AGENTS.md\n')
                    after['setup_slots']=n.setup_slots(root,[]);after['setup_scope']=n.setup_scope(root)
                    for name,slot in after['setup_slots'].items():
                        after['files'][str(root/name)]={'exists':slot['kind']!='absent','realpath':slot['realpath'],'sha256':slot['sha256']}
                    replaced[0]['params']['item']['changes'][0]['path']=str(root/'CLAUDE.md')
                result=original(edge,after,replaced+[events[-1]],history);saved.append(result);return result
            with self.subTest(replacement=replacement),mock.patch.object(n.SetupArtifactEdge,'terminal',terminal):
                SetupArtifactEdgeTests('test_mocked_live_dispatch_closes_at_terminal_edge_without_next_USER').test_mocked_live_dispatch_closes_at_terminal_edge_without_next_USER()
                self.assertEqual(len(saved),1)
                self.assertEqual(saved[0]['status'],'OBSERVED_SETUP_OUTPUT_CHECKPOINT_REQUIRES_PARENT_REVIEW' if replacement is retained else 'HELD_UNVERIFIED_SETUP_OUTPUT_PROVENANCE')

class SetupCommandReviewR2Tests(unittest.TestCase):
    def make_case(self, work):
        import types
        from unittest import mock
        root=work/'copy-setup-agents-only';root.mkdir();(root/'AGENTS.md').write_text('GRANT sentinel\n')
        body=root/'.agents/skills/ains-setup/SKILL.md';body.parent.mkdir(parents=True);body.write_text('synthetic reviewed setup body')
        installed=[{'name':'ains-setup','path':str(body),'realpath':str(body.resolve()),'source_sha256':n.sha(body)}]
        manifest_hash=n.sha(work/'manifest.json') if (work/'manifest.json').is_file() else 'manifest'
        def bundle():
            slots=n.setup_slots(root,[])
            return {'setup_slots':slots,'setup_scope':n.setup_scope(root),
                    'files':{str(root/name):{'exists':x['kind']!='absent','realpath':x['realpath'],'sha256':x['sha256']} for name,x in slots.items()},
                    'installed':installed,'config':{'strict':'fixed'}}
        before=bundle()
        contract={'schema':n.SETUP_EDGE_SCHEMA,'stage':'setup','row_id':'copy-setup-agents-only','root':str(root),'realroot':str(root.resolve()),
                  'initial_slots':before['setup_slots'],'preserve':{'AGENTS.md':['GRANT sentinel\n'],'CLAUDE.md':[]},
                  'setup_input_sha256':n.canonical_hash('actual setup'),'allowed_outputs':[],
                  'manifest_sha256':manifest_hash,'release_id':'release'}
        edge=n.SetupArtifactEdge(before,contract,root,contract['row_id'])
        (root/'CLAUDE.md').write_text('@AGENTS.md\n')
        item={'id':'synthetic-shell-write','type':'commandExecution','cwd':str(root),
              'command':"printf '%s\\n' '@AGENTS.md' > CLAUDE.md",'status':'completed','exitCode':0,'aggregatedOutput':''}
        events=[{'method':'item/completed','params':{'item':item,'threadId':'thread-C0','turnId':'turn-C0'}},
                {'method':'turn/completed','params':{'threadId':'thread-C0','turn':{'id':'turn-C0','status':'completed'}}}]
        cp=edge.terminal(bundle(),events,[{'role':'user','text':'actual setup'}])
        self.assertEqual(cp['status'],'HELD_UNVERIFIED_SETUP_OUTPUT_PROVENANCE')
        cp.update(process_id=42,thread_id='thread-C0',wire_start_index=10,wire_end_index=15,source_recipe_sha256='C0-recipe',protected_paths=[])
        sink=work/'rpc';sink.mkdir();n.write(sink/'closed.json',{'mock_closed':True})
        rpc=types.SimpleNamespace(close=mock.Mock(),p=types.SimpleNamespace(poll=lambda:0),sink=sink)
        n.close_setup_checkpoint(rpc,cp,work/'checkpoint.json');rpc.close.assert_called_once()
        recipe={'predecessor_recipe_sha256':'C0-recipe','predecessor_user_history':cp['user_history'],
                'checkpoint_installed':cp['terminal']['installed'],'setup_content_ack_text':'actual new acknowledgment','setup_repeat_text':'actual setup'}
        delta={'before_slots':cp['baseline']['setup_slots'],'after_slots':cp['post_slots'],
               'before_scope':cp['baseline']['setup_scope'],'after_scope':cp['terminal']['setup_scope']}
        write_review={'mode':'CONCRETE_PARENT_LITERAL_COMMAND_REVIEW_V1','observations_sha256':n.canonical_hash(cp['provenance']),
              'artifact_delta_sha256':n.canonical_hash({'before':before['setup_slots'],'after':cp['post_slots']}),
              'context':{'process_id':42,'thread_id':'thread-C0','turn_id':'turn-C0','wire_start_index':10,'wire_end_index':15},
              'scoped_delta_sha256':n.canonical_hash(delta),'evidence':'Synthetic parent review of exact retained command/result and entire artifact delta',
              'selections':[{'event_index':0,'item':copy.deepcopy(item),'target_path':str(root/'CLAUDE.md'),
                             'expected_bytes_hex':b'@AGENTS.md\n'.hex(),
                             'evidence':{'target':'Literal CLAUDE.md at the recorded consumer cwd',
                                         'bytes':'Literal printf import plus LF equals exact observed new file',
                                         'scope':'AGENTS grant and all nonartifact inputs unchanged; no other consumer delta'}}]}
        review={'decision':'APPROVED_SETUP_CHECKPOINT','checkpoint_sha256':n.canonical_hash(cp),
                'post_slots_sha256':n.canonical_hash(cp['post_slots']),'fixture_slots_sha256':n.canonical_hash(before['setup_slots']),
                'terminal_scope_sha256':n.canonical_hash(cp['terminal']['setup_scope']),'setup_body_sha256':installed[0]['source_sha256'],
                'evidence':{k:'Synthetic exact fixture/output/source review' for k in ('existing_values','grants','unrelated_bytes','one_import','topology','source_bound_policy','scope')},
                'preservation_checks':{k:True for k in ('existing_values','grants','unrelated_bytes','one_import','topology','source_bound_policy','scope')},'write_provenance':write_review}
        approval={'role':'user','action':'approve_setup_checkpoint_new_context','checkpoint_sha256':n.canonical_hash(cp),
                  'review_sha256':n.canonical_hash(review),'new_context':True,'text':'Synthetic separate scoped USER approval; not actual consent'}
        return root,cp,review,approval,recipe

    def test_exact_R2_printf_closed_held_candidate_can_receive_concrete_C1_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,cp,review,approval,recipe=self.make_case(Path(tmp));original=copy.deepcopy(cp)
            result=n.validate_setup_continuation(cp,review,approval,root,recipe,'manifest','release')
            self.assertTrue(result['explicit_new_context']);self.assertEqual(cp,original)
            self.assertEqual(cp['status'],'HELD_UNVERIFIED_SETUP_OUTPUT_PROVENANCE')
            self.assertEqual(result['command_artifact_relation']['targets'],[str(root/'CLAUDE.md')])

    def test_wrong_item_cwd_target_bytes_review_USER_and_dynamic_syntax_stay_held(self):
        for mutation in ['index','id','cwd','target','bytes','context','delta','evidence','USER','command','missing-result','read-command','actual-cwd','unexplained-scope','open-context','postimage']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                root,cp,review,approval,recipe=self.make_case(Path(tmp))
                selected=review['write_provenance']['selections'][0]
                if mutation=='index':selected['event_index']=1
                if mutation=='id':selected['item']['id']='other-item'
                if mutation=='cwd':selected['item']['cwd']=str(root.parent)
                if mutation=='target':selected['target_path']=str(root/'AGENTS.md')
                if mutation=='bytes':selected['expected_bytes_hex']=b'wrong'.hex()
                if mutation=='context':review['write_provenance']['context']['turn_id']='other-turn'
                if mutation=='delta':review['write_provenance']['scoped_delta_sha256']='wrong'
                if mutation=='evidence':selected['evidence']['scope']=''
                if mutation=='USER':approval['role']='assistant'
                if mutation in ('command','missing-result','read-command','actual-cwd','unexplained-scope','open-context','postimage'):
                    item=cp['events'][0]['params']['item']
                    if mutation=='command':item['command']="printf '%s\\n' '$DYNAMIC' > $TARGET"
                    if mutation=='read-command':item['command']='cat CLAUDE.md'
                    if mutation=='missing-result':item['exitCode']=None
                    if mutation=='actual-cwd':item['cwd']=str(root.parent)
                    if mutation=='unexplained-scope':
                        cp['terminal']['setup_scope']['foreign-file']={'sha256':'new','realpath':str(root/'foreign-file')}
                        review['write_provenance']['scoped_delta_sha256']=n.canonical_hash({'before_slots':cp['baseline']['setup_slots'],'after_slots':cp['post_slots'],'before_scope':cp['baseline']['setup_scope'],'after_scope':cp['terminal']['setup_scope']})
                    if mutation=='open-context':cp['closed']=False
                    if mutation=='postimage':cp['post_slots']['CLAUDE.md']['bytes_hex']=b'foreign bytes'.hex()
                    selected['item']=copy.deepcopy(item)
                    cp['provenance']=n.setup_write_provenance(cp['baseline']['setup_slots'],cp['post_slots'],cp['terminal']['setup_scope'],cp['events'],cp['contract'])
                    review['write_provenance']['observations_sha256']=n.canonical_hash(cp['provenance'])
                    review['checkpoint_sha256']=n.canonical_hash(cp);approval['checkpoint_sha256']=n.canonical_hash(cp)
                approval['review_sha256']=n.canonical_hash(review)
                with self.assertRaises(RuntimeError):n.validate_setup_continuation(cp,review,approval,root,recipe,'manifest','release')

    def test_command_review_C1_dispatch_ack_then_repeat_without_recopy_or_install(self, _pending=False, _tuple=False, _extra=False, _changed_ack=False):
        import argparse,contextlib,io,json,types
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);manifest=work/'manifest.json';n.write(manifest,{'suite_files':{}})
            root,cp,review,approval,continuation_recipe=self.make_case(work)
            checkpoint=work/'checkpoint.json';checkpoint_before=n.sha(checkpoint);baseline_before=copy.deepcopy(cp['baseline'])
            review_path=work/'review.json';n.write(review_path,review)
            proof=work/'proof';proof.write_text('synthetic source binding')
            prepared=work/'C1-prepared';prepared.mkdir()
            row={'id':'copy-setup-agents-only','transport':'live','fixture':'agents-only','mode':'copy',
                 'initial_user_text':continuation_recipe['setup_repeat_text'] if _pending else continuation_recipe['setup_content_ack_text'],'max_user_turns':1 if _pending else 2}
            recipe=dict(continuation_recipe,release_manifest=str(manifest),release_manifest_sha256=n.sha(manifest),
                        adapter_sha256=n.sha(n.__file__),helper_imports=[],fixture_hashes={},fixture_root=str(work/'unused-original-fixtures'),
                        consumer_root=str(work),rows=[row],setup_checkpoint_file_sha256=n.sha(checkpoint))
            if _pending:
                cp['schema']=n.DERIVATIVE_SCHEMA;n.write(checkpoint,cp);checkpoint_before=n.sha(checkpoint)
                recipe.update(pending_repeat_ack={'path':'synthetic frozen receipt','sha256':'synthetic hash'},setup_checkpoint_file_sha256=n.sha(checkpoint))
            n.write(prepared/'recipe.json',recipe)
            expected={key:None for key in n.THREAD_FIELDS};expected['instructionSources']=[]
            contract={'schema':n.SETUP_EDGE_SCHEMA,'stage':'setup-repeat','row_id':row['id'],'root':str(root),'realroot':str(root.resolve()),
                      'initial_slots':cp['post_slots'],'preserve':{name:[] for name in n.SETUP_SLOTS},'allowed_outputs':[],
                      'setup_input_sha256':n.canonical_hash(recipe['setup_repeat_text']),'recipe_sha256':n.sha(prepared/'recipe.json'),
                      'manifest_sha256':n.sha(manifest),'proof_sha256':n.sha(proof),'release_id':'release'}
            binding={'codex_version':'synthetic','parent_release_id':'release','scope':'configured-native-selector','proof_path':str(proof),
                     'proof_sha256':n.sha(proof),'transports':['live'],'forward_thread_expectation':expected,
                     'forward_trust_root':str(work),'setup_artifact_contract':contract}
            pending_release=work/'pending-release.json';n.write(pending_release,{'release_id':'release'})
            if _pending:binding['derivative_release_sha256']=n.sha(pending_release)
            binding_path=work/'binding.json';n.write(binding_path,binding)
            calls=[];rpcs=[];texts=[]
            class RPC:
                def __init__(self,sink):
                    self.sink=Path(sink);self.sink.mkdir();self.log=[];self.events=[];self.env={};self.selected_environment={};self.closed=False
                    self.p=types.SimpleNamespace(pid=84,poll=lambda:0 if self.closed else None);rpcs.append(self)
                def call(self,method,params,timeout=30):
                    calls.append(method)
                    if method=='thread/start':return {'thread':{'id':'new-C1-thread'}}
                    if method=='turn/start':texts.append(params['input'][0]['text']);return {}
                    return {'config':{},'layers':[]}
                def next(self,deadline):
                    if _changed_ack and len(texts)==1:(root/'AGENTS.md').write_text((root/'AGENTS.md').read_text()+'actual changed ack output\n')
                    event={'method':'turn/completed','params':{'threadId':'new-C1-thread','turn':{'id':'C1-'+str(len(texts)),'status':'completed'}}}
                    self.log.append({'direction':'response_or_event','payload':event});return event
                def close(self):self.closed=True;n.write(self.sink/'closed.json',{'synthetic_closed':True})
            def bundle(rpc,r,installed,paths,m,h,b,instructions):
                files={str(r/name):{'exists':(r/name).exists(),'realpath':str((r/name).resolve()),'sha256':n.sha(r/name)} for name in n.SETUP_SLOTS}
                return {'files':files,'catalog_proof':{},'environment':{},'installed':installed,'config':{'stable':True},
                        'process_id':84,'thread_id':rpc.bound_thread,'synthetic_roundtrip':(1,2) if _tuple else [1,2]}, {'config':{},'layers':[]}
            a=types.SimpleNamespace(probe=lambda r:{'files':{},'all_layer_mcp_names':[]},inventory=lambda r:cp['terminal']['installed'],CANONICAL=n.CANONICAL_FEATURES)
            helpers={'runtime':types.SimpleNamespace(snapshot=lambda r:{}),'activation_recheck':types.SimpleNamespace(write=n.write),
                     'activation_r3':a,'activation_closure_probe':types.SimpleNamespace(structural=lambda c:{})}
            inputs=[recipe['setup_repeat_text']] if _pending else [recipe['setup_content_ack_text'],recipe['setup_repeat_text']]
            stdin=io.StringIO(json.dumps(approval)+'\n'+''.join(json.dumps({'text':text})+'\n' for text in inputs)+(json.dumps({'text':'UNREAD'})+'\n' if _extra else ''))
            args=argparse.Namespace(release_id='release',prepared=str(prepared),manifest=str(manifest),native_binding=str(binding_path),out=str(work/'C1-out'),
                    row=row['id'],packet=None,setup_checkpoint=str(checkpoint),setup_checkpoint_review=str(review_path),derivative_release=str(pending_release) if _pending else None)
            with mock.patch.object(n,'validate_derivative_continuation',return_value={'explicit_new_context':True,'pending_repeat_ack':{'synthetic':'validated by separate pure tests'}}),mock.patch.object(n,'released_source'),mock.patch.object(n,'bound_helpers',return_value=contextlib.nullcontext((helpers,[]))),mock.patch.object(n.subprocess,'run',return_value=types.SimpleNamespace(stdout='synthetic',returncode=0)) as processes,mock.patch.object(n.shutil,'copytree') as copytree,mock.patch.object(n,'recorded_rpc',side_effect=lambda rt,ar,r,o,sink,b:RPC(sink)),mock.patch.object(n,'live_bundle',side_effect=bundle),mock.patch.object(n,'validate_catalog',return_value={}),mock.patch.object(n,'native_selection_receipt',return_value={}),mock.patch.object(n,'reconcile_thread',return_value={}),mock.patch.object(n,'validate_startup',return_value='synthetic-unchanged'),mock.patch.object(n,'require_environment',return_value={}),mock.patch.object(n,'native_oracle',return_value={}),mock.patch.object(n.sys,'stdin',stdin),mock.patch.object(Path,'home',return_value=work/'fake-home'),mock.patch('builtins.print') as printed:
                n.run_row(args)
                copytree.assert_not_called()
                self.assertEqual([call.args[0] for call in processes.call_args_list],[['codex','--version']])
            self.assertEqual(texts,inputs);self.assertEqual(calls.count('thread/start'),1)
            completed=[json.loads(c.args[0])['completed_user_turn'] for c in printed.call_args_list if 'completed_user_turn' in c.args[0]]
            self.assertEqual(completed,list(range(1,len(inputs)+1)))
            if _extra:self.assertEqual(json.loads(stdin.readline()),{'text':'UNREAD'})
            self.assertTrue(all(rpc.closed for rpc in rpcs));self.assertEqual(n.sha(checkpoint),checkpoint_before);self.assertEqual(cp['baseline'],baseline_before)
            receipt=json.loads((work/'C1-out/setup-continuation-input-v1.json').read_text())
            self.assertTrue(receipt['explicit_new_context']);self.assertIn('pending_repeat_ack' if _pending else 'command_artifact_relation',receipt)

class C0DerivativeRecoveryTests(unittest.TestCase):
    def request(self):
        import json
        base=n.SOURCE/'.omx/ultragoal/evidence'
        design=json.loads((base/'codex-c0-artifact-recovery-design/index.json').read_text())
        def ref(path):return {'path':str(path),'sha256':n.sha(path)}
        prep=base/'g004/codex/native-v4/preparation/r7-setup-c0-final'
        run=base/'g004/codex/native-v4/runs-r7-setup-canary-RELEASE-REQUIRED'
        sources={name:ref(Path(next(p for p in design['pinned_inputs'] if 'uninstalled templates' in p and p.endswith('/'+name)))) for name in ['calc.py','tests/test_calc.py']}
        return {'schema':'frozen-c0-recovery-request-v1','manifest':ref(run/'FROZEN-C0-MANIFEST.json'),
                'design_index':ref(base/'codex-c0-artifact-recovery-design/index.json'),'design_report':ref(base/'codex-c0-artifact-recovery-design/REPORT.md'),
                'disposition':ref(base/'r7-parent-verification/codex-C0-recovery-disposition.json'),
                'parent_facts':ref(base/'r7-parent-verification/codex-C0-concrete-semantic-facts.json'),
                'recipe':ref(prep/'recipe.json'),'native_binding':ref(prep/'native-binding.json'),
                'runtime_release':ref(base/'r7-parent-verification/codex-setup-C0-runtime-release.json'),
                'product_manifest':ref(base/'source-repair-r7/manifest.json'),
                'predecessor_collector':ref(base/'codex-r7-command-review-r2-fix/archive/after-native_delta.py'),
                'sources':sources,'generated_expected':{k:v['sha256'] for k,v in design['generated_file_observations'].items()},
                'writer':{'event_index':106,'wire_index':143},'verifier':{'event_index':108,'wire_index':145}}

    def test_actual_frozen_shape_offline_derivative_no_process_and_no_v1_fabrication(self):
        from unittest import mock
        request=self.request();before=n.sha(request['manifest']['path'])
        with mock.patch.object(n.subprocess,'Popen',side_effect=AssertionError('no process')),mock.patch.object(n.subprocess,'run',side_effect=AssertionError('no process')):
            result=n.recover_frozen_c0(request)
        self.assertEqual(result['schema'],'codex-c0-derivative-observation-v1')
        self.assertEqual(result['status'],'HELD_DERIVATIVE_REQUIRES_ROOT_REVIEW')
        self.assertEqual(result['original_status'],'FROZEN_C0_UNVERIFIED_HELD_SCOPE_DRIFT_CLOSED')
        self.assertIsNone(result['closure']['app_server_exit_code'])
        self.assertNotIn('closed_process_returncode',result)
        self.assertEqual(len(result['generated_artifacts']['items']),2)
        self.assertEqual(result['source_bridge']['predecessor_collector_sha256'],'e58c83206e7181dc3a46ef8ae9043d55687675d77c298db259741c48e8b82fd3')
        self.assertEqual(n.sha(request['manifest']['path']),before)
        self.assertEqual(result,n.recover_frozen_c0(request))

    def test_altered_input_and_wrong_generated_binding_are_refused_offline(self):
        for mutation in ['manifest','writer','hash','source','extra']:
            with self.subTest(mutation=mutation):
                request=self.request()
                if mutation=='manifest':request['manifest']['sha256']='0'*64
                if mutation=='writer':request['writer']['wire_index']=145
                if mutation=='hash':request['generated_expected']['__pycache__/calc.cpython-314.pyc']='0'*64
                if mutation=='source':request['sources']['calc.py']['sha256']='0'*64
                if mutation=='extra':request['generated_expected']['__pycache__/extra.pyc']='0'*64
                with self.assertRaises(RuntimeError):n.recover_frozen_c0(request)

    def copied_request(self, work, mutation):
        import json
        request=self.request();original=Path(request['manifest']['path']).parent;copy=work/'frozen';copy.mkdir()
        manifest=json.loads(Path(request['manifest']['path']).read_text())
        for relative in manifest['files']:
            target=copy/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((original/relative).read_bytes())
        def change(relative,apply):
            path=copy/relative;data=json.loads(path.read_text());apply(data);n.write(path,data)
        if mutation=='wire':change('C0/live-rpc/rpc.json',lambda x:x[143]['payload']['params']['item'].update(command='wrong program'))
        if mutation=='closure':change('C0-terminal-handoff.json',lambda x:x.update(RPC_process_still_active=True))
        if mutation=='extra':change('C0/config-01.json',lambda x:x['after']['setup_scope'].update({'third.pyc':{'sha256':'0'*64,'realpath':'/foreign/third.pyc'}}))
        if mutation=='protected-alias':change('C0/config-01.json',lambda x:x['after']['setup_scope'][n.C0_GENERATED[0]].update(realpath='/etc/codex/config.toml'))
        if mutation=='preexisting':
            receipt=json.loads((copy/'C0/config-01.json').read_text())['after']['setup_scope'][n.C0_GENERATED[0]]
            change('C0/config-01.json',lambda x:x['before']['setup_scope'].update({n.C0_GENERATED[0]:receipt}))
            change('C0/before-config-01-v3.json',lambda x:x['setup_scope'].update({n.C0_GENERATED[0]:receipt}))
            change('C0/poststart-baseline-v3.json',lambda x:[x[k]['setup_scope'].update({n.C0_GENERATED[0]:receipt}) for k in ('first','second')])
        if mutation=='B0':change('C0/config-01.json',lambda x:x['before']['config'].update(unknown='changed'))
        manifest['files']={name:n.sha(copy/name) for name in manifest['files']};n.write(copy/'FROZEN-C0-MANIFEST.json',manifest)
        design=json.loads(Path(request['design_index']['path']).read_text())
        oldkey=next(k for k in design['pinned_inputs'] if k.endswith('FROZEN-C0-MANIFEST.json'))
        design['pinned_inputs'][str(copy/'FROZEN-C0-MANIFEST.json')]=dict(design['pinned_inputs'].pop(oldkey),sha256=n.sha(copy/'FROZEN-C0-MANIFEST.json'))
        n.write(work/'design.json',design)
        facts=json.loads(Path(request['parent_facts']['path']).read_text())
        facts['raw_bindings']={str(copy/str(Path(path).relative_to(original))):manifest['files'][str(Path(path).relative_to(original))] for path in facts['raw_bindings']}
        n.write(work/'facts.json',facts)
        for key,path in [('manifest',copy/'FROZEN-C0-MANIFEST.json'),('design_index',work/'design.json'),('parent_facts',work/'facts.json')]:request[key]={'path':str(path),'sha256':n.sha(path)}
        return request

    def test_copied_actual_shapes_wire_closure_delta_preexisting_and_alias_hold(self):
        for mutation in ['wire','closure','extra','protected-alias','preexisting','B0']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(RuntimeError):n.recover_frozen_c0(self.copied_request(Path(tmp),mutation))

    def reviews(self, d, work):
        digest=n.canonical_hash(d);bridge=d['source_bridge'];collector=n.sha(n.__file__)
        program={'schema':'EXTERNALLY_REVIEWED_PROGRAM_V1','derivative_sha256':digest,'context':d['context'],
                 'commands_sha256':n.canonical_hash(d['commands']),'writer':d['writer'],'verifier':d['verifier'],
                 'inventory':d['program_inventory'],'post_slots_sha256':n.canonical_hash(d['post_slots']),
                 'full_scope_delta_sha256':n.canonical_hash({'before':d['baseline']['setup_scope'],'after':d['terminal']['setup_scope']}),
                 'policy_sources_sha256':n.canonical_hash(d['policy_sources']),'parent_facts':d['external_parent_facts'],
                 'evidence':{key:'SYNTHETIC review data only, not root consent or an authority claim' for key in ('outer_quoting','imports','reads','writes','subprocesses','authority','scratch','limitations')}}
        review={'program':program,'generated':{'receipt_sha256':n.canonical_hash(d['generated_artifacts']),'items':d['generated_artifacts']['items'],
                    'evidence':{key:'Synthetic exact source/test/header/authority reference review' for key in n.C0_GENERATED}},
                'content':{'post_slots_sha256':n.canonical_hash(d['post_slots']),'policy_sources_sha256':n.canonical_hash(d['policy_sources']),'evidence':'Synthetic full byte/grant/import preservation review'},
                'scratch':{'disposition':d['request']['disposition'],'observation':d['scratch']['observation'],'historical_preimage':'UNVERIFIED',
                    'exclusive_ownership':'UNVERIFIED','decision':'ACCEPT_FINITE_OBSERVATION_WITH_UNVERIFIED_HISTORICAL_OWNERSHIP',
                    'authority_to_repeat_external_write':False,'evidence':'Synthetic bounded policy acceptance; no ownership reconstruction'}}
        source_report=work/'synthetic-source-review.txt';source_report.write_text('Synthetic report fixture only, not independent approval')
        source_review=work/'new-source-review.json';n.write(source_review,{'collector_sha256':collector,'verdict':'APPROVE_BOUNDED_DERIVATIVE_RECOVERY','report':{'path':str(source_report),'sha256':n.sha(source_report)},'fixture':'synthetic only'})
        review['independent_source_review']={'path':str(source_review),'sha256':n.sha(source_review)}
        root_review={'schema':'ROOT_C0_DERIVATIVE_ADJUDICATION_V1','derivative_sha256':digest,
            'program_review_sha256':n.canonical_hash(program),'generated_review_sha256':n.canonical_hash(review['generated']),
            'content_review_sha256':n.canonical_hash(review['content']),'scratch_review_sha256':n.canonical_hash(review['scratch']),
            'closure_sha256':n.canonical_hash(d['closure']),'B0_identity_sha256':n.canonical_hash(d['B0_identity']),
            'independent_source_review':review['independent_source_review'],'decision':'ELIGIBLE_FOR_BOUNDED_C1_AFTER_NEW_RELEASE_AND_USER'}
        n.write(work/'root-review.json',root_review);review['root_review']={'path':str(work/'root-review.json'),'sha256':n.sha(work/'root-review.json')}
        recipe={'adapter_sha256':collector,'derivative_source_bridge':{'predecessor_collector_sha256':bridge['predecessor_collector_sha256'],
                'predecessor_recipe_sha256':bridge['predecessor_recipe_sha256'],'collector_sha256':collector,
                'product_manifest_sha256':bridge['product_manifest_sha256'],'helper_imports_sha256':n.canonical_hash(bridge['helper_imports'])},
                'helper_imports':bridge['helper_imports'],'checkpoint_installed':d['terminal']['installed'],
                'predecessor_user_history':d['user_history'],'predecessor_recipe_sha256':bridge['predecessor_recipe_sha256'],
                'setup_repeat_text':d['original_setup_user_text'],'setup_content_ack_text':'Synthetic new actual content acknowledgment',
                '_verified_recipe_sha256':'synthetic-C1-recipe-hash'}
        release={'scope':'C1_FROM_REVIEWED_DERIVATIVE','explicit_parent_model_release':True,'release_id':'synthetic-NEW-C1-release',
                 'derivative_sha256':digest,'collector_sha256':collector,'max_new_contexts':1,'max_new_model_USER_turns':2,
                 'review_sha256':n.canonical_hash(review),'recipe_sha256':recipe['_verified_recipe_sha256']}
        approval={'role':'user','action':'approve_C1_from_derivative','new_context':True,'derivative_sha256':digest,
                  'review_sha256':n.canonical_hash(review),'release_sha256':n.canonical_hash(release),'text':'Synthetic USER fixture, not actual consent'}
        return copy.deepcopy((review,approval,recipe,release))

    def test_program_bridge_requires_new_source_root_artifact_policy_and_actual_USER(self):
        from unittest import mock
        d=n.recover_frozen_c0(self.request());original=copy.deepcopy(d)
        for mutation in ['none','program','target','policy','generic','USER','old-release','old-collector','source-review','scratch']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                review,approval,recipe,release=self.reviews(d,Path(tmp))
                if mutation=='program':review['program']['writer']['event']['params']['item']['command']='wrong'
                if mutation=='target':review['program']['inventory']=dict(review['program']['inventory'],explicit_writes=['other'])
                if mutation=='policy':review['program']['policy_sources_sha256']='wrong'
                if mutation=='generic':review['program']={'approved':True}
                if mutation=='USER':approval['role']='assistant'
                if mutation=='old-release':release['release_id']=d['contract']['release_id']
                if mutation=='old-collector':recipe['adapter_sha256']=d['source_bridge']['predecessor_collector_sha256']
                if mutation=='source-review':review['independent_source_review']['sha256']='0'*64
                if mutation=='scratch':review['scratch']['exclusive_ownership']='PROVED'
                with mock.patch.object(n,'validate_derivative_current') as live:
                    if mutation=='none':
                        result=n.validate_derivative_continuation(d,review,approval,Path(d['root']),recipe,d['source_bridge']['product_manifest_sha256'],release)
                        self.assertTrue(result['explicit_new_context']);live.assert_called_once()
                    else:
                        with self.assertRaises(RuntimeError):n.validate_derivative_continuation(d,review,approval,Path(d['root']),recipe,d['source_bridge']['product_manifest_sha256'],release)
                        live.assert_not_called()
                self.assertEqual(d,original)

    def test_future_failed_terminal_facts_are_saved_closed_without_latch_reset(self):
        from unittest import mock
        saved=[];close=n.close_setup_checkpoint
        def capture(rpc,checkpoint,path):
            close(rpc,checkpoint,path);saved.append(copy.deepcopy(checkpoint))
            self.assertTrue(Path(path).is_file());self.assertEqual(Path(path).name,'setup-terminal-held-facts-v2.json')
        with mock.patch.object(n.SetupArtifactEdge,'terminal',side_effect=RuntimeError('synthetic unexplained pyc delta')),mock.patch.object(n,'close_setup_checkpoint',side_effect=capture):
            with self.assertRaisesRegex(RuntimeError,'synthetic unexplained pyc delta'):
                SetupArtifactEdgeTests('test_mocked_live_dispatch_closes_at_terminal_edge_without_next_USER').test_mocked_live_dispatch_closes_at_terminal_edge_without_next_USER()
        self.assertEqual(len(saved),1);self.assertEqual(saved[0]['schema'],'setup-terminal-held-facts-v2');self.assertTrue(saved[0]['closed']);self.assertFalse(saved[0]['authorizes_dispatch'])

    def test_current_derivative_stale_cache_extra_file_and_protected_alias_hold(self):
        import os
        for mutation in ['none','stale','extra','alias']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);root=work/'consumer';root.mkdir();(root/'AGENTS.md').write_text('fixture');(root/'CLAUDE.md').write_text('@AGENTS.md\n')
                protected=work/'protected';protected.write_text('protected source fixture')
                generated=[]
                for name in n.C0_GENERATED:
                    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'synthetic cache')
                    generated.append({'logical_path':str(path),'realpath':str(path.resolve()),'sha256':n.sha(path)})
                d={'root':str(root),'post_slots':n.setup_slots(root,[protected]),'source_bridge':{},
                   'terminal':{'setup_scope':n.setup_scope(root),'files':{str(protected):{'exists':True,'realpath':str(protected.resolve()),'sha256':n.sha(protected)}}},
                   'generated_artifacts':{'items':generated}}
                if mutation=='stale':(root/n.C0_GENERATED[0]).write_bytes(b'changed')
                if mutation=='extra':(root/'third.pyc').write_bytes(b'unknown extra')
                if mutation=='alias':
                    path=root/n.C0_GENERATED[0];path.unlink();os.link(protected,path)
                    # Even an otherwise matching reviewed hash/scope cannot
                    # waive a current protected inode alias.
                    generated[0]['sha256']=n.sha(path);d['terminal']['setup_scope']=n.setup_scope(root)
                if mutation=='none':n.validate_derivative_current(d,{})
                else:
                    with self.assertRaises(RuntimeError):n.validate_derivative_current(d,{})

class IntercontextBridgeTests(unittest.TestCase):
    def fixture(self, work):
        import json
        b=n.SOURCE/'.omx/ultragoal/evidence'
        def ref(path):return {'path':str(path),'sha256':n.sha(path)}
        audit=checked=json.loads((b/'codex-C1-intercontext-config-audit/index.json').read_text())
        dref=ref(b/'codex-c0-derivative-recovery-implementation/offline-candidate/derivative-observation-v1.json')
        d=json.loads(Path(dref['path']).read_text())
        contexts=[]
        for i,context in enumerate(audit['contexts']):
            folder=n.SOURCE/Path(context['baseline_path']).parent
            if i==0:
                parent=folder.parent;auth=parent/'C0-authorization-receipt.json';op=parent/'C0-operator-result.json';closure=parent/'C0-terminal-handoff.json';release=b/'r7-parent-verification/codex-setup-C0-runtime-release.json'
            else:
                parent=folder.parent;auth=parent/'authorization-receipt.json';op=parent/(folder.name+'-operator-result.json')
                closure=op if i==1 else parent/('default-r7-build-questions-closure-inspection.json' if i==2 else 'copy-timeout-handoff.json')
                release=b/'r7-parent-verification'/('codex-build-questions-runtime-release.json' if i==1 else 'codex-questions-source55-runtime-release.json')
            rel=json.loads(release.read_text())
            binding=Path(rel['native_binding_path']) if i==0 else Path(rel['native_bindings'][folder.name]['path'])
            source=b/('codex-c0-derivative-recovery-implementation/archive/before-native_delta.py' if i<2 else 'codex-c0-derivative-recovery-implementation/archive/after-native_delta.py')
            contexts.append({'baseline':ref(folder/'poststart-baseline-v3.json'),'startup':ref(folder/'startup-diagnostic-v3.json'),
                'thread':ref(folder/'thread-start-v3.json'),'native':ref(folder/'live-native-selection-receipt.json'),'recorded_release':ref(folder/'release.json'),
                'source':ref(source),'release':ref(release),'authorization':ref(auth),'binding':ref(binding),
                'operator':ref(op),'closure':ref(closure),'closed_rpc':ref(folder/'live-rpc/closed.json'),'wire':ref(folder/'live-rpc/rpc.json'),
                'trust_root':audit['startup_edges'][i]['added_schema_roots'][0]})
        config_path=next(path for path,record in d['terminal']['files'].items() if record==audit['contexts'][0]['user_file'])
        receipt={'schema':'C1_INTERCONTEXT_TRUST_BRIDGE_V1','derivative':dref,'derivative_canonical_sha256':n.canonical_hash(d),
            'producer':ref(b/'codex-c0-derivative-recovery-implementation/archive/after-native_delta.py'),
            'producer_review':ref(b/'codex-c0-derivative-recovery-review-r1/index.json'),
            'validator_sha256':n.sha(n.__file__),'audit':ref(b/'codex-C1-intercontext-config-audit/index.json'),
            'audit_report':ref(b/'codex-C1-intercontext-config-audit/REPORT.md'),
            'disposition':ref(b/'r7-parent-verification/codex-intercontext-bridge-plan-disposition.json'),
            'plan_review':ref(b/'codex-intercontext-bridge-plan-review/index.json'),
            'plan_report':ref(b/'codex-intercontext-bridge-plan-review/REPORT.md'),
            'endpoint_witness':ref(b/'r7-parent-verification/codex-C1-after-closure-config-endpoint.json'),'contexts':contexts,
            'config_path':config_path,'old_user_file':audit['contexts'][0]['user_file'],'endpoint_user_file':audit['contexts'][-1]['user_file'],
            'evidence_boundary':'RECORDED_RAW_COMPARATOR_UNDER_EXPLICIT_ROOT_TRUST_NOT_INDEPENDENT_RAW_REPLAY'}
        path=work/'synthetic-bridge.json';n.write(path,receipt)
        return d,receipt,ref(path)

    def test_captured_chain_and_source55_producer_recomputation_are_exact(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            d,receipt,reference=self.fixture(Path(tmp));original=n.canonical_hash(d)
            result=n.inspect_intercontext_bridge(d,reference)
            self.assertEqual(result['old_user_file']['sha256'][:4],'348d')
            self.assertEqual(result['endpoint_user_file']['sha256'][:5],'bbcee')
            n.verify_derivative_producer(d,{'intercontext_bridge':reference})
            self.assertEqual(n.canonical_hash(d),original)
            self.assertEqual(json.loads(Path(receipt['derivative']['path']).read_text()),d)

    def test_missing_reordered_unknown_root_release_closure_and_endpoint_hold(self):
        for mutation in ['missing','reordered','root','release','closure','source','endpoint','derivative','extra-edge','old-endpoint','closure-hash','witness']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                d,receipt,reference=self.fixture(Path(tmp))
                if mutation=='missing':receipt['contexts'].pop()
                if mutation=='reordered':receipt['contexts'][1:3]=list(reversed(receipt['contexts'][1:3]))
                if mutation=='root':receipt['contexts'][2]['trust_root']='/unknown/project'
                if mutation=='release':receipt['contexts'][2]['release']=receipt['contexts'][1]['release']
                if mutation=='closure':receipt['contexts'][3]['closure']=receipt['contexts'][2]['closure']
                if mutation=='source':receipt['contexts'][2]['source']=receipt['contexts'][0]['source']
                if mutation=='endpoint':receipt['endpoint_user_file']['sha256']='0'*64
                if mutation=='derivative':receipt['derivative_canonical_sha256']='0'*64
                if mutation=='extra-edge':receipt['contexts'].append(copy.deepcopy(receipt['contexts'][-1]))
                if mutation=='old-endpoint':receipt['old_user_file']['sha256']='0'*64
                if mutation=='closure-hash':receipt['contexts'][3]['closed_rpc']['sha256']='0'*64
                if mutation=='witness':receipt['endpoint_witness']['sha256']='0'*64
                n.write(reference['path'],receipt);reference['sha256']=n.sha(reference['path'])
                with self.assertRaises(RuntimeError):n.inspect_intercontext_bridge(d,reference)

    def test_unknown_config_changes_and_nonproducer_recomputation_difference_hold(self):
        from unittest import mock
        import json
        with tempfile.TemporaryDirectory() as tmp:
            d,receipt,reference=self.fixture(Path(tmp))
            audit=json.loads(Path(receipt['audit']['path']).read_text());frame=receipt['contexts'][2]
            startup=json.loads(Path(frame['startup']['path']).read_text());before=startup['preflight']['config'];after=startup['post_start']['config']
            changed=copy.deepcopy(after);changed['safe_identity']['fields']['model']='0'*64
            with self.assertRaisesRegex(RuntimeError,'unknown retained config'):n.retained_trust_edge(before,changed,frame['trust_root'])
            recomputed=copy.deepcopy(d);recomputed['source_bridge']['recovery_collector_sha256']=n.sha(n.__file__);recomputed['context']['thread_id']='wrong'
            with mock.patch.object(n,'recover_frozen_c0',return_value=recomputed):
                with self.assertRaisesRegex(RuntimeError,'beyond producer identity'):n.verify_derivative_producer(d,{'intercontext_bridge':reference})

    def test_C1_chain_requires_new_source_root_release_and_USER_binding(self):
        from unittest import mock
        import json
        for mutation in ['none','source-verdict','root-trust','release','USER']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);d,receipt,reference=self.fixture(work)
                review,approval,recipe,release=C0DerivativeRecoveryTests().reviews(d,work)
                recipe['intercontext_bridge']=reference
                recipe['derivative_source_bridge'].update(producer_collector_sha256=d['source_bridge']['recovery_collector_sha256'],intercontext_bridge_sha256=reference['sha256'])
                trust={'receipt':reference,'producer':receipt['producer'],'decision':'ACCEPT_RECORDED_CLASSIFIER_UNDER_EXPLICIT_ROOT_TRUST',
                       'limits':{'raw_projects_origins_reconstructed':False,'independent_raw_replay':False,'raw_file_hash_equality_claim':False,'exclusive_historical_causality':False},
                       'evidence':'Synthetic fixture: exact closed authorized roots/classifiers and continuous captures; not raw replay'}
                review['intercontext_bridge_review']=trust
                source=json.loads(Path(review['independent_source_review']['path']).read_text());source['verdict']='APPROVE_BOUNDED_INTERCONTEXT_BRIDGE_IMPLEMENTATION'
                if mutation=='source-verdict':source['verdict']='APPROVE_BOUNDED_DERIVATIVE_RECOVERY'
                n.write(review['independent_source_review']['path'],source);review['independent_source_review']['sha256']=n.sha(review['independent_source_review']['path'])
                root=json.loads(Path(review['root_review']['path']).read_text());root['independent_source_review']=review['independent_source_review'];root['intercontext_bridge_review_sha256']=n.canonical_hash(trust)
                n.write(review['root_review']['path'],root);review['root_review']['sha256']=n.sha(review['root_review']['path'])
                release.update(intercontext_bridge_sha256=reference['sha256'],producer_collector_sha256=d['source_bridge']['recovery_collector_sha256'],review_sha256=n.canonical_hash(review))
                approval.update(intercontext_bridge_sha256=reference['sha256'],review_sha256=n.canonical_hash(review),release_sha256=n.canonical_hash(release))
                if mutation=='root-trust':review['intercontext_bridge_review']['limits']['independent_raw_replay']=True
                if mutation=='release':release['intercontext_bridge_sha256']='unbound'
                if mutation=='USER':approval.pop('intercontext_bridge_sha256')
                with mock.patch.object(n,'validate_derivative_current') as current:
                    if mutation=='none':
                        result=n.validate_derivative_continuation(d,review,approval,Path(d['root']),recipe,d['source_bridge']['product_manifest_sha256'],release)
                        self.assertTrue(result['explicit_new_context']);current.assert_called_once()
                    else:
                        with self.assertRaises(RuntimeError):n.validate_derivative_continuation(d,review,approval,Path(d['root']),recipe,d['source_bridge']['product_manifest_sha256'],release)
                        current.assert_not_called()

    def test_only_one_current_config_tuple_after_closures_and_known_collector(self):
        from unittest import mock
        import hashlib,os
        for mutation in ['none','endpoint','missing','realpath','other-file','alternate-path','collector','alias']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);root=work/'consumer';root.mkdir();(root/'AGENTS.md').write_text('fixture');(root/'CLAUDE.md').write_text('@AGENTS.md\n')
                config=work/'config.toml';config.write_text('captured endpoint fixture')
                protected=work/'source';protected.write_text('protected source')
                generated=[]
                for name in n.C0_GENERATED:
                    path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'cache fixture')
                    generated.append({'logical_path':str(path),'realpath':str(path.resolve()),'sha256':n.sha(path)})
                def record(path):return {'exists':True,'realpath':str(path.resolve()),'sha256':n.sha(path)}
                old=record(config);old['sha256']=hashlib.sha256(b'old C0 fixture').hexdigest();endpoint=record(config)
                collector=Path(n.__file__).resolve();original_collector='e58-old-fixture'
                files={str(config):old,str(protected):record(protected),str(collector):dict(record(collector),sha256=original_collector)}
                d={'root':str(root),'post_slots':n.setup_slots(root,list(files)),'terminal':{'setup_scope':n.setup_scope(root),'files':files},
                   'generated_artifacts':{'items':generated},'source_bridge':{'predecessor_collector_sha256':original_collector,'recovery_collector_sha256':'55-producer-fixture'}}
                bound={'config_path':str(config),'old_user_file':copy.deepcopy(old),'endpoint_user_file':endpoint,'validator_sha256':n.sha(n.__file__)}
                if mutation=='endpoint':config.write_text('later unexplained drift')
                if mutation=='missing':config.unlink()
                if mutation=='realpath':files[str(config)]['realpath']=str(work/'another-realpath')
                if mutation=='other-file':protected.write_text('unexplained source change')
                if mutation=='alternate-path':bound['config_path']=str(work/'another-config.toml')
                if mutation=='collector':files[str(collector)]['sha256']='unknown-old-collector'
                if mutation=='alias':
                    path=Path(generated[0]['logical_path']);path.unlink();os.link(config,path);generated[0]['sha256']=n.sha(path);d['terminal']['setup_scope']=n.setup_scope(root)
                order=[];real_sha=n.sha
                def digest(path):
                    if Path(path)==config:order.append('current config digest')
                    return real_sha(path)
                def verified(*args):order.append('all exact closures checked');return bound
                with mock.patch.object(n,'inspect_intercontext_bridge',side_effect=verified),mock.patch.object(n,'sha',side_effect=digest):
                    if mutation=='none':
                        n.validate_derivative_current(d,{'intercontext_bridge':{'synthetic':'fixture'}})
                        self.assertLess(order.index('all exact closures checked'),order.index('current config digest'))
                    else:
                        with self.assertRaises(RuntimeError):n.validate_derivative_current(d,{'intercontext_bridge':{'synthetic':'fixture'}})

    def test_discontinuous_capture_and_changed_classifier_AST_are_held(self):
        from unittest import mock
        import json
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);d,receipt,reference=self.fixture(work)
            real=n.checked_json
            def discontinuous(ref):
                value=real(ref)
                if ref==receipt['contexts'][2]['startup']:
                    value['preflight']['config']['safe_identity']['fields']['model']='0'*64
                return value
            with mock.patch.object(n,'checked_json',side_effect=discontinuous):
                with self.assertRaisesRegex(RuntimeError,'discontinuous intercontext'):n.inspect_intercontext_bridge(d,reference)
            source=Path(receipt['producer']['path']).read_text().replace("return 'persisted-trust-only'","return 'unsupported-classification'",1)
            altered=work/'synthetic-changed-source.py';altered.write_text(source)
            with self.assertRaisesRegex(RuntimeError,'changed source-bound classifier'):
                n.pinned_source_ast({'path':str(altered),'sha256':n.sha(altered)},['startup_relation','validate_startup'])

class CurrentAuthorContinuationTests(unittest.TestCase):
    def test_complete_inventory_includes_empty_git_cache_modes_and_aliases(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root';root.mkdir();(root/'.git/objects').mkdir(parents=True)
            (root/'app/__pycache__').mkdir(parents=True);p=root/'app/__pycache__/x.pyc';p.write_bytes(b'cache')
            first=n.current_author_inventory(root)
            self.assertIn('.git/objects',first);self.assertIn('app/__pycache__/x.pyc',first)
            p.chmod(0o600);self.assertNotEqual(first,n.current_author_inventory(root))
            os.link(p,root/'alias')
            with self.assertRaises(RuntimeError):n.current_author_inventory(root)
            (root/'alias').unlink();(root/'escape').symlink_to(root.parent)
            with self.assertRaises(RuntimeError):n.current_author_inventory(root)

    def test_deadline_only_exact_released_row_and_types(self):
        row={'id':'copy-r7-build-authority-continuation','terminal_deadline_seconds':360,'max_user_turns':1,'mode':'copy','transport':'live'}
        self.assertEqual(n.current_author_seconds(row,True),360)
        self.assertEqual(n.current_author_seconds({'id':'ordinary','terminal_deadline_seconds':360},False),180)
        for key,value in [('terminal_deadline_seconds',True),('terminal_deadline_seconds','360'),('terminal_deadline_seconds',359),('max_user_turns',True),('transport','cli'),('id','other')]:
            with self.subTest(key=key,value=value),self.assertRaises(RuntimeError):n.current_author_seconds(dict(row,**{key:value}),True)

    def fixture(self,work,cp_change=None):
        import json
        base=n.SOURCE/'.omx/ultragoal/evidence/g004/codex/native-v6/runs-question-layout-source55-RELEASE-REQUIRED'
        diag=n.SOURCE/'.omx/ultragoal/evidence/g004/codex/native-v7/preparation/copy-timeout-current-state'
        def ref(p):return {'path':str(p),'sha256':n.sha(p)}
        index=json.loads((diag/'index.json').read_text());plan=json.loads((diag/'plan.json').read_text())
        inventory={k:{'kind':'file','sha256':v['sha256'],'mode':v['mode'],'realpath':v['realpath']} for k,v in index['current_project_before_readonly_hashes_modes_paths'].items()}
        inventory['.']={'kind':'directory','realpath':plan['same_consumer']['canonical']}
        cp={'schema':'current-author-checkpoint-v1','diagnosis_index':ref(diag/'index.json'),
            'predecessor':index['pinned_frozen_evidence'],'root':plan['same_consumer']['logical'],'realroot':plan['same_consumer']['canonical'],
            'inventory':inventory,'absent':['.git/index','.git/HEAD.lock','.git/index.lock'],
            'prior_recipe':ref(base.parent/'preparation/questions-source55-review-pending/recipe.json'),
            'prior_authorization':ref(base/'authorization-receipt.json'),
            'prior_collector':ref(n.SOURCE/'.omx/ultragoal/evidence/codex-c0-derivative-recovery-implementation/archive/after-native_delta.py'),
            'server_returncode':None,'successful_terminal3':False,'postcomparison3':None,
            'settled_USER':plan['same_consumer']['settled_actual_USER_0600'],'memo':plan['same_consumer']['actual_recorded_memo']}
        # Exact source55 archive, not current integrated collector.
        candidates=list((n.SOURCE/'.omx/ultragoal/evidence').glob('*/archive/*native_delta.py'))
        cp['prior_collector']=next(ref(p) for p in candidates if n.sha(p)=='55a87d72995f90d288d306216648472ce82507b9fb811173c1deeda3888c6a73')
        if cp_change:cp.update(cp_change)
        checkpoint=work/'checkpoint.json';n.write(checkpoint,cp)
        manifest=n.SOURCE/'.omx/ultragoal/evidence/source-repair-r7/manifest.json'
        # Use exact predecessor manifest path from its prepared recipe.
        old=json.loads(Path(cp['prior_recipe']['path']).read_text());manifest=Path(old['release_manifest'])
        row={'id':'copy-r7-build-authority-continuation','mode':'copy','transport':'live','max_user_turns':1,'terminal_deadline_seconds':360,
             'initial_user_text':plan['draft_future_actual_USER_text_UNSENT'],'execution_kind':'current-author-continuation'}
        recipe={'execution_kind':'current-author-continuation','rows':[row],'current_author_checkpoint':ref(checkpoint),
            'adapter_sha256':n.sha(n.__file__),'release_manifest':str(manifest),'release_manifest_sha256':n.sha(manifest),
            'helper_imports':old['helper_imports'],'checkpoint_installed':json.loads((base/'copy-r7-build-questions/installed.json').read_text())['inventory']}
        recipe_path=work/'recipe.json';n.write(recipe_path,recipe)
        native=work/'native-premises.json';n.write(native,{'scope':'configured-native-selector','proof_sha256':plan['proposed_runtime_premises']['native_source_proof']['sha256'],
            'forward_thread_expectation':plan['proposed_runtime_premises']['proposed13fields'],'forward_trust_root':plan['proposed_runtime_premises']['canonical_trust_root']})
        bindings={'checkpoint_sha256':n.sha(checkpoint),'recipe_sha256':n.sha(recipe_path),'collector_sha256':n.sha(n.__file__),
                  'helpers':recipe['helper_imports'],'manifest_sha256':n.sha(manifest),'native_premises_sha256':n.sha(native)}
        source=work/'source-review.json';n.write(source,dict(bindings,schema='current-author-source-review-v1',verdict='APPROVE',report=ref(n.SOURCE/'.omx/ultragoal/evidence/codex-intercontext-bridge-plan-review/REPORT.md')))
        root=work/'root-review.json';n.write(root,dict(bindings,schema='current-author-root-review-v1',verdict='APPROVE',source_review_sha256=n.sha(source),
            inventory_sha256=n.canonical_hash(inventory),settled_USER=cp['settled_USER'],memo=cp['memo'],
            scope='approved spec/tasks; T1-T3 done; T4/AC9 pending; no Git authority',input_change='none',
            user_sha256=hashlib.sha256(row['initial_user_text'].encode()).hexdigest(),input_base_sha256=hashlib.sha256(plan['draft_future_actual_USER_text_UNSENT'].encode()).hexdigest(),report=ref(diag/'REPORT.md')))
        release=work/'release.json';n.write(release,dict(bindings,schema='current-author-release-v1',release_id='new-release',row_id=row['id'],
            root=cp['root'],realroot=cp['realroot'],source_review=ref(source),root_review=ref(root),native_premises=ref(native),
            user_sha256=hashlib.sha256(row['initial_user_text'].encode()).hexdigest(),new_contexts=1,new_USER_turns=1,terminal_deadline_seconds=360,
            actual_before=18,held_before=88,whole_ceiling=106,unused_question_turns=1,out=str((work/'out').resolve())))
        binding={'scope':'configured-native-selector','current_author_release_sha256':n.sha(release),'native_premises_sha256':n.sha(native),'proof_sha256':plan['proposed_runtime_premises']['native_source_proof']['sha256'],
            'forward_thread_expectation':plan['proposed_runtime_premises']['proposed13fields'],'forward_trust_root':plan['proposed_runtime_premises']['canonical_trust_root']}
        return checkpoint,release,recipe_path,row,binding,inventory

    def test_actual_shaped_closed_timeout_and_review_chain(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);cp,release,recipe,row,binding,inventory=self.fixture(work)
            with mock.patch.object(n,'current_author_inventory',return_value=inventory):
                result=n.validate_current_author(cp,release,recipe,row,binding,'new-release',work/'out')
            self.assertEqual(result['root'],__import__('json').loads(cp.read_text())['root'])
            self.assertIsNone(result['server_returncode'])
            self.assertFalse(result['successful_terminal3'])
            self.assertEqual(result['prior_body_event_index'],28)

    def test_changed_inventory_and_concrete_references_fail_closed(self):
        import json
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);cp,release,recipe,row,binding,inventory=self.fixture(work)
            for key in ['.git/HEAD','AGENTS.md','docs/ains/human-review-rules','docs/changes/2026-10-25-email-notification-toggle/tasks.md']:
                changed=copy.deepcopy(inventory);changed[key]['sha256']='wrong'
                with self.subTest(key=key),mock.patch.object(n,'current_author_inventory',return_value=changed),self.assertRaises(RuntimeError):
                    n.validate_current_author(cp,release,recipe,row,binding,'new-release',work/'out')
            changed=dict(inventory,**{'app/__pycache__/extra.pyc':{'kind':'file','sha256':'extra'}})
            with mock.patch.object(n,'current_author_inventory',return_value=changed),self.assertRaises(RuntimeError):
                n.validate_current_author(cp,release,recipe,row,binding,'new-release',work/'out')
            for key,value in [('successful_terminal3',True),('server_returncode',0),('postcomparison3',{}),('predecessor',{}),('settled_USER',{}),('memo',{})]:
                original=cp.read_bytes();data=json.loads(original);data[key]=value;n.write(cp,data)
                with self.subTest(key=key),mock.patch.object(n,'current_author_inventory',return_value=inventory),self.assertRaises(RuntimeError):
                    n.validate_current_author(cp,release,recipe,row,binding,'new-release',work/'out')
                cp.write_bytes(original)
            for key,value in [('user_sha256','wrong'),('terminal_deadline_seconds',True),('new_USER_turns',2),('root','wrong'),('source_review',{'path':str(cp),'sha256':n.sha(cp)}),('out',str(work/'other'))]:
                original=release.read_bytes();data=json.loads(original);data[key]=value;n.write(release,data)
                with self.subTest(key=key),mock.patch.object(n,'current_author_inventory',return_value=inventory),self.assertRaises(RuntimeError):
                    n.validate_current_author(cp,release,recipe,row,dict(binding,current_author_release_sha256=n.sha(release)),'new-release',work/'out')
                release.write_bytes(original)

    def test_fully_rebound_forged_timeout_fields_and_decision_still_reject(self):
        from unittest import mock
        cases=[{'successful_terminal3':True},{'server_returncode':0},{'postcomparison3':{}},{'predecessor':{}},
               {'settled_USER':{}},{'memo':{}},{'root':'wrong consumer'},{'absent':[]},{'prior_collector':{'path':str(n.__file__),'sha256':n.sha(n.__file__)}}]
        for changed in cases:
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as tmp:
                cp,release,recipe,row,binding,inventory=self.fixture(Path(tmp),changed)
                with mock.patch.object(n,'current_author_inventory',return_value=inventory),self.assertRaises(RuntimeError):
                    n.validate_current_author(cp,release,recipe,row,binding,'new-release',Path(tmp)/'out')

    def test_source_root_native_and_hash_verdicts_are_decisive(self):
        import json
        from unittest import mock
        for target,key,value in [('source-review.json','verdict','PENDING'),('root-review.json','scope','Git authorized'),
                                 ('root-review.json','settled_USER',{}),('root-review.json','user_sha256','wrong'),
                                 ('root-review.json','inventory_sha256','wrong')]:
            with self.subTest(target=target,key=key),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);cp,release,recipe,row,binding,inventory=self.fixture(work)
                path=work/target;doc=json.loads(path.read_text());doc[key]=value;n.write(path,doc)
                rel=json.loads(release.read_text());rel['source_review' if target=='source-review.json' else 'root_review']['sha256']=n.sha(path);n.write(release,rel)
                binding['current_author_release_sha256']=n.sha(release)
                with mock.patch.object(n,'current_author_inventory',return_value=inventory),self.assertRaises(RuntimeError):
                    n.validate_current_author(cp,release,recipe,row,binding,'new-release',work/'out')
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);cp,release,recipe,row,binding,inventory=self.fixture(work)
            binding['forward_thread_expectation']['modelProvider']='wrong'
            with mock.patch.object(n,'current_author_inventory',return_value=inventory),self.assertRaises(RuntimeError):
                n.validate_current_author(cp,release,recipe,row,binding,'new-release',work/'out')

    def dispatch(self,work,scenario='success',at=250):
        import argparse,contextlib,io,json,types
        from unittest import mock
        root=work/'consumer';root.mkdir();(root/'AGENTS.md').write_text('unchanged grants')
        (root/'setup.sh').write_text('must never execute');inventory=n.current_author_inventory(root)
        manifest=work/'manifest';n.write(manifest,{'suite_files':{}});proof=work/'proof';proof.write_text('proof')
        row={'id':'copy-r7-build-authority-continuation','execution_kind':'current-author-continuation','mode':'copy','transport':'live','max_user_turns':1,'terminal_deadline_seconds':360,'initial_user_text':'$ains-build actual reviewed input'}
        recipe={'execution_kind':'current-author-continuation','current_author_checkpoint':{'path':'synthetic-checkpoint','sha256':'synthetic checkpoint hash'},'rows':[row],'release_manifest':str(manifest),'release_manifest_sha256':n.sha(manifest),'adapter_sha256':n.sha(n.__file__),'helper_imports':[],'checkpoint_installed':[]}
        n.write(work/'recipe.json',recipe)
        expected={k:None for k in n.THREAD_FIELDS};expected['instructionSources']=[]
        binding={'codex_version':'synthetic','parent_release_id':'release','scope':'configured-native-selector','proof_path':str(proof),'proof_sha256':n.sha(proof),'transports':['live'],'forward_thread_expectation':expected,'forward_trust_root':str(root)}
        n.write(work/'binding.json',binding)
        args=argparse.Namespace(release_id='release',prepared=str(work),manifest=str(manifest),native_binding=str(work/'binding.json'),out=str(work/'out'),row=row['id'],packet=None,setup_checkpoint=None,current_author_checkpoint='synthetic-checkpoint',current_author_release='synthetic-release')
        cp={'root':str(root),'inventory':inventory,'current_release_sha256':'synthetic release hash'}
        calls=[];instances=[];clock=[0];bundles=[0]
        class RPC:
            def __init__(self,sink):
                self.sink=Path(sink);self.sink.mkdir();self.log=[];self.events=[];self.selected_environment={};self.closed=False;self.bound_thread=None
                self.p=types.SimpleNamespace(pid=42,poll=lambda:0 if self.closed else None);instances.append(self)
            def call(self,method,params,timeout=30):
                calls.append((method,params))
                if method=='thread/start':return {'thread':{'id':'fresh-thread'}}
                if method=='turn/start':
                    e={'method':'turn/started','params':{'turn':{'id':'fresh-turn','status':'inProgress'}}}
                    self.events=[e];self.log.append({'direction':'response_or_event','payload':e})
                return {'config':{},'layers':[]}
            def next(self,deadline):
                calls.append(('deadline',deadline));clock[0]=at
                if at>deadline and scenario!='buffered-late':raise TimeoutError('synthetic absolute deadline')
                e={'method':'turn/completed','params':{'turn':{'id':'fresh-turn','status':'completed','error':None}}}
                if scenario=='structured':e={'id':'authority','method':'item/tool/requestUserInput','params':{'questions':[{'id':'git','question':'Allow Git?'}]}}
                self.log.append({'direction':'response_or_event','payload':e});return e
            def close(self):self.closed=True;n.write(self.sink/'closed.json',{'synthetic_closed':True})
        def bundle(rpc,*unused):
            bundles[0]+=1
            if len([x for x in calls if x[0]=='turn/start']) and scenario=='drain-structured':
                rpc.log.append({'direction':'response_or_event','payload':{'id':'late-authority','method':'item/tool/requestUserInput','params':{'questions':[]}}})
            if len([x for x in calls if x[0]=='turn/start']) and scenario=='late-error':
                rpc.log.append({'direction':'response_or_event','payload':{'method':'error','params':{'error':{'message':'late error'}}}})
            value={'files':{},'catalog_proof':{},'environment':{},'config':{'stable':True}}
            if len([x for x in calls if x[0]=='turn/start']) and scenario=='drift':value['config']['stable']=False
            if scenario=='before-drift' and bundles[0]==4:(root/'unexpected').write_text('drift')
            return value,{'config':{},'layers':[]}
        a=types.SimpleNamespace(probe=lambda r:{'files':{},'all_layer_mcp_names':[]},inventory=lambda r:[],CANONICAL=n.CANONICAL_FEATURES)
        helpers={'runtime':types.SimpleNamespace(snapshot=lambda r:{}),'activation_recheck':types.SimpleNamespace(write=n.write),'activation_r3':a,'activation_closure_probe':types.SimpleNamespace(structural=lambda c:{})}
        stream=io.StringIO(json.dumps({'text':row['initial_user_text'] if scenario!='wrong-user' else 'not reviewed'})+'\n'+json.dumps({'text':'MUST REMAIN UNREAD'})+'\n')
        def process(argv,**kwargs):
            self.assertEqual(argv,['codex','--version']);return types.SimpleNamespace(stdout='synthetic',returncode=0)
        with mock.patch.object(n,'validate_current_author',return_value=cp),mock.patch.object(n,'released_source'),mock.patch.object(n,'bound_helpers',return_value=contextlib.nullcontext((helpers,[]))),mock.patch.object(n.subprocess,'run',side_effect=process),mock.patch.object(n.shutil,'copytree',side_effect=AssertionError('no copy')),mock.patch.object(n,'recorded_rpc',side_effect=lambda rt,ar,r,ov,s,b:RPC(s)),mock.patch.object(n,'live_bundle',side_effect=bundle),mock.patch.object(n,'validate_catalog',return_value={}),mock.patch.object(n,'native_selection_receipt',return_value={}),mock.patch.object(n,'reconcile_thread',return_value={}),mock.patch.object(n,'validate_startup',return_value='synthetic unchanged'),mock.patch.object(n,'require_environment',return_value={}),mock.patch.object(n,'native_oracle',return_value={}),mock.patch.object(n.sys,'stdin',stream),mock.patch.object(Path,'home',return_value=work/'fake-home'),mock.patch.object(n.time,'monotonic',side_effect=lambda:clock[0]),mock.patch('builtins.print'):
            error=None
            try:n.run_row(args)
            except (RuntimeError,TimeoutError) as caught:error=caught
        self.assertTrue(all(r.closed for r in instances))
        self.assertEqual(len([x for x in calls if x[0]=='thread/start']),1)
        self.assertEqual(stream.readline(),json.dumps({'text':'MUST REMAIN UNREAD'})+'\n')
        self.assertFalse(any(x[0] in ('thread/resume','send') for x in calls))
        self.assertEqual((root/'AGENTS.md').read_text(),'unchanged grants')
        return error,calls,work/'out'

    def test_same_current_root_fresh_one_turn_181_to_359_without_copy_install_or_next_input(self):
        import json
        for elapsed in [181,250,359]:
            with self.subTest(elapsed=elapsed),tempfile.TemporaryDirectory() as tmp:
                error,calls,out=self.dispatch(Path(tmp),at=elapsed)
                self.assertIsNone(error)
                self.assertEqual(len([x for x in calls if x[0]=='turn/start']),1)
                self.assertIn(('deadline',360),calls)
                self.assertEqual(json.loads((out/'current-author-observation-v1.json').read_text())['status'],'OBSERVED_CURRENT_AUTHOR_TERMINAL_REQUIRES_PARENT_REVIEW')
                self.assertTrue((out/'config-01.json').is_file());self.assertTrue((out/'current-author-closure-v1.json').is_file())

    def test_structured_authority_timeout_late_error_and_drift_are_retained_not_healthy(self):
        import json
        for scenario,elapsed in [('structured',200),('timeout',361),('buffered-late',361),('buffered-late',360),('late-error',200),('drain-structured',200),('drift',200),('wrong-user',200),('before-drift',200)]:
            with self.subTest(scenario=scenario),tempfile.TemporaryDirectory() as tmp:
                error,calls,out=self.dispatch(Path(tmp),scenario,elapsed)
                self.assertIsNotNone(error)
                self.assertFalse((out/'current-author-observation-v1.json').exists())
                self.assertTrue((out/'current-author-closure-v1.json').is_file())
                if scenario not in ('wrong-user','before-drift'):self.assertTrue((out/'turn-01.json').is_file())
                if scenario=='before-drift':self.assertFalse(any(x[0]=='turn/start' for x in calls))
                if scenario=='timeout':
                    partial=json.loads((out/'turn-01.json').read_text());self.assertEqual(partial['seconds'],361)
                    self.assertEqual(partial['events'][0]['method'],'turn/started');self.assertFalse((out/'config-01.json').exists())
                if scenario=='structured':
                    self.assertEqual(json.loads((out/'pending-01.json').read_text())['id'],'authority')
                    self.assertFalse((out/'user-ui-response-01.json').exists())

    def test_modes_cannot_mix_or_select_unreleased_transport(self):
        import argparse
        row={'id':'copy-r7-build-authority-continuation','execution_kind':'current-author-continuation','mode':'copy','transport':'live','max_user_turns':1,'terminal_deadline_seconds':360}
        recipe={'execution_kind':'current-author-continuation'}
        args=argparse.Namespace(current_author_checkpoint='checkpoint',current_author_release='release')
        self.assertTrue(n.current_author_mode(args,recipe,row,{}))
        for key in ['setup_checkpoint','setup_checkpoint_review','derivative_release','packet']:
            with self.subTest(key=key),self.assertRaises(RuntimeError):n.current_author_mode(argparse.Namespace(**dict(vars(args),**{key:'foreign'})),recipe,row,{})
        with self.assertRaises(RuntimeError):n.current_author_mode(args,recipe,dict(row,transport='cli'),{})
        with self.assertRaises(RuntimeError):n.current_author_mode(args,recipe,row,{'setup_artifact_contract':{'stage':'setup'}})
        with self.assertRaises(RuntimeError):n.current_author_mode(argparse.Namespace(current_author_checkpoint='only'),recipe,row,{})

class CanonicalEdgePendingRepeatTests(unittest.TestCase):
    ACK=n.SOURCE/'.omx/ultragoal/evidence/g004/codex/native-v9/runs-C1-source62-operatorfix-RELEASE-REQUIRED'

    def actual(self,work):
        import json
        d,bridge,reference=IntercontextBridgeTests().fixture(work)
        old=json.loads((n.SOURCE/'.omx/ultragoal/evidence/g004/codex/native-v8/preparation/C1-source62-bridge/recipe.json').read_text())
        recipe=dict(old,intercontext_bridge=reference,pending_repeat_ack={'path':str(self.ACK/'FROZEN-MANIFEST.json'),'sha256':n.sha(self.ACK/'FROZEN-MANIFEST.json')})
        row=dict(recipe['rows'][0],initial_user_text=recipe['setup_repeat_text'],max_user_turns=1);recipe['rows']=[row]
        return d,recipe,n.inspect_intercontext_bridge(d,reference)

    def test_actual_serialized_equal_ack_and_roundtrip_use_same_immutable_identity(self):
        import json
        held=json.loads((self.ACK/'setup-terminal-held-facts-v2.json').read_text())
        baseline=json.loads((self.ACK/'poststart-baseline-v3.json').read_text())
        edge=n.SetupArtifactEdge(held['baseline'],held['contract'],Path(held['contract']['root']),held['contract']['row_id'])
        self.assertTrue(edge.unchanged(held['terminal']));self.assertEqual(baseline['first'],baseline['second'])
        before=copy.deepcopy(held['baseline']);before['synthetic_tuple']=(1,2)
        edge=n.SetupArtifactEdge(before,held['contract'],Path(held['contract']['root']),held['contract']['row_id'])
        after=json.loads(json.dumps(before));self.assertNotEqual(before,after)
        self.assertTrue(edge.unchanged(after));edge.strict.check(after)
        after['synthetic_tuple'][1]=3;self.assertFalse(edge.unchanged(after))
        with self.assertRaises(RuntimeError):edge.strict.check(after)
        with self.assertRaises(RuntimeError):edge.strict.check(before)

    def test_genuine_changed_ack_still_requires_actual_named_setup_provenance(self):
        import json
        held=json.loads((self.ACK/'setup-terminal-held-facts-v2.json').read_text());after=copy.deepcopy(held['terminal'])
        after['setup_slots']['AGENTS.md']['sha256']='changed'
        edge=n.SetupArtifactEdge(held['baseline'],held['contract'],Path(held['contract']['root']),held['contract']['row_id'])
        self.assertFalse(edge.unchanged(after))
        with self.assertRaisesRegex(RuntimeError,'actual setup USER provenance'):edge.terminal(after,held['events'],held['user_history'])
        with self.assertRaisesRegex(RuntimeError,'closed/failed'):edge.terminal(after,held['events'],held['user_history'])

    def test_actual_frozen_ack_pending_facts_no_process_no_history_rewrite(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            d,recipe,bridge=self.actual(Path(tmp));original=copy.deepcopy(d)
            with mock.patch.object(n.subprocess,'run',side_effect=AssertionError('no process')),mock.patch.object(n,'validate_derivative_current',side_effect=AssertionError('offline facts only')):
                facts=n.pending_repeat_ack_facts(d,recipe,bridge)
            self.assertEqual(facts['root'],d['root']);self.assertEqual(facts['consumer_scope_sha256'],n.canonical_hash(d['terminal']['setup_scope']))
            self.assertEqual(facts['acknowledgment_sha256'],n.canonical_hash(recipe['setup_content_ack_text']))
            self.assertEqual(facts['pending_repeat_sha256'],n.canonical_hash(d['original_setup_user_text']));self.assertEqual(original,d)

    def test_roundtrip_ack_emits_completion_and_normal_two_turns_stop_before_third_input(self):
        SetupCommandReviewR2Tests().test_command_review_C1_dispatch_ack_then_repeat_without_recopy_or_install(_tuple=True,_extra=True)

    def test_pending_one_repeat_dispatch_no_ack_replay_or_second_input(self):
        SetupCommandReviewR2Tests().test_command_review_C1_dispatch_ack_then_repeat_without_recopy_or_install(_pending=True,_tuple=True,_extra=True)

    def test_real_ack_delta_still_closes_with_provenance_hold(self):
        with self.assertRaisesRegex(RuntimeError,'actual setup USER provenance'):
            SetupCommandReviewR2Tests().test_command_review_C1_dispatch_ack_then_repeat_without_recopy_or_install(_tuple=True,_changed_ack=True)

    def pending_case(self,work):
        import json
        d,actual,bridge=self.actual(work)
        review,approval,recipe,release=C0DerivativeRecoveryTests().reviews(d,work)
        for key in ('intercontext_bridge','pending_repeat_ack','setup_content_ack_text','setup_repeat_text','rows'):recipe[key]=actual[key]
        reference=recipe['intercontext_bridge'];receipt=json.loads(Path(reference['path']).read_text())
        recipe['derivative_source_bridge'].update(producer_collector_sha256=d['source_bridge']['recovery_collector_sha256'],intercontext_bridge_sha256=reference['sha256'])
        trust={'receipt':reference,'producer':receipt['producer'],'decision':'ACCEPT_RECORDED_CLASSIFIER_UNDER_EXPLICIT_ROOT_TRUST',
               'limits':{'raw_projects_origins_reconstructed':False,'independent_raw_replay':False,'raw_file_hash_equality_claim':False,'exclusive_historical_causality':False},'evidence':'Synthetic exact chain fixture only'}
        review['intercontext_bridge_review']=trust
        source=json.loads(Path(review['independent_source_review']['path']).read_text());source['verdict']='APPROVE_BOUNDED_INTERCONTEXT_BRIDGE_IMPLEMENTATION'
        n.write(review['independent_source_review']['path'],source);review['independent_source_review']['sha256']=n.sha(review['independent_source_review']['path'])
        facts=n.pending_repeat_ack_facts(d,recipe,bridge)
        ack_review={'schema':'ROOT_C1_PENDING_REPEAT_ACK_REVIEW_V1','facts':facts,'independent_source_review':review['independent_source_review'],
            'decision':'ACCEPT_EXACT_OBSERVED_ACK_NO_EDITS_NO_UNRESOLVED_JUDGMENT_FOR_ONE_PENDING_REPEAT',
            'report':{'path':str(work/'synthetic-source-review.txt'),'sha256':n.sha(work/'synthetic-source-review.txt')}}
        n.write(work/'ack-review.json',ack_review);review['pending_repeat_ack_review']={'path':str(work/'ack-review.json'),'sha256':n.sha(work/'ack-review.json')}
        root=json.loads(Path(review['root_review']['path']).read_text());root.update(independent_source_review=review['independent_source_review'],intercontext_bridge_review_sha256=n.canonical_hash(trust),pending_repeat_ack_review=review['pending_repeat_ack_review'])
        n.write(review['root_review']['path'],root);review['root_review']['sha256']=n.sha(review['root_review']['path'])
        bindings={'pending_repeat_ack_sha256':recipe['pending_repeat_ack']['sha256'],'pending_repeat_ack_review_sha256':review['pending_repeat_ack_review']['sha256']}
        release.update(bindings,max_new_model_USER_turns=1,actual_before=20,held_before=86,whole_ceiling=106,intercontext_bridge_sha256=reference['sha256'],producer_collector_sha256=d['source_bridge']['recovery_collector_sha256'],review_sha256=n.canonical_hash(review))
        approval.update(bindings,intercontext_bridge_sha256=reference['sha256'],review_sha256=n.canonical_hash(review),release_sha256=n.canonical_hash(release))
        return d,review,approval,recipe,release

    def test_pending_repeat_requires_new_concrete_review_release_and_external_USER(self):
        import json
        from unittest import mock
        for mutation in ['none','ROOT-review','source-review','USER','release','two-turns','bool-turns','stale-quota','exhausted-release','repeat-input']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);d,review,approval,recipe,release=self.pending_case(work)
                if mutation=='ROOT-review':
                    doc=json.loads(Path(review['pending_repeat_ack_review']['path']).read_text());doc['facts']['terminal_bundle_sha256']='wrong';n.write(review['pending_repeat_ack_review']['path'],doc)
                    review['pending_repeat_ack_review']['sha256']=n.sha(review['pending_repeat_ack_review']['path'])
                if mutation=='source-review':review['independent_source_review']['sha256']='wrong'
                if mutation=='USER':approval.pop('pending_repeat_ack_sha256')
                if mutation=='release':release['pending_repeat_ack_review_sha256']='wrong'
                if mutation=='two-turns':release['max_new_model_USER_turns']=2
                if mutation=='bool-turns':release['max_new_model_USER_turns']=True
                if mutation=='stale-quota':release['actual_before']=19
                if mutation=='exhausted-release':release['release_id']='ains-codex-r7-C1-source62-operatorfix-runtime-release-20261025'
                if mutation=='repeat-input':recipe['rows'][0]['initial_user_text']=recipe['setup_content_ack_text']
                with mock.patch.object(n,'validate_derivative_current') as current:
                    if mutation=='none':
                        result=n.validate_derivative_continuation(d,review,approval,Path(d['root']),recipe,d['source_bridge']['product_manifest_sha256'],release)
                        self.assertIn('pending_repeat_ack',result);current.assert_called_once()
                    else:
                        with self.assertRaises(RuntimeError):n.validate_derivative_continuation(d,review,approval,Path(d['root']),recipe,d['source_bridge']['product_manifest_sha256'],release)
                        current.assert_not_called()

    def test_rehashed_ack_native_config_closure_wire_and_artifact_mutations_hold(self):
        import json,shutil
        from unittest import mock
        for mutation in ['none','ack','native','config','closure','consumer','cache','alias','source','extra-turn']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);d,recipe,bridge=self.actual(work);clone=work/'frozen-ack';shutil.copytree(self.ACK,clone)
                def load(name):return json.loads((clone/name).read_text())
                held=load('setup-terminal-held-facts-v2.json');held['closure_receipt_path']=str(clone/'live-rpc/closed.json')
                n.write(clone/'setup-terminal-held-facts-v2.json',held)
                name=None
                if mutation=='ack':name='turn-01.json';data=load(name);data['text']='wrong'
                if mutation=='native':name='thread-start-v3.json';data=load(name);data['response']['model']='wrong'
                if mutation=='config':name='config-01.json';data=load(name);data['after']['config']['safe_identity']['sha256']='wrong'
                if mutation=='closure':name='setup-terminal-held-facts-v2.json';data=load(name);data['closed_process_returncode']=None
                if mutation=='consumer':name='operator-result.json';data=load(name);data['consumer_after']['calc.py']['sha256']='wrong'
                if mutation in ('cache','alias'):
                    name='setup-terminal-held-facts-v2.json';data=load(name)
                    if mutation=='cache':data['terminal']['setup_scope'][n.C0_GENERATED[0]]['sha256']='wrong'
                    else:data['terminal']['setup_slots']['AGENTS.md']['target_identity']=[1,2]
                if mutation=='source':name='release.json';data=load(name);data['reviewed_native_binding']['adapter_sha256']='wrong'
                if mutation=='extra-turn':
                    name='live-rpc/rpc.json';data=load(name);data.append({'direction':'request','payload':{'method':'turn/start','params':{}}})
                if name:n.write(clone/name,data)
                manifest=load('FROZEN-MANIFEST.json');manifest['files']={rel:n.sha(clone/rel) for rel in manifest['files']};n.write(clone/'FROZEN-MANIFEST.json',manifest)
                reference={'path':str(clone/'FROZEN-MANIFEST.json'),'sha256':n.sha(clone/'FROZEN-MANIFEST.json')};recipe['pending_repeat_ack']=reference
                # Test-only anchor substitution reaches inner checks. Actual
                # production code accepts only the exact immutable33 receipt.
                with mock.patch.object(n,'PENDING_ACK_RECEIPT',reference):
                    if mutation=='none':n.pending_repeat_ack_facts(d,recipe,bridge)
                    else:
                        with self.assertRaises(RuntimeError):n.pending_repeat_ack_facts(d,recipe,bridge)

    def test_wrong_ack_root_repeat_count_and_scope_are_denied(self):
        for mutation in ['ack','root','repeat','count','slot','cache','protected','native-root']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                d,recipe,bridge=self.actual(Path(tmp))
                if mutation=='ack':recipe['setup_content_ack_text']='wrong reworded acknowledgment'
                if mutation=='root':d['root']+='/foreign'
                if mutation=='repeat':recipe['setup_repeat_text']='another setup request'
                if mutation=='count':recipe['rows'][0]['max_user_turns']=2
                if mutation=='slot':d['post_slots']['AGENTS.md']['sha256']='wrong'
                if mutation=='cache':d['terminal']['setup_scope'][n.C0_GENERATED[0]]['sha256']='wrong'
                if mutation=='protected':d['terminal']['files'][next(iter(d['terminal']['files']))]['sha256']='wrong'
                if mutation=='native-root':bridge['endpoint_user_file']['sha256']='wrong'
                with self.assertRaises(RuntimeError):n.pending_repeat_ack_facts(d,recipe,bridge)

class RemainingWorkflowTests(unittest.TestCase):
    def budget_usage_fixture(self,work,entries):
        # Entries: purpose, phase, unit, actual requests, historical release max,
        # failed/timeout. Real history is never rewritten by this fixture.
        refs=[]
        def ref(path):return {'path':str(path),'sha256':n.sha(path)}
        for index,(purpose,phase,unit,count,maximum,failed) in enumerate(entries):
            folder=work/str(index);folder.mkdir()
            wire=folder/'wire.json'
            n.write(wire,[{'direction':'request','payload':{'method':'turn/start','params':{'threadId':'t'+str(index)}}} for _ in range(count)])
            closed=folder/'closed.json';n.write(closed,{'stable':True})
            thread=folder/'thread.json';n.write(thread,{'process_id':index+10,'response':{'thread':{'id':'t'+str(index)}}})
            collector='55a87d72995f90d288d306216648472ce82507b9fb811173c1deeda3888c6a73' if index%2==0 else n.sha(n.__file__)
            record={'schema':'workflow-context-v1','purpose':purpose,'phase':phase,'unit':unit,'root':str(work/'same-root'),
                'closed':True,'healthy':not failed,'timeout':failed,'server_returncode':-15 if failed else 0,
                'collector_sha256':collector,'wire':ref(wire),'prior_usage_sha256':n.canonical_hash(refs),
                'release_id':'distinct-release-'+str(index),'row_id':'distinct-row-'+str(index),'process_id':index+10,'thread_id':'t'+str(index),
                'facts':{'live-rpc/closed.json':ref(closed),'thread-start-v3.json':ref(thread)}}
            release=folder/'release.json';n.write(release,dict(record,max_new_model_USER_turns=maximum))
            record['release']=ref(release);path=folder/'context.json';n.write(path,record);refs.append(ref(path))
        return refs

    def test_r2_original_eleven_incoming_without_refill_or_metadata_authority(self):
        recipe={'purpose':'original-notification-draft','phase':'original-draft','unit':'original-notification'}
        row={'id':'fresh-row','transport':'live','mode':'default','terminal_deadline_seconds':180,'max_user_turns':1}
        for used in [6,7,8,10,11,12,13,14]:
            for count in range(1,7):
                with self.subTest(used=used,count=count):
                    candidate=dict(row,max_user_turns=count)
                    if count<=14-used:self.assertEqual(n.workflow_limits(recipe,candidate,{'original-notification/original-draft':used}),count)
                    else:
                        with self.assertRaises(RuntimeError):n.workflow_limits(recipe,candidate,{'original-notification/original-draft':used})
        for changes in [{'max_user_turns':True},{'terminal_deadline_seconds':360},{'mode':'copy'}]:
            with self.subTest(changes=changes),self.assertRaises(RuntimeError):n.workflow_limits(recipe,dict(row,**changes),{})
        with self.assertRaises(RuntimeError):n.workflow_limits(dict(recipe,unit='foreign'),row,{})
        forged=dict(recipe,allocation={'units':{'original-notification':999},'cap':999},release_id='new-unused')
        self.assertEqual(n.workflow_limits(forged,dict(row,id='new-row-12',max_user_turns=3),{'original-notification/original-draft':11}),3)
        with self.assertRaises(RuntimeError):n.workflow_limits(forged,dict(row,id='new-row-12',max_user_turns=4),{'original-notification/original-draft':11})
        with self.assertRaises(RuntimeError):n.workflow_limits(forged,dict(row,id='new-row-15'),{'original-notification/original-draft':14})

    def test_r2_all_exact_ceilings_and_closed_claude_only_incoming(self):
        expected={
            'workflow-router':{'router':1},'setup-observe':{'setup-observe':4},'setup-ack-repeat':{'setup-ack-repeat':2},
            'workflow-after-setup':{'spec':10,'tasks':6,'build':3,'AC9-handoff':5},
            'workflow-review-unavailable':{'unavailable':1},'workflow-independent-review':{'reviewer':1},
            'workflow-after-review':{'localship':5,'scope-invalidation':2},'original-notification-draft':{'original-draft':14},'spec-closure-regression':{'closure':3}}
        self.assertEqual(n.WORKFLOW_LIMITS,expected)
        self.assertEqual(n.WORKFLOW_UNIT_LIMITS,{('setup-observe','setup-observe','setup-claude-only'):1,('setup-ack-repeat','setup-ack-repeat','setup-claude-only'):2,
            ('setup-observe','setup-observe','setup-existing-import'):1,('setup-ack-repeat','setup-ack-repeat','setup-existing-import'):2,
            ('setup-observe','setup-observe','setup-samefile'):1,('setup-observe','setup-observe','setup-symlink'):2,('setup-observe','setup-observe','notification-workflow'):6})
        total=0;components={'standalone':0,'original':0,'workflow':0,'reviewer':0,'unavailable':0,'closure':0}
        for purpose,phases in expected.items():
            for phase,ceiling in phases.items():
                units={'changed-spec'} if purpose=='spec-closure-regression' else n.WORKFLOW_SETUP_UNITS|{'notification-workflow'} if purpose in ('setup-observe','setup-ack-repeat') else {'original-notification'} if purpose=='original-notification-draft' else {'notification-workflow'}
                for unit in units:
                    limit={'setup-claude-only':1,'setup-existing-import':1,'setup-samefile':1,'setup-symlink':2,'notification-workflow':6}.get(unit,ceiling) if phase=='setup-observe' else ceiling
                    recipe={'purpose':purpose,'phase':phase,'unit':unit}
                    row={'transport':'live','mode':'default' if unit=='original-notification' else 'copy','terminal_deadline_seconds':180,'max_user_turns':1 if purpose=='spec-closure-regression' else limit}
                    if purpose=='spec-closure-regression':row.update(id='codex-copy-equivalent-preanswer')
                    with self.subTest(purpose=purpose,unit=unit):
                        self.assertEqual(n.workflow_ceiling(purpose,phase,unit),limit)
                        self.assertEqual(n.workflow_limits(recipe,row,{}),row['max_user_turns'])
                        with self.assertRaises(RuntimeError):n.workflow_limits(recipe,dict(row,max_user_turns=limit+1),{})
                        with self.assertRaises(RuntimeError):n.workflow_limits(recipe,dict(row,max_user_turns=1),{unit+'/'+phase:limit})
                        if unit in ('setup-claude-only','setup-existing-import') and phase=='setup-observe':
                            with self.assertRaises(RuntimeError):n.workflow_limits(recipe,dict(row,max_user_turns=2),{})
                    total+=limit
                    component='closure' if unit=='changed-spec' else 'standalone' if unit.startswith('setup-') else 'original' if unit=='original-notification' else phase if phase in ('unavailable','reviewer') else 'workflow'
                    components[component]+=limit
        self.assertEqual(total,84) # standalone25 + original14 + workflow40 + review1+1 + closure3
        self.assertEqual(components,{'standalone':25,'original':14,'workflow':40,'reviewer':1,'unavailable':1,'closure':3})
        for recipe in [{'purpose':'foreign','phase':'setup-observe','unit':'setup-claude-only'},
                       {'purpose':'setup-observe','phase':'foreign','unit':'setup-claude-only'},
                       {'purpose':'setup-observe','phase':'setup-observe','unit':'foreign'}]:
            with self.assertRaises(RuntimeError):n.workflow_limits(recipe,{'transport':'live','mode':'copy','terminal_deadline_seconds':180,'max_user_turns':1},{})

    def test_contact_allocation_incoming_has_exact_remaining_boundaries(self):
        row={'transport':'live','mode':'copy','terminal_deadline_seconds':180,'max_user_turns':1}
        for unit,used,count,allowed in [('setup-symlink',1,1,True),('setup-symlink',1,2,False),('setup-symlink',2,1,False),
                ('notification-workflow',4,1,True),('notification-workflow',4,2,True),('notification-workflow',4,3,False),
                ('notification-workflow',5,1,True),('notification-workflow',5,2,False),('notification-workflow',6,1,False)]:
            recipe={'purpose':'setup-observe','phase':'setup-observe','unit':unit}
            with self.subTest(unit=unit,used=used,count=count):
                if allowed:self.assertEqual(n.workflow_limits(recipe,dict(row,max_user_turns=count),{unit+'/setup-observe':used}),count)
                else:
                    with self.assertRaises(RuntimeError):n.workflow_limits(recipe,dict(row,max_user_turns=count),{unit+'/setup-observe':used})
        self.assertEqual(n.WORKFLOW_LIMITS['setup-observe']['setup-observe'],4)
        self.assertEqual(n.workflow_ceiling('setup-observe','setup-observe','setup-samefile'),1) # Proposed source ceiling only; activation/allocation external
        recipe={'purpose':'setup-observe','phase':'setup-observe','unit':'notification-workflow',
                'allocation':{'cap':999,'units':{'notification-workflow':999}},'release_id':'fresh'}
        with self.assertRaises(RuntimeError):n.workflow_limits(recipe,dict(row,id='fresh-row'),{'notification-workflow/setup-observe':6})

    def test_contact_allocation_history_preserves_maxima_failures_and_both_cumulative_caps(self):
        for donor_maximum in [1,4]:
            base=[('setup-observe','setup-observe','setup-symlink',1,donor_maximum,False),
                  ('setup-ack-repeat','setup-ack-repeat','setup-symlink',2,2,False),
                  ('setup-observe','setup-observe','setup-duplicate',1,4,False),
                  ('setup-ack-repeat','setup-ack-repeat','setup-duplicate',2,2,True),
                  ('setup-observe','setup-observe','notification-workflow',4,4,False),
                  ('setup-observe','setup-observe','notification-workflow',2,2,True)]
            for extra in [[],[('setup-observe','setup-observe','setup-symlink',2,2,False)],
                          [('setup-observe','setup-observe','notification-workflow',1,1,False)]]:
                with self.subTest(donor_maximum=donor_maximum,extra=extra),tempfile.TemporaryDirectory() as tmp:
                    refs=self.budget_usage_fixture(Path(tmp),base+extra)
                    if extra:
                        with self.assertRaisesRegex(RuntimeError,'recorded phase ceiling exceeded'):n.workflow_usage(refs)
                        continue
                    records=[n.checked_json(x) for x in refs];used=n.workflow_usage(refs)
                    self.assertEqual(used,{'setup-symlink/setup-observe':1,'setup-symlink/setup-ack-repeat':2,
                        'setup-duplicate/setup-observe':1,'setup-duplicate/setup-ack-repeat':2,'notification-workflow/setup-observe':6})
                    self.assertEqual(n.checked_json(records[0]['release'])['max_new_model_USER_turns'],donor_maximum)
                    self.assertEqual(n.checked_json(records[1]['release'])['max_new_model_USER_turns'],2)
                    self.assertTrue(records[3]['timeout']);self.assertFalse(records[3]['healthy'])
                    self.assertTrue(records[5]['timeout']);self.assertFalse(records[5]['healthy'])
                    self.assertEqual(sum(used.values()),12);self.assertGreater(len({x['collector_sha256'] for x in records}),1)
                    with self.assertRaises(RuntimeError):n.workflow_limits({'purpose':'setup-observe','phase':'setup-observe','unit':'notification-workflow'},
                        {'transport':'live','mode':'copy','terminal_deadline_seconds':180,'max_user_turns':1},used)

    def test_r2_history_preserves_release_max_actuals_mixed_collectors_and_failed_dispatches(self):
        import json
        base=[('setup-observe','setup-observe','setup-claude-only',1,4,False),
              ('setup-ack-repeat','setup-ack-repeat','setup-claude-only',2,2,False),
              ('setup-observe','setup-observe','setup-duplicate',1,4,False),
              ('setup-ack-repeat','setup-ack-repeat','setup-duplicate',2,2,True),
              ('original-notification-draft','original-draft','original-notification',7,8,False),
              ('setup-observe','setup-observe','setup-existing-import',1,1,False),
              ('setup-ack-repeat','setup-ack-repeat','setup-existing-import',2,2,False)]
        for extra in [[],[('original-notification-draft','original-draft','original-notification',4,4,True)],
                      [('original-notification-draft','original-draft','original-notification',4,4,True),('original-notification-draft','original-draft','original-notification',1,1,False)],
                      [('original-notification-draft','original-draft','original-notification',4,4,True),('original-notification-draft','original-draft','original-notification',1,1,False),('original-notification-draft','original-draft','original-notification',2,2,False)],
                      [('original-notification-draft','original-draft','original-notification',4,4,True),('original-notification-draft','original-draft','original-notification',1,1,False),('original-notification-draft','original-draft','original-notification',2,2,False),('original-notification-draft','original-draft','original-notification',1,1,False)],
                      [('setup-observe','setup-observe','setup-existing-import',1,4,False)],
                      [('setup-ack-repeat','setup-ack-repeat','setup-existing-import',1,2,False)],
                      [('setup-observe','setup-observe','setup-claude-only',1,4,False)],
                      [('setup-ack-repeat','setup-ack-repeat','setup-claude-only',1,2,False)]]:
            with self.subTest(extra=extra),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);refs=self.budget_usage_fixture(work,base+extra)
                original_count=7+sum(x[3] for x in extra if x[2]=='original-notification')
                if extra and (extra[-1][2] in ('setup-claude-only','setup-existing-import') or original_count>14):
                    with self.assertRaisesRegex(RuntimeError,'recorded phase ceiling exceeded'):n.workflow_usage(refs)
                    continue
                used=n.workflow_usage(refs)
                self.assertEqual(used,{'setup-claude-only/setup-observe':1,'setup-claude-only/setup-ack-repeat':2,
                    'setup-duplicate/setup-observe':1,'setup-duplicate/setup-ack-repeat':2,'original-notification/original-draft':original_count,
                    'setup-existing-import/setup-observe':1,'setup-existing-import/setup-ack-repeat':2})
                records=[n.checked_json(x) for x in refs]
                self.assertEqual(n.checked_json(records[0]['release'])['max_new_model_USER_turns'],4)
                self.assertEqual(n.checked_json(records[1]['release'])['max_new_model_USER_turns'],2)
                self.assertEqual(n.checked_json(records[5]['release'])['max_new_model_USER_turns'],1)
                self.assertEqual(n.checked_json(records[6]['release'])['max_new_model_USER_turns'],2)
                self.assertGreater(len({x['collector_sha256'] for x in records}),1)
                # Actual unsuccessful dispatches are counted, never refunded.
                self.assertTrue(records[3]['timeout']);self.assertFalse(records[3]['healthy'])
                for unit in ['setup-claude-only','setup-existing-import']:
                    for purpose,phase in [('setup-observe','setup-observe'),('setup-ack-repeat','setup-ack-repeat')]:
                        with self.assertRaises(RuntimeError):n.workflow_limits({'purpose':purpose,'phase':phase,'unit':unit},
                            {'transport':'live','mode':'copy','terminal_deadline_seconds':180,'max_user_turns':1},used)
                if extra:
                    next_recipe={'purpose':'original-notification-draft','phase':'original-draft','unit':'original-notification'}
                    next_row={'id':'new-row','release_id':'new-release','context':'fresh','transport':'live','mode':'default','terminal_deadline_seconds':180,'max_user_turns':1}
                    if original_count==14:
                        with self.assertRaises(RuntimeError):n.workflow_limits(next_recipe,next_row,used)
                    else:self.assertEqual(n.workflow_limits(next_recipe,next_row,used),1)
        # Release-max and allowlist validation remain independent of cumulative caps.
        for entry in [('setup-observe','setup-observe','setup-claude-only',1,0,False),('setup-observe','setup-observe','foreign',1,4,False),('foreign','setup-observe','setup-claude-only',1,4,False),('setup-observe','foreign','setup-claude-only',1,4,False)]:
            with tempfile.TemporaryDirectory() as tmp:
                refs=self.budget_usage_fixture(Path(tmp),[entry])
                with self.assertRaises(RuntimeError):n.workflow_usage(refs)

    def test_cap14_existing_import_historical_maximum_compatibility_and_failed_charge(self):
        for maximum in [1,4]:
            with self.subTest(maximum=maximum),tempfile.TemporaryDirectory() as tmp:
                refs=self.budget_usage_fixture(Path(tmp),[
                    ('setup-observe','setup-observe','setup-existing-import',1,maximum,True),
                    ('setup-ack-repeat','setup-ack-repeat','setup-existing-import',2,2,False)])
                self.assertEqual(n.workflow_usage(refs),{'setup-existing-import/setup-observe':1,'setup-existing-import/setup-ack-repeat':2})
                self.assertEqual(n.checked_json(n.checked_json(refs[0])['release'])['max_new_model_USER_turns'],maximum)
                self.assertEqual(n.checked_json(n.checked_json(refs[1])['release'])['max_new_model_USER_turns'],2)

    def test_r2_anchor_and_current_release_guards_are_not_budget_metadata(self):
        import json
        for field,value in [('none',None),('actual_anchor',22),('held_anchor',84),('required',83),('whole',107),('reserve',0),('collector',None)]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);args,recipe,row,binding=self.checkpoint_case(work)
                release_path=work/'release.json';release=json.loads(release_path.read_text())
                allocation=work/'quota.json';data=json.loads(allocation.read_text());data.update(units={'original-notification':999},cap=999)
                if field not in ('none','collector'):data[field]=value
                n.write(allocation,data);release['allocation']['sha256']=n.sha(allocation)
                if field=='collector':release['collector_sha256']='historical-is-not-current-approval'
                n.write(release_path,release);binding['workflow_release_sha256']=n.sha(release_path)
                if field=='none':self.assertEqual(n.validate_workflow_checkpoint(args,recipe,row,binding)['root'],str(work/'consumer'))
                else:
                    with self.assertRaises(RuntimeError):n.validate_workflow_checkpoint(args,recipe,row,binding)

    def test_finite_phase_limits_do_not_refill_or_accept_bool_or_360(self):
        recipe={'purpose':'workflow-after-setup','phase':'spec','unit':'notification-workflow'}
        row={'transport':'live','mode':'copy','max_user_turns':6,'terminal_deadline_seconds':180}
        self.assertEqual(n.workflow_limits(recipe,row,{'notification-workflow/spec':4}),6)
        for changes in [{'max_user_turns':7},{'max_user_turns':True},{'terminal_deadline_seconds':360},{'terminal_deadline_seconds':'180'}]:
            with self.subTest(changes=changes),self.assertRaises(RuntimeError):n.workflow_limits(recipe,dict(row,**changes),{'notification-workflow/spec':4})
        for changes in [{'purpose':'plugin'},{'phase':'ship'},{'unit':'foreign'}]:
            with self.subTest(changes=changes),self.assertRaises(RuntimeError):n.workflow_limits(dict(recipe,**changes),row,{})
        with self.assertRaises(RuntimeError):n.workflow_limits(recipe,row,{'notification-workflow/spec':10})

    def test_setup_inventory_keeps_exact_pair_hardlink_but_no_third_or_protected_alias(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root';root.mkdir();(root/'AGENTS.md').write_text('grant sentinel');os.link(root/'AGENTS.md',root/'CLAUDE.md')
            before=n.workflow_inventory(root,[],True);self.assertEqual(before['AGENTS.md']['identity'],before['CLAUDE.md']['identity'])
            os.link(root/'AGENTS.md',root/'third')
            with self.assertRaises(RuntimeError):n.workflow_inventory(root,[],True)
            (root/'third').unlink()
            with self.assertRaises(RuntimeError):n.workflow_inventory(root,[root/'AGENTS.md'],True)

    def test_prospective_setup_keeps_unpredicted_program_cache_bytes_and_closes_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'AGENTS.md').write_text('grant sentinel')
            initial=n.workflow_inventory(root,[],True)
            before={'files':{},'config':{'safe':'same'},'setup_slots':n.setup_slots(root,[]),'setup_scope':n.setup_scope(root)}
            (root/'AGENTS.md').write_text('grant sentinel\nactual output');(root/'CLAUDE.md').write_text('@AGENTS.md\n')
            (root/'__pycache__').mkdir();(root/'__pycache__/test.pyc').write_bytes(b'actual cache')
            after=dict(before,setup_slots=n.setup_slots(root,[]),setup_scope=n.setup_scope(root))
            events=[{'method':'item/completed','params':{'item':{'type':'commandExecution','id':'actual','command':'unpredicted python heredoc','cwd':str(root),'status':'completed','exitCode':0,'aggregatedOutput':'actual result'}}},{'method':'turn/completed','params':{'turn':{'status':'completed'}}}]
            contract={'root':str(root),'setup_user_text':'$ains-setup actual','preserve':{'AGENTS.md':['grant sentinel'],'CLAUDE.md':[]}}
            candidate=n.workflow_setup_observation(before,after,initial,n.workflow_inventory(root,[],True),events,[{'role':'user','text':'$ains-setup actual'}],contract)
            self.assertFalse(candidate['authorizes_dispatch']);self.assertEqual(candidate['status'],'HELD_PROSPECTIVE_SETUP_REQUIRES_ROOT_REVIEW')
            self.assertEqual(candidate['events'],events);self.assertEqual(candidate['postimages']['__pycache__/test.pyc'],'61637475616c206361636865')
            changed=dict(after,config={'safe':'unknown drift'})
            with self.assertRaises(RuntimeError):n.workflow_setup_observation(before,changed,initial,n.workflow_inventory(root,[],True),events,[{'role':'user','text':'$ains-setup actual'}],contract)
            self.assertEqual(before['config'],{'safe':'same'})

    def test_usage_counts_actual_sent_requests_including_failure_not_reported_success(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);wire=work/'wire.json';n.write(wire,[{'direction':'request','payload':{'method':'turn/start','params':{'input':[{'type':'text','text':'actual'}]}}}])
            receipt={'schema':'workflow-context-v1','purpose':'workflow-after-setup','phase':'spec','unit':'notification-workflow','root':str(work),
                     'closed':True,'server_returncode':-15,'wire':{'path':str(wire),'sha256':n.sha(wire)},'prior_usage_sha256':n.canonical_hash([]),'release_id':'one'}
            release=work/'release.json';n.write(release,dict(receipt,max_new_model_USER_turns=1))
            closed=work/'closed.json';n.write(closed,{'stable':True})
            thread=work/'thread.json';n.write(thread,{'process_id':10,'response':{'thread':{'id':'thread'}}})
            receipt.update(release={'path':str(release),'sha256':n.sha(release)},process_id=10,thread_id='thread',facts={'live-rpc/closed.json':{'path':str(closed),'sha256':n.sha(closed)},'thread-start-v3.json':{'path':str(thread),'sha256':n.sha(thread)}})
            path=work/'context.json';n.write(path,receipt);refs=[{'path':str(path),'sha256':n.sha(path)}]
            self.assertEqual(n.workflow_usage(refs),{'notification-workflow/spec':1})
            with self.assertRaises(RuntimeError):n.workflow_usage(refs+refs)
            receipt['prior_usage_sha256']='wrong';n.write(path,receipt);refs[0]['sha256']=n.sha(path)
            with self.assertRaises(RuntimeError):n.workflow_usage(refs)

    def checkpoint_case(self,work):
        import argparse,json
        root=work/'consumer';root.mkdir();(root/'AGENTS.md').write_text('grant sentinel');(root/'CLAUDE.md').write_text('@AGENTS.md\n')
        source=work/'source.txt';source.write_text('grant sentinel');proof=work/'proof.txt';proof.write_text('SYNTHETIC report only; not actual approval')
        def ref(p):return {'path':str(p),'sha256':n.sha(p)}
        state=n.workflow_inventory(root,[],True)
        material=work/'material.json';n.write(material,{'schema':'workflow-file-materialization-v1','root':str(root),'state':state,'sources':[dict(ref(source),destination='AGENTS.md')]})
        cp=work/'checkpoint.json';n.write(cp,{'schema':'workflow-materialization-v1','root':str(root),'realroot':str(root.resolve()),'state':state,'materialization':ref(material)})
        manifest=work/'manifest.json';n.write(manifest,{'suite_files':{}})
        row={'id':'setup-new','transport':'live','mode':'copy','max_user_turns':4,'terminal_deadline_seconds':180,'initial_user_text':'$ains-setup actual'}
        recipe={'execution_kind':'bounded-workflow-v1','purpose':'setup-observe','phase':'setup-observe','unit':'setup-duplicate','rows':[row],
            'workflow_checkpoint':ref(cp),'usage':[],'protected_files':[],'helper_imports':[],'release_manifest':str(manifest),
            'release_manifest_sha256':n.sha(manifest),'adapter_sha256':n.sha(n.__file__),'checkpoint_installed':[]}
        n.write(work/'recipe.json',recipe)
        expected={k:None for k in n.THREAD_FIELDS};expected['instructionSources']=[]
        binding={'codex_version':'synthetic','parent_release_id':'new','scope':'configured-native-selector','proof_path':str(proof),'proof_sha256':n.sha(proof),'transports':['live'],
            'forward_thread_expectation':expected,'forward_trust_root':str(root)}
        binding['prospective_setup_contract']={'schema':'prospective-setup-contract-v1','root':str(root),'setup_user_text':row['initial_user_text'],'preserve':{'AGENTS.md':['grant sentinel'],'CLAUDE.md':['@AGENTS.md']},
            'recipe_sha256':n.sha(work/'recipe.json'),'manifest_sha256':n.sha(manifest),'proof_sha256':n.sha(proof),'release_id':'new'}
        native=work/'native.json';n.write(native,binding)
        common={'checkpoint_sha256':n.sha(cp),'recipe_sha256':n.sha(work/'recipe.json'),'collector_sha256':n.sha(n.__file__),'helpers':[],
            'manifest_sha256':n.sha(manifest),'native_premises_sha256':n.sha(native),'purpose':recipe['purpose'],'phase':recipe['phase'],'unit':recipe['unit']}
        source_review=work/'source-review.json';n.write(source_review,dict(common,schema='WORKFLOW_SOURCE_REVIEW_V1',decision='APPROVE_EXACT_BOUND_CONTEXT',report=ref(proof)))
        root_review=work/'root-review.json';n.write(root_review,dict(common,schema='WORKFLOW_ROOT_REVIEW_V1',decision='APPROVE_EXACT_BOUND_CONTEXT',report=ref(proof),source_review=ref(source_review),state_sha256=n.canonical_hash(state),usage_sha256=n.canonical_hash([]),authority_evidence=[ref(proof)]))
        quota=work/'quota.json';n.write(quota,{'actual_anchor':21,'held_anchor':85,'whole':106,'required':84,'reserve':1,'evidence':ref(proof)})
        release=work/'release.json';n.write(release,dict(common,schema='WORKFLOW_RELEASE_V1',release_id='new',root=str(root),realroot=str(root.resolve()),row_id=row['id'],out=str((work/'out').resolve()),
            max_new_contexts=1,max_new_model_USER_turns=4,seconds=180,actual_before=21,held_before=85,whole=106,initial_USER_sha256=n.canonical_hash(row['initial_user_text']),
            native_premises=ref(native),source_review=ref(source_review),root_review=ref(root_review),allocation=ref(quota)))
        binding.update(workflow_native_premises_sha256=n.sha(native),workflow_release_sha256=n.sha(release));n.write(work/'binding.json',binding)
        args=argparse.Namespace(prepared=str(work),row=row['id'],out=str(work/'out'),release_id='new',manifest=str(manifest),native_binding=str(work/'binding.json'),current_author_checkpoint=str(cp),current_author_release=str(release))
        return args,recipe,row,binding

    def cross_unit_checkpoint_case(self,work,sequence=('A','B'),mutation='none'):
        import json
        args,recipe,row,binding=self.checkpoint_case(work);root=work/'consumer';other=work/'other';other.mkdir()
        original=n.SOURCE/'tests/evals/ains-spec/new-feature-stops-at-spec-gate/files'
        for name in ('app/settings.py','app/notifier.py','app/__init__.py','tests/test_settings.py','tests/__init__.py','AGENTS.md'):
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((original/name).read_bytes())
        draft=root/'docs/changes/notification/spec.md';draft.parent.mkdir(parents=True);draft.write_text('---\nstatus: '+('approved' if mutation=='business' else 'draft')+'\n---\nSynthetic evolved draft')
        old=work/'old-draft';old.write_text('SYNTHETIC historical original draft input')
        choice=work/'defaultON';choice.write_text('SYNTHETIC historical settled choice input')
        # Only these two unrelated historical content digests are synthetic.
        # No checkpoint/usage/chronology/healthy/native/B1/review guard is mocked.
        actual_sha=n.sha
        overrides={old.resolve():'a017831f061fea8da5923558e2a5aa58ffb3b1fadfe8fdc3140e02d026bba92b',choice.resolve():'be1bb5cca54da515f3e25e6cd6eada77563883b8c2fd7a20191c2144b5b8f86c'}
        def digest(path):return overrides.get(Path(path).resolve(),actual_sha(path))
        def ref(path):return {'path':str(path),'sha256':digest(path)}
        entries=[('original-notification-draft','original-draft','original-notification',14 if mutation=='cap' else 1,14 if mutation=='cap' else 1,False) if label.startswith('A') else ('setup-observe','setup-observe','setup-symlink',1,4,False) for label in sequence]
        history=work/'history';history.mkdir();initial_refs=self.budget_usage_fixture(history,entries);refs=[];records=[]
        for index,(label,initial) in enumerate(zip(sequence,initial_refs)):
            path=Path(initial['path']);folder=path.parent;record=json.loads(path.read_text());context_root=root if label.startswith('A') else other
            record.update(root=str(context_root),realroot=str(context_root.resolve()),state=n.workflow_inventory(context_root),healthy=not (mutation=='health' and label=='A'),prior_usage_sha256=n.canonical_hash(refs))
            wire_path=Path(record['wire']['path']);events=json.loads(wire_path.read_text())
            events.append({'direction':'response_or_event','payload':{'method':'turn/completed','params':{'turn':{'status':'completed','error':None}}}})
            if mutation=='fullwire' and label=='A':events.append({'direction':'response_or_event','payload':{'method':'error','params':{'error':'late synthetic error'}}})
            n.write(wire_path,events);record['wire']=ref(wire_path)
            snapshot={k:None for k in n.THREAD_FIELDS};snapshot.update(model='gpt-6.1-sol',modelProvider='openai',cwd=str(context_root),runtimeWorkspaceRoots=[str(context_root)],instructionSources=[str(context_root/'AGENTS.md')],approvalPolicy='never',sandbox={'type':'workspaceWrite','networkAccess':False},disabledPluginIds=[],multiAgentMode='explicitRequestOnly')
            thread=Path(record['facts']['thread-start-v3.json']['path']);response=dict(snapshot,thread={'id':record['thread_id']})
            if mutation=='snapshot' and label=='A':response['model']='wrong'
            n.write(thread,{'process_id':record['process_id'],'response':response});record['facts']['thread-start-v3.json']=ref(thread)
            pair=folder/'poststart.json';n.write(pair,{'first':{'stable':True},'second':{'stable':mutation!='B1' or label!='A'},'snapshot':{'snapshot':snapshot}})
            native=folder/'native.json';n.write(native,{'status':'BOUND_ACTUAL_RECEIPTS','catalog':{'enabled_unique_targets':15 if mutation=='native' and label=='A' else 16,'load_errors':0}})
            record['facts'].update({'poststart-baseline-v3.json':ref(pair),'live-native-selection-receipt.json':ref(native)})
            if mutation=='forked' and label=='B':record['prior_usage_sha256']='not-the-prefix'
            release_path=Path(record['release']['path']);release=json.loads(release_path.read_text());release.update(root=record['root']);n.write(release_path,release);record['release']=ref(release_path)
            n.write(path,record);refs.append(ref(path));records.append(record)
        selected=next(i for i in reversed(range(len(sequence))) if sequence[i].startswith('A'))
        if mutation=='stale':selected=0
        if mutation=='wrong-unit':selected=sequence.index('B')
        cp=work/'checkpoint.json';checkpoint=copy.deepcopy(records[selected])
        if mutation=='cp':checkpoint['unexplained']=True
        if mutation=='root':checkpoint.update(root=str(other),realroot=str(other.resolve()))
        n.write(cp,checkpoint);args.current_author_checkpoint=str(cp)
        row.update(id='original-next',mode='default',max_user_turns=1,initial_user_text='$ains-spec synthetic next single judgment');args.row=row['id']
        recipe.update(purpose='original-notification-draft',phase='original-draft',unit='original-notification',workflow_checkpoint=ref(cp),usage=refs,protected_files=[])
        full_refs=list(refs)
        if mutation=='reordered':recipe['usage']=list(reversed(refs))
        if mutation=='omitted-prefix':recipe['usage']=refs[1:]
        if mutation=='omitted-tail':recipe['usage']=refs[:-1]
        if mutation=='duplicate':recipe['usage']=refs+refs[-1:]
        n.write(work/'recipe.json',recipe)
        binding.pop('prospective_setup_contract');native_path=work/'native.json';n.write(native_path,{k:v for k,v in binding.items() if k not in ('workflow_native_premises_sha256','workflow_release_sha256')});binding['workflow_native_premises_sha256']=digest(native_path)
        common={'checkpoint_sha256':digest(cp),'recipe_sha256':digest(work/'recipe.json'),'collector_sha256':digest(n.__file__),'helpers':[],
            'manifest_sha256':digest(work/'manifest.json'),'native_premises_sha256':digest(native_path),'purpose':recipe['purpose'],'phase':recipe['phase'],'unit':recipe['unit']}
        proof=ref(work/'proof.txt');source_path=work/'source-review.json';source=dict(common,schema='WORKFLOW_SOURCE_REVIEW_V1',decision='APPROVE_EXACT_BOUND_CONTEXT',report=proof)
        if mutation=='source':source['collector_sha256']='unreviewed'
        n.write(source_path,source)
        review_path=work/'root-review.json';n.write(review_path,dict(common,schema='WORKFLOW_ROOT_REVIEW_V1',decision='APPROVE_EXACT_BOUND_CONTEXT',report=proof,source_review=ref(source_path),state_sha256=n.canonical_hash(checkpoint['state']),usage_sha256=n.canonical_hash(full_refs),authority_evidence=[proof],business={'draft':ref(draft),'original_draft':ref(old),'defaultON_only':ref(choice)}))
        count=sum(x[3] for x in entries);release_path=work/'release.json'
        n.write(release_path,dict(common,schema='WORKFLOW_RELEASE_V1',release_id='new',root=str(root),realroot=str(root.resolve()),row_id=row['id'],out=str(Path(args.out).resolve()),max_new_contexts=1,
            max_new_model_USER_turns=2 if mutation=='release' else 1,seconds=180,actual_before=21+count,held_before=85-count,whole=106,initial_USER_sha256=n.canonical_hash(row['initial_user_text']),native_premises=ref(native_path),source_review=ref(source_path),root_review=ref(review_path),allocation=ref(work/'quota.json')))
        binding['workflow_release_sha256']=digest(release_path)
        if mutation=='state':(root/'foreign').write_text('unbound changed artifact')
        return args,recipe,row,binding,digest,full_refs

    def test_cross_unit_latest_related_checkpoint_accepts_full_global_chain(self):
        from unittest import mock
        for sequence in [('A',),('A','B'),('A','B','A2')]:
            with self.subTest(sequence=sequence),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);args,recipe,row,binding,digest,refs=self.cross_unit_checkpoint_case(work,sequence)
                before=copy.deepcopy(recipe['usage'])
                with mock.patch.object(n,'sha',side_effect=digest):
                    used=n.workflow_usage(refs);result=n.validate_workflow_checkpoint(args,recipe,row,binding)
                self.assertEqual(result['used'],used);self.assertEqual(recipe['usage'],before)
                self.assertEqual(sum(used.values()),len(sequence));self.assertEqual(result['checkpoint']['unit'],'original-notification')
                self.assertEqual(result['checkpoint'],n.checked_json(refs[-1 if sequence[-1].startswith('A') else 0]))
                self.assertEqual(result['release']['actual_before'],21+len(sequence))
                self.assertEqual(result['release']['held_before'],85-len(sequence))

    def test_cross_unit_checkpoint_preserves_chronology_and_all_existing_gates(self):
        from unittest import mock
        for mutation in ['stale','wrong-unit','cp','root','health','native','B1','snapshot','fullwire','state','business','source','release','reordered','forked','omitted-prefix','omitted-tail','duplicate','cap']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                sequence=('A','B','A2') if mutation=='stale' else ('A','B')
                args,recipe,row,binding,digest,refs=self.cross_unit_checkpoint_case(Path(tmp),sequence,mutation)
                with mock.patch.object(n,'sha',side_effect=digest),self.assertRaises(RuntimeError):n.validate_workflow_checkpoint(args,recipe,row,binding)

    def test_cross_unit_retained_DATA_keeps_original_record15_and_all21_charges(self):
        import json
        directory=n.SOURCE/'.omx/ultragoal/evidence/g004/codex/native-v36/preparation/original-notification-storedtype-response-source02'
        path=directory/'recipe-DATA.json'
        self.assertEqual(n.sha(path),'602d26b0a1c885b1b72a7e9ac65368203effaa04ad8d97cbe47e3ab7066ec90b')
        recipe=json.loads(path.read_text());before=copy.deepcopy(recipe['usage'])
        used=n.workflow_usage(recipe['usage']);records=[n.checked_json(x) for x in recipe['usage']]
        related=[x for x in records if x['unit']==recipe['unit']];checkpoint=n.checked_json(recipe['workflow_checkpoint'])
        self.assertEqual(len(records),21);self.assertEqual(records[14],related[-1]);self.assertEqual(related[-1],checkpoint)
        self.assertNotEqual(records[-1],checkpoint);self.assertEqual(records[-1]['unit'],'setup-symlink')
        self.assertIs(checkpoint['healthy'],True);self.assertEqual(used['original-notification/original-draft'],11)
        self.assertEqual((21+sum(used.values()),85-sum(used.values()),106),(47,59,106))
        self.assertEqual(n.workflow_limits(recipe,recipe['rows'][0],used),1);self.assertEqual(recipe['usage'],before)
        # No actual future Root/native/release records exist in this DATA cut;
        # only synthetic cases above exercise positive complete admission.
        index=json.loads((directory/'index.json').read_text())
        self.assertEqual(index['actual_new_dispatches'],0);self.assertIsNone(index['operator']);self.assertIsNone(index['lookup'])

    def test_exact_checkpoint_native_source_Root_release_and_state_bindings(self):
        import json
        for mutation in ['none','release','Root','source','native','state','quota','USER-hash','purpose','materialized-bytes']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);args,recipe,row,binding=self.checkpoint_case(work)
                if mutation=='release':binding['workflow_release_sha256']='wrong'
                if mutation in ('Root','source','quota','USER-hash'):
                    rel=json.loads((work/'release.json').read_text())
                    if mutation=='USER-hash':rel['initial_USER_sha256']='wrong'
                    elif mutation=='quota':rel['actual_before']=20
                    else:rel['root_review' if mutation=='Root' else 'source_review']['sha256']='wrong'
                    n.write(work/'release.json',rel);binding['workflow_release_sha256']=n.sha(work/'release.json')
                if mutation=='native':binding['forward_thread_expectation']['model']='wrong'
                if mutation=='state':(work/'consumer/extra.pyc').write_bytes(b'foreign')
                if mutation=='purpose':recipe['purpose']='unknown'
                if mutation=='materialized-bytes':(work/'source.txt').write_text('wrong')
                if mutation=='none':self.assertEqual(n.validate_workflow_checkpoint(args,recipe,row,binding)['root'],str(work/'consumer'))
                else:
                    with self.assertRaises(RuntimeError):n.validate_workflow_checkpoint(args,recipe,row,binding)

    def test_packet_materialization_excludes_private_producer_context_and_never_initializes_Git(self):
        import json
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);context,contract,manifest,process,root=self.export_case(work)
            with mock.patch.object(n.subprocess,'run',side_effect=process):n.make_notification_review_packet(context,work/'packet',manifest,contract)
            self.review_export_fixture(work/'packet')
            with mock.patch.object(n.subprocess,'run',side_effect=AssertionError('no Git/install')):
                receipt=n.materialize_notification_packet(work/'packet',work/'reviewer')
            self.assertFalse((work/'reviewer/.git').exists());self.assertFalse((work/'reviewer/notification-packet.json').exists())
            self.assertNotIn(str(context),(work/'reviewer/review-input.json').read_text());self.assertFalse(receipt['installed'])
            (work/'packet/author-chat.txt').write_text('must never copy')
            with self.assertRaises(RuntimeError):n.notification_packet_manifest(work/'packet')

    def test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(self, _business=False, _ack=False, _startup=None, _choice=False, _reverse=False, _timing=None, _request=None, _business_edit=None, _build=False, _native_final=None, _serialization=False, _closure=False):
        import contextlib,io,json,types
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);args,recipe,row,binding=(None,None,None,None) if (_request and _request!='legacy-ui') or _business_edit else self.choice_ack_case(work) if _choice else self.ack_case(work) if _ack else self.checkpoint_case(work);root=work/'consumer';instances=[];calls=[];sent=[];clock=[0];received=[];printed=[]
            codec=BusinessSerializationTests.serializers(str(work if _serialization else work/'fake-home'))
            native_inputs=[]
            pins=None
            if _request and _request!='legacy-ui':
                # Real finite admission, only immutable pin constants are synthetic.
                args,recipe,row,binding,material,pins,refresh=TasksTimeoutHandoffTests().fixture(work)
            if _business_edit:args,recipe,row,binding,edit_data,business,edit_refresh=(NotificationBusinessEditTests().ac9_fixture(work) if _business_edit=='git' else NotificationBusinessEditTests().fixture(work))
            if _business_edit in ('between','two','waiting','late-between','immutable-between'):row['max_user_turns']=2;edit_refresh()
            if _build:
                original_cp=n.checked_json(recipe['workflow_checkpoint']);n.write(work/'checkpoint.json',original_cp)
            real_validate=n.validate_workflow_checkpoint;real_startup=n.validate_startup
            if _startup:_business=True
            if _business and not (_request and _request!='legacy-ui') and not _business_edit:
                recipe.update(purpose='workflow-after-setup',phase='spec',unit='notification-workflow');row.update(max_user_turns=1,initial_user_text='$ains-spec actual draft')
                n.write(work/'recipe.json',recipe)
            startup_data={'config':{},'layers':[{'name':{'type':'user','file':str(work/'user')},'version':'fixed','config':{}}]}
            if _startup:
                binding['executable_identity']={'sha256':'synthetic-binary'}
                current=work/'current-lookup.json'
                if _startup=='dangling-custom':
                    startup_data['config']['project_root_markers']=['MARKER']
                    startup_data['layers'][0]['config']['project_root_markers']=['MARKER']
                n.write(current,{'schema':'startup-no-write-current-v1','collector_sha256':n.sha(n.__file__),
                    'recipe_sha256':n.sha(work/'recipe.json'),'manifest_sha256':n.sha(work/'manifest.json'),
                    'binary_sha256':'synthetic-binary','mode':'projectless' if _startup!='bad-current' else 'UNKNOWN',
                    'classification':n.startup_lookup(startup_data,root,root)})
                binding['unchanged_startup']={'path':str(current),'sha256':n.sha(current)}
                n.write(work/'binding.json',binding)
                if _startup=='dangling-git':(root/'.git').symlink_to(work/'absent')
                if _startup=='dangling-custom':(work/'MARKER').symlink_to(work/'absent')
            def validate(*a,**kw):
                if _build:return {'checkpoint':json.loads((work/'checkpoint.json').read_text()),'review':{},'root':str(root),'protected':[str((root/'draft.md').resolve())] if _closure=='canonical' else [],'setup':False,**({'spec_closure':{'draft_path':'draft.md'}} if _closure else {'build_posttimeout_handoff':True})}
                if not _business or (_request and _request!='legacy-ui') or _business_edit:return real_validate(*a,**kw)
                return {'checkpoint':json.loads((work/'checkpoint.json').read_text()),'review':{},'root':str(root),'protected':[],'setup':False}
            question={'id':'actual-question','method':'item/tool/requestUserInput','params':{'questions':[{'id':'extra','question':'Another decision?'}]}}
            answer={'request_id':'actual-question','result':{'answers':{'extra':{'answers':['Actual queued second USER']}}}}
            class RPC:
                def __init__(self,sink):
                    self.sink=Path(sink);self.sink.mkdir();self.log=[];self.events=[];self.selected_environment={};self.closed=False;self.bound_thread=None
                    self.p=types.SimpleNamespace(pid=42,poll=lambda:0 if self.closed else None);instances.append(self)
                def call(self,method,params,timeout=30):
                    calls.append(method);self.log.append({'direction':'request','payload':{'method':method,'params':params}})
                    if method=='turn/start':
                        sent.append(params['input'][0]['text'])
                        if _request in ('queued','queued-terminal','call-fail'):
                            self.events=[question]
                            if _request=='queued-terminal':self.events.append({'method':'turn/completed','params':{'turn':{'status':'completed','error':None}}})
                            self.log.extend({'direction':'response_or_event','payload':e} for e in self.events)
                            if _request=='call-fail':raise RuntimeError('synthetic call failure with queued request')
                        if _timing and 'start' in _timing:
                            clock[0]=_timing['start']
                            event={'method':'turn/started','params':{'turn':{'status':'inProgress'}}}
                            self.events.append(event);self.log.append({'direction':'response_or_event','payload':event})
                    if method=='thread/start':return {'thread':{'id':'new-thread'}}
                    if method=='turn/start' and _closure:return {'turn':{'id':'closure-turn'}}
                    return {'config':{},'layers':[]}
                def send(self,value):
                    calls.append('UI-send');self.log.append({'direction':'request','payload':value})
                def next(self,deadline):
                    calls.append('next')
                    if _request in ('event','legacy-ui') and not received:
                        received.append(question);self.log.append({'direction':'response_or_event','payload':question});return question
                    if _timing:
                        self_test.assertEqual(deadline,180)
                        clock[0]=_timing.get('first_at',_timing.get('at',179)) if not received else _timing.get('at',179)
                    if _closure=='atomic':
                        stage=root/'stage.tmp';stage.write_text('---\nstatus: draft\n---\natomic draft edit');stage.replace(root/'draft.md')
                    if _closure in ('draft','canonical','approved'):
                        (root/'draft.md').write_text('---\nstatus: '+('approved' if _closure=='approved' else 'draft')+'\n---\nactual model draft evolution')
                    if _closure=='cache':(root/'foreign.pyc').write_bytes(b'not authorized')
                    if _ack:pass
                    elif _business_edit:
                        target=root/('app/__init__.py' if _business_edit=='outside' else 'app/settings.py');target.write_text('model business implementation')
                        (root/'tests/test_notifier.py').write_text('model test first evidence fixture')
                        if _business_edit=='git':(root/'off.json').write_bytes(b'{"notification":false}\n');(root/'.git/HEAD').write_text('observed Git delta candidate fixture')
                    elif _business and not (_request and _request!='legacy-ui'):
                        p=root/'docs/changes/new/spec.md';p.parent.mkdir(parents=True,exist_ok=True);p.write_text('---\nstatus: draft\n---\nactual model draft')
                    elif not _business:(root/'AGENTS.md').write_text('grant sentinel\nmodel actual output')
                    events=[{'method':'item/completed','params':{'item':{'type':'commandExecution','id':'writer','cwd':str(root),'command':'unpredicted Python heredoc','status':'completed','exitCode':0,'aggregatedOutput':'actual'}}},
                            {'method':'turn/completed','params':{'turn':{'status':'completed','error':None}}}]
                    if _timing and _timing.get('event')=='item' and not received:events=events[:1]
                    if _build and _request!='no-final':events.insert(-1,copy.deepcopy(_native_final) if _native_final is not None else {'method':'item/completed','params':{'item':{'type':'agentMessage','phase':'final_answer','text':'Synthetic final verification report'}}})
                    if _build and _request=='native-unhealthy':events[-1]['params']['turn']['status']='failed'
                    if _closure:
                        for e in events:
                            e['params']['threadId']='new-thread'
                            if e['method']=='turn/completed':e['params']['turn']['id']='closure-turn'
                            else:e['params']['turnId']='closure-turn'
                    received.extend(events)
                    for e in events:self.log.append({'direction':'response_or_event','payload':e})
                    self.events.extend(events[:-1]);return events[-1]
                def close(self):
                    self.closed=True;codec.write(self.sink/'rpc.json',self.log);codec.write(self.sink/'closed.json',{'stable':True})
            self_test=self
            bundle_count=0
            def bundle(rpc,r,installed,*unused,**kwargs):
                nonlocal bundle_count
                bundle_count+=1
                if _closure=='unstable' and bundle_count==1:(root/'draft.md').write_text('changed inside bundle')
                if _business_edit=='unstable' and bundle_count==1:(root/'app/settings.py').write_text('changed during bundle')
                if _request=='drain' and sent:
                    rpc.log.append({'direction':'response_or_event','payload':question})
                if _timing and sent and received:
                    clock[0]=_timing.get('drain',clock[0])
                    if _timing.get('late_error'):
                        rpc.log.append({'direction':'response_or_event','payload':{'method':'error','params':{'error':{'message':'late drain error'}}}})
                if _serialization:
                    for index,payload in enumerate(BusinessSerializationTests().sample_responses(str(work))):
                        ident=1000+bundle_count*3+index;payload['id']=ident;method='skills/list' if index==1 else 'config/read'
                        rpc.log.extend([{'direction':'request','payload':{'id':ident,'method':method,'params':{}}},{'direction':'response_or_event','payload':payload}])
                if _startup:calls.append('bundle-'+str(bundle_count))
                files={str(r/name):{'exists':True,'realpath':str((r/name).resolve()),'sha256':n.sha(r/name)} for name in n.SETUP_SLOTS}
                data=copy.deepcopy(startup_data) if _startup else {'config':{},'layers':[]}
                if _startup=='post-drift' and bundle_count==2:data['config']['unknown']='changed'
                if _startup=='lookup-drift' and bundle_count==3:
                    (r/'.git').mkdir();(r/'.git/HEAD').write_text('ref: synthetic')
                observation={'files':files,'catalog_proof':{},'environment':{},'installed':installed,'config':{'stable':not (((_startup=='B1-drift' or _request=='premodel') and bundle_count==3) or ((_business_edit=='config' or (_business_edit=='immutable-between' and (work/'out/business-observation-01.json').is_file())) and sent))},'process_id':42,'thread_id':rpc.bound_thread}
                if _serialization:observation['formatter_probe']={'path':str(work/'own-evidence-path'),'api_key_schema':'NoneType'}
                return observation,data
            a=types.SimpleNamespace(probe=lambda r:{'files':{str((r/'draft.md').resolve()):{}} if _closure=='collision' else {},'all_layer_mcp_names':[]},inventory=lambda r:[],CANONICAL=n.CANONICAL_FEATURES)
            helpers={'runtime':types.SimpleNamespace(snapshot=lambda r:{},select=types.SimpleNamespace(select=lambda *args:(calls.append('UI-select') or [args[0],[],[]]))),'activation_recheck':codec,'activation_r3':a,'activation_closure_probe':types.SimpleNamespace(structural=lambda c:{})}
            approval={'role':'user','action':'approve_bounded_workflow_context','new_context':True,'checkpoint_sha256':recipe['workflow_checkpoint']['sha256'],'release_sha256':n.sha(args.current_author_release),'text':'Synthetic only; not real approval'}
            inputs=[recipe['setup_content_ack_text'],recipe['setup_repeat_text']] if _ack else [row['initial_user_text'],'Actual second released input'] if _business_edit in ('between','two','waiting','late-between','immutable-between') else [row['initial_user_text']]
            if _reverse:inputs.reverse()
            class BusinessWaitingStream(io.StringIO):
                def __next__(self):
                    if _business_edit=='waiting' and len(sent)==1:(root/'app/settings.py').write_text('EXTERNAL while waiting for actual second input')
                    return super().__next__()
            stream=BusinessWaitingStream(json.dumps(approval)+'\n'+''.join(json.dumps({'text':t})+'\n' for t in inputs)+(json.dumps(answer)+'\n' if _request else '')+json.dumps({'text':'UNREAD content acknowledgment'})+'\n')
            def process(argv,**kw):self.assertEqual(argv,['codex','--version']);return types.SimpleNamespace(stdout='synthetic',returncode=0)
            real_write=n.write
            def write_with_between_drift(path,value):
                result=real_write(path,value)
                if _business_edit=='late-between' and Path(path).name=='business-observation-01.json':
                    instances[-1].log.append({'direction':'response_or_event','payload':{'method':'error','params':{'error':'late after healthy observation'}}})
                if _business_edit=='between' and Path(path).name=='business-observation-01.json':
                    (root/'app/settings.py').write_text('EXTERNAL after observation, before second stdin read')
                return result
            def release_check(*unused):pass
            with mock.patch.object(n,'write',side_effect=write_with_between_drift),mock.patch.object(n,'validate_workflow_checkpoint',side_effect=validate),mock.patch.object(n,'released_source',side_effect=release_check),mock.patch.object(n,'bound_helpers',return_value=contextlib.nullcontext((helpers,[]))),mock.patch.object(n.subprocess,'run',side_effect=process),mock.patch.object(n.shutil,'copytree',side_effect=AssertionError('no copy')),mock.patch.object(n,'recorded_rpc',side_effect=lambda rt,ar,r,ov,s,b:RPC(s)),mock.patch.object(n,'live_bundle',side_effect=bundle),mock.patch.object(n,'validate_catalog',return_value={}),mock.patch.object(n,'native_selection_receipt',return_value={}),mock.patch.object(n,'reconcile_thread',return_value={}),mock.patch.object(n,'validate_startup',side_effect=real_startup if _startup else lambda *a,**kw:'synthetic unchanged'),mock.patch.object(n,'require_environment',return_value={}),mock.patch.object(n,'native_oracle',side_effect=lambda events,*a,**kw:native_inputs.append(copy.deepcopy(events)) or {}),mock.patch.object(n.sys,'stdin',stream),mock.patch.object(Path,'home',return_value=work/'fake-home'),mock.patch.object(n.time,'monotonic',side_effect=lambda:clock[0]) if _timing else contextlib.nullcontext(),mock.patch('builtins.print',side_effect=lambda *a,**kw:printed.append(a)),mock.patch.object(n,'TASKS_TIMEOUT_PINS',pins) if pins is not None else contextlib.nullcontext():
                if _build:
                    if _closure:
                        (root/'draft.md').write_text('---\nstatus: draft\n---\n');cp=json.loads((work/'checkpoint.json').read_text());cp['state']=n.workflow_inventory(root);n.write(work/'checkpoint.json',cp)
                    closure_success=_request=='build-healthy' and _closure not in ('cache','approved','collision','unstable')
                    if closure_success:n.run_row(args)
                    else:
                        with self.assertRaises(RuntimeError):n.run_row(args)
                    self.assertEqual(sent,[] if _closure in ('collision','unstable') else [row['initial_user_text']]);self.assertNotIn('UI-send',calls);self.assertNotIn('UI-select',calls);self.assertEqual(json.loads(stream.readline()),{'text':row['initial_user_text']} if _closure in ('collision','unstable') else answer)
                    receipt=json.loads((work/'out/workflow-context.json').read_text());self.assertTrue(receipt['closed']);self.assertEqual(receipt['healthy'],closure_success)
                    if _request in ('queued','queued-terminal','call-fail','event','drain'):self.assertTrue((work/'out/pending-01.json').is_file())
                    if _request in ('queued','queued-terminal','call-fail'):self.assertNotIn('next',calls)
                    return
                if _business_edit in ('outside','unstable','config','between','waiting','late-between','immutable-between'):
                    with self.assertRaises(RuntimeError):n.run_row(args)
                    self.assertEqual(len(sent),0 if _business_edit=='unstable' else 1);self.assertTrue(all(x.closed for x in instances))
                    path=work/'out/workflow-context.json';receipt=json.loads(path.read_text());self.assertTrue(receipt['closed']);self.assertFalse(receipt['healthy'])
                    self.assertEqual(json.loads(stream.readline()),{'text':row['initial_user_text']} if _business_edit=='unstable' else {'text':'Actual second released input'} if _business_edit in ('between','late-between','immutable-between') else {'text':'UNREAD content acknowledgment'})
                    if _business_edit=='outside':self.assertTrue((work/'out/business-held-01.json').is_file())
                    if _business_edit=='between':self.assertEqual(len(receipt['business_facts']),1)
                    return
                if _request=='premodel':
                    with self.assertRaises(RuntimeError):n.run_row(args)
                    self.assertEqual(sent,[]);self.assertTrue(all(x.closed for x in instances))
                    self.assertEqual(json.loads(stream.readline()),{'text':row['initial_user_text']})
                    path=work/'out/workflow-context.json';receipt=json.loads(path.read_text())
                    self.assertTrue(receipt['closed']);self.assertFalse(receipt['healthy']);self.assertIn('tasks_timeout_handoff',receipt)
                    usage=recipe['usage']+[{'path':str(path),'sha256':n.sha(path)}]
                    self.assertEqual(n.workflow_usage(usage)['notification-workflow/tasks'],1)
                    return
                if _request and _request not in ('legacy-ui','healthy'):
                    with self.assertRaises(RuntimeError):n.run_row(args)
                    self.assertEqual(json.loads(stream.readline()),answer)
                    self.assertNotIn('UI-send',calls);self.assertNotIn('UI-select',calls)
                    self.assertFalse(any('actual_USER_response_required' in str(v) or 'completed_user_turn' in str(v) for v in printed))
                    self.assertFalse((work/'out/user-ui-response-01.json').exists())
                    receipt=json.loads((work/'out/workflow-context.json').read_text())
                    self.assertTrue(receipt['closed']);self.assertFalse(receipt['healthy']);self.assertIn('tasks_timeout_handoff',receipt)
                    wire=json.loads((work/'out/live-rpc/rpc.json').read_text())
                    self.assertEqual(sum(e.get('direction')=='request' and e['payload'].get('method')=='turn/start' for e in wire),1)
                    self.assertIn(question,[e['payload'] for e in wire])
                    if _request!='call-fail' and _request!='drain':self.assertTrue((work/'out/pending-01.json').exists())
                    if _request in ('queued','queued-terminal','call-fail'):self.assertNotIn('next',calls)
                    self.assertTrue(all(x.closed for x in instances));self.assertEqual(sent,[row['initial_user_text']])
                    reference={'path':str(work/'out/workflow-context.json'),'sha256':n.sha(work/'out/workflow-context.json')}
                    charged=recipe['usage']+[reference]
                    self.assertEqual(n.workflow_usage(charged)['notification-workflow/tasks'],2)
                    proposed=copy.deepcopy(material);proposed['usage_sha256']=n.canonical_hash(charged);proposed['zero_request_suffix']=[reference]
                    with self.assertRaisesRegex(RuntimeError,'already dispatched'):
                        n.workflow_tasks_handoff(proposed,charged,dict(recipe,usage=charged),row)
                    return
                if _timing and (_timing.get('at',0)>=180 or _timing.get('start',0)>=180 or _timing.get('late_error')):
                    with self.assertRaises(RuntimeError if _timing.get('late_error') else TimeoutError):n.run_row(args)
                    self.assertEqual(sent,[row['initial_user_text']]);self.assertTrue(all(x.closed for x in instances))
                    self.assertEqual(json.loads(stream.readline()),{'text':inputs[1] if _ack else 'UNREAD content acknowledgment'})
                    turn=json.loads((work/'out/turn-01.json').read_text())
                    self.assertTrue(turn['events'])
                    if not _timing.get('late_error'):self.assertFalse((work/'out/config-01.json').exists())
                    receipt=json.loads((work/'out/workflow-context.json').read_text())
                    self.assertTrue(receipt['closed']);self.assertFalse(receipt['healthy'])
                    if _timing.get('start',0)>=180:self.assertEqual(received,[])
                    elif _serialization and _timing.get('late_error'):self.assertTrue(any(event.get('method')=='error' for event in turn['events']))
                    else:self.assertEqual(turn['events'][-1]['method'],'error' if _timing.get('late_error') else 'item/completed' if _timing.get('event')=='item' and 'first_at' not in _timing else 'turn/completed')
                    return
                if _reverse:
                    with self.assertRaises(RuntimeError):n.run_row(args)
                    self.assertEqual(sent,[]);self.assertTrue(all(x.closed for x in instances))
                    return
                if _startup in ('bad-current','post-drift','B1-drift','lookup-drift','dangling-git','dangling-custom'):
                    with self.assertRaises(RuntimeError):n.run_row(args)
                    self.assertEqual(calls.count('turn/start'),0)
                    self.assertEqual(calls.count('thread/start'),0 if _startup in ('bad-current','dangling-git','dangling-custom') else 1)
                    self.assertTrue(all(x.closed for x in instances))
                    self.assertEqual(json.loads(stream.readline()),{'text':inputs[0]})
                    self.assertFalse((work/'out/poststart-baseline-v3.json').exists())
                    return
                n.run_row(args)
            if _business_edit:
                self.assertEqual(sent,[row['initial_user_text'],'Actual second released input'] if _business_edit=='two' else [row['initial_user_text']]);self.assertTrue(all(x.closed for x in instances));self.assertEqual(json.loads(stream.readline()),{'text':'UNREAD content acknowledgment'})
                receipt=json.loads((work/'out/workflow-context.json').read_text());self.assertTrue(receipt['healthy']);self.assertTrue(receipt['business_facts'])
                roles=json.loads((work/'out/business-path-roles-v1.json').read_text());self.assertEqual(roles['protected_preimage_paths'],[entry['path'] for entry in recipe['protected_files']]);self.assertIn(str(root/'app/settings.py'),roles['business_paths']);self.assertNotIn(str(root/'app/settings.py'),roles['caller_immutable_paths'])
                observed=json.loads(Path(receipt['business_facts'][0]['path']).read_text());self.assertFalse(observed['business_files_equal']);self.assertIn('app/settings.py',observed['changed'])
                if _business_edit=='git':self.assertTrue(observed['git_candidate']);self.assertEqual(observed['status'],'HELD_GIT_SCOPE_REQUIRES_ROOT_REVIEW');self.assertFalse(any('completed_user_turn' in str(v) for v in printed))
                if _serialization:
                    raw=instances[-1].log;persisted=json.loads((work/'out/live-rpc/rpc.json').read_text());self.assertNotEqual(raw,persisted)
                    baseline=json.loads((work/'out/poststart-baseline-v3.json').read_text())
                    for number,reference in enumerate(receipt['business_facts'],1):
                        fact=json.loads(Path(reference['path']).read_text());frame=json.loads((work/('out/config-%02d.json'%number)).read_text())
                        self.assertEqual(fact['schema'],'workflow-notification-business-observation-v2');self.assertEqual(frame['schema_version'],'workflow-business-bundle-v2')
                        self.assertEqual(fact['events'],[entry['payload'] for entry in persisted[fact['wire_start_index']:fact['wire_end_index']] if entry['direction']=='response_or_event'])
                        self.assertEqual(frame['contract'],recipe['business_edit_contract']);self.assertEqual(frame['business_before'],fact['before']);self.assertEqual(frame['business_after'],fact['current']);self.assertEqual(frame['immutable_before'],baseline['first']);self.assertEqual(frame['immutable_after'],baseline['second'])
                    self.assertNotEqual(codec.sanitized(recipe['business_edit_contract']),recipe['business_edit_contract'])
                    self.assertTrue(any(entry.get('structural_result',{}).get('safe_identity',{}).get('schema',{}).get('features',{}).get('api_key_model_discovery')!='<REDACTED>' for capture in native_inputs for entry in capture if 'structural_result' in entry))
                    self.assertTrue(any(entry['direction']=='response_or_event' and entry['payload'].get('structural_result',{}).get('safe_identity',{}).get('schema',{}).get('features',{}).get('api_key_model_discovery')=='<REDACTED>' for entry in persisted))
                result=json.loads((work/'out/config-01.json').read_text());self.assertTrue(result['immutable_stable']);self.assertFalse(result['full_observed_files_equal']);self.assertFalse(result['baseline_reset_allowed'])
                reference={'path':str(work/'out/workflow-context.json'),'sha256':n.sha(work/'out/workflow-context.json')};usage=recipe['usage']+[reference]
                self.assertEqual(n.workflow_usage(usage)['notification-workflow/'+recipe['phase']],2 if _business_edit=='two' else 1)
                actual_fact=Path(receipt['business_facts'][0]['path']);actual_fact.write_text('{}')
                with self.assertRaises(RuntimeError):n.workflow_usage(usage)
                return
            if _request=='healthy':
                self.assertEqual(json.loads(stream.readline()),answer)
                receipt=json.loads((work/'out/workflow-context.json').read_text());self.assertTrue(receipt['closed']);self.assertTrue(receipt['healthy']);self.assertIn('tasks_timeout_handoff',receipt)
                self.assertEqual(sent,[row['initial_user_text']]);self.assertTrue(all(x.closed for x in instances));return
            if _request=='legacy-ui':self.assertIn('UI-send',calls);self.assertIn('UI-select',calls)
            if _choice:self.assertEqual(sent,[recipe['setup_content_ack_text'],recipe['setup_repeat_text']])
            if _startup:
                self.assertLess(calls.index('bundle-1'),calls.index('thread/start'))
                self.assertLess(calls.index('thread/start'),calls.index('bundle-2'))
                self.assertLess(calls.index('bundle-2'),calls.index('bundle-3'))
                self.assertLess(calls.index('bundle-3'),calls.index('turn/start'))
                diagnostic=json.loads((work/'out/startup-diagnostic-v3.json').read_text())
                self.assertEqual(diagnostic['classified_relation'],'unchanged-source-bound-no-write')
                self.assertEqual(diagnostic['no_write_lookup']['before'],diagnostic['no_write_lookup']['after'])
            self.assertEqual(calls.count('thread/start'),1);self.assertEqual(calls.count('turn/start'),len(inputs));self.assertNotIn('thread/resume',calls)
            self.assertTrue(all(x.closed for x in instances));self.assertEqual(json.loads(stream.readline()),{'text':'UNREAD content acknowledgment'})
            receipt=json.loads((work/'out/workflow-context.json').read_text());self.assertTrue(receipt['closed']);self.assertFalse(receipt['business_PASS'])
            if _ack:self.assertIsNone(receipt['setup_observation']);self.assertTrue(receipt['healthy'])
            elif _business:
                self.assertIsNone(receipt['setup_observation']);self.assertTrue((root/'docs/changes/new/spec.md').is_file());self.assertTrue((work/'out/config-01.json').is_file())
            else:
                self.assertEqual(receipt['setup_observation']['events'][-1]['method'],'turn/completed');self.assertTrue((work/'out/prospective-setup-output.json').is_file())

    def test_tasks_handoff_does_not_consume_available_matching_second_USER(self):
        for mode in ('event','queued','queued-terminal','call-fail','drain'):
            with self.subTest(mode=mode):
                self.test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_business=True,_request=mode)

    def test_tasks_handoff_real_predispatch_B1_hold_retains_zero_charge_and_unread_input(self):
        self.test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_business=True,_request='premodel')

    def test_tasks_handoff_healthy_one_input_retains_normal_terminal_and_drains(self):
        self.test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_business=True,_request='healthy')

    def test_ordinary_workflow_still_accepts_actual_structured_UI_response(self):
        self.test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_business=True,_request='legacy-ui')

    def test_workflow_absolute_deadline_rejects_buffered_late_events_and_start_response(self):
        for timing in [{'at':212.210158},{'at':180},{'at':180,'event':'item'},
                       {'at':212.210158,'event':'item'},
                       {'at':212.210158,'event':'item','first_at':51.790093},{'start':180},{'start':212.210158}]:
            with self.subTest(timing=timing):
                self.test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_business=True,_timing=timing)

    def test_setup_observation_and_ack_routes_keep_180_terminal_bound(self):
        for kwargs in [{},{'_ack':True}]:
            with self.subTest(route=kwargs):
                self.test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_timing={'at':180},**kwargs)

    def test_workflow_predeadline_terminal_allows_later_drains_but_keeps_late_error_guard(self):
        for timing in [{'at':179.999,'drain':215.653391},{'at':179,'event':'item','drain':215.653391},{'at':179,'drain':215.653391,'late_error':True}]:
            with self.subTest(timing=timing):
                self.test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_business=True,_timing=timing)

    def test_no_write_startup_dispatch_keeps_two_B1_bundles_and_predispatch_holds(self):
        for mode in ['valid','bad-current','post-drift','B1-drift','lookup-drift']:
            with self.subTest(mode=mode):
                self.test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_startup=mode)

    def test_dangling_startup_markers_hold_before_thread_or_USER_dispatch(self):
        for mode in ['dangling-git','dangling-custom']:
            with self.subTest(mode=mode):
                self.test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_startup=mode)

    def test_original_newpath_matches_old_provenance_by_bytes_then_evolves_with_lineage(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);root=work/'new-consumer';old=work/'old-provenance.md';draft=root/'docs/changes/email/spec.md';draft.parent.mkdir(parents=True)
            text='---\nstatus: draft\n---\nActual draft fixture\n';old.write_text(text);draft.write_text(text)
            source=work/'SOURCE';case=source/'tests/evals/ains-spec/new-feature-stops-at-spec-gate/files'
            for name in ('app/settings.py','app/notifier.py','app/__init__.py','tests/test_settings.py','tests/__init__.py','AGENTS.md'):
                for target in (case/name,root/name):target.parent.mkdir(parents=True,exist_ok=True);target.write_text('original fixture '+name)
            choice=work/'choice.json';choice.write_text('synthetic defaultON evidence')
            original_sha=n.sha
            def digest(path):
                if Path(path) in (old,draft):return 'a017831f061fea8da5923558e2a5aa58ffb3b1fadfe8fdc3140e02d026bba92b'
                if Path(path)==choice:return 'be1bb5cca54da515f3e25e6cd6eada77563883b8c2fd7a20191c2144b5b8f86c'
                return original_sha(path)
            business={'draft':{'path':str(draft),'sha256':digest(draft)},'original_draft':{'path':str(old),'sha256':digest(old)},'defaultON_only':{'path':str(choice),'sha256':digest(choice)}}
            self.assertNotEqual(business['draft'],business['original_draft'])
            with mock.patch.object(n,'SOURCE',source),mock.patch.object(n,'sha',side_effect=digest):
                n.workflow_business({'phase':'original-draft','usage':[]},{'business':business},root)
                draft.write_text(text+'changed before first context')
                with self.assertRaises(RuntimeError):n.workflow_business({'phase':'original-draft','usage':[]},{'business':business},root)
                context=work/'prior.json';n.write(context,{'unit':'original-notification'})
                usage=[{'path':str(context),'sha256':original_sha(context)}]
                n.workflow_business({'phase':'original-draft','usage':usage},{'business':business},root)

    def export_case(self,work,mutation='none'):
        import json,types
        root=work/'author';root.mkdir();original=n.SOURCE/'tests/evals/ains-spec/new-feature-stops-at-spec-gate/files'
        names=[str(p.relative_to(original)) for folder in ('app','tests') for p in (original/folder).rglob('*.py')]
        for name in names:
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((original/name).read_bytes())
        (root/'app/settings.py').write_text((root/'app/settings.py').read_text()+'\n# synthetic implementation\n')
        brief=root/'.agents/skills/ains-review/review-prompt.md';brief.parent.mkdir(parents=True);brief.write_text('actual installed brief fixture')
        for name in ('spec','tasks'):
            target=root/'docs/changes/notification'/(name+'.md');target.parent.mkdir(parents=True,exist_ok=True);target.write_text('---\nstatus: approved\n---\n'+name)
        data=root/'verification/off.json';data.parent.mkdir();n.write(data,{'email_notifications':False})
        proof=work/'Root-report.txt';proof.write_text('SYNTHETIC factual review fixture only, no actual approval')
        def ref(path):return {'path':str(path),'sha256':n.sha(path)}
        closed=work/'closed.json';n.write(closed,{'stable':True});thread=work/'thread.json';n.write(thread,{'process_id':5,'response':{'thread':{'id':'author'}}})
        wire=work/'wire.json';events=[]
        for text in ['actual spec approval','actual tasks approval','actual scoped Git grant']:
            events +=[{'direction':'request','payload':{'method':'turn/start','params':{'threadId':'author','input':[{'type':'text','text':text}]}}},
                      {'direction':'response_or_event','payload':{'method':'turn/completed','params':{'turn':{'status':'completed'}}}}]
        n.write(wire,events)
        recipe=work/'recipe.json';n.write(recipe,{'usage':[],'adapter_sha256':n.sha(n.__file__)})
        cp={'schema':'workflow-context-v1','purpose':'workflow-after-setup','phase':'AC9-handoff','unit':'notification-workflow','root':str(root),'closed':True,'healthy':True,'server_returncode':0,
            'release_id':'producer','collector_sha256':n.sha(n.__file__),'process_id':5,'thread_id':'author','prior_usage_sha256':n.canonical_hash([]),'state':n.workflow_inventory(root),'recipe':ref(recipe),'wire':ref(wire),
            'facts':{'live-rpc/closed.json':ref(closed),'thread-start-v3.json':ref(thread)}}
        release=work/'release.json';n.write(release,dict(cp,max_new_model_USER_turns=5));cp['release']=ref(release)
        context=work/'context.json';n.write(context,cp);producer=ref(context)
        refs=[];changed=['app/settings.py','app/notifier.py','tests/test_settings.py','tests/test_notifier.py']
        spec=ref(root/'docs/changes/notification/spec.md');tasks=ref(root/'docs/changes/notification/tasks.md')
        for i,text in enumerate(['actual spec approval','actual tasks approval','actual scoped Git grant']):
            obj={'context':producer,'wire_index':i*2,'payload_sha256':n.canonical_hash(events[i*2]['payload']),'text':text}
            if i<2:
                obj['approved_artifact']=[spec,tasks][i]
                draft=work/('draft-%d.md'%i);draft.write_text('---\nstatus: draft\n---\nactual prior draft fixture');obj['draft_artifact']=ref(draft)
            else:obj['operation_scope']={'root':str(root),'operations':['commit','revert','revert-revert'],'paths':changed}
            path=work/('USER-%d.json'%i);n.write(path,obj);refs.append(ref(path))
        approvals=work/'approvals.json';n.write(approvals,{'root':str(root),'spec':spec,'tasks':tasks,'actual_USER_receipts':refs[:1] if mutation=='missing-USER' else refs,'spec_approval':refs[0],'tasks_approval':refs[1],'Git_grant':refs[2]})
        steps=[{'kind':kind,'argv':['actual','recorded','fixture','command'],'cwd':str(root),'exit':0,'stdout':'actual synthetic output','data_sha256':n.sha(data),'actor':'authorized-fixture-actor','grant_payload_sha256':n.canonical_hash(events[4]['payload']),'evidence':ref(proof)} for kind in ('implementation-commit','revert','baseline-behavior','restore','restored-tests')]
        if mutation=='missing-step':steps.pop(2)
        if mutation=='missing-actor':steps[0].pop('actor')
        if mutation=='wrong-grant':steps[0]['grant_payload_sha256']='wrong'
        ac9={'root':str(root),'base_oid':'a'*40,'implementation_oid':'b'*40,'revert_oid':'c'*40,'restore_oid':'d'*40,'main_oid':'a'*40,'data':{'path':'verification/off.json','sha256':n.sha(data)},'steps':steps}
        ac9_review=work/'AC9-review.json';n.write(ac9_review,{'AC9_sha256':n.canonical_hash(ac9),'decision':'ACCEPT_EXACT_NOTIFICATION_AC9_COMMAND_DATA_RELATION','report':ref(proof)})
        ac9['root_review']=ref(ac9_review);ac9_path=work/'AC9.json';n.write(ac9_path,ac9)
        contract={'schema':'notification-packet-contract-v1','producer':producer,'base_oid':'a'*40,'head_oid':'d'*40,'spec':spec,'tasks':tasks,'AC9':ref(ac9_path),'approvals':ref(approvals),'check_argv':['python3','-B','-m','unittest','discover','-s','tests','-t','.']}
        review_path=work/'packet-review.json';n.write(review_path,{'data_sha256':n.canonical_hash(contract),'decision':'ACCEPT_EXACT_NOTIFICATION_PACKET_INPUTS','report':ref(proof)})
        contract['root_review']=ref(review_path);contract_path=work/'contract.json';n.write(contract_path,contract)
        manifest=work/'manifest.json';n.write(manifest,{'suite_files':{}})
        def process(argv,**kwargs):
            self.assertEqual(Path(kwargs['cwd']),root)
            if argv[0]=='python3':return types.SimpleNamespace(returncode=0,stdout='synthetic tests PASS',stderr='')
            self.assertEqual(argv[0],'git');args=argv[1:];output='';rc=0
            if args[0]=='rev-parse':
                target=args[-1];output={'a'*40+'^{commit}':'a'*40,'HEAD':('e'*40 if mutation=='stale-head' else 'd'*40),'main':'a'*40,'b'*40+'^':'a'*40,'c'*40+'^':'b'*40,'d'*40+'^':'c'*40}[target]+'\n'
            elif args[0]=='ls-files':rc=(0 if mutation=='tracked-data' else 1) if '--error-unmatch' in args else 0
            elif args[0]=='diff-tree':output='\n'.join(changed)+'\n'
            elif args[0]=='diff':output=('bad restore' if mutation=='restore-diff' else '') if 'b'*40 in args else 'diff --git a/app/settings.py b/app/settings.py\nactual diff\n'
            elif args[0]=='ls-tree':output='\n'.join(names+(['calc.py'] if mutation=='toy-base' else []))+'\n'
            elif args[0]=='show':output=(original/args[-1].split(':',1)[1]).read_text()
            elif args[0]!='status':raise AssertionError('unexpected Git command '+str(argv))
            return types.SimpleNamespace(returncode=rc,stdout=output,stderr='')
        return context,contract_path,manifest,process,root

    def review_export_fixture(self,packet):
        # Synthetic external Root adjudication only; never a real approval.
        import json
        record=json.loads((packet/'notification-packet.json').read_text())
        retained=packet.with_name(packet.name+'-export.json')
        if not retained.exists():n.write(retained,record)
        report=packet.parent/'postexport-review.txt';report.write_text('SYNTHETIC concrete output review fixture')
        receipt=packet.parent/'postexport-review.json'
        n.write(receipt,{'schema':'notification-packet-output-review-v1',
            'decision':'ACCEPT_EXACT_NOTIFICATION_PACKET_OUTPUTS',
            'candidate':{'path':str(retained),'sha256':n.sha(retained)},
            'report':{'path':str(report),'sha256':n.sha(report)}})
        record['export_review']={'path':str(receipt),'sha256':n.sha(receipt)}
        n.write(packet/'notification-packet.json',record)
        return record

    def test_packet_rejects_seven_self_rehashed_R1_substitutions(self):
        import json
        from unittest import mock
        for name in ['diff.patch','checks.json','AC9.json','approvals.json',
                     'base/app/settings.py','review-prompt.md','tests/test_unproduced.py']:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);context,contract,manifest,process,root=self.export_case(work)
                with mock.patch.object(n.subprocess,'run',side_effect=process):
                    n.make_notification_review_packet(context,work/'packet',manifest,contract)
                record=self.review_export_fixture(work/'packet')
                target=work/'packet'/name;target.write_text('# unproduced substitution fixture\n')
                record['files'][name]=n.sha(target);n.write(work/'packet/notification-packet.json',record)
                with self.assertRaises(RuntimeError):n.notification_packet_manifest(work/'packet')
                with self.assertRaises(RuntimeError):n.materialize_notification_packet(work/'packet',work/'reviewer')
                self.assertFalse((work/'reviewer').exists())
                if name=='tests/test_unproduced.py':
                    # Namespace equality remains mechanical even if a new synthetic
                    # external review explicitly binds the extra Python input.
                    retained=work/'packet-export.json'
                    n.write(retained,{k:v for k,v in record.items() if k!='export_review'})
                    self.review_export_fixture(work/'packet')
                    with self.assertRaisesRegex(RuntimeError,'target namespace'):
                        n.notification_packet_manifest(work/'packet')

    def test_packet_output_receipt_rejects_missing_or_changed_concrete_bindings(self):
        import json
        from unittest import mock
        for mutation in ['candidate-hash','report-hash','decision','schema','self-candidate','missing-report']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);context,contract,manifest,process,root=self.export_case(work)
                with mock.patch.object(n.subprocess,'run',side_effect=process):
                    n.make_notification_review_packet(context,work/'packet',manifest,contract)
                record=self.review_export_fixture(work/'packet')
                review_path=work/'postexport-review.json';review=json.loads(review_path.read_text())
                if mutation=='candidate-hash':review['candidate']['sha256']='wrong'
                if mutation=='report-hash':review['report']['sha256']='wrong'
                if mutation=='decision':review['decision']='APPROVE'
                if mutation=='schema':review['schema']='unknown'
                if mutation=='self-candidate':review['candidate']={'path':str(work/'packet/notification-packet.json'),'sha256':n.sha(work/'packet/notification-packet.json')}
                if mutation=='missing-report':Path(review['report']['path']).unlink()
                n.write(review_path,review);record['export_review']['sha256']=n.sha(review_path)
                n.write(work/'packet/notification-packet.json',record)
                with self.assertRaises((RuntimeError,FileNotFoundError)):
                    n.materialize_notification_packet(work/'packet',work/'reviewer')
                self.assertFalse((work/'reviewer').exists())

    def test_packet_requires_concrete_postexport_review_without_forward_hash_cycle(self):
        import json
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);context,contract,manifest,process,root=self.export_case(work)
            with mock.patch.object(n.subprocess,'run',side_effect=process):
                candidate=n.make_notification_review_packet(context,work/'packet',manifest,contract)
            self.assertNotIn('export_review',candidate)
            with self.assertRaises(RuntimeError):n.notification_packet_manifest(work/'packet')
            record=self.review_export_fixture(work/'packet')
            with mock.patch.object(n.subprocess,'run',side_effect=AssertionError('admission must use retained evidence only')):
                self.assertEqual(n.notification_packet_manifest(work/'packet'),record)
                n.materialize_notification_packet(work/'packet',work/'reviewer')
            retained=work/'packet-export.json'
            self.assertEqual(json.loads(retained.read_text()),candidate)
            # Even rehashing both the packet and retained candidate cannot alter
            # the separately bound concrete Root receipt.
            target=work/'packet/checks.json';target.write_text('{}')
            record['files']['checks.json']=n.sha(target)
            n.write(retained,{k:v for k,v in record.items() if k!='export_review'})
            n.write(work/'packet/notification-packet.json',record)
            with self.assertRaises(RuntimeError):n.notification_packet_manifest(work/'packet')

    def test_notification_export_uses_postclosure_actual_objects_OFF_data_and_three_USERs(self):
        import json
        from unittest import mock
        for mutation in ['none','missing-USER','missing-step','missing-actor','wrong-grant','stale-head','tracked-data','restore-diff','toy-base']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);context,contract,manifest,process,root=self.export_case(work,mutation)
                before=n.sha(root/'verification/off.json')
                with mock.patch.object(n.subprocess,'run',side_effect=process):
                    if mutation=='none':
                        record=n.make_notification_review_packet(context,work/'packet',manifest,contract)
                        self.assertEqual(record['base_oid'],'a'*40);self.assertEqual(n.sha(root/'verification/off.json'),before)
                        self.assertTrue((work/'packet/base/app/settings.py').is_file());self.assertNotIn('root_review',json.loads((work/'packet/AC9.json').read_text()))
                        self.review_export_fixture(work/'packet')
                        reviewer=n.materialize_notification_packet(work/'packet',work/'reviewer')
                        self.assertFalse(reviewer['Git_initialized']);self.assertNotIn('producer',(work/'reviewer/review-input.json').read_text())
                    else:
                        with self.assertRaises(RuntimeError):n.make_notification_review_packet(context,work/'packet',manifest,contract)

    def test_business_draft_outputs_are_detached_from_immutable_configuration_B1(self):
        self.test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_business=True)

    def test_actual_reviewer_handoff_uses_latest_fallback_and_retained_model_report(self):
        import json
        from unittest import mock
        for mutation in ['none','author-state','packet','test-items','report','destination']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);context,contract,manifest,process,root=self.export_case(work)
                with mock.patch.object(n.subprocess,'run',side_effect=process):n.make_notification_review_packet(context,work/'packet',manifest,contract)
                self.review_export_fixture(work/'packet')
                def ref(p):return {'path':str(p),'sha256':n.sha(p)}
                producer=ref(context);base=json.loads(context.read_text())
                fallback=root/'docs/ains/incomplete.md';fallback.parent.mkdir(parents=True,exist_ok=True);fallback.write_text('actual incomplete fallback fixture')
                author_recipe=work/'author-recipe.json';n.write(author_recipe,{'usage':[producer],'adapter_sha256':n.sha(n.__file__)})
                closed=base['facts']['live-rpc/closed.json'];thread=base['facts']['thread-start-v3.json']
                author_wire=work/'fallback-wire.json';n.write(author_wire,[{'direction':'request','payload':{'method':'turn/start'}},{'direction':'response_or_event','payload':{'method':'turn/completed','params':{'turn':{'status':'completed'}}}}])
                author=dict(base,purpose='workflow-review-unavailable',phase='unavailable',state=n.workflow_inventory(root),recipe=ref(author_recipe),wire=ref(author_wire),release_id='fallback',prior_usage_sha256=n.canonical_hash([producer]))
                ar=work/'fallback-release.json';n.write(ar,dict(author,max_new_model_USER_turns=1));author['release']=ref(ar);ap=work/'fallback.json';n.write(ap,author);author_ref=ref(ap)
                reviewroot=work/'reviewer';reviewroot.mkdir()
                review_recipe=work/'reviewer-recipe.json';n.write(review_recipe,{'usage':[producer,author_ref],'review_packet':ref(work/'packet/notification-packet.json')})
                item={'type':'commandExecution','command':'model chosen literal command wrapping supplied tests','status':'completed','exitCode':0,'aggregatedOutput':'actual test output'}
                report='Actual independent review findings and evidence fixture'
                events=[{'method':'item/completed','params':{'item':item}},{'method':'item/completed','params':{'item':{'type':'agentMessage','text':report}}},{'method':'turn/completed','params':{'turn':{'status':'completed'}}}]
                if mutation=='test-items':events=events[1:]
                rw=work/'review-wire.json';n.write(rw,[{'direction':'request','payload':{'method':'turn/start'}},*[{'direction':'response_or_event','payload':e} for e in events]])
                reviewer=dict(base,purpose='workflow-independent-review',phase='reviewer',root=str(reviewroot),recipe=ref(review_recipe),wire=ref(rw),release_id='reviewer',prior_usage_sha256=n.canonical_hash([producer,author_ref]))
                rr=work/'reviewer-release.json';n.write(rr,dict(reviewer,max_new_model_USER_turns=1));reviewer['release']=ref(rr);rp=work/'reviewer.json';n.write(rp,reviewer);reviewer_ref=ref(rp)
                proof=work/'Root-review.txt';proof.write_text('SYNTHETIC exact semantic program review only')
                review={'author':author_ref,'reviewer':reviewer_ref,'packet_sha256':n.sha(work/'packet/notification-packet.json'),'report_sha256':__import__('hashlib').sha256(report.encode()).hexdigest(),
                    'completed_program_items_sha256':n.canonical_hash([item] if mutation!='test-items' else []),'check_argv':['python3','-B','-m','unittest','discover','-s','tests','-t','.'],
                    'decision':'ACCEPT_ACTUAL_REVIEWER_TEST_AND_CURRENT_PACKET_RELATION','report':ref(proof)}
                if mutation=='author-state':(root/'unexpected').write_text('foreign')
                if mutation=='packet':review['packet_sha256']='wrong'
                if mutation=='report':review['report_sha256']='wrong'
                with mock.patch.object(n.subprocess,'run',side_effect=AssertionError('no Git/install in handoff')):
                    if mutation=='none':
                        receipt=n.materialize_notification_review(author_ref,reviewer_ref,work/'packet',review)
                        self.assertEqual((root/receipt['destination']).read_text(),report);self.assertTrue(fallback.is_file());self.assertEqual(receipt['before'],author['state'])
                    else:
                        with self.assertRaises(RuntimeError):n.materialize_notification_review(author_ref,reviewer_ref,work/'packet',review,'app/settings.py' if mutation=='destination' else 'docs/ains/reviews/notification-review.md')

    def ack_case(self,work):
        import json
        args,recipe,row,binding=self.checkpoint_case(work);root=work/'consumer';(root/'calc.py').write_text('pinned source fixture')
        initial=n.workflow_inventory(root,[],True);before={'files':{},'config':{'same':True},'setup_slots':n.setup_slots(root,[]),'setup_scope':n.setup_scope(root)}
        (root/'AGENTS.md').write_text('grant sentinel\nobserved setup output');(root/'__pycache__').mkdir();cache=root/'__pycache__/calc.cpython-314.pyc';cache.write_bytes(b'observed generated cache')
        after=dict(before,setup_slots=n.setup_slots(root,[]),setup_scope=n.setup_scope(root))
        events=[{'method':'item/completed','params':{'item':{'type':'commandExecution','status':'completed','exitCode':0,'cwd':str(root),'command':'actual unpredicted program','aggregatedOutput':'actual output'}}},{'method':'turn/completed','params':{'turn':{'status':'completed'}}}]
        observation=n.workflow_setup_observation(before,after,initial,n.workflow_inventory(root,[],True),events,[{'role':'user','text':'$ains-setup actual'}],binding['prospective_setup_contract'])
        def ref(p):return {'path':str(p),'sha256':n.sha(p)}
        wire=work/'prior-wire.json';n.write(wire,[{'direction':'request','payload':{'method':'turn/start','params':{'input':[{'type':'text','text':'$ains-setup actual'}]}}},*[{'direction':'response_or_event','payload':e} for e in events]])
        closed=work/'prior-closed.json';n.write(closed,{'stable':True});thread=work/'prior-thread.json';n.write(thread,{'process_id':7,'response':{'thread':{'id':'prior'}}})
        prior={'schema':'workflow-context-v1','purpose':'setup-observe','phase':'setup-observe','unit':'setup-duplicate','root':str(root),'realroot':str(root.resolve()),'state':n.workflow_inventory(root,[],True),
            'closed':True,'healthy':True,'server_returncode':0,'release_id':'prior','process_id':7,'thread_id':'prior','prior_usage_sha256':n.canonical_hash([]),'wire':ref(wire),'setup_observation':observation,
            'facts':{'live-rpc/closed.json':ref(closed),'thread-start-v3.json':ref(thread)}}
        previous_release=work/'prior-release.json';n.write(previous_release,dict(prior,max_new_model_USER_turns=4));prior['release']=ref(previous_release)
        snapshot={k:None for k in n.THREAD_FIELDS};snapshot.update(cwd=str(root),runtimeWorkspaceRoots=[str(root)])
        native=work/'prior-native.json';n.write(native,{'status':'BOUND_ACTUAL_RECEIPTS','catalog':{'enabled_unique_targets':16,'load_errors':0}})
        pair=work/'prior-B1.json';n.write(pair,{'first':{'stable':True},'second':{'stable':True},'snapshot':{'snapshot':snapshot}})
        n.write(thread,{'process_id':7,'response':dict(snapshot,thread={'id':'prior'})})
        prior['facts'].update({'thread-start-v3.json':ref(thread),'poststart-baseline-v3.json':ref(pair),'live-native-selection-receipt.json':ref(native)})
        context=work/'prior-context.json';n.write(context,prior)
        recipe.update(purpose='setup-ack-repeat',phase='setup-ack-repeat',usage=[ref(context)],workflow_checkpoint=ref(context),setup_content_ack_text='actual reviewed content acknowledgement',setup_repeat_text='$ains-setup actual')
        row.update(max_user_turns=2,initial_user_text=recipe['setup_content_ack_text']);n.write(work/'recipe.json',recipe)
        args.current_author_checkpoint=str(context);args.release_id='new-ack';binding['parent_release_id']='new-ack'
        binding['prospective_setup_contract'].update(recipe_sha256=n.sha(work/'recipe.json'),release_id='new-ack')
        native={k:v for k,v in binding.items() if k not in ('workflow_native_premises_sha256','workflow_release_sha256')};n.write(work/'native.json',native)
        common={'checkpoint_sha256':n.sha(context),'recipe_sha256':n.sha(work/'recipe.json'),'collector_sha256':n.sha(n.__file__),'helpers':[],
            'manifest_sha256':recipe['release_manifest_sha256'],'native_premises_sha256':n.sha(work/'native.json'),'purpose':recipe['purpose'],'phase':recipe['phase'],'unit':recipe['unit']}
        source=json.loads((work/'source-review.json').read_text());source.update(common);n.write(work/'source-review.json',source)
        review=json.loads((work/'root-review.json').read_text());review.update(common,source_review=ref(work/'source-review.json'),state_sha256=n.canonical_hash(prior['state']),usage_sha256=n.canonical_hash(recipe['usage']))
        review['setup']={'candidate_sha256':n.canonical_hash(observation),'program_sha256':n.canonical_hash(events),'postimages_sha256':n.canonical_hash(observation['postimages']),
            'delta_sha256':n.canonical_hash([observation['initial_state'],observation['state']]),'report':ref(work/'proof.txt'),
            'generated':[{'path':'__pycache__/calc.cpython-314.pyc','sha256':n.sha(cache),'sources':[{'path':'calc.py','sha256':n.sha(root/'calc.py')}],'command_events':[0]}]}
        n.write(work/'root-review.json',review)
        release=json.loads((work/'release.json').read_text());release.update(common,release_id='new-ack',max_new_model_USER_turns=2,actual_before=22,held_before=84,
            initial_USER_sha256=n.canonical_hash(row['initial_user_text']),native_premises=ref(work/'native.json'),source_review=ref(work/'source-review.json'),root_review=ref(work/'root-review.json'))
        n.write(work/'release.json',release);binding.update(workflow_release_sha256=n.sha(work/'release.json'),workflow_native_premises_sha256=n.sha(work/'native.json'));n.write(work/'binding.json',binding)
        return args,recipe,row,binding

    def choice_ack_case(self,work,mutation='none'):
        import json
        args,recipe,row,binding=self.ack_case(work)
        def ref(p):return {'path':str(p),'sha256':n.sha(p)}
        first_path=work/'prior-context.json';first=json.loads(first_path.read_text());first['unit']='setup-conflict'
        original=recipe['setup_repeat_text'];choice='$ains-setup Keep docs/changes/; this directory choice only.'
        wire_path=Path(first['wire']['path']);wire=json.loads(wire_path.read_text());wire[0]['payload']['params']['threadId']='prior'
        if mutation=='nonsetup':wire[0]['payload']['params']['input'][0]['text']='Keep docs/changes/ without a named setup command.'
        if mutation=='thread':wire[0]['payload']['params']['threadId']='foreign-thread'
        if mutation=='direction':
            wire[0]['direction']='response_or_event';wire.insert(1,{'direction':'request','payload':copy.deepcopy(wire[0]['payload'])})
        if mutation=='later-named':wire.insert(1,{'direction':'request','payload':{'method':'turn/start','params':{'threadId':'prior','input':[{'type':'text','text':'$ains-setup later request'}]}}})
        n.write(wire_path,wire);first['wire']=ref(wire_path)
        if mutation=='root':first['root']=str(work/'foreign-root')
        if mutation=='unit':first['unit']='setup-duplicate'
        if mutation=='router':first.update(unit='notification-workflow',purpose='workflow-router',phase='router')
        first_release=Path(first['release']['path']);r=json.loads(first_release.read_text());r.update(unit=first['unit'],root=first['root'],purpose=first['purpose'],phase=first['phase']);n.write(first_release,r);first['release']=ref(first_release)
        n.write(first_path,first);first_ref=ref(first_path)
        latest=copy.deepcopy(first);latest.update(unit='setup-conflict',root=str(work/'consumer'),purpose='setup-observe',phase='setup-observe',release_id='choice',process_id=8,thread_id='choice',prior_usage_sha256=n.canonical_hash([first_ref]))
        latest_wire=work/'choice-wire.json';choice_payload={'method':'turn/start','params':{'threadId':'choice','input':[{'type':'text','text':choice}]}}
        n.write(latest_wire,[{'direction':'request','payload':choice_payload},*wire[-2:]]);latest['wire']=ref(latest_wire)
        thread_path=work/'choice-thread.json';thread=copy.deepcopy(n.checked_json(first['facts']['thread-start-v3.json']));thread['process_id']=8;thread['response']['thread']['id']='choice';n.write(thread_path,thread);latest['facts']['thread-start-v3.json']=ref(thread_path)
        candidate=latest['setup_observation'];candidate['contract']['setup_user_text']=choice;candidate['user_history']=[{'role':'user','text':choice}]
        latest_release=work/'choice-release.json';n.write(latest_release,dict(latest,max_new_model_USER_turns=1));latest['release']=ref(latest_release)
        latest_path=work/'choice-context.json';n.write(latest_path,latest);latest_ref=ref(latest_path)
        proof_index=1 if mutation=='later-named' else 0;proof_payload=wire[proof_index]['payload']
        proof={'context':first_ref,'wire_index':proof_index,'payload_sha256':n.canonical_hash(proof_payload),'text':proof_payload['params']['input'][0]['text']}
        if mutation=='payload':proof['payload_sha256']='forged'
        if mutation=='later-choice':proof.update(context=latest_ref,wire_index=0,payload_sha256=n.canonical_hash(choice_payload),text=choice)
        if mutation=='context':proof['context']=ref(work/'prior-release.json')
        proof_path=work/'original-setup-USER.json';n.write(proof_path,proof)
        recipe.update(unit='setup-conflict',usage=[first_ref,latest_ref],workflow_checkpoint=latest_ref,original_setup_USER_provenance=ref(proof_path))
        if mutation=='missing':recipe.pop('original_setup_USER_provenance')
        if mutation=='proof-hash':recipe['original_setup_USER_provenance']['sha256']='forged'
        if mutation in ('nonsetup','later-named'):recipe['setup_repeat_text']=proof['text']
        if mutation=='repeat':recipe['setup_repeat_text']=original+' altered'
        n.write(work/'recipe.json',recipe);args.current_author_checkpoint=str(latest_path)
        binding['prospective_setup_contract']['recipe_sha256']=n.sha(work/'recipe.json')
        native_path=work/'native.json';n.write(native_path,{k:v for k,v in binding.items() if k not in ('workflow_native_premises_sha256','workflow_release_sha256')})
        common={'checkpoint_sha256':n.sha(latest_path),'recipe_sha256':n.sha(work/'recipe.json'),'collector_sha256':n.sha(n.__file__),'helpers':[],
            'manifest_sha256':recipe['release_manifest_sha256'],'native_premises_sha256':n.sha(native_path),'purpose':recipe['purpose'],'phase':recipe['phase'],'unit':recipe['unit']}
        source_path=work/'source-review.json';source=json.loads(source_path.read_text());source.update(common);n.write(source_path,source)
        review_path=work/'root-review.json';review=json.loads(review_path.read_text());review.update(common,source_review=ref(source_path),usage_sha256=n.canonical_hash(recipe['usage']))
        review['setup'].update(candidate_sha256=n.canonical_hash(candidate),program_sha256=n.canonical_hash(candidate['events']),postimages_sha256=n.canonical_hash(candidate['postimages']),delta_sha256=n.canonical_hash([candidate['initial_state'],candidate['state']]))
        n.write(review_path,review)
        count=sum(x['direction']=='request' and x['payload'].get('method')=='turn/start' for x in wire)+1
        release_path=work/'release.json';release=json.loads(release_path.read_text());release.update(common,actual_before=21+count,held_before=85-count,native_premises=ref(native_path),source_review=ref(source_path),root_review=ref(review_path));n.write(release_path,release)
        binding.update(workflow_native_premises_sha256=n.sha(native_path),workflow_release_sha256=n.sha(release_path));n.write(work/'binding.json',binding)
        return args,recipe,row,binding

    def test_original_setup_repeat_after_choice_uses_first_actual_setup_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            args,recipe,row,binding=self.choice_ack_case(Path(tmp))
            latest=n.checked_json(recipe['workflow_checkpoint'])
            self.assertNotEqual(recipe['setup_repeat_text'],latest['setup_observation']['contract']['setup_user_text'])
            result=n.validate_workflow_checkpoint(args,recipe,row,binding)
            self.assertEqual(result['checkpoint'],latest);self.assertEqual(result['used']['setup-conflict/setup-observe'],2)
            self.assertEqual(n.workflow_user_evidence(recipe['original_setup_USER_provenance'],recipe['usage'],Path(result['root']))['text'],recipe['setup_repeat_text'])

    def test_original_setup_repeat_provenance_rejects_missing_foreign_later_and_forged_evidence(self):
        for mutation in ['missing','payload','proof-hash','root','unit','router','context','later-choice','later-named','nonsetup','thread','direction','repeat']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                args,recipe,row,binding=self.choice_ack_case(Path(tmp),mutation)
                with self.assertRaises(RuntimeError):n.validate_workflow_checkpoint(args,recipe,row,binding)

    def test_original_setup_repeat_choice_dispatch_keeps_ack_first_and_no_third_input(self):
        self.test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_ack=True,_choice=True)
        self.test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_ack=True,_choice=True,_reverse=True)

    def test_retained_conflict_original_and_choice_provenance_remain_distinct(self):
        import json
        directory=n.SOURCE/'.omx/ultragoal/evidence/g004/codex/native-v42/preparation/setup-conflict-ack-repeat-sourcef1-usage52'
        recipe=json.loads((directory/'recipe.json').read_text());proof_path=directory/'original-setup-USER-provenance.json'
        latest=n.checked_json(recipe['workflow_checkpoint']);root=Path(latest['root'])
        proof=n.workflow_user_evidence({'path':str(proof_path),'sha256':n.sha(proof_path)},recipe['usage'],root)
        related=[ref for ref in recipe['usage'] if n.checked_json(ref)['unit']==recipe['unit'] and n.checked_json(ref)['purpose']=='setup-observe' and n.checked_json(ref)['phase']=='setup-observe']
        self.assertTrue(n.workflow_ref_equal(proof['context'],related[0]));self.assertEqual(proof['context']['sha256'],'58f7f1d52438d896e7f634aa8c1fa1edf921f4ddfefcd46d6a2afa2914b5f6b7')
        self.assertEqual(recipe['workflow_checkpoint']['sha256'],'cd258ff1d1e66db8d3b4a4ac673ff80de50807ad430dcb70ee90d26b15314e6d')
        self.assertEqual(proof['text'],recipe['setup_repeat_text']);self.assertNotEqual(proof['text'],latest['setup_observation']['contract']['setup_user_text'])
        context=n.checked_json(proof['context']);wire=n.checked_json(context['wire'])
        named=[i for i,x in enumerate(wire) if x['direction']=='request' and x['payload'].get('method')=='turn/start' and x['payload']['params'].get('input')==[{'type':'text','text':proof['text']}]]
        self.assertEqual(proof['wire_index'],named[0]);self.assertEqual(wire[named[0]]['payload']['params']['threadId'],context['thread_id'])
        used=n.workflow_usage(recipe['usage']);self.assertEqual((21+sum(used.values()),85-sum(used.values()),106),(52,54,106))
        self.assertEqual(used['setup-conflict/setup-observe'],2)
        # Immutable PREP still lacks this new recipe field/future authority.
        self.assertNotIn('original_setup_USER_provenance',recipe)

    def test_prospective_ack_admission_requires_concrete_program_generated_content_and_exact_pair(self):
        import json
        for mutation in ['none','generated','program','ack','repeat','foreign','Root-report','counts']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);args,recipe,row,binding=self.ack_case(work)
                if mutation in ('generated','program','Root-report'):
                    review=json.loads((work/'root-review.json').read_text())
                    if mutation=='generated':review['setup']['generated']=[]
                    if mutation=='program':review['setup']['program_sha256']='wrong'
                    if mutation=='Root-report':review['setup']['report']['sha256']='wrong'
                    n.write(work/'root-review.json',review)
                    release=json.loads((work/'release.json').read_text());release['root_review']['sha256']=n.sha(work/'root-review.json');n.write(work/'release.json',release);binding['workflow_release_sha256']=n.sha(work/'release.json')
                if mutation=='ack':row['initial_user_text']='wrong acknowledgement'
                if mutation=='repeat':recipe['setup_repeat_text']='wrong named repeat'
                if mutation=='foreign':(work/'consumer/foreign').write_text('unknown')
                if mutation=='counts':row['max_user_turns']=3
                if mutation=='none':self.assertTrue(n.validate_workflow_checkpoint(args,recipe,row,binding)['setup'])
                else:
                    with self.assertRaises(RuntimeError):n.validate_workflow_checkpoint(args,recipe,row,binding)

    def test_new_prospective_pair_dispatches_exact_ack_then_original_repeat_and_stops(self):
        self.test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_ack=True)

    def test_scope_handoff_needs_real_helper10_correct_rule_and_actual_local_pr(self):
        import json
        for mutation in ['none','exit','null-output','helper','program-base','missing-localpr']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);context,contract,manifest,process,root=self.export_case(work)
                def ref(p):return {'path':str(p),'sha256':n.sha(p)}
                helper=root/'.agents/skills/ains-review-gate/scripts/route-review.sh';helper.parent.mkdir(parents=True);helper.write_text('installed helper fixture')
                rule=root/'docs/ains/human-review-rules';rule.parent.mkdir(parents=True,exist_ok=True);rule.write_text('mandatory app/settings.py fixture rule')
                local=root/'docs/changes/notification/pr.md';local.write_text('actual local handoff fixture')
                item={'type':'commandExecution','status':'completed','exitCode':0 if mutation=='exit' else 10,'aggregatedOutput':None if mutation=='null-output' else '判定: HUMAN_REQUIRED'}
                event={'method':'item/completed','params':{'item':item}}
                wire=work/'ship-wire.json';n.write(wire,[{'direction':'response_or_event','payload':event}])
                ship_context=work/'ship-context.json';n.write(ship_context,{'phase':'localship','root':str(root),'wire':ref(wire)})
                program={'route_event_sha256':n.canonical_hash(event),'context':ref(ship_context),'rules':ref(rule),'base_oid':'a'*40,'head_oid':'d'*40,
                    'resolved_argv':[str(helper),str(rule),'a'*40,'d'*40],'decision':'ACCEPT_ACTUAL_INSTALLED_ROUTE_BASE_WORK_RULE_RELATION','report':ref(work/'Root-report.txt')}
                if mutation=='program-base':program['base_oid']='wrong'
                program_path=work/'route-program.json';n.write(program_path,program)
                receipt={'context':ref(ship_context),'route_wire_index':0,'route_payload_sha256':n.canonical_hash(event),'installed_helper_sha256':'wrong' if mutation=='helper' else n.sha(helper),'localpr':ref(local),'program_review':ref(program_path)}
                receipt_path=work/'localship.json';n.write(receipt_path,receipt)
                packet_contract=json.loads(contract.read_text())
                business={'spec':packet_contract['spec'],'tasks':packet_contract['tasks'],'spec_approval':ref(work/'USER-0.json'),'tasks_approval':ref(work/'USER-1.json'),'local_ship':ref(receipt_path)}
                if mutation=='missing-localpr':local.unlink()
                recipe={'phase':'scope-invalidation','usage':[ref(context),ref(ship_context)]}
                if mutation=='none':n.workflow_business(recipe,{'business':business},root)
                else:
                    with self.assertRaises((RuntimeError,OSError)):n.workflow_business(recipe,{'business':business},root)


class TasksTimeoutHandoffTests(unittest.TestCase):
    def fixture(self,work):
        import json
        base=RemainingWorkflowTests();args,recipe,row,binding=base.checkpoint_case(work);root=work/'consumer'
        binding.pop('prospective_setup_contract')
        def ref(p):return {'path':str(p),'sha256':n.sha(p)}
        draft=work/'spec-draft.md';draft.write_text('---\nstatus: draft\n---\nReviewed spec')
        spec=root/'docs/spec.md';spec.parent.mkdir();spec.write_text('---\nstatus: approved\n---\nReviewed spec')
        before=n.workflow_inventory(root);tasks=root/'docs/tasks.md';tasks.write_text('---\nstatus: draft\n---\nSix complete tasks, scope and stops')
        state=n.workflow_inventory(root);history=work/'history';history.mkdir()
        refs=base.budget_usage_fixture(history,[('workflow-after-setup','spec','notification-workflow',1,1,False),('workflow-after-setup','tasks','notification-workflow',1,1,True)])
        rebuilt=[]
        for j,reference in enumerate(refs):
            cp=n.checked_json(reference);cp.update(root=str(root),realroot=str(root.resolve()),server_returncode=0,state=state if j else before,
                state_error=None,close_error=None,collector_sha256='old-producer',prior_usage_sha256=n.canonical_hash(rebuilt))
            release=n.checked_json(cp['release']);release.update(root=str(root),seconds=180);n.write(cp['release']['path'],release);cp['release']=ref(Path(cp['release']['path']))
            wire=n.checked_json(cp['wire']);wire[0]['payload']['params']={'threadId':cp['thread_id'],'input':[{'type':'text','text':'Approve the spec' if j==0 else '$ains-tasks create original'}]}
            if j:
                for kind in ('commandExecution','fileChange','commandExecution'):
                    item={'id':kind+str(len(wire)),'type':kind,'status':'completed','cwd':str(root),'exitCode':0,'command':'actual retained program','aggregatedOutput':'actual result'}
                    wire.append({'direction':'response_or_event','payload':{'method':'item/completed','params':{'item':item}}})
                cp.update(healthy=False,failure='Absolute terminal deadline exceeded',config_facts={})
            n.write(cp['wire']['path'],wire);cp['wire']=ref(Path(cp['wire']['path']))
            snap={k:None for k in n.THREAD_FIELDS};snap.update(cwd=str(root),instructionSources=[],model='gpt-6.1-sol')
            thread=Path(cp['facts']['thread-start-v3.json']['path']);n.write(thread,{'process_id':cp['process_id'],'response':dict(snap,thread={'id':cp['thread_id']})});cp['facts']['thread-start-v3.json']=ref(thread)
            pair=thread.parent/'B1.json';n.write(pair,{'first':{'files':{},'environment':{},'catalog_proof':{}},'second':{'files':{},'environment':{},'catalog_proof':{}},'snapshot':{'snapshot':snap}})
            native=thread.parent/'native.json';n.write(native,{'status':'BOUND_ACTUAL_RECEIPTS','catalog':{'enabled_unique_targets':16,'load_errors':0}})
            cp['facts'].update({'poststart-baseline-v3.json':ref(pair),'live-native-selection-receipt.json':ref(native)})
            prior=thread.parent/'before.json';n.write(prior,before);cp['scope_facts']={'workflow-before-01.json':ref(prior)}
            n.write(reference['path'],cp);rebuilt.append(ref(Path(reference['path'])))
        refs=rebuilt;origin=n.checked_json(refs[-1]);wire=n.checked_json(origin['wire'])
        proof=work/'spec-USER.json';n.write(proof,{'context':refs[0],'wire_index':0,'payload_sha256':n.canonical_hash(n.checked_json(n.checked_json(refs[0])['wire'])[0]['payload']),
            'text':'Approve the spec','approved_artifact':ref(spec),'draft_artifact':ref(draft)})
        oldreview=work/'old-root-review.json';n.write(oldreview,{'business':{'spec':ref(spec),'spec_approval':ref(proof)}})
        oldrelease=n.checked_json(origin['release']);oldrelease['root_review']=ref(oldreview);n.write(origin['release']['path'],oldrelease);origin['release']=ref(Path(origin['release']['path']))
        origin_recipe=work/'old-recipe.json';n.write(origin_recipe,dict(recipe,usage=refs[:1],protected_files=[],adapter_sha256='old-producer'))
        origin['recipe']=ref(origin_recipe);n.write(refs[-1]['path'],origin);refs[-1]=ref(Path(refs[-1]['path']))
        archive=work/'old-collector.py';archive.write_text('Archived producer bytes, never executed')
        oldtest=work/'old-test.py';oldtest.write_text('Archived tests, never executed')
        origin['collector_sha256']=n.sha(archive);oldrec=n.checked_json(origin['recipe']);oldrec['adapter_sha256']=n.sha(archive);n.write(origin_recipe,oldrec);origin['recipe']=ref(origin_recipe);n.write(refs[-1]['path'],origin);refs[-1]=ref(Path(refs[-1]['path']))
        manifest=work/'frozen.json';n.write(manifest,{'files':[refs[-1]],'external_operator_logs':[]})
        audit=work/'audit.md';audit.write_text('SYNTHETIC independent complete draft review')
        audit_index=work/'audit-index.json';n.write(audit_index,{'report':ref(audit)})
        content=work/'content.json';n.write(content,{'actual_context':refs[-1],'frozen_manifest':ref(manifest),'current_state_sha256':n.canonical_hash(state),
            'tasks_draft':ref(tasks),'current_records':len(state),'actual_plan_approval_delivered':False,'runtime_authorized':False})
        user=work/'input.txt';user.write_text('Actual distinct whole-plan content and scope approval. No implementation or Git.\n')
        data=work/'approval-DATA.json';n.write(data,{'status':'NOT_SENT_NOT_ACTUAL_APPROVAL','context':refs[-1],'content_program_state_review':ref(content),'model_input_DATA':ref(user),'draft_artifact':ref(tasks)})
        material=work/'handoff.json';program=[{'wire_index':j,'payload_sha256':n.canonical_hash(wire[j]['payload']),'item_id':wire[j]['payload']['params']['item']['id']} for j in (1,2,3)]
        m={'schema':'workflow-tasks-closed-timeout-state-v1','root':str(root),'state':state,'origin':refs[-1],'manifest':ref(manifest),
            'producer':{'collector':ref(archive),'tests':ref(oldtest),'helpers':[]},'before_scope':origin['scope_facts']['workflow-before-01.json'],
            'tasks':{'path':'docs/tasks.md','sha256':n.sha(tasks)},'program':program,'content_review':ref(content),'audit':ref(audit),'audit_index':ref(audit_index),
            'approval_DATA':ref(data),'input_DATA':ref(user),'usage_sha256':n.canonical_hash(refs),'zero_request_suffix':[]}
        n.write(material,m);cp=work/'checkpoint.json';n.write(cp,{'schema':'workflow-materialization-v1','root':str(root),'realroot':str(root.resolve()),'state':state,'materialization':ref(material)})
        recipe.update(purpose='workflow-after-setup',phase='tasks',unit='notification-workflow',usage=refs,workflow_checkpoint=ref(cp))
        row.update(id='copy-notification-workflow-tasks-closed-timeout-approval',max_user_turns=1,initial_user_text=user.read_bytes().decode('utf-8'))
        recipe['rows']=[row];args.row=row['id']
        pins={k:m[k]['sha256'] for k in ('origin','manifest','content_review','audit','audit_index','approval_DATA','input_DATA')};pins.update(collector=n.sha(archive),tests=n.sha(oldtest),program_indices=(1,2,3))
        quota_ref=ref(work/'quota.json')
        def refresh(prepared=None):
            nonlocal work,material,cp
            if prepared is not None:
                previous=n.checked_json(ref(cp));work=prepared;work.mkdir();material=work/'handoff.json';cp=work/'checkpoint.json';n.write(cp,previous)
                args.prepared=str(work);args.out=str(work/'out');args.current_author_checkpoint=str(cp);args.current_author_release=str(work/'release.json')
            n.write(material,m);checkpoint=n.checked_json(ref(cp));checkpoint.update(state=m['state'],materialization=ref(material));n.write(cp,checkpoint);recipe['workflow_checkpoint']=ref(cp);n.write(work/'recipe.json',recipe)
            native=work/'native.json';n.write(native,{k:v for k,v in binding.items() if k not in ('workflow_native_premises_sha256','workflow_release_sha256')})
            common={'checkpoint_sha256':n.sha(cp),'recipe_sha256':n.sha(work/'recipe.json'),'collector_sha256':n.sha(n.__file__),'helpers':[],
                'manifest_sha256':recipe['release_manifest_sha256'],'native_premises_sha256':n.sha(native),'purpose':recipe['purpose'],'phase':recipe['phase'],'unit':recipe['unit']}
            source=work/'source-review.json';source_doc=dict(common,schema='WORKFLOW_SOURCE_REVIEW_V1',decision='APPROVE_EXACT_BOUND_CONTEXT',report=ref(audit))
            if 'live_source_protection' in m:
                section=m['live_source_protection'];index=json.loads(Path(section['review_index']['path']).read_text());report=Path(section['review_index']['path']).parent/'REPORT.md'
                source_doc.update(implementation_review=section['review_index'],report={'path':str(report),'sha256':index['files']['REPORT.md']['sha256']})
            n.write(source,source_doc)
            relation={'origin':m['origin'],'materialization':ref(material),'row_id':row['id']}
            review=work/'root-review.json';n.write(review,dict(common,schema='WORKFLOW_ROOT_REVIEW_V1',decision='APPROVE_EXACT_BOUND_CONTEXT',report=ref(audit),source_review=ref(source),
                state_sha256=n.canonical_hash(m['state']),usage_sha256=n.canonical_hash(recipe['usage']),authority_evidence=[ref(content),ref(data)],tasks_timeout_handoff=relation,business={'spec':ref(spec),'spec_approval':ref(proof)},**({'live_source_protection':m['live_source_protection']} if 'live_source_protection' in m else {})))
            release=work/'release.json';n.write(release,dict(common,schema='WORKFLOW_RELEASE_V1',release_id=args.release_id,root=str(root),realroot=str(root.resolve()),row_id=row['id'],out=str(Path(args.out).resolve()),
                max_new_contexts=1,max_new_model_USER_turns=1,seconds=180,actual_before=21+sum(n.workflow_usage(recipe['usage']).values()),held_before=85-sum(n.workflow_usage(recipe['usage']).values()),whole=106,
                initial_USER_sha256=n.canonical_hash(row['initial_user_text']),native_premises=ref(native),source_review=ref(source),root_review=ref(review),allocation=quota_ref,tasks_timeout_handoff=relation))
            binding.update(workflow_native_premises_sha256=n.sha(native),workflow_release_sha256=n.sha(release));n.write(work/'binding.json',binding)
            return relation
        refresh()
        return args,recipe,row,binding,m,pins,refresh

    def test_real_validator_admits_only_finite_failed_origin_with_approved_spec_not_tasks(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            args,recipe,row,binding,m,pins,refresh=self.fixture(Path(tmp))
            with mock.patch.object(n,'TASKS_TIMEOUT_PINS',pins,create=True):
                flow=n.validate_workflow_checkpoint(args,recipe,row,binding)
                self.assertEqual(flow['tasks_timeout_handoff'],refresh());self.assertEqual(flow['used']['notification-workflow/tasks'],1)
                recipe['workflow_checkpoint']=m['origin'];args.current_author_checkpoint=m['origin']['path']
                with self.assertRaisesRegex(RuntimeError,'latest healthy'):n.validate_workflow_checkpoint(args,recipe,row,binding)

    def test_finite_materialization_rehashed_mutations_and_current_state_deny(self):
        from unittest import mock
        mutations=['origin','manifest','producer','tasks','program','usage','suffix','healthy','missing-closure','wrong-native','unknown-B1','extra-file','alias','cache','Git','mode','spec','USER','max','deadline','unit','phase','purpose','root','Root','source','release','native','no-prior-task-approval']
        for mutation in mutations:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);args,recipe,row,binding,m,pins,refresh=self.fixture(work)
                if mutation in ('origin','manifest'):m[mutation]=dict(m[mutation],sha256='wrong')
                elif mutation=='producer':m['producer']['collector']['sha256']='wrong'
                elif mutation=='tasks':m['tasks']['sha256']='wrong'
                elif mutation=='program':m['program'][0]['payload_sha256']='wrong'
                elif mutation=='usage':m['usage_sha256']='wrong'
                elif mutation=='suffix':m['zero_request_suffix']=[m['origin']]
                elif mutation=='USER':row['initial_user_text']='not reviewed'
                elif mutation=='unit':recipe['unit']='foreign'
                elif mutation=='phase':recipe['phase']='build'
                elif mutation=='purpose':recipe['purpose']='setup-observe'
                elif mutation=='root':m['root']=str(work/'other')
                elif mutation=='max':row['max_user_turns']=True
                elif mutation=='deadline':row['terminal_deadline_seconds']=360
                elif mutation in ('healthy','missing-closure','wrong-native','unknown-B1'):
                    origin=n.checked_json(m['origin'])
                    if mutation=='healthy':origin['healthy']=True
                    elif mutation=='missing-closure':origin['facts'].pop('live-rpc/closed.json')
                    elif mutation=='wrong-native':origin['facts']['live-native-selection-receipt.json']['sha256']='wrong'
                    else:origin['facts']['poststart-baseline-v3.json']['sha256']='wrong'
                    n.write(m['origin']['path'],origin) # pins intentionally do not move with forged bytes
                elif mutation in ('extra-file','cache','Git'):(work/'consumer'/mutation).write_text('foreign')
                elif mutation=='alias':(work/'consumer/escape').symlink_to(work/'input.txt')
                elif mutation=='mode':(work/'consumer/docs/tasks.md').chmod(0o600)
                elif mutation=='spec':(work/'consumer/docs/spec.md').write_text('unapproved')
                if mutation not in ('healthy','missing-closure','wrong-native','unknown-B1'):
                    refresh()
                if mutation in ('Root','source','release','native'):
                    path=work/({'Root':'root-review.json','source':'source-review.json','release':'release.json','native':'binding.json'}[mutation]);doc=n.checked_json({'path':str(path),'sha256':n.sha(path)})
                    if mutation=='source':doc['collector_sha256']='wrong'
                    elif mutation=='native':doc['workflow_native_premises_sha256']='wrong';binding=doc
                    else:doc['tasks_timeout_handoff']={'unbound':True}
                    n.write(path,doc)
                    if mutation in ('Root','source'):
                        rel=n.checked_json({'path':str(work/'release.json'),'sha256':n.sha(work/'release.json')})
                        rel['root_review' if mutation=='Root' else 'source_review']={'path':str(path),'sha256':n.sha(path)}
                        n.write(work/'release.json',rel)
                    if mutation!='native':binding['workflow_release_sha256']=n.sha(work/'release.json')
                with mock.patch.object(n,'TASKS_TIMEOUT_PINS',pins,create=True):
                    if mutation=='no-prior-task-approval':self.assertIn('tasks_timeout_handoff',n.validate_workflow_checkpoint(args,recipe,row,binding))
                    else:
                        with self.assertRaises((RuntimeError,OSError,KeyError)):n.validate_workflow_checkpoint(args,recipe,row,binding)

    def append_attempt(self,work,args,recipe,row,m,relation,count):
        import json
        def ref(p):return {'path':str(p),'sha256':n.sha(p)}
        wire=work/'attempt-wire.json'
        sent=[{'direction':'request','payload':{'method':'turn/start','params':{'threadId':'new-thread','input':[{'type':'text','text':row['initial_user_text']}]}}},
              {'direction':'response_or_event','payload':{'id':'pending','method':'item/tool/requestUserInput','params':{'questions':[{'question':'Another decision?'}]}}}] if count else []
        n.write(wire,sent);closed=work/'attempt-closed.json';n.write(closed,{'stable':True})
        thread=work/'attempt-thread.json';n.write(thread,{'process_id':900,'response':{'thread':{'id':'new-thread'}}})
        record={'schema':'workflow-context-v1','purpose':recipe['purpose'],'phase':recipe['phase'],'unit':recipe['unit'],'closed':True,'healthy':False,
            'failure':'structured request stop' if count else 'pre-model gap','server_returncode':0,'state':m['state'],'state_error':None,'close_error':None,
            'root':m['root'],'realroot':str(Path(m['root']).resolve()),'collector_sha256':recipe['adapter_sha256'],'process_id':900,'thread_id':'new-thread',
            'prior_usage_sha256':n.canonical_hash(recipe['usage']),'release_id':args.release_id,'release':ref(Path(args.current_author_release)),
            'recipe':ref(Path(args.prepared)/'recipe.json'),'wire':ref(wire),'tasks_timeout_handoff':relation,
            'facts':{'live-rpc/closed.json':ref(closed),'thread-start-v3.json':ref(thread)}}
        context=work/'attempt.json';n.write(context,record);return ref(context)

    def test_zero_request_hold_can_correct_under_new_release_but_dispatched_failure_consumes_once(self):
        from unittest import mock
        for count in (0,1):
            with self.subTest(count=count),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);args,recipe,row,binding,m,pins,refresh=self.fixture(work)
                with mock.patch.object(n,'TASKS_TIMEOUT_PINS',pins):
                    relation=n.validate_workflow_checkpoint(args,recipe,row,binding)['tasks_timeout_handoff']
                    attempt=self.append_attempt(work,args,recipe,row,m,relation,count)
                    usage=recipe['usage']+[attempt];self.assertEqual(n.workflow_usage(usage)['notification-workflow/tasks'],1+count)
                    recipe['usage']=usage;m['usage_sha256']=n.canonical_hash(usage);m['zero_request_suffix']=[attempt]
                    refresh(work/'new-attempt')
                    if not count:
                        with self.assertRaisesRegex(RuntimeError,'release already used'):n.validate_workflow_checkpoint(args,recipe,row,binding)
                    args.release_id='corrected-new-release';refresh()
                    if count:
                        with self.assertRaisesRegex(RuntimeError,'already dispatched'):n.validate_workflow_checkpoint(args,recipe,row,binding)
                    else:
                        self.assertIn('tasks_timeout_handoff',n.validate_workflow_checkpoint(args,recipe,row,binding))
                        second=self.append_attempt(work/'new-attempt',args,recipe,row,m,refresh(),1)
                        usage=usage+[second];self.assertEqual(n.workflow_usage(usage)['notification-workflow/tasks'],2)
                        recipe['usage']=usage;m['usage_sha256']=n.canonical_hash(usage);m['zero_request_suffix']=[attempt,second]
                        args.release_id='forbidden-third-attempt';refresh(work/'third-attempt')
                        with self.assertRaisesRegex(RuntimeError,'already dispatched'):n.validate_workflow_checkpoint(args,recipe,row,binding)

    def test_history_marker_release_and_full_chain_cannot_be_omitted_or_forged(self):
        from unittest import mock
        for mutation in ('marker','release','recipe','root','reorder','omit','fork','count','missing-wire','state-zero','UI-answer','Root-semantic'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);args,recipe,row,binding,m,pins,refresh=self.fixture(work)
                with mock.patch.object(n,'TASKS_TIMEOUT_PINS',pins):
                    relation=refresh();attempt=self.append_attempt(work,args,recipe,row,m,relation,0 if mutation=='state-zero' else 1);record=n.checked_json(attempt)
                    if mutation=='marker':record.pop('tasks_timeout_handoff')
                    elif mutation=='release':record['release']['sha256']='wrong'
                    elif mutation=='recipe':record['recipe']['sha256']='wrong'
                    elif mutation=='root':record['root']='foreign'
                    elif mutation=='fork':record['prior_usage_sha256']='wrong'
                    elif mutation=='missing-wire':record['wire']['sha256']='wrong'
                    elif mutation=='state-zero':record['state']={}
                    elif mutation=='UI-answer':
                        wire=n.checked_json(record['wire']);wire.append({'direction':'request','payload':{'id':'pending','result':{'answers':{}}}});n.write(record['wire']['path'],wire);record['wire']['sha256']=n.sha(record['wire']['path'])
                    elif mutation=='Root-semantic':
                        release=n.checked_json(record['release']);review=n.checked_json(release['root_review']);review['business']={'fabricated':'approval'}
                        n.write(release['root_review']['path'],review);release['root_review']['sha256']=n.sha(release['root_review']['path']);n.write(record['release']['path'],release);record['release']['sha256']=n.sha(record['release']['path'])
                    elif mutation=='count':
                        wire=n.checked_json(record['wire']);wire.append(wire[0]);n.write(record['wire']['path'],wire);record['wire']['sha256']=n.sha(record['wire']['path'])
                    n.write(attempt['path'],record);attempt['sha256']=n.sha(attempt['path']);usage=recipe['usage']+[attempt]
                    if mutation=='reorder':usage=list(reversed(usage))
                    elif mutation=='omit':usage=usage[1:]
                    with self.assertRaises((RuntimeError,KeyError)):n.workflow_usage(usage)

    def test_frozen_v59_shape_is_supported_offline_without_consumer_access(self):
        import json
        from unittest import mock
        base=n.SOURCE/'.omx/ultragoal/evidence';folder=base/'g004/codex/native-v59/runs-notification-workflow-tasks-initial-sourcedca-usage66-RELEASE-REQUIRED'
        def ref(p):return {'path':str(p),'sha256':n.sha(p)}
        origin=ref(folder/'workflow-context.json');cp=n.checked_json(origin);old=n.checked_json(cp['recipe']);usage=old['usage']+[origin];wire=n.checked_json(cp['wire'])
        scope=base/'r7-parent-verification/tasks-closed-timeout-handoff-scope/archive'
        data=base/'r7-parent-verification/notification-workflow-unsolicited-task-plan-approval-DATA'
        content=base/'r7-parent-verification/tasks-timeout-current-state-content-review/review.json';review=n.checked_json(ref(content))
        row={'id':n.TASKS_TIMEOUT_ROW,'mode':'copy','transport':'live','max_user_turns':1,'terminal_deadline_seconds':180,'initial_user_text':(data/'model-input-DATA.txt').read_bytes().decode('utf-8')}
        recipe=dict(old,rows=[row],usage=usage,adapter_sha256=n.sha(n.__file__))
        material={'schema':'workflow-tasks-closed-timeout-state-v1','root':cp['root'],'state':cp['state'],'origin':origin,'manifest':ref(folder/'FROZEN-MANIFEST.json'),
            'before_scope':cp['scope_facts']['workflow-before-01.json'],'tasks':{'path':str(Path(review['tasks_draft']['path']).relative_to(cp['realroot'])),'sha256':review['tasks_draft']['sha256']},
            'producer':{'collector':ref(scope/'native_delta.py'),'tests':ref(scope/'native_delta_test.py'),'helpers':[ref(scope/Path(x['path']).name) for x in old['helper_imports']]},
            'content_review':ref(content),'audit':ref(base/'notification-workflow-tasks-timeout-state-disposition/REPORT.md'),'audit_index':ref(base/'notification-workflow-tasks-timeout-state-disposition/index.json'),
            'approval_DATA':ref(data/'approval-DATA.json'),'input_DATA':ref(data/'model-input-DATA.txt'),'usage_sha256':n.canonical_hash(usage),'zero_request_suffix':[],
            'program':[{'wire_index':j,'payload_sha256':n.canonical_hash(wire[j]['payload']),'item_id':wire[j]['payload']['params']['item']['id']} for j in (113,211,214)]}
        used=n.workflow_usage(usage);self.assertEqual(used['notification-workflow/tasks'],1);self.assertEqual(21+sum(used.values()),67)
        actual_resolve=Path.resolve
        def frozen_resolve(path,*a,**kw):
            if str(path)==cp['root']:return Path(cp['realroot'])
            self.assertFalse(str(path).startswith(cp['root']+'/'),'No live consumer path sampled')
            return actual_resolve(path,*a,**kw)
        with mock.patch.object(Path,'resolve',frozen_resolve):
            self.assertEqual(n.workflow_tasks_handoff(material,usage,recipe,row),origin)

class LiveSourceProtectionRebindTests(unittest.TestCase):
    def proof(self,work):
        def ref(p):return {'path':str(p),'sha256':n.sha(p)}
        folder=work/'independent';folder.mkdir();report=folder/'REPORT.md';report.write_text('SYNTHETIC independent authority fixture only, no actual source approval')
        files=[];reviewed={}
        for name in ('native_delta.py','native_delta_test.py'):
            p=n.SOURCE/'tests/runtime/codex'/name;meta=p.lstat();relative=str(p.relative_to(n.SOURCE))
            files.append({'path':str(p),'sha256':n.sha(p),'mode':oct(meta.st_mode&0o777),'realpath':str(p.resolve()),'identity':[meta.st_dev,meta.st_ino]})
            reviewed[relative]={'sha256':n.sha(p),'mode':'0o644','bytes':meta.st_size}
        index=folder/'index.json';n.write(index,{'verdict':'APPROVED_SOURCE_ONLY','mandatory_findings':[],
            'reviewed_source':reviewed,'files':{'REPORT.md':{'sha256':n.sha(report),'mode':'0o644','bytes':report.stat().st_size}}})
        return {'review_index':ref(index),'files':files}

    def fixture(self,work):
        args,recipe,row,binding,m,pins,refresh=TasksTimeoutHandoffTests().fixture(work)
        def ref(p):return {'path':str(p),'sha256':n.sha(p)}
        keep=work/'keep.txt';keep.write_text('Third protected path must remain exact')
        origin=n.checked_json(m['origin']);old=n.checked_json(origin['recipe'])
        old['protected_files']=[{'path':str(n.SOURCE/'tests/runtime/codex/native_delta.py'),'sha256':pins['collector']},
                                {'path':str(n.SOURCE/'tests/runtime/codex/native_delta_test.py'),'sha256':pins['tests']},ref(keep)]
        n.write(origin['recipe']['path'],old);origin['recipe']=ref(Path(origin['recipe']['path']));n.write(m['origin']['path'],origin)
        m['origin']=ref(Path(m['origin']['path']));recipe['usage'][-1]=m['origin'];pins['origin']=m['origin']['sha256']
        manifest=n.checked_json(m['manifest']);manifest['files']=[m['origin']];n.write(m['manifest']['path'],manifest);m['manifest']=ref(Path(m['manifest']['path']));pins['manifest']=m['manifest']['sha256']
        content=n.checked_json(m['content_review']);content.update(actual_context=m['origin'],frozen_manifest=m['manifest']);n.write(m['content_review']['path'],content);m['content_review']=ref(Path(m['content_review']['path']));pins['content_review']=m['content_review']['sha256']
        data=n.checked_json(m['approval_DATA']);data.update(context=m['origin'],content_program_state_review=m['content_review']);n.write(m['approval_DATA']['path'],data);m['approval_DATA']=ref(Path(m['approval_DATA']['path']));pins['approval_DATA']=m['approval_DATA']['sha256']
        m['usage_sha256']=n.canonical_hash(recipe['usage']);m['live_source_protection']=self.proof(work)
        recipe['protected_files']=[dict(old['protected_files'][i],sha256=m['live_source_protection']['files'][i]['sha256']) if i<2 else x.copy() for i,x in enumerate(old['protected_files'])]
        refresh();return args,recipe,row,binding,m,pins,refresh,old

    def test_real_incoming_rebind_protects_actual_source_and_test_without_mocking_comparator(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            args,recipe,row,binding,m,pins,refresh,old=self.fixture(Path(tmp))
            with mock.patch.object(n,'TASKS_TIMEOUT_PINS',pins):
                flow=n.validate_workflow_checkpoint(args,recipe,row,binding)
                self.assertIn('tasks_timeout_handoff',flow)
                self.assertEqual(len(recipe['protected_files']),len(old['protected_files']))
                self.assertEqual([r['path'] for r in recipe['protected_files']],[r['path'] for r in old['protected_files']])
                self.assertEqual(recipe['protected_files'][2:],old['protected_files'][2:])
                for ref in recipe['protected_files']:self.assertEqual(n.sha(ref['path']),ref['sha256'])
                self.assertNotEqual(recipe['adapter_sha256'],pins['collector'])

    def test_frozen_v60_exact179_reproduction_and_corrected_relation(self):
        from unittest import mock
        base=n.SOURCE/'.omx/ultragoal/evidence';v60=base/'g004/codex/native-v60/preparation/notification-workflow-tasks-timeout-approval-source63-usage67'
        recipe=n.checked_json({'path':str(v60/'recipe.json'),'sha256':n.sha(v60/'recipe.json')});cp=n.checked_json(recipe['workflow_checkpoint']);m=n.checked_json(cp['materialization']);origin=n.checked_json(m['origin']);old=n.checked_json(origin['recipe'])
        self.assertEqual(recipe['protected_files'],old['protected_files']);self.assertEqual(len(old['protected_files']),179)
        # Recorded full179 snapshot: no live consumer or host configuration is read.
        inventory=n.checked_json({'path':str(v60/'protected-inventory-DATA.json'),'sha256':n.sha(v60/'protected-inventory-DATA.json')})
        self.assertEqual(sum(x['expected']['sha256']!=x['actual']['sha256'] for x in inventory['entries']),2)
        paths=[str(n.SOURCE/'tests/runtime/codex'/name) for name in ('native_delta.py','native_delta_test.py')]
        self.assertTrue(all(n.sha(p)!=next(x['sha256'] for x in old['protected_files'] if x['path']==p) for p in paths))
        rebound=[dict(x,sha256=n.sha(x['path'])) if x['path'] in paths else x.copy() for x in old['protected_files']]
        actual_resolve=Path.resolve
        def frozen_root_resolve(path,*a,**kw):
            if str(path)==origin['root']:return Path(origin['realroot'])
            self.assertFalse(str(path).startswith(origin['root']+'/'),'No live consumer read')
            return actual_resolve(path,*a,**kw)
        with mock.patch.object(Path,'resolve',frozen_root_resolve),self.assertRaisesRegex(RuntimeError,'protection identity'):
            n.workflow_tasks_handoff(m,recipe['usage'],dict(recipe,protected_files=rebound),recipe['rows'][0])
        with self.assertRaises(RuntimeError):n.workflow_live_source_protection(m,old,dict(recipe,protected_files=rebound))
        with tempfile.TemporaryDirectory() as tmp:
            m=dict(m,live_source_protection=self.proof(Path(tmp)))
            # Only review authority is synthetic. Full ordered179 relation is real.
            n.workflow_live_source_protection(m,old,dict(recipe,protected_files=rebound,adapter_sha256=n.sha(n.__file__)))
            self.assertEqual([i for i,(a,b) in enumerate(zip(rebound,old['protected_files'])) if a!=b],[old['protected_files'].index(next(x for x in old['protected_files'] if x['path']==p)) for p in paths])

    def test_rehashed_pair_certificate_index_and_scope_mutations_deny(self):
        from unittest import mock
        mutations=('one','third','reorder','drop','duplicate','pair-path','pair-hash','mode','inode','realpath','report','index-sha','verdict','findings','reviewed-test','namespace','unreviewed','source-cert','Root-cert','collector','live-bytes')
        for mutation in mutations:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);args,recipe,row,binding,m,pins,refresh,old=self.fixture(work);section=m['live_source_protection']
                if mutation=='one':recipe['protected_files'][1]=old['protected_files'][1]
                elif mutation=='third':recipe['protected_files'][2]['sha256']='0'*64
                elif mutation=='reorder':recipe['protected_files'].reverse()
                elif mutation=='drop':recipe['protected_files'].pop()
                elif mutation=='duplicate':recipe['protected_files'].append(recipe['protected_files'][0])
                elif mutation=='pair-path':section['files'][0]['path']=str(work/'alias.py')
                elif mutation=='pair-hash':section['files'][1]['sha256']='0'*64
                elif mutation=='mode':section['files'][0]['mode']='0o600'
                elif mutation=='inode':section['files'][0]['identity'][1]+=1
                elif mutation=='realpath':section['files'][0]['realpath']=str(work/'other.py')
                elif mutation=='report':(work/'independent/REPORT.md').write_text('unreviewed substitution')
                elif mutation=='index-sha':section['review_index']['sha256']='wrong'
                elif mutation=='unreviewed':section['review_index']['sha256']='0'*64
                elif mutation in ('verdict','findings','reviewed-test','namespace'):
                    index=n.checked_json(section['review_index'])
                    if mutation=='verdict':index['verdict']='APPROVE'
                    elif mutation=='findings':index['mandatory_findings']=['unresolved']
                    elif mutation=='namespace':index['reviewed_source']['third.py']={'sha256':'0'*64,'mode':'0o644','bytes':10}
                    else:index['reviewed_source']['tests/runtime/codex/native_delta_test.py']['sha256']='0'*64
                    n.write(section['review_index']['path'],index);section['review_index']['sha256']=n.sha(section['review_index']['path'])
                elif mutation=='collector':recipe['adapter_sha256']='0'*64
                refresh()
                if mutation in ('source-cert','Root-cert'):
                    path=work/('source-review.json' if mutation=='source-cert' else 'root-review.json');doc=n.checked_json({'path':str(path),'sha256':n.sha(path)})
                    doc.pop('implementation_review' if mutation=='source-cert' else 'live_source_protection');n.write(path,doc)
                    release=n.checked_json({'path':str(work/'release.json'),'sha256':n.sha(work/'release.json')});release['source_review' if mutation=='source-cert' else 'root_review']['sha256']=n.sha(path);n.write(work/'release.json',release);binding['workflow_release_sha256']=n.sha(work/'release.json')
                actual_sha=n.sha
                def changed_sha(path):return '0'*64 if mutation=='live-bytes' and str(path)==section['files'][1]['path'] else actual_sha(path)
                with mock.patch.object(n,'TASKS_TIMEOUT_PINS',pins),mock.patch.object(n,'sha',side_effect=changed_sha):
                    with self.assertRaises((RuntimeError,OSError,KeyError)):n.validate_workflow_checkpoint(args,recipe,row,binding)

    def test_current_pair_actual_temp_files_deny_symlink_hardlink_mode_and_atomic_replacement(self):
        import os,shutil
        from unittest import mock
        original=n.SOURCE
        for mutation in ('symlink','hardlink','mode','replacement'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);source_root=work/'source';folder=source_root/'tests/runtime/codex';folder.mkdir(parents=True)
                for name in ('native_delta.py','native_delta_test.py'):shutil.copyfile(original/'tests/runtime/codex'/name,folder/name)
                with mock.patch.object(n,'SOURCE',source_root.resolve()):
                    args,recipe,row,binding,m,pins,refresh,old=self.fixture(work)
                    path=folder/'native_delta_test.py'
                    if mutation=='symlink':
                        target=work/'same-bytes.py';target.write_bytes(path.read_bytes());path.unlink();path.symlink_to(target)
                    elif mutation=='hardlink':os.link(path,work/'same-inode.py')
                    elif mutation=='mode':path.chmod(0o600)
                    else:
                        target=work/'replacement';target.write_bytes(path.read_bytes());os.replace(target,path)
                    with mock.patch.object(n,'TASKS_TIMEOUT_PINS',pins),self.assertRaisesRegex(RuntimeError,'topology changed'):
                        n.validate_workflow_checkpoint(args,recipe,row,binding)

    def test_historical_reviewed_epoch_never_rehashes_current_pair_and_does_not_reset_lifetime(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);args,recipe,row,binding,m,pins,refresh,old=self.fixture(work)
            # A clearly synthetic previous source epoch, not claimed actual approval.
            historical='a'*64;section=m['live_source_protection'];index=n.checked_json(section['review_index'])
            index['reviewed_source']['tests/runtime/codex/native_delta.py']['sha256']=historical
            n.write(section['review_index']['path'],index);section['review_index']['sha256']=n.sha(section['review_index']['path']);section['files'][0]['sha256']=historical
            recipe['protected_files'][0]['sha256']=historical;recipe['adapter_sha256']=historical;relation=refresh()
            def ref(path):return {'path':str(path),'sha256':n.sha(path)}
            source=work/'source-review.json';doc=n.checked_json(ref(source));doc['collector_sha256']=historical;n.write(source,doc)
            review=work/'root-review.json';doc=n.checked_json(ref(review));doc.update(collector_sha256=historical,source_review=ref(source));n.write(review,doc)
            release=work/'release.json';doc=n.checked_json(ref(release));doc.update(collector_sha256=historical,source_review=ref(source),root_review=ref(review));n.write(release,doc);binding['workflow_release_sha256']=n.sha(release)
            attempt=TasksTimeoutHandoffTests().append_attempt(work,args,recipe,row,m,relation,0);usage=recipe['usage']+[attempt]
            pair_paths={x['path'] for x in section['files']};actual_sha=n.sha
            def no_current_pair_read(path):
                self.assertNotIn(str(path),pair_paths,'Historical admission must not read current source or test bytes')
                return actual_sha(path)
            with mock.patch.object(n,'TASKS_TIMEOUT_PINS',pins):
                with mock.patch.object(n,'sha',side_effect=no_current_pair_read):self.assertEqual(n.workflow_usage(usage)['notification-workflow/tasks'],1)
                with self.assertRaisesRegex(RuntimeError,'protected workflow'):n.validate_workflow_checkpoint(args,recipe,row,binding)
                recipe['usage']=usage;m['usage_sha256']=n.canonical_hash(usage);m['zero_request_suffix']=[attempt]
                next_prepared=work/'next';next_prepared.mkdir();m['live_source_protection']=self.proof(next_prepared)
                recipe['adapter_sha256']=n.sha(n.__file__)
                for i in (0,1):recipe['protected_files'][i]['sha256']=m['live_source_protection']['files'][i]['sha256']
                args.release_id='new-current-epoch';refresh(work/'current-prepared')
                flow=n.validate_workflow_checkpoint(args,recipe,row,binding)
                sent=TasksTimeoutHandoffTests().append_attempt(work/'current-prepared',args,recipe,row,m,flow['tasks_timeout_handoff'],1)
                charged=usage+[sent];self.assertEqual(n.workflow_usage(charged)['notification-workflow/tasks'],2)
                m['usage_sha256']=n.canonical_hash(charged);m['zero_request_suffix']=[attempt,sent];recipe['usage']=charged
                with self.assertRaisesRegex(RuntimeError,'already dispatched'):n.workflow_tasks_handoff(m,charged,recipe,row)
                # Rehashing the old independent index cannot repair its retained reference.
                oldindex=Path(section['review_index']['path']);oldindex.write_text('{}')
                with self.assertRaises(RuntimeError):n.workflow_usage(usage)

class NotificationBusinessEditTests(unittest.TestCase):
    def test_frozen_v62_five_file_conflict_and_original_latch_remain_real(self):
        import json
        base=n.SOURCE/'.omx/ultragoal/evidence';v61=base/'g004/codex/native-v61/runs-notification-workflow-tasks-timeout-approval-sourcee1-usage67-RELEASE-REQUIRED'
        frame=json.loads((v61/'poststart-baseline-v3.json').read_text())['second']
        diagnosis=json.loads((base/'r7-parent-verification/workflow-build-business-protection-diagnosis/diagnosis.json').read_text())
        self.assertEqual(len(diagnosis['consumer_business_protections']),5)
        for ref in diagnosis['consumer_business_protections']:
            with self.subTest(path=ref['path']):
                baseline=n.PostStartBaseline(frame,copy.deepcopy(frame));changed=copy.deepcopy(frame);changed['files'][ref['path']]['sha256']='actual changed business projection'
                with self.assertRaisesRegex(RuntimeError,'baseline drift'):baseline.check(changed)
                with self.assertRaises(RuntimeError):baseline.check(frame)

    def fixture(self,work):
        import json
        args,recipe,row,binding,m,pins,_=TasksTimeoutHandoffTests().fixture(work);root=work/'consumer'
        def ref(p):return {'path':str(p),'sha256':n.sha(p)}
        for name in ('app/settings.py','app/notifier.py','app/__init__.py','tests/test_settings.py','tests/__init__.py'):
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('# initial '+name)
        tasks=root/'docs/tasks.md';draft=work/'tasks-draft.md';draft.write_bytes(tasks.read_bytes());tasks.write_text('---\nstatus: approved\n---\nT1 through T6 approved plan and stops')
        snapshot=work/'approved-tasks.md';snapshot.write_bytes(tasks.read_bytes())
        reference=recipe['usage'][-1];cp=n.checked_json(reference);wire=n.checked_json(cp['wire'])
        wire[0]['payload']['params']['input']=[{'type':'text','text':'Actual plan-only approval; no implementation'}]
        wire.append({'direction':'response_or_event','payload':{'method':'turn/completed','params':{'turn':{'status':'completed','error':None}}}})
        n.write(cp['wire']['path'],wire);cp['wire']=ref(Path(cp['wire']['path']));cp.update(healthy=True,failure=None,state=n.workflow_inventory(root))
        oldrecipe=n.checked_json(cp['recipe']);oldrecipe['protected_files']=[ref(root/name) for name in ('app/settings.py','app/notifier.py','app/__init__.py','tests/test_settings.py','tests/__init__.py','AGENTS.md','CLAUDE.md')]
        n.write(cp['recipe']['path'],oldrecipe);cp['recipe']=ref(Path(cp['recipe']['path']));n.write(reference['path'],cp);reference=ref(Path(reference['path']));recipe['usage'][-1]=reference
        taskproof=work/'tasks-USER.json';n.write(taskproof,{'context':reference,'wire_index':0,'payload_sha256':n.canonical_hash(wire[0]['payload']),'text':wire[0]['payload']['params']['input'][0]['text'],'approved_artifact':ref(tasks),'draft_artifact':ref(draft)})
        business={'spec':ref(root/'docs/spec.md'),'spec_approval':ref(work/'spec-USER.json'),'tasks':ref(tasks),'tasks_approval':ref(taskproof)}
        row.update(id='copy-notification-build-test',initial_user_text='Actual distinct implementation start for the selected approved tasks',max_user_turns=1)
        recipe.update(phase='build',workflow_checkpoint=reference,rows=[row],protected_files=oldrecipe['protected_files']);args.current_author_checkpoint=reference['path'];args.row=row['id']
        contract=work/'business-edit.json'
        data={'schema':'workflow-notification-business-edit-v1','root':str(root),'realroot':str(root.resolve()),'phase':'build','row_id':row['id'],'predecessor':reference,'state_sha256':n.canonical_hash(cp['state']),
            'spec':business['spec'],'spec_USER':business['spec_approval'],'tasks':business['tasks'],'tasks_USER':business['tasks_approval'],
            'grant':{'initial_USER_sha256':n.canonical_hash(row['initial_user_text'])},'directories':[],
            'files':[{'path':'app/settings.py','canonical_path':str(root.resolve()/'app/settings.py'),'action':'edit','preimage':cp['state']['app/settings.py'],'mode':'0o644','tasks':['T1'],'parent':cp['state']['app']},
                     {'path':'tests/test_notifier.py','canonical_path':str(root.resolve()/'tests/test_notifier.py'),'action':'create','preimage':None,'mode':'0o644','tasks':['T4'],'parent':cp['state']['tests']}]}
        audit_ref=ref(work/'audit.md');quota_ref=ref(work/'quota.json')
        def refresh(prepared=None):
            nonlocal work,contract
            if prepared is not None:
                work=prepared;work.mkdir();contract=work/'business-edit.json';args.prepared=str(work);args.out=str(work/'out');args.current_author_release=str(work/'release.json');args.current_author_checkpoint=recipe['workflow_checkpoint']['path']
            current_cp=n.checked_json(recipe['workflow_checkpoint'])
            n.write(contract,data);recipe['business_edit_contract']=ref(contract);n.write(work/'recipe.json',recipe)
            native=work/'native.json';n.write(native,{k:v for k,v in binding.items() if k not in ('workflow_native_premises_sha256','workflow_release_sha256')})
            common={'checkpoint_sha256':recipe['workflow_checkpoint']['sha256'],'recipe_sha256':n.sha(work/'recipe.json'),'collector_sha256':n.sha(n.__file__),'helpers':recipe['helper_imports'],
                'manifest_sha256':recipe['release_manifest_sha256'],'native_premises_sha256':n.sha(native),'purpose':recipe['purpose'],'phase':recipe['phase'],'unit':recipe['unit']}
            source=work/'source-review.json';source_doc=dict(common,schema='WORKFLOW_SOURCE_REVIEW_V1',decision='APPROVE_EXACT_BOUND_CONTEXT',report=audit_ref,business_edit_contract=ref(contract))
            if data.get('implementation_review'):
                epoch=data['implementation_review'];index=n.checked_json(epoch);report=Path(epoch['path']).parent/'REPORT.md';source_doc.update(implementation_review=epoch,report=ref(report))
            n.write(source,source_doc)
            review=work/'root-review.json';n.write(review,dict(common,schema='WORKFLOW_ROOT_REVIEW_V1',decision='APPROVE_EXACT_BOUND_CONTEXT',report=audit_ref,source_review=ref(source),business=business,business_edit_contract=ref(contract),
                authority_evidence=[ref(taskproof)],state_sha256=n.canonical_hash(current_cp['state']),usage_sha256=n.canonical_hash(recipe['usage']),**({'business_transition':business['transition_review']} if business.get('transition_review') else {})))
            release=work/'release.json';n.write(release,dict(common,schema='WORKFLOW_RELEASE_V1',release_id=args.release_id,root=str(root),realroot=str(root.resolve()),row_id=row['id'],out=str(Path(args.out).resolve()),
                max_new_contexts=1,max_new_model_USER_turns=row['max_user_turns'],seconds=180,actual_before=21+sum(n.workflow_usage(recipe['usage']).values()),held_before=85-sum(n.workflow_usage(recipe['usage']).values()),whole=106,
                initial_USER_sha256=n.canonical_hash(row['initial_user_text']),native_premises=ref(native),source_review=ref(source),root_review=ref(review),allocation=quota_ref,business_edit_contract=ref(contract)))
            binding.update(workflow_native_premises_sha256=n.sha(native),workflow_release_sha256=n.sha(release));n.write(work/'binding.json',binding)
        refresh();return args,recipe,row,binding,data,business,refresh

    def test_real_validator_business_partition_allows_only_declared_edits_and_new_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);args,recipe,row,binding,data,business,refresh=self.fixture(work)
            flow=n.validate_workflow_checkpoint(args,recipe,row,binding);edit=flow['business_edit'];before=n.notification_business_sample(edit)
            immutable={p for p in flow['protected'] if p not in edit['paths']}
            strict=n.PostStartBaseline({'files':{p:n.sha(p) for p in immutable}},{'files':{p:n.sha(p) for p in immutable}})
            (work/'consumer/app/settings.py').write_text('# implemented authorized change');(work/'consumer/tests/test_notifier.py').write_text('# new authorized test')
            after=n.notification_business_sample(edit);result=n.notification_business_delta(edit,before,after)
            self.assertEqual(set(result['changed']),{'app/settings.py','tests/test_notifier.py'});self.assertFalse(result['business_files_equal']);self.assertEqual(result['status'],'OBSERVED_BUSINESS_SCOPE_REQUIRES_ROOT_REVIEW')
            strict.check({'files':{p:n.sha(p) for p in immutable}})
            with self.assertRaises(RuntimeError):n.notification_business_sample(edit,[str(work/'consumer/app/settings.py')])
            (work/'consumer/app/__init__.py').write_text('not authorized')
            with self.assertRaises(RuntimeError):n.notification_business_delta(edit,after,n.notification_business_sample(edit))

    def test_missing_scope_authority_preimage_and_alias_denials(self):
        for mutation in ('init','nonbuild','root','preimage','grant','plan-only','outside','mode','parent','spec','tasks','source','Root','release'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);args,recipe,row,binding,data,business,refresh=self.fixture(work)
                if mutation=='init':data['files'][0]['path']='app/__init__.py'
                elif mutation=='nonbuild':recipe['phase']='tasks'
                elif mutation=='root':data['root']=str(work)
                elif mutation=='preimage':data['files'][0]['preimage']={}
                elif mutation=='grant':data['grant']={}
                elif mutation=='plan-only':data['grant']={'actual_USER':business['tasks_approval']}
                elif mutation=='outside':data['files'][0]['canonical_path']=str(n.SOURCE/'skills/ains-build/SKILL.md')
                elif mutation=='mode':data['files'][0]['mode']='0o777'
                elif mutation=='parent':data['files'][0]['parent']={}
                elif mutation=='spec':data['spec']['sha256']='wrong'
                elif mutation=='tasks':data['tasks_USER']={}
                refresh()
                if mutation in ('source','Root','release'):
                    path=work/({'source':'source-review.json','Root':'root-review.json','release':'release.json'}[mutation]);doc=n.checked_json({'path':str(path),'sha256':n.sha(path)});doc.pop('business_edit_contract');n.write(path,doc)
                    if mutation=='release':binding['workflow_release_sha256']=n.sha(path)
                with self.assertRaises((RuntimeError,KeyError,OSError)):n.validate_workflow_checkpoint(args,recipe,row,binding)

    def test_mocked_dispatch_real_contract_raw_inequality_and_scope_failures(self):
        for mode in ('healthy','two','outside','unstable','config','between','waiting','late-between','immutable-between','git'):
            with self.subTest(mode=mode):RemainingWorkflowTests().test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_business=True,_business_edit=mode)

    def test_live_bundle_implicit_immutable_union_wins_before_any_RPC(self):
        import types
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);args,recipe,row,binding,data,business,refresh=self.fixture(work);edit=n.validate_workflow_checkpoint(args,recipe,row,binding)['business_edit'];target=work/'consumer/app/settings.py'
            helpers={'activation_r3':types.SimpleNamespace(),'activation_closure_probe':types.SimpleNamespace(structural=lambda x:x)}
            for role in ('raw-config','instruction','manifest','installed'):
                calls=[];rpc=types.SimpleNamespace(call=lambda *a,**kw:calls.append(a))
                raw=[str(target)] if role=='raw-config' else [];instructions=[str(target)] if role=='instruction' else []
                manifest=target if role=='manifest' else work/'manifest.json';installed=[{'path':str(target)}] if role=='installed' else []
                with self.subTest(role=role),mock.patch.object(n,'released_source'),self.assertRaisesRegex(RuntimeError,'immutable role'):
                    n.live_bundle(rpc,work/'consumer',installed,raw,manifest,helpers,{'proof_path':str(work/'proof.txt')},instructions,business_edit=edit)
                self.assertEqual(calls,[])

    def test_business_continuity_rejects_cache_unknown_and_alias_but_accepts_atomic_regular_write(self):
        import os
        for mutation in ('cache','unknown','alias','hardlink','atomic'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);args,recipe,row,binding,data,business,refresh=self.fixture(work);edit=n.validate_workflow_checkpoint(args,recipe,row,binding)['business_edit'];before=n.notification_business_sample(edit);root=work/'consumer'
                if mutation=='cache':(root/'unexpected.pyc').write_bytes(b'unknown')
                elif mutation=='unknown':(root/'app/extra.py').write_text('not declared')
                elif mutation=='alias':(root/'tests/test_notifier.py').symlink_to(root/'app/settings.py')
                elif mutation=='hardlink':os.link(root/'app/settings.py',root/'tests/test_notifier.py')
                else:
                    replacement=work/'replacement';replacement.write_text('authorized atomically replaced business file');os.replace(replacement,root/'app/settings.py')
                if mutation=='atomic':self.assertIn('app/settings.py',n.notification_business_delta(edit,before,n.notification_business_sample(edit))['changed'])
                else:
                    with self.assertRaises(RuntimeError):n.notification_business_delta(edit,before,n.notification_business_sample(edit))

    def ac9_fixture(self,work):
        args,recipe,row,binding,data,business,refresh=self.fixture(work);root=work/'consumer'
        def ref(path):return {'path':str(path),'sha256':n.sha(path)}
        (root/'.git').mkdir();(root/'.git/HEAD').write_text('before Git operation fixture')
        cp=n.checked_json(recipe['workflow_checkpoint']);wire=n.checked_json(cp['wire']);index=len(wire)-1
        question={'direction':'response_or_event','payload':{'id':'git','method':'item/tool/requestUserInput','params':{'questions':[{'id':'operations','question':'Actual operation scope?'}]}}}
        answer={'direction':'request','payload':{'id':'git','result':{'answers':{'operations':{'answers':['Actual separate Git operation decision fixture']}}}}}
        wire[index:index]=[question,answer];n.write(cp['wire']['path'],wire);cp['wire']=ref(Path(cp['wire']['path']));cp['state']=n.workflow_inventory(root)
        n.write(recipe['workflow_checkpoint']['path'],cp);reference=ref(Path(recipe['workflow_checkpoint']['path']));recipe['workflow_checkpoint']=reference;recipe['usage'][-1]=reference;args.current_author_checkpoint=reference['path']
        taskproof=n.checked_json(business['tasks_approval']);taskproof['context']=reference;n.write(business['tasks_approval']['path'],taskproof);business['tasks_approval']=ref(Path(business['tasks_approval']['path']))
        build_wire=work/'prior-build-wire.json';build_events=copy.deepcopy(wire);build_events[0]['payload']['params']['input']=[{'type':'text','text':'Actual prior BUILD fixture, then operation question'}];n.write(build_wire,build_events)
        build_release=work/'prior-build-release.json';released=n.checked_json(cp['release']);released.update(phase='build',release_id='prior-build');n.write(build_release,released)
        build=dict(cp,phase='build',wire=ref(build_wire),release=ref(build_release),release_id='prior-build',prior_usage_sha256=n.canonical_hash(recipe['usage']))
        build_context=work/'prior-build-context.json';n.write(build_context,build);reference=ref(build_context);recipe['usage'].append(reference);recipe['workflow_checkpoint']=reference;args.current_author_checkpoint=reference['path']
        grant=work/'Git-USER.json';n.write(grant,{'context':reference,'wire_index':index+1,'payload_sha256':n.canonical_hash(answer['payload']),'text':'Actual separate Git operation decision fixture'});business['Git_grant']=ref(grant)
        recipe['phase']='AC9-handoff';data.update(phase='AC9-handoff',predecessor=reference,state_sha256=n.canonical_hash(cp['state']),tasks_USER=business['tasks_approval'],git=True,
            off_data={'path':'off.json','sha256':hashlib.sha256(b'{"notification":false}\n').hexdigest(),'preimage':None,'parent':cp['state']['.']})
        refresh();return args,recipe,row,binding,data,business,refresh

    def test_actual_separate_Git_USER_is_required_for_AC9_contract_before_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);args,recipe,row,binding,data,business,refresh=self.ac9_fixture(work)
            self.assertIn('business_edit',n.validate_workflow_checkpoint(args,recipe,row,binding))
            grant=business.pop('Git_grant');refresh()
            with self.assertRaises((KeyError,RuntimeError)):n.validate_workflow_checkpoint(args,recipe,row,binding)
            business['Git_grant']=grant;data.pop('off_data');refresh()
            with self.assertRaisesRegex(RuntimeError,'OFF data before dispatch'):n.validate_workflow_checkpoint(args,recipe,row,binding)

    def test_AC9_git_candidate_requires_grant_scope_and_keeps_exact_OFF_data(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);args,recipe,row,binding,data,business,refresh=self.fixture(work);root=work/'consumer';edit=n.validate_workflow_checkpoint(args,recipe,row,binding)['business_edit']
            before=n.notification_business_sample(edit);(root/'.git').mkdir();(root/'.git/HEAD').write_text('actual changed Git metadata fixture')
            with self.assertRaisesRegex(RuntimeError,'Git change'):n.notification_business_delta(edit,before,n.notification_business_sample(edit))
            edit['data']=dict(edit['data'],phase='AC9-handoff',git=True)
            with self.assertRaisesRegex(RuntimeError,'OFF data'):n.notification_business_delta(edit,before,n.notification_business_sample(edit))
            off=root/'off.json';off.write_text('{"notification":false}\n');digest=n.sha(off)
            edit['data']['off_data']={'path':'off.json','sha256':digest};edit['entries']['off.json']={'path':'off.json','mode':'0o644','action':'create'}
            result=n.notification_business_delta(edit,before,n.notification_business_sample(edit));self.assertTrue(result['git_candidate']);self.assertEqual(result['status'],'HELD_GIT_SCOPE_REQUIRES_ROOT_REVIEW')
            stable=n.notification_business_sample(edit);off.unlink()
            with self.assertRaises(RuntimeError):n.notification_business_delta(edit,stable,n.notification_business_sample(edit))
            off.write_text('{"notification":true}\n')
            with self.assertRaises(RuntimeError):n.notification_business_delta(edit,stable,n.notification_business_sample(edit))

    def test_reviewed_task_progress_carries_actual_approval_without_reapproving_new_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);args,recipe,row,binding,data,business,refresh=self.fixture(work);root=work/'consumer';approved=dict(business['tasks']);snapshot=work/'approved-tasks.md';tasks=root/'docs/tasks.md'
            tasks.write_text(tasks.read_text()+'\nT1: real completed progress fixture\n');current={'path':str(tasks),'sha256':n.sha(tasks)}
            context=n.checked_json(recipe['workflow_checkpoint']);context['state']=n.workflow_inventory(root);path=work/'progress-context.json';n.write(path,context);reference={'path':str(path),'sha256':n.sha(path)}
            recipe['usage']=recipe['usage']+[reference];business['tasks']=current
            with self.assertRaises(RuntimeError):n.workflow_business(recipe,{'business':business},root)
            business['tasks_progress']={'approved_artifact':approved,'approved_snapshot':{'path':str(snapshot),'sha256':n.sha(snapshot)},'current_artifact':current,'context':reference,'wire':context['wire'],'report':{'path':str(work/'audit.md'),'sha256':n.sha(work/'audit.md')}}
            n.workflow_business(recipe,{'business':business},root)
            business['tasks_progress']['approved_artifact']=current
            with self.assertRaises(RuntimeError):n.workflow_business(recipe,{'business':business},root)

    def test_reviewed_postimage_new_context_preserves_old_recipe_and_rejects_stale_seed_or_missing_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);args,recipe,row,binding,data,business,refresh=self.fixture(work);root=work/'consumer'
            edit=n.validate_workflow_checkpoint(args,recipe,row,binding)['business_edit'];before=n.notification_business_sample(edit)
            def ref(path):return {'path':str(path),'sha256':n.sha(path)}
            old_recipe=ref(work/'recipe.json');old_release=ref(work/'release.json');immutable_recipe_bytes=(work/'recipe.json').read_bytes()
            (root/'app/settings.py').write_text('genuine observed implementation postimage fixture')
            (root/'tests/test_notifier.py').write_text('genuine observed test fixture')
            after=n.notification_business_sample(edit);facts=n.notification_business_delta(edit,before,after)
            previous=n.checked_json(recipe['workflow_checkpoint']);thread=previous['thread_id']
            events=[{'method':'turn/completed','params':{'turn':{'status':'completed','error':None}}}]
            wire=work/'build-wire.json';n.write(wire,[{'direction':'request','payload':{'method':'turn/start','params':{'threadId':thread,'input':[{'type':'text','text':row['initial_user_text']}]}}}]+[{'direction':'response_or_event','payload':e} for e in events])
            facts.update(contract=recipe['business_edit_contract'],events=events,user_history=[{'role':'user','text':row['initial_user_text']}],wire_start_index=0,wire_end_index=2,process_id=previous['process_id'],thread_id=thread);fact_file=work/'build-fact.json';n.write(fact_file,facts)
            immutable=n.checked_json(previous['facts']['poststart-baseline-v3.json'])['first'];config_file=work/'build-config.json'
            n.write(config_file,{'schema_version':'workflow-business-bundle-v1','contract':recipe['business_edit_contract'],'immutable_before':immutable,'immutable_after':immutable,'immutable_stable':True,
                'business_before':before,'business_after':after,'business_files_equal':False,'full_observed_files_equal':False,'baseline_reset_allowed':False})
            cp=dict(previous,purpose='workflow-after-setup',phase='build',unit='notification-workflow',state=after,collector_sha256=recipe['adapter_sha256'],config_facts={'config-01.json':ref(config_file)},healthy=True,failure=None,prior_usage_sha256=n.canonical_hash(recipe['usage']),release_id=args.release_id,
                release=old_release,recipe=old_recipe,wire=ref(wire),business_edit_contract=recipe['business_edit_contract'],business_facts=[ref(fact_file)])
            context=work/'build-context.json';n.write(context,cp);reference=ref(context);recipe['usage']=recipe['usage']+[reference];recipe['workflow_checkpoint']=reference
            data.update(predecessor=reference,state_sha256=n.canonical_hash(after));data['files'][0]['preimage']=after['app/settings.py'];data['files'][1].update(action='edit',preimage=after['tests/test_notifier.py'])
            for entry in recipe['protected_files']:
                if entry['path']==str(root/'app/settings.py'):entry['sha256']=n.sha(root/'app/settings.py')
            business['transition_review']={'context':reference,'facts':ref(fact_file),'state_sha256':n.canonical_hash(after),'report':ref(work/'audit.md')}
            args.release_id='next-real-context';refresh(work/'next-prepared')
            self.assertIn('business_edit',n.validate_workflow_checkpoint(args,recipe,row,binding));self.assertEqual((work/'recipe.json').read_bytes(),immutable_recipe_bytes)
            saved=business.pop('transition_review');refresh()
            with self.assertRaises((RuntimeError,KeyError)):n.validate_workflow_checkpoint(args,recipe,row,binding)
            business['transition_review']=saved;recipe['protected_files'][0]['sha256']='stale-seed';refresh()
            with self.assertRaisesRegex(RuntimeError,'protected workflow'):n.validate_workflow_checkpoint(args,recipe,row,binding)

    def history_case(self,work,turns=1):
        args,recipe,row,binding,data,business,refresh=self.fixture(work);root=work/'consumer'
        row['max_user_turns']=turns;refresh()
        def ref(path):return {'path':str(path),'sha256':n.sha(path)}
        original=n.checked_json(recipe['workflow_checkpoint']);pair=n.checked_json(original['facts']['poststart-baseline-v3.json'])
        current=n.notification_business_sample(n.validate_workflow_checkpoint(args,recipe,row,binding)['business_edit']);initial=copy.deepcopy(current)
        wire=[];observations=[];history=[];config={}
        for number in range(1,turns+1):
            text=row['initial_user_text'] if number==1 else 'Actual second released input'
            start=len(wire);wire.append({'direction':'request','payload':{'method':'turn/start','params':{'threadId':original['thread_id'],'input':[{'type':'text','text':text}]}}})
            history.append({'role':'user','text':text});before=current
            (root/'app/settings.py').write_text('Actual implementation '+str(number));(root/'tests/test_notifier.py').write_text('Actual test postimage')
            current=n.workflow_inventory(root)
            # Terminal followed by real-shaped config drain request/response: all belong to this interval.
            wire.extend([{'direction':'response_or_event','payload':{'method':'turn/completed','params':{'turn':{'status':'completed','error':None}}}},
                         {'direction':'request','payload':{'id':number,'method':'config/read','params':{'cwd':str(root)}}},
                         {'direction':'response_or_event','payload':{'id':number,'status':'ok','receipt_schema':n.RECEIPT_VERSION}}])
            edit={'data':data,'entries':{item['path']:item for item in data['files']},'directories':set()}
            fact=n.notification_business_delta(edit,before,current)
            fact.update(contract=recipe['business_edit_contract'],events=[e['payload'] for e in wire[start:] if e['direction']=='response_or_event'],user_history=copy.deepcopy(history),
                        wire_start_index=start,wire_end_index=len(wire),process_id=original['process_id'],thread_id=original['thread_id'])
            path=work/('fact-%02d.json'%number);n.write(path,fact);observations.append(ref(path))
            path=work/('config-%02d.json'%number);n.write(path,{'schema_version':'workflow-business-bundle-v1','contract':recipe['business_edit_contract'],
                'immutable_before':pair['first'],'immutable_after':pair['first'],'immutable_stable':True,'business_before':before,'business_after':current,
                'business_files_equal':before==current,'full_observed_files_equal':False,'baseline_reset_allowed':False});config[path.name]=ref(path)
        path=work/'history-wire.json';n.write(path,wire)
        record=dict(original,purpose=recipe['purpose'],phase=recipe['phase'],unit=recipe['unit'],healthy=True,failure=None,state=current,collector_sha256=recipe['adapter_sha256'],
            prior_usage_sha256=n.canonical_hash(recipe['usage']),release_id=args.release_id,release=ref(work/'release.json'),recipe=ref(work/'recipe.json'),wire=ref(path),
            business_edit_contract=recipe['business_edit_contract'],business_facts=observations,business_samples=[],config_facts=config)
        context=work/'history-context.json'
        def save():n.write(context,record);return recipe['usage']+[ref(context)]
        return record,wire,save,initial

    def bind_history_authority(self,record):
        """Synthetic retained reviews are re-bound, never actual Root authority."""
        def ref(path):return {'path':str(path),'sha256':n.sha(path)}
        recipe=n.checked_json(record['recipe']);release=n.checked_json(record['release'])
        source=n.checked_json(release['source_review']);review=n.checked_json(release['root_review'])
        for doc in (source,review,release):doc.update(recipe_sha256=record['recipe']['sha256'],collector_sha256=recipe['adapter_sha256'],business_edit_contract=recipe['business_edit_contract'])
        n.write(release['source_review']['path'],source);review['source_review']=release['source_review']=ref(release['source_review']['path'])
        n.write(release['root_review']['path'],review);release['root_review']=ref(release['root_review']['path'])
        n.write(record['release']['path'],release);record['release']=ref(record['release']['path'])

    def test_history_uses_retained_producer_epoch_without_reading_current_business_or_source(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);record,wire,save,initial=self.history_case(work,2)
            recipe=n.checked_json(record['recipe']);recipe['adapter_sha256']='a'*64
            n.write(record['recipe']['path'],recipe);record['recipe']['sha256']=n.sha(record['recipe']['path']);record['collector_sha256']=recipe['adapter_sha256'];self.bind_history_authority(record)
            (work/'consumer/app/settings.py').write_text('later actual business bytes must not rehash the historical preimage')
            real_sha=n.sha
            def retained_only(path):
                self.assertFalse(str(path).startswith(str(work/'consumer')))
                self.assertNotIn(str(path),(str(n.SOURCE/'tests/runtime/codex/native_delta.py'),str(n.SOURCE/'tests/runtime/codex/native_delta_test.py')))
                return real_sha(path)
            usage=save()
            with mock.patch.object(n,'sha',side_effect=retained_only):self.assertEqual(n.workflow_usage(usage)['notification-workflow/build'],2)

    def test_history_recomputes_transition_producer_and_distinct_full_turn_intervals(self):
        import json
        for change in ('before','changed','equality','exclude-USER','exclude-drain','collector','duplicate','contract-preimage','Root','source','producer-usage','USER','late-error','scope','immutable-config','wrong-thread','protected-list','unknown-contract','row-bool'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);record,wire,save,initial=self.history_case(work,2 if change=='duplicate' else 1)
                self.assertEqual(n.workflow_usage(save())['notification-workflow/build'],2 if change=='duplicate' else 1)
                fact=n.checked_json(record['business_facts'][0])
                if change=='before':fact['before']={}
                elif change=='changed':fact['changed']=[]
                elif change=='equality':fact['business_files_equal']=True
                elif change=='exclude-USER':fact['wire_start_index']=1
                elif change=='exclude-drain':fact['wire_end_index']=2;fact['events']=fact['events'][:1]
                elif change=='collector':record['collector_sha256']='0'*64
                elif change=='duplicate':record['business_facts']=[record['business_facts'][0]]*2
                elif change=='USER':fact['user_history']=[{'role':'user','text':'forged USER'}]
                elif change=='immutable-config':
                    config=n.checked_json(record['config_facts']['config-01.json']);config.update(immutable_before={'forged':True},immutable_after={'forged':True})
                    n.write(record['config_facts']['config-01.json']['path'],config);record['config_facts']['config-01.json']['sha256']=n.sha(record['config_facts']['config-01.json']['path'])
                elif change=='wrong-thread':
                    wire[0]['payload']['params']['threadId']='other';n.write(record['wire']['path'],wire);record['wire']['sha256']=n.sha(record['wire']['path'])
                elif change=='late-error':
                    wire.append({'direction':'response_or_event','payload':{'method':'error','params':{'error':'late after terminal'}}});n.write(record['wire']['path'],wire);record['wire']['sha256']=n.sha(record['wire']['path'])
                elif change=='scope':fact['current']['app/__init__.py']['sha256']='unapproved';record['state']=fact['current']
                elif change in ('contract-preimage','producer-usage','protected-list','unknown-contract','row-bool'):
                    recipe=n.checked_json(record['recipe'])
                    if change in ('contract-preimage','unknown-contract'):
                        contract=n.checked_json(record['business_edit_contract'])
                        if change=='contract-preimage':contract['files'][0]['preimage']={}
                        else:contract['unreviewed_extension']=True
                        n.write(record['business_edit_contract']['path'],contract);record['business_edit_contract']['sha256']=n.sha(record['business_edit_contract']['path']);recipe['business_edit_contract']=record['business_edit_contract']
                    elif change=='protected-list':recipe['protected_files']=recipe['protected_files'][:-1]
                    elif change=='row-bool':recipe['rows'][0]['max_user_turns']=True
                    else:recipe['usage']=[]
                    n.write(record['recipe']['path'],recipe);record['recipe']['sha256']=n.sha(record['recipe']['path'])
                    self.bind_history_authority(record)
                else:
                    release=n.checked_json(record['release']);key='root_review' if change=='Root' else 'source_review';review=n.checked_json(release[key]);review['collector_sha256']='0'*64
                    n.write(release[key]['path'],review);release[key]['sha256']=n.sha(release[key]['path']);n.write(record['release']['path'],release);record['release']['sha256']=n.sha(record['release']['path'])
                if change in ('before','changed','equality','exclude-USER','exclude-drain','USER','scope'):
                    path=work/'mutated-fact.json';n.write(path,fact);record['business_facts'][0]={'path':str(path),'sha256':n.sha(path)}
                with self.assertRaises((RuntimeError,KeyError,ValueError)):n.workflow_usage(save())

    def test_history_cannot_turn_unhealthy_predecessor_into_business_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);record,wire,save,initial=self.history_case(work)
            usage=save();producer=n.checked_json(record['recipe']);cp=n.checked_json(producer['workflow_checkpoint']);cp['healthy']=False
            path=work/'unhealthy-cp.json';n.write(path,cp);reference={'path':str(path),'sha256':n.sha(path)}
            usage[-2]=reference;producer['usage']=usage[:-1];producer['workflow_checkpoint']=reference;record['prior_usage_sha256']=n.canonical_hash(producer['usage'])
            contract=n.checked_json(record['business_edit_contract']);proof=n.checked_json(contract['tasks_USER']);proof['context']=reference
            n.write(contract['tasks_USER']['path'],proof);contract['tasks_USER']['sha256']=n.sha(contract['tasks_USER']['path']);contract['predecessor']=reference
            n.write(record['business_edit_contract']['path'],contract);record['business_edit_contract']['sha256']=n.sha(record['business_edit_contract']['path']);producer['business_edit_contract']=record['business_edit_contract']
            n.write(record['recipe']['path'],producer);record['recipe']['sha256']=n.sha(record['recipe']['path'])
            release=n.checked_json(record['release'])
            for key in ('source_review','root_review'):
                doc=n.checked_json(release[key]);doc['checkpoint_sha256']=reference['sha256']
                if key=='root_review':doc['usage_sha256']=n.canonical_hash(producer['usage']);doc['business']['tasks_approval']=contract['tasks_USER'];doc['authority_evidence']=[contract['tasks_USER']]
                n.write(release[key]['path'],doc);release[key]['sha256']=n.sha(release[key]['path'])
            release['checkpoint_sha256']=reference['sha256'];n.write(record['release']['path'],release);record['release']['sha256']=n.sha(record['release']['path']);self.bind_history_authority(record)
            # No fabricated observation is needed to charge a failed dispatch; admission itself must still be valid.
            record.update(healthy=False,business_facts=[],business_samples=[]);n.write(usage[-1]['path'],record);usage[-1]['sha256']=n.sha(usage[-1]['path'])
            with self.assertRaises(RuntimeError):n.workflow_usage(usage)

    def test_history_failed_dispatch_charged_without_fabricated_healthy_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);record,wire,save,initial=self.history_case(work,2)
            # A second request was actually dispatched but timed out: first complete proof remains, second has none.
            second=n.checked_json(record['business_facts'][1]);wire=wire[:second['wire_start_index']+1]
            n.write(record['wire']['path'],wire);record['wire']['sha256']=n.sha(record['wire']['path']);record.update(healthy=False,failure='Absolute terminal deadline exceeded',business_facts=record['business_facts'][:1])
            self.assertEqual(n.workflow_usage(save())['notification-workflow/build'],2)
            record['healthy']=True
            with self.assertRaises(RuntimeError):n.workflow_usage(save())
            record.update(healthy=False,business_facts=[])
            self.assertEqual(n.workflow_usage(save())['notification-workflow/build'],2)

    def actual_v63_history(self):
        directory=n.SOURCE/'.omx/ultragoal/evidence/g004/codex/native-v63/runs-notification-workflow-build-initial-source365-usage68-RELEASE-REQUIRED'
        reference={'path':str(directory/'workflow-context.json'),'sha256':'761b78bd5c19bd9b1c0d49d04b6c7c51e63fdbff8017462b7acf8ac6e95eee51'}
        record=n.checked_json(reference);producer=n.checked_json(record['recipe'])
        return record,producer['usage']+[reference]

    def test_actual_v63_full41_charges_failed_BUILD_without_live_business_discovery(self):
        from unittest import mock
        record,usage=self.actual_v63_history();self.assertEqual(len(usage),41)
        protected=[]
        for root in (Path(record['root']),Path(record['realroot'])):
            protected.extend(str(root/name) for name in ('app','tests','docs/changes/2026-10-25-order-confirmation-email-toggle/tasks.md'))
        def guard(function):
            def call(path,*args,**kwargs):
                self.assertFalse(any(str(path)==name or str(path).startswith(name+'/') for name in protected),'current historical business path read: '+str(path))
                return function(path,*args,**kwargs)
            return call
        with mock.patch.object(Path,'resolve',guard(Path.resolve)),mock.patch.object(Path,'stat',guard(Path.stat)),mock.patch.object(Path,'lstat',guard(Path.lstat)),mock.patch.object(Path,'read_bytes',guard(Path.read_bytes)),mock.patch.object(Path,'read_text',guard(Path.read_text)):
            previous=n.workflow_usage(usage[:-1]);used=n.workflow_usage(usage)
        self.assertEqual(sum(previous.values()),47);self.assertEqual(sum(used.values()),48);self.assertEqual(used['notification-workflow/build'],1)
        self.assertEqual((21+sum(used.values()),85-sum(used.values()),106),(69,37,106))
        self.assertFalse(record['healthy']);self.assertTrue(record['closed']);self.assertEqual(record['failure'],'Absolute terminal deadline exceeded');self.assertEqual(record['business_facts'],[])
        self.assertEqual(record['config_facts'],{})
        self.assertEqual(sum(e['direction']=='request' and e['payload'].get('method')=='turn/start' for e in n.checked_json(record['wire'])),1)
        self.assertFalse(any(e['direction']=='response_or_event' and e['payload'].get('method')=='turn/completed' for e in n.checked_json(record['wire'])))

    def retained_namespace_case(self,work,change):
        # Clone only evidence JSON to the temporary fixture; no consumer files are read or materialized.
        record,usage=self.actual_v63_history();prior=usage[:-1];producer=n.checked_json(record['recipe']);cp=n.checked_json(producer['workflow_checkpoint'])
        release=n.checked_json(record['release']);review=n.checked_json(release['root_review']);source=n.checked_json(release['source_review']);data=n.checked_json(record['business_edit_contract'])
        def ref(name,value):
            path=work/name;n.write(path,value);return {'path':str(path),'sha256':n.sha(path)}
        name='docs/changes/2026-10-25-order-confirmation-email-toggle/tasks.md';canonical=Path(record['realroot']);logical=Path(record['root'])
        if change=='logical':review['business']['tasks']['path']=str(logical/name)
        elif change=='outside':review['business']['tasks']['path']='/outside/'+name
        elif change=='prefix':review['business']['tasks']['path']=str(canonical)+'-other/'+name
        elif change=='relative':review['business']['tasks']['path']=name
        elif change=='traversal':review['business']['tasks']['path']=str(canonical/'docs/..'/name)
        elif change=='dot':review['business']['tasks']['path']=str(canonical)+'/./'+name
        elif change=='suffix':review['business']['tasks']['path']=str(canonical/'other/tasks.md')
        elif change=='ambiguous':record['root']=cp['root']=data['root']=str(canonical/'docs')
        elif change=='wrong-root':record['realroot']=cp['realroot']=data['realroot']=str(canonical)+'-wrong'
        elif change=='hash':review['business']['tasks']['sha256']='0'*64
        elif change=='realpath':cp['state'][name]['realpath']='/outside/tasks.md'
        elif change=='kind':cp['state'][name]['kind']='symlink'
        elif change=='link':cp['state'][name]['link_text']='elsewhere'
        elif change=='parent-alias':cp['state'][str(Path(name).parent)]['kind']='symlink'
        elif change=='parent-escape':cp['state'][str(Path(name).parent)]['realpath']='/outside'
        elif change=='missing-parent':del cp['state'][str(Path(name).parent)]
        elif change=='missing-root':del cp['state']['.']
        elif change=='identity':cp['state']['app/__init__.py']['identity']=cp['state'][name]['identity']
        elif change=='missing-identity':cp['state'][name].pop('identity')
        data['tasks']=review['business']['tasks']
        # Bind changed retained checkpoint and real USER reference without changing the facts under test.
        reference=ref('checkpoint.json',cp);prior[-1]=reference;producer['usage']=prior;producer['workflow_checkpoint']=reference;record['prior_usage_sha256']=n.canonical_hash(prior)
        proof=n.checked_json(data['tasks_USER']);proof['context']=reference;data['tasks_USER']=ref('tasks-USER.json',proof);review['business']['tasks_approval']=data['tasks_USER'];review['authority_evidence']=[data['tasks_USER']]
        data['predecessor']=reference;data['state_sha256']=n.canonical_hash(cp['state'])
        for item in data['files']:
            if item['path']==name:item['preimage']=cp['state'].get(name);item['parent']=cp['state'].get(str(Path(name).parent))
        record['business_edit_contract']=ref('contract.json',data);producer['business_edit_contract']=record['business_edit_contract'];record['recipe']=ref('producer.json',producer)
        samples=[]
        for number,item in enumerate(record['business_samples']):
            sample=n.checked_json(item);sample['contract']=record['business_edit_contract'];samples.append(ref('sample-%02d.json'%number,sample))
        record['business_samples']=samples
        common={'checkpoint_sha256':reference['sha256'],'recipe_sha256':record['recipe']['sha256'],'business_edit_contract':record['business_edit_contract']}
        source.update(common);release.update(common);review.update(common,state_sha256=n.canonical_hash(cp['state']),usage_sha256=n.canonical_hash(prior))
        review['source_review']=release['source_review']=ref('source.json',source);release['root_review']=ref('Root.json',review)
        return record,prior,n.checked_json(record['wire']),release

    def test_retained_tasks_logical_and_canonical_namespaces_are_equivalent(self):
        for name in ('logical','canonical'):
            with self.subTest(namespace=name),tempfile.TemporaryDirectory() as tmp:
                record,prior,wire,release=self.retained_namespace_case(Path(tmp),name)
                n.notification_business_history(record,prior,wire,release)
        with tempfile.TemporaryDirectory() as tmp:
            record,wire,save,initial=self.history_case(Path(tmp).resolve())
            self.assertEqual(record['root'],record['realroot']);self.assertEqual(n.workflow_usage(save())['notification-workflow/build'],1)

    def test_retained_tasks_namespace_containment_and_inventory_denials(self):
        for change in ('outside','prefix','relative','traversal','dot','suffix','ambiguous','wrong-root','hash','realpath','kind','link','parent-alias','parent-escape','missing-parent','missing-root','identity','missing-identity'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as tmp:
                record,prior,wire,release=self.retained_namespace_case(Path(tmp),change)
                with self.assertRaisesRegex(RuntimeError,'HELD' if change in ('ambiguous','wrong-root') else 'retained tasks'):
                    n.notification_business_history(record,prior,wire,release)

    def test_source_epoch_requires_independent_current_pair_and_preserves_archived_producer(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);args,recipe,row,binding,data,business,refresh=self.fixture(work)
            def ref(path):return {'path':str(path),'sha256':n.sha(path)}
            cp=n.checked_json(recipe['workflow_checkpoint']);old=n.checked_json(cp['recipe']);scope=n.SOURCE/'.omx/ultragoal/evidence/r7-parent-verification/workflow-build-business-protection-implementation-scope/archive'
            for name in ('native_delta.py','native_delta_test.py'):old['protected_files'].append({'path':str(n.SOURCE/'tests/runtime/codex'/name),'sha256':n.sha(scope/name)})
            n.write(cp['recipe']['path'],old);cp['recipe']=ref(Path(cp['recipe']['path']));n.write(recipe['workflow_checkpoint']['path'],cp);reference=ref(Path(recipe['workflow_checkpoint']['path']))
            recipe['workflow_checkpoint']=reference;recipe['usage'][-1]=reference;args.current_author_checkpoint=reference['path'];data['predecessor']=reference
            proof=n.checked_json(business['tasks_approval']);proof['context']=reference;n.write(business['tasks_approval']['path'],proof);business['tasks_approval']=ref(Path(business['tasks_approval']['path']));data['tasks_USER']=business['tasks_approval']
            recipe['protected_files']=[x.copy() for x in old['protected_files']]
            epoch=LiveSourceProtectionRebindTests().proof(work)['review_index'];data['implementation_review']=epoch
            for item in recipe['protected_files']:
                if item['path'] in (str(n.SOURCE/'tests/runtime/codex/native_delta.py'),str(n.SOURCE/'tests/runtime/codex/native_delta_test.py')):item['sha256']=n.sha(item['path'])
            refresh();self.assertIn('business_edit',n.validate_workflow_checkpoint(args,recipe,row,binding))
            data.pop('implementation_review');refresh()
            with self.assertRaisesRegex(RuntimeError,'ordered protections'):n.validate_workflow_checkpoint(args,recipe,row,binding)

class BuildPosttimeoutHandoffTests(unittest.TestCase):
    """Only temporary future DATA fixtures; real frozen origin stays failed and untouched."""
    def fixture(self,work):
        import json
        e=n.SOURCE/'.omx/ultragoal/evidence';root_review=e/'r7-parent-verification/notification-workflow-build-timeout-actual-state-review'
        def existing(path):return {'path':str(path),'sha256':n.sha(path)}
        def put(name,value):
            path=work/name;n.write(path,value);return existing(path)
        origin,usage=NotificationBusinessEditTests().actual_v63_history();O=usage[-1];old=n.checked_json(origin['recipe']);oldrelease=n.checked_json(origin['release']);state=origin['state']
        decision=existing(e/'r7-parent-verification/notification-workflow-build-implementation-owner-review/decision.json');owner=n.checked_json(decision);H=owner['postimages']
        tp=n.checked_json(existing(e/'r7-parent-verification/workflow-build-approved-task-progress-review/tasks_progress-DATA.json'))
        memo=n.checked_json(existing(e/'r7-parent-verification/workflow-build-approved-task-progress-review/exact-added-memos.json'))
        G={'before':tp['approved_snapshot'],'after':H['docs/changes/2026-10-25-order-confirmation-email-toggle/tasks.md'],'checkoffs':['T1','T2','T3','T4','T5','T6'],'memos':memo['insertions'][0]['exact_text'],'body_equal':True}
        progress=put('progress.json',G);pair=LiveSourceProtectionRebindTests().proof(work)['review_index'];index=n.checked_json(pair)
        changed={str(Path(origin['root'])/name):name for name in ('app/settings.py','app/notifier.py','tests/test_settings.py')}
        K={'historical':origin['recipe'],'immutable':[dict(item) for item in old['protected_files'] if item['path'] not in changed],
           'business_deltas':[{'path':path,'before':existing(Path(O['path']).parent/'business-initial'/name),'after':H[name],'authorization':origin['business_edit_contract']} for path,name in changed.items()],
           'source_pair_review':pair,'forward':[dict(item) for item in old['protected_files']]}
        for item in K['forward']:
            if item['path'] in changed:item['sha256']=state[changed[item['path']]]['sha256']
            for name,info in index['reviewed_source'].items():
                if item['path']==str(n.SOURCE/name):item['sha256']=info['sha256']
        protections=put('protections.json',K)
        P={'origin':O,'state':state,'postimages':H,'protections':protections,'plan_progress':progress};p=put('P.json',P)
        input_decision=existing(e/'r7-parent-verification/workflow-build-close-flush-verification-input-DATA/input-decision.json');A=n.checked_json(input_decision);text=A['initial_user_text']
        C=n.checked_json(origin['business_edit_contract']);C.update(row_id=A['row_id'],predecessor=p,state_sha256=n.canonical_hash(state),tasks=tp['current_artifact'],grant={'initial_USER_sha256':n.canonical_hash(text)},
             directories=[],git=False,implementation_review=pair,files=[{'path':'tests/test_settings.py','canonical_path':str(Path(origin['realroot'])/'tests/test_settings.py'),'action':'edit','preimage':state['tests/test_settings.py'],'mode':'0o644','tasks':['T3'],'parent':state['tests']}]);C.pop('off_data',None)
        closure=put('closure.json',{'origin':O,'wire':origin['wire'],'operator_result':n.checked_json(existing(root_review/'review.json'))['actual_operator_result'],
             'closed_receipt':origin['facts']['live-rpc/closed.json'],'process_evidence':existing(root_review/'review.json'),'EOF':True,'terminal_count':0,'final_count':0})
        full=put('full-usage.json',{'contexts':usage,'postanchor_starts':48,'actual':69,'held':37,'whole':106,'build_used':1,'build_cap':3})
        M={'schema':'workflow-build-posttimeout-current-state-v1','root':origin['root'],'realroot':origin['realroot'],'state':state,'current_state':p,'current_state_sha256':n.canonical_hash(P),
           'origin_manifest':existing(Path(O['path']).parent/'FROZEN-MANIFEST.json'),'origin':O,'wire':origin['wire'],'original_recipe':origin['recipe'],'original_release':origin['release'],
           'original_contract':origin['business_edit_contract'],'original_source_review':oldrelease['source_review'],'original_root_review':oldrelease['root_review'],'original_native_premises':oldrelease['native_premises'],
           'audit_report':existing(e/'notification-workflow-build-timeout-state-disposition/REPORT.md'),'audit_coverage':existing(e/'notification-workflow-build-timeout-state-disposition/coverage.json'),'audit_index':existing(e/'notification-workflow-build-timeout-state-disposition/index.json'),
           'actual_review':existing(root_review/'review.json'),'program':existing(root_review/'completed-program.json'),'file_changes':existing(root_review/'completed-fileChanges.json'),'visible_messages':existing(root_review/'completed-visible-messages.json'),
           'accounting':existing(root_review/'usage-accounting.json'),'history_gap':existing(root_review/'history-gap.json'),'full_usage':full,
           'namespace_fix_review':existing(e/'workflow-build-history-canonical-root-source-review-r1/index.json'),'namespace_fix_adoption':existing(e/'r7-parent-verification/workflow-build-history-source63cc-activation/adoption.json'),
           'current_pair_review':pair,'owner_decision':decision,'closure':closure,'postimages':H,'protections':protections,'plan_progress':progress,'disposition':'CURRENT_STATE_ONLY_NOT_V63_PASS'}
        row={'id':A['row_id'],'mode':'copy','transport':'live','initial_user_text':text,'max_user_turns':1,'terminal_deadline_seconds':180}
        R=dict(old,adapter_sha256=n.sha(n.__file__),usage=usage,rows=[row],protected_files=K['forward'])
        B=dict(n.checked_json(oldrelease['root_review'])['business'],tasks=tp['current_artifact'],tasks_progress=tp)
        def refresh():
            M['next_action']={'id':'verify-close-flush','purpose':'workflow-after-setup','phase':'build','unit':'notification-workflow','row_id':row['id'],'input_decision':input_decision,'initial_USER_sha256':n.canonical_hash(text),'contract':put('C.json',C),'limits':{'contexts':1,'model_USER':1,'terminal_seconds':180,'outer_seconds':360}}
            M.pop('root_content_review',None);q=n.canonical_hash(M);report=work/'content-report.md';report.write_text('SYNTHETIC content review only: '+q)
            M['root_content_review']=put('Q.json',{'payload_sha256':q,'owner_decision':decision,'input_decision':input_decision,'decision':'APPROVE_EXACT_CURRENT_STATE_HANDOFF_CONTENT','report':existing(report)})
            material=put('M.json',M);X={'schema':'workflow-materialization-v1','root':M['root'],'realroot':M['realroot'],'state':M['state'],'materialization':material}
            R['workflow_checkpoint']=put('X.json',X);R['business_edit_contract']=M['next_action']['contract'];recipe=put('recipe.json',R)
            common={'checkpoint_sha256':R['workflow_checkpoint']['sha256'],'recipe_sha256':recipe['sha256'],'collector_sha256':R['adapter_sha256'],'helpers':R['helper_imports'],'manifest_sha256':R['release_manifest_sha256'],
                'native_premises_sha256':oldrelease['native_premises']['sha256'],'purpose':R['purpose'],'phase':R['phase'],'unit':R['unit'],'business_edit_contract':R['business_edit_contract']}
            source=dict(common,schema='WORKFLOW_SOURCE_REVIEW_V1',decision='APPROVE_EXACT_BOUND_CONTEXT',implementation_review=pair,report=existing(Path(pair['path']).parent/'REPORT.md'));source_ref=put('source.json',source)
            review=dict(common,schema='WORKFLOW_ROOT_REVIEW_V1',decision='APPROVE_EXACT_BOUND_CONTEXT',report=existing(report),source_review=source_ref,state_sha256=n.canonical_hash(state),usage_sha256=n.canonical_hash(R['usage']),business=B,authority_evidence=[decision,input_decision,progress,tp['report']]);review_ref=put('Root.json',review)
            release=dict(common,schema='WORKFLOW_RELEASE_V1',root=M['root'],realroot=M['realroot'],release_id='synthetic-new-context',row_id=row['id'],out=str((work/'out').resolve()),max_new_contexts=1,max_new_model_USER_turns=1,seconds=180,
                initial_USER_sha256=n.canonical_hash(text),actual_before=69,held_before=37,whole=106,native_premises=oldrelease['native_premises'],allocation=oldrelease['allocation'],source_review=source_ref,root_review=review_ref)
            put('release.json',release)
            return material,source,review,release
        return origin,R,row,M,C,P,K,G,B,refresh

    def test_actual_failed_origin_is_not_an_ordinary_healthy_checkpoint(self):
        from unittest import mock
        import types
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);args,R,row,binding,*unused=NotificationBusinessEditTests().fixture(work);origin,usage=NotificationBusinessEditTests().actual_v63_history()
            cp=dict(origin,root=str(work/'consumer'),realroot=str((work/'consumer').resolve()));path=work/'failed.json';n.write(path,cp);reference={'path':str(path),'sha256':n.sha(path)}
            R.update(usage=[reference],workflow_checkpoint=reference);args.current_author_checkpoint=str(path)
            with mock.patch.object(n,'workflow_usage',return_value={'notification-workflow/build':1}),self.assertRaisesRegex(RuntimeError,'latest healthy'):
                n.validate_workflow_checkpoint(args,R,row,binding)
            self.assertFalse(origin['healthy']);self.assertEqual(origin['business_facts'],[])

    def test_acyclic_bootstrap_exact153_179_progress_and_tests_only_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            origin,R,row,M,C,P,K,G,B,refresh=self.fixture(Path(tmp));material,source,review,release=refresh()
            self.assertEqual(len(M['state']),153);self.assertEqual(len(K['forward']),179);self.assertEqual(len(K['immutable']),176);self.assertEqual(len(K['business_deltas']),3)
            self.assertEqual(C['tasks'],B['tasks']);self.assertEqual(C['tasks']['sha256'],'475f3c941073fd3159ff5df197ce1a512eb096de69e3308cf2ce841bfb240dab')
            self.assertEqual(B['tasks_progress']['approved_artifact']['sha256'],'e6de5de42fb18f7ae481aab41ee390e5f8b867089489a8683913b3c7fa4b77f2')
            self.assertEqual(n.workflow_build_posttimeout(material,R['usage'],R,row,source,review,release),M)
            self.assertEqual(C['predecessor'],M['current_state']);self.assertNotEqual(C['predecessor'],R['workflow_checkpoint'])
            self.assertFalse(origin['healthy']);self.assertEqual(origin['business_facts'],[])

    def test_rehashed_bootstrap_owner_progress_scope_and_self_exclusion_denials(self):
        for change in ('pc','P-extra','state','owner','action','grant','predecessor','task-ref','scope','directory','git','git-int','progress-body','progress-memos','protection-third','source-pair','Q-exclusion','Q-extra','duplicate'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);origin,R,row,M,C,P,K,G,B,refresh=self.fixture(work)
                if change=='pc':M['current_state_sha256']='0'*64
                elif change=='P-extra':
                    P['extra']=True;n.write(M['current_state']['path'],P);M['current_state']['sha256']=n.sha(M['current_state']['path']);M['current_state_sha256']=n.canonical_hash(P);C['predecessor']=M['current_state']
                elif change=='state':M['state']=dict(M['state'],foreign={'kind':'file'})
                elif change=='owner':M['owner_decision']=M['audit_index']
                elif change=='action':row['max_user_turns']=2
                elif change=='grant':C['grant']={'actual_USER':M['owner_decision']}
                elif change=='predecessor':C['predecessor']=M['origin']
                elif change=='task-ref':C['tasks']=B['tasks_progress']['approved_artifact']
                elif change=='scope':C['files'][0]['path']='app/settings.py'
                elif change=='directory':C['directories']=[{'path':'new','preimage':None,'mode':'0o755'}]
                elif change=='git':C['git']=True
                elif change=='git-int':C['git']=0
                elif change.startswith('progress-'):
                    G['body_equal']=False if change=='progress-body' else True
                    if change=='progress-memos':G['memos']=G['memos'].rstrip()
                    n.write(M['plan_progress']['path'],G);M['plan_progress']['sha256']=n.sha(M['plan_progress']['path']);P['plan_progress']=M['plan_progress'];n.write(M['current_state']['path'],P);M['current_state']['sha256']=n.sha(M['current_state']['path']);M['current_state_sha256']=n.canonical_hash(P)
                elif change=='protection-third':K['forward'][0]['sha256']='0'*64;n.write(M['protections']['path'],K);M['protections']['sha256']=n.sha(M['protections']['path']);P['protections']=M['protections'];n.write(M['current_state']['path'],P);M['current_state']['sha256']=n.sha(M['current_state']['path']);M['current_state_sha256']=n.canonical_hash(P)
                elif change=='source-pair':M['current_pair_review']=M['namespace_fix_review']
                material,source,review,release=refresh()
                if change.startswith('Q-'):
                    Q=n.checked_json(M['root_content_review'])
                    if change=='Q-exclusion':Q['payload_sha256']=n.canonical_hash({k:v for k,v in M.items() if k not in ('root_content_review','owner_decision')})
                    else:Q['unused']=True
                    n.write(M['root_content_review']['path'],Q);M['root_content_review']['sha256']=n.sha(M['root_content_review']['path']);n.write(material['path'],M);material['sha256']=n.sha(material['path'])
                if change=='duplicate':
                    path=Path(material['path']);text=path.read_text();path.write_text(text[:-2]+',"schema":"workflow-build-posttimeout-current-state-v1"}');material['sha256']=n.sha(path)
                with self.assertRaises((RuntimeError,KeyError,ValueError,TypeError)):n.workflow_build_posttimeout(material,R['usage'],R,row,source,review,release)

    def future_record(self,work,R,origin,release,dispatches=1):
        def put(name,value):
            path=work/name;n.write(path,value);return {'path':str(path),'sha256':n.sha(path)}
        thread='synthetic-new-thread';process=12345;wire=[]
        for unused in range(dispatches):wire.append({'direction':'request','payload':{'id':91,'method':'turn/start','params':{'threadId':thread,'input':[{'type':'text','text':R['rows'][0]['initial_user_text']}]}}})
        start=n.checked_json(origin['facts']['thread-start-v3.json']);start['process_id']=process;start['response']['thread']['id']=thread
        facts=dict(origin['facts']);facts['thread-start-v3.json']=put('new-thread.json',start);facts['live-rpc/closed.json']=put('new-closed.json',{'stable':True})
        result=dict(origin,process_id=process,thread_id=thread,recipe=put('recipe.json',R),release=put('release.json',release),release_id=release['release_id'],
            wire=put('new-wire.json',wire),prior_usage_sha256=n.canonical_hash(R['usage']),collector_sha256=R['adapter_sha256'],facts=facts,business_edit_contract=R['business_edit_contract'],business_samples=[],business_facts=[],config_facts={},healthy=False,failure='Synthetic lost turn/start ack or timeout')
        return result,put('new-context.json',result)

    def test_full42_failed_lostack_charged_zero_hold_unconsumed_and_lifetime_exhausted(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);origin,R,row,M,C,P,K,G,B,refresh=self.fixture(work);material,source,review,release=refresh()
            N,reference=self.future_record(work,R,origin,release)
            used=n.workflow_usage(R['usage']+[reference]);self.assertEqual(sum(used.values()),49);self.assertEqual(used['notification-workflow/build'],2);self.assertEqual((21+sum(used.values()),85-sum(used.values())),(70,36))
            with self.assertRaisesRegex(RuntimeError,'lifetime'):n.workflow_build_posttimeout(material,R['usage']+[reference],R,row,source,review,release)
            zero=work/'zero';zero.mkdir();Z,zref=self.future_record(zero,R,origin,dict(release,release_id='synthetic-zero'),0)
            self.assertEqual(sum(n.workflow_usage(R['usage']+[zref]).values()),48)
            R['usage']=R['usage']+[zref]
            self.assertEqual(n.workflow_build_posttimeout(material,R['usage'],R,row)['origin'],M['origin'])
            N['healthy']=True;n.write(reference['path'],N);reference['sha256']=n.sha(reference['path'])
            with self.assertRaises(RuntimeError):n.workflow_usage(R['usage'][:-1]+[reference])

    def test_prospective_validator_progress_and_p_predecessor_with_mocked_current_IO(self):
        import types
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);origin,R,row,M,C,P,K,G,B,refresh=self.fixture(work);material,source,review,release=refresh();real_sha=n.sha;real_resolve=Path.resolve;real_text=Path.read_text
            state=M['state'];logical=Path(M['root']);canonical=Path(M['realroot']);protected={item['path']:item['sha256'] for item in R['protected_files']}
            def relative(path):
                for base in (logical,canonical):
                    if Path(path).is_relative_to(base):return Path(path).relative_to(base).as_posix()
                return None
            def digest(path):
                name=relative(path)
                if name is not None:return state[name]['sha256']
                if str(path) in protected:return protected[str(path)]
                return real_sha(path)
            def resolve(path,*a,**kw):
                name=relative(path)
                return canonical/name if name is not None else real_resolve(path,*a,**kw)
            spec=n.SOURCE/'.omx/ultragoal/evidence/g004/codex/native-v58/runs-notification-workflow-unsolicited-spec-approval-sourcedca-usage65-RELEASE-REQUIRED/approved-spec.md'
            tasks=Path(M['postimages']['docs/changes/2026-10-25-order-confirmation-email-toggle/tasks.md']['path']).read_text()
            def text(path,*a,**kw):
                if str(path)==B['tasks']['path']:return tasks
                if str(path)==B['spec']['path']:return real_text(spec,*a,**kw)
                self.assertIsNone(relative(path),'unexpected current consumer read')
                return real_text(path,*a,**kw)
            args=types.SimpleNamespace(current_author_checkpoint=R['workflow_checkpoint']['path'],current_author_release=str(work/'release.json'),prepared=str(work),out=str(work/'out'),release_id=release['release_id'])
            binding=n.checked_json(release['native_premises']);binding.update(workflow_native_premises_sha256=release['native_premises']['sha256'],workflow_release_sha256=n.sha(work/'release.json'))
            with mock.patch.object(n,'workflow_inventory',return_value=state),mock.patch.object(n,'sha',side_effect=digest),mock.patch.object(Path,'resolve',resolve),mock.patch.object(Path,'read_text',text):
                flow=n.validate_workflow_checkpoint(args,R,row,binding);self.assertTrue(flow['build_posttimeout_handoff']);edit=flow['business_edit']
                after=copy.deepcopy(state);after['tests/test_settings.py']['sha256']='synthetic new verification';self.assertEqual(n.notification_business_delta(edit,state,after)['changed'],['tests/test_settings.py'])
                for path in ('app/settings.py','docs/changes/2026-10-25-order-confirmation-email-toggle/tasks.md','.git/HEAD','tests/unexpected.pyc'):
                    bad=copy.deepcopy(state);bad[path]=dict(bad.get(path,{}),sha256='unexpected')
                    with self.assertRaises(RuntimeError):n.notification_business_delta(edit,state,bad)
                B['tasks_progress']['approved_artifact']=dict(B['tasks_progress']['approved_artifact'],sha256='0'*64);refresh();binding['workflow_release_sha256']=n.sha(work/'release.json')
                with self.assertRaises(RuntimeError):n.validate_workflow_checkpoint(args,R,row,binding)

    def test_subtype_requests_never_consume_or_send_second_USER(self):
        for request in ('queued','queued-terminal','call-fail','event','drain','no-final','build-healthy'):
            with self.subTest(request=request):
                RemainingWorkflowTests().test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_business=True,_request=request,_build=True)

class BuildNativeFinalPhaseTests(unittest.TestCase):
    def retained_native(self):
        path=n.SOURCE/'.omx/ultragoal/evidence/g004/codex/native-v61/runs-notification-workflow-tasks-timeout-approval-sourcee1-usage67-RELEASE-REQUIRED/live-rpc/rpc.json'
        wire=n.checked_json({'path':str(path),'sha256':'912eac2e2b3be41f3d65c441b5a517e5be35a0923bfee8431231f5273fde65ce'})
        final=wire[196]['payload'];commentary=wire[98]['payload']
        self.assertEqual(wire[196]['direction'],'response_or_event');self.assertEqual(final['method'],'item/completed');self.assertEqual(final['params']['item']['type'],'agentMessage');self.assertEqual(final['params']['item']['phase'],'final_answer')
        self.assertEqual(commentary['params']['item']['phase'],'commentary');self.assertTrue(n.healthy_terminal([e['payload'] for e in wire if e['direction']=='response_or_event'],'live'))
        return final,commentary

    def variants(self):
        final,commentary=self.retained_native();result={'native':final,'commentary':commentary}
        for phase in ('final','partial',None):
            item=copy.deepcopy(final);item['params']['item']['phase']=phase;result[str(phase)]=item
        missing=copy.deepcopy(final);missing['params']['item'].pop('phase');result['missing-phase']=missing
        partial=copy.deepcopy(final);partial['method']='item/agentMessage/delta';result['partial-event']=partial
        return result

    def test_retained_native_completed_report_through_fake_live_and_negative_controls(self):
        for kind,event in self.variants().items():
            with self.subTest(kind=kind):
                RemainingWorkflowTests().test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_business=True,_request='build-healthy' if kind=='native' else 'native-invalid',_build=True,_native_final=event)
        final,unused=self.retained_native()
        for request in ('native-unhealthy','event','queued-terminal','drain','no-final'):
            with self.subTest(request=request):
                RemainingWorkflowTests().test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_business=True,_request=request,_build=True,_native_final=final)

    def test_retained_final_is_recognized_by_failed_origin_absence_predicate(self):
        import ast
        final,commentary=self.retained_native();tree=ast.parse(Path(n.__file__).read_text());function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='workflow_build_posttimeout')
        guard=next(node for node in ast.walk(function) if isinstance(node,ast.If) and any(isinstance(child,ast.Constant) and child.value=='HELD original BUILD has no completed terminal/final' for child in ast.walk(node)))
        expression=compile(ast.Expression(guard.test),str(n.__file__),'eval')
        request={'direction':'request','payload':{'method':'turn/start'}}
        self.assertTrue(eval(expression,{'sent':[request],'wire':[request,{'direction':'response_or_event','payload':final}]}))
        self.assertFalse(eval(expression,{'sent':[request],'wire':[request,{'direction':'response_or_event','payload':commentary}]}))
        origin,usage=NotificationBusinessEditTests().actual_v63_history();wire=n.checked_json(origin['wire']);sent=[e for e in wire if e['direction']=='request' and e['payload'].get('method')=='turn/start']
        self.assertFalse(eval(expression,{'sent':sent,'wire':wire}));self.assertFalse(origin['healthy']);self.assertEqual(origin['business_facts'],[])

    def test_complete_historical_N_native_phase_and_rehashed_negative_controls(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);origin,R,row,M,C,P,K,G,B,refresh=BuildPosttimeoutHandoffTests().fixture(work);material,source,review,release=refresh()
            N,reference=BuildPosttimeoutHandoffTests().future_record(work,R,origin,release);initial=copy.deepcopy(M['state']);after=copy.deepcopy(initial)
            body=b'# synthetic close/flush test-only postimage\n';after['tests/test_settings.py']['sha256']=hashlib.sha256(body).hexdigest()
            image=work/'verification-postimage.py';image.write_bytes(body)
            terminal={'method':'turn/completed','params':{'turn':{'status':'completed','error':None}}};start=n.checked_json(N['wire'])[0]
            immutable=n.checked_json(N['facts']['poststart-baseline-v3.json'])['first']
            edit={'data':C,'entries':{item['path']:item for item in C['files']},'directories':set()}
            def put(path,value):n.write(path,value);return {'path':str(path),'sha256':n.sha(path)}
            real_sha=n.sha
            def historical_only(path):
                self.assertFalse(any(str(path)==root or str(path).startswith(root+'/') for root in (origin['root'],origin['realroot'])),'historical consumer hash forbidden')
                return real_sha(path)
            for kind,event in self.variants().items():
                with self.subTest(kind=kind):
                    events=[copy.deepcopy(event),copy.deepcopy(terminal)];wire=[start]+[{'direction':'response_or_event','payload':e} for e in events]
                    wire.extend([{'direction':'request','payload':{'id':92,'method':'config/read','params':{'cwd':N['root']}}},{'direction':'response_or_event','payload':{'id':92,'status':'ok','receipt_schema':n.RECEIPT_VERSION}}])
                    N['wire']=put(work/'new-wire.json',wire);events=[e['payload'] for e in wire if e['direction']=='response_or_event']
                    fact=n.notification_business_delta(edit,initial,after);fact.update(contract=R['business_edit_contract'],events=events,user_history=[{'role':'user','text':row['initial_user_text']}],postimages={'tests/test_settings.py':{'path':str(image),'sha256':n.sha(image)}},wire_start_index=0,wire_end_index=len(wire),process_id=N['process_id'],thread_id=N['thread_id'])
                    N.update(healthy=True,failure=None,state=after,business_facts=[put(work/'new-fact.json',fact)],config_facts={'config-01.json':put(work/'new-config.json',{'schema_version':'workflow-business-bundle-v1','contract':R['business_edit_contract'],'immutable_before':immutable,'immutable_after':immutable,'immutable_stable':True,'business_before':initial,'business_after':after,'business_files_equal':False,'full_observed_files_equal':False,'baseline_reset_allowed':False})})
                    reference=put(work/'new-context.json',N)
                    with mock.patch.object(n,'sha',side_effect=historical_only):
                        if kind=='native':
                            used=n.workflow_usage(R['usage']+[reference]);self.assertEqual(sum(used.values()),49);self.assertEqual(used['notification-workflow/build'],2);self.assertEqual(21+sum(used.values()),70)
                        else:
                            with self.assertRaises(RuntimeError):n.workflow_usage(R['usage']+[reference])
            # Retain valid native final but deny an unhealthy terminal or an unanswered request.
            final,unused=self.retained_native()
            for reason in ('unhealthy','pending'):
                events=[copy.deepcopy(final),copy.deepcopy(terminal)]
                if reason=='unhealthy':events[-1]['params']['turn']['status']='failed'
                else:events.append({'id':'unanswered','method':'item/tool/requestUserInput','params':{'questions':[]}})
                wire=[start]+[{'direction':'response_or_event','payload':e} for e in events];N['wire']=put(work/'new-wire.json',wire)
                fact.update(events=events,wire_end_index=len(wire));N['business_facts']=[put(work/'new-fact.json',fact)];reference=put(work/'new-context.json',N)
                with self.assertRaises(RuntimeError):n.workflow_usage(R['usage']+[reference])
            self.assertFalse(origin['healthy']);self.assertEqual(origin['business_facts'],[])

class BusinessSerializationTests(unittest.TestCase):
    def actual(self):
        e=n.SOURCE/'.omx/ultragoal/evidence';d=e/'g004/codex/native-v64/runs-notification-workflow-build-posttimeout-close-flush-source5ed-usage69-RELEASE-REQUIRED'
        ref={'path':str(d/'workflow-context.json'),'sha256':'a9b07122473f6e2b15f89bd6d4f324641a93f85d85de9d9c54855bbc38e10b30'}
        record=n.checked_json(ref);producer=n.checked_json(record['recipe']);fact=n.checked_json(record['business_facts'][0]);wire=n.checked_json(record['wire']);config=n.checked_json(record['config_facts']['config-01.json'])
        return ref,record,producer,fact,wire,config

    @staticmethod
    def serializers(home):
        import ast,json,re,types
        from pathlib import PurePosixPath
        # Execute current pinned PURE codec definitions only, never module initialization/OUT.
        runtime=ast.parse((n.SOURCE/'tests/runtime/codex/runtime.py').read_text());ar=ast.parse((n.SOURCE/'tests/runtime/codex/activation_recheck.py').read_text())
        clean=next(node for node in runtime.body if isinstance(node,ast.FunctionDef) and node.name=='clean')
        namespace={'json':json,'re':re,'pathlib':types.SimpleNamespace(Path=types.SimpleNamespace(home=lambda:PurePosixPath(home)))}
        exec(compile(ast.Module(body=[clean],type_ignores=[]),'real-runtime-clean','exec'),namespace)
        selected=[node for node in ar.body if (isinstance(node,ast.FunctionDef) and node.name in ('sanitized','write')) or (isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='SENSITIVE' for target in node.targets))]
        exec(compile(ast.Module(body=selected,type_ignores=[]),'real-activation-codecs','exec'),namespace)
        return types.SimpleNamespace(write=namespace['write'],sanitized=namespace['sanitized'])

    def sample_responses(self,home):
        unused,record,producer,fact,wire,config=self.actual();events=[e['payload'] for e in wire[36:428] if e['direction']=='response_or_event']
        raw=fact['events'][385]['structural_result']['layers'][1]['source']['file'];display=events[385]['structural_result']['layers'][1]['source']['file'];suffix=display[len('<HOST_HOME>'):];oldhome=raw[:-len(suffix)]
        def adapt(value):
            if isinstance(value,str):return value.replace(oldhome,str(home))
            if isinstance(value,list):return [adapt(v) for v in value]
            if isinstance(value,dict):return {k:adapt(v) for k,v in value.items()}
            return value
        return [adapt(fact['events'][i]) for i in (385,386,387)]

    def test_actual_v64_full42_and_transition_preserve_original_artifacts(self):
        from unittest import mock
        ref,record,producer,fact,wire,config=self.actual();usage=producer['usage']+[ref]
        # Historical comparison may use captured root pairs, never the current consumer/HOME.
        roots={}
        for item in usage:
            value=n.checked_json(item);roots[value['root']]=value['realroot'];roots[value['realroot']]=value['realroot']
        inside=lambda path:any(str(path)==root or str(path).startswith(root+'/') for root in roots)
        def guard(fn):
            def call(path,*a,**kw):
                self.assertFalse(inside(path),'live consumer read forbidden');return fn(path,*a,**kw)
            return call
        real_resolve=Path.resolve
        def resolve(path,*a,**kw):
            if str(path) in roots:return Path(roots[str(path)])
            self.assertFalse(inside(path),'live business resolution forbidden');return real_resolve(path,*a,**kw)
        with mock.patch.object(Path,'resolve',resolve),mock.patch.object(Path,'read_bytes',guard(Path.read_bytes)),mock.patch.object(Path,'read_text',guard(Path.read_text)),mock.patch.object(Path,'stat',guard(Path.stat)),mock.patch.object(Path,'lstat',guard(Path.lstat)),mock.patch.object(Path,'home',side_effect=AssertionError('current HOME forbidden')):
            used=n.workflow_usage(usage)
            self.assertEqual(sum(used.values()),49);self.assertEqual(used['notification-workflow/build'],2);self.assertEqual((21+sum(used.values()),85-sum(used.values()),106),(70,36,106))
            with tempfile.TemporaryDirectory() as tmp:
                report=Path(tmp)/'synthetic-transition-report.md';report.write_text('TEST ONLY; no actual transition approval')
                review={'business_transition':{'context':ref,'facts':record['business_facts'][-1],'state_sha256':n.canonical_hash(record['state']),'report':{'path':str(report),'sha256':n.sha(report)}}}
                n.notification_business_transition({'workflow_checkpoint':ref},review,record)
        self.assertTrue(record['healthy']);self.assertTrue(record['closed']);self.assertEqual(n.checked_json(producer['usage'][-1])['healthy'],False)

    def test_exact_legacy_relation_covers_events_and_contract_without_lossy_fallback(self):
        ref,record,producer,fact,wire,config=self.actual();events=[e['payload'] for e in wire[36:428] if e['direction']=='response_or_event']
        self.assertNotEqual(fact['events'],events);self.assertNotEqual(config['contract'],fact['contract'])
        self.assertTrue(n.legacy_v64_business_serialization(record,fact,events,config))
        for mutation in ('masked','home','icon','contract','extra-sensitive','id','omit','reorder','interval','before','equal','producer','helper','context','wire','config','baseline'):
            with self.subTest(mutation=mutation):
                r=copy.deepcopy(record);f=copy.deepcopy(fact);w=copy.deepcopy(events);c=copy.deepcopy(config)
                if mutation=='masked':f['events'][385]['structural_result']['safe_identity']['schema']['features']['api_key_model_discovery']='synthetic masked change'
                elif mutation=='home':f['events'][385]['structural_result']['layers'][1]['source']['file']+='-foreign'
                elif mutation=='icon':f['events'][386]['result']['data'][0]['skills'][438]['interface']['iconSmall']+='-foreign'
                elif mutation=='contract':c['contract']['sha256']='0'*64
                elif mutation=='extra-sensitive':f['events'][385]['api_key_new']='synthetic'
                elif mutation=='id':w[385]['id']=777
                elif mutation=='omit':w.pop(387)
                elif mutation=='reorder':w[385],w[387]=w[387],w[385]
                elif mutation=='interval':f['wire_start_index']+=1
                elif mutation=='before':f['before']={}
                elif mutation=='equal':f['business_files_equal']=True
                elif mutation=='producer':r['collector_sha256']='0'*64
                elif mutation=='helper':r['recipe']={'path':r['recipe']['path'],'sha256':'0'*64}
                elif mutation=='context':r['process_id']+=1
                elif mutation=='wire':r['wire']['sha256']='0'*64
                elif mutation=='config':r['config_facts']['config-01.json']['sha256']='0'*64
                elif mutation=='baseline':r['facts']['poststart-baseline-v3.json']['sha256']='0'*64
                self.assertFalse(n.legacy_v64_business_serialization(r,f,w,c))

    def test_strict_v1_and_v2_versions_and_mixed_unknown_denials(self):
        for fact_version,config_version in ((1,1),(2,2),(1,2),(2,1),(3,3)):
            with self.subTest(versions=(fact_version,config_version)),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);record,wire,save,initial=NotificationBusinessEditTests().history_case(work)
                f=n.checked_json(record['business_facts'][0]);f['schema']='workflow-notification-business-observation-v'+str(fact_version);n.write(record['business_facts'][0]['path'],f);record['business_facts'][0]['sha256']=n.sha(record['business_facts'][0]['path'])
                c=n.checked_json(record['config_facts']['config-01.json']);c['schema_version']='workflow-business-bundle-v'+str(config_version);n.write(record['config_facts']['config-01.json']['path'],c);record['config_facts']['config-01.json']['sha256']=n.sha(record['config_facts']['config-01.json']['path'])
                if (fact_version,config_version) in ((1,1),(2,2)):self.assertEqual(n.workflow_usage(save())['notification-workflow/build'],1)
                else:
                    with self.assertRaises(RuntimeError):n.workflow_usage(save())

    def test_actual_event_then_contract_boundary_and_real_future_serializers(self):
        import ast
        unused,record,producer,fact,wire,config=self.actual();events=[e['payload'] for e in wire[36:428] if e['direction']=='response_or_event']
        raw=fact['events'][385]['structural_result']['layers'][1]['source']['file'];display=events[385]['structural_result']['layers'][1]['source']['file'];home=raw[:-len(display[len('<HOST_HOME>'):])]
        codec=self.serializers(home);self.assertEqual(codec.sanitized(fact['events']),events);self.assertEqual(codec.sanitized(fact['contract']),config['contract'])
        tree=ast.parse(Path(n.__file__).read_text());function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='notification_business_history')
        guard=next(node for node in ast.walk(function) if isinstance(node,ast.If) and any(isinstance(value,ast.Constant) and value.value=='HELD historical immutable/business comparison receipt' for value in ast.walk(node)))
        expression=compile(ast.Expression(guard.test),str(n.__file__),'eval')
        namespace={'config':config,'reference':fact['contract'],'current':fact['before'],'after':fact['current'],'baseline':n.checked_json(record['facts']['poststart-baseline-v3.json']),'version':1,'legacy':False}
        self.assertTrue(eval(expression,namespace));namespace['legacy']=True;self.assertFalse(eval(expression,namespace))
        for mode in ('healthy','two','between','config','unstable'):
            with self.subTest(mode=mode):RemainingWorkflowTests().test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_business=True,_business_edit=mode,_serialization=True)
        for timing in ({'at':180},{'late_error':True}):
            with self.subTest(timing=timing):RemainingWorkflowTests().test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_business=True,_business_edit='healthy',_timing=timing,_serialization=True)
        for request in ('queued-terminal','call-fail','event','drain'):
            with self.subTest(request=request):RemainingWorkflowTests().test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_business=True,_request=request,_build=True,_serialization=True)

    def test_rehashed_corpus_cannot_borrow_legacy_even_after_lossy_or_version_conversion(self):
        ref,record,producer,fact,wire,config=self.actual();events=[e['payload'] for e in wire[36:428] if e['direction']=='response_or_event'];release=n.checked_json(record['release'])
        for mutation in ('masked','path','icon','suffix','extra-sensitive','id','omit','duplicate','reorder','interval','user','model','mcp','fingerprint','before','after','changed','equal','contractSHA','contractPath','configB1','self-sanitized','fake-v2'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);r=copy.deepcopy(record);f=copy.deepcopy(fact);c=copy.deepcopy(config);w=copy.deepcopy(wire)
                if mutation=='masked':f['events'][385]['structural_result']['safe_identity']['schema']['features']['api_key_model_discovery']='changed under mask'
                elif mutation in ('path','suffix'):f['events'][386]['result']['data'][0]['skills'][16]['path']+='foreign'
                elif mutation=='icon':f['events'][386]['result']['data'][0]['skills'][438]['interface']['iconLarge']+='foreign'
                elif mutation=='extra-sensitive':f['events'][385]['api_key_extra']='synthetic'
                elif mutation=='id':f['events'][385]['id']=777
                elif mutation=='omit':f['events'].pop(387)
                elif mutation=='duplicate':f['events'].append(f['events'][387])
                elif mutation=='reorder':f['events'][385],f['events'][387]=f['events'][387],f['events'][385]
                elif mutation=='interval':f['wire_start_index']+=1
                elif mutation=='user':f['user_history'][0]['text']='foreign'
                elif mutation=='model':f['events'][385]['structural_result']['safe_identity']['sha256']='0'*64
                elif mutation=='mcp':f['events'][385]['structural_result']['effective']['structure']['mcp_server_names'].append('foreign')
                elif mutation=='fingerprint':f['events'][385]['structural_result']['response_identity']['sha256']='0'*64
                elif mutation=='before':f['before']={}
                elif mutation=='after':f['current']['app/settings.py']['sha256']='0'*64
                elif mutation=='changed':f['changed']=[]
                elif mutation=='equal':f['business_files_equal']=True
                elif mutation=='contractSHA':c['contract']['sha256']='0'*64
                elif mutation=='contractPath':c['contract']['path']+='foreign'
                elif mutation=='configB1':c['immutable_before']['config']['safe_identity']['sha256']='0'*64
                else:
                    f['events']=copy.deepcopy(events);c['contract']=f['contract']
                    if mutation=='fake-v2':f['schema']='workflow-notification-business-observation-v2';c['schema_version']='workflow-business-bundle-v2'
                def put(name,value):
                    path=work/name;n.write(path,value);return {'path':str(path),'sha256':n.sha(path)}
                r['business_facts']=[put('fact.json',f)];r['config_facts']['config-01.json']=put('config.json',c)
                # Pass verified rehashed temporary outputs through the real historical function.
                with self.assertRaises(RuntimeError):n.notification_business_history(r,producer['usage'],w,release)

class SpecClosureComponentTests(unittest.TestCase):
    ROWS=(('codex-default-authentic-preanswer','default','original'),('codex-copy-equivalent-preanswer','copy','original'),('codex-copy-D2-authentic-pre-v57-answer','copy','D2'))

    def fixture(self, work, selected=0, root_override=None):
        import argparse,difflib,json,types
        E=n.SOURCE/'.omx/ultragoal/evidence'
        def ref(path):return {'path':str(path),'sha256':n.sha(path)}
        def save(name,data):p=work/name;n.write(p,data);return ref(p)
        rowid,mode,lin=self.ROWS[selected];root=Path(root_override) if root_override else work/'consumer'
        if root_override is None:root.mkdir()
        supplement=E/'r7-parent-verification/original-preanswer-eleven-byte-archive/MAP-supplement.json';blueprint=E/'postv65-closure-materialization-blueprint/MAP.json';mapping=json.loads(supplement.read_text());line=mapping['lineages'][lin]
        design=E/'spec-approval-closure-repair-design/PLAN.md';paragraph=next(x[2:] for x in design.read_text().splitlines() if x.startswith('> '))
        products=mapping['product_identity_map'];oldref=next(x['old_retained_ref'] for x in products if x['relative_path']=='skills/ains-spec/SKILL.md');old=Path(oldref['path']).read_text();head,tail=old.split('## 5. 承認を得る\n\n');first,rest=tail.split('未決の業務判断をこの要約に混ぜて',1);new=head+'## 5. 承認を得る\n\n'+paragraph+'未決の業務判断をこの要約に混ぜて'+rest
        body=work/'future-body.md';body.write_text(new)
        suite={x['relative_path']:{'sha256':ref(body)['sha256'] if x['relative_path']=='skills/ains-spec/SKILL.md' else x['old_retained_ref']['sha256'],'mode':x['old_mode']} for x in products}
        manifest=save('future-manifest.json',{'release':'SYNTHETIC-ONLY','suite_files':suite,'suite_skill_metadata_sha256':{}})
        diff=work/'future.diff';diff.write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/skills/ains-spec/SKILL.md',tofile='b/skills/ains-spec/SKILL.md')))
        report=work/'review.md';report.write_text('SYNTHETIC external review evidence; no real authority')
        product_review=save('product-review.json',{'schema':'spec-closure-product-review-v1','decision':'APPROVE_EXACT_SECTION5_ONLY','old_manifest':ref(E/'spec-closure-root-baseline/index.json'),'new_manifest':manifest,'diff':ref(diff),'design':ref(design),'report':ref(report)})
        product=save('product.json',{'old_manifest':ref(E/'spec-closure-root-baseline/index.json'),'new_manifest':manifest,'diff':ref(diff),'source_review':product_review,'old_body':oldref,'new_body':ref(body)})
        records=[r for r in mapping['records'] if r['lineage']==lin]
        for r in ([] if root_override else sorted(records,key=lambda x:len(Path(x['relative_path']).parts))):
            target=root/r['relative_path']
            if r['expected']['kind']=='directory':target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body.read_bytes() if r['relative_path']=='.agents/skills/ains-spec/SKILL.md' else Path(r['retained_byte_ref']['path']).read_bytes())
            target.chmod(int(r['expected']['mode'],8))
        lock=SpecClosureInstallerLockTests.model_lock(work,rowid,mode,root,records,products,manifest,ref(body),save,ref(report))
        state=n.workflow_inventory(root);draft=next(r['relative_path'] for r in records if r['expected']['sha256']==line['authentic_preanswer_draft']['sha256'])
        rows=[]
        for r in records:rows.append({'path':r['relative_path'],'source':r['retained_byte_ref'],'historical':r['expected'],'target':state[r['relative_path']],'parent':r['parent_relative'],'alias_group':r['alias_group']})
        bm=save('map.json',{'schema':'spec-closure-business-map-v1','lineage':'original-pre-v39' if lin=='original' else 'D2-pre-v57','witness':line['witness'],'blueprint':ref(blueprint),'supplement':ref(supplement),'records':rows,'absence_assertions':mapping['absence_assertions'][lin],'relocations':{'root':str(root),'realroot':str(root.resolve()),'product':product},'draft_path':draft})
        files={x['relative_path']:{'path':str(root/'.agents'/x['relative_path']),**{k:state['.agents/'+x['relative_path']][k] for k in ('realpath','identity','kind','sha256','mode')}} for x in products}
        bodies={k:files['skills/'+k+'/SKILL.md'] for k in n.MANUAL|n.AUTO};metadata={k:v for k,v in files.items() if k.endswith('/agents/openai.yaml')}
        install_program=save('install-program.json',{'row_id':rowid,'root':str(root),'mode':mode,'manifest':manifest,'files_sha256':n.canonical_hash(files),'report':ref(report),'lock':lock})
        install=save('install.json',{'schema':'spec-closure-install-v1','row_id':rowid,'mode':mode,'root':str(root),'realroot':str(root.resolve()),'manifest':manifest,'files':files,'bodies':bodies,'metadata':metadata,'program':install_program})
        actual=line['actual_final_USER_and_historical_response'];wire=n.checked_json(actual['wire']);payload=wire[36]['payload'];text=payload['params']['input'][0]['text']
        proof=save('actual-USER.json',{'context':actual['context'],'wire_index':36,'payload_sha256':n.canonical_hash(payload),'text':text})
        carry=ref(E/('spec-closure-oracle-carry-budget-review/REPORT.md' if lin=='original' else 'spec-closure-D2-frontier-oracle-addendum-r2/REPORT.md'))
        origin={'oracle':ref(E/('spec-closure-oracle-root-adoption/adoption.json' if lin=='original' else 'spec-closure-D2-oracle-addendum-critic-r1/REPORT.md')),'carry':carry,'witness':line['witness'],'blueprint':ref(blueprint),'supplement':ref(supplement),'question_context':line['preceding_question']['context'],'question_wire':line['preceding_question']['wire'],'preanswer_draft':line['authentic_preanswer_draft'],'actual_USER':proof,'decision_lineage':line.get('history_attestation',carry),'initial_request':ref(E/('spec-closure-oracle-carry-budget-review/coverage.json' if lin=='original' else 'spec-closure-D2-frontier-oracle-addendum-r2/REPORT.md'))}
        material={'schema':'spec-closure-materialization-v1','row_id':rowid,'mode':mode,'lineage':bm and ('original-pre-v39' if lin=='original' else 'D2-pre-v57'),'root':str(root),'realroot':str(root.resolve()),'state':state,'origin':origin,'business_map':bm,'product':product,'install':install}
        material_ref=save('material.json',material);cp={'schema':'workflow-materialization-v1','root':str(root),'realroot':str(root.resolve()),'state':state,'materialization':material_ref};cpref=save('checkpoint.json',cp)
        # Full authentic global history, ending at actual v65 (not just the original branch).
        actual65=E/'g004/codex/native-v65/runs-notification-workflow-build-readonly-handoff-source1249-usage70-RELEASE-REQUIRED/workflow-context.json';last=json.loads(actual65.read_text());producer=n.checked_json(last['recipe']);usage=producer['usage']+[ref(actual65)]
        row={'id':rowid,'mode':mode,'transport':'live','max_user_turns':1,'terminal_deadline_seconds':180,'initial_user_text':text}
        recipe={'execution_kind':'bounded-workflow-v1','purpose':'spec-closure-regression','phase':'closure','unit':'changed-spec','rows':[row],'usage':usage,'workflow_checkpoint':cpref,'release_manifest':manifest['path'],'release_manifest_sha256':manifest['sha256'],'adapter_sha256':n.sha(n.__file__),'helper_imports':[{'path':'tests/runtime/codex/'+x+'.py','sha256':n.sha(n.SOURCE/'tests/runtime/codex'/(x+'.py')),'OUT_assignment_rebound':x=='runtime','function_bodies_changed':False} for x in n.HELPERS],'protected_files':[{'path':str(root/draft),'sha256':state[draft]['sha256']},{'path':str(root/'skills-lock.json'),'sha256':state['skills-lock.json']['sha256']}]}
        args=argparse.Namespace(current_author_checkpoint=str(work/'checkpoint.json'),current_author_release=str(work/'release.json'),setup_checkpoint=None,setup_checkpoint_review=None,derivative_release=None,packet=None,prepared=str(work),out=str(work/'out'),release_id='synthetic-'+rowid)
        # Relocate the retained actual0.164 response shape; no ApiConfig defaults invented.
        actual_response=n.checked_json(last['facts']['thread-start-v3.json'])['response'];oldroots=(last['realroot'],last['root'])
        def relocate(value):
            if isinstance(value,str):
                for oldroot in oldroots:value=value.replace(oldroot,str(root))
                return value
            if isinstance(value,list):return [relocate(v) for v in value]
            if isinstance(value,dict):return {k:relocate(v) for k,v in value.items()}
            return value
        expected={k:relocate(actual_response[k]) for k in n.THREAD_FIELDS}
        expected['instructionSources']=[str(root/name) for name in ('AGENTS.md','CLAUDE.md') if name in state]
        binding={'transports':['live'],'forward_thread_expectation':expected,'setup_artifact_contract':None,'official_commit':n.SEMANTIC_COMMIT,'proof_sha256':n.sha(report),'parent_release_id':args.release_id,'executable_identity':{'sha256':'synthetic-binary'}}
        native=save('native.json',binding);binding['workflow_native_premises_sha256']=native['sha256']
        def refresh():
            nonlocal native
            binding['parent_release_id']=args.release_id
            native=save('native.json',{k:v for k,v in binding.items() if k not in ('workflow_native_premises_sha256','workflow_release_sha256')});binding['workflow_native_premises_sha256']=native['sha256']
            n.write(work/'recipe.json',recipe)
            common={'checkpoint_sha256':recipe['workflow_checkpoint']['sha256'],'recipe_sha256':n.sha(work/'recipe.json'),'collector_sha256':recipe['adapter_sha256'],'helpers':recipe['helper_imports'],'manifest_sha256':manifest['sha256'],'native_premises_sha256':native['sha256'],'purpose':recipe['purpose'],'phase':recipe['phase'],'unit':recipe['unit']}
            source=save('source.json',dict(common,schema='WORKFLOW_SOURCE_REVIEW_V1',decision='APPROVE_EXACT_BOUND_CONTEXT',report=ref(report)))
            authority=[material_ref,product_review,install_program,origin['oracle'],lock]+[x for x in recipe['usage'] if n.checked_json(x)['unit']=='changed-spec']
            review=save('Root.json',dict(common,schema='WORKFLOW_ROOT_REVIEW_V1',decision='APPROVE_EXACT_BOUND_CONTEXT',report=ref(report),source_review=source,state_sha256=n.canonical_hash(state),usage_sha256=n.canonical_hash(recipe['usage']),authority_evidence=authority,business={'closure_materialization':material_ref}))
            used=n.workflow_usage(recipe['usage']);allocation=save('allocation.json',{'actual_anchor':21,'held_anchor':85,'whole':106,'required':84,'reserve':1,'evidence':ref(report)})
            release=dict(common,schema='WORKFLOW_RELEASE_V1',release_id=args.release_id,source_review=source,root_review=review,native_premises=native,allocation=allocation,root=str(root),realroot=str(root.resolve()),row_id=rowid,out=str((work/'out').resolve()),max_new_contexts=1,max_new_model_USER_turns=1,seconds=180,actual_before=21+sum(used.values()),held_before=85-sum(used.values()),whole=106,initial_USER_sha256=n.canonical_hash(text))
            n.write(work/'release.json',release);binding['workflow_release_sha256']=n.sha(work/'release.json')
            return release
        return args,recipe,row,binding,material,refresh,save,draft

    def test_three_fixed_rows_and_samefile_donor_boundaries(self):
        for ident,mode,lin in self.ROWS:
            recipe={'purpose':'spec-closure-regression','phase':'closure','unit':'changed-spec'};row={'id':ident,'mode':mode,'transport':'live','max_user_turns':1,'terminal_deadline_seconds':180}
            self.assertEqual(n.workflow_limits(recipe,row,{}),1)
            for change in ({'id':'alias'},{'mode':'default' if mode=='copy' else 'copy'},{'max_user_turns':True},{'terminal_deadline_seconds':360}):
                with self.assertRaises(RuntimeError):n.workflow_limits(recipe,{**row,**change},{})
        self.assertEqual(n.workflow_ceiling('setup-observe','setup-observe','setup-samefile'),1)
        with tempfile.TemporaryDirectory() as tmp:
            refs=RemainingWorkflowTests().budget_usage_fixture(Path(tmp),[('setup-observe','setup-observe','setup-samefile',1,4,False)])
            self.assertEqual(n.workflow_usage(refs)['setup-samefile/setup-observe'],1)
            with self.assertRaises(RuntimeError):n.workflow_limits({'purpose':'setup-observe','phase':'setup-observe','unit':'setup-samefile'},{'mode':'copy','transport':'live','max_user_turns':1,'terminal_deadline_seconds':180},n.workflow_usage(refs))

    def test_actual_origin_materialization_all_three_real_incoming_guards(self):
        for selected in range(3):
            with self.subTest(row=selected),tempfile.TemporaryDirectory() as tmp:
                args,recipe,row,binding,material,refresh,save,draft=self.fixture(Path(tmp),selected);refresh()
                flow=n.validate_workflow_checkpoint(args,recipe,row,binding)
                self.assertEqual(flow['spec_closure']['draft_path'],draft);self.assertEqual(sum(flow['used'].values()),50)
                self.assertEqual(flow['used']['notification-workflow/build'],3)

    def test_rehashed_wrong_lineage_product_install_map_and_current_guards_deny(self):
        for mutation in ('USER','origin','terminal-draft','product','map','install','source','Root','native','protected','extra','alias','status','mode'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);args,r,row,b,m,refresh,save,draft=self.fixture(work,2);refresh()
                if mutation=='USER':row['initial_user_text']+=' suffix';refresh()
                elif mutation=='origin':m['origin']['actual_USER']=m['origin']['question_context'];r['workflow_checkpoint']=save('checkpoint.json',{**n.checked_json(r['workflow_checkpoint']),'materialization':save('material.json',m)});refresh()
                elif mutation=='terminal-draft':(work/'consumer'/draft).write_text('---\nstatus: approved\n---\nforged')
                elif mutation in ('product','map','install'):
                    key='business_map' if mutation=='map' else mutation;doc=n.checked_json(m[key]);doc['foreign']='unbound';m[key]=save(mutation+'.json',doc);r['workflow_checkpoint']=save('checkpoint.json',{**n.checked_json(r['workflow_checkpoint']),'materialization':save('material.json',m)});refresh()
                elif mutation in ('source','Root'):(work/(mutation+'.json')).write_text('{}')
                elif mutation=='native':b['forward_thread_expectation']['model']='foreign'
                elif mutation=='protected':r['protected_files'][0]['sha256']='0'*64;refresh()
                elif mutation=='extra':(work/'consumer/foreign.pyc').write_bytes(b'x')
                elif mutation=='alias':(work/'consumer/escape').symlink_to(work)
                elif mutation=='status':(work/'consumer'/draft).write_text('---\nstatus: approved\n---\n')
                elif mutation=='mode':row['mode']='default';refresh()
                with self.assertRaises((RuntimeError,KeyError,ValueError)):n.validate_workflow_checkpoint(args,r,row,b)

    def retain(self, work, args, recipe, row, binding, material, healthy=False, count=1, home=None):
        import json
        release=n.checked_json({'path':args.current_author_release,'sha256':n.sha(args.current_author_release)})
        out=Path(args.out).resolve();(out/'live-rpc').mkdir(parents=True)
        codec=BusinessSerializationTests.serializers(home) if home else None
        def save(name,data):p=out/name;(codec.write if codec else n.write)(p,data);return {'path':str(p),'sha256':n.sha(p)}
        thread='synthetic-thread';pid=123;state=n.workflow_inventory(Path(material['root'])) if healthy else copy.deepcopy(material['state']);wire=[];facts={};cfg={};scope={}
        def emit(direction,payload):
            wire.append({'direction':direction,'payload':copy.deepcopy(payload),'wire_index':len(wire),'monotonic_ns':len(wire)*1_000_000})
        def call(method,params,result):
            index=len(wire);ident=index+1;emit('request',{'id':ident,'method':method,'params':params})
            emit('response_or_event',{'id':ident,'status':'ok','receipt_schema':n.RECEIPT_VERSION,'structural_result':result} if method=='config/read' else {'id':ident,'result':result})
            return index,len(wire)
        call('initialize',{'clientInfo':{'name':'SYNTHETIC','version':'2'}},{})
        emit('request',{'method':'initialized'})
        E=n.SOURCE/'.omx/ultragoal/evidence';actual65=E/'g004/codex/native-v65/runs-notification-workflow-build-readonly-handoff-source1249-usage70-RELEASE-REQUIRED/workflow-context.json'
        actual=n.checked_json({'path':str(actual65),'sha256':n.sha(actual65)});template=copy.deepcopy(n.checked_json(actual['facts']['poststart-baseline-v3.json'])['first'])
        install=n.checked_json(material['install']);installed=[]
        for name,body in sorted(install['bodies'].items()):
            metadata=install['metadata'].get('skills/'+name+'/agents/openai.yaml');installed.append({'name':name,'path':body['path'],'realpath':body['realpath'],'sha256':body['sha256'],'source_sha256':body['sha256'],'metadata_sha256':metadata['sha256'] if metadata else None,'source_metadata_sha256':metadata['sha256'] if metadata else None})
        config_facts=template['config'];catalog={'data':[{'cwd':material['root'],'errors':[],'skills':[{'name':v['name'],'path':v['path'],'enabled':True} for v in installed]}]}
        environment=template['environment']
        if home:environment['identity_sha256']['HOME']=hashlib.sha256(home.encode()).hexdigest()
        self.assertFalse(environment['selected_environment_file']['exists'])
        frame=copy.deepcopy(template);frame.update(process_id=pid,thread_id=None,installed=installed,catalog=catalog,manifest_sha256=recipe['release_manifest_sha256'],binary_sha256=binding['executable_identity']['sha256'])
        frame['catalog_proof']=n.validate_catalog(catalog,installed,config_facts,'live')
        native_start=len(wire);call('config/read',{'includeLayers':True,'cwd':material['root']},config_facts);call('skills/list',{'cwds':[material['root']],'forceReload':True},catalog)
        native=n.native_selection_receipt(binding,frame['catalog_proof'],n.require_environment(environment,binding),'live');native['closure_wire']={'schema':'spec-closure-native-wire-v1','wire_start_index':native_start,'wire_end_index':len(wire)}
        facts['live-native-selection-receipt.json']=save('live-native-selection-receipt.json',native)
        def bundle(phase,identity,observed):
            start=len(wire);call('config/read',{'includeLayers':True,'cwd':material['root']},config_facts);call('skills/list',{'cwds':[material['root']],'forceReload':True},catalog);call('config/read',{'includeLayers':True,'cwd':material['root']},config_facts)
            fr=copy.deepcopy(frame);fr['thread_id']=None if phase=='preflight' else thread
            frame_name='workflow-closure-bundle-%03d.json'%identity;frame_ref=save(frame_name,fr);scope[frame_name]=frame_ref
            sample_name='workflow-closure-sample-%03d.json'%identity;scope[sample_name]=save(sample_name,{'schema':'spec-closure-sample-v2','bundle_id':identity,'phase':phase,'frame':frame_ref,'before':observed,'after':observed,'stable':True,'process_id':pid,'thread_id':fr['thread_id'],'wire_start_index':start,'wire_end_index':len(wire)})
            return fr
        if count:
            bundle('preflight',0,material['state'])
            request={'cwd':material['root'],'model':binding['forward_thread_expectation']['model'],'approvalPolicy':'never','sandbox':'workspace-write','ephemeral':True}
            response=copy.deepcopy(n.checked_json(actual['facts']['thread-start-v3.json'])['response']);response.update(copy.deepcopy(binding['forward_thread_expectation']));response['thread']=dict(response['thread'],id=thread,**{k:response[k] for k in ('cwd','model','modelProvider','reasoningEffort')})
            ts,te=call('thread/start',request,response)
            facts['thread-start-v3.json']=save('thread-start-v3.json',{'schema_version':n.RECEIPT_VERSION,'process_id':pid,'request':request,'response':response,'wire_start_index':ts,'wire_end_index':te})
            one=bundle('post-start-1',1,material['state']);two=bundle('post-start-2',2,material['state'])
            facts['poststart-baseline-v3.json']=save('poststart-baseline-v3.json',{'schema_version':n.RECEIPT_VERSION,'first':one,'second':two,'snapshot':n.reconcile_thread(response,request,binding['forward_thread_expectation']),'wire_end_index':len(wire),'relation':'SYNTHETIC finite retained observations'})
            pre=bundle('predispatch',3,material['state']);facts['before-config-01-v3.json']=save('before-config-01-v3.json',pre);turn_start=len(wire)
            call('turn/start',{'threadId':thread,'input':[{'type':'text','text':row['initial_user_text']}]},{'turn':{'id':'t','items':[],'status':'inProgress','error':None}})
            if healthy:
                emit('response_or_event',{'method':'turn/started','params':{'threadId':thread,'turn':{'id':'t','items':[],'status':'inProgress','error':None}}})
                emit('response_or_event',{'method':'item/completed','params':{'threadId':thread,'turnId':'t','completedAtMs':3,'item':{'type':'agentMessage','id':'final','phase':'final_answer','text':'SYNTHETIC final; semantic oracle external'}}})
                emit('response_or_event',{'method':'turn/completed','params':{'threadId':thread,'turn':{'id':'t','status':'completed','error':None}}})
                post=bundle('postterminal',4,state)
                cfg['config-01.json']=save('config-01.json',{'schema_version':n.RECEIPT_VERSION,'before':pre,'after':post,'raw_stable':pre==post,'baseline_reset_allowed':False,'projection_used':False})
                facts['turn-01.json']=save('turn-01.json',{'text':row['initial_user_text'],'thread':thread,'seconds':190,'wire_start_index':turn_start,'wire_end_index':len(wire),'events':[e['payload'] for e in wire[turn_start:] if e['direction']=='response_or_event']})
                draft=n.checked_json(material['business_map'])['draft_path'];image=out/'draft.md';image.write_bytes((Path(material['root'])/draft).read_bytes());state[draft]['sha256']=n.sha(image)
                scope['workflow-closure-postimage.json']=save('workflow-closure-postimage.json',{'schema':'spec-closure-postimage-v1','draft':draft,'state_sha256':n.canonical_hash(state),'postimage':{'path':str(image),'sha256':n.sha(image)},'before':material['state'],'after':state,'business_PASS':False})
        wire_ref=save('live-rpc/rpc.json',wire);facts['live-rpc/closed.json']=save('live-rpc/closed.json',{'stable':True,'environment_after':environment})
        record={'schema':'workflow-context-v1','purpose':recipe['purpose'],'phase':recipe['phase'],'unit':recipe['unit'],'root':material['root'],'realroot':material['realroot'],'state':state,'closed':True,'server_returncode':0,'healthy':healthy,'failure':None if healthy else 'synthetic timeout' if count else 'synthetic concrete pre-model gap','release_id':args.release_id,'release':{'path':args.current_author_release,'sha256':n.sha(args.current_author_release)},'prior_usage_sha256':n.canonical_hash(recipe['usage']),'wire':wire_ref,'recipe':{'path':str(work/'recipe.json'),'sha256':n.sha(work/'recipe.json')},'collector_sha256':recipe['adapter_sha256'],'process_id':pid,'thread_id':thread if count else None,'facts':facts,'config_facts':cfg,'scope_facts':scope,'row_id':row['id'],'mode':row['mode']}
        return save('context.json',record),record,save

    def test_full43_and_three_distinct_rows_failures_charge_and_lifetime_replay_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            W=Path(tmp);history=None
            for selected in (1,2,0):
                w=W/str(selected);w.mkdir();args,r,row,b,m,refresh,save,draft=self.fixture(w,selected)
                if history is not None:r['usage']=history
                refresh();n.validate_workflow_checkpoint(args,r,row,b)
                reference,record,write=self.retain(w,args,r,row,b,m,healthy=selected!=2)
                history=r['usage']+[reference];used=n.workflow_usage(history)
                self.assertEqual(used['changed-spec/closure'],len(history)-43)
                self.assertEqual(used['notification-workflow/build'],3)
            self.assertEqual((21+sum(used.values()),85-sum(used.values()),106),(74,32,106))
            # Same row cannot be resurrected by another root/source/release, even after timeout.
            w=W/'replay';w.mkdir();args,r,row,b,m,refresh,save,draft=self.fixture(w,2);r['usage']=history
            refresh()
            with self.assertRaises(RuntimeError):n.validate_workflow_checkpoint(args,r,row,b)
            wire_bytes=Path(n.checked_json(history[-1])['wire']['path']).read_bytes();turn_bytes=Path(n.checked_json(history[-1])['facts']['turn-01.json']['path']).read_bytes()
            for mutation in ('omitted','reordered','forked','row','USER','native','health','mode','config','interval','producer'):
                reference=history[-1];record=n.checked_json(reference);wrong=copy.deepcopy(record)
                if mutation=='omitted':bad=history[:-2]+history[-1:]
                elif mutation=='reordered':bad=history[:-2]+[history[-1],history[-2]]
                elif mutation=='forked':wrong['prior_usage_sha256']='0'*64
                elif mutation=='row':wrong['row_id']=self.ROWS[1][0]
                elif mutation=='USER':v=n.checked_json(wrong['wire']);v[next(i for i,e in enumerate(v) if e.get('payload',{}).get('method')=='turn/start')]['payload']['params']['input'][0]['text']+=' forged';wrong['wire']=write('live-rpc/rpc.json',v)
                elif mutation=='native':wrong['facts']['live-native-selection-receipt.json']=save('wrongnative.json',{'status':'unknown'})
                elif mutation=='health':wrong['healthy']=True;wrong['state']={}
                elif mutation=='mode':wrong['mode']='copy'
                elif mutation=='config':wrong['config_facts']['config-01.json']=save('wrongconfig.json',{})
                elif mutation=='interval':v=n.checked_json(wrong['facts']['turn-01.json']);v['wire_end_index']-=1;wrong['facts']['turn-01.json']=write('turn-01.json',v)
                elif mutation=='producer':wrong['collector_sha256']='0'*64
                if mutation not in ('omitted','reordered'):bad=history[:-1]+[save('wrongcontext.json',wrong)]
                with self.subTest(mutation=mutation),self.assertRaises((RuntimeError,KeyError)):n.workflow_usage(bad)
                Path(record['wire']['path']).write_bytes(wire_bytes);Path(record['facts']['turn-01.json']['path']).write_bytes(turn_bytes)

    def test_complete_zero_hold_new_release_correction_and_failed_consumption(self):
        with tempfile.TemporaryDirectory() as tmp:
            W=Path(tmp);a=W/'first';a.mkdir();args,r,row,b,m,refresh,save,draft=self.fixture(a);refresh()
            zero,rec,write=self.retain(a,args,r,row,b,m,count=0);used=n.workflow_usage(r['usage']+[zero]);self.assertEqual(used['changed-spec/closure'],0);self.assertEqual(sum(used.values()),50)
            # Current same-root state and source are rebound under a new exact release; no reinstall/reset.
            prefix=r['usage']+[zero];second=W/'second';second.mkdir();same=Path(m['root'])
            args,r,row,b,m,refresh,save,draft=self.fixture(second,root_override=same);r['usage']=prefix;args.release_id+='-corrected';refresh();n.validate_workflow_checkpoint(args,r,row,b)
            reference,failed,write=self.retain(second,args,r,row,b,m,count=1);history=r['usage']+[reference]
            self.assertEqual(n.workflow_usage(history)['changed-spec/closure'],1)
            third=W/'third';third.mkdir();args,r,row,b,m,refresh,save,draft=self.fixture(third,root_override=same);r['usage']=history;args.release_id+='-not-a-retry';refresh()
            with self.assertRaises(RuntimeError):n.validate_workflow_checkpoint(args,r,row,b)

    def test_empty_or_truncated_zero_wire_is_not_complete_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Path(tmp);a,r,row,b,m,refresh,save,d=self.fixture(w);refresh();ref,record,write=self.retain(w,a,r,row,b,m,count=0)
            original=n.checked_json(record['wire'])
            for cut in (0,1,2):
                altered=copy.deepcopy(record);altered['wire']=write('live-rpc/rpc.json',original[:cut]);bad=write('truncated-context.json',altered)
                with self.subTest(cut=cut),self.assertRaises(RuntimeError):n.workflow_usage(r['usage']+[bad])
            write('live-rpc/rpc.json',original)

    def test_draft_evolution_canonical_role_and_immutable_scope_collisions(self):
        for role in ('draft','canonical','atomic','cache','approved','collision','unstable'):
            with self.subTest(role=role):RemainingWorkflowTests().test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_business=True,_request='build-healthy',_build=True,_closure=role)

    def test_healthy_scope_receipt_rehashed_false_before_or_PASS_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Path(tmp);a,r,row,b,m,refresh,save,d=self.fixture(w);refresh();ref,record,write=self.retain(w,a,r,row,b,m,healthy=True)
            key='workflow-closure-postimage.json';original=n.checked_json(record['scope_facts'][key])
            for mutation in ('before','after','business_PASS'):
                doc=copy.deepcopy(original);doc[mutation]=True if mutation=='business_PASS' else {}
                altered=copy.deepcopy(record);altered['scope_facts'][key]=write(key,doc);bad=write('mutated-context.json',altered)
                with self.subTest(mutation=mutation),self.assertRaises(RuntimeError):n.workflow_usage(r['usage']+[bad])
            write(key,original)

    def test_named_draft_atomic_replacement_retains_actual_identity_without_alias_waiver(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Path(tmp);a,r,row,b,m,refresh,save,d=self.fixture(w);refresh();n.validate_workflow_checkpoint(a,r,row,b)
            draft=Path(m['root'])/d;stage=draft.with_name('stage.tmp');stage.write_bytes(draft.read_bytes()+b'\nSYNTHETIC observed draft update\n');stage.chmod(0o644);stage.replace(draft)
            ref,record,write=self.retain(w,a,r,row,b,m,healthy=True)
            self.assertNotEqual(record['state'][d]['identity'],m['state'][d]['identity'])
            self.assertEqual(n.workflow_usage(r['usage']+[ref])['changed-spec/closure'],1)
            # A claimed alias to another protected record is not an atomic edit.
            bad=copy.deepcopy(record);bad['state'][d]['identity']=bad['state']['app/settings.py']['identity']
            with self.assertRaises(RuntimeError):n.workflow_usage(r['usage']+[write('alias-context.json',bad)])

    def test_closure_structured_requests_never_read_second_USER(self):
        for request in ('queued','queued-terminal','call-fail','event','drain','build-healthy'):
            with self.subTest(request=request):RemainingWorkflowTests().test_new_setup_dispatch_closes_before_ack_without_copy_init_install_or_resume(_business=True,_request=request,_build=True,_closure=True)

class SpecClosureHistoryR1Tests(unittest.TestCase):
    def fixture(self, work):
        case=SpecClosureComponentTests();a,r,row,b,m,refresh,save,d=case.fixture(work);release=refresh();n.validate_workflow_checkpoint(a,r,row,b)
        ref,record,write=case.retain(work,a,r,row,b,m,healthy=True)
        self.assertEqual(n.workflow_usage(r['usage']+[ref])['changed-spec/closure'],1)
        return case,a,r,row,b,m,release,record,write

    def test_actual_run_row_emits_five_wire_bound_bundles_with_real_live_bundle(self, _ownership=None, _home=None, _final='SYNTHETIC observed output; no semantic PASS', _omit_final=False, _expect_hold=False):
        import contextlib,io,json,types,time
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            w=Path(tmp);case=SpecClosureComponentTests();a,r,row,b,m,refresh,save,d=case.fixture(w)
            captured_home=str(w/'fake-home')
            if _home in ('instruction','both'):
                hp=w/'fake-home/.codex/AGENTS.md';hp.parent.mkdir(parents=True);hp.write_text('SYNTHETIC global instructions');b['forward_thread_expectation']['instructionSources'].append(str(hp))
            sandbox_home=None
            if _home in ('sandbox','both','sandbox-exact','sandbox-repeated','sandbox-embedded','sandbox-literal'):
                sandbox_home={'sandbox-exact':captured_home,'sandbox-repeated':captured_home+'/nested'+captured_home+'/sandbox','sandbox-embedded':str(w/'outer')+captured_home+'/sandbox','sandbox-literal':str(w/'<HOST_HOME>')+captured_home+'/sandbox'}.get(_home,captured_home+'/sandbox')
                Path(sandbox_home).mkdir(parents=True,exist_ok=True);b['forward_thread_expectation']['sandbox']['writableRoots']=[sandbox_home]
            binary=w/'fake-binary';binary.write_text('SYNTHETIC ONLY; never executed')
            b.update(codex_version='synthetic',scope='configured-native-selector',proof_path=str(w/'review.md'),proof_sha256=n.sha(w/'review.md'),forward_trust_root=m['root'],executable_identity={'sha256':n.sha(binary),'symlink_target':str(binary)})
            refresh();a.native_binding=str(w/'binding.json');a.row=row['id'];n.write(a.native_binding,b)
            install=n.checked_json(m['install']);installed=[]
            for name,body in sorted(install['bodies'].items()):
                meta=install['metadata'].get('skills/'+name+'/agents/openai.yaml');installed.append({'name':name,'path':body['path'],'realpath':body['realpath'],'sha256':body['sha256'],'source_sha256':body['sha256'],'metadata_sha256':meta['sha256'] if meta else None,'source_metadata_sha256':meta['sha256'] if meta else None})
            r['checkpoint_installed']=copy.deepcopy(installed);refresh();n.write(a.native_binding,b)
            raw={'config':{'features':{**{k:False for k in n.CANONICAL_FEATURES},**{k:False for k in n.DISCOVERY_KEYS}},'skills':{'include_instructions':True}},'layers':[]}
            if sandbox_home is not None:raw['config']['sandbox_workspace_write']={'writable_roots':[sandbox_home],'network_access':False}
            raw['layers']=[{'name':{'type':'sessionFlags'},'version':'synthetic','config':copy.deepcopy(raw['config'])}]
            catalog={'data':[{'cwd':m['root'],'errors':[],'skills':[{'name':v['name'],'path':v['path'],'enabled':True} for v in installed]}]}
            environment={'identity_sha256':{'HOME':hashlib.sha256(captured_home.encode()).hexdigest()},'selector_names':[],'default_home':True,'default_codex_home':True,'selected_environment_file':{'path':'<HOST_HOME>/.codex/environments.toml','realpath':'<HOST_HOME>/.codex/environments.toml','exists':False,'sha256':None}}
            codec=BusinessSerializationTests.serializers(str(w/'fake-home'));sent=[];instances=[]
            class RPC:
                def __init__(self,sink):
                    self.sink=Path(sink);self.sink.mkdir();self.log=[];self.events=[];self.env={};self.selected_environment=n.require_environment(environment,b);self.args=[str(binary)];self.bound_thread=None;self.closed=False;self.p=types.SimpleNamespace(pid=555,poll=lambda:0 if self.closed else None);self.seq=0;self.queue=[];instances.append(self)
                    self.call('initialize',{'clientInfo':{'name':'synthetic','version':'2'}});self.emit('request',{'method':'initialized'})
                def emit(self,direction,payload):self.log.append({'direction':direction,'payload':copy.deepcopy(payload),'wire_index':len(self.log),'monotonic_ns':time.monotonic_ns()})
                def call(self,method,params,timeout=30):
                    self.seq+=1;ident=self.seq;self.emit('request',{'id':ident,'method':method,'params':params})
                    if method=='initialize':result={}
                    elif method=='config/read':result=raw
                    elif method=='skills/list':result=catalog
                    elif method=='thread/start':
                        result=copy.deepcopy(b['forward_thread_expectation']);result['thread']={'id':'producer-thread',**{k:result[k] for k in ('cwd','model','modelProvider','reasoningEffort')}}
                    elif method=='turn/start':
                        sent.append(params['input'][0]['text']);result={'turn':{'id':'producer-turn','items':[],'status':'inProgress','error':None}}
                        self.queue=[{'method':'turn/started','params':{'threadId':'producer-thread','turn':{'id':'producer-turn','status':'inProgress','error':None}}},{'method':'item/completed','params':{'threadId':'producer-thread','turnId':'producer-turn','item':{'id':'final','type':'agentMessage','phase':'final_answer','text':'SYNTHETIC observed output; no semantic PASS'}}},{'method':'turn/completed','params':{'threadId':'producer-thread','turn':{'id':'producer-turn','status':'completed','error':None}}}]
                    else:raise AssertionError('unexpected RPC')
                    if method=='turn/start' and _ownership=='returned-turn':result['turn']['id']='foreign-turn'
                    if method=='turn/start' and _ownership=='foreign-terminal':self.queue[-1]['params']['threadId']='foreign-thread'
                    if method=='turn/start':
                        self.queue[1]['params']['item']['text']=_final
                        if _omit_final:self.queue[1]['params']['item'].pop('text')
                    projected={'id':ident,'status':'ok','receipt_schema':n.RECEIPT_VERSION,'structural_result':n.config_facts(result,lambda c:{})} if method=='config/read' else {'id':ident,'result':n.redacted_config(result)}
                    self.emit('response_or_event',projected);return copy.deepcopy(result)
                def next(self,deadline):event=self.queue.pop(0);self.emit('response_or_event',event);return event
                def close(self):self.closed=True;codec.write(self.sink/'rpc.json',self.log);codec.write(self.sink/'closed.json',{'stable':True,'environment_after':environment})
            runtime=types.SimpleNamespace(snapshot=lambda root:{})
            activation=types.SimpleNamespace(probe=lambda root:{'files':{},'all_layer_mcp_names':[]},inventory=lambda root:copy.deepcopy(installed),mdm_forced=lambda:{'synthetic':False},CANONICAL=n.CANONICAL_FEATURES)
            helpers={'runtime':runtime,'activation_recheck':codec,'activation_r3':activation,'activation_closure_probe':types.SimpleNamespace(structural=lambda c:{})}
            approval={'role':'user','action':'approve_bounded_workflow_context','new_context':True,'checkpoint_sha256':r['workflow_checkpoint']['sha256'],'release_sha256':n.sha(a.current_author_release),'text':'SYNTHETIC only'}
            stream=io.StringIO(json.dumps(approval)+'\n'+json.dumps({'text':row['initial_user_text']})+'\n'+json.dumps({'text':'MUST STAY UNREAD'})+'\n')
            # Only unrelated launch/source/startup premises are isolated. The property under
            # proof uses real checkpoint/native/config/catalog/reconcile/live_bundle/history.
            with mock.patch.object(n,'released_source'),mock.patch.object(n,'bound_helpers',return_value=contextlib.nullcontext((helpers,[]))),mock.patch.object(n.subprocess,'run',return_value=types.SimpleNamespace(stdout='synthetic',returncode=0)),mock.patch.object(n,'recorded_rpc',side_effect=lambda rt,ar,root,overrides,sink,binding:RPC(sink)),mock.patch.object(n,'environment_facts',return_value=environment),mock.patch.object(n,'validate_startup',return_value='synthetic unrelated startup premise'),mock.patch.object(Path,'home',return_value=w/'fake-home'),mock.patch.object(n.sys,'stdin',stream),mock.patch('builtins.print'):
                if _ownership or _expect_hold:
                    with self.assertRaises(RuntimeError):n.run_row(a)
                else:n.run_row(a)
            self.assertEqual(sent,[row['initial_user_text']]);self.assertEqual(json.loads(stream.readline()),{'text':'MUST STAY UNREAD'});self.assertTrue(all(x.closed for x in instances))
            path=Path(a.out).resolve()/'workflow-context.json';record=n.checked_json({'path':str(path),'sha256':n.sha(path)})
            self.assertEqual(record['healthy'],not (_ownership or _expect_hold));self.assertEqual(n.workflow_usage(r['usage']+[{'path':str(path),'sha256':n.sha(path)}])['changed-spec/closure'],1)
            samples=[n.checked_json(record['scope_facts']['workflow-closure-sample-%03d.json'%i]) for i in range(5)]
            self.assertEqual([v['phase'] for v in samples],['preflight','post-start-1','post-start-2','predispatch','postterminal']);self.assertTrue(all(v['wire_start_index']<v['wire_end_index'] for v in samples))

    def test_live_sandbox_only_HOME_roundtrip_and_instruction_controls(self):
        for home in ('sandbox','instruction','both','sandbox-exact','sandbox-repeated','sandbox-embedded','sandbox-literal'):
            with self.subTest(home=home):self.test_actual_run_row_emits_five_wire_bound_bundles_with_real_live_bundle(_home=home)

    def test_live_ineligible_final_text_is_failed_charged_and_next_USER_unread(self):
        for text in ('',' \t\n',None,1,[]):
            with self.subTest(text=text):self.test_actual_run_row_emits_five_wire_bound_bundles_with_real_live_bundle(_final=text,_expect_hold=True)
        self.test_actual_run_row_emits_five_wire_bound_bundles_with_real_live_bundle(_omit_final=True,_expect_hold=True)

    def test_nested_sandbox_HOME_requires_digest_and_unique_candidate(self):
        for mutation in ('wrong-digest','conflicting-candidate'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);case=SpecClosureComponentTests();a,r,row,b,m,refresh,save,d=case.fixture(work)
                home=str(work/'captured-home');other=str(work/'another-home')
                b['forward_thread_expectation']['sandbox']['writableRoots']=[home+'/sandbox',other+'/sandbox'];refresh()
                ref,record,write=case.retain(work,a,r,row,b,m,healthy=True,home=home)
                self.assertEqual(n.workflow_usage(r['usage']+[ref])['changed-spec/closure'],1)
                if mutation=='wrong-digest':
                    closed=n.checked_json(record['facts']['live-rpc/closed.json']);closed['environment_after']['identity_sha256']['HOME']='0'*64
                    record['facts']['live-rpc/closed.json']=write('live-rpc/closed.json',closed);reason='historical HOME identity'
                else:
                    thread=n.checked_json(record['facts']['thread-start-v3.json']);pair=n.checked_json(record['facts']['poststart-baseline-v3.json']);wire=n.checked_json(record['wire'])
                    thread['response']['sandbox']['writableRoots'][1]='<HOST_HOME>/sandbox'
                    pair['snapshot']['snapshot']['sandbox']['writableRoots'][1]='<HOST_HOME>/sandbox'
                    response=next(e for e in wire[thread['wire_start_index']:thread['wire_end_index']] if e['direction']=='response_or_event' and 'result' in e['payload']);response['payload']['result']=copy.deepcopy(thread['response'])
                    record['facts']['thread-start-v3.json']=write('thread-start-v3.json',thread);record['facts']['poststart-baseline-v3.json']=write('poststart-baseline-v3.json',pair);record['wire']=write('live-rpc/rpc.json',wire);reason='ambiguous historical HOME'
                with self.assertRaisesRegex(RuntimeError,reason):n.workflow_usage(r['usage']+[write('bad-context.json',record)])

    def test_live_foreign_terminal_and_returned_turn_hold_without_second_USER(self):
        for mutation in ('foreign-terminal','returned-turn'):
            with self.subTest(mutation=mutation):self.test_actual_run_row_emits_five_wire_bound_bundles_with_real_live_bundle(_ownership=mutation)

    def test_retained_native13_home_display_is_bound_to_historical_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);case=SpecClosureComponentTests();a,r,row,b,m,refresh,save,d=case.fixture(work)
            home=str(work/'captured-home');b['forward_thread_expectation']['instructionSources'].append(home+'/.codex/AGENTS.md');refresh()
            ref,record,write=case.retain(work,a,r,row,b,m,healthy=True,home=home)
            self.assertEqual(n.workflow_usage(r['usage']+[ref])['changed-spec/closure'],1)
            closed=n.checked_json(record['facts']['live-rpc/closed.json']);closed['environment_after']['identity_sha256']['HOME']='0'*64
            record['facts']['live-rpc/closed.json']=write('live-rpc/closed.json',closed)
            with self.assertRaises(RuntimeError):n.workflow_usage(r['usage']+[write('bad-context.json',record)])

    def test_producer_shaped_positive_and_four_independent_leaf_attacks(self):
        for mutation in ('postimage-ref-sha','native13-model','foreign-terminal-thread','missing-bundle-boundaries'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                case,a,r,row,b,m,release,record,write=self.fixture(Path(tmp));bad=copy.deepcopy(record)
                wire=n.checked_json(bad['wire']);start=next(i for i,e in enumerate(wire) if e.get('payload',{}).get('method')=='turn/start')
                self.assertEqual([e['payload']['method'] for e in wire if e['direction']=='request' and e['payload'].get('method') in ('config/read','skills/list')].count('skills/list'),6)
                if mutation=='postimage-ref-sha':
                    key='workflow-closure-postimage.json';doc=n.checked_json(bad['scope_facts'][key]);doc['postimage']['sha256']='0'*64;bad['scope_facts'][key]=write(key,doc)
                elif mutation=='native13-model':
                    key='poststart-baseline-v3.json';doc=n.checked_json(bad['facts'][key]);doc['snapshot']['snapshot']['model']='unapproved-forged-model';bad['facts'][key]=write(key,doc)
                    key='thread-start-v3.json';doc=n.checked_json(bad['facts'][key]);doc['response']['model']='unapproved-forged-model';bad['facts'][key]=write(key,doc)
                elif mutation=='foreign-terminal-thread':
                    end=next(e for e in wire if e.get('payload',{}).get('method')=='turn/completed');end['payload']['params']['threadId']='foreign-thread';bad['wire']=write('live-rpc/rpc.json',wire)
                    key='turn-01.json';doc=n.checked_json(bad['facts'][key]);doc['events']=[e['payload'] for e in wire[start:] if e['direction']=='response_or_event'];bad['facts'][key]=write(key,doc)
                else:
                    for key in bad['scope_facts']:
                        if not key.startswith('workflow-closure-sample-'):continue
                        doc=n.checked_json(bad['scope_facts'][key]);doc['wire_start_index']=doc['wire_end_index']=len(wire);bad['scope_facts'][key]=write(key,doc)
                immutable={k:copy.deepcopy(release[k]) for k in ('native_premises','source_review','root_review')}
                with self.assertRaises(RuntimeError):n.workflow_usage(r['usage']+[write('bad-context.json',bad)])
                self.assertEqual(immutable,{k:n.checked_json(record['release'])[k] for k in immutable})

    def test_all13_rehashed_observed_fields_cannot_change_unchanged_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            case,a,r,row,b,m,release,record,write=self.fixture(Path(tmp));saved={k:Path(record['facts'][k]['path']).read_bytes() for k in ('poststart-baseline-v3.json','thread-start-v3.json')};original_wire=Path(record['wire']['path']).read_bytes()
            for field in n.THREAD_FIELDS:
                bad=copy.deepcopy(record);pair=n.checked_json(record['facts']['poststart-baseline-v3.json']);thread=n.checked_json(record['facts']['thread-start-v3.json']);wire=n.checked_json(record['wire'])
                value=['/unreleased'] if isinstance(thread['response'][field],list) else {'unreleased':True} if isinstance(thread['response'][field],dict) or thread['response'][field] is None else 'unreleased-value'
                thread['response'][field]=value;pair['snapshot']['snapshot'][field]=value
                if field in ('cwd','model','modelProvider','reasoningEffort'):thread['response']['thread'][field]=value
                # Make the wire agree too: the remaining contradiction is the unchanged release.
                response=next(e for e in wire[thread['wire_start_index']:thread['wire_end_index']] if e['direction']=='response_or_event' and 'result' in e['payload']);response['payload']['result']=copy.deepcopy(thread['response'])
                bad['wire']=write('live-rpc/rpc.json',wire)
                for key,doc in (('poststart-baseline-v3.json',pair),('thread-start-v3.json',thread)):bad['facts'][key]=write(key,doc)
                with self.subTest(field=field),self.assertRaises(RuntimeError):n.workflow_usage(r['usage']+[write('bad-context.json',bad)])
                for key,raw in saved.items():Path(record['facts'][key]['path']).write_bytes(raw)
                Path(record['wire']['path']).write_bytes(original_wire)

    def test_lifecycle_ownership_returned_turn_and_deadline_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            case,a,r,row,b,m,release,record,write=self.fixture(Path(tmp));raw=Path(record['wire']['path']).read_bytes();turnraw=Path(record['facts']['turn-01.json']['path']).read_bytes()
            for mutation in ('foreign-terminal-same-turn','missing-terminal-thread','returned-turn','foreign-started','wrong-started-turn','deadline-equality'):
                wire=n.checked_json(record['wire']);bad=copy.deepcopy(record);start=next(i for i,e in enumerate(wire) if e.get('payload',{}).get('method')=='turn/start');terminal=next(e for e in wire if e.get('payload',{}).get('method')=='turn/completed');started=next(e for e in wire if e.get('payload',{}).get('method')=='turn/started')
                if mutation=='foreign-terminal-same-turn':terminal['payload']['params']['threadId']='foreign-thread'
                elif mutation=='missing-terminal-thread':terminal['payload']['params'].pop('threadId')
                elif mutation=='returned-turn':wire[start+1]['payload']['result']['turn']['id']='different-returned-turn'
                elif mutation=='foreign-started':started['payload']['params']['threadId']='foreign-thread'
                elif mutation=='wrong-started-turn':started['payload']['params']['turn']['id']='contradictory-turn'
                else:
                    stamp=wire[start]['monotonic_ns']+180_000_000_000
                    for i in range(terminal['wire_index'],len(wire)):wire[i]['monotonic_ns']=stamp+i
                    terminal['monotonic_ns']=stamp
                bad['wire']=write('live-rpc/rpc.json',wire);turn=n.checked_json(record['facts']['turn-01.json']);turn['events']=[e['payload'] for e in wire[start:] if e['direction']=='response_or_event'];bad['facts']['turn-01.json']=write('turn-01.json',turn)
                with self.subTest(mutation=mutation),self.assertRaises(RuntimeError):n.workflow_usage(r['usage']+[write('bad-context.json',bad)])
                Path(record['wire']['path']).write_bytes(raw);Path(record['facts']['turn-01.json']['path']).write_bytes(turnraw)

    def test_rehashed_thread_start_result_cannot_name_different_dispatched_thread(self):
        with tempfile.TemporaryDirectory() as tmp:
            case,a,r,row,b,m,release,record,write=self.fixture(Path(tmp));bad=copy.deepcopy(record);wire=n.checked_json(record['wire'])
            thread=n.checked_json(record['facts']['thread-start-v3.json']);thread['response']['thread']['id']='foreign-created-thread'
            pair=n.checked_json(record['facts']['poststart-baseline-v3.json']);pair['snapshot']['thread_id']='foreign-created-thread'
            wire[thread['wire_start_index']+1]['payload']['result']=copy.deepcopy(thread['response'])
            bad['facts']['thread-start-v3.json']=write('thread-start-v3.json',thread);bad['facts']['poststart-baseline-v3.json']=write('poststart-baseline-v3.json',pair);bad['wire']=write('live-rpc/rpc.json',wire)
            with self.assertRaises(RuntimeError):n.workflow_usage(r['usage']+[write('bad-context.json',bad)])

    def test_bundle_phase_range_frame_and_native_proof_substitutions_deny(self):
        with tempfile.TemporaryDirectory() as tmp:
            case,a,r,row,b,m,release,record,write=self.fixture(Path(tmp));paths={ref['path'] for ref in record['scope_facts'].values()}|{record['wire']['path'],record['facts']['live-native-selection-receipt.json']['path']};saved={path:Path(path).read_bytes() for path in paths}
            for mutation in ('collapse','duplicate-phase','duplicate-id','missing-sample','swapped-frame','missing-frame','frame-config','config-cwd','disabled-catalog','reply-id','native-proof','six-event-wire'):
                bad=copy.deepcopy(record);key='workflow-closure-sample-003.json';doc=n.checked_json(bad['scope_facts'][key]);wire=n.checked_json(bad['wire'])
                if mutation=='collapse':doc['wire_start_index']=doc['wire_end_index']=len(wire)
                elif mutation=='duplicate-phase':doc['phase']='post-start-2'
                elif mutation=='duplicate-id':doc['bundle_id']=2
                elif mutation=='missing-sample':bad['scope_facts'].pop(key)
                elif mutation=='swapped-frame':doc['frame']=bad['scope_facts']['workflow-closure-bundle-002.json']
                elif mutation=='missing-frame':bad['scope_facts'].pop('workflow-closure-bundle-003.json')
                elif mutation=='frame-config':
                    frame=n.checked_json(doc['frame']);frame['config']['effective']['canonical_features'][n.CANONICAL_FEATURES[0]]=True;doc['frame']=write('workflow-closure-bundle-003.json',frame);bad['scope_facts']['workflow-closure-bundle-003.json']=doc['frame']
                elif mutation=='config-cwd':wire[doc['wire_start_index']]['payload']['params']['cwd']='/foreign'
                elif mutation=='disabled-catalog':
                    response=next(e for e in wire[doc['wire_start_index']:doc['wire_end_index']] if 'result' in e.get('payload',{}) and 'data' in e['payload']['result']);response['payload']['result']['data'][0]['skills'][0]['enabled']=False
                elif mutation=='reply-id':wire[doc['wire_start_index']+1]['payload']['id']='foreign-reply-id'
                elif mutation=='native-proof':
                    receipt=n.checked_json(bad['facts']['live-native-selection-receipt.json']);receipt['source_proof_sha256']='0'*64;bad['facts']['live-native-selection-receipt.json']=write('live-native-selection-receipt.json',receipt)
                else:
                    start=next(i for i,e in enumerate(wire) if e.get('payload',{}).get('method')=='turn/start');wire=wire[:3]+wire[start:start+3]
                    for i,e in enumerate(wire):e['wire_index']=i
                if mutation not in ('missing-sample',):bad['scope_facts'][key]=write(key,doc)
                bad['wire']=write('live-rpc/rpc.json',wire)
                with self.subTest(mutation=mutation),self.assertRaises((RuntimeError,KeyError)):n.workflow_usage(r['usage']+[write('bad-context.json',bad)])
                for path,raw in saved.items():Path(path).write_bytes(raw)



class SpecClosureInstallerLockTests(unittest.TestCase):
    @staticmethod
    def model_lock(work,rowid,mode,root,records,products,manifest,body,save,narrative):
        """SYNTHETIC test model; never claims an installer or Root acted."""
        import json,posixpath
        E=n.SOURCE/'.omx/ultragoal/evidence'
        P=E/'g004/codex/native-v66/preparation/spec-closure-three-row-S-source9bb-usage71'
        def ref(p):return {'path':str(p),'sha256':n.sha(p)}
        record=next(x for x in records if x['relative_path']=='skills-lock.json')
        old=n.checked_json(record['retained_byte_ref']);new=copy.deepcopy(old)
        order=n.checked_json(ref(E/'workflow-closure-installer-lock-relation-plan-critic-r1/index.json'))['verification']['independent_offline_proof']['finite_order']
        source=posixpath.normpath(posixpath.join(posixpath.dirname(record['expected']['realpath']),old['skills']['ains']['source']))
        for name,entry in new['skills'].items():
            files={x['relative_path'].split('/',2)[2]:x for x in products if x['relative_path'].startswith('skills/'+name+'/')}
            raw=b''.join(k.encode()+Path((body if name=='ains-spec' and k=='SKILL.md' else files[k]['old_retained_ref'])['path']).read_bytes() for k in order[name]['relative_file_order'])
            entry['computedHash']=hashlib.sha256(raw).hexdigest();entry['source']=posixpath.relpath(source,str(root.resolve()))
        raw=(json.dumps(new,ensure_ascii=False,indent=2)+'\n').encode();target=root/'skills-lock.json'
        # Preserve identity when the same synthetic consumer is reused.
        if target.read_bytes()!=raw:target.write_bytes(raw)
        newpath=work/'model-new-lock.json';newpath.write_bytes(raw)
        pins=ref(P/'inputs-start.json');identities={k:v for k,v in n.checked_json(pins).items() if '/node_modules/skills/' in k}
        cli=save('model-cli.json',{'schema':'spec-closure-installer-cli-v1','version':'1.7.4','identities':identities,'pins':pins,'version_receipt':ref(P/'installer-version-command.json'),'historical_collector':ref(E/'r7-parent-verification/closure-installer-lock-implementation-scope/archive/native_delta.py'),'excerpt':ref(E/'workflow-closure-installer-lock-relation-plan/pinned-installer-functions.txt')})
        command=copy.deepcopy(n.checked_json(ref(P/(rowid+'-command.json'))));command['cwd']=str(root);command['argv'][5]=source
        cmd=save('model-command.json',command)
        fields={'row_id':rowid,'root':str(root),'realroot':str(root.resolve()),'old_lock':record['retained_byte_ref'],'new_lock':ref(newpath),'manifest':manifest,'cli':cli,'command':cmd,'source_root':source}
        review=save('model-lock-review.json',dict(fields,schema='ROOT_SPEC_CLOSURE_INSTALLER_LOCK_REVIEW_V1',decision='APPROVE_EXACT_INSTALLER_LOCK_RELATION',report=narrative))
        return save('model-lock.json',dict(fields,schema='spec-closure-installer-lock-v1',report=review))

    def test_real_predicate_derives_model_lock_all_three_rows(self):
        for selected in range(3):
            with self.subTest(selected=selected),tempfile.TemporaryDirectory() as tmp:
                a,r,row,b,m,refresh,save,d=SpecClosureComponentTests().fixture(Path(tmp),selected)
                refresh();result=n.spec_closure_component(r,row,m,r['usage'])
                self.assertEqual(result['initial']['skills-lock.json']['sha256'],n.sha(Path(m['root'])/'skills-lock.json'))
                n.validate_workflow_checkpoint(a,r,row,b)

    def test_required_lock_and_immutable_protection(self):
        for change in ('missing-lock','missing-protection','drift'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as tmp:
                w=Path(tmp);a,r,row,b,m,refresh,save,d=SpecClosureComponentTests().fixture(w)
                install=n.checked_json(m['install']);program=n.checked_json(install['program'])
                if change=='missing-lock':
                    del program['lock'];install['program']=save('bad-program.json',program);m['install']=save('bad-install.json',install)
                elif change=='missing-protection':r['protected_files']=r['protected_files'][:1]
                else:(Path(m['root'])/'skills-lock.json').write_bytes(b'{}')
                refresh()
                with self.assertRaises((RuntimeError,KeyError,ValueError)):
                    if change=='drift':n.validate_workflow_checkpoint(a,r,row,b)
                    else:n.spec_closure_component(r,row,m,r['usage'])

    def test_rehashed_closed_relation_negatives_real_helper(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            w=Path(tmp);a,r,row,b,m,refresh,save,d=SpecClosureComponentTests().fixture(w)
            products=n.checked_json(n.checked_json(m['business_map'])['supplement'])['product_identity_map'];product=n.checked_json(m['product'])
            mapping=n.checked_json(n.checked_json(m['business_map'])['supplement']);records=[x for x in mapping['records'] if x['lineage']=='original']
            baseline=n.checked_json(n.checked_json(m['install'])['program']);receipt=n.checked_json(baseline['lock'])
            def check(program):return n.spec_closure_installer_lock(r,row,m,records,products,product,program)
            self.assertEqual(check(baseline),m['state']['skills-lock.json']['sha256'])
            mutations=('extra','missing','row','root','realroot','manifest','source','old-ref','new-ref','version','hash','other-hash','relative','nonlocal','entry-extra','missing-skill','extra-skill','duplicate','serialization','cli','cli-source','cli-version','command-mode','command-cwd','command-exit','review','review-bool','review-fields','live-output')
            for mutation in mutations:
                with self.subTest(mutation=mutation):
                    lock=copy.deepcopy(receipt);program=copy.deepcopy(baseline)
                    if mutation=='extra':lock['unbound']=True
                    elif mutation=='missing':del lock['command']
                    elif mutation in ('row','root','realroot','source'):lock[{'row':'row_id','source':'source_root'}.get(mutation,mutation)]='foreign'
                    elif mutation=='manifest':lock['manifest']=lock['old_lock']
                    elif mutation=='old-ref':lock['old_lock']=lock['new_lock']
                    elif mutation=='new-ref':lock['new_lock']['sha256']='0'*64
                    elif mutation in ('version','hash','other-hash','relative','nonlocal','entry-extra','missing-skill','extra-skill','duplicate','serialization'):
                        data=n.checked_json(lock['new_lock'])
                        if mutation=='version':data['version']=True
                        elif mutation=='hash':data['skills']['ains-spec']['computedHash']='0'*64
                        elif mutation=='other-hash':data['skills']['ains']['computedHash']='0'*64
                        elif mutation=='relative':data['skills']['ains']['source']='../wrong'
                        elif mutation=='nonlocal':data['skills']['ains']['sourceType']='git'
                        elif mutation=='entry-extra':data['skills']['ains']['extra']=1
                        elif mutation=='missing-skill':del data['skills']['ains']
                        elif mutation=='extra-skill':data['skills']['foreign']=data['skills']['ains']
                        ref=save('bad-new.json',data)
                        if mutation=='duplicate':(w/'bad-new.json').write_text((w/'bad-new.json').read_text().replace('"version": 1','"version": 1, "version": 1'))
                        if mutation=='serialization':(w/'bad-new.json').write_text(json.dumps(data))
                        lock['new_lock']={'path':str(w/'bad-new.json'),'sha256':n.sha(w/'bad-new.json')}
                    elif mutation.startswith('cli'):
                        data=n.checked_json(lock['cli'])
                        if mutation=='cli':data['extra']=1
                        elif mutation=='cli-version':data['version']='1.7.5'
                        else:next(iter(data['identities'].values()))['sha256']='0'*64
                        lock['cli']=save('bad-cli.json',data)
                    elif mutation.startswith('command'):
                        data=n.checked_json(lock['command'])
                        if mutation=='command-mode':data['argv'].append('--copy')
                        elif mutation=='command-cwd':data['cwd']=str(w)
                        else:data['returncode']=True
                        lock['command']=save('bad-command.json',data)
                    elif mutation=='review':lock['report']=lock['cli']
                    elif mutation=='review-bool':lock['report']=save('bad-review.json',{'approved':True})
                    elif mutation=='review-fields':
                        data=n.checked_json(lock['report']);data['source_root']='foreign';lock['report']=save('bad-review.json',data)
                    elif mutation=='live-output':lock['new_lock']={'path':str(Path(m['root'])/'skills-lock.json'),'sha256':m['state']['skills-lock.json']['sha256']}
                    program['lock']=save('bad-lock.json',lock)
                    with self.assertRaises((RuntimeError,KeyError,ValueError,TypeError)):check(program)

    def test_actual_retained_pairs_with_synthetic_review_only(self):
        """Real retained data and real validator; test Root fixtures grant no authority."""
        import json
        E=n.SOURCE/'.omx/ultragoal/evidence';P=E/'g004/codex/native-v66/preparation/spec-closure-three-row-S-source9bb-usage71';O=E/'workflow-closure-installer-lock-relation-implementation'
        for rowid,mode,lin in SpecClosureComponentTests.ROWS:
            with self.subTest(row=rowid),tempfile.TemporaryDirectory() as tmp:
                w=Path(tmp)
                def ref(p):return {'path':str(p),'sha256':n.sha(p)}
                def save(name,data):p=w/name;n.write(p,data);return ref(p)
                m=json.loads((P/rowid/'candidate-materialization-DATA.json').read_text());r=json.loads((P/rowid/'candidate-recipe-DATA.json').read_text());row=r['rows'][0]
                install=n.checked_json(m['install']);program=n.checked_json(install['program']);business=n.checked_json(m['business_map']);old=next(x['source'] for x in business['records'] if x['path']=='skills-lock.json')
                pins=ref(P/'inputs-start.json');identities={k:v for k,v in n.checked_json(pins).items() if '/node_modules/skills/' in k}
                cli=save('cli.json',{'schema':'spec-closure-installer-cli-v1','version':'1.7.4','identities':identities,'pins':pins,'version_receipt':ref(P/'installer-version-command.json'),'historical_collector':ref(E/'r7-parent-verification/closure-installer-lock-implementation-scope/archive/native_delta.py'),'excerpt':ref(E/'workflow-closure-installer-lock-relation-plan/pinned-installer-functions.txt')})
                fields={'row_id':rowid,'root':m['root'],'realroot':m['realroot'],'old_lock':old,'new_lock':ref(O/rowid/'actual-new-lock.json'),'manifest':install['manifest'],'cli':cli,'command':ref(P/(rowid+'-command.json')),'source_root':str(n.SOURCE)}
                note=w/'SYNTHETIC-REVIEW.txt';note.write_text('SYNTHETIC review fixture only; actual Root has not approved this relation.')
                review=save('SYNTHETIC-review.json',dict(fields,schema='ROOT_SPEC_CLOSURE_INSTALLER_LOCK_REVIEW_V1',decision='APPROVE_EXACT_INSTALLER_LOCK_RELATION',report=ref(note)))
                program['lock']=save('lock.json',dict(fields,schema='spec-closure-installer-lock-v1',report=review));install['program']=save('program.json',program);m['install']=save('install.json',install)
                r['workflow_checkpoint']=save('checkpoint.json',{'materialization':save('material.json',m)})
                r['protected_files']=[{'path':str(Path(m['root'])/'skills-lock.json'),'sha256':fields['new_lock']['sha256']}]
                last=E/'g004/codex/native-v65/runs-notification-workflow-build-readonly-handoff-source1249-usage70-RELEASE-REQUIRED/workflow-context.json'
                history=n.checked_json(n.checked_json(ref(last))['recipe'])['usage']+[ref(last)]
                r['usage']=history
                result=n.spec_closure_component(r,row,m,history)
                self.assertEqual(len(result['initial']),151 if lin=='D2' else 127)
                self.assertEqual(result['initial']['skills-lock.json']['sha256'],fields['new_lock']['sha256'])
                # No current root or cache access: the shared predicate replays solely
                # immutable receipts. Incoming physical validation belongs to its caller.
                from unittest import mock
                raw=Path.read_bytes
                def guarded(p,*args,**kwargs):
                    if str(p).startswith(m['root']) or str(p).startswith(m['realroot']) or str(p).startswith('/Users/oreore/.npm/'):raise AssertionError('live producer read')
                    return raw(p,*args,**kwargs)
                with mock.patch.object(Path,'read_bytes',guarded):n.spec_closure_component(r,row,m,history)
                with self.assertRaisesRegex(RuntimeError,'concrete Root'):
                    n.spec_closure_component(r,row,m,history,{'business':{'closure_materialization':n.checked_json(r['workflow_checkpoint'])['materialization']},'authority_evidence':[n.checked_json(r['workflow_checkpoint'])['materialization'],n.checked_json(m['product'])['source_review'],install['program'],m['origin']['oracle']]})

    def test_lock_is_immutable_in_all_five_samples_and_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            w=Path(tmp);case=SpecClosureComponentTests();a,r,row,b,m,refresh,save,d=case.fixture(w);refresh()
            reference,record,write=case.retain(w,a,r,row,b,m,healthy=True)
            self.assertEqual(n.workflow_usage(r['usage']+[reference])['changed-spec/closure'],1)
            samples=[k for k in record['scope_facts'] if k.startswith('workflow-closure-sample-')]
            self.assertEqual(len(samples),5)
            for key in samples:
                bad=copy.deepcopy(record);doc=n.checked_json(bad['scope_facts'][key]);raw=Path(bad['scope_facts'][key]['path']).read_bytes()
                for side in ('before','after'):doc[side]['skills-lock.json']['sha256']='0'*64
                bad['scope_facts'][key]=write(key,doc)
                with self.subTest(sample=key),self.assertRaises(RuntimeError):n.workflow_usage(r['usage']+[write('bad-context.json',bad)])
                Path(record['scope_facts'][key]['path']).write_bytes(raw)
            bad=copy.deepcopy(record);bad['state']['skills-lock.json']['sha256']='0'*64
            with self.assertRaises(RuntimeError):n.workflow_usage(r['usage']+[write('bad-context.json',bad)])



class FiniteSessionTrustTests(unittest.TestCase):
    def fixture(self, scope="default"):
        import json
        choice_path={
            'default':'.omx/ultragoal/evidence/r7-parent-verification/closure-session-trust-implementation-scope/operator-choice.json',
            'copy':'.omx/continuations/resume-20261027-j56k2v96/copy-equivalent-preparation/operator-choice-v2.json',
            'D2':'.omx/continuations/resume-20261027-j56k2v96/D2-preparation/operator-choice.json'}[scope]
        choice=json.loads((n.SOURCE/choice_path).read_text())
        recipe={'purpose':'spec-closure-regression','phase':'closure','unit':'changed-spec','rows':[{'id':choice['row_id'],'mode':choice['mode'],'transport':'live'}]}
        policy=n.finite_session_policy(choice,recipe)
        session={'name':{'type':'sessionFlags'},'version':policy['session_version'],'config':copy.deepcopy(policy['session'])}
        user={'name':{'type':'user','file':'/synthetic/config.toml'},'version':'sha256:'+n.canonical_hash({}),'config':{}}
        data={'config':copy.deepcopy(policy['session']),'layers':[session,user],'origins':{'projects.'+choice['canonical_root']+'.trust_level':{'name':session['name'],'version':session['version']}}}
        return policy,data

    def test_copy_scope_constructor_projection_and_retained_replay(self):
        for scope in ('default','copy','D2'):
            with self.subTest(scope=scope),tempfile.TemporaryDirectory() as tmp:
                policy,data=self.fixture(scope)
                argv=['/opt/homebrew/bin/codex','--no-daemon','-a','never','app-server','--strict-config','--stdio']
                for value in policy['overrides']:argv+=['-c',value]
                self.assertEqual(n.validate_finite_policy_argv(argv,policy),argv)
                self.assertEqual(n.finite_policy_projection(data,policy)['session'],policy['session'])
                replay,r,p,w,retained,save=self.history_fixture(Path(tmp),scope)
                self.assertEqual(len(p['usage']),{'default':44,'copy':45,'D2':46}[scope])
                self.assertEqual(replay(r,p,w,r['fixture_release']),retained)

    def test_copy_exact45_chronology_and_unchanged_default_policy_bytes(self):
        policy,_=self.fixture()
        proof=n.spec_closure_zero_provenance()
        launch=n.checked_json(proof['record']['policy_facts']['live-rpc/launch.json'])
        historical={k:v for k,v in launch['finite_policy'].items() if k not in ('declaration','metadata_paths')}
        self.assertEqual(policy,historical)
        scope=next(v for v in n.FINITE_SCOPES.values() if v['mode']=='copy')
        base=n.checked_json(scope['base_recipe'])
        self.assertEqual(len(base['protected_files']),72)
        self.assertEqual(base['usage'][:43],proof['base']['usage'])
        self.assertEqual(base['usage'][43],n.SPEC_CLOSURE_ZERO_CONTEXT)
        self.assertEqual(base['usage'][44]['sha256'],'48f9fba92c3f88789a579ccc8454caf4799c216642e49e384003d67a6fca07ba')
        usage=n.finite_recipe_usage(base,base)
        used=n.workflow_usage(usage)
        actual=n.checked_json(usage[-1]);producer=n.checked_json(actual['recipe'])
        checkpoint=n.checked_json(producer['workflow_checkpoint']);material=n.checked_json(checkpoint['materialization'])
        release=n.checked_json(actual['release']);review=n.checked_json(release['root_review'])
        with self.assertRaisesRegex(RuntimeError,'row lifetime dispatched'):
            n.spec_closure_component(producer,producer['rows'][0],material,usage,review)
        self.assertEqual(sum(used.values()),51)
        self.assertEqual(used['changed-spec/closure'],1)
        for change in ('omitted','reordered','duplicate','foreign-row'):
            with self.subTest(base=change):
                bad=copy.deepcopy(base)
                if change=='omitted':bad['usage'].pop()
                elif change=='reordered':bad['usage'][-2:]=reversed(bad['usage'][-2:])
                elif change=='duplicate':bad['usage'].append(bad['usage'][-1])
                else:bad['rows'][0]['id']='codex-default-authentic-preanswer'
                with self.assertRaises(RuntimeError):n.finite_recipe_usage(bad,bad)

    def test_copy_scope_rejects_cross_scope_policy_choice_and_history(self, scope="copy"):
        import json
        row_id='codex-copy-equivalent-preanswer' if scope=='copy' else 'codex-copy-D2-authentic-pre-v57-answer'
        choice=n.checked_json(next(v for v in n.FINITE_SCOPES.values() if v['row_id']==row_id)['operator_choice'])
        recipe=n.checked_json(choice['base_recipe'])
        for key,value in (('root',n.FINITE_LOGICAL_ROOT),('canonical_root',n.FINITE_CANONICAL_ROOT),('row_id','codex-default-authentic-preanswer'),('mode','default'),('checkpoint',{}),('base_recipe',{}),('argv_pair',[])):
            with self.subTest(choice_key=key):
                bad=copy.deepcopy(choice);bad[key]=value
                with self.assertRaises(RuntimeError):n.finite_session_policy(bad,recipe)
        policy,data=self.fixture(scope)
        for key,value in (('root',n.FINITE_LOGICAL_ROOT),('canonical_root',n.FINITE_CANONICAL_ROOT),('row_id','codex-default-authentic-preanswer'),('operator_choice_sha256',n.FINITE_CHOICE_SHA256)):
            with self.subTest(policy_key=key):
                bad=copy.deepcopy(policy);bad[key]=value
                with self.assertRaises(RuntimeError):n.finite_policy_projection(data,bad)
                with self.assertRaises(RuntimeError):n.validate_finite_policy_argv([],bad)
        for mutation in ('choice','USER','checkpoint','root','strip-markers','omit-zero','omit-default','reorder','duplicate','foreign','default-zero-exception'):
            with self.subTest(history=mutation),tempfile.TemporaryDirectory() as tmp:
                replay,r,p,w,policy,save=self.history_fixture(Path(tmp),scope)
                if mutation=='choice':
                    d=n.checked_json(policy['declaration']);d['operator_choice']=n.finite_scope(n.FINITE_LOGICAL_ROOT)['operator_choice'];ref=save('cross-choice.json',d);r['finite_policy_declaration']=p['finite_policy_declaration']=ref
                elif mutation=='USER':p['rows'][0]['initial_user_text']='FOREIGN USER'
                elif mutation=='checkpoint':p['workflow_checkpoint']={}
                elif mutation=='root':r['root']=n.FINITE_LOGICAL_ROOT
                elif mutation=='strip-markers':r.pop('producer_schema');p.pop('producer_schema');r.pop('finite_policy_declaration');p.pop('finite_policy_declaration')
                elif mutation=='omit-zero':p['usage'].pop(-2)
                elif mutation=='omit-default':p['usage'].pop()
                elif mutation=='reorder':p['usage'][-2:]=reversed(p['usage'][-2:])
                elif mutation=='duplicate':p['usage'].append(p['usage'][-1])
                elif mutation=='foreign':p['usage'][-1]={'path':'/foreign-not-read','sha256':'0'*64}
                if mutation=='default-zero-exception':
                    with self.assertRaises(RuntimeError):replay(r,p,w,r['fixture_release'],n.SPEC_CLOSURE_ZERO_CONTEXT)
                else:
                    with self.assertRaises(RuntimeError):replay(r,p,w,r['fixture_release'])

    def test_D2_scope_cross_row_USER_checkpoint_and_chronology_attacks(self):
        self.test_copy_scope_rejects_cross_scope_policy_choice_and_history('D2')

    def test_D2_exact46_state151_and_both_actual_producers_replay(self):
        scope=next(v for v in n.FINITE_SCOPES.values() if v['row_id']=='codex-copy-D2-authentic-pre-v57-answer')
        choice=n.checked_json(scope['operator_choice']);base=n.checked_json(scope['base_recipe']);cp=n.checked_json(scope['checkpoint'])
        self.assertEqual(scope['state_count'],151)
        self.assertEqual(len(cp['state']),151)
        self.assertEqual(len(base['protected_files']),86)
        self.assertEqual(len(base['checkpoint_installed']),16)
        self.assertEqual(len(base['usage']),46)
        self.assertEqual(base['usage'][43],n.SPEC_CLOSURE_ZERO_CONTEXT)
        self.assertEqual(base['usage'][44]['sha256'],'48f9fba92c3f88789a579ccc8454caf4799c216642e49e384003d67a6fca07ba')
        self.assertEqual(base['usage'][45]['sha256'][:4],'0b51')
        used=n.workflow_usage(n.finite_recipe_usage(base,base))
        self.assertEqual(sum(used.values()),52)
        self.assertEqual(used['changed-spec/closure'],2)
        for ref in base['usage'][-2:]:
            record=n.checked_json(ref);producer=n.checked_json(record['recipe'])
            decl=n.checked_json(record['finite_policy_declaration']);old_choice=n.checked_json(decl['operator_choice'])
            policy=n.finite_session_policy(old_choice,producer)
            launch=n.checked_json(record['policy_facts']['live-rpc/launch.json'])
            self.assertEqual(policy,{k:v for k,v in launch['finite_policy'].items() if k not in ('declaration','metadata_paths')})
            self.assertNotEqual(base['rows'][0]['initial_user_text'],producer['rows'][0]['initial_user_text'])
            old_cp=n.checked_json(producer['workflow_checkpoint']);material=n.checked_json(old_cp['materialization']);release=n.checked_json(record['release']);review=n.checked_json(release['root_review'])
            with self.assertRaisesRegex(RuntimeError,'row lifetime dispatched'):
                n.spec_closure_component(producer,producer['rows'][0],material,base['usage'],review)
        for mutation in ('state127','copy-root','copy-choice','copy-USER','omit-copy','extra-zero'):
            with self.subTest(mutation=mutation):
                bad_choice=copy.deepcopy(choice);bad=copy.deepcopy(base)
                if mutation=='state127':
                    bad_choice['state_count']=127
                    # The exact scope, not caller-supplied state_count, controls admission.
                    self.assertEqual(n.finite_scope(bad_choice['root'])['state_count'],151)
                    bad['workflow_checkpoint']={}
                elif mutation=='copy-root':bad_choice['root']=next(v['root'] for v in n.FINITE_SCOPES.values() if v['row_id']=='codex-copy-equivalent-preanswer')
                elif mutation=='copy-choice':bad_choice['base_recipe']={}
                elif mutation=='copy-USER':bad['rows'][0]['initial_user_text']='original-v39-FOREIGN'
                elif mutation=='omit-copy':bad['usage'].pop()
                else:bad['usage'].append(n.SPEC_CLOSURE_ZERO_CONTEXT)
                if mutation in ('copy-root','copy-choice'):
                    with self.assertRaises(RuntimeError):n.finite_session_policy(bad_choice,bad)
                else:
                    with self.assertRaises(RuntimeError):n.finite_recipe_usage(bad,bad)

    def test_config_read_layers_follow_native_high_to_low_order(self):
        # ConfigManager::read at 6aaac694 uses all_layers_high_to_low().
        policy,data=self.fixture()
        by_kind={layer['name']['type']:layer for layer in data['layers']}
        by_kind['system']={'name':{'type':'system','file':'/synthetic/system.toml'},
                          'version':'sha256:'+n.canonical_hash({}),'config':{}}
        for order in (('sessionFlags','user'),('sessionFlags','user','system')):
            with self.subTest(valid_order=order):
                native=copy.deepcopy(data)
                native['layers']=[copy.deepcopy(by_kind[kind]) for kind in order]
                projection=n.finite_policy_projection(native,policy)
                self.assertEqual(projection['origin'],native['origins'][projection['origin_path']])
                self.assertEqual([layer['metadata']['name']['type'] for layer in projection['persistent_layers']],list(order[1:]))
        for order in (('user','sessionFlags'),('system','user','sessionFlags'),
                      ('sessionFlags','system','user'),('user','system','sessionFlags'),
                      ('sessionFlags','user','user'),('sessionFlags','sessionFlags','user'),
                      ('sessionFlags',),('sessionFlags','user','system','system')):
            with self.subTest(invalid_order=order):
                invalid=copy.deepcopy(data)
                invalid['layers']=[copy.deepcopy(by_kind[kind]) for kind in order]
                with self.assertRaises(RuntimeError):
                    n.finite_policy_projection(invalid,policy)

    def test_native_optional_skills_defaults_and_invalid_shapes(self):
        from unittest import mock
        # Pinned config/mod.rs:4173-4177 maps absent Option<SkillsConfig>
        # and include_instructions=None to true without changing raw config.
        for shape in ('absent',None,{}, {'include_instructions':None}, {'include_instructions':True}):
            with self.subTest(valid_skills=shape):
                policy,data=self.fixture()
                if shape!='absent':data['config']['skills']=copy.deepcopy(shape)
                original=copy.deepcopy(data)
                projection=n.finite_policy_projection(data,policy)
                self.assertEqual(data,original)
                self.assertEqual(projection['config_identity'],n.safe_config_identity(original['config']))
        for shape in (False,True,0,1,'',[],['skills'],{'include_instructions':False},
                      {'include_instructions':0},{'include_instructions':1},
                      {'include_instructions':'true'},{'include_instructions':[]},
                      {'include_instructions':{}}):
            with self.subTest(invalid_skills=shape):
                policy,data=self.fixture();data['config']['skills']=shape
                with self.assertRaises(RuntimeError):n.finite_policy_projection(data,policy)
        policy,data=self.fixture();data['config']['skills']=None
        with mock.patch.object(n,'sha',return_value='stale-default-source'):
            with self.assertRaisesRegex(RuntimeError,'default source'):
                n.finite_policy_projection(data,policy)

    def test_exact_constructor_and_source_fingerprint(self):
        policy,data=self.fixture()
        self.assertEqual(policy['session_version'],'sha256:1b300e8ab133aa80cc31926e1227c56f554204a1cd807442941c32cd269014d3')
        self.assertEqual(policy['overrides'][-1],'projects.'+policy['canonical_root']+'.trust_level="trusted"')
        result=n.finite_policy_projection(data,policy)
        self.assertEqual(result['origin'],data['origins'][result['origin_path']])
        self.assertEqual(len(result['persistent_layers'][0]['candidates']),4)

    def test_missing_actual_origin_is_hold(self):
        policy,data=self.fixture();data.pop('origins')
        with self.assertRaisesRegex(RuntimeError,'origin'):n.finite_policy_projection(data,policy)

    def test_full_session_and_observed_metadata_required(self):
        for mutation in ('version','origin-version','origin-source','extra-key','extra-project','untrusted','duplicate-session','project-layer','managed','disabled','persistent-canonical','persistent-logical','hooks','mcp-command','mcp-name'):
            with self.subTest(mutation=mutation):
                p,d=self.fixture();session=d['layers'][0]
                if mutation=='version':session['version']='sha256:wrong'
                elif mutation=='origin-version':next(iter(d['origins'].values()))['version']='wrong'
                elif mutation=='origin-source':next(iter(d['origins'].values()))['name']={'type':'user'}
                elif mutation=='extra-key':session['config']['arbitrary']=False
                elif mutation=='extra-project':session['config']['projects']['/foreign']={'trust_level':'trusted'}
                elif mutation=='untrusted':session['config']['projects'][p['canonical_root']]['trust_level']='untrusted'
                elif mutation=='duplicate-session':d['layers'].append(copy.deepcopy(session))
                elif mutation=='project-layer':d['layers'][1]['name']['type']='project'
                elif mutation=='managed':d['layers'][1]['name']['type']='mdm'
                elif mutation=='disabled':session['disabledReason']=''
                elif mutation.startswith('persistent-'):d['layers'][1]['config']['projects']={p['canonical_root'] if mutation.endswith('canonical') else p['root']: {}}
                elif mutation=='hooks':d['config']['features']['hooks']=True
                elif mutation=='mcp-command':d['config']['mcp_servers']['node_repl']['command']='other'
                elif mutation=='mcp-name':d['config']['mcp_servers']['foreign']={'enabled':False}
                with self.assertRaises(RuntimeError):n.finite_policy_projection(d,p)

    def test_argv_whitelist_precedes_every_external_process(self):
        from unittest import mock
        p,d=self.fixture();argv=['/opt/homebrew/bin/codex','--no-daemon','-a','never','app-server','--strict-config','--stdio']
        for value in p['overrides']:argv+=['-c',value]
        self.assertEqual(n.validate_finite_policy_argv(argv,p),argv)
        for extra in (['-c','x=false'],['-c',p['overrides'][-1]],['--dangerously-bypass-approvals-and-sandbox']):
            with self.assertRaises(RuntimeError):n.validate_finite_policy_argv(argv+extra,p)
        for root in (p['root'],'/foreign',p['canonical_root']+'.dotted','"'+p['canonical_root']+'"'):
            bad=argv[:-1]+['projects.'+root+'.trust_level="trusted"']
            with self.assertRaises(RuntimeError):n.validate_finite_policy_argv(bad,p)
        with mock.patch.object(n.subprocess,'run',side_effect=AssertionError('external version process')),mock.patch.object(n.subprocess,'Popen',side_effect=AssertionError('external config process')):
            with self.assertRaisesRegex(RuntimeError,'argv'):
                n.recorded_rpc(None,None,p['root'],p['overrides']+['x=false'],None,{'finite_session_policy':p})

    def test_metadata_bootstrap_never_launches_probe(self):
        from unittest import mock
        p,d=self.fixture()
        helper=mock.Mock();helper.probe.side_effect=AssertionError('unguarded probe');helper.mdm_forced.return_value={'managed':False}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'raw';path.write_text('preserved')
            policy=copy.deepcopy(p);policy['metadata_paths']={str(path):{'exists':True,'sha256':n.sha(path),'realpath':str(path)}}
            with mock.patch.object(n.subprocess,'Popen',side_effect=AssertionError('external process')):
                sample=n.finite_metadata_sample(policy,{'files':{str(path):{'exists':True,'sha256':n.sha(path),'realpath':str(path)}},'mdm_before':helper.mdm_forced(),'mdm_after':helper.mdm_forced()})
            self.assertEqual(sample['files'],policy['metadata_paths']);helper.probe.assert_not_called()
            path.write_text('changed')
            with self.assertRaises(RuntimeError):n.finite_metadata_sample(policy,{'files':{str(path):{'exists':True,'sha256':n.sha(path),'realpath':str(path)}},'mdm_before':helper.mdm_forced(),'mdm_after':helper.mdm_forced()})

    def test_constructor_scope_is_single_default_row(self):
        import json
        choice=json.loads((n.SOURCE/'.omx/ultragoal/evidence/r7-parent-verification/closure-session-trust-implementation-scope/operator-choice.json').read_text())
        for mutation in ('root','canonical','row','mode','transport','purpose','phase','unit'):
            c=copy.deepcopy(choice);recipe={'purpose':'spec-closure-regression','phase':'closure','unit':'changed-spec','rows':[{'id':c['row_id'],'mode':'default','transport':'live'}]}
            if mutation in ('root','canonical'):c['root' if mutation=='root' else 'canonical_root']='/foreign'
            elif mutation in ('row','mode','transport'):recipe['rows'][0]['id' if mutation=='row' else mutation]='other'
            else:recipe[mutation]='other'
            with self.assertRaises(RuntimeError):n.finite_session_policy(c,recipe)

    def test_actual_recorded_rpc_serializes_origin_and_same_argv(self):
        import types
        from unittest import mock
        policy,data=self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);raw=work/'raw';raw.write_text('SYNTHETIC immutable')
            policy.update(declaration={'path':'SYNTHETIC DATA only','sha256':'draft'},metadata_paths={str(raw):{'exists':True,'sha256':n.sha(raw),'realpath':str(raw)}})
            sample=n.finite_metadata_sample(policy,{'files':policy['metadata_paths'],'mdm_before':{'synthetic':False},'mdm_after':{'synthetic':False}})
            environment={'identity_sha256':{'HOME':hashlib.sha256(str(work/'SYNTHETIC-home').encode()).hexdigest()},'selector_names':[],'default_home':True,'default_codex_home':True,'selected_environment_file':{'exists':False}}
            binding={'_finite_home_identity':environment['identity_sha256']['HOME'],'finite_session_policy':policy,'_metadata_sample':lambda:copy.deepcopy(sample),'codex_version':'synthetic','executable_identity':{'sha256':'binary','symlink_target':'/opt/homebrew/bin/codex'}}
            class Base:
                def send(self,obj):self.pending=copy.deepcopy(obj)
                def next(self,deadline):
                    result=data if self.pending.get('method')=='config/read' else {'data':[]}
                    return {'id':self.pending['id'],'result':copy.deepcopy(result)}
                def call(self,method,params,timeout=30):
                    self.seq+=1;self.send({'id':self.seq,'method':method,'params':params});return self.next(0)['result']
                def close(self):self.p.returncode=0
            proc=types.SimpleNamespace(pid=777,returncode=None)
            with n.bound_helpers(work/'helpers') as (helpers,_),mock.patch.object(n.shutil,'which',return_value='/opt/homebrew/bin/codex'),mock.patch.object(n.subprocess,'run',return_value=types.SimpleNamespace(stdout='synthetic')),mock.patch.object(n.subprocess,'Popen',return_value=proc) as popen,mock.patch.object(n,'environment_facts',return_value=environment),mock.patch.object(n,'sha',side_effect=lambda p:'binary' if str(p)=='/opt/homebrew/bin/codex' else hashlib.sha256(Path(p).read_bytes()).hexdigest()),mock.patch.object(Path,'resolve',autospec=True,side_effect=lambda p,*a,**k:p):
                for phase in ('catalog','live'):
                    rpc=n.recorded_rpc(types.SimpleNamespace(RPC=Base),helpers['activation_recheck'],policy['root'],policy['overrides'],work/phase,binding)
                    rpc.call('config/read',{'includeLayers':True,'cwd':policy['root']});rpc.call('skills/list',{'cwds':[policy['root']],'forceReload':True});rpc.call('config/read',{'includeLayers':True,'cwd':policy['root']});rpc.close()
                    recorded=n.checked_json({'path':str(work/phase/'rpc.json'),'sha256':n.sha(work/phase/'rpc.json')})
                    projections=[x['payload']['policy'] for x in recorded if 'policy' in x.get('payload',{})]
                    self.assertEqual(len(projections),2);self.assertEqual(projections[0],n.finite_policy_projection(data,policy))
                    launch=n.checked_json({'path':str(work/phase/'launch.json'),'sha256':n.sha(work/phase/'launch.json')})
                    self.assertEqual(launch['policy_metadata'],sample)
                self.assertEqual(popen.call_count,2);self.assertEqual(popen.call_args_list[0].args,popen.call_args_list[1].args)

    def history_fixture(self,work,scope="default"):
        import ast,json
        policy,data=self.fixture(scope)
        def save(name,value):
            path=work/name;path.parent.mkdir(parents=True,exist_ok=True);n.write(path,value);return {'path':str(path),'sha256':n.sha(path)}
        choice_path={
            'default':'.omx/ultragoal/evidence/r7-parent-verification/closure-session-trust-implementation-scope/operator-choice.json',
            'copy':'.omx/continuations/resume-20261027-j56k2v96/copy-equivalent-preparation/operator-choice-v2.json',
            'D2':'.omx/continuations/resume-20261027-j56k2v96/D2-preparation/operator-choice.json'}[scope]
        choice_ref={'path':str(n.SOURCE/choice_path),'sha256':n.sha(n.SOURCE/choice_path)}
        choice=n.checked_json(choice_ref);base=n.checked_json(choice['base_recipe'])
        metadata=FiniteSessionTrustRepairTests.metadata_fixture(base,choice,work/'SYNTHETIC-home')
        archived=work/'retained-producer.py';archived.write_text('SYNTHETIC retained producer DATA; never executed')
        archived_test=work/'retained-test.py';archived_test.write_text('SYNTHETIC retained test DATA; never executed')
        producer_hash=n.sha(archived)
        for name,digest in (('native_delta.py',producer_hash),('native_delta_test.py',n.sha(archived_test))):
            metadata[str(n.SOURCE/'tests/runtime/codex'/name)]['sha256']=digest
        declaration=save('synthetic-declaration-DATA.json',{'synthetic_fixture_only':True,'schema':'ROOT_FINITE_SESSION_TRUST_DECLARATION_V1','decision':'DECLARE_EXACT_PROCESS_ONLY_POLICY','operator_choice':choice_ref,'base_recipe':choice['base_recipe'],'checkpoint':choice['checkpoint'],'product':choice['product'],'collector_sha256':producer_hash,'tests_sha256':n.sha(archived_test),'producer':{'collector':{'path':str(archived),'sha256':producer_hash},'tests':{'path':str(archived_test),'sha256':n.sha(archived_test)},'helpers':[{'path':str(n.SOURCE/x['path']),'sha256':x['sha256']} for x in base['helper_imports']]},'helpers':base['helper_imports'],'official_commit':n.SEMANTIC_COMMIT,'metadata_paths':metadata,'binary_sha256':'synthetic-binary'})
        policy.update(declaration=declaration,metadata_paths=metadata)
        sample=n.finite_metadata_sample(policy,{'mdm_before':{'synthetic':False},'mdm_after':{'synthetic':False},'files':metadata})
        argv=['/opt/homebrew/bin/codex','--no-daemon','-a','never','app-server','--strict-config','--stdio']
        for value in policy['overrides']:argv+=['-c',value]
        environment={'identity_sha256':{'HOME':hashlib.sha256(str(work/'SYNTHETIC-home').encode()).hexdigest()},'selector_names':[],'default_home':True,'default_codex_home':True,'selected_environment_file':{'exists':False}}
        launch={'environment':environment,'producer_schema':n.FINITE_PRODUCER_SCHEMA,'finite_policy':policy,'policy_metadata':sample,'actual_argv':argv,'identity':{'sha256':'synthetic-binary'}}
        projection=n.finite_policy_projection(data,policy);facts=n.config_facts(data,lambda c:{})
        installed=copy.deepcopy(base['checkpoint_installed'])
        catalog={'data':[{'cwd':policy['root'],'errors':[],'skills':[{'name':v['name'],'path':v['path'],'enabled':True} for v in installed]}]}
        wire=[]
        for ident,method in enumerate(('initialize','initialized','config/read','skills/list','config/read')):
            wire.append({'direction':'request','payload':{'id':ident,'method':method}})
            if method=='initialized':continue
            payload={'id':ident,'status':'ok','receipt_schema':n.RECEIPT_VERSION,'structural_result':facts,'policy':projection} if method=='config/read' else {'id':ident,'result':catalog if method=='skills/list' else {}}
            wire.append({'direction':'response_or_event','payload':copy.deepcopy(payload)})
        for index,entry in enumerate(wire):entry.update(wire_index=index,monotonic_ns=index)
        pf={'finite-prelaunch.json':save('pre.json',sample),'preflight.json':save('preflight.json',{'first':sample,'second':sample,'transport':'live'})}
        for kind in ('catalog','live'):
            pf[kind+'-rpc/launch.json']=save(kind+'/launch.json',dict(launch,process_id=777 if kind=='live' else 111,cwd=policy['root']))
            pf[kind+'-rpc/closed.json']=save(kind+'/closed.json',{'stable':True,'policy_metadata':sample})
        pf['catalog-rpc/rpc.json']=save('catalog/rpc.json',wire)
        record={'root':policy['root'],'realroot':policy['canonical_root'],'producer_schema':n.FINITE_PRODUCER_SCHEMA,'finite_policy_declaration':declaration,'collector_sha256':producer_hash,'process_id':777,'healthy':False,'policy_facts':pf,'facts':{'live-rpc/closed.json':pf['live-rpc/closed.json']}}
        producer=dict(base,producer_schema=n.FINITE_PRODUCER_SCHEMA,finite_policy_declaration=declaration,adapter_sha256=producer_hash)
        producer['usage']=n.finite_recipe_usage(base,producer)
        pair={'native_delta.py':producer_hash,'native_delta_test.py':n.sha(archived_test)}
        producer['protected_files']=[dict(v,sha256=pair[Path(v['path']).name]) if v['path'].endswith(tuple('/tests/runtime/codex/'+name for name in pair)) else dict(v) for v in base['protected_files']]
        producer['checkpoint_installed']=installed

        recipe_ref=save('recipe.json',producer);record['recipe']=recipe_ref
        lookup=FiniteSessionTrustRepairTests.lookup_fixture(policy,data,producer_hash,recipe_ref['sha256'],producer['release_manifest_sha256'],'synthetic-binary')
        lookup_ref=save('lookup.json',lookup)
        expected=FiniteSessionTrustRepairTests.expected_fixture(policy)
        native={'forward_thread_expectation':expected,'unchanged_startup':lookup_ref}
        record['fixture_release']={'native_premises':save('native-premises.json',native)}
        pf['finite-lookup-input.json']=save('lookup-input.json',{'current_receipt':lookup_ref,'failure_stage':'before-live'})
        tree=ast.parse(Path(n.__file__).read_text());definition=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='workflow_usage');helper=next(x for x in definition.body if isinstance(x,ast.FunctionDef) and x.name=='finite_policy_history');ns=dict(n.__dict__);exec(compile(ast.Module(body=[helper],type_ignores=[]),n.__file__,'exec'),ns)
        return ns['finite_policy_history'],record,producer,wire,policy,save

    def test_retained_zero_failed_history_never_reads_current_host_or_executes_producer(self):
        from unittest import mock
        for failed in (False,True):
            with self.subTest(failed=failed),tempfile.TemporaryDirectory() as tmp:
                fixture=FiniteSessionTrustRepairTests.failed_fixture(Path(tmp)) if failed else self.history_fixture(Path(tmp))
                replay,r,p,w,policy,save=fixture
                with mock.patch.object(Path,'home',side_effect=AssertionError('today HOME')),mock.patch.object(n.subprocess,'Popen',side_effect=AssertionError('archived execution')):
                    self.assertEqual(replay(r,p,w,r['fixture_release']),policy)
                self.assertEqual(sum(x['payload'].get('method')=='turn/start' for x in w),int(failed))


    def test_rehashed_policy_history_strip_downgrade_origin_raw_and_argv_attacks(self):
        for change in ('strip','downgrade','producer','origin','fingerprint','candidate','raw','argv','close','missing-launch','metadata','recipe-protected','recipe-usage'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as tmp:
                replay,r,p,w,policy,save=self.history_fixture(Path(tmp))
                if change=='strip':r.pop('finite_policy_declaration')
                elif change=='downgrade':r['producer_schema']='legacy'
                elif change=='producer':p['adapter_sha256']='different'
                elif change=='missing-launch':r['policy_facts'].pop('live-rpc/launch.json')
                elif change=='recipe-protected':p['protected_files']=p['protected_files'][:-1]
                elif change=='recipe-usage':p['usage']=p['usage'][:-1]
                elif change in ('origin','fingerprint','candidate','raw'):
                    v=next(x['payload'] for x in w if 'policy' in x['payload'])
                    if change=='origin':v['policy'].pop('origin')
                    elif change=='fingerprint':v['policy']['session_version']='wrong'
                    elif change=='candidate':v['policy']['persistent_layers'][0]['candidates'][0]['present']=True
                    else:v['policy']['response_identity']['sha256']='wrong'
                    r['policy_facts']['catalog-rpc/rpc.json']=save('rehash-wire.json',w)
                elif change=='argv':
                    launch=n.checked_json(r['policy_facts']['live-rpc/launch.json']);launch['actual_argv']+=['-c','unrelated=true'];r['policy_facts']['live-rpc/launch.json']=save('rehash-launch.json',launch)
                elif change=='close':r['facts']['live-rpc/closed.json']=save('rehash-close.json',{'stable':True})
                else:
                    doc=n.checked_json(r['policy_facts']['finite-prelaunch.json']);doc['files']={};r['policy_facts']['finite-prelaunch.json']=save('rehash-pre.json',doc)
                with self.assertRaises(RuntimeError):replay(r,p,w,r['fixture_release'])

    def test_run_row_bootstrap_calls_are_confined_to_legacy_branch(self):
        import ast
        tree=ast.parse(Path(n.__file__).read_text());run=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='run_row')
        probes=[x for x in ast.walk(run) if isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr=='probe']
        self.assertEqual(len(probes),3)
        branch=next(x for x in ast.walk(run) if isinstance(x,ast.If) and ast.unparse(x.test)=='policy' and any(isinstance(y,ast.FunctionDef) and y.name=='metadata_sample' for y in x.body))
        self.assertTrue(any(x is probes[0] or x is probes[1] for stmt in branch.orelse for x in ast.walk(stmt)))
        second=next(x for x in ast.walk(run) if isinstance(x,ast.IfExp) and ast.unparse(x.test)=='policy' and isinstance(x.orelse,ast.Call) and isinstance(x.orelse.func,ast.Attribute) and x.orelse.func.attr=='probe')
        self.assertEqual(ast.unparse(second.body),'metadata_sample()')

    def test_current_declaration_binding_requires_exact_inputs_and_native_instructions(self):
        import ast
        from unittest import mock
        policy,data=self.fixture();choice_ref={'path':str(n.SOURCE/'.omx/ultragoal/evidence/r7-parent-verification/closure-session-trust-implementation-scope/operator-choice.json'),'sha256':n.FINITE_CHOICE_SHA256}
        choice=n.checked_json(choice_ref);base=n.checked_json(choice['base_recipe']);cp=n.checked_json(choice['checkpoint'])
        tree=ast.parse(Path(n.__file__).read_text());run=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='run_row');definition=next(x for x in run.body if isinstance(x,ast.FunctionDef) and x.name=='bind_finite_session_policy');ns=dict(n.__dict__);exec(compile(ast.Module(body=[definition],type_ignores=[]),n.__file__,'exec'),ns);bind=ns['bind_finite_session_policy']
        for mutation in ('valid','source','tests','binary','contributors','AGENTS','dot-codex','protected','USER','usage-omit','usage-duplicate','usage-order','usage-foreign','usage-second-zero','missing-sidecar','missing-zero'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);home=work/'SYNTHETIC-home/.codex';root=Path(policy['root']);canonical=Path(policy['canonical_root'])
                paths={x['path']:{'exists':True,'sha256':x['sha256'],'realpath':x['path']} for x in base['protected_files']}
                paths[str(root/'AGENTS.md')]={'exists':True,'sha256':choice['AGENTS_sha256'],'realpath':str(canonical/'AGENTS.md')}
                contributors={Path('/etc/codex/config.toml'),Path('/etc/codex/requirements.toml'),Path('/etc/codex/managed_config.toml'),home/'managed_config.toml',home/'config.toml',home/'hooks.json',home/'environments.toml',root/'.codex',canonical/'.codex'}
                for ancestor in {root,*root.parents,canonical,*canonical.parents}:contributors.update((ancestor/'.codex/config.toml',ancestor/'.codex/hooks.json'))
                paths.update({str(p):{'exists':False,'sha256':None,'realpath':str(p)} for p in contributors})
                paths.update({v['path']:{'exists':True,'sha256':v['sha256'],'realpath':v['path']} for v in (n.SPEC_CLOSURE_ZERO_DISPOSITION,n.SPEC_CLOSURE_ZERO_CONTEXT)})
                declaration={'synthetic_fixture_only':True,'schema':'ROOT_FINITE_SESSION_TRUST_DECLARATION_V1','decision':'DECLARE_EXACT_PROCESS_ONLY_POLICY','operator_choice':choice_ref,'base_recipe':choice['base_recipe'],'checkpoint':choice['checkpoint'],'product':choice['product'],'collector_sha256':n.sha(n.__file__),'tests_sha256':n.sha(Path(n.__file__).with_name('native_delta_test.py')),'helpers':base['helper_imports'],'official_commit':n.SEMANTIC_COMMIT,'binary_sha256':'synthetic-binary','metadata_paths':paths}
                recipe=copy.deepcopy(base);recipe['producer_schema']=n.FINITE_PRODUCER_SCHEMA;recipe['adapter_sha256']=n.sha(n.__file__)
                recipe['usage']=list(base['usage'])+[dict(n.SPEC_CLOSURE_ZERO_CONTEXT)]
                pair={str(Path(n.__file__)):n.sha(n.__file__),str(Path(n.__file__).with_name('native_delta_test.py')):n.sha(Path(n.__file__).with_name('native_delta_test.py'))}
                recipe['protected_files']=[dict(v,sha256=pair.get(v['path'],v['sha256'])) for v in recipe['protected_files']]
                for path,digest in pair.items():paths[path]['sha256']=digest
                for role,source in (('collector',Path(n.__file__)),('tests',Path(n.__file__).with_name('native_delta_test.py'))):
                    target=work/(role+'-archive-DATA.py');target.write_bytes(source.read_bytes())
                    declaration.setdefault('producer',{})[role]={'path':str(target),'sha256':n.sha(target)}
                declaration['producer']['helpers']=[{'path':str(n.SOURCE/x['path']),'sha256':x['sha256']} for x in base['helper_imports']]
                binding={'executable_identity':{'sha256':'synthetic-binary'},'forward_thread_expectation':{'instructionSources':[str(root/'AGENTS.md')]}}
                if mutation in ('source','tests','binary'):declaration[{'source':'collector_sha256','tests':'tests_sha256','binary':'binary_sha256'}[mutation]]='stale'
                elif mutation=='contributors':paths.pop(str(home/'hooks.json'))
                elif mutation=='AGENTS':binding['forward_thread_expectation']['instructionSources']=[]
                elif mutation=='dot-codex':paths[str(root/'.codex')]['exists']=True
                elif mutation=='protected':paths[base['protected_files'][0]['path']]['sha256']='drift'
                elif mutation=='USER':recipe['rows'][0]['initial_user_text']='different'
                elif mutation=='usage-omit':recipe['usage'].pop()
                elif mutation in ('usage-duplicate','usage-second-zero'):recipe['usage'].append(dict(n.SPEC_CLOSURE_ZERO_CONTEXT))
                elif mutation=='usage-order':recipe['usage'][-2:]=list(reversed(recipe['usage'][-2:]))
                elif mutation=='usage-foreign':recipe['usage'][-1]={'path':'/foreign-not-read','sha256':'0'*64}
                elif mutation in ('missing-sidecar','missing-zero'):paths.pop((n.SPEC_CLOSURE_ZERO_DISPOSITION if mutation=='missing-sidecar' else n.SPEC_CLOSURE_ZERO_CONTEXT)['path'])
                target=work/'synthetic-declaration-DATA.json';n.write(target,declaration);ref={'path':str(target),'sha256':n.sha(target)};recipe['finite_policy_declaration']=ref
                real_sha=n.sha;real_resolve=Path.resolve
                def resolve(p,*a,**kw):return canonical if str(p)==str(root) else real_resolve(p,*a,**kw)
                def digest(p):return choice['AGENTS_sha256'] if str(p)==str(root/'AGENTS.md') else real_sha(p)
                with mock.patch.object(Path,'home',return_value=home.parent),mock.patch.object(Path,'resolve',resolve),mock.patch.dict(ns,{'sha':digest,'workflow_inventory':lambda *a:cp['state']}):
                    if mutation=='valid':self.assertEqual(bind(ref,recipe,root,binding)['declaration'],ref)
                    else:
                        with self.assertRaises(RuntimeError):bind(ref,recipe,root,binding)

    def test_actual13_and_native_receipt_keep_policy_required(self):
        p,d=self.fixture();p['declaration']={'path':'SYNTHETIC-DATA','sha256':'draft'}
        binding={'official_commit':n.SEMANTIC_COMMIT,'parent_release_id':'SYNTHETIC-only','transports':['live'],'proof_sha256':'synthetic-proof','finite_session_policy':p,'_finite_policy_observation':n.finite_policy_projection(d,p)}
        receipt=n.native_selection_receipt(binding,{'enabled_unique_targets':16,'load_errors':0},{'selected_environment_kind':'local','required_skills':[]},'live')
        self.assertEqual(receipt['producer_schema'],n.FINITE_PRODUCER_SCHEMA);self.assertEqual(receipt['policy_declaration'],p['declaration'])
        missing=copy.deepcopy(binding);missing.pop('_finite_policy_observation')
        with self.assertRaises(RuntimeError):n.native_selection_receipt(missing,{'enabled_unique_targets':16,'load_errors':0},{'selected_environment_kind':'local','required_skills':[]},'live')
        for key in n.THREAD_FIELDS:
            with self.subTest(missing=key),self.assertRaises(RuntimeError):n.reconcile_thread({k:None for k in n.THREAD_FIELDS if k!=key},{},{k:None for k in n.THREAD_FIELDS})
        for catalog in ({'enabled_unique_targets':15,'load_errors':0},{'enabled_unique_targets':16,'load_errors':1}):
            with self.assertRaises(RuntimeError):n.native_selection_receipt(binding,catalog,{'selected_environment_kind':'local','required_skills':[]},'live')



class FiniteSessionTrustRepairTests(unittest.TestCase):
    def test_locally_computed_identity_receipt_matches_direct_lookup_and_is_idempotent(self):
        import json
        cfg={'model':'gpt-6.1-sol','api_key':'PRIVATE-API-CREDENTIAL',
             'developer_instructions':'PRIVATE-INSTRUCTION-TEXT',
             'environment':{'PRIVATE_VARIABLE':'PRIVATE-ENV-VALUE'},
             'model_providers':{'openai':{'api_key':'PRIVATE-PROVIDER-KEY',
                                       'http_headers':{'X-Private':'PRIVATE-HEADER'}}}}
        policy={'config_identity':n.safe_config_identity(cfg),
                'response_identity':n.safe_config_identity({'config':cfg,'layers':[{'config':cfg}]})}
        direct_lookup=json.loads(json.dumps(policy))
        retained=n.finite_receipt(policy)
        self.assertEqual(json.loads(json.dumps(retained)),direct_lookup)
        self.assertEqual(n.finite_receipt(retained),retained)
        self.assertEqual(n.finite_receipt(copy.deepcopy(policy)),retained)
        self.assertIsNot(type(policy['config_identity']),dict)
        self.assertIs(type(copy.deepcopy(policy['config_identity'])),type(policy['config_identity']))
        self.assertIs(type(direct_lookup['config_identity']),dict)
        for secret in ('PRIVATE-API-CREDENTIAL','PRIVATE-INSTRUCTION-TEXT','PRIVATE-ENV-VALUE',
                       'PRIVATE-PROVIDER-KEY','PRIVATE-HEADER'):
            self.assertNotIn(secret,json.dumps(retained))

    def test_identity_lookalikes_and_private_containers_still_use_generic_redaction(self):
        import json
        cfg={'api_key':'PRIVATE-RAW-KEY','developer_instructions':'PRIVATE-RAW-INSTRUCTION',
             'environment':{'key':'PRIVATE-RAW-ENV'}}
        local=n.safe_config_identity(cfg)
        decoded=json.loads(json.dumps(local))
        self.assertEqual(n.finite_receipt(decoded),n.redacted_config(decoded))
        self.assertNotEqual(n.finite_receipt(decoded),decoded)
        forged=copy.deepcopy(decoded)
        forged['schema']['api_key']='PRIVATE-FORGED-SCHEMA'
        forged['fields']['api_key']='PRIVATE-FORGED-KEY'
        forged['fields']['developer_instructions']='PRIVATE-FORGED-INSTRUCTION'
        value={'raw':cfg,'lookalike':forged,'api_key':local}
        retained=n.finite_receipt(value)
        self.assertEqual(retained,n.redacted_config(value))
        for secret in ('PRIVATE-RAW-KEY','PRIVATE-RAW-INSTRUCTION','PRIVATE-RAW-ENV',
                       'PRIVATE-FORGED-SCHEMA','PRIVATE-FORGED-KEY','PRIVATE-FORGED-INSTRUCTION'):
            self.assertNotIn(secret,json.dumps(retained))

    def test_marked_identity_rejects_mutated_shape_and_unsafe_payloads(self):
        for mutation in ('extra','digest','valid-digest-change','field-digest','schema-leaf','schema-type-change','schema-fields','auth-claim','version'):
            with self.subTest(mutation=mutation):
                identity=n.safe_config_identity({'api_key':'PRIVATE-CREDENTIAL',
                                                 'developer_instructions':'PRIVATE-INSTRUCTION'})
                if mutation=='extra':identity['raw_payload']='PRIVATE-UNSAFE-EXTRA'
                elif mutation=='digest':identity['sha256']='g'*64
                elif mutation=='valid-digest-change':identity['sha256']='0'*64
                elif mutation=='field-digest':identity['fields']['api_key']='PRIVATE-UNSAFE-FIELD'
                elif mutation=='schema-leaf':identity['schema']['api_key']='PRIVATE-UNSAFE-SCHEMA'
                elif mutation=='schema-type-change':identity['schema']['api_key']={'redacted':'str','type':'str'}
                elif mutation=='schema-fields':identity['fields'].pop('api_key')
                elif mutation=='auth-claim':identity['auth_stability_claim']=True
                else:identity['schema_version']='foreign'
                with self.assertRaises(RuntimeError):n.finite_receipt({'identity':identity})

    @staticmethod
    def metadata_fixture(recipe,choice,home):
        root=Path(choice['root']);canonical=Path(choice['canonical_root']);user=home/'.codex'
        paths={v['path']:{'exists':True,'sha256':v['sha256'],'realpath':v['path']} for v in recipe['protected_files']}
        paths[str(root/'AGENTS.md')]={'exists':True,'sha256':choice['AGENTS_sha256'],'realpath':str(canonical/'AGENTS.md')}
        contributors={Path('/etc/codex/config.toml'),Path('/etc/codex/requirements.toml'),Path('/etc/codex/managed_config.toml'),user/'managed_config.toml',user/'config.toml',user/'hooks.json',user/'environments.toml',root/'.codex',canonical/'.codex'}
        for ancestor in {root,*root.parents,canonical,*canonical.parents}:contributors.update((ancestor/'.codex/config.toml',ancestor/'.codex/hooks.json'))
        paths.update({str(p):{'exists':False,'sha256':None,'realpath':str(p)} for p in contributors})
        paths.update({v['path']:{'exists':True,'sha256':v['sha256'],'realpath':v['path']} for v in (n.SPEC_CLOSURE_ZERO_DISPOSITION,n.SPEC_CLOSURE_ZERO_CONTEXT)})
        return paths

    @staticmethod
    def expected_fixture(policy):
        root=policy['root']
        return {'model':'gpt-6.1-sol','modelProvider':'openai','serviceTier':None,'reasoningEffort':'high','cwd':root,'runtimeWorkspaceRoots':[root],'instructionSources':[root+'/AGENTS.md'],'approvalPolicy':'never','approvalsReviewer':'user','sandbox':{'type':'workspaceWrite','networkAccess':False,'writableRoots':[root]},'activePermissionProfile':None,'disabledPluginIds':[],'multiAgentMode':'explicitRequestOnly'}

    @staticmethod
    def lookup_fixture(policy,data,collector,recipe,manifest,binary):
        projection=n.finite_policy_projection(data,policy)
        candidates=[{'category':label,'path':path,'present':path==policy['canonical_root'],'trust':'trusted' if path==policy['canonical_root'] else None,'origin_identity':n.canonical_hash(projection['origin'] if path==policy['canonical_root'] else None)} for label,path in [('cwd-canonical',policy['canonical_root']),('cwd-original',policy['root']),('repo-canonical',policy['canonical_root']),('repo-original',policy['root'])]]
        def identity(path):return {'path':path,'realpath':policy['canonical_root'],'device':123,'inode':456,'mode':448}
        classification={'schema':'startup-trust-lookup-v1','commit':n.SEMANTIC_COMMIT,'sources':n.STARTUP_LOOKUP_SOURCES,'skip_predicate':'existing-active-project','active_project':candidates[0],'project_layer_count':0,'marker_root':policy['root'],'checkout_root':policy['root'],'cwd':identity(policy['root']),'repo':identity(policy['root']),'trust_root':identity(policy['canonical_root']),'candidates':candidates,'layer_identities':['SYNTHETIC layer DATA' for _ in data['layers']],'config_identity':projection['response_identity']['sha256'],'auth_stability_claim':False,'historical_cause':'UNKNOWN'}
        return {'schema':'startup-no-write-owned-fixture-policy-v2','collector_sha256':collector,'recipe_sha256':recipe,'manifest_sha256':manifest,'binary_sha256':binary,'declaration':policy['declaration'],'mode':'existing-active-project','classification':classification,'policy':projection}

    @staticmethod
    def failed_fixture(work,scope="default"):
        replay,r,p,original,policy,save=FiniteSessionTrustTests().history_fixture(work,scope)
        wire=copy.deepcopy(original[:3]);seq=100
        data=FiniteSessionTrustTests().fixture(scope)[1];projection=n.finite_policy_projection(data,policy);facts=n.config_facts(data,lambda c:{})
        catalog=next(e['payload']['result'] for e in original if 'data' in e['payload'].get('result',{}))
        environment=n.checked_json(r['policy_facts']['live-rpc/launch.json'])['environment'];expected=FiniteSessionTrustRepairTests.expected_fixture(policy)
        premises=n.checked_json(r['fixture_release']['native_premises']);premises.update(official_commit=n.SEMANTIC_COMMIT,parent_release_id='SYNTHETIC-only',transports=['live'],proof_sha256='SYNTHETIC-proof',executable_identity={'sha256':'synthetic-binary'})
        r['fixture_release']['native_premises']=save('native-premises.json',premises)
        def emit(direction,payload):wire.append({'direction':direction,'payload':copy.deepcopy(payload),'wire_index':len(wire),'monotonic_ns':len(wire)})
        def call(method,params,value):
            nonlocal seq
            seq+=1;emit('request',{'id':seq,'method':method,'params':params})
            emit('response_or_event',{'id':seq,'status':'ok','receipt_schema':n.RECEIPT_VERSION,'structural_result':facts,'policy':projection} if method=='config/read' else {'id':seq,'result':value})
        start=len(wire);call('config/read',{'includeLayers':True,'cwd':policy['root']},None);call('skills/list',{'cwds':[policy['root']],'forceReload':True},catalog)
        proof={'enabled_unique_targets':16,'applicable_catalog_entries':16,'load_errors':0,'target_paths':[v['path'] for v in catalog['data'][0]['skills']],'layer_root_sources':[v['source'] for v in facts['layers']],'loader_relation':'Actual live RPC active config/catalog; no ignored-user projection','semantic_source':n.SEMANTIC_COMMIT,'universal_global_catalog_claim':False}
        native=n.native_selection_receipt(dict(premises,finite_session_policy=policy,_finite_policy_observation=projection),proof,n.require_environment(environment,premises),'live');native['closure_wire']={'schema':'spec-closure-native-wire-v1','wire_start_index':start,'wire_end_index':len(wire)}
        r['facts']['live-native-selection-receipt.json']=save('native-selection.json',native)
        choice=n.checked_json(n.checked_json(policy['declaration'])['operator_choice']);state=n.checked_json(choice['checkpoint'])['state'];r['scope_facts']={};r['thread_id']='SYNTHETIC-thread'
        frames=[]
        def bundle(index,phase):
            start=len(wire)
            call('config/read',{'includeLayers':True,'cwd':policy['root']},None);call('skills/list',{'cwds':[policy['root']],'forceReload':True},catalog);call('config/read',{'includeLayers':True,'cwd':policy['root']},None)
            frame={'schema_version':n.RECEIPT_VERSION,'config':facts,'catalog':catalog,'catalog_proof':proof,'finite_policy':projection,'policy_metadata':n.checked_json(r['policy_facts']['finite-prelaunch.json']),'environment':environment,'installed':p['checkpoint_installed'],'process_id':r['process_id'],'thread_id':None if index==0 else r['thread_id'],'files':copy.deepcopy(policy['metadata_paths']),'manifest_sha256':p['release_manifest_sha256'],'binary_sha256':'synthetic-binary'}
            ref=save('bundle-%03d.json'%index,frame);r['scope_facts']['workflow-closure-bundle-%03d.json'%index]=ref
            r['scope_facts']['workflow-closure-sample-%03d.json'%index]=save('sample-%03d.json'%index,{'schema':'spec-closure-sample-v2','bundle_id':index,'phase':phase,'frame':ref,'stable':True,'before':state,'after':state,'process_id':r['process_id'],'thread_id':frame['thread_id'],'wire_start_index':start,'wire_end_index':len(wire)})
            frames.append(frame)
        bundle(0,'preflight');request={'cwd':policy['root'],'model':'gpt-6.1-sol','approvalPolicy':'never','sandbox':'workspace-write','ephemeral':True};actual=dict(expected,thread={'id':r['thread_id'],**{k:expected[k] for k in ('cwd','model','modelProvider','reasoningEffort')}})
        start=len(wire);call('thread/start',request,actual)
        r['facts']['thread-start-v3.json']=save('thread.json',{'schema_version':n.RECEIPT_VERSION,'process_id':r['process_id'],'request':request,'response':actual,'wire_start_index':start,'wire_end_index':len(wire)})
        bundle(1,'post-start-1');bundle(2,'post-start-2')
        r['facts']['poststart-baseline-v3.json']=save('baseline.json',{'snapshot':n.reconcile_thread(actual,request,expected),'first':frames[1],'second':frames[2],'wire_end_index':len(wire)})
        bundle(3,'predispatch')
        certificate=n.checked_json(premises['unchanged_startup']);classification=certificate['classification']
        r['policy_facts']['startup-diagnostic-v3.json']=save('diagnostic.json',{'startup_raw_equal':True,'post_bundle_lookup':classification,'no_write_lookup':{'schema':certificate['schema'],'before':classification,'after':classification,'policy':projection,'declaration':policy['declaration'],'mode':certificate['mode'],'current_receipt':premises['unchanged_startup']}})
        r['policy_facts']['finite-lookup-input.json']=save('dispatched-input.json',{'current_receipt':premises['unchanged_startup'],'failure_stage':'dispatched'})
        emit('request',{'id':999,'method':'turn/start','params':{'threadId':r['thread_id'],'input':[{'type':'text','text':p['rows'][0]['initial_user_text']}]}})
        return replay,r,p,wire,policy,save

    def test_copy_failed_dispatch_replay_denies_duplicate_USER(self, scope="copy"):
        with tempfile.TemporaryDirectory() as tmp:
            replay,r,p,w,policy,save=self.failed_fixture(Path(tmp),scope)
            self.assertEqual(replay(r,p,w,r['fixture_release']),policy)
            w.append(copy.deepcopy(next(e for e in w if e['payload'].get('method')=='turn/start')))
            with self.assertRaises(RuntimeError):replay(r,p,w,r['fixture_release'])

    def test_D2_failed_dispatch_replay_denies_duplicate_USER(self):
        self.test_copy_failed_dispatch_replay_denies_duplicate_USER('D2')

    def test_complete_failed_dispatch_positive_then_wire_and_diagnostic_attacks(self):
        for mutation in ('valid','missing-thread','foreign-process','foreign-thread','config-error','layer-order','bundle-range','bundle-frame','missing-diagnostic','null-classification','missing-input','lookup-recipe','lookup-mode','lookup-origin'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                replay,r,p,w,policy,save=self.failed_fixture(Path(tmp));release=r['fixture_release']
                self.assertEqual(replay(r,p,w,release),policy)
                if mutation=='missing-thread':
                    for e in w:
                        if e['payload'].get('method')=='thread/start':e['payload']['method']='detached/start'
                elif mutation in ('foreign-process','foreign-thread'):
                    key='process_id' if mutation=='foreign-process' else 'thread_id';value=9999 if key=='process_id' else 'FOREIGN'
                    baseline=n.checked_json(r['facts']['poststart-baseline-v3.json'])
                    for side in ('first','second'):baseline[side][key]=value
                    r['facts']['poststart-baseline-v3.json']=save('bad-baseline.json',baseline)
                    for i in range(1,4):
                        name='workflow-closure-bundle-%03d.json'%i;frame=n.checked_json(r['scope_facts'][name]);frame[key]=value;r['scope_facts'][name]=save('bad-frame-%d.json'%i,frame)
                elif mutation=='config-error':w[4]['payload']['status']='error'
                elif mutation=='layer-order':
                    for event in w:
                        structural=event['payload'].get('structural_result')
                        if structural is not None:structural['layers'].reverse()
                elif mutation in ('bundle-range','bundle-frame'):
                    name='workflow-closure-sample-003.json';sample=n.checked_json(r['scope_facts'][name]);sample['wire_end_index' if mutation=='bundle-range' else 'frame']=0 if mutation=='bundle-range' else r['scope_facts']['workflow-closure-bundle-002.json'];r['scope_facts'][name]=save('bad-sample.json',sample)
                elif mutation=='missing-diagnostic':r['policy_facts'].pop('startup-diagnostic-v3.json')
                elif mutation=='null-classification':
                    diagnostic=n.checked_json(r['policy_facts']['startup-diagnostic-v3.json']);diagnostic['no_write_lookup'].update(before=None,after=None);diagnostic['post_bundle_lookup']=None;r['policy_facts']['startup-diagnostic-v3.json']=save('bad-diagnostic.json',diagnostic)
                elif mutation=='missing-input':r['policy_facts'].pop('finite-lookup-input.json')
                elif mutation.startswith('lookup-'):
                    premises=n.checked_json(release['native_premises']);cert=n.checked_json(premises['unchanged_startup'])
                    if mutation=='lookup-recipe':cert['recipe_sha256']='wrong'
                    elif mutation=='lookup-mode':cert['mode']='projectless'
                    else:cert['policy']['origin']=None
                    ref=save('bad-lookup.json',cert);premises['unchanged_startup']=ref;release['native_premises']=save('bad-native.json',premises);r['policy_facts']['finite-lookup-input.json']=save('bad-input.json',{'current_receipt':ref,'failure_stage':'dispatched'})
                if mutation=='valid':self.assertEqual(replay(r,p,w,release),policy)
                else:
                    with self.assertRaises(RuntimeError):replay(r,p,w,release)

    def test_shared_metadata_rejects_rehashed_empty_missing_and_present_inputs(self):
        for mutation in ('empty','protected-presence','protected-hash','instruction-presence','AGENTS-canonical','user-hooks','ancestor','system-present','managed-present','root-dotcodex','ambiguous-home'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                replay,r,p,w,policy,save=FiniteSessionTrustTests().history_fixture(Path(tmp));decl=n.checked_json(policy['declaration']);choice=n.checked_json(decl['operator_choice']);paths=decl['metadata_paths'];instructions=self.expected_fixture(policy)['instructionSources']
                with unittest.mock.patch.object(Path,'home',side_effect=AssertionError('current HOME')):n.validate_finite_metadata(decl,p,instructions,choice)
                if mutation=='empty':paths.clear()
                elif mutation=='protected-presence':paths[p['protected_files'][0]['path']].update(exists=False,sha256=None)
                elif mutation=='protected-hash':paths[p['protected_files'][0]['path']]['sha256']='0'*64
                elif mutation=='instruction-presence':paths[instructions[0]].update(exists=False,sha256=None)
                elif mutation=='AGENTS-canonical':paths[instructions[0]]['realpath']='/foreign/AGENTS.md'
                elif mutation=='user-hooks':paths.pop(next(p for p in paths if 'SYNTHETIC-home/.codex/hooks.json' in p))
                elif mutation=='ancestor':paths.pop(str(Path(policy['root']).parent/'.codex/hooks.json'))
                elif mutation=='system-present':paths['/etc/codex/config.toml'].update(exists=True,sha256='0'*64)
                elif mutation=='managed-present':paths[next(p for p in paths if 'SYNTHETIC-home/.codex/managed_config.toml' in p)].update(exists=True,sha256='0'*64)
                elif mutation=='root-dotcodex':paths[policy['root']+'/.codex'].update(exists=True,sha256='0'*64)
                else:paths['/other-home/.codex/environments.toml']={'exists':False,'sha256':None,'realpath':'/other-home/.codex/environments.toml'}
                with self.assertRaises(RuntimeError):n.validate_finite_metadata(decl,p,instructions,choice)

    def test_all_archives_checked_before_admission_and_bytes_never_executed(self):
        from unittest import mock
        for mutation in ('missing','collector','tests','helper-byte','helper-order','helper-omit'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                _,r,p,w,policy,save=FiniteSessionTrustTests().history_fixture(Path(tmp));decl=n.checked_json(policy['declaration'])
                n.validate_finite_producer(decl,p['helper_imports'])
                if mutation=='missing':decl.pop('producer')
                elif mutation in ('collector','tests'):decl['producer'][mutation]['sha256']='0'*64
                elif mutation=='helper-byte':decl['producer']['helpers'][0]={'path':decl['producer']['collector']['path'],'sha256':p['helper_imports'][0]['sha256']}
                elif mutation=='helper-order':decl['producer']['helpers'].reverse()
                else:decl['producer']['helpers'].pop()
                with mock.patch.object(n.subprocess,'Popen',side_effect=AssertionError('archive executed')),self.assertRaises(RuntimeError):n.validate_finite_producer(decl,p['helper_imports'])

    def test_real_finite_run_row_recorded_rpc_bundle_close_and_usage_roundtrip(self, scope="D2"):
        """Read the exact frozen fixture/binary; never execute or mutate either.

        Requires the Root-authorized exact unused D2live151/binary read scope. SOURCE,
        __file__, path resolution, sha, admission, serializers and replay stay real.
        Only subprocess execution, RPC transport and fixture MDM are faked.
        """
        import argparse,contextlib,io,json,types
        from unittest import mock
        self.assertEqual(Path(n.__file__).resolve(),n.SOURCE/'tests/runtime/codex/native_delta.py')
        row_id={'default':'codex-default-authentic-preanswer','copy':'codex-copy-equivalent-preanswer','D2':'codex-copy-D2-authentic-pre-v57-answer'}[scope]
        choice_ref=next(v for v in n.FINITE_SCOPES.values() if v['row_id']==row_id)['operator_choice']
        choice=n.checked_json(choice_ref);base=n.checked_json(choice['base_recipe']);cp=n.checked_json(choice['checkpoint']);root=Path(choice['root'])
        executable=Path('/opt/homebrew/bin/codex');binary=executable.resolve()
        self.assertEqual(n.sha(binary),'d8990e3ee7acfbc26f91265b12a1a83f0fee40d0e0f8f1f40a37d4ec21f499cf')
        original_state=n.workflow_inventory(root)
        self.assertEqual(original_state,cp['state'])
        for outcome in ('healthy','failed','zero-before-thread'):
            failed=outcome!='healthy';zero=outcome=='zero-before-thread'
            with self.subTest(outcome=outcome),tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);home=work/'fixture-home';home.mkdir()
                def ref(path):return {'path':str(path),'sha256':n.sha(path)}
                def save(name,data):path=work/name;path.parent.mkdir(parents=True,exist_ok=True);n.write(path,data);return ref(path)
                report=work/'synthetic-review-DATA.md';report.write_text('SYNTHETIC TEST DATA ONLY. No actual Root declaration/release/lookup/model authority.')
                pair={str(n.SOURCE/'tests/runtime/codex'/name):n.sha(n.SOURCE/'tests/runtime/codex'/name) for name in ('native_delta.py','native_delta_test.py')}
                recipe=copy.deepcopy(base);recipe.update(adapter_sha256=pair[str(Path(n.__file__))],producer_schema=n.FINITE_PRODUCER_SCHEMA)
                recipe['usage']=n.finite_recipe_usage(base,recipe)
                recipe['protected_files']=[dict(v,sha256=pair.get(v['path'],v['sha256'])) for v in base['protected_files']]
                policy,raw=FiniteSessionTrustTests().fixture(scope);raw['layers'][1]['name']['file']=str(home/'.codex/config.toml')
                private={'developer_instructions':'PRIVATE-INTEGRATION-INSTRUCTIONS','model_providers':{'custom':{'experimental_bearer_token':'PRIVATE-INTEGRATION-TOKEN','http_headers':{'Authorization':'PRIVATE-INTEGRATION-HEADER'}}}}
                raw['config'].update(copy.deepcopy(private));raw['config']['skills']=None
                raw['layers'][1]['config'].update(copy.deepcopy(private))
                raw['layers'][1]['version']='sha256:'+n.canonical_hash(raw['layers'][1]['config'])
                paths=self.metadata_fixture(recipe,choice,home)
                paths={path:{'exists':Path(path).exists(),'sha256':n.sha(path) if Path(path).is_file() else None,'realpath':str(Path(path).resolve())} for path in paths}
                archives={}
                for role,name in (('collector','native_delta.py'),('tests','native_delta_test.py')):
                    path=work/('archive/'+name);path.parent.mkdir(exist_ok=True);path.write_bytes((n.SOURCE/'tests/runtime/codex'/name).read_bytes());archives[role]=ref(path)
                archives['helpers']=[]
                for entry in base['helper_imports']:
                    path=work/'archive'/Path(entry['path']).name;path.write_bytes((n.SOURCE/entry['path']).read_bytes());archives['helpers'].append(ref(path))
                declaration={'synthetic_fixture_only':True,'schema':'ROOT_FINITE_SESSION_TRUST_DECLARATION_V1','decision':'DECLARE_EXACT_PROCESS_ONLY_POLICY','operator_choice':choice_ref,**{k:choice[k] for k in ('base_recipe','checkpoint','product')},'collector_sha256':pair[str(Path(n.__file__))],'tests_sha256':pair[str(Path(n.__file__).with_name('native_delta_test.py'))],'producer':archives,'helpers':base['helper_imports'],'official_commit':n.SEMANTIC_COMMIT,'binary_sha256':n.sha(binary),'metadata_paths':paths}
                declaration_ref=save('synthetic-declaration-DATA.json',declaration);recipe['finite_policy_declaration']=declaration_ref;recipe_ref=save('recipe.json',recipe)
                policy.update(declaration=declaration_ref,metadata_paths=paths)
                # Real unchanged classifier, backed by this exact read-only fixture.
                classification=n.startup_lookup(raw,root,choice['canonical_root'])
                lookup_ref=save('synthetic-lookup-DATA.json',{'schema':'startup-no-write-owned-fixture-policy-v2','collector_sha256':recipe['adapter_sha256'],'recipe_sha256':recipe_ref['sha256'],'manifest_sha256':recipe['release_manifest_sha256'],'binary_sha256':n.sha(binary),'mode':classification['skip_predicate'],'classification':classification,'policy':n.finite_policy_projection(raw,policy),'declaration':declaration_ref})
                expected=self.expected_fixture(policy);release_id='SYNTHETIC-finite-roundtrip-'+outcome
                binding={'transports':['live'],'forward_thread_expectation':expected,'forward_trust_root':choice['canonical_root'],'setup_artifact_contract':None,'official_commit':n.SEMANTIC_COMMIT,'proof_path':str(report),'proof_sha256':n.sha(report),'parent_release_id':release_id,'codex_version':'SYNTHETIC fixture version; no binary execution','scope':'configured-native-selector','executable_identity':{'sha256':n.sha(binary),'symlink_target':str(binary)},'finite_policy_declaration':declaration_ref,'unchanged_startup':lookup_ref}
                native=save('synthetic-native-DATA.json',binding);binding['workflow_native_premises_sha256']=native['sha256']
                common={'checkpoint_sha256':recipe['workflow_checkpoint']['sha256'],'recipe_sha256':recipe_ref['sha256'],'collector_sha256':recipe['adapter_sha256'],'helpers':recipe['helper_imports'],'manifest_sha256':recipe['release_manifest_sha256'],'native_premises_sha256':native['sha256'],'purpose':recipe['purpose'],'phase':recipe['phase'],'unit':recipe['unit']}
                source=save('synthetic-source-review-DATA.json',dict(common,schema='WORKFLOW_SOURCE_REVIEW_V1',decision='APPROVE_EXACT_BOUND_CONTEXT',report=ref(report)))
                material=n.checked_json(cp['materialization']);product=n.checked_json(material['product']);installed=n.checked_json(material['install']);program=n.checked_json(installed['program'])
                authority=[cp['materialization'],product['source_review'],installed['program'],material['origin']['oracle'],program['lock']]+[v for v in recipe['usage'] if n.checked_json(v).get('purpose')=='spec-closure-regression' and n.checked_json(v).get('row_id')==recipe['rows'][0]['id']]
                authority.extend((n.SPEC_CLOSURE_ZERO_DISPOSITION,n.SPEC_CLOSURE_ZERO_CONTEXT))
                review=save('synthetic-Root-review-DATA.json',dict(common,schema='WORKFLOW_ROOT_REVIEW_V1',decision='APPROVE_EXACT_BOUND_CONTEXT',report=ref(report),source_review=source,state_sha256=n.canonical_hash(cp['state']),usage_sha256=n.canonical_hash(recipe['usage']),authority_evidence=authority,business={'closure_materialization':cp['materialization']}))
                allocation=save('synthetic-allocation-DATA.json',{'actual_anchor':21,'held_anchor':85,'whole':106,'required':84,'reserve':1,'evidence':ref(report)})
                used=n.workflow_usage(recipe['usage']);row=recipe['rows'][0]
                release=save('synthetic-release-DATA.json',dict(common,schema='WORKFLOW_RELEASE_V1',release_id=release_id,source_review=source,root_review=review,native_premises=native,allocation=allocation,root=str(root),realroot=str(root.resolve()),row_id=row['id'],out=str(work/'out'),max_new_contexts=1,max_new_model_USER_turns=1,seconds=180,actual_before=21+sum(used.values()),held_before=85-sum(used.values()),whole=106,initial_USER_sha256=n.canonical_hash(row['initial_user_text'])))
                binding['workflow_release_sha256']=release['sha256'];binding_ref=save('binding.json',binding)
                args=argparse.Namespace(prepared=str(work),manifest=recipe['release_manifest'],native_binding=binding_ref['path'],row=row['id'],release_id=release_id,current_author_checkpoint=recipe['workflow_checkpoint']['path'],current_author_release=release['path'],out=str(work/'out'),setup_checkpoint=None,setup_checkpoint_review=None,derivative_release=None,packet=None)
                catalog={'data':[{'cwd':str(root),'errors':[],'skills':[{'name':v['name'],'path':v['path'],'enabled':True} for v in recipe['checkpoint_installed']]}]}
                processes=[];sent=[]
                class Process:
                    def __init__(self):self.pid=8000+len(processes);self.returncode=None;processes.append(self)
                    def poll(self):return self.returncode
                    def wait(self,timeout=None):self.returncode=0;return 0
                def popen(argv,**kwargs):
                    self.assertEqual(argv[0],str(executable));self.assertEqual(kwargs['cwd'],root);return Process()
                def send(rpc,obj):
                    rpc._synthetic_queue=getattr(rpc,'_synthetic_queue',[])
                    method=obj['method']
                    if method=='initialized':return
                    if method=='initialize':value={}
                    elif method=='config/read':
                        if zero and len(processes)==2:
                            rpc._synthetic_queue.append({'id':obj['id'],'error':{'code':-1,'message':'SYNTHETIC zero before thread'}});return
                        value=raw
                    elif method=='skills/list':value=catalog
                    elif method=='thread/start':value=dict(expected,thread={'id':'finite-producer-thread',**{k:expected[k] for k in ('cwd','model','modelProvider','reasoningEffort')}})
                    elif method=='turn/start':
                        sent.append(obj['params']);value={'turn':{'id':'finite-producer-turn'}}
                    else:raise AssertionError(method)
                    rpc._synthetic_queue.append({'id':obj['id'],'result':copy.deepcopy(value)})
                    if method=='turn/start':
                        rpc._synthetic_queue.extend([{'method':'turn/started','params':{'threadId':'finite-producer-thread','turn':{'id':'finite-producer-turn','status':'inProgress','error':None}}},{'method':'item/completed','params':{'threadId':'finite-producer-thread','turnId':'finite-producer-turn','item':{'id':'final','type':'agentMessage','phase':'final_answer','text':'SYNTHETIC final; no semantic PASS or actual model'}}},{'method':'turn/completed','params':{'threadId':'finite-producer-thread','turn':{'id':'finite-producer-turn','status':'failed' if failed else 'completed','error':None}}}])
                real_bound=n.bound_helpers
                @contextlib.contextmanager
                def fixture_helpers(sink):
                    with real_bound(sink) as (helpers,imports),contextlib.ExitStack() as stack:
                        rt=helpers['runtime']
                        stack.enter_context(mock.patch.object(rt.RPC,'send',send));stack.enter_context(mock.patch.object(rt.RPC,'next',lambda rpc,deadline:rpc._synthetic_queue.pop(0)))
                        stack.enter_context(mock.patch.object(rt.RPC,'close',lambda rpc:rpc.p.wait()))
                        stack.enter_context(mock.patch.object(helpers['activation_r3'],'mdm_forced',return_value={'synthetic_fixture':False}))
                        yield helpers,imports
                approval={'role':'user','action':'approve_bounded_workflow_context','new_context':True,'checkpoint_sha256':recipe['workflow_checkpoint']['sha256'],'release_sha256':release['sha256'],'text':'SYNTHETIC test only; no actual authority'}
                stream=io.StringIO(json.dumps(approval)+'\n'+json.dumps({'text':row['initial_user_text']})+'\n'+json.dumps({'text':'MUST REMAIN UNREAD'})+'\n')
                environment={'HOME':str(home),'PATH':'/opt/homebrew/bin:/usr/bin:/bin'}
                with mock.patch.dict(n.os.environ,environment,clear=True),mock.patch.object(Path,'home',return_value=home),mock.patch.object(n,'bound_helpers',fixture_helpers),mock.patch.object(n.subprocess,'run',return_value=types.SimpleNamespace(stdout=binding['codex_version'])),mock.patch.object(n.subprocess,'Popen',side_effect=popen),mock.patch.object(n.sys,'stdin',stream),mock.patch('builtins.print'):
                    if failed:
                        with self.assertRaisesRegex(RuntimeError,'SYNTHETIC zero before thread' if zero else 'Non-success terminal'):n.run_row(args)
                    else:n.run_row(args)
                self.assertEqual(sent,[] if zero else [{'threadId':'finite-producer-thread','input':[{'type':'text','text':row['initial_user_text']}]}]);self.assertEqual(json.loads(stream.readline()),{'text':row['initial_user_text'] if zero else 'MUST REMAIN UNREAD'})
                context_ref=ref(work/'out/workflow-context.json');record=n.checked_json(context_ref)
                self.assertEqual(record['healthy'],not failed);self.assertTrue(all(p.poll()==0 for p in processes));self.assertEqual(len(processes),2)
                self.assertEqual(n.workflow_usage(recipe['usage']+[context_ref])['changed-spec/closure'],used.get('changed-spec/closure',0)+(0 if zero else 1))
                # Mutate one retained diagnostic in the actual serialized producer output.
                if zero:
                    self.assertNotIn('startup-diagnostic-v3.json',record['policy_facts']);self.assertNotIn('thread-start-v3.json',record['facts'])
                    self.assertEqual(n.checked_json(record['policy_facts']['finite-lookup-input.json'])['failure_stage'],'before-live')
                    record['policy_facts'].pop('finite-lookup-input.json')
                else:
                    diagnostic=n.checked_json(record['policy_facts']['startup-diagnostic-v3.json']);diagnostic['no_write_lookup']['current_receipt']=None
                    record['policy_facts']['startup-diagnostic-v3.json']=save('tampered-diagnostic.json',diagnostic)
                with self.assertRaises(RuntimeError):n.workflow_usage(recipe['usage']+[save('tampered-context.json',record)])
                for receipt in (work/'out').rglob('*.json'):
                    self.assertNotIn('PRIVATE-INTEGRATION',receipt.read_text())
                self.assertEqual(n.workflow_inventory(root),original_state)

class KnownSpecClosureZeroTests(unittest.TestCase):
    def test_exact_suffix_is_shared_and_no_second_zero_or_fork_is_selected(self):
        proof=n.spec_closure_zero_provenance();base=proof['base'];old=proof['recipe']
        self.assertEqual(n.finite_recipe_usage(base,old),base['usage'])
        current=copy.deepcopy(old);current['adapter_sha256']=n.sha(n.__file__)
        expected=base['usage']+[n.SPEC_CLOSURE_ZERO_CONTEXT]
        self.assertEqual(n.finite_recipe_usage(base,current),expected)
        for usage in (base['usage'],expected+[n.SPEC_CLOSURE_ZERO_CONTEXT],
                      base['usage'][:-1]+[n.SPEC_CLOSURE_ZERO_CONTEXT,base['usage'][-1]],
                      base['usage']+[{'path':'/foreign-not-read','sha256':'0'*64}]):
            with self.subTest(usage_count=len(usage)):
                current['usage']=usage
                self.assertNotEqual(current['usage'],n.finite_recipe_usage(base,current))

    def test_provenance_denies_missing_pins_audit_actual_USER_and_state_changes(self):
        from unittest import mock
        actual=n.spec_closure_zero_provenance();sidecar=actual['sidecar'];real=n.checked_json
        cases=('decision','audit','audit-check','raw-identity','state','failure','closed','actual-USER')
        for mutation in cases:
            with self.subTest(mutation=mutation):
                def load(reference):
                    value=copy.deepcopy(real(reference))
                    if mutation=='decision' and reference==n.SPEC_CLOSURE_ZERO_DISPOSITION:value['decision']='UNKNOWN'
                    elif mutation in ('audit','audit-check') and reference==sidecar['audit']:
                        if mutation=='audit':value['verdict']='UNKNOWN'
                        else:value['checks'].pop('zero_turn_start')
                    elif mutation in ('raw-identity','state','failure','closed') and reference==n.SPEC_CLOSURE_ZERO_CONTEXT:
                        if mutation=='raw-identity':value['process_id']+=1
                        elif mutation=='state':value['state']={}
                        elif mutation=='failure':value['failure']='invented historical failure'
                        else:value['closed']=False
                    elif mutation=='actual-USER' and reference==sidecar['wire']:
                        value.append({'direction':'request','payload':{'method':'turn/start','params':{'input':[{'type':'text','text':'UNAUTHORIZED'}]}}})
                    return value
                with mock.patch.object(n,'checked_json',side_effect=load):
                    with self.assertRaises(RuntimeError):n.spec_closure_zero_provenance()
        with mock.patch.object(n,'SPEC_CLOSURE_ZERO_DISPOSITION',dict(n.SPEC_CLOSURE_ZERO_DISPOSITION,sha256='0'*64)):
            with self.assertRaises(RuntimeError):n.spec_closure_zero_provenance()
        real_sha=n.sha
        with mock.patch.object(n,'sha',side_effect=lambda path: (_ for _ in ()).throw(AssertionError('mutable claim must not be read')) if str(path)==sidecar['claim']['original_path'] else real_sha(path)):
            n.spec_closure_zero_provenance()

    def test_replacement_review_requires_raw_and_sidecar_authority(self):
        proof=n.spec_closure_zero_provenance();recipe=copy.deepcopy(proof['recipe']);recipe['adapter_sha256']=n.sha(n.__file__)
        recipe['usage']=n.finite_recipe_usage(proof['base'],recipe)
        cp=n.checked_json(recipe['workflow_checkpoint']);material=n.checked_json(cp['materialization'])
        release=n.checked_json(proof['record']['release']);review=n.checked_json(release['root_review'])
        review['authority_evidence'] += [dict(n.SPEC_CLOSURE_ZERO_CONTEXT),dict(n.SPEC_CLOSURE_ZERO_DISPOSITION)]
        n.spec_closure_component(recipe,recipe['rows'][0],material,recipe['usage'],review)
        for ref in (n.SPEC_CLOSURE_ZERO_CONTEXT,n.SPEC_CLOSURE_ZERO_DISPOSITION):
            with self.subTest(missing=ref['path']):
                bad=copy.deepcopy(review);bad['authority_evidence']=[v for v in bad['authority_evidence'] if v!=ref]
                with self.assertRaises(RuntimeError):n.spec_closure_component(recipe,recipe['rows'][0],material,recipe['usage'],bad)

    def test_exact_actual_zero_is_accounted_without_rewriting_raw(self):
        sidecar=n.checked_json({'path':str(n.SOURCE/'.omx/continuations/resume-20261027-j56k2v96/zero-recovery/disposition.json'),
                                'sha256':'86fa632d52e0753ffe3a45df554cd668ecdabd1307123c1a91bb8793a904f070'})
        raw=sidecar['original_context'];before=Path(raw['path']).read_bytes()
        recipe=n.checked_json(sidecar['original_recipe'])
        prior=n.workflow_usage(recipe['usage'])
        actual=n.workflow_usage(recipe['usage']+[raw])
        self.assertEqual(actual,dict(prior,**{'changed-spec/closure':0}))
        self.assertEqual(sum(actual.values()),50)
        self.assertEqual(Path(raw['path']).read_bytes(),before)

if __name__=='__main__':unittest.main()
