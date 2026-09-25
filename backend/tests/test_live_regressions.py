import ast
import asyncio
from pathlib import Path
import pytest
from app.live import clob_transport
from app.live.clob_transport import normalize_order_status
from app.live.clob_staged import (PersistedPositionState, RemoteStateProjector,
    ReadOnlyPositionSynchronizer, PositionStateStore, RecoveryReconciler)
from app.live.risk import RiskManager


def test_sdk_dictionary_remains_structured():
    data={"order_id":"fixture", "status":"LIVE"}
    assert clob_transport._plain(data)==data


def test_mystery_rejected_even_when_remaining_zero():
    value=normalize_order_status({"response":{"status":"MYSTERY","original_size":"10","size_matched":"10"}})
    state=PersistedPositionState("s","m","t")
    assert not RemoteStateProjector().apply(state,value)["ok"]
    assert state.state=="PREPARED" and state.filled_shares==0


@pytest.mark.parametrize("filled,expected_open",[(10,0),(4,6)])
def test_exit_updates_sold_not_entry_fills(tmp_path,filled,expected_open):
    class Client:
        async def get_order(self,**kwargs):
            return {"status":"MATCHED" if filled==10 else "LIVE","original_size":"10","size_matched":str(filled)}
    store=PositionStateStore(tmp_path/"position.json")
    state=PersistedPositionState("s","m","t",state="FILLED",entry_order_id="buy",exit_order_id="sell",filled_shares=10)
    result=asyncio.run(ReadOnlyPositionSynchronizer(Client(),store).sync(state))
    assert result["ok"]
    assert state.filled_shares==10 and state.sold_shares==filled and state.open_shares==expected_open
    assert not store.assert_flat_or_recover()["allow_new_entry"]


def test_closed_restart_requires_remote_policy():
    class Client:
        calls=0
        async def get_order(self,**kwargs):
            self.calls+=1
            return {"status":"MATCHED","original_size":"10","size_matched":"10"}
    client=Client()
    state=PersistedPositionState("s","m","t",state="CLOSED",entry_order_id="buy",exit_order_id="sell",filled_shares=10,sold_shares=10)
    result=asyncio.run(RecoveryReconciler(client).reconcile(state))
    assert client.calls==1
    assert not result["allow_new_entry"]


def test_inaccessible_remote_requires_recovery():
    class Client:
        async def get_order(self,**kwargs): raise OSError("unavailable")
    state=PersistedPositionState("s","m","t",state="FILLED",entry_order_id="buy",filled_shares=10)
    result=asyncio.run(RecoveryReconciler(Client()).reconcile(state))
    assert result["reason"]=="RECOVERY_REQUIRED" and not result["allow_new_entry"]


def test_one_usdc_cannot_fund_25_usdc():
    assert not RiskManager().approve(notional=25,bankroll=1,open_positions=0,session_pnl=0)[0]


def test_precheck_compares_usdc_not_raw_units():
    source=Path(clob_transport.__file__).resolve().parents[3]/"analysis/pre_live_check_d6.py"
    tree=ast.parse(source.read_text(encoding="utf-8"))
    main=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=="main")
    conversion=next(n for n in main.body if isinstance(n,ast.Try) and any(
        isinstance(x,ast.Name) and x.id=="balance_value" for x in ast.walk(n)))
    scope={"result":{"collateral_balance":"1000000","collateral_balance_usdc":1.0}}
    exec(compile(ast.Module(body=[conversion],type_ignores=[]),"balance_precheck","exec"),scope)
    assert scope["balance_value"]==1.0


@pytest.mark.parametrize("report",[
    {"status":"LIVE","original_size":"10","size_matched":"nan"},
    {"status":"MATCHED","original_size":"10","size_matched":"4"},
    {"status":"LIVE","original_size":"10"},
    {"status":"LIVE","original_size":"10","size_matched":"4","filled_size":"5"},
])
def test_ambiguous_sizes_rejected(report):
    assert normalize_order_status({"response":report})["known"] is False


def test_conflicting_ack_ids_are_ambiguous():
    assert clob_transport.extract_order_id({"response":{"order_id":"first","id":"second"}}) is None
