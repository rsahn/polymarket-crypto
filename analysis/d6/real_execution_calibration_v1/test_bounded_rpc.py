import asyncio,copy,pytest
from .test_bounded_reconciliation import case,FixtureAuthority,NOW,D6,TX,EXCHANGE,H0,H1
from .bounded_reconciliation import REQUIRED
from .bounded_acquisition import acquire
from .bounded_rpc import BoundedRPC
from .native_v2 import COLLATERAL,TRANSFER,COMMIT
URL='https://fixture.invalid/rpc'
def test_last_provider_latency_is_not_rejuvenated(case):
    async def run():
        b=case[1];clock=[NOW]
        def provider(k):
            def read(ctx):
                if k==REQUIRED[-1]:clock[0]+=6001
                return copy.deepcopy(b[k])
            return read
        r=await acquire(case[0],providers={k:provider(k) for k in REQUIRED},authorized_kinds=REQUIRED,context={'market':b['market'],'tokens':b['tokens']},authority=FixtureAuthority(),clock=lambda:clock[0],expected_operator='FICTIONAL_TEST_OPERATOR')
        assert 'CLOSING_OLDEST_READ_STALE' in r['verdict']['blockers'] and not r['verdict']['status'].startswith('BOUNDED_MATCH')
    asyncio.run(run())
@pytest.mark.parametrize('failure',[RuntimeError,asyncio.CancelledError])
def test_failed_or_cancelled_provider_never_returns_state(case,failure):
    async def run():
        def fail(ctx):raise failure()
        with pytest.raises(failure):await acquire(case[0],providers={'baseline':fail},authorized_kinds=['baseline'],context={'market':case[1]['market'],'tokens':case[1]['tokens']},authority=FixtureAuthority(),clock=lambda:NOW,expected_operator='X')
    asyncio.run(run())
def rpc(result=None,clock=None):
    calls=[]
    async def transport(endpoint,req):
        calls.append(req)
        value=result(req) if callable(result) else result
        return dict(jsonrpc='2.0',id=req['id'],result=value)
    return BoundedRPC(transport=transport,endpoint=URL,allowed_endpoints=[URL],transactions=[TX],blocks={100:H0,101:H1},clock=clock or (lambda:NOW)),calls
@pytest.mark.parametrize('method,params',[
    ('eth_sendRawTransaction',['0x']),('eth_getCode',[EXCHANGE,'latest']),('eth_getTransactionReceipt',['0x'+'1'*64]),
    ('eth_getLogs',[dict(address=COLLATERAL,topics=[TRANSFER],fromBlock='0x0',toBlock='0xffff')]),
    ('eth_getLogs',[dict(address=D6,topics=[TRANSFER],fromBlock='0x64',toBlock='0x65')]),
    ('eth_getLogs',[dict(address=COLLATERAL,topics=[None],fromBlock='0x64',toBlock='0x65')])])
def test_disallowed_rpc_never_invokes_transport(method,params):
    r,c=rpc()
    with pytest.raises(ValueError):asyncio.run(r.call(method,params))
    assert c==[]
@pytest.mark.parametrize('endpoint',['http://fixture.invalid','https://evil.invalid','https://user:pass@fixture.invalid','https://fixture.invalid/rpc?secret=x'])
def test_endpoint_rejected(endpoint):
    with pytest.raises(ValueError):BoundedRPC(transport=lambda:None,endpoint=endpoint,allowed_endpoints=[URL],transactions=[],blocks={100:H0})
def test_receipt_canonical_recheck_and_wrong_hash(case):
    receipt=case[1]['receipts']['payload']['receipts'][0]['receipt']
    def response(req):return copy.deepcopy(receipt) if req['method']=='eth_getTransactionReceipt' else {'number':'0x65','hash':H1}
    r,c=rpc(response);out=asyncio.run(r.receipt(TX));assert out['receipt_digest'] and not out['finality_proven'] and len(c)==2
    receipt['logs'][0]['blockHash']=H0
    with pytest.raises(ValueError):asyncio.run(r.receipt(TX))
def test_late_response_rejected():
    clock=[NOW]
    def response(req):clock[0]+=6001;return '0x89'
    r,c=rpc(response,lambda:clock[0])
    with pytest.raises(ValueError,match='LATE'):asyncio.run(r.call('eth_chainId',[]))
