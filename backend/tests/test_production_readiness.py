import asyncio
from decimal import Decimal
from types import SimpleNamespace
import pytest

class Pages:
    def __init__(self,rows=(),more=False):self.rows=rows;self.more=more
    async def first_page(self):return SimpleNamespace(items=self.rows,has_more=self.more,next_cursor="again" if self.more else None)
    def from_cursor(self,cursor):return self

class Client:
    wallet="0x"+"1"*40
    def __init__(self):self.orders=[];self.positions=[];self.trades=[];self.calls=[]
    async def get_balance_allowance(self,**kw):
        self.calls.append(kw)
        return dict(balance=1000000 if kw["asset_type"]=="COLLATERAL" else 4000000,allowances={"exchange":25000000})
    def list_open_orders(self):return Pages(self.orders)
    def list_account_trades(self):return Pages(self.trades)
    def list_positions(self,**kw):self.position_args=kw;return Pages(self.positions)


def test_collateral_units_and_exact_spender():
    from app.live.production_readonly import AccountStateSource
    c=Client();s=AccountStateSource(c,wallet=c.wallet,spender="exchange",clock=lambda:1000)
    value=asyncio.run(s.read())
    assert value["balance_collateral"]=="1" and value["allowance_collateral"]=="25"
    assert value["authenticated"] is True
    assert value["complete"] is False  # credential scope is not full-wallet proof


def test_missing_spender_does_not_use_some_other_allowance():
    from app.live.production_readonly import AccountStateSource
    c=Client();v=asyncio.run(AccountStateSource(c,wallet=c.wallet,spender="wrong").read())
    assert not v["available"]


def test_broken_pagination_never_means_empty_account():
    from app.live.production_readonly import AccountStateSource
    c=Client();c.list_open_orders=lambda:Pages(more=True)
    v=asyncio.run(AccountStateSource(c,wallet=c.wallet,spender="exchange").read())
    assert not v["available"]


def test_positions_use_all_history_and_reconcile_conditional_balance():
    from app.live.production_readonly import PositionSource
    c=Client();c.positions=[dict(wallet=c.wallet,asset_id="t",current_size=Decimal("4"))]
    v=asyncio.run(PositionSource(c,wallet=c.wallet,asset_types={"t":"CONDITIONAL"}).read())
    assert v["available"] and v["balances"]=={"t":"4"}
    assert c.position_args["full_history"] is True and c.position_args["filter_amount"]==0


def test_position_mismatch_fails_closed():
    from app.live.production_readonly import PositionSource
    c=Client();c.positions=[dict(wallet=c.wallet,asset_id="t",current_size=Decimal("3"))]
    assert not asyncio.run(PositionSource(c,wallet=c.wallet,asset_types={"t":"CONDITIONAL"}).read())["available"]


def test_book_disconnect_resync_and_generation():
    from app.live.production_readonly import BookStateSource
    b=BookStateSource(clock=lambda:1000)
    b.connect("m",("u","d"),1)
    b.update("u",[(.5,10)],[(.51,10)],1000,1)
    assert not b.read()["available"]
    b.update("d",[(.48,10)],[(.49,10)],1000,1)
    assert b.read()["available"]
    b.disconnect();assert not b.read()["available"]
    b.connect("m",("u","d"),2)
    b.update("u",[(.5,10)],[(.51,10)],1000,1)
    assert not b.read()["available"]


def test_exit_uses_depth_limits_slippage_and_preserves_remainder():
    from app.live.production_readonly import BookStateSource
    from app.live.exit_policy import plan_exit
    b=BookStateSource(clock=lambda:1000);b.connect("m",("u","d"),1)
    b.update("u",[(.5,3),(.49,7)],[(.51,10)],1000,1);b.update("d",[(.48,10)],[(.49,10)],1000,1)
    r=plan_exit(b.read(),token_id="u",market_slug="m",confirmed_shares="10",requested_shares="10",tick_size=".01",max_slippage_bps=100,now_ms=1000)
    assert r["quantity"]=="3" and r["remaining_shares"]=="7" and not r["can_close"]
    assert r["limit_price"]=="0.50"


