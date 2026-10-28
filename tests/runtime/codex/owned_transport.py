"""Owned subprocess IO with bounded, failure-retaining cleanup.

This adapter does not authorize a launch or establish business completion. The
caller supplies the exact argv/root/environment and must validate RPC lifecycle
separately. ``deadline`` bounds work; ``cleanup_deadline`` bounds all cleanup and
defaults to two seconds later. No historical receipt is repaired by this code.
"""
from __future__ import annotations

import hashlib
import math
import os
import select
import signal
import subprocess
import tempfile
import threading
import time


MAX_STDOUT = 16 * 1024 * 1024
MAX_STDERR = 8 * 1024 * 1024
MAX_CLEANUP_SECONDS = 2


class TransportError(ValueError):
    pass


class _CleanupReceipt(dict):
    """Locally produced diagnostic data; never launch authority."""


def diagnostic_receipt(receipt):
    """Retain owned cleanup facts while replacing original tail bytes by hashes."""
    if type(receipt) is not _CleanupReceipt:
        return None
    result = dict(receipt)
    result['tail_frames'] = [dict(bytes=len(frame), sha256=hashlib.sha256(frame).hexdigest())
                             for frame in receipt['tail_frames']]
    return result


def require_healthy_close(receipt):
    """Transport health only; a completed business turn is a separate claim."""
    timing = ('cleanup_started_monotonic', 'cleanup_finished_monotonic', 'cleanup_deadline')
    bounded = isinstance(receipt, dict) and all(
        type(receipt.get(key)) in (int, float) and math.isfinite(receipt[key]) for key in timing)
    if not isinstance(receipt, dict) or not (
            bounded and receipt['cleanup_started_monotonic'] <=
            receipt['cleanup_finished_monotonic'] <= receipt['cleanup_deadline'] and
            receipt.get('cleanup_finished') is True and
            receipt.get('termination_attempted') is False and
            receipt.get('reaped') is True and receipt.get('returncode') == 0 and
            receipt.get('group_state') == 'absent' and
            receipt.get('cleanup_errors') == [] and
            receipt.get('stderr_complete') is True and receipt.get('stderr_bytes') == 0 and
            receipt.get('stdout_complete') is True and receipt.get('partial_stdout_bytes') == 0 and
            receipt.get('watchdog_fired') is False and receipt.get('watchdog_error') is None):
        raise TransportError('unhealthy owned cleanup receipt')
    return receipt