def test_timeout_and_rpc_error_rejected():
    async def slow(endpoint,req):await asyncio.sleep(.1)
    r,c=rpc();r.transport=slow;r.timeout=.001
    with pytest.raises(asyncio.TimeoutError):asyncio.run(r.call('eth_chainId',[]))
    async def error(endpoint,req):return {'jsonrpc':'2.0','id':req['id'],'error':{'code':-1}}
    r.transport=error
    with pytest.raises(ValueError):asyncio.run(r.call('eth_chainId',[]))
def test_logs_empty_is_not_attested_coverage():
    def response(req):
        if req['method']=='eth_getLogs':return []
        n=int(req['params'][0],16);return dict(number=hex(n),hash={100:H0,101:H1}[n])
    r,c=rpc(response);out=asyncio.run(r.logs(address=COLLATERAL,topic=TRANSFER,lo=100,hi=101))
    assert out['queried_range_complete'] and out['coverage_proven'] is False
    r.max_logs=1
    def trunc(req):return [{}]
    r.transport=(rpc(trunc)[0]).transport
    with pytest.raises(ValueError,match='TRUNCATION'):asyncio.run(r.logs(address=COLLATERAL,topic=TRANSFER,lo=100,hi=101))
def test_runtime_artifact_required_not_source_commit_or_nonempty_code():
    r,c=rpc('0x6000')
    with pytest.raises(ValueError,match='ARTIFACT_MISSING'):asyncio.run(r.deployment(exchange=EXCHANGE,block=101,artifact=None,artifact_verifier=lambda x:True))
    assert c==[]
    a=dict(source_commit=COMMIT,chain_id=137,exchange=EXCHANGE,kind='EXACT_NONPROXY_RUNTIME',unresolved_immutables=[],runtime_code='0x6000',fixture_only=True)
    def response(req):
        return {'eth_chainId':'0x89','eth_getCode':'0x6001','eth_getBlockByNumber':dict(number='0x65',hash=H1)}[req['method']]
    r,c=rpc(response)
    with pytest.raises(ValueError,match='BYTECODE_MISMATCH'):asyncio.run(r.deployment(exchange=EXCHANGE,block=101,artifact=a,artifact_verifier=lambda x:True))
    a['kind']='PROXY'
    with pytest.raises(ValueError,match='UNSUPPORTED'):asyncio.run(r.deployment(exchange=EXCHANGE,block=101,artifact=a,artifact_verifier=lambda x:True))

@pytest.mark.parametrize('key',['deadline_ms','market_expiry_ms'])
def test_completion_crossing_deadline_blocks(case,key):
    async def run():
        b=case[1];providers={k:(lambda ctx,k=k:copy.deepcopy(b[k])) for k in REQUIRED}
        r=await acquire(case[0],providers=providers,authorized_kinds=REQUIRED,context={'market':b['market'],'tokens':b['tokens'],key:NOW},authority=FixtureAuthority(),clock=lambda:NOW,expected_operator='FICTIONAL_TEST_OPERATOR')
        assert key.upper()+'_CROSSED' in r['verdict']['blockers']
    asyncio.run(run())
def test_wrong_chain_and_canonical_hash_rejected():
    r,c=rpc('0x1')
    with pytest.raises(ValueError,match='CHAIN'):asyncio.run(r.call('eth_chainId',[]))
    r,c=rpc(dict(number='0x65',hash=H0))
    with pytest.raises(ValueError,match='CANONICAL'):asyncio.run(r.canonical(101))
def test_exact_fixture_artifact_match_and_recheck_produces_only_bound_proof():
    a=dict(source_commit=COMMIT,chain_id=137,exchange=EXCHANGE,kind='EXACT_NONPROXY_RUNTIME',unresolved_immutables=[],runtime_code='0x6000',fixture_only=True)
    def response(req):return {'eth_chainId':'0x89','eth_getCode':'0x6000','eth_getBlockByNumber':dict(number='0x65',hash=H1)}[req['method']]
    r,c=rpc(response);out=asyncio.run(r.deployment(exchange=EXCHANGE,block=101,artifact=a,artifact_verifier=lambda x:x.get('fixture_only') is True))
    assert out['block_hash']==H1 and out['runtime_code_hash'] and len(c)==4
