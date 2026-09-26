import asyncio
import pytest


class Clock:
    def __init__(self):self.value=0.0
    def now(self):return self.value
    def sleep(self,seconds):self.value+=seconds


def test_preparation_spaces_all_reads_without_changing_final_rpc():
    from app.live.preparation_rpc import PreparationRPC
    clock=Clock();starts=[]
    class RPC:
        wallet='0x'+'1'*40
        log_window=10
        parallel_inventory_reads=True
        def call(self,*a):starts.append(clock.now());return 'value'
    original=RPC();rpc=PreparationRPC(original,clock=clock.now,sleep=clock.sleep)
    for _ in range(104):assert rpc.call('eth_chainId',[])=='value'
    assert all(b-a>=.2-1e-9 for a,b in zip(starts,starts[1:]))
    assert rpc.parallel_inventory_reads is False
    assert original.parallel_inventory_reads is True
    assert rpc.log_window==10 and rpc.wallet==original.wallet
    assert rpc.report()['requests_started']==104
    assert rpc.report()['retries']==0


def test_preparation_budget_stops_before_extra_remote_read():
    from app.live.preparation_rpc import PreparationRPC
    clock=Clock();calls=[]
    class RPC:
        def call(self,*a):calls.append(a)
    rpc=PreparationRPC(RPC(),clock=clock.now,sleep=clock.sleep,budget_seconds=.3)
    rpc.call('eth_chainId',[]);rpc.call('eth_chainId',[])
    with pytest.raises(ValueError,match='PREPARATION_RPC_BUDGET_EXCEEDED'):
        rpc.call('eth_chainId',[])
    assert len(calls)==2


def test_preparation_429_stops_without_retry_or_leaking_exception():
    from app.live.preparation_rpc import PreparationRPC
    clock=Clock()
    class RPC:
        calls=[]
        def call(self,*a):
            self.calls.append({'http_status':429})
            raise RuntimeError('SECRET_URL')
    original=RPC();rpc=PreparationRPC(original,clock=clock.now,sleep=clock.sleep)
    for _ in range(2):
        with pytest.raises(ValueError,match='PREPARATION_RPC_RATE_LIMITED') as exc:
            rpc.call('eth_chainId',[])
        assert 'SECRET' not in str(exc.value)
    assert len(original.calls)==1
    assert rpc.report()['failure_reason']=='PREPARATION_RPC_RATE_LIMITED'


def test_early_failure_does_not_republish_old_generation_timing(monkeypatch):
    import analysis.qualify_post_genesis as q
    import analysis.qualify_post_b_proofs as p
    for flag in ('REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED'):monkeypatch.setenv(flag,'false')
    monkeypatch.setenv('POLYGON_ARCHIVE_RPC_URL','https://example.invalid')
    prior=dict(phase='GENESIS_RECONCILED',event_count=0,last_hash='a',snapshot_sha256='b',
        snapshot=dict(wallet='wallet',collateral={'contract':q.CONTRACT}))
    old=dict(from_block=1,to_block=10,block_hash='old',balances={},events_count=0,
        observed_ms=1000,critical_path={'scan_observed_ms':1000,'scan_dispatch_ms':900,
        'scan_worker_finished_ms':1100,'scan_resume_delay_ms':176,'account_started_ms':1276},
        post_b_proof={'inventory_through_C_proven':True,'current_inventory_proven':False,
                      'reason':'GENERATION_STALE_500MS'})
    monkeypatch.setattr(q,'read_genesis',lambda *a:prior)
    monkeypatch.setattr(q,'expected_wallet',lambda:'wallet')
    monkeypatch.setattr(q,'load_inventory_cursor',lambda *a:old)
    class RPC:
        def __init__(self,*a,**kw):self.calls=[]
    class Get:
        def __init__(self,*a,**kw):pass
        async def get_json(self,*a):return 1
    monkeypatch.setattr(q,'PublicRPC',RPC)
    monkeypatch.setattr(q,'GetOnlyTransport',Get)
    def fail(*a):raise ValueError('TAIL_SCAN_FAILED')
    monkeypatch.setattr(p,'prepare_finalized_inventory',fail)
    def no_save(*a):raise AssertionError('FAILED_SCAN_MUST_NOT_PUBLISH_CURSOR')
    monkeypatch.setattr(q,'save_inventory_cursor',no_save)
    report=asyncio.run(q.run(True,health_contract=True))
    assert report['reconciliation']['reason']=='TAIL_SCAN_FAILED'
    assert report['scheduler_timing']['measured_scan_resume_delay_ms'] is None
    assert report['scheduler_timing']['account_started_ms'] is None
    assert report['final_timing_budget']['critical_path_wall_ms'] is None
    assert not report['inventory_completeness']['evidence_available']
    assert 'critical_path' not in report['inventory_incremental']
    assert report['inventory_incremental']['observed_ms']==1000
    assert report['inventory_evidence_origin']=='PREPARATION_OR_PRIOR_CURSOR'
    assert old['critical_path']['scan_resume_delay_ms']==176
    assert not report['readiness']['submit_allowed']


