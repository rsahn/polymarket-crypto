"""Architecture experiments ONLY. No production acceptance, authority or exposure.

The custody process is a sibling of a disposable supervisor. Test acceptance is
explicitly labelled TEST_ONLY and must never be consumed by production code.
"""
import json
import hashlib
import multiprocessing
import os
from pathlib import Path
import time
import pytest
from eth_account import Account
from eth_account.messages import encode_defunct


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def write_new(path, value):
    with open(path, 'x', encoding='utf-8') as handle:
        handle.write(canonical(value))
        handle.flush()
        os.fsync(handle.fileno())


def custody_service(directory, ready, release):
    key = Account.create()  # test key, never provisioned or written to disk
    request = {'schema': 'TEST_ONLY', 'session': 'test', 'revision': 'r1',
               'future_results': ['test-intent-1'], 'acceptance': 'TEST_ONLY'}
    write_new(Path(directory)/'request.json', request)
    receipt = {'schema': 'TEST_ONLY', 'owner': key.address, 'request': request}
    receipt['signature'] = key.sign_message(encode_defunct(text='D6_TEST_CUSTODY:'+canonical(receipt))).signature.hex()
    write_new(Path(directory)/'receipt.json', receipt)
    ready.set()
    release.wait(15)


def disposable_supervisor(ready):
    ready.set()
    time.sleep(30)


def verify_receipt(receipt, expected, public_key):
    envelope = dict(receipt)
    signature = envelope.pop('signature')
    return (envelope.get('schema') == 'TEST_ONLY' and envelope.get('request') == expected
        and Account.recover_message(encode_defunct(text='D6_TEST_CUSTODY:'+canonical(envelope)),
                                    signature=bytes.fromhex(signature)) == public_key)


def test_signed_durable_custody_survives_supervisor_death_and_reader_restart(tmp_path):
    ctx = multiprocessing.get_context('spawn')
    custody_ready, supervisor_ready, release = ctx.Event(), ctx.Event(), ctx.Event()
    owner = ctx.Process(target=custody_service, args=(str(tmp_path), custody_ready, release))
    supervisor = ctx.Process(target=disposable_supervisor, args=(supervisor_ready,))
    owner.start(); supervisor.start()
    try:
        assert custody_ready.wait(10) and supervisor_ready.wait(10)
        request = json.loads((tmp_path/'request.json').read_text())
        receipt = json.loads((tmp_path/'receipt.json').read_text())
        pinned_test_key = receipt['owner']  # fixture pin, NOT independent production approval
        assert verify_receipt(receipt, request, pinned_test_key)
        supervisor.terminate(); supervisor.join(5)
        assert not supervisor.is_alive() and owner.is_alive()
        del receipt
        recovered = json.loads((tmp_path/'receipt.json').read_text())
        assert verify_receipt(recovered, request, pinned_test_key)
        assert not verify_receipt(recovered, {**request, 'revision': 'r2'}, pinned_test_key)
        assert not verify_receipt(recovered, {**request, 'future_results': []}, pinned_test_key)
        recovered['request']['revision'] = 'tampered'
        assert not verify_receipt(recovered, recovered['request'], pinned_test_key)
    finally:
        release.set()
        owner.join(5)
        if owner.is_alive(): owner.terminate(); owner.join(5)
        if supervisor.is_alive(): supervisor.terminate(); supervisor.join(5)


@pytest.mark.parametrize('changed', ['code', 'policy', 'deployment'])
def test_durable_technical_attestation_invalidated_by_binding_change(changed):
    approved = {'code': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'policy': 'test-only-policy', 'deployment': 'test-only-deployment'}
    key = Account.create()
    receipt = {'schema': 'TEST_ONLY', 'owner': key.address, 'request': approved}
    receipt['signature'] = key.sign_message(encode_defunct(text='D6_TEST_CUSTODY:'+canonical(receipt))).signature.hex()
    current = dict(approved)
    assert verify_receipt(receipt, current, key.address)
    current[changed] = 'different'
    assert not verify_receipt(receipt, current, key.address)
    # Even substituting the embedded binding to match the changed deployment
    # cannot repair the signature without the independent signing key.
    forged = {**receipt, 'request': current}
    assert not verify_receipt(forged, current, key.address)


