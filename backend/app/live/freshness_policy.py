"""Deprecated compatibility context for historical callers/tests only.
Production domain guards no longer consume this global value. In particular,
1300 cannot relax the book or create readiness. Use temporal_contract policies.
"""
from contextlib import contextmanager
from contextvars import ContextVar

_limit = ContextVar('d6_freshness_limit_ms', default=500)


def freshness_limit_ms():
    return _limit.get()


def stale_reason(prefix):
    return f'{prefix}_STALE_{freshness_limit_ms()}MS'


@contextmanager
def freshness_policy(limit):
    if type(limit) is not int or limit not in (500, 1300):
        raise ValueError('UNAPPROVED_FRESHNESS_POLICY')
    token = _limit.set(limit)
    try:
        yield
    finally:
        _limit.reset(token)
