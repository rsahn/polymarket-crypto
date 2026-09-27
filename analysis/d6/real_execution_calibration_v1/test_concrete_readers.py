import asyncio,copy,pytest
from .test_bounded_reconciliation import case,NOW,D6,H0,H1,ORDER,MARKET,FixtureAuthority,reseal,evaluate
from .bounded_rpc import BoundedRPC
from .concrete_readers import ConcreteReaders,PinnedEvidenceAuthority
from .core import digest

def test_concrete_snapshots_receipt_native_to_bounded_verdict(case):
    async def run():
        b=copy.deepcopy(case[1]);clock=[80000]
        async def transport(endpoint,req):
            n=int(req['params'][-1],16) if req['method']=='eth_call' else int(req['params'][0],16)
            if req['method']=='eth_call':
                data=req['params'][0]['data'];token=int(data[-64:],16)
                value=(100000000 if n==100 else 98990000) if data.startswith('0x70a08231') else (2000000 if n==101 and token==123 else 0)
                result='0x'+format(value,'064x')
            else:result=dict(number=hex(n),hash={100:H0,101:H1}[n])
            return dict(jsonrpc='2.0',id=req['id'],result=result)
        rpc=BoundedRPC(transport=transport,endpoint='https://fixture.invalid',allowed_endpoints=['https://fixture.invalid'],transactions=[],blocks={100:H0,101:H1},clock=lambda:clock[0])
        readers=ConcreteReaders(rpc,account=D6,tokens=['123','456'],market=MARKET,baseline_block=100,closing_block=101)
        b['baseline']['payload']=await readers.snapshot(100)
        clock[0]=100000;b['closing']['payload']=await readers.snapshot(101)
        clock[0]=100005;b['finality']['payload']=await readers.finality(b['finality']['payload'])
        b['terminal_orders']['payload']=readers.terminal(b['terminal_orders']['payload']['orders'],{ORDER:{}})
        b['coverage']['payload']=readers.coverage(b['coverage']['payload'],[],b['receipts']['payload']['receipts'])
        # Explicit fixture authority; never a production trust claim.
        r=evaluate(case[0],reseal(b),authority=FixtureAuthority(),now_ms=NOW,expected_operator='FICTIONAL_TEST_OPERATOR')
        assert r['status'].startswith('BOUNDED_MATCH'),r
        with pytest.raises(ValueError):await rpc.call('eth_call',[{'to':D6,'data':'0x70a08231'},'0x64'])
        with pytest.raises(ValueError):readers.terminal([{'order_id':'foreign','status':'FILLED'}],{ORDER:{}})
        bad=copy.deepcopy(b['coverage']['payload']);bad['pagination_complete']=False
        with pytest.raises(ValueError):readers.coverage(bad,[],[])
    asyncio.run(run())
def test_authority_requires_independent_provider_and_exact_payload_pin():
    from .bounded_reconciliation import SCOPE
    r=dict(kind='baseline',scope=SCOPE,provider_identity='fixture-provider',payload={'raw':'fixture'},fixture_only=True);r['source_digest']=digest(r['payload'])
    assert not PinnedEvidenceAuthority('fixture-provider',{},fixture_only=True).verify(r)
    a=PinnedEvidenceAuthority('fixture-provider',{('baseline','result'):r['source_digest']},fixture_only=True)
    assert a.verify(r)
    r['provider_identity']='other';assert not a.verify(r)
