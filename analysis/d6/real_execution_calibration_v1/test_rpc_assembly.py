import asyncio,copy,json,pytest
from .test_bounded_reconciliation import case,NOW,TX,H1,FixtureAuthority
from .bounded_reconciliation import REQUIRED
from .bounded_acquisition import acquire
from .rpc_assembly import assemble,HTTPSReadOnly,RuntimeArtifactVerifier
URL='https://fixture.invalid/explicit-rpc'
@pytest.mark.parametrize('advance,expected',[(0,0),(1,1)])
def test_no_callbacks_after_deadline(case,advance,expected):
    clock=[NOW];calls=[];b=case[1]
    def provider(k):
        def read(c):calls.append(k);assert c['remaining_budget_ms']>0;clock[0]+=2;return copy.deepcopy(b[k])
        return read
    r=asyncio.run(acquire(case[0],providers={k:provider(k) for k in REQUIRED},authorized_kinds=REQUIRED,context={'market':b['market'],'tokens':b['tokens'],'deadline_ms':NOW+advance},authority=FixtureAuthority(),expected_operator='X',clock=lambda:clock[0]))
    assert len(calls)==expected and 'DEADLINE_MS_CROSSED' in r['verdict']['blockers']
def test_cooperative_provider_timeout_has_no_detached_task(case):
    async def run():
        stopped=[]
        async def slow(c):
            try:await asyncio.sleep(10)
            finally:stopped.append(True)
        with pytest.raises(asyncio.TimeoutError):await acquire(case[0],providers={'baseline':slow},authorized_kinds=['baseline'],context={'market':case[1]['market'],'tokens':case[1]['tokens'],'deadline_ms':NOW+1},authority=FixtureAuthority(),expected_operator='X',clock=lambda:NOW)
        assert stopped and len(asyncio.all_tasks())==1
    asyncio.run(run())
class Response:
    status=200
    def __init__(self,data):self.data=data
    def getheader(self,k,default=None):return {'Content-Type':'application/json'}.get(k,default)
    def read1(self,n):
        out=self.data[:n];self.data=self.data[n:];return out
def factory_for(receipt,calls,status=200,wrong_block=False):
    class Connection:
        def __init__(self,host,port,timeout):assert host=='fixture.invalid' and timeout<=2
        def request(self,method,path,body,headers):
            assert method=='POST' and path=='/explicit-rpc' and 'Authorization' not in headers
            self.req=json.loads(body);calls.append(self.req)
        def getresponse(self):
            r=self.req;value=receipt if r['method']=='eth_getTransactionReceipt' else dict(number='0x65',hash=('0x'+'0'*64) if wrong_block else H1)
            out=Response(json.dumps(dict(jsonrpc='2.0',id=r['id'],result=value)).encode());out.status=status;return out
        def close(self):pass
    return Connection
@pytest.mark.parametrize('status,wrong,reason',[(200,False,'ARTIFACT_MISSING'),(302,False,'REDIRECT'),(200,True,'CANONICAL')])
def test_entire_assembly_http_to_rpc_receipt_and_artifact_gate(case,status,wrong,reason):
    b=case[1];calls=[];receipt=b['receipts']['payload']['receipts'][0]['receipt']
    out=asyncio.run(assemble(case[0],endpoint=URL,approved_endpoint=URL,transactions=[TX],blocks={101:H1},context={'market':b['market'],'tokens':b['tokens']},source_records={k:b[k] for k in REQUIRED},source_authority=FixtureAuthority(),expected_operator='X',clock=lambda:NOW,deadline_ms=NOW+5000,max_calls=4,connection_factory=factory_for(receipt,calls,status,wrong)))
    assert reason in str(out['result']['verdict']['blockers']) and calls and not out['submit_allowed']
    if status==200 and not wrong:assert out['observations']['receipts'][0]['receipt_digest']
def test_http_budget_and_path_identity(case):
    calls=[];h=HTTPSReadOnly(endpoint=URL,approved_endpoint=URL,max_calls=1,deadline_ms=NOW+1000,clock=lambda:NOW,connection_factory=factory_for({},calls))
    h.validator=lambda m,p:None
    req=dict(jsonrpc='2.0',id=1,method='eth_getBlockByNumber',params=['0x65',False])
    asyncio.run(h(URL,req))
    with pytest.raises(ValueError,match='BUDGET'):asyncio.run(h(URL,req))
    with pytest.raises(ValueError,match='CONTEXT'):asyncio.run(h(URL+'/other',req))
    assert len(calls)==1
