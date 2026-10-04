import copy
import pytest
from analysis.provisioning_clock_candidate import ClockCandidate


def setup():
    time = [10000, 10000]
    lease = ClockCandidate(wall_ms=lambda: time[0], monotonic_ms=lambda: time[1])
    samples = [dict(host=h, observed_ms=10000, offset_ms=1.2, uncertainty_ms=50.1)
               for h in ('one', 'two', 'three')]
    return time, lease, samples


def test_conservative_unsigned_payload():
    _, lease, samples = setup()
    r = lease.update(samples)
    assert r['payload'] == dict(offset_ms=1, uncertainty_ms=53)
    assert r['signed'] is False and r['production_qualified'] is False


@pytest.mark.parametrize('offset,uncertainty', [(99.1, .8), (0, 101), (float('nan'), 1), (0, -1)])
def test_invalid_refresh_invalidates_previous_success(offset, uncertainty):
    _, lease, samples = setup()
    lease.update(samples)
    for s in samples: s.update(offset_ms=offset, uncertainty_ms=uncertainty)
    with pytest.raises(ValueError): lease.update(samples)
    with pytest.raises(ValueError, match='NO_CLOCK_LEASE'): lease.read()


@pytest.mark.parametrize('wall,mono', [(15001,15001), (10003,10000), (9999,10000), (10000,9999)])
def test_expiry_and_clock_steps_fail_closed(wall, mono):
    t, lease, samples = setup(); lease.update(samples)
    t[:] = [wall,mono]
    with pytest.raises(ValueError): lease.read()
    with pytest.raises(ValueError, match='NO_CLOCK_LEASE'): lease.read()


def test_source_disagreement_and_missing_source():
    _, lease, samples = setup()
    with pytest.raises(ValueError): lease.update(samples[:2])
    samples[0].update(offset_ms=-80, uncertainty_ms=1)
    with pytest.raises(ValueError, match='DISAGREE'): lease.update(samples)


def test_oldest_measurement_controls_expiry():
    t, lease, samples = setup(); samples[0]['observed_ms']=5000
    assert lease.update(samples)['valid_until_ms'] == 10000
    t[:] = [10001,10001]
    with pytest.raises(ValueError): lease.read()
