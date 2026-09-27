import asyncio,copy,io,types
from pathlib import Path
import pytest
from .core import digest
from .selection import inspect_selection
from .observation_collector import ObservationGET,ReadBudget,bounded_pages,build_collector,ObservationAuthority
from .chain_observer import ReceiptRPC
from .manual_custody import ManualCustodyChannel,ManualReceiptAuthority,ManualReceiptVerifier

def test_selection_conflicts_without_loading_secret_fields(tmp_path):
    from app.live.l2_existing_reader import EXPECTED
    (tmp_path/'.env').write_text('SIGNER_PRIVATE_KEY=SECRET_CANARY\nPOLYMARKET_WALLET_ADDRESS='+EXPECTED+'\nREAL_ORDERS_ENABLED=false\nLIVE_EXECUTION_ARMED=false\n')
    result=inspect_selection(tmp_path,{})
    assert result['selection_ready'] and 'CANARY' not in str(result)
    assert not inspect_selection(tmp_path,{'POLYMARKET_WALLET_ADDRESS':'0x'+'1'*40})['selection_ready']
    assert not inspect_selection(tmp_path,{'READONLY_SIGNER_ADDRESS':'0x'+'1'*40})['selection_ready']

@pytest.mark.parametrize('route',['/order','/orders','/cancel','/auth/api-key','/auth/derive-api-key','/balance-allowance/update'])
def test_forbidden_routes_cannot_construct(route):
    with pytest.raises(ValueError):ObservationGET('https://clob.polymarket.com',(route,),budget=ReadBudget())

@pytest.mark.parametrize('method',['eth_sendRawTransaction','eth_sendTransaction','personal_sign','eth_sign','eth_chainId','eth_getCode'])
def test_rpc_allowlist_rejects_before_network(method):
    rpc=ReceiptRPC('0x'+'1'*40)
    with pytest.raises(ValueError):rpc.call(method,[])
    assert not rpc.calls

def test_pagination_limit_is_not_completeness():
    class Pages:
        def __init__(self,n=0):self.n=n
        async def first_page(self):return types.SimpleNamespace(items=[{'id':str(self.n)}],has_more=True,next_cursor=str(self.n+1))
        def from_cursor(self,c):return Pages(int(c))
    rows,complete,pages=asyncio.run(bounded_pages(Pages()))
    assert len(rows)==2 and pages==2 and complete is False

def test_no_retry_after_429(monkeypatch):
    from app.live.network_readonly import GetOnlyTransport
    calls=[]
    async def fail(self,*a,**kw):self.audit.append({'http_status':429});calls.append(1);raise RuntimeError('fixture')
    monkeypatch.setattr(GetOnlyTransport,'get_json',fail)
    async def case():
        budget=ReadBudget(interval=0);t=ObservationGET('https://clob.polymarket.com',('/time',),budget=budget)
        for _ in range(2):
            with pytest.raises((RuntimeError,ValueError)):await t.get_json('/time')
        assert len(calls)==1 and budget.limited
    asyncio.run(case())

def test_hmac_only_get_no_key_bootstrap():
    creds=dict(apiKey='fixture-key',secret='ZmFrZQ==',passphrase='fixture-pass')
    c=build_collector(creds,'0x'+'1'*40,'0x'+'1'*40,0)
    assert c.client.clob.routes=={'/balance-allowance','/data/orders','/data/trades'}
    h=asyncio.run(c.client.clob.headers('/data/orders'))
    assert h['POLY_API_KEY']=='fixture-key' and h['POLY_SIGNATURE']
    with pytest.raises(ValueError):asyncio.run(c.client.clob.headers('/order'))
    assert not c.audit

def test_observation_authority_does_not_qualify_transport_or_fabricate_scope():
    authority=ObservationAuthority({'session':'fixture'})
    for check in ('account_evidence_adapter_qualified','fee_upper_bound_proven','exit_handoff_ready'):
        with pytest.raises(ValueError):authority.record(check,{},'a'*64,1000)
    record=authority.record('market_identity_verified',{'fixture':True},'a'*64,1000)
    assert authority.verify(record)
    changed=copy.deepcopy(record);changed['payload']['fixture']=False
    assert not authority.verify(changed) and not authority.verify_client(object(),record) and not authority.verify_bindings((),{})

def manual(tmp_path,clock):
    platform=types.SimpleNamespace(sid='OFFLINE_FIXTURE_USER',create_private_directory=lambda p:p.mkdir())
    return ManualCustodyChannel(tmp_path/'custody',clock=clock,platform=platform,acl=lambda *a:None)