def test_self_hashed_manifest_not_trusted():
    assert RuntimeArtifactVerifier(trusted_manifests={})({'origin':'self','runtime_code':'0x6000'}) is False

def test_complete_mock_http_assembly_reaches_native_validation(case):
    import hashlib
    from .core import digest
    from .native_v2 import COMMIT
    from .test_bounded_reconciliation import EXCHANGE
    b=case[1];calls=[];receipt=b['receipts']['payload']['receipts'][0]['receipt']
    artifact=dict(origin='fixture://reviewed-build',source_commit=COMMIT,chain_id=137,exchange=EXCHANGE,kind='EXACT_NONPROXY_RUNTIME',unresolved_immutables=[],runtime_code='0x6000',runtime_sha256=hashlib.sha256(bytes.fromhex('6000')).hexdigest(),source_contents={'fixture.sol':'synthetic'},build_provenance=dict(compiler_version='0.8.30',compiler_settings={'fixture':True},source_sha256={'fixture.sol':hashlib.sha256(b'synthetic').hexdigest()},dependencies={},libraries={},constructor_immutables={}),fixture_only=True)
    Base=factory_for(receipt,calls)
    class Connection(Base):
        def getresponse(self):
            method=self.req['method']
            if method in ('eth_chainId','eth_getCode'):
                return Response(json.dumps(dict(jsonrpc='2.0',id=self.req['id'],result='0x89' if method=='eth_chainId' else '0x6000')).encode())
            return super().getresponse()
    class NoInventedAuthority:
        def verify(self,r):return r.get('fixture_only') is True # rejects generated unauthenticated envelopes
    out=asyncio.run(assemble(case[0],endpoint=URL,approved_endpoint=URL,transactions=[TX],blocks={101:H1},context={'market':b['market'],'tokens':b['tokens']},source_records={k:b[k] for k in REQUIRED},source_authority=NoInventedAuthority(),expected_operator='X',clock=lambda:NOW,deadline_ms=NOW+5000,max_calls=8,connection_factory=Connection,artifacts={TX:artifact},trusted_manifests={artifact['origin']:digest(artifact)}))
    assert len(calls)==6 and out['observations']['receipts'] and out['result']['verdict']['blockers']
    assert not out['result']['verdict']['status'].startswith('BOUNDED_MATCH') # generated provenance is not self-trusted

@pytest.mark.parametrize('body',[b'{',b'{"jsonrpc":"2.0","id":1,"id":1,"result":[]}',b'x'*1100])
def test_http_bad_or_oversize_json_closes(body):
    closed=[]
    class C:
        def __init__(self,*a,**k):pass
        def request(self,*a,**k):pass
        def getresponse(self):return Response(body)
        def close(self):closed.append(True)
    h=HTTPSReadOnly(endpoint=URL,approved_endpoint=URL,max_calls=1,deadline_ms=NOW+1000,clock=lambda:NOW,connection_factory=C,max_bytes=1024);h.validator=lambda m,p:None
    with pytest.raises((ValueError,json.JSONDecodeError)):asyncio.run(h(URL,dict(jsonrpc='2.0',id=1,method='eth_chainId',params=[])))
    assert closed==[True]
def test_socket_thread_cancellation_owned_until_close():
    import threading
    entered=threading.Event();release=threading.Event();closed=[]
    class C:
        def __init__(self,*a,**k):pass
        def request(self,*a,**k):entered.set();release.wait(1)
        def getresponse(self):return Response(b'{"jsonrpc":"2.0","id":1,"result":"0x89"}')
        def close(self):closed.append(True)
    async def run():
        h=HTTPSReadOnly(endpoint=URL,approved_endpoint=URL,max_calls=1,deadline_ms=NOW+1000,clock=lambda:NOW,connection_factory=C);h.validator=lambda m,p:None
        t=asyncio.create_task(h(URL,dict(jsonrpc='2.0',id=1,method='eth_chainId',params=[])))
        while not entered.is_set():await asyncio.sleep(.001)
        t.cancel();await asyncio.sleep(.01);assert not t.done();release.set()
        with pytest.raises(asyncio.CancelledError):await t
        assert closed and len(asyncio.all_tasks())==1
    asyncio.run(run())