def test_open_order_and_chain_views_cannot_prove_all_terminal_history():
    history_a = []
    history_b = [{'id': 'unknown-unfilled-cancelled-order', 'status': 'CANCELED', 'fills': []}]
    def observed(history):
        return {'open': [x for x in history if x['status']=='LIVE'],
                'chain_fills': [f for x in history for f in x['fills']]}
    assert history_a != history_b
    assert observed(history_a) == observed(history_b)
    # Additional exchange/archive evidence is necessary for the literal full-history invariant.


def test_candidate_signed_channel_requires_durable_manual_acceptance(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from analysis.provisioning_signed_custody import (
        SignedManualChannel, SignedReceiptAuthority, ManualReceiptVerifier, DOMAIN,
        encoded, write_document, ManualCustodyChannel)
    from analysis.d6.real_execution_calibration_v1.core import digest
    now = [1000]
    platform = SimpleNamespace(sid='TEST_ONLY',create_private_directory=lambda p:p.mkdir())
    base = ManualCustodyChannel(tmp_path/'custody',clock=lambda:now[0],platform=platform,acl=lambda *a:None)
    channel = SignedManualChannel(base)
    key = Account.create()
    authority = SignedReceiptAuthority(channel, pinned_address=key.address)
    exposure = {'orders':{'test-intent':{'order_id':None}},'positions':{},'cash':'0'}
    r = dict(account='TEST_ONLY',experiment_id='TEST_ONLY',exposure=exposure,
        exposure_digest=digest(exposure),exposure_revision=digest(exposure),journal_sequence=0)
    assert asyncio.run(channel.accept(r)) is None
    challenge = base.challenge(r)
    monkeypatch.setattr('sys.stdin', SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr('builtins.input', lambda: 'ACCEPT CUSTODY '+r['experiment_id']+' '+r['exposure_digest']+' '+challenge['nonce'])
    receipt = base.accept_interactively(challenge['challenge_id'])
    assert asyncio.run(channel.accept(r)) is None  # unsigned receipt insufficient
    receipt['custody_signature'] = key.sign_message(encode_defunct(text=DOMAIN+encoded(receipt))).signature.hex()
    assert not asyncio.run(authority.verify_durable(receipt))  # not persisted yet
    import analysis.provisioning_signed_custody as candidate
    monkeypatch.setattr(candidate,'load_key',lambda *a:key)
    monkeypatch.setattr(candidate,'ManualCustodyChannel',lambda *a:base)
    monkeypatch.setattr('sys.argv',['signed-custody','--directory',str(base.directory),
        '--resume-accepted',receipt['receipt_id'],'--key-file','TEST_ONLY',
        '--approved-public-address',key.address])
    monkeypatch.setattr('builtins.input',lambda *a:'SIGN ACCEPTED CUSTODY '+receipt['receipt_id'])
    candidate.main()  # recover the crash gap: accepted, but not yet signed
    stored_bytes = (base.directory/(receipt['receipt_id']+'.signed.json')).read_bytes()
    candidate.main()  # idempotent restart, no overwrite
    assert (base.directory/(receipt['receipt_id']+'.signed.json')).read_bytes() == stored_bytes
    assert asyncio.run(channel.accept(r)) == receipt
    verifier = ManualReceiptVerifier(authority)
    assert asyncio.run(verifier.verify(receipt,r))
    now[0] = 9000
    assert asyncio.run(verifier.verify(receipt,r))  # accepted responsibility persists
    assert not asyncio.run(SignedReceiptAuthority(channel,pinned_address=Account.create().address).verify_durable(receipt))
    assert not asyncio.run(authority.verify_durable({**receipt,'future_result_client_ids':[]}))
    assert not asyncio.run(verifier.verify(receipt,{**r,'exposure_digest':'0'*64}))


def test_candidate_cli_requires_human_terminal_before_key_read(monkeypatch):
    from io import StringIO
    from analysis.provisioning_signed_custody import main
    monkeypatch.setattr('sys.stdin',StringIO())
    monkeypatch.setattr('sys.argv',['signed-custody','--directory','absent','--accept','absent',
        '--key-file','must-not-read.dpapi','--approved-public-address','absent'])
    with pytest.raises(ValueError,match='OPERATOR_TTY_REQUIRED'):
        main()
