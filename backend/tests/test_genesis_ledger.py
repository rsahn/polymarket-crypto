import json
import sqlite3
import pytest
from app.live.genesis_ledger import assess,create_genesis,read_genesis,append_activity,reconcile_empty_baseline,digest,expected_wallet,LIMITS
from app.live.collateral_onchain import CONTRACT,CTF


def evidence():
    return {'chain_id':137,'wallet':expected_wallet(),'block_number':42,'block_hash':'0x'+'a'*64,
        'timestamp_ms':1000,'block_hash_rechecked':True,'dedicated_wallet_policy':'D6_DEDICATED_FROM_GENESIS',
        'local_prior_state':'NO_AUTHORITATIVE_LEDGER_CONFIGURED',
        'collateral':{'contract':CONTRACT,'balance_raw':'109160000','qualification_sha256':'a'*64},
        'views':{n:{'rows':[],'observed_ms':1000,'pagination_complete':True,'repeat_sha256':digest([])} for n in ('positions','orders','trades')},
        'conditional_assets':{'contract':CTF,'status':'PASS_SCOPED_READS','start_boundary':'WALLET_CODE_ONSET_READ','to_block':42,'block_hash':'0x'+'a'*64,'balances':{'123':'0'}},
        'journal_assets':[],'coverage_limitations':LIMITS}


def test_atomic_genesis_hash_and_limits(tmp_path):
    p=tmp_path/'ledger.db';s=evidence();r=create_genesis(p,s,now_ms=1001)
    assert r['created'] and r['phase']=='GENESIS_RECONCILED'
    loaded=read_genesis(p)
    assert loaded['snapshot_sha256']==digest(s) and not loaded['reconciled_now']
    assert loaded['snapshot']['coverage_limitations']==LIMITS
    assert not create_genesis(p,s,now_ms=1001)['created']


@pytest.mark.parametrize('kind',['order','asset','changed','stale','missing_ctf'])
def test_refuses_unexplained_or_missing_evidence(tmp_path,kind):
    s=evidence()
    if kind=='order':s['views']['orders']['rows']=[{'id':'unexplained'}]
    if kind=='asset':s['conditional_assets']['balances']['123']='1'
    if kind=='changed':s['views']['positions']['repeat_sha256']='bad'
    if kind=='missing_ctf':s['conditional_assets']={}
    r=create_genesis(tmp_path/'ledger.db',s,now_ms=200000 if kind=='stale' else 1001)
    assert not r['created'] and not (tmp_path/'ledger.db').exists()
    if kind in ('order','asset','changed'):assert r['phase']=='RECOVERY_REQUIRED'


def test_interruption_before_publish_leaves_no_partial(tmp_path):
    def fail():raise OSError('simulated')
    with pytest.raises(OSError):create_genesis(tmp_path/'ledger.db',evidence(),now_ms=1001,before_publish=fail)
    assert list(tmp_path.iterdir())==[]


def test_tamper_detected(tmp_path):
    p=tmp_path/'ledger.db';create_genesis(p,evidence(),now_ms=1001)
    with sqlite3.connect(p) as db:db.execute("UPDATE genesis SET hash='bad'")
    with pytest.raises(ValueError):read_genesis(p)


def test_activity_chained_and_divergence_persisted(tmp_path):
    p=tmp_path/'ledger.db';create_genesis(p,evidence(),now_ms=1001)
    append_activity(p,'INTENT',{'intent':'fake'},now_ms=1002)
    assert read_genesis(p)['event_count']==1
    assert not reconcile_empty_baseline(p,{'scope_complete':True,'fresh':True,'wallet':expected_wallet(),'open_orders':[],'balances':{'123':'1'}})
    assert read_genesis(p)['phase']=='RECOVERY_REQUIRED'


def test_full_readiness_pusd_and_genesis_requires_fresh_reconciliation():
    import asyncio
    from app.live.readiness import ProductionReadinessCheck
    class S:
        def read(self):return {'available':True,'observed_ms':1000,'authenticated':True,'collateral_symbol':'pUSD','balance_collateral':'109.16','allowance_collateral':'1000','complete':False}
    r=asyncio.run(ProductionReadinessCheck(account=S(),local_reader=lambda:{'phase':'GENESIS_RECONCILED','integrity_verified':True,'reconciled_now':False},clock=lambda:1000,collateral_unit='pUSD').run())
    assert len(r['checks'])==12 and r['checks']['balance_pusd']
    assert not r['checks']['local_recovery_state'] and not r['ready_for_arm']


def test_code_onset_public_reads_and_archive_failure():
    from app.live.genesis_discovery import code_onset
    class R:
        wallet=expected_wallet()
        def call(self,m,p):
            assert m=='eth_getCode' and p[0]==self.wallet
            return '0x6000' if int(p[1],16)>=80 else '0x'
    assert code_onset(R(),100)==80
    class Broken(R):
        def call(self,m,p):raise RuntimeError('archive unavailable')
    with pytest.raises(RuntimeError):code_onset(Broken(),100)


def test_creation_race_never_overwrites(tmp_path):
    p=tmp_path/'ledger.db'
    def race():p.write_bytes(b'existing')
    with pytest.raises(FileExistsError):create_genesis(p,evidence(),now_ms=1001,before_publish=race)
    assert p.read_bytes()==b'existing'


def test_recovery_blocks_new_intent(tmp_path):
    p=tmp_path/'ledger.db';create_genesis(p,evidence(),now_ms=1001)
    append_activity(p,'RECOVERY_REQUIRED',{'reason':'fixture'},now_ms=1002)
    with pytest.raises(ValueError):append_activity(p,'INTENT',{},now_ms=1003)


def test_offline_readiness_never_loads_l2(monkeypatch):
    import asyncio
    import analysis.qualify_genesis as q
    monkeypatch.setattr(q,'qualification',lambda:({'collateral':{'observed_ms':1,'balance_human':'109.160000'},'inventory':{'remote_views':{'positions':{'observed_ms':1}}}},'a'*64))
    def forbidden(*a):raise AssertionError('credential or network forbidden')
    monkeypatch.setattr(q,'load_existing',forbidden)
    monkeypatch.setattr(q,'PublicRPC',forbidden)
    r=asyncio.run(q.run(False))
    assert len(r['readiness']['checks'])==12 and not r['genesis']['created']
    assert not r['network_executed']


def test_nonzero_discovery_requires_recovery_before_credential_load(monkeypatch):
    import asyncio,time
    import analysis.qualify_genesis as q
    monkeypatch.setattr(q,'qualification',lambda:({'collateral':{'observed_ms':1,'balance_human':'109.160000'},'inventory':{'remote_views':{'positions':{'observed_ms':1}}}},'a'*64))
    class RPC:
        calls=[]
        def __init__(self,*a):pass
    class T:
        def __init__(self,*a,**k):pass
        async def get_json(self,path):return int(time.time()) if path=='/time' else {'blocked':False}
    monkeypatch.setattr(q,'PublicRPC',RPC);monkeypatch.setattr(q,'GetOnlyTransport',T)
    monkeypatch.setattr(q,'conditional_snapshot',lambda *a:{'balances':{'123':'1'}})
    monkeypatch.setattr(q,'read_local_ledger',lambda *a:({'configured':False},set()))
    def forbidden(*a):raise AssertionError('must not load')
    monkeypatch.setattr(q,'load_existing',forbidden)
    r=asyncio.run(q.run(True))
    assert r['genesis']['phase']=='RECOVERY_REQUIRED' and not r['genesis']['created']