@pytest.mark.parametrize('preexpired',[False,True])
def test_market_expiry_inside_receipt_recheck_stops_deployment(case,monkeypatch,preexpired):
    # 5 ms is a synthetic ordering boundary, NOT a real HTTP/thread-start SLA.
    # All elapsed-time consumers (including asyncio timers) share controlled time.
    import types
    from . import rpc_assembly as assembly_module
    b=case[1];clock=[NOW];calls=[];mono=lambda:clock[0]/1000
    real_rpc=assembly_module.BoundedRPC;real_acquire=assembly_module.acquire
    monkeypatch.setattr(assembly_module,'time',types.SimpleNamespace(monotonic=mono))
    monkeypatch.setattr(assembly_module,'BoundedRPC',lambda **kw:real_rpc(**kw,monotonic=mono))
    async def controlled_acquire(*args,**kw):return await real_acquire(*args,**kw,monotonic=mono)
    monkeypatch.setattr(assembly_module,'acquire',controlled_acquire)
    Base=factory_for(b['receipts']['payload']['receipts'][0]['receipt'],calls)
    class C(Base):
        def getresponse(self):
            r=super().getresponse()
            if self.req['method']=='eth_getBlockByNumber':clock[0]+=10
            return r
    async def run():
        loop=asyncio.get_running_loop();monkeypatch.setattr(loop,'time',mono)
        return await assemble(case[0],endpoint=URL,approved_endpoint=URL,transactions=[TX],blocks={101:H1},context={'market':b['market'],'tokens':b['tokens'],'market_expiry_ms':NOW if preexpired else NOW+5},source_records=b_subset(b),source_authority=FixtureAuthority(),expected_operator='X',clock=lambda:clock[0],deadline_ms=NOW+5000,max_calls=8,connection_factory=C)
    out=asyncio.run(run())
    expected=[] if preexpired else ['eth_getTransactionReceipt','eth_getBlockByNumber']
    assert [c['method'] for c in calls]==expected and out['result']['verdict']['blockers']
    assert not out['result']['verdict']['status'].startswith('BOUNDED_MATCH')

def b_subset(b):return {k:b[k] for k in REQUIRED}
@pytest.mark.parametrize('mutation',['ok','foreign','truncated','reorg'])
def test_nonempty_http_log_queries(case,mutation):
    from .bounded_rpc import BoundedRPC
    from .native_v2 import COLLATERAL,TRANSFER
    b=case[1];calls=[];log=copy.deepcopy(b['receipts']['payload']['receipts'][0]['receipt']['logs'][0]);Base=factory_for({},calls)
    if mutation=='foreign':log['address']='0x'+'1'*40
    if mutation=='reorg':log['blockHash']='0x'+'0'*64
    class C(Base):
        def getresponse(self):
            if self.req['method']=='eth_getLogs':return Response(json.dumps(dict(jsonrpc='2.0',id=self.req['id'],result=[log]*(2 if mutation=='truncated' else 1))).encode())
            return super().getresponse()
    h=HTTPSReadOnly(endpoint=URL,approved_endpoint=URL,max_calls=4,deadline_ms=NOW+1000,clock=lambda:NOW,connection_factory=C)
    rpc=BoundedRPC(transport=h,endpoint=URL,allowed_endpoints=[URL],transactions=[TX],blocks={101:H1},clock=lambda:NOW,max_logs=2,max_span=1);h.validator=rpc.validate
    if mutation=='ok':assert asyncio.run(rpc.logs(address=COLLATERAL,topic=TRANSFER,lo=101,hi=101))['logs']==[log]
    else:
        with pytest.raises(ValueError):asyncio.run(rpc.logs(address=COLLATERAL,topic=TRANSFER,lo=101,hi=101))

def test_assembly_nonempty_log_queries_are_executed(case):
    from .native_v2 import COLLATERAL,TRANSFER
    b=case[1];calls=[];receipt=b['receipts']['payload']['receipts'][0]['receipt'];Base=factory_for(receipt,calls)
    class C(Base):
        def getresponse(self):
            if self.req['method']=='eth_getLogs':return Response(json.dumps(dict(jsonrpc='2.0',id=self.req['id'],result=[receipt['logs'][0]])).encode())
            return super().getresponse()
    out=asyncio.run(assemble(case[0],endpoint=URL,approved_endpoint=URL,transactions=[TX],blocks={101:H1},context={'market':b['market'],'tokens':b['tokens']},source_records=b_subset(b),source_authority=FixtureAuthority(),expected_operator='X',clock=lambda:NOW,deadline_ms=NOW+5000,max_calls=8,log_queries=[dict(address=COLLATERAL,topic=TRANSFER,lo=101,hi=101)],connection_factory=C))
    assert out['observations']['logs'][0]['logs']==[receipt['logs'][0]] and out['result']['verdict']['blockers']
