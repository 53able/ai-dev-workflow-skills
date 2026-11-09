#!/usr/bin/env python3
import contextlib
import io
import sys
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('live', Path(__file__).with_name('live.py'))
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)

# The status string the real capture() reports for a completed container run.
with patch.object(live.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'', b'')):
    OBSERVED = live.capture(['fake'], env={}, name='status-probe')[1]['status']


class LiveEvidenceTests(unittest.TestCase):
    def test_success_captures_both_streams(self):
        with patch.object(live.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'payload', b'diagnostic')):
            data, meta = live.capture(['fake'], env={}, name='isolated')
        self.assertEqual(data, b'payload\ndiagnostic')
        self.assertEqual(meta['exitCode'], 0)

    def test_timeout_preserves_partial_and_cleanup_failure(self):
        timeout = subprocess.TimeoutExpired(['fake'], 2, output=b'partial token', stderr=b'error token')
        with patch.object(live.subprocess, 'run', side_effect=[timeout, subprocess.TimeoutExpired(['cleanup'],10)]):
            data, meta = live.capture(['fake'], env={}, name='isolated', timeout=2)
        self.assertEqual(live.redact(data, {'token'}), b'partial \nerror ')
        self.assertEqual(meta['cleanup'], 'cleanup failure')
        self.assertEqual(meta['status'], 'timeout')

    def test_redaction_reaches_fixed_point_including_short_values(self):
        self.assertEqual(live.redact(b'abXcd', {'X','abcd'}), b'')
        self.assertEqual(live.redact(b'clear', set()), b'clear')

    def test_auth_snapshot_and_artifacts_cover_rotated_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            auth = root/'auth.json'
            auth.write_text('{"tokens":{"old":"old-secret"}}')
            values = live.auth_strings(auth)
            auth.write_text('{"tokens":{"new":"new-secret"}}')
            values.update(live.auth_strings(auth))
            auth.unlink()
            artifact = root/'artifact.txt'
            artifact.write_text('old-secret/new-secret')
            self.assertEqual(live.sanitize_artifacts(root, values), ['artifact.txt'])
            self.assertEqual(artifact.read_text(), '/')

    def test_main_never_prints_secret_bearing_artifact_name(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inputs = root/'input-live-v4'
            (inputs/'candidate/skills').mkdir(parents=True)
            def fake_capture(argv, **kwargs):
                evidence = root/'live/fake'
                (evidence/'runtime-secret.txt').write_text('payload runtime-secret')
                return b'event runtime-secret', {'exitCode':0,'status':'observed'}
            output = io.StringIO()
            argv = ['live.py',str(root),'--product','claude','--bundle','candidate','--scenario','status','--run-id','fake']
            with patch.object(sys,'argv',argv), patch.dict(live.os.environ,{'CLAUDE_CODE_OAUTH_TOKEN':'runtime-secret'}), patch.object(live,'capture',side_effect=fake_capture), patch.object(live,'image_digest',return_value='fake-digest'), contextlib.redirect_stdout(output):
                live.main()
            self.assertNotIn('runtime-secret', output.getvalue())
            for path in (root/'live/fake').rglob('*'):
                self.assertNotIn('runtime-secret',str(path))
                if path.is_file(): self.assertNotIn(b'runtime-secret',path.read_bytes())

    def test_main_does_not_chmod_outside_symlink_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'input-live-v4/candidate/skills').mkdir(parents=True)
            outside = root/'outside'
            outside.write_text('unchanged')
            outside.chmod(0o644)
            def fake_capture(argv, **kwargs):
                (root/'live/fake/link').symlink_to(outside)
                return b'event', {'exitCode':0,'status':'observed'}
            argv = ['live.py',str(root),'--product','claude','--bundle','candidate','--scenario','status','--run-id','fake']
            with patch.object(sys,'argv',argv), patch.dict(live.os.environ,{'CLAUDE_CODE_OAUTH_TOKEN':'runtime-secret'}), patch.object(live,'capture',side_effect=fake_capture), patch.object(live,'image_digest',return_value='fake-digest'), contextlib.redirect_stdout(io.StringIO()):
                exit_code = live.main()
            self.assertEqual(exit_code,1)
            failure=__import__('json').loads((root/'live/fake/result.json').read_text())
            self.assertEqual(failure['failureCode'],'evidence-validation-failed')
            self.assertEqual(failure['capture']['exitCode'],0)
            self.assertEqual((root/'live/fake/events.sanitized.log').read_text(),'event')
            self.assertEqual(outside.read_text(),'unchanged')
            self.assertEqual(outside.stat().st_mode & 0o777,0o644)

    def test_cli_only_review_configuration_uses_distinct_cache_and_flags(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'input-live-v4/candidate/skills').mkdir(parents=True)
            home = root/'host-auth'
            home.mkdir()
            (home/'auth.json').write_text('{"auth_mode":"chatgpt","tokens":{"access":"private-token"}}')
            def fake_capture(argv, **kwargs):
                self.assertIn('AINS_REVIEW_MODE=cli-only',argv)
                self.assertIn('multi_agent',argv)
                self.assertIn('multi_agent_v2',argv)
                mount = next(value for value in argv if value.startswith('type=bind,source=') and 'target=/private-review-codex' in value)
                cache = Path(mount.split('source=',1)[1].split(',target=',1)[0])
                self.assertEqual(cache.name,'review-cache')
                self.assertTrue((cache/'auth.json').is_file())
                return b'private-token', {'exitCode':0,'status':'observed'}
            argv = ['live.py',str(root),'--product','codex','--bundle','candidate','--scenario','approved','--run-id','fake','--native-review-disabled']
            output=io.StringIO()
            with patch.object(sys,'argv',argv), patch.dict(live.os.environ,{'CODEX_HOME':str(home)}), patch.object(live,'capture',side_effect=fake_capture), patch.object(live,'image_digest',return_value='fake-digest'), contextlib.redirect_stdout(output):
                live.main()
            self.assertNotIn('private-token',output.getvalue())
            self.assertFalse(list(root.glob('ains-codex-auth-*')))

    def test_auth_failure_has_safe_distinct_code_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'input-live-v4/candidate/skills').mkdir(parents=True)
            argv=['live.py',str(root),'--product','claude','--bundle','candidate','--scenario','status','--run-id','fake']
            with patch.object(sys,'argv',argv), patch.dict(live.os.environ,{},clear=True), patch.object(live,'image_digest',return_value='fake-digest'), contextlib.redirect_stdout(io.StringIO()):
                code=live.main()
            failure=__import__('json').loads((root/'live/fake/result.json').read_text())
            self.assertEqual(code,1)
            self.assertEqual(failure['failureCode'],'authentication-unavailable')
            self.assertEqual(failure['capture'],{})

    def test_reserved_result_and_event_symlinks_do_not_overwrite_host_target(self):
        for reserved in ('result.json','events.sanitized.log'):
            with self.subTest(reserved=reserved), tempfile.TemporaryDirectory() as temp:
                root=Path(temp)
                (root/'input-live-v4/candidate/skills').mkdir(parents=True)
                outside=root/'outside'
                outside.write_text('outside unchanged')
                outside.chmod(0o644)
                def fake_capture(argv, **kwargs):
                    (root/'live/fake'/reserved).symlink_to(outside)
                    return b'safe capture', {'exitCode':0,'status':'observed'}
                argv=['live.py',str(root),'--product','claude','--bundle','candidate','--scenario','status','--run-id','fake']
                with patch.object(sys,'argv',argv), patch.dict(live.os.environ,{'CLAUDE_CODE_OAUTH_TOKEN':'runtime-secret'}), patch.object(live,'capture',side_effect=fake_capture), patch.object(live,'image_digest',return_value='fake-digest'), contextlib.redirect_stdout(io.StringIO()):
                    code=live.main()
                self.assertEqual(code,1)
                failure=__import__('json').loads((root/'live/fake/result.json').read_text())
                self.assertEqual(failure['failureCode'],'evidence-validation-failed')
                self.assertEqual(outside.read_text(),'outside unchanged')
                self.assertEqual(outside.stat().st_mode & 0o777,0o644)
                self.assertFalse((root/'live/fake'/reserved).is_symlink())

    def test_failed_cleanup_quarantines_without_any_evidence_walk(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'input-live-v4/candidate/skills').mkdir(parents=True)
            outside=root/'outside'
            outside.write_text('unchanged runtime-secret')
            outside.chmod(0o644)
            finished=False
            original_rglob=Path.rglob
            def guarded_rglob(path,*args,**kwargs):
                if finished and path == root/'live/fake':
                    raise AssertionError('unsafe artifact traversal after cleanup failure')
                return original_rglob(path,*args,**kwargs)
            def fake_capture(argv,**kwargs):
                nonlocal finished
                (root/'live/fake/link').symlink_to(outside)
                finished=True
                return b'partial runtime-secret', {'status':'timeout','timeoutSeconds':240,'cleanup':'cleanup failure'}
            argv=['live.py',str(root),'--product','claude','--bundle','candidate','--scenario','status','--run-id','fake']
            with patch.object(sys,'argv',argv), patch.dict(live.os.environ,{'CLAUDE_CODE_OAUTH_TOKEN':'runtime-secret'}), patch.object(live,'capture',side_effect=fake_capture), patch.object(live,'image_digest',return_value='fake-digest'), patch.object(Path,'rglob',guarded_rglob), patch.object(live,'sanitize_artifacts') as sanitize, contextlib.redirect_stdout(io.StringIO()):
                code=live.main()
            sanitize.assert_not_called()
            self.assertEqual(code,1)
            failure=__import__('json').loads((root/'live/fake/result.json').read_text())
            self.assertEqual(failure['failureCode'],'container-cleanup-failed')
            self.assertEqual(failure['stopRequiredContainer'],'ains-live-fake')
            self.assertTrue(failure['quarantined'])
            self.assertEqual((root/'live/fake/events.sanitized.log').read_text(),'partial ')
            self.assertEqual(outside.read_text(),'unchanged runtime-secret')
            self.assertEqual(outside.stat().st_mode & 0o777,0o644)

    def run_main_with(self, root, fake_capture):
        (root/'input-live-v4/candidate/skills').mkdir(parents=True, exist_ok=True)
        argv=['live.py',str(root),'--product','claude','--bundle','candidate','--scenario','status','--run-id','fake']
        with patch.object(sys,'argv',argv), patch.dict(live.os.environ,{'CLAUDE_CODE_OAUTH_TOKEN':'runtime-secret'}), patch.object(live,'capture',side_effect=fake_capture), patch.object(live,'image_digest',return_value='fake-digest'), contextlib.redirect_stdout(io.StringIO()):
            code=live.main()
        return code, __import__('json').loads((root/'live/fake/result.json').read_text())

    def test_wrapper_propagates_collector_failure_after_agent_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            seen={}
            def fake_capture(argv, **kwargs):
                seen['wrapper']=argv[argv.index('-c')+1]
                return b'event', {'exitCode':0,'status':'observed'}
            self.run_main_with(root, fake_capture)
            fake_case=root/'fake_case.py'
            fake_case.write_text('import sys\nsys.exit(23 if sys.argv[1] == "collect" else 0)\n')
            wrapper=seen['wrapper'].replace('/tmp/ains-claude/node_modules/.bin/claude --version','true').replace('env -u CLAUDE_CODE_OAUTH_TOKEN npm install','true').replace('/inputs/container_case.py',str(fake_case))
            for agent, expected in (('true', live.COLLECT_FAILED_EXIT), ('false', live.COLLECT_FAILED_EXIT)):
                result=subprocess.run(['sh','-c',wrapper,'ains-live',agent],capture_output=True)
                self.assertEqual(result.returncode, expected)
            fake_case.write_text('import sys\nsys.exit(0)\n')
            self.assertEqual(subprocess.run(['sh','-c',wrapper,'ains-live','true']).returncode, 0)
            self.assertEqual(subprocess.run(['sh','-c',wrapper,'ains-live','sh','-c','exit 5']).returncode, 5)
            # Preflight/setup failures keep their own code and never run the collector.
            marker=root/'collected'
            for failing, code in (('auth-preflight', 7), ('setup-live', 9)):
                marker.unlink(missing_ok=True)
                fake_case.write_text(f'import sys, pathlib\nif sys.argv[1] == "collect": pathlib.Path({str(marker)!r}).touch()\nsys.exit({code} if sys.argv[1] == {failing!r} else 0)\n')
                self.assertEqual(subprocess.run(['sh','-c',wrapper,'ains-live','true']).returncode, code)
                self.assertFalse(marker.exists())

    def test_collector_failure_exit_is_classified_and_nonzero(self):
        with tempfile.TemporaryDirectory() as temp:
            code, result = self.run_main_with(Path(temp), lambda argv, **kwargs: (b'event', {'exitCode':live.COLLECT_FAILED_EXIT,'status':OBSERVED}))
            self.assertEqual(code,1)
            self.assertEqual(result['failureCode'],'evidence-collection-failed')
            self.assertEqual(result['evidenceCollection'],'incomplete')
            self.assertEqual(result['status'],'blocked')

    def test_timeout_and_setup_failure_are_not_relabelled_as_collection_failure(self):
        for meta in ({'status':'timeout','timeoutSeconds':240,'cleanup':'removed'}, {'exitCode':9,'status':OBSERVED}):
            with self.subTest(meta=meta), tempfile.TemporaryDirectory() as temp:
                code, result = self.run_main_with(Path(temp), lambda argv, **kwargs: (b'event', dict(meta)))
                self.assertEqual(code,1)
                self.assertNotIn('failureCode', result)
                self.assertEqual(result['status'], meta['status'])
                self.assertEqual(result['evidenceCollection'],'incomplete')

    def test_missing_collected_evidence_after_agent_success_is_nonzero(self):
        with tempfile.TemporaryDirectory() as temp:
            code, result = self.run_main_with(Path(temp), lambda argv, **kwargs: (b'event', {'exitCode':0,'status':OBSERVED}))
            self.assertEqual(code,1)
            self.assertEqual(result['failureCode'],'evidence-collection-failed')
            self.assertEqual(result['status'],'blocked')

    def test_complete_collection_with_agent_success_returns_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            def fake_capture(argv, **kwargs):
                for name in live.COLLECTED_EVIDENCE:
                    (root/'live/fake'/name).write_text('{}')
                return b'event', {'exitCode':0,'status':OBSERVED}
            code, result = self.run_main_with(root, fake_capture)
            self.assertEqual(code,0)
            self.assertEqual(result['evidenceCollection'],'complete')
            self.assertNotIn('failureCode', result)

    def test_symlink_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'link').symlink_to('/outside')
            with self.assertRaises(RuntimeError): live.sanitize_artifacts(root,set())


if __name__ == '__main__': unittest.main()
