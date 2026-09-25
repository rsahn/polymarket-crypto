import asyncio
import pytest


def test_warmup_discards_account_values_and_reads_chain_only():
    from app.live.readonly_warmup import warm_readonly
    calls=[]
    class RPC:
        def call(self,method,params):
            calls.append((method,params))
            return '0x89'
    async def account():return {'SECRET_PAYLOAD':('old',1)}
    result=asyncio.run(warm_readonly(RPC(),account))
    assert calls==[('eth_chainId',[])]*8
    assert result['account_values_discarded'] is True
    assert 'SECRET_PAYLOAD' not in str(result)
    assert result['status']=='READS_COMPLETED_REUSE_NOT_GUARANTEED'


@pytest.mark.parametrize('failure',['account','chain'])
def test_warmup_failure_drains_all_reads_and_never_returns_evidence(failure):
    from app.live.readonly_warmup import warm_readonly
    calls=[]
    class RPC:
        def call(self,*args):
            calls.append(1)
            return '0x1' if failure=='chain' else '0x89'
    async def account():
        if failure=='account':raise RuntimeError('SECRET')
        return {}
    with pytest.raises(ValueError,match='READ_ONLY_WARMUP_FAILED') as e:
        asyncio.run(warm_readonly(RPC(),account))
    assert len(calls)==8 and 'SECRET' not in str(e.value)


def test_final_reads_are_new_and_preserve_their_own_time(monkeypatch):
    from app.live.readonly_warmup import warm_readonly
    import analysis.qualify_post_genesis as q
    import analysis.qualify_post_b_proofs as p
    now=[1000];reads=[];rpc_calls=[]
    def h(n):return {'number':hex(n),'hash':'0x'+('a' if n==10 else 'b')*64,'timestamp':'0x1'}
    class RPC:
        def call(self,m,args):
            rpc_calls.append((m,args))
            return '0x89' if m=='eth_chainId' else h(12 if args[0]=='latest' else int(args[0],16))
    class Geo:
        async def read(self):return {}
    async def views(client=None):
        reads.append(now[0])
        return {k:([],now[0]) for k in ('balance','orders','trades','positions')}
    anchored=dict(from_block=9,to_block=10,block_hash='0x'+'a'*64,balances={},
                  cursor_previous=8,anchor_catchup_ranges=[[9,10]],observed_ms=1000)
    monkeypatch.setattr(q,'fresh_views',views)
    monkeypatch.setattr(p,'now_ms',lambda:now[0])
    monkeypatch.setattr(p,'fixed_scan',lambda *a:({**anchored,'to_block':12,'block_hash':'0x'+'b'*64,
        'events_count':0,'observed_ms':2000},[[11,12]]))
    async def go():
        rpc=RPC()
        await warm_readonly(rpc,views)
        now[0]=2100
        return await p.acquire_post_b(None,Geo(),rpc,anchored,
            {'status':'PASS_PROVIDER_FINALIZED_READ','anchor':{'number':10,'hash':'0x'+'a'*64}})
    observed,geo,inventory=asyncio.run(go())
    assert reads==[1000,2100]
    assert all(v[1]==2100 for v in observed.values())
    assert inventory['observed_ms']==2000
    assert not inventory['post_b_proof']['current_inventory_proven']


def test_warmup_account_failure_drains_other_pages(monkeypatch):
    import analysis.qualify_post_genesis as q
    completed=[]
    async def page():
        await asyncio.sleep(.01)
        completed.append(True)
        return []
    class Client:
        wallet='fixture'
        async def get_balance_allowance(self,**kw):raise ValueError('account_failure')
        def list_open_orders(self):return page()
        def list_account_trades(self):return page()
        def list_positions(self,**kw):return page()
    async def drain(value):return await value
    monkeypatch.setattr(q,'drain',drain)
    with pytest.raises(ValueError,match='account_failure'):
        asyncio.run(q.fresh_views(Client(),drain_errors=True))
    assert len(completed)==3


def test_cancelled_warmup_drains_workers_before_return():
    import threading
    from app.live.readonly_warmup import warm_readonly
    released=threading.Event();started=threading.Event();finished=[]
    class RPC:
        def call(self,*a):
            started.set()
            assert released.wait(2)
            finished.append(True)
            return '0x89'
    async def account():return {}
    async def go():
        task=asyncio.create_task(warm_readonly(RPC(),account))
        while not started.is_set():await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        released.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert len(finished)==8
    asyncio.run(go())
