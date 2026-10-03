import asyncio, copy
import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from .core import digest,encoded
from .production_authority import ProductionAuthority
from .production_evidence_source import ProductionEvidenceSource, COMPONENTS

def material():
    key=Account.create();now=[1000]
    ctx=dict(account='a',collateral='pUSD',session='s')
    authority=ProductionAuthority(keys={'external':dict(address=key.address,kinds=['baseline','snapshot','execution'])},provider='approved-provider',context=ctx,clock=lambda:now[0],approval_digest='a'*64)
    def seal(r):
        r=copy.deepcopy(r);r.pop('provenance_signature',None)
        r['provenance_signature']=key.sign_message(encode_defunct(text='D6_PROVENANCE_V1:'+encoded(r))).signature.hex();return r
    inv=dict(cash=[dict(id='pUSD',balance='500')],positions=[],orders=[],trades=[],fees=[])
    f=dict(sequence=0,digest=digest(inv))
    r=dict(**ctx,kind='baseline',provider='approved-provider',key_id='external',trust_policy_digest='a'*64,scope='wallet',observed_ms=1000,valid_until_ms=6000,atomic_frontier=f,inventory=inv,cash='500',positions={},trade_ids=[],experiment_trade_ids=[],open_orders=[],terminal_order_ids=[],inventory_proven=True,cash_proven=True,orders_complete=True,trades_complete=True,positions_complete=True)
    r['coverage']={name:dict(scope='wallet',filters={},frontier=f,complete=True,next_cursor=None,origin='wallet_creation',count=len(rows),digest=digest(rows)) for name,rows in inv.items()}
    baseline=seal(r)
    r.update(kind='snapshot',baseline_digest=digest(baseline),ancestor_frontiers=[f])
    class Provider:
        record=seal(r)
        async def snapshot(self):return copy.deepcopy(self.record)
    provider=Provider()
    source=ProductionEvidenceSource(provider,authority=authority,**ctx,baseline=baseline,clock=lambda:now[0])
    return source,provider,authority,seal,now

def test_signed_snapshot_and_no_mutable_reference():
    source,p,a,seal,now=material();r=asyncio.run(source.snapshot());r['cash']='0'
    assert asyncio.run(source.snapshot())['cash']=='500'
    assert not a.verify_client(object(),p.record)
    assert not a.verify_bindings((a,)*5,{'x':p.record})

@pytest.mark.parametrize('field',['cash','positions','account','collateral','session','scope','observed_ms','valid_until_ms','inventory','coverage','baseline_digest','provider','key_id','trust_policy_digest'])
def test_unsigned_mutation_rejected(field):
    source,p,a,seal,now=material();p.record[field]='tampered'
    with pytest.raises(ValueError,match='AUTHORITY_REJECTED'):asyncio.run(source.snapshot())

@pytest.mark.parametrize('component',sorted(COMPONENTS))
@pytest.mark.parametrize('change',[dict(complete=False),dict(next_cursor='more'),dict(origin='market_start'),dict(filters={'market':'m'}),dict(count=999),dict(digest='0'*64),dict(scope='market'),dict(frontier={'sequence':9,'digest':'0'*64})])
def test_signed_incomplete_coverage_rejected(component,change):
    source,p,a,seal,now=material();p.record['coverage'][component].update(change);p.record=seal(p.record)
    with pytest.raises(ValueError):asyncio.run(source.snapshot())

@pytest.mark.parametrize('field,value',[('cash','0'),('positions',{'foreign':'1'}),('trade_ids',['unknown']),('open_orders',['unknown']),('terminal_order_ids',['unknown']),('baseline_digest','0'*64),('inventory_proven',False)])
def test_signed_projection_or_binding_rejected(field,value):
    source,p,a,seal,now=material();p.record[field]=value;p.record=seal(p.record)
    with pytest.raises(ValueError):asyncio.run(source.snapshot())

def test_stale_external_record_cannot_be_restamped():
    source,p,a,seal,now=material();now[0]=6001
    with pytest.raises(ValueError):asyncio.run(source.snapshot())

def test_self_attesting_authority_rejected_at_source_boundary():
    from .evidence import SelfAttestingAuthority
    with pytest.raises(ValueError,match='PRODUCTION_AUTHORITY_REQUIRED'):
        ProductionEvidenceSource(None,authority=SelfAttestingAuthority(),account='a',collateral='c',session='s',baseline={},clock=lambda:0)


