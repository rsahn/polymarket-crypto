"""Unsigned clock payload preparation. Does not approve a time source or arm D6.

Existing production EvidenceVerifier/ProductionAuthority remain unchanged.
A designated producer must run measurements continuously and authenticate them.
"""
import math


class ClockCandidate:
    def __init__(self, *, wall_ms, monotonic_ms):
        self.wall_ms = wall_ms
        self.monotonic_ms = monotonic_ms
        self._lease = None

    def invalidate(self):
        self._lease = None

    def update(self, samples):
        # A failed refresh must never leave an earlier successful lease usable.
        self.invalidate()
        now, mono = self.wall_ms(), self.monotonic_ms()
        if not samples or len({s.get('host') for s in samples}) < 3:
            raise ValueError('TIME_SOURCES_REQUIRED')
        intervals = []
        oldest = now
        for s in samples:
            observed = s.get('observed_ms')
            offset, uncertainty = s.get('offset_ms'), s.get('uncertainty_ms')
            if (type(observed) is not int or not 0 <= now-observed <= 5000
                or type(offset) not in (int, float) or type(uncertainty) not in (int, float)
                or not math.isfinite(offset) or not math.isfinite(uncertainty)
                or uncertainty < 0 or abs(offset)+uncertainty > 100):
                raise ValueError('TIME_MEASUREMENT_INVALID')
            intervals.append((offset-uncertainty, offset+uncertainty))
            oldest = min(oldest, observed)
        if max(lo for lo, _ in intervals) > min(hi for _, hi in intervals):
            raise ValueError('TIME_SOURCES_DISAGREE')
        # Enclose every accepted interval; rounding and local-step allowance
        # can only make the candidate more conservative than raw observations.
        lo, hi = min(x[0] for x in intervals), max(x[1] for x in intervals)
        offset = round((lo+hi)/2)
        uncertainty = math.ceil(max(offset-lo, hi-offset)) + 2
        if abs(offset)+uncertainty > 100:
            raise ValueError('CONSERVATIVE_CLOCK_BOUND')
        self._lease = (now, mono, oldest, offset, uncertainty)
        return self.read()

    def read(self):
        if self._lease is None:
            raise ValueError('NO_CLOCK_LEASE')
        wall, mono, oldest, offset, uncertainty = self._lease
        elapsed = self.monotonic_ms()-mono
        now = self.wall_ms()
        if elapsed < 0 or now-oldest > 5000 or now < wall or abs(now-wall-elapsed) > 2:
            self.invalidate()
            raise ValueError('CLOCK_STALE_OR_STEP')
        return dict(payload=dict(offset_ms=offset, uncertainty_ms=uncertainty),
                    observed_ms=oldest, valid_until_ms=oldest+5000,
                    signed=False, production_qualified=False)


def main():
    import json
    from pathlib import Path
    import sys
    import time
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from analysis.provisioning_live_observe import ntp
    candidate = ClockCandidate(wall_ms=lambda: time.time_ns()//1000000,
                               monotonic_ms=lambda: time.monotonic_ns()//1000000)
    observations = []
    for _ in range(3):
        samples = [ntp(host) for host in ('time.google.com', 'time.cloudflare.com', 'time.windows.com')]
        try:
            payload = candidate.update(samples)
            observations.append(dict(samples=samples, candidate=payload))
        except ValueError as exc:
            candidate.invalidate()
            observations.append(dict(samples=samples, rejection=str(exc)))
        time.sleep(.25)
    report = dict(unsigned_only=True, production_qualified=False, observations=observations,
                  source_policy_approved=False, live_monitor_stopped=True)
    with Path(sys.argv[1]).open('x', encoding='utf-8') as out:
        json.dump(report, out, indent=2)
    print(json.dumps(dict(candidate_updates=sum('candidate' in x for x in observations),
                         total=len(observations), production_qualified=False)))


if __name__ == '__main__':
    main()
