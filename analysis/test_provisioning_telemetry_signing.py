import copy
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import pytest
from eth_account import Account
from analysis.provisioning_telemetry_signing import TelemetrySigner, KINDS
from analysis.provisioning_clock_candidate import ClockCandidate
from analysis.d6.real_execution_calibration_v1.core import digest
from app.live.readonly_book_stream import StreamBook


def fixture():
    t=[10000]; key=Account.create()  # Ephemeral TEST key, never a production approval.
    context=dict(account='wallet',signer='owner',collateral='pUSD',session='TEST_ONLY',
                 market='condition',strategy_hashes={'v1':'a'*64})
    policy=dict(keys={'test':dict(address=key.address,kinds=sorted(KINDS))},provider='TEST_ONLY',
                context={k:context[k] for k in ('account','signer','collateral','session')})
    signer=TelemetrySigner(policy=policy,approved_digest=digest(policy),key_id='test',key=key,context=context,now=lambda:t[0])
    return t,signer,policy,key,context


def test_clock_real_crypto_and_expiry():
    t,s,_,_,_=fixture(); lease=ClockCandidate(wall_ms=lambda:t[0],monotonic_ms=lambda:t[0])
    lease.update([dict(host=h,observed_ms=10000,offset_ms=1,uncertainty_ms=20) for h in ('a','b','c')])
    record=s.clock(lease)
    assert s.authority.verify(record)
    changed=copy.deepcopy(record);changed['payload']['offset_ms']=0
    assert not s.authority.verify(changed)
    t[0]=15001
    assert not s.authority.verify(record)
    with pytest.raises(ValueError):s.clock(lease)


def test_no_default_approval_or_account_signing():
    _,s,p,k,c=fixture()
    with pytest.raises(ValueError):TelemetrySigner(policy=p,approved_digest=None,key_id='test',key=k,context=c,now=lambda:10000)
    with pytest.raises(ValueError):s._sign('balance_sufficient',{},10000,11000)
    p['keys']['test']['kinds'].append('snapshot')
    with pytest.raises(ValueError):TelemetrySigner(policy=p,approved_digest=digest(p),key_id='test',key=k,context=c,now=lambda:10000)


def test_real_stream_type_snapshots_staleness_disconnect():
    t,s,_,_,_=fixture()
    with pytest.raises(ValueError):s.book(object())
    stream=StreamBook('slug','condition',('1','2'),20000,clock=lambda:t[0])
    stream.connected_generation()
    for token in ('1','2'):
        stream.ingest(dict(event_type='book',market='condition',asset_id=token,timestamp='10000',
                           bids=[dict(price='0.4',size='2')],asks=[dict(price='0.6',size='2')]),wire_received_ms=10000)
    record=s.book(stream)
    assert s.authority.verify(record) and record['valid_until_ms']==10500
    t[0]=10501
    with pytest.raises(ValueError):s.book(stream)
    stream.disconnect()
    with pytest.raises(ValueError):s.book(stream)


def test_pipeline_withdraws_on_source_failure_and_shutdown(monkeypatch):
    import asyncio
    import analysis.provisioning_telemetry_signing as module
    async def scenario():
        t,s,_,_,_=fixture()
        lease=ClockCandidate(wall_ms=lambda:t[0],monotonic_ms=lambda:t[0])
        stop=asyncio.Event(); published=[]
        def publish(directory,records,now):
            published.append(records)
            if len(published)==2:stop.set()
        monkeypatch.setattr(module,'publish_subset',publish)
        def failed_source():raise TimeoutError()
        await module.run_telemetry(signer=s,stream=object(),lease=lease,
            sample_clock=failed_source,directory='UNUSED_TEST',stop=stop)
        assert len(published)>=3 and all(x=={} for x in published)
    asyncio.run(scenario())