def test_preparation_scanner_keeps_every_ten_block_range_outside_readiness():
    from app.live.preparation_rpc import PreparationRPC
    from analysis.qualify_post_b_proofs import qualify_finalized,fixed_scan
    clock=Clock();ranges=[];calls=[]
    class RPC:
        wallet='0x'+'1'*40
        log_window=10
        parallel_inventory_reads=True
        def call(self,method,params):
            calls.append((method,params,clock.now()))
            if method=='eth_chainId':return '0x89'
            if method=='eth_getCode':return '0x1234'
            if method=='eth_getLogs':
                ranges.append((int(params[0]['fromBlock'],16),int(params[0]['toBlock'],16)))
                return []
            assert method=='eth_getBlockByNumber'
            n=1046 if params[0]=='finalized' else 1048 if params[0]=='latest' else int(params[0],16)
            return dict(number=hex(n),hash='0x'+'a'*64,timestamp='0x1')
    original=RPC();rpc=PreparationRPC(original,clock=clock.now,sleep=clock.sleep)
    cursor=dict(from_block=1,to_block=10,block_hash='0x'+'a'*64,balances={},events_count=0)
    prior={'snapshot':dict(block_number=0,block_hash='0x'+'a'*64)}
    qualified=qualify_finalized(rpc)
    result,_=fixed_scan(rpc,cursor,qualified['anchor'])
    assert ranges==[(i,min(i+9,1046)) for i in range(11,1047,10)]
    assert len(ranges)==104
    assert result['to_block']==1046 and qualified['anchor']['number']==1046
    assert calls[-1][:2]==('eth_getBlockByNumber',['0x416',False])
    assert all(b[2]-a[2]>=.2-1e-9 for a,b in zip(calls,calls[1:]))
    assert original.parallel_inventory_reads is True
    assert cursor['to_block']==10


def test_run_reports_preparation_429_and_never_starts_account(monkeypatch):
    import analysis.qualify_post_genesis as q
    import analysis.qualify_post_b_proofs as p
    for flag in ('REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED'):monkeypatch.setenv(flag,'false')
    monkeypatch.setenv('POLYGON_ARCHIVE_RPC_URL','https://example.invalid')
    prior=dict(phase='GENESIS_RECONCILED',event_count=0,last_hash='a',snapshot_sha256='b',
        snapshot=dict(wallet='wallet',collateral={'contract':q.CONTRACT}))
    monkeypatch.setattr(q,'read_genesis',lambda *a:prior)
    monkeypatch.setattr(q,'expected_wallet',lambda:'wallet')
    monkeypatch.setattr(q,'load_inventory_cursor',lambda *a:{'observed_ms':1000})
    class RPC:
        def __init__(self,*a,**kw):self.calls=[]
        def call(self,*a):
            self.calls.append({'http_status':429})
            raise RuntimeError('PRIVATE_ENDPOINT')
    class Get:
        def __init__(self,*a,**kw):pass
        async def get_json(self,*a):return 1
    monkeypatch.setattr(q,'PublicRPC',RPC)
    monkeypatch.setattr(q,'GetOnlyTransport',Get)
    def unavailable(rpc,*a):rpc.call('eth_chainId',[])
    monkeypatch.setattr(p,'prepare_finalized_inventory',unavailable)
    def forbidden(*a):raise AssertionError('MUST_NOT_LOAD_ACCOUNT')
    monkeypatch.setattr(q,'load_existing',forbidden)
    result=asyncio.run(q.run(True,health_contract=True))
    assert result['reconciliation']['reason']=='PREPARATION_RPC_RATE_LIMITED'
    assert result['preparation_rpc_policy']['requests_started']==1
    assert not result['readiness']['SYSTEM_READY'] and not result['readiness']['submit_allowed']
    import json
    assert 'PRIVATE_ENDPOINT' not in json.dumps(result)
