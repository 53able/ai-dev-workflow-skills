"""Model-free regression tests for the exact ignored-user two-field projection."""
import copy
import hashlib
import unittest
import activation_r3 as collector


class ActivationProjectionTests(unittest.TestCase):
    def setUp(self):
        self.file = '/fixture-home/.codex/config.toml'
        self.names = ['agent-browser', 'computer-use', 'node_repl']
        empty = {'top_level_keys': [], 'mcp_server_names': []}
        structural = {
            'layers': [
                {'source': {'type': 'user', 'file': self.file, 'profile': None},
                 'version': 'sha256:' + 'a' * 64, 'disabled_reason': None,
                 'structure': {'top_level_keys': ['mcp_servers'], 'mcp_server_names': self.names[:]}},
                {'source': {'type': 'system', 'file': '/etc/codex/config.toml'},
                 'version': 'sha256:' + 'b' * 64, 'disabled_reason': None, 'structure': empty},
            ],
            'files': {
                self.file: {'exists': True, 'sha256': 'a' * 64},
                '/fixture-home/.codex/hooks.json': {'exists': False, 'sha256': None},
                '/etc/codex/config.toml': {'exists': False, 'sha256': None},
                '/fixture/.codex/config.toml': {'exists': False, 'sha256': None},
            },
            'mdm_before': {'config_toml_base64': False, 'requirements_toml_base64': False},
            'mdm_after': {'config_toml_base64': False, 'requirements_toml_base64': False},
            'all_layer_mcp_names': self.names[:],
            'cli_loader_relation': 'source-bound fixture',
            'current_structural_only': True,
        }
        applied = {'mcp_names': self.names[:], 'mcp_enabled': dict.fromkeys(self.names, False),
                   'canonical_features': dict.fromkeys(collector.CANONICAL, False)}
        self.before = collector.comparison_input(structural, applied,
            [{'name': 'ains-spec', 'path': '/fixture/.agents/skills/ains-spec/SKILL.md',
              'sha256': 'c' * 64, 'metadata_sha256': 'd' * 64}], 'e' * 64)
        overrides = ['features.' + n + '=false' for n in collector.CANONICAL]
        for name in self.names:
            overrides.extend(['mcp_servers.' + name + '.enabled=false',
                              'mcp_servers.' + name + '.command="/usr/bin/false"'])
        argv = ['codex', '--no-daemon', '-a', 'never', 'exec', '--ignore-user-config',
                '--ephemeral', '--strict-config']
        for value in overrides:
            argv.extend(['-c', value])
        argv += ['-s', 'workspace-write', '-m', 'gpt-6.1-sol', '--json', '-C', '/fixture', 'prompt']
        self.launch = {'argv': argv, 'stdin': 'DEVNULL', 'stdin_appended_bytes': 0,
                       'fresh_process': True, 'no_daemon': True, 'ignore_user_config': True,
                       'ephemeral': True, 'typed_skill_inputs': False, 'typed_mention_inputs': False,
                       'env_names': ['HOME'], 'env_nonempty': {'HOME': True},
                       'environment_identity_sha256': {'HOME': self.digest('/fixture-home')}}

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def compare(self, after=None, launch=None):
        return collector.compare_activation_inputs(self.before, self.before if after is None else after,
                                                    self.launch if launch is None else launch, self.file)

    def test_only_exact_two_ignored_fields_may_drift_without_mutating_inputs(self):
        after = copy.deepcopy(self.before)
        after['structural']['layers'][0]['version'] = 'sha256:' + 'f' * 64
        after['structural']['files'][self.file]['sha256'] = 'f' * 64
        originals = copy.deepcopy((self.before, after, self.launch))
        result = self.compare(after)
        self.assertFalse(result['raw_stable'])
        self.assertTrue(result['projected_stable'])
        self.assertEqual(result['premise_errors'], [])
        self.assertEqual(len(result['excluded_field_paths']), 2)
        self.assertEqual({d['path'] for d in result['raw_differences']}, set(result['excluded_field_paths']))
        self.assertEqual((self.before, after, self.launch), originals)
        self.assertEqual(result['projection_version'], 'ignored-user-identities-v1')
        self.assertIn('empty table', result['reason'])

    def test_identical_receipts_pass_both_equalities(self):
        result = self.compare()
        self.assertTrue(result['raw_stable'])
        self.assertTrue(result['projected_stable'])

    def test_each_relevant_receipt_change_still_blocks(self):
        changes = {
            'user source': lambda x: x['structural']['layers'][0]['source'].update(type='project'),
            'user path': lambda x: x['structural']['layers'][0]['source'].update(file='/different/config.toml'),
            'user profile': lambda x: x['structural']['layers'][0]['source'].update(profile='other'),
            'unexpected source field': lambda x: x['structural']['layers'][0]['source'].update(extra=True),
            'unknown layer': lambda x: x['structural']['layers'].append({'source': {'type': 'managed'}}),
            'reordered layers': lambda x: x['structural']['layers'].reverse(),
            'system version': lambda x: x['structural']['layers'][1].update(version='sha256:' + 'f' * 64),
            'system contents': lambda x: x['structural']['layers'][1]['structure']['top_level_keys'].append('features'),
            'layer error': lambda x: x['structural']['layers'][0].update(disabled_reason='error'),
            'user structure': lambda x: x['structural']['layers'][0]['structure']['top_level_keys'].append('skills'),
            'user MCP structure': lambda x: x['structural']['layers'][0]['structure']['mcp_server_names'].append('new'),
            'MCP union': lambda x: x['structural']['all_layer_mcp_names'].append('new'),
            'effective MCP enabled': lambda x: x['applied']['mcp_enabled'].update(node_repl=True),
            'effective MCP names': lambda x: x['applied']['mcp_names'].append('new'),
            'effective flag': lambda x: x['applied']['canonical_features'].update(token_budget=True),
            'missing effective flag': lambda x: x['applied']['canonical_features'].pop('goals'),
            'unknown effective flag': lambda x: x['applied']['canonical_features'].update(unknown=False),
            'project file': lambda x: x['structural']['files']['/fixture/.codex/config.toml'].update(exists=True, sha256='f' * 64),
            'system file': lambda x: x['structural']['files']['/etc/codex/config.toml'].update(exists=True, sha256='f' * 64),
            'hooks digest': lambda x: x['structural']['files']['/fixture-home/.codex/hooks.json'].update(exists=True, sha256='f' * 64),
            'user file absence': lambda x: x['structural']['files'][self.file].update(exists=False),
            'user file path': lambda x: x['structural']['files'].update({'/other/config.toml': x['structural']['files'].pop(self.file)}),
            'MDM forced': lambda x: x['structural']['mdm_after'].update(config_toml_base64=True),
            'MDM unknown': lambda x: x['structural']['mdm_after'].update(extra=False),
            'install body': lambda x: x['installed_provenance'][0].update(sha256='f' * 64),
            'install metadata': lambda x: x['installed_provenance'][0].update(metadata_sha256='f' * 64),
            'install path': lambda x: x['installed_provenance'][0].update(path='/different/SKILL.md'),
            'source release': lambda x: x.update(source_manifest_sha256='f' * 64),
            'unknown top field': lambda x: x.update(unexpected=True),
            'unknown nested field': lambda x: x['structural']['layers'][0]['structure'].update(unexpected=True),
        }
        for name, mutate in changes.items():
            with self.subTest(name=name):
                after = copy.deepcopy(self.before)
                mutate(after)
                self.assertFalse(self.compare(after)['projected_stable'])

    def test_invalid_launch_premises_block_even_identical_receipts(self):
        changes = {
            'ignore flag absent': lambda x: x['argv'].remove('--ignore-user-config'),
            'ignore receipt false': lambda x: x.update(ignore_user_config=False),
            'other loader': lambda x: x['argv'].__setitem__(4, 'app-server'),
            'user profile flag': lambda x: x['argv'].extend(['--profile', 'other']),
            'not fresh': lambda x: x.update(fresh_process=False),
            'stdin open': lambda x: x.update(stdin='PIPE'),
            'typed skill': lambda x: x.update(typed_skill_inputs=True),
            'HOME differs': lambda x: x['environment_identity_sha256'].update(HOME=self.digest('/other')),
            'missing env receipt': lambda x: x.update(env_names=[]),
        }
        for name, mutate in changes.items():
            with self.subTest(name=name):
                launch = copy.deepcopy(self.launch)
                mutate(launch)
                result = self.compare(launch=launch)
                self.assertTrue(result['raw_stable'])
                self.assertFalse(result['projected_stable'])
                self.assertTrue(result['premise_errors'])
        for name in ['CODEX_EXEC_SERVER_URL', 'CODEX_EXEC_SERVER_NOISE_REGISTRY_URL',
                     'CODEX_EXEC_SERVER_NOISE_AUTH_TOKEN', 'CODEX_HOME']:
            with self.subTest(name=name):
                launch = copy.deepcopy(self.launch)
                launch['env_names'] = sorted(['HOME', name])
                launch['env_nonempty'][name] = True
                launch['environment_identity_sha256'][name] = self.digest('/other')
                self.assertFalse(self.compare(launch=launch)['projected_stable'])

    def test_bad_shared_premises_do_not_pass_just_because_equal(self):
        self.before['structural']['mdm_before']['config_toml_base64'] = True
        self.assertFalse(self.compare()['projected_stable'])


if __name__ == '__main__':
    unittest.main()
