import asyncio,io,json,subprocess,sys,types
from pathlib import Path
import pytest
from .core import CalibrationLedger,Journal,digest
from .live_logging import LiveLog,LoggedJournal

CONDITION='0x'+'a'*64
TX='0x'+'b'*64

def test_typed_canonical_shadow_and_closed_recovery(tmp_path):
    log=LiveLog(tmp_path,'fixture',console=io.StringIO(),background=False)
    log.public_tokens.update({'1','2'});log.public_markets.add(CONDITION);log.public_transactions.add(TX)
    journal=LoggedJournal(tmp_path/'sealed.jsonl','fixture',log);ledger=CalibrationLedger(journal,'fixture','100')
    shadow={'market':CONDITION,'token':'1','actual_selected_book':{'market':CONDITION,'token':'1','asks':[['.5','2']],'bids':[['.4','2']]},'expected_quantity':'2','expected_exit_behavior':{'depth':'password=TRUE_SECRET_CANARY','hold_ms':500},'private_key':'KEY_CANARY'}
    sealed=journal.project_shadow(shadow)
    assert journal.project_shadow(sealed)==sealed
    h=ledger.seal_shadow('op',shadow);assert ledger.shadows['op']==(h,sealed)
    journal.append('FILL_OBSERVATION',{'client_id':'fixture','fill':{'trade_id':'trade','transaction_hash':TX,'token':'1','market':CONDITION,'shares':'1','fee_evidence':{'cash_effect_proven':True,'access_token':'ACCESS_CANARY'}}})
    ledger.checkpoint();journal.close();log.close()
    rows=list(Journal.read(journal.path));record=next(x['payload'] for x in rows if x['kind']=='SHADOW_SEALED')
    assert record['shadow']==sealed and digest(record['shadow'])==record['sha256']==h
    content=journal.path.read_text()+log.path.read_text()+log.console.getvalue()
    assert CONDITION in content and TX in content and 'CANARY' not in content
    operational=[json.loads(line) for line in log.path.read_text().splitlines()]
    logged=next(x['payload'] for x in operational if x['kind']=='SHADOW_SEALED')
    assert logged==record
    recovered=CalibrationLedger.recover(journal.path)
    assert recovered['shadow_hashes']['op']==h and not recovered['resume_allowed']

def test_foreign_public_position_remains_in_authoritative_journal(tmp_path):
    from .test_calibration import snapshot
    log=LiveLog(tmp_path,'fixture',console=io.StringIO(),background=False);log.public_tokens.update({'1','2'})
    journal=LoggedJournal(tmp_path/'positions.jsonl','fixture',log);ledger=CalibrationLedger(journal,'account','100')
    foreign=str(2**200+123)
    observation=snapshot(ledger,positions={foreign:'7.25'})
    try:
        assert not ledger.reconcile(observation,1000) and ledger.stop
        records=list(Journal.read(journal.path));saved=next(x['payload']['snapshot'] for x in records if x['kind']=='RECONCILIATION_OBSERVATION')
        assert saved['positions']==observation['positions'] and foreign in log.path.read_text()
    finally:journal.close();log.close()

def test_guarded_crash_recovers_typed_live_shadow(tmp_path):
    child=tmp_path/'crash'
    result=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('crash_fixture.py')),str(child)],capture_output=True,timeout=15)
    assert result.returncode==9,result.stderr.decode()
    path=child/'typed-live-fixture'/'sealed.jsonl'
    recovered=CalibrationLedger.recover(path)
    p=next(r['payload'] for r in recovered['verified_rows'] if r['kind']=='SHADOW_SEALED')
    assert p['shadow']['market']==CONDITION and p['sha256']==digest(p['shadow'])
    assert 'CANARY' not in path.read_text() and not recovered['resume_allowed']

def test_sdk_binding_only_reads_public_identity():
    from polymarket import AsyncSecureClient
    from .readonly_provider import SDKIdentityBinding
    wallet='0x'+'1'*40;signer='0x'+'2'*40
    class Context:
        from polymarket.environments import PRODUCTION as environment
        @property
        def credentials(self):raise AssertionError('SECRET_READ')
    ctx=Context();ctx.wallet=wallet;ctx.signer=types.SimpleNamespace(address=signer)
    client=object.__new__(AsyncSecureClient);client._ended=False;client._ctx=ctx
    binding=SDKIdentityBinding.inspect(client,wallet=wallet,signer=signer)
    assert binding.matches(client) and not binding.report()['transport_qualified'] and not binding.report()['submit_allowed']
    assert not binding.matches(object());ctx.wallet='0x'+'3'*40;assert not binding.matches(client)

def test_concrete_readonly_provider_never_promotes_scope(tmp_path):
    from app.live.network_readonly import GetOnlyTransport,ReadOnlyClient
    from .readonly_provider import RepositoryReadOnlyProvider
    wallet='0x'+'1'*40
    clob=GetOnlyTransport('https://clob.polymarket.com',('/balance-allowance','/data/orders','/data/trades'))
    data=GetOnlyTransport('https://data-api.polymarket.com',('/v2/positions',))
    client=ReadOnlyClient(wallet=wallet,signature_type=0,clob=clob,data=data)
    provider=RepositoryReadOnlyProvider(client,wallet=wallet,spender='0x'+'2'*40,collateral='pUSD',asset_types={'1':'CONDITIONAL'},session='fixture',clock=lambda:1000)
    async def account():return dict(available=True,wallet=wallet,collateral_symbol='pUSD',observed_ms=1000,balance_collateral='100',open_order_ids=[],trade_ids=[],scope='credential')
    async def positions():return dict(available=True,wallet=wallet,collateral_symbol='pUSD',observed_ms=1000,balances={'1':'0'},scope='enumerated_assets')
    provider.account_reader.read=account;provider.position_reader.read=positions
    result=asyncio.run(provider.snapshot())
    assert not any(result[k] for k in ('inventory_proven','cash_proven','orders_complete','trades_complete','positions_complete','finality_proven','fee_effects_proven','independent_attestation','submit_allowed'))
    assert result['atomic_frontier'] is None
    with pytest.raises(ValueError):asyncio.run(provider.execution('order'))
    client.data=GetOnlyTransport('https://data-api.polymarket.com',('/v2/positions',))
    with pytest.raises(ValueError):provider.check_binding()
