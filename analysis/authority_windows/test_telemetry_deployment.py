"""Deployment binding checks only; no production key, network or account changes."""
import copy
import json
from pathlib import Path
import pytest
from analysis.authority_windows import telemetry_host as host
from analysis.d6.real_execution_calibration_v1.core import digest


def config():
    policy = {'keys': {}, 'context': {}, 'provider': 'fixture'}
    return {'approval': {'approved': True, 'source_trust_approved': True,
                        'policy': policy, 'approved_policy_digest': digest(policy)},
            'time_sources': {'approved': True, 'policy_digest': digest(policy),
                'authentication': 'UNAUTHENTICATED_NTP',
                'sources': ['time.google.com', 'time.cloudflare.com', 'time.windows.com']}}


@pytest.mark.parametrize('mutation', ['approval', 'source_approval', 'policy', 'source_digest', 'host', 'authentication'])
def test_configuration_rejects_changed_trust(tmp_path, monkeypatch, mutation):
    value = config()
    if mutation == 'approval': value['approval']['approved'] = False
    elif mutation == 'source_approval': value['time_sources']['approved'] = False
    elif mutation == 'policy': value['approval']['policy']['provider'] = 'changed'
    elif mutation == 'source_digest': value['time_sources']['policy_digest'] = '0'*64
    elif mutation == 'host': value['time_sources']['sources'][0] = 'unapproved.invalid'
    else: value['time_sources']['authentication'] = 'claimed-authenticated'
    (tmp_path/'deployment.json').write_text(json.dumps(value))
    monkeypatch.setattr(host, 'RUNTIME', tmp_path)
    with pytest.raises(ValueError): host.configuration()


def test_existing_approved_configuration_preserved(tmp_path, monkeypatch):
    value = config()
    (tmp_path/'deployment.json').write_text(json.dumps(value))
    monkeypatch.setattr(host, 'RUNTIME', tmp_path)
    assert host.configuration() == value
