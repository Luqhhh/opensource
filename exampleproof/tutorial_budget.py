"""Observed cumulative token threshold and fail-closed wall-clock deadline."""
from contextlib import contextmanager
import math
import signal
import threading
import time


class AnalysisDeadline(ValueError):
    pass


def validate_limits(max_total_tokens=None, deadline_seconds=None):
    if max_total_tokens is not None and (type(max_total_tokens) is not int or max_total_tokens < 1):
        raise ValueError("Total token threshold must be a positive integer")
    if deadline_seconds is not None and (type(deadline_seconds) not in {int, float} or not math.isfinite(deadline_seconds) or deadline_seconds <= 0):
        raise ValueError("Deadline must be finite and positive")


@contextmanager
def deadline(seconds):
    """Interrupt blocking HTTP too; unsupported contexts stop before starting work."""
    validate_limits(deadline_seconds=seconds)
    if seconds is None:
        yield
        return
    if not hasattr(signal, "setitimer") or threading.current_thread() is not threading.main_thread():
        raise ValueError("A hard deadline requires a POSIX main thread; no unbounded fallback")
    old_handler = signal.getsignal(signal.SIGALRM)
    old_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    def expire(signum, frame):
        raise AnalysisDeadline("Analysis wall-clock deadline exceeded")
    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, min(seconds, old_timer[0]) if old_timer[0] else seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        remaining = old_timer[0] - (time.monotonic() - started)
        if old_timer[0] and remaining > 0:
            signal.setitimer(signal.ITIMER_REAL, remaining, old_timer[1])


def token_state(calls, threshold):
    values = [(c.get("input_tokens"), c.get("output_tokens")) for c in calls]
    known = all(type(v) is int and v >= 0 for pair in values for v in pair)
    total = sum(sum(pair) for pair in values) if known else None
    reason = None
    if calls and threshold is not None:
        reason = "usage_unknown" if not known else "token_budget" if total >= threshold else None
    return {"max_total_tokens": threshold, "observed_total_tokens": total, "stop_reason": reason,
            "semantics": "Observed input+output threshold checked before each next call; one in-flight request may exceed it. Unknown usage stops further calls."}
