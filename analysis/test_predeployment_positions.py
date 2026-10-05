"""Adversarial checks for the read-only predeployment coverage collector."""
import json
from decimal import Decimal
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_predeployment_positions as scan
from provisioning_identity_book import diagnostic_json


def item(logs=None):
    logs = [] if logs is None else logs
    return dict(from_block=0, to_block=29999, logs=logs, sha256=scan.digest(logs))


def row():
    return dict(removed=False, blockNumber=hex(12), blockHash='0x'+'11'*32,
                logIndex='0x0', topics=[scan.SINGLE, '0x'+'00'*32,
                                     '0x'+'00'*32, scan.PAD])


def test_resume_validated_checkpoint_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(scan, 'BASE', tmp_path)
    checkpoint = item()
    (tmp_path/'range_000000000_000029999.json').write_text(json.dumps(checkpoint))
    monkeypatch.setattr(scan, 'RPC', lambda *_: pytest.fail('checkpoint refetched'))
    assert scan.fetch((0, 29999)) == checkpoint


@pytest.mark.parametrize('mutation', ['hash', 'bounds', 'removed', 'outside', 'recipient', 'topic', 'duplicate', 'cap'])
def test_untrusted_coverage_rejected(mutation):
    value = item([row()])
    if mutation == 'hash':
        value['sha256'] = '0'*64
    elif mutation == 'bounds':
        value['from_block'] = 1
    else:
        log = value['logs'][0]
        if mutation == 'removed': log['removed'] = True
        elif mutation == 'outside': log['blockNumber'] = hex(30000)
        elif mutation == 'recipient': log['topics'][3] = '0x'+'00'*32
        elif mutation == 'topic': log['topics'][0] = '0x'+'00'*32
        elif mutation == 'duplicate': value['logs'].append(log.copy())
        elif mutation == 'cap': value['logs'] *= 10000
        value['sha256'] = scan.digest(value['logs'])
    with pytest.raises(ValueError): scan.validate(value, 0, 29999)


def test_provider_failure_not_cached_as_empty(tmp_path, monkeypatch):
    class FailedRPC:
        def __init__(self, *_): pass
        def call(self, *_): raise TimeoutError()
    monkeypatch.setattr(scan, 'BASE', tmp_path)
    monkeypatch.setattr(scan, 'RPC', FailedRPC)
    result = scan.fetch((0, 29999))
    assert result['error_type'] == 'TimeoutError'
    assert 'logs' not in result and not list(tmp_path.iterdir())


def test_nonempty_receipts_retained():
    value = item([row()])
    assert scan.validate(value, 0, 29999)['logs'] == [row()]


def test_diagnostic_decimal_preserves_precision():
    assert json.loads(json.dumps({'p': Decimal('0.1234567890123456789')}, default=diagnostic_json))['p'] == '0.1234567890123456789'
    with pytest.raises(TypeError): diagnostic_json(Decimal('NaN'))
    with pytest.raises(TypeError): diagnostic_json(object())
