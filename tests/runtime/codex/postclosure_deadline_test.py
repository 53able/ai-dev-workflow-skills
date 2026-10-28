"""Simulated-clock/MockIO proof only; never launch an actual producer."""
import json
import unittest

import postclosure as core
import postclosure_operator as op
from postclosure_deadline import await_terminal


class Clock:
    def __init__(self, now=0):
        self.now = now
        self.ticks = 0

    def __call__(self):
        return self.now

    def ns(self):
        self.ticks += 1
        return self.ticks


class MockIO:
    def __init__(self, clock, frames):
        self.clock = clock
        self.frames = list(frames)
        self.deadlines = []

    def read(self, deadline):
        self.deadlines.append(deadline)
        if not self.frames or self.frames[0][0] >= deadline:
            self.clock.now = deadline
            raise TimeoutError('mock read deadline')
        at, frame = self.frames.pop(0)
        self.clock.now = at
        if isinstance(frame, BaseException):
            raise frame
        return (json.dumps(frame) + '\n').encode()


def terminal(thread='thread-1', status='completed'):
    return {'method': 'turn/completed', 'params': {
        'threadId': thread, 'turn': {'id': 'turn-1', 'status': status}}}


def progress():
    return {'method': 'turn/started', 'params': {
        'threadId': 'thread-1', 'turn': {'id': 'turn-1', 'status': 'inProgress'}}}


class DeadlineTests(unittest.TestCase):
    def rpc(self, frames=(), now=0, hard_deadline=180):
        clock = Clock(now)
        transport = MockIO(clock, frames)
        rpc = op.RecordingRPC(transport, hard_deadline, clock=clock, monotonic_ns=clock.ns)
        rpc.thread_id = 'thread-1'
        rpc.turn_id = 'turn-1'
        rpc.dispatched = True
        return rpc, transport, clock

    def test_old_no_argument_loop_reproduces_idle_30_failure(self):
        rpc, io, clock = self.rpc([(119.581, terminal())], now=29.581)
        with self.assertRaisesRegex(TimeoutError, 'mock read deadline'):
            while not rpc.completed:
                rpc.receive()
        self.assertAlmostEqual(clock.now, 59.581)
        self.assertEqual(io.deadlines, [59.581])
        self.assertFalse(rpc.completed)
        self.assertTrue(rpc.failed)

    def test_90_seconds_silent_then_healthy_terminal_before_180(self):
        rpc, io, clock = self.rpc([(119.581, terminal())], now=29.581)
        await_terminal(rpc, 180, clock)
        self.assertAlmostEqual(clock.now, 119.581)
        self.assertEqual(io.deadlines, [180])
        self.assertTrue(rpc.completed)
        self.assertFalse(rpc.failed)
        self.assertTrue(core.load_legacy().healthy_terminal(rpc.events, 'live'))

    def test_progress_does_not_extend_original_deadline(self):
        rpc, io, clock = self.rpc([(20, progress()), (100, progress()), (179, progress()),
                                  (181, terminal())])
        with self.assertRaises(TimeoutError):
            await_terminal(rpc, 180, clock)
        self.assertEqual(io.deadlines, [180, 180, 180, 180])
        self.assertEqual(clock.now, 180)
        self.assertFalse(rpc.completed)

    def test_expired_deadline_never_reads(self):
        for now in (180, 181):
            with self.subTest(now=now):
                rpc, io, clock = self.rpc(now=now)
                with self.assertRaisesRegex(TimeoutError, 'absolute terminal deadline'):
                    await_terminal(rpc, 180, clock)
                self.assertEqual(io.deadlines, [])

    def test_recording_rpc_hard_deadline_remains_authoritative(self):
        rpc, io, clock = self.rpc([(150, terminal())], hard_deadline=120)
        with self.assertRaises(TimeoutError):
            await_terminal(rpc, 180, clock)
        self.assertEqual(io.deadlines, [120])

    def test_transport_errors_propagate_without_retry(self):
        for error in (EOFError('mock EOF'), OSError('mock read failure'),
                      TimeoutError('mock timeout')):
            with self.subTest(error=type(error).__name__):
                rpc, io, clock = self.rpc([(10, error), (11, terminal())])
                with self.assertRaises(type(error)) as caught:
                    await_terminal(rpc, 180, clock)
                self.assertIs(caught.exception, error)
                self.assertEqual(io.deadlines, [180])
                self.assertEqual(len(io.frames), 1)

    def test_owned_rpc_rejects_foreign_or_unhealthy_terminal_without_retry(self):
        for frame in (terminal(thread='foreign'), terminal(status='failed')):
            with self.subTest(frame=frame):
                rpc, io, clock = self.rpc([(10, frame), (11, terminal())])
                with self.assertRaises(core.Hold):
                    await_terminal(rpc, 180, clock)
                self.assertEqual(io.deadlines, [180])
                self.assertTrue(rpc.failed)
                self.assertEqual(len(io.frames), 1)

    def test_nonfinite_deadline_or_clock_never_reads(self):
        for deadline, now in ((float('inf'), 0), (float('nan'), 0),
                              (180, float('inf')), (180, float('nan'))):
            with self.subTest(deadline=deadline, now=now):
                rpc, io, clock = self.rpc(now=now)
                with self.assertRaises(ValueError):
                    await_terminal(rpc, deadline, clock)
                self.assertEqual(io.deadlines, [])

    def test_already_completed_never_reads(self):
        rpc, io, clock = self.rpc()
        rpc.completed = True
        await_terminal(rpc, 180, clock)
        self.assertEqual(io.deadlines, [])


if __name__ == '__main__':
    unittest.main()