def request():
    exposure={'orders':{'fixture-intent':{'order_id':None}},'positions':{'123':'2'},'cash':'98'}
    return dict(account='fixture-account',experiment_id='fixture-session',exposure=exposure,exposure_revision=digest(exposure),exposure_digest=digest(exposure),journal_sequence=12)

def test_designation_is_not_acceptance_and_manual_receipt_is_exact(tmp_path,monkeypatch):
    now=[1000];channel=manual(tmp_path,lambda:now[0]);r=request()
    assert asyncio.run(channel.accept(r)) is None
    challenge=channel.challenge(r)
    monkeypatch.setattr('sys.stdin',types.SimpleNamespace(isatty=lambda:True))
    phrase='ACCEPT CUSTODY '+r['experiment_id']+' '+r['exposure_digest']+' '+challenge['nonce']
    monkeypatch.setattr('builtins.input',lambda:phrase)
    receipt=channel.accept_interactively(challenge['challenge_id'])
    verifier=ManualReceiptVerifier(ManualReceiptAuthority(channel));now[0]=9000
    assert asyncio.run(verifier.verify(receipt,r))  # responsibility does not expire after five seconds
    assert receipt['future_result_client_ids']==['fixture-intent']
    assert asyncio.run(verifier.verify(receipt,r))  # durable acceptance is re-readable, never a new order
    restarted=manual(tmp_path,lambda:now[0])
    assert asyncio.run(ManualReceiptAuthority(restarted).verify_durable(receipt))
    wrong={**r,'exposure_digest':'b'*64}
    assert not asyncio.run(ManualReceiptVerifier(ManualReceiptAuthority(channel)).verify(receipt,wrong))
    assert not asyncio.run(ManualReceiptVerifier(ManualReceiptAuthority(channel)).verify(receipt,{**r,'custody_request_nonce':'new-public-challenge'}))
    changed={**receipt,'future_result_client_ids':[]}
    assert not asyncio.run(ManualReceiptAuthority(channel).verify_durable(changed))

def test_manual_tty_required_and_unaccepted_challenge_can_expire(tmp_path,monkeypatch):
    now=[1000];channel=manual(tmp_path,lambda:now[0]);r=request();c=channel.challenge(r)
    monkeypatch.setattr('sys.stdin',io.StringIO())
    with pytest.raises(ValueError):channel.accept_interactively(c['challenge_id'])
    now[0]=700000;assert channel.request_expired(r)
    assert asyncio.run(channel.accept(r)) is None

def test_unsafe_custody_path_rejected(tmp_path):
    from .manual_custody import read_document
    with pytest.raises((FileNotFoundError,ValueError)):read_document(tmp_path/'absent')

def test_canonical_account_conflict_blocks_before_storage_or_network(tmp_path,monkeypatch):
    from app.live.l2_existing_reader import EXPECTED
    from app.live.genesis_ledger import expected_wallet
    from .qualify_observations import observe
    (tmp_path/'.env').write_text('POLYMARKET_WALLET_ADDRESS='+EXPECTED+'\n')
    (tmp_path/'runtime').mkdir();(tmp_path/'runtime'/'d6_genesis.db').touch()
    monkeypatch.setattr('app.live.genesis_ledger.read_genesis',lambda p:dict(snapshot={'wallet':expected_wallet()},snapshot_sha256='a'*64,phase='GENESIS_RECONCILED'))
    def forbidden(*a):raise AssertionError('MUST_NOT_LOAD_CREDENTIALS')
    monkeypatch.setattr('app.live.l2_existing_reader.load_existing',forbidden)
    selected=inspect_selection(tmp_path,{})
    assert not selected['selection_ready'] and selected['canonical_runtime_account']['wallet']==expected_wallet().lower()
    report=asyncio.run(observe(tmp_path,selected))
    assert report['mode']=='NO_NETWORK_SELECTION_GATE' and report['credentials_accessed'] is False and report['requests']==[]
    explicit=inspect_selection(tmp_path,{},account_choice='canonical-d6')
    assert explicit['selection_ready'] and explicit['selected_wallet']==expected_wallet().lower()

def test_new_manual_challenge_invalidates_in_progress_operator_prompt(tmp_path,monkeypatch):
    channel=manual(tmp_path,lambda:1000);r=request();c=channel.challenge(r)
    monkeypatch.setattr('sys.stdin',types.SimpleNamespace(isatty=lambda:True))
    def changed():
        channel.challenge({**r,'journal_sequence':13})
        return 'ACCEPT CUSTODY '+r['experiment_id']+' '+r['exposure_digest']+' '+c['nonce']
    monkeypatch.setattr('builtins.input',changed)
    with pytest.raises(ValueError,match='CHANGED'):channel.accept_interactively(c['challenge_id'])
    assert not list(channel.directory.glob('*.receipt.json'))
