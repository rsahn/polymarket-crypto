from app.live.clob_staged import KillSwitch,SimulatedLifecycle

def test_full_fill_exit():
 s=SimulatedLifecycle();s.ack();s.fill(size=10,price=.4,requested_size=10)
 assert s.state=="FILLED" and s.open_size==10
 s.exit_fill(size=10,price=.41)
 assert s.state=="CLOSED" and round(s.realized_pnl,8)==.1

def test_partial_cancel_then_exit():
 s=SimulatedLifecycle();s.ack();s.fill(size=4,price=.5,requested_size=10);s.cancel()
 assert s.state=="CANCELLED_PARTIAL" and s.open_size==4
 s.exit_fill(size=4,price=.49)
 assert s.state=="CLOSED" and round(s.realized_pnl,8)==-.04

def test_kill_switch():
 k=KillSwitch()
 assert k.check(open_positions=0,session_pnl=0)["allow"]
 assert not k.check(open_positions=1,session_pnl=0)["allow"]
 assert not k.check(open_positions=0,session_pnl=-25)["allow"]
 assert not k.check(open_positions=0,session_pnl=0,geoblock_blocked=True)["allow"]
 assert not k.check(open_positions=0,session_pnl=0,market_rotated=True)["allow"]
 assert not k.check(open_positions=0,session_pnl=0,book_available=False)["allow"]
