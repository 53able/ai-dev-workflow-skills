"""Owned transport regressions; fake failures and one non-model child smoke."""
import contextlib
import errno
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import owned_transport as t


class Stream:
    def __init__(self, fd):
        self.fd, self.closed = fd, False
        self.close_error = None

    def fileno(self):
        return self.fd

    def close(self):
        self.closed = True
        if self.close_error:
            raise self.close_error


class Process:
    pid = 9312

    def __init__(self, waits=()):
        self.stdin, self.stdout = Stream(91), Stream(92)
        self.waits = list(waits)
        self.wait_calls, self.returncode = [], None

    def wait(self, timeout):
        self.wait_calls.append(timeout)
        result = self.waits.pop(0) if self.waits else 0
        if isinstance(result, BaseException):
            raise result
        self.returncode = result
        return result


class Timer:
    def __init__(self, duration, callback):
        self.duration, self.callback = duration, callback
        self.alive, self.daemon = False, False
        self.cancelled, self.joined = False, False

    def start(self):
        self.alive = True

    def cancel(self):
        self.cancelled, self.alive = True, False

    def join(self, timeout):
        self.joined = True

    def is_alive(self):
        return self.alive


def waiting():
    return subprocess.TimeoutExpired('private-command-canary', 0.1)


class TransportTests(unittest.TestCase):
    @contextlib.contextmanager
    def fake(self, *, waits=(), signal_error=None, probe='absent', pgid=9312):
        process, stderr, timers = Process(waits), io.BytesIO(), []
        def timer(duration, callback):
            result = Timer(duration, callback)
            timers.append(result)
            return result
        def killpg(group, sig):
            self.assertEqual(group, 9312)
            if sig == 0:
                if probe == 'absent':
                    raise ProcessLookupError(errno.ESRCH, 'private-probe-canary')
                if probe == 'denied':
                    raise PermissionError(errno.EPERM, 'private-probe-canary')
                return
            if sig == signal_error:
                raise PermissionError(errno.EPERM, 'private-signal-canary')
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(t.subprocess, 'Popen', return_value=process))
            stack.enter_context(mock.patch.object(t.tempfile, 'TemporaryFile', return_value=stderr))
            stack.enter_context(mock.patch.object(t.threading, 'Timer', side_effect=timer))
            stack.enter_context(mock.patch.object(t.os, 'getpgid', return_value=pgid))
            stack.enter_context(mock.patch.object(t.os, 'getsid', return_value=9312))
            stack.enter_context(mock.patch.object(t.os, 'set_blocking'))
            kill = stack.enter_context(mock.patch.object(t.os, 'killpg', side_effect=killpg))
            child_kill = stack.enter_context(mock.patch.object(t.os, 'kill'))
            stack.enter_context(mock.patch.object(t.os, 'read', return_value=b''))
            stack.enter_context(mock.patch.object(t.select, 'select', side_effect=lambda r, w, x, timeout: (r, w, [])))
            yield process, stderr, timers, kill, child_kill

    def make(self):
        return t.ProcessTransport(['/not-executed'], '/unused', {}, 11,
                                  cleanup_deadline=13, clock=lambda: 10)

    def test_clean_eof_reaps_before_probe_without_group_signal(self):
        with self.fake() as (process, stderr, timers, kill, _):
            transport = self.make()
            receipt = transport.close()
            self.assertIs(t.require_healthy_close(receipt), receipt)
            self.assertEqual(receipt['ownership'], dict(pid=9312, pgid=9312, sid=9312, observed_monotonic=10))
            self.assertTrue(process.stdin.closed and process.stdout.closed and stderr.closed)
            self.assertTrue(timers[0].cancelled and timers[0].joined)
            kill.assert_called_once_with(9312, 0)
            with self.assertRaises(t.TransportError):
                transport.close()

    def test_signal_eperm_does_not_skip_wait_streams_or_receipt(self):
        for denied in (signal.SIGTERM, signal.SIGKILL):
            with self.subTest(denied=denied), self.fake(
                    waits=(waiting(), waiting(), 0), signal_error=denied) as (process, stderr, timers, kill, _):
                receipt = self.make().close()
                self.assertTrue(receipt['reaped'])
                self.assertTrue(process.stdin.closed and process.stdout.closed and stderr.closed)
                self.assertEqual(len(process.wait_calls), 3)
                self.assertTrue(timers[0].cancelled and timers[0].joined)
                operation = 'terminate' if denied == signal.SIGTERM else 'kill'
                self.assertIn(dict(operation=operation, exception_type='PermissionError', errno=errno.EPERM),
                              receipt['cleanup_errors'])
                self.assertNotIn('private-', json.dumps(receipt))
                with self.assertRaises(t.TransportError):
                    t.require_healthy_close(receipt)

    def test_final_wait_timeout_retains_unreaped_state_and_closes_resources(self):
        with self.fake(waits=(waiting(), waiting(), waiting())) as (process, stderr, _, _, _):
            receipt = self.make().close()
            self.assertFalse(receipt['reaped'])
            self.assertIsNone(receipt['returncode'])
            self.assertEqual(receipt['cleanup_errors'][-1]['operation'], 'wait-kill')
            self.assertTrue(process.stdout.closed and stderr.closed)
            self.assertNotIn('private-command-canary', json.dumps(receipt))

    def test_stream_error_does_not_skip_other_streams_and_timer(self):
        with self.fake() as (process, stderr, timers, _, _):
            process.stdin.close_error = OSError(errno.EIO, 'private-stream-canary')
            receipt = self.make().close()
            self.assertTrue(process.stdout.closed and stderr.closed and timers[0].joined)
            self.assertEqual(receipt['cleanup_errors'][0]['operation'], 'stdin-close')
            with self.assertRaises(t.TransportError):
                t.require_healthy_close(receipt)

    def test_stdout_close_failure_still_captures_and_closes_stderr(self):
        with self.fake() as (process, stderr, timers, _, _):
            process.stdout.close_error = OSError(errno.EIO, 'private-output-canary')
            receipt = self.make().close()
            self.assertTrue(stderr.closed and timers[0].joined)
            self.assertTrue(receipt['stderr_complete'])
            self.assertIn('stdout-close', [item['operation'] for item in receipt['cleanup_errors']])
            with self.assertRaises(t.TransportError):
                t.require_healthy_close(receipt)

    def test_stderr_read_failure_still_closes_it_and_reports_incomplete(self):
        with self.fake() as (_, stderr, timers, _, _):
            transport = self.make()
            with mock.patch.object(stderr, 'read', side_effect=OSError(errno.EIO, 'private-stderr-canary')):
                receipt = transport.close()
            self.assertTrue(stderr.closed and timers[0].joined)
            self.assertFalse(receipt['stderr_complete'])
            self.assertNotIn('private-stderr-canary', json.dumps(receipt))
            with self.assertRaises(t.TransportError):
                t.require_healthy_close(receipt)

    def test_reaped_leader_with_surviving_group_is_not_signalled_or_healthy(self):
        with self.fake(probe='present') as (_, _, _, kill, _):
            receipt = self.make().close()
            kill.assert_called_once_with(9312, 0)
            self.assertTrue(receipt['reaped'])
            self.assertEqual(receipt['group_state'], 'present')
            with self.assertRaises(t.TransportError):
                t.require_healthy_close(receipt)

    def test_probe_eperm_is_unknown_not_absent(self):
        with self.fake(probe='denied'):
            receipt = self.make().close()
            self.assertEqual(receipt['group_state'], 'unknown')
            self.assertEqual(receipt['cleanup_errors'][-1]['exception_type'], 'PermissionError')
            with self.assertRaises(t.TransportError):
                t.require_healthy_close(receipt)

    def test_watchdog_eperm_preserved_through_later_successful_reap(self):
        with self.fake(signal_error=signal.SIGKILL) as (_, _, timers, kill, _):
            transport = self.make()
            timers[0].callback()
            receipt = transport.close()
            self.assertTrue(receipt['watchdog_fired'])
            self.assertEqual(receipt['watchdog_error'], 'PermissionError')
            self.assertTrue(receipt['reaped'])
            self.assertIn(mock.call(9312, signal.SIGKILL), kill.call_args_list)
            with self.assertRaises(t.TransportError):
                t.require_healthy_close(receipt)

    def test_close_watchdog_race_does_not_signal_after_reaping(self):
        with self.fake() as (process, _, _, kill, _):
            transport = self.make()
            threads = []
            original_wait = process.wait
            def wait(timeout):
                worker = threading.Thread(target=transport._expire)
                threads.append(worker)
                worker.start()
                return original_wait(timeout)
            process.wait = wait
            receipt = transport.close()
            for worker in threads:
                worker.join(timeout=1)
                self.assertFalse(worker.is_alive())
            self.assertFalse(receipt['watchdog_fired'])
            kill.assert_called_once_with(9312, 0)

    def test_changed_session_identity_never_receives_group_signal(self):
        with self.fake(waits=(waiting(), waiting(), 0)) as (_, _, _, kill, _):
            transport = self.make()
            with mock.patch.object(t.os, 'getsid', return_value=4321):
                receipt = transport.close()
            kill.assert_called_once_with(9312, 0)
            self.assertEqual([e['operation'] for e in receipt['cleanup_errors']],
                             ['terminate-identity', 'kill-identity'])

    def test_known_reaped_popen_never_receives_another_group_signal(self):
        with self.fake() as (process, _, timers, kill, _):
            transport = self.make()
            process.returncode = 0  # A caller has already waited/polled its child.
            timers[0].callback()
            receipt = transport.close()
            kill.assert_called_once_with(9312, 0)
            self.assertTrue(receipt['reaped'])
            self.assertTrue(receipt['watchdog_fired'])

    def test_constructor_identity_failure_retains_cleanup_without_unproven_group_signal(self):
        with self.fake(pgid=4321, waits=(waiting(), 0)) as (process, stderr, timers, kill, child_kill):
            with self.assertRaises(t.TransportError) as failure:
                self.make()
            receipt = failure.exception.cleanup_receipt
            self.assertIsNone(receipt['ownership'])
            self.assertTrue(receipt['reaped'])
            self.assertTrue(process.stdout.closed and stderr.closed)
            kill.assert_not_called()
            child_kill.assert_called_once_with(9312, signal.SIGTERM)
            self.assertEqual(timers, [])

    def test_stdout_tail_and_stderr_are_not_healthy_when_incomplete(self):
        with self.fake():
            transport = self.make()
            transport.buffer = b'complete\npartial'
            with mock.patch.object(t.select, 'select', return_value=([], [], [])):
                receipt = transport.close()
            self.assertEqual(receipt['tail_frames'], [b'complete\n'])
            self.assertEqual(receipt['partial_stdout_bytes'], 7)
            self.assertFalse(receipt['stdout_complete'])
            with self.assertRaises(t.TransportError):
                t.require_healthy_close(receipt)

    def test_timeout_termination_is_not_clean_business_completion(self):
        with self.fake(waits=(waiting(), -signal.SIGTERM)):
            receipt = self.make().close()
            self.assertTrue(receipt['reaped'])
            self.assertEqual(receipt['returncode'], -signal.SIGTERM)
            with self.assertRaises(t.TransportError):
                t.require_healthy_close(receipt)

    def test_termination_handler_exit_zero_is_still_not_healthy(self):
        with self.fake(waits=(waiting(), 0)):
            receipt = self.make().close()
            self.assertEqual(receipt['returncode'], 0)
            self.assertTrue(receipt['termination_attempted'])
            self.assertTrue(receipt['reaped'])
            with self.assertRaises(t.TransportError):
                t.require_healthy_close(receipt)

    def test_constructor_diagnostic_retains_facts_but_hashes_original_tail(self):
        with self.fake():
            receipt = self.make().close()
        receipt['tail_frames'] = [b'private-tail-canary']
        diagnostic = t.diagnostic_receipt(receipt)
        self.assertEqual(diagnostic['ownership'], receipt['ownership'])
        self.assertEqual(diagnostic['tail_frames'][0]['bytes'], 19)
        self.assertNotIn('private-tail-canary', json.dumps(diagnostic))
        self.assertIsNone(t.diagnostic_receipt(dict(receipt)))

    def test_work_deadline_is_distinct_from_cleanup_watchdog(self):
        with self.fake() as (_, _, timers, _, _):
            transport = self.make()
            self.assertEqual(timers[0].duration, 3)
            with self.assertRaises(TimeoutError):
                transport.read(10)
            t.require_healthy_close(transport.close())

    def test_cleanup_past_outer_deadline_is_not_healthy(self):
        with self.fake():
            transport = self.make()
            now = [10]
            transport.clock = lambda: now[0]
            original = transport._stdout_tail
            def delayed_tail():
                result = original()
                now[0] = 14
                return result
            transport._stdout_tail = delayed_tail
            receipt = transport.close()
            self.assertTrue(receipt['reaped'])
            self.assertGreater(receipt['cleanup_finished_monotonic'], receipt['cleanup_deadline'])
            with self.assertRaises(t.TransportError):
                t.require_healthy_close(receipt)

    def test_nonfinite_or_unbounded_deadlines_reject_before_launch(self):
        with mock.patch.object(t.subprocess, 'Popen') as launch:
            for deadline, cleanup in ((float('nan'), 13), (11, 14), (9, 10), (True, 3)):
                with self.subTest(deadline=deadline, cleanup=cleanup), self.assertRaises(t.TransportError):
                    t.ProcessTransport([], '/', {}, deadline, cleanup_deadline=cleanup, clock=lambda: 10)
            launch.assert_not_called()

    def test_real_owned_nonmodel_echo_child_reaped_cleanly(self):
        with tempfile.TemporaryDirectory() as root:
            transport = t.ProcessTransport([sys.executable, '-u', '-c',
                'import sys\nfor line in sys.stdin:\n sys.stdout.write(line); sys.stdout.flush()'],
                root, dict(os.environ), time.monotonic() + 5)
            try:
                transport.write(b'{"owned":true}\n', time.monotonic() + 2)
                self.assertEqual(transport.read(time.monotonic() + 2), b'{"owned":true}\n')
            finally:
                receipt = transport.close()
            t.require_healthy_close(receipt)
            self.assertTrue(receipt['reaped'])
            self.assertEqual(receipt['group_state'], 'absent')


if __name__ == '__main__':
    unittest.main()
