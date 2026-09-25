import pytest
from app.live.execution import ExecutionController, ExecutionBlocked
from app.live.clob_staged import StagedLimitOrder


def test_sources_are_required_and_disconnect_is_immediate():
    from app.live.execution_sources import ExecutionStateSources
    book=dict(connected=True,book_synced=True,market_slug="m",token_id="t",observed_ms=1000,expiry_ms=200000,fillable_shares=10)
    risk=dict(observed_ms=1000,session_pnl=-2,available_usdc=109.16)
    geo=dict(blocked=False,observed_ms=1000)
    signal=dict(valid=True,observed_ms=1000)
    position=dict(open_positions=0,recovery_complete=True)
    source=ExecutionStateSources(book=lambda:book,risk=lambda:risk,geo=lambda:geo,signal=lambda:signal,position=lambda:position)
    assert source()["session_pnl"]==-2 and source()["available_usdc"]==109.16
    book["connected"]=False
    assert source()["connected"] is False
    geo.clear()
    assert source()["geoblock_blocked"] is None


def test_unknown_staging_state_cannot_pass():
    from app.live.execution_sources import staging_gate
    result=staging_gate(None,StagedLimitOrder("s","m","t","BUY",5,.5,10,.01,1),now_ms=1000)
    assert not result["allow"]


def test_stale_geo_cannot_pass():
    from app.live.execution_sources import staging_gate
    value=dict(connected=True,book_synced=True,signal_valid=True,recovery_complete=True,geoblock_blocked=False,
        market_slug="m",token_id="t",book_ms=1000,risk_ms=1000,signal_ms=1000,geo_ms=0,expiry_ms=200000,
        open_positions=0,session_pnl=0,available_usdc=100,fillable_shares=20)
    assert not staging_gate(lambda:value,StagedLimitOrder("s","m","t","BUY",5,.5,10,.01,1),now_ms=1000)["allow"]


def test_exit_source_preserves_book_snapshot_and_explicit_policy():
    from app.live.execution_sources import ExecutionStateSources
    book={'books':{'t':{'bids':[(.4,10)],'asks':[(.5,10)]}},'generation':3,'observed_ms':1000}
    src=ExecutionStateSources(book=lambda:book,risk=lambda:{},geo=lambda:{},signal=lambda:{},position=lambda:{},exit_policy=lambda:{'max_slippage_bps':25})
    snap=src()
    assert snap['max_exit_slippage_bps']==25
    assert snap['exit_book']['generation']==3
    book['books']['t']['bids'].clear()
    assert snap['exit_book']['books']['t']['bids']==[(.4,10)]


def test_missing_exit_policy_never_gets_an_optimistic_default():
    from app.live.execution_sources import ExecutionStateSources
    src=ExecutionStateSources(book=lambda:{},risk=lambda:{},geo=lambda:{},signal=lambda:{},position=lambda:{})
    assert src()['max_exit_slippage_bps'] is None