def execution_material():
    source,p,a,seal,now=material()
    fill=dict(trade_id='trade',order_id='order',token='1',market='m',side='BUY',price='.5',shares='10',cash_fee='.1',share_fee='0',fee_evidence=dict(cash_effect_proven=True,share_effect_proven=True),exchange_ts_ms=999,receive_ts_ms=1000)
    r=copy.deepcopy(p.record)
    r.update(cash='494.9',positions={'1':'10'},trade_ids=['trade'],experiment_trade_ids=['trade'],terminal_order_ids=['order'])
    r['inventory']=dict(cash=[dict(id='pUSD',balance='494.9')],positions=[dict(id='1',shares='10')],orders=[dict(id='order',terminal=True)],trades=[dict(id='trade',fill=fill)],fees=[dict(id='trade',cash_fee='.1',share_fee='0')])
    r['atomic_frontier']=dict(sequence=1,digest=digest(r['inventory']))
    for name,rows in r['inventory'].items():r['coverage'][name].update(frontier=r['atomic_frontier'],count=len(rows),digest=digest(rows))
    p.record=seal(r)
    execution={k:copy.deepcopy(v) for k,v in r.items() if k not in ('provenance_signature','coverage','inventory')}
    execution.update(kind='execution',schema='independent-settled/v1',order_id='order',market='m',token='1',side='BUY',fills=[fill],terminal_status='FILLED',cumulative_shares='10',account_snapshot=p.record)
    p.executed=seal(execution)
    async def execute(oid):return p.executed
    p.execution=execute
    return source,p,a,seal,now

def test_signed_execution_through_real_account_adapter():
    from .adapters import AccountAdapter
    source,p,a,seal,now=execution_material()
    adapter=AccountAdapter(None,None,account='a',collateral='pUSD',session='s',authority=a,baseline=source.baseline,evidence_source=source,intents=lambda:{'intent':dict(order_id='order',market='m',token='1',side='BUY')},clock=lambda:now[0])
    result=asyncio.run(adapter.execution('order'))
    assert result['cumulative_shares']=='10' and result['account_snapshot']['cash']=='494.9'
    assert result['fills'][0]['cash_fee']=='0.1'

@pytest.mark.parametrize('field,value',[('fills',[]),('order_id','other'),('fills',[dict(trade_id='missing',order_id='order')])])
def test_signed_execution_omission_and_unknown_fill_rejected(field,value):
    source,p,a,seal,now=execution_material();p.executed[field]=value;p.executed=seal(p.executed)
    with pytest.raises(ValueError):asyncio.run(source.execution('order'))

def test_signed_frontier_replay_rejected():
    source,p,a,seal,now=execution_material();asyncio.run(source.snapshot())
    p.record=seal(dict(source.baseline,kind='snapshot',baseline_digest=digest(source.baseline),ancestor_frontiers=[]))
    with pytest.raises(ValueError,match='FORK_OR_REPLAY'):asyncio.run(source.snapshot())

def test_external_authority_human_arm_contract(monkeypatch):
    import types
    from .test_repairs import evidence
    from .preflight import evaluate,REQUIRED
    from .engine import HumanArm
    _,v,e=evidence();key=Account.create()
    a=ProductionAuthority(keys={'external':dict(address=key.address,kinds=REQUIRED)},provider='reviewed',context=dict(account='account',session='experiment',collateral='pUSD'),clock=lambda:1000,approval_digest='a'*64)
    v.authority=a
    for check in REQUIRED:
        r=e[check];r.update(provider='reviewed',key_id='external',trust_policy_digest='a'*64)
        r['provenance_signature']=key.sign_message(encode_defunct(text='D6_PROVENANCE_V1:'+encoded(r))).signature.hex()
    report=evaluate(e,1000,2**40,v)
    assert report['status']=='CALIBRATION_READY'
    monkeypatch.setattr('time.time_ns',lambda:1000000000)
    monkeypatch.setattr('sys.stdin',types.SimpleNamespace(isatty=lambda:True))
    monkeypatch.setattr('builtins.input',lambda prompt:'CALIBRATE experiment')
    arm=HumanArm.confirm('experiment',report,verifier=v,evidence=e)
    arm.check('experiment')
    e['tests_green']['payload']['passed']=999
    with pytest.raises(ValueError):HumanArm.confirm('experiment',report,verifier=v,evidence=e)


def test_only_authenticated_staleness_is_recoverable():
    from .engine import transient_availability
    source,p,a,seal,now=material();now[0]=6001
    with pytest.raises(ValueError) as stale:asyncio.run(source.snapshot())
    assert str(stale.value)=='ACCOUNT_CLOCK' and transient_availability(stale.value)
    assert not a.verify(p.record)
    p.record['cash']='tampered'
    with pytest.raises(ValueError) as tampered:asyncio.run(source.snapshot())
    assert str(tampered.value)=='AUTHORITY_REJECTED' and not transient_availability(tampered.value)


def test_concurrent_observations_are_serialized():
    async def case():
        source,p,a,seal,now=material();gate=asyncio.Event();calls=[]
        async def observe():
            calls.append(1)
            if len(calls)==1:await gate.wait()
            return copy.deepcopy(p.record)
        p.snapshot=observe
        first=asyncio.create_task(source.snapshot());await asyncio.sleep(0);await asyncio.sleep(0)
        second=asyncio.create_task(source.snapshot());await asyncio.sleep(0);await asyncio.sleep(0)
        assert len(calls)==1
        gate.set();await asyncio.gather(first,second)
        assert len(calls)==2
    asyncio.run(case())
