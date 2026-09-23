from app.live.clob_dry_run import ClobDryRunAdapter

def test_prepare_buy_never_submits():
 a=ClobDryRunAdapter();o=a.prepare_buy(signal_id="s1",market_slug="m1",token_id="t1",notional=25,best_ask=.50)
 r=a.serialize(o)
 assert r["mode"]=="DRY_RUN" and r["submit_allowed"] is False
 assert o.notional==25 and 0<o.limit_price<1 and o.size>0

def test_invalid_ask_rejected():
 a=ClobDryRunAdapter()
 try:a.prepare_buy(signal_id="s",market_slug="m",token_id="t",notional=25,best_ask=1)
 except ValueError:return
 assert False