class ProcessTransport:
    """Own exactly one newly spawned session, without process searches.

    Group signals require the original unreaped Popen child to retain its
    observed PID=PGID=SID identity. Once wait() reaps the leader, the adapter
    never signals that numeric group again; a surviving group is reported and
    blocks health. This avoids targeting a potentially reused group identifier.
    A group probe is an observation at that time, not retroactive termination.
    """
    def __init__(self, argv, root, environment, deadline, *, cleanup_deadline=None,
                 clock=None):
        self.clock = clock or time.monotonic
        cleanup_deadline = deadline + MAX_CLEANUP_SECONDS if cleanup_deadline is None else cleanup_deadline
        if not (type(deadline) in (int, float) and math.isfinite(deadline) and
                type(cleanup_deadline) in (int, float) and math.isfinite(cleanup_deadline) and
                self.clock() < deadline <= cleanup_deadline <= deadline + MAX_CLEANUP_SECONDS):
            raise TransportError('finite work and cleanup deadlines required')
        self.deadline, self.cleanup_deadline = deadline, cleanup_deadline
        self.process = self.stderr = self.watchdog = None
        self.buffer = b''
        self.closed = self.closing = self.reaped = False
        self.watchdog_fired, self.watchdog_error = False, None
        self.termination_attempted = False
        self.ownership = None
        self.operations, self.cleanup_errors = [], []
        self._lock = threading.Lock()
        self.launched_monotonic = None
        self.close_receipt = None
        try:
            self.stderr = tempfile.TemporaryFile()
            self.process = subprocess.Popen(argv, cwd=root, env=environment,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                start_new_session=True)
            self.launched_monotonic = self.clock()
            pid = self.process.pid
            pgid, sid = os.getpgid(pid), os.getsid(pid)
            if type(pid) is not int or pid <= 0 or (pgid, sid) != (pid, pid):
                raise TransportError('new child session ownership mismatch')
            self.ownership = dict(pid=pid, pgid=pgid, sid=sid,
                observed_monotonic=self.launched_monotonic)
            os.set_blocking(self.process.stdin.fileno(), False)
            os.set_blocking(self.process.stdout.fileno(), False)
            self.watchdog = threading.Timer(max(0, cleanup_deadline - self.clock()), self._expire)
            self.watchdog.daemon = True
            self.watchdog.start()
        except BaseException as primary:
            receipt = self.close()
            primary.cleanup_receipt = receipt
            primary._postclosure_cleanup_failures = [item['exception_type'] for item in self.cleanup_errors]
            raise

    @property
    def pid(self):
        return self.process.pid

    def _operation(self, name, action, *, absence=False):
        try:
            value = action()
        except ProcessLookupError as error:
            if absence:
                self.operations.append(dict(operation=name, outcome='absent'))
                return 'absent', None
            self._error(name, error)
            return 'error', None
        except BaseException as error:
            self._error(name, error)
            return 'error', None
        self.operations.append(dict(operation=name, outcome='ok'))
        return 'ok', value

    def _error(self, name, error):
        # Never include exception messages, command arguments or environment.
        item = dict(operation=name, exception_type=type(error).__name__)
        if isinstance(error, OSError) and type(error.errno) is int:
            item['errno'] = error.errno
        self.cleanup_errors.append(item)
        self.operations.append(dict(operation=name, outcome='error', **{k: v for k, v in item.items() if k != 'operation'}))

    def _signal_group(self, sig, name):
        if self.process is None or self.reaped or self.process.returncode is not None:
            self.operations.append(dict(operation=name, outcome='skipped_unproven_or_reaped'))
            return
        if self.ownership is None:
            # Constructor recovery still owns its unreaped child, but has no
            # authority over an unobserved group/session.
            self.termination_attempted = True
            self._operation(name + '-child', lambda: os.kill(self.process.pid, sig), absence=True)
            return
        pid = self.ownership['pid']
        state, identity = self._operation(name + '-identity',
            lambda: (os.getpgid(pid), os.getsid(pid)), absence=True)
        if state != 'ok':
            return
        if identity != (self.ownership['pgid'], self.ownership['sid']):
            self._error(name + '-identity', TransportError('owned session identity changed'))
            return
        self.termination_attempted = True
        self._operation(name, lambda: os.killpg(self.ownership['pgid'], sig), absence=True)

    def _expire(self):
        with self._lock:
            if self.closing or self.closed:
                return
            self.watchdog_fired = True
            previous = len(self.cleanup_errors)
            self._signal_group(signal.SIGKILL, 'watchdog-kill')
            if len(self.cleanup_errors) != previous:
                self.watchdog_error = self.cleanup_errors[-1]['exception_type']

    def write(self, data, deadline):
        sent = 0
        while sent < len(data):
            remaining = min(deadline, self.deadline) - self.clock()
            if remaining <= 0 or not select.select([], [self.process.stdin], [], remaining)[1]:
                raise TimeoutError('owned write deadline')
            count = os.write(self.process.stdin.fileno(), data[sent:])
            if count <= 0:
                raise TransportError('partial owned write')
            sent += count

    def read(self, deadline):
        while b'\n' not in self.buffer:
            remaining = min(deadline, self.deadline) - self.clock()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise TimeoutError('owned read deadline')
            data = os.read(self.process.stdout.fileno(), 65536)
            if not data:
                raise EOFError('owned stdout EOF')
            self.buffer += data
            if len(self.buffer) > MAX_STDOUT:
                raise TransportError('owned stdout limit')
        line, self.buffer = self.buffer.split(b'\n', 1)
        return line + b'\n'

    def drain(self, deadline):
        frames = []
        while self.clock() < min(deadline, self.deadline):
            if b'\n' not in self.buffer and not select.select([self.process.stdout], [], [], 0)[0]:
                break
            frames.append(self.read(deadline))
        return frames

    def _wait(self, name, limit):
        remaining = max(0, min(limit, self.cleanup_deadline - self.clock()))
        try:
            self.process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as error:
            if name == 'wait-kill':
                self._error(name, error)
            else:
                self.operations.append(dict(operation=name, outcome='running'))
        except BaseException as error:
            self._error(name, error)
        else:
            self.operations.append(dict(operation=name, outcome='ok'))
            self.reaped = True

    def _stdout_tail(self):
        while self.clock() < self.cleanup_deadline:
            if not select.select([self.process.stdout], [], [], 0)[0]:
                return False
            try:
                data = os.read(self.process.stdout.fileno(), 65536)
            except BlockingIOError:
                return False
            if not data:
                return True
            self.buffer += data
            if len(self.buffer) > MAX_STDOUT:
                raise TransportError('owned close stdout limit')
        raise TimeoutError('owned close stdout deadline')

    def close(self):
        # All independent cleanup operations continue after signal/wait failure.
        with self._lock:
            if self.closing or self.closed:
                raise TransportError('owned cleanup already requested')
            self.closing = True
            started = self.clock()
            if self.watchdog is not None:
                self._operation('watchdog-cancel', self.watchdog.cancel)
            if self.process is not None:
                self._operation('stdin-close', self.process.stdin.close)
                # EOF permits normal server shutdown before bounded escalation.
                self._wait('wait-eof', 0.25)
                if not self.reaped:
                    self._signal_group(signal.SIGTERM, 'terminate')
                    self._wait('wait-term', 0.5)
                if not self.reaped:
                    self._signal_group(signal.SIGKILL, 'kill')
                    self._wait('wait-kill', MAX_CLEANUP_SECONDS)
                stdout_state, stdout_eof = self._operation('stdout-drain', self._stdout_tail)
                self._operation('stdout-close', self.process.stdout.close)
            else:
                stdout_state, stdout_eof = 'error', False
            stderr_data, stderr_complete = b'', False
            if self.stderr is not None:
                state, _ = self._operation('stderr-seek', lambda: self.stderr.seek(0))
                if state == 'ok':
                    state, captured = self._operation('stderr-read', lambda: self.stderr.read(MAX_STDERR + 1))
                    if state == 'ok':
                        stderr_data = captured
                        stderr_complete = len(captured) <= MAX_STDERR
                        if not stderr_complete:
                            self._error('stderr-limit', TransportError('owned stderr limit'))
                self._operation('stderr-close', self.stderr.close)
            group_state = 'unknown'
            if self.ownership is not None:
                state, _ = self._operation('group-probe',
                    lambda: os.killpg(self.ownership['pgid'], 0), absence=True)
                group_state = {'ok': 'present', 'absent': 'absent', 'error': 'unknown'}[state]
            self.closed = True
        # Do not join a watchdog while holding the lock it may be waiting for.
        if self.watchdog is not None and self.watchdog is not threading.current_thread():
            remaining = max(0, self.cleanup_deadline - self.clock())
            self._operation('watchdog-join', lambda: self.watchdog.join(timeout=remaining))
            state, alive = self._operation('watchdog-stopped', self.watchdog.is_alive)
            if state == 'ok' and alive:
                self._error('watchdog-stopped', TransportError('owned watchdog remains active'))
        frames = []
        while b'\n' in self.buffer:
            frame, self.buffer = self.buffer.split(b'\n', 1)
            frames.append(frame + b'\n')
        self.close_receipt = _CleanupReceipt(
            ownership=self.ownership, cleanup_started=True, cleanup_finished=True,
            cleanup_started_monotonic=started, cleanup_finished_monotonic=self.clock(),
            cleanup_deadline=self.cleanup_deadline, cleanup_errors=list(self.cleanup_errors),
            termination_attempted=self.termination_attempted,
            operations=list(self.operations), reaped=self.reaped,
            returncode=None if self.process is None else self.process.returncode,
            group_state=group_state, stdout_complete=stdout_state == 'ok' and stdout_eof is True,
            stderr_complete=stderr_complete, stderr_sha256=hashlib.sha256(stderr_data).hexdigest(),
            stderr_bytes=len(stderr_data), partial_stdout_bytes=len(self.buffer), tail_frames=frames,
            watchdog_fired=self.watchdog_fired, watchdog_error=self.watchdog_error)
        return self.close_receipt