def test_no_liquidity_never_closed():
    from app.live.exit_policy import plan_exit
    r=plan_exit({"available":False},token_id="u",market_slug="m",confirmed_shares="10",requested_shares="10",tick_size=".01",max_slippage_bps=100,now_ms=1000)
    assert r["state"]=="EXIT_REQUIRED" and not r["can_close"]


def test_unknown_geoblock_and_session_risk_reject():
    from app.live.production_readonly import GeoBlockSource,SessionRiskSource
    async def geo():return {}
    assert not asyncio.run(GeoBlockSource(geo).read())["available"]
    assert not SessionRiskSource(lambda:None).read()["available"]


def test_readiness_missing_sources_never_ready():
    from app.live.readiness import ProductionReadinessCheck
    report=asyncio.run(ProductionReadinessCheck().run())
    assert report["ready_for_arm"] is False and report["submit_allowed"] is False
    assert set(("wallet_auth","balance_usdc","allowance_usdc","geoblock","book_freshness","account_reconciliation","open_orders","inventory","local_recovery_state","session_risk","transport_lock"))<=set(report["checks"])


def test_readiness_confirms_transport_lock_even_in_harness():
    from app.live.readiness import ProductionReadinessCheck
    assert asyncio.run(ProductionReadinessCheck().run())["checks"]["transport_lock"] is True


def test_book_cannot_regress_generation():
    from app.live.production_readonly import BookStateSource
    b=BookStateSource(clock=lambda:1000);b.connect("m",("u","d"),2)
    with pytest.raises(ValueError):b.connect("m",("u","d"),1)


def test_exit_rejects_stale_individual_side():
    from app.live.exit_policy import plan_exit
    book=dict(available=True,connected=True,book_synced=True,market_slug="m",generation=1,observed_ms=1000,
        books={"u":{"bids":[(.5,10)],"observed_ms":0}})
    r=plan_exit(book,token_id="u",market_slug="m",confirmed_shares="10",requested_shares="10",tick_size=".01",max_slippage_bps=100,now_ms=1000)
    assert r["state"]=="EXIT_REQUIRED"


@pytest.mark.parametrize("value",[True,"nan","-1","1.1"])
def test_bad_raw_units_rejected(value):
    from app.live.production_readonly import units
    with pytest.raises(ValueError):units(value)


def test_sdk_balance_model_adapter():
    from polymarket.models.clob.account import BalanceAllowance
    from app.live.production_readonly import AccountStateSource
    class ModelClient(Client):
        async def get_balance_allowance(self,**kw):return BalanceAllowance(balance=109160000,allowances={"exchange":25000000})
    c=ModelClient();v=asyncio.run(AccountStateSource(c,wallet=c.wallet,spender="exchange",clock=lambda:1000).read())
    assert v["balance_collateral"]=="109.16" and v["balance_usdc"] is None


def test_failed_refresh_does_not_reuse_old_success():
    from app.live.production_readonly import AccountStateSource
    c=Client();s=AccountStateSource(c,wallet=c.wallet,spender="exchange",clock=lambda:1000)
    assert asyncio.run(s.read())["available"]
    async def offline(**kw):raise OSError()
    c.get_balance_allowance=offline
    assert not asyncio.run(s.read())["available"]


def test_session_risk_includes_fees_and_reservations():
    from app.live.production_readonly import SessionRiskSource
    row=dict(mode="REAL_CONFIRMED",reconciled=True,observed_ms=1000,realized_net_pnl="-24",reserved_usdc="5",balance_usdc="30",open_positions=0,fees_complete=True)
    source=SessionRiskSource(lambda:row,clock=lambda:1000)
    assert source.read()["available_usdc"]=="25" and source.read()["allow"]
    row["realized_net_pnl"]="-25"
    assert not source.read()["allow"]
    row["fees_complete"]=False
    assert not source.read()["available"]
