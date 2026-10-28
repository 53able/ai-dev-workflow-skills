"""Inert candidate for a future reviewed source epoch; no producer integration."""
import math


def await_terminal(rpc, absolute_deadline, clock):
    """Receive through the original deadline using the caller's owned RPC.

    RPC retains protocol/identity validation and its own hard deadline. The
    caller retains terminal health checks, draining, and lifecycle ownership.
    Errors propagate directly; this helper never retries or dispatches input.
    """
    if not math.isfinite(absolute_deadline):
        raise ValueError('finite absolute deadline required')
    while not rpc.completed:
        remaining = absolute_deadline - clock()
        if not math.isfinite(remaining):
            raise ValueError('finite remaining deadline required')
        if remaining <= 0:
            raise TimeoutError('absolute terminal deadline')
        rpc.receive(timeout=remaining)
