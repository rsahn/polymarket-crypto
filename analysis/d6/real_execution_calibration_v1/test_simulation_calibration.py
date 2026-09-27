import io,json,time,threading
from decimal import Decimal
from pathlib import Path
import pytest
from analysis.d6.real_execution_calibration_v1.offline import Simulation,RotatingLog,recover_prefix,sanitize,deny_network
from analysis.d6.real_execution_calibration_v1.core import Journal

def sim(tmp_path,**kw):return Simulation(tmp_path,console=io.StringIO(),background=False,**kw)

@pytest.mark.parametrize("scenario,orders,position,stopped",[
 ("full",2,0,False),("partial",2,0,False),("no-fill",1,0,False),
 ("kill",2,0,True),("mismatch",1,50,True),("residual",2,25,True)])
def test_independent_exchange_scenarios(tmp_path,scenario,orders,position,stopped):
 s=sim(tmp_path)
 try:
  s.cycle(scenario)
  assert len(s.ledger.orders)==orders
  assert s.ledger.positions.get("SIM_TOKEN",0)==position
  assert s.ledger.stop is stopped
  assert s.exchange.cash==s.ledger.cash or scenario=="mismatch"
  if scenario=="kill":assert s.ledger.reconciled and s.ledger.active is None
  if stopped:
   with pytest.raises(ValueError):s.cycle()
  if scenario=="partial":assert s.ledger.report()["partial_fills"]==1
  if scenario=="no-fill":assert s.ledger.report()["no_fills"]==1
  rows=list(Journal.read(s.journal.path))
  for i,row in enumerate(rows):
   if row["kind"]=="DURABLE_INTENT":
    assert rows[i-1]["kind"]=="SHADOW_COMPARISON"
    assert rows[i-1]["payload"]["phase"]=="SEALED_BEFORE_SIMULATED_ORDER"
 finally:s.finish()

def test_caps_and_fee_budget(tmp_path):
 s=sim(tmp_path)
 try:
  with pytest.raises(ValueError,match="CAP_25"):s.cycle(notional="25.01")
  for _ in range(3):s.cycle("no-fill")
  assert s.ledger.allocated==78
  with pytest.raises(ValueError,match="CAP_100"):s.cycle("no-fill")
 finally:s.finish()

def test_position_gate_after_residual(tmp_path):
 s=sim(tmp_path)
 try:
  s.cycle("residual")
  with pytest.raises(ValueError):s.cycle()
  assert len(s.ledger.orders)==2
 finally:s.finish()

def test_rotation_quiet_timer_and_report(tmp_path):
 now=[0];log=RotatingLog(tmp_path,"quiet",console=io.StringIO(),clock=lambda:now[0],background=True)
 log.snapshot=lambda:{"mode":"SIMULATION_ONLY","example":"snapshot"}
 try:
  original=log.path;now[0]=7200
  deadline=time.monotonic()+2
  while log.part==0 and time.monotonic()<deadline:time.sleep(.02)
  assert log.part==1 and log.path!=original
  assert len(list(tmp_path.glob("*.log")))==2
  assert len(list(tmp_path.glob("SIMULATION_REPORT*.json")))==1
 finally:log.close()

def test_rotation_boundary_no_overwrite_and_console(tmp_path):
 now=[0];stream=io.StringIO()
 log=RotatingLog(tmp_path,"boundary",console=stream,clock=lambda:now[0],background=False)
 try:
  log.write({"kind":"test","seq":0});now[0]=7199.99;log.tick();assert log.part==0
  old=log.path.read_bytes();now[0]=7200;log.tick()
  log.write({"kind":"test","seq":1})
  assert len(stream.getvalue().splitlines())==2
  assert list(sorted(tmp_path.glob("*.log")))[0].read_bytes()==old
  with pytest.raises(FileExistsError):RotatingLog(tmp_path,"boundary",console=io.StringIO(),background=False)
 finally:log.close()

def test_fsync_error_poison_prevents_simulated_order(tmp_path,monkeypatch):
 s=sim(tmp_path)
 try:
  monkeypatch.setattr("os.fsync",lambda fd:(_ for _ in ()).throw(OSError("fixture")))
  with pytest.raises(OSError):s.cycle()
  assert s.ledger.stop and not s.exchange.orders and s.journal.failed
 finally:
  monkeypatch.undo();s.finish()

def test_external_kill_file_and_manage_existing_exit(tmp_path):
 s=sim(tmp_path)
 try:
  (tmp_path/"STOP_NEW_ENTRIES").touch()
  with pytest.raises(ValueError):s.cycle()
  assert s.ledger.stop and not s.exchange.orders
 finally:s.finish()

def test_crash_prefix_recovery_never_modifies_or_resumes(tmp_path):
 s=sim(tmp_path);s.cycle();s.finish()
 raw=s.journal.path.read_bytes()
 torn=tmp_path/"torn.jsonl";torn.write_bytes(raw+b'{"partial":')
 r=recover_prefix(torn)
 assert r["problem"]=="TORN_TAIL" and r["last_checkpoint"]
 assert not r["resume_allowed"] and not r["armed"] and r["STOP_NEW_ENTRIES"]
 assert torn.read_bytes()==raw+b'{"partial":'
 bad=tmp_path/"bad.jsonl";bad.write_bytes(raw.replace(b"INIT",b"FAIL",1))
 assert recover_prefix(bad)["problem"]=="CORRUPTION"
 assert recover_prefix(bad)["verified_records"]==0

def test_secret_filter_does_not_echo_freeform_tokens(tmp_path):
 log=RotatingLog(tmp_path,"redaction",console=io.StringIO(),background=False)
 try:
  log.write({"private-key":"CANARY_ONE","nested":{"signature":"CANARY_TWO"},
             "message":"Bearer CANARY_THREE","text":"secret=CANARY_FOUR"})
  text=log.path.read_text()+log.console.getvalue()
  assert "CANARY" not in text and text.count("[REDACTED]")==8
 finally:log.close()

@pytest.mark.parametrize("event",["socket.connect","socket.bind","socket.getaddrinfo"])
def test_runner_network_guard(event):
 with pytest.raises(RuntimeError,match="NETWORK_FORBIDDEN"):deny_network(event,())

def test_report_is_explicitly_simulated(tmp_path):
 s=sim(tmp_path);s.cycle();s.finish()
 r=json.loads(next(tmp_path.glob("SIMULATION_FINAL*")).read_text())
 assert r["mode"]=="SIMULATION_ONLY" and not r["armed"] and not r["real_execution_ready"]
 assert len(r["differences"])==2 and Decimal(r["ledger"]["net_realized_pnl"])==Decimal("-0.7")
 assert not r["ledger"]["SYSTEM_READY"] and not r["ledger"]["submit_allowed"]


@pytest.mark.parametrize("reason",["UNKNOWN_ORDER","UNKNOWN_FILL","UNKNOWN_POSITION",
 "WS_INVALID","BUDGET_UNCERTAINTY","CRITICAL_EXCEPTION"])
def test_uncertainty_stops_entries_but_reconciliation_can_manage_exit(tmp_path,reason):
 s=sim(tmp_path)
 try:
  op="held";s.ledger.seal_shadow(op,{"market":"SIM_MARKET","token":"SIM_TOKEN"})
  s.ledger.reserve(op,"25","1");s.order("entry","BUY",Decimal(50),"1")
  s.kill(reason)
  assert s.ledger.stop and not s.ledger.reconciled and s.ledger.positions["SIM_TOKEN"]==50
  with pytest.raises(ValueError):s.cycle()
  assert s.reconcile()
  s.order("exit","SELL",Decimal(50),"1")
  assert not any(s.ledger.positions.values()) and s.ledger.stop
 finally:s.finish()

def test_runtime_corruption_closes_gate(tmp_path):
 s=sim(tmp_path)
 try:
  raw=s.journal.path.read_bytes()
  with s.journal.path.open("r+b") as f:f.write(raw.replace(b"INIT",b"FAIL",1))
  with pytest.raises(ValueError,match="CORRUPTION"):s.cycle()
  assert s.ledger.stop and not s.exchange.orders
 finally:s.finish()

def test_process_crash_durable_recovery(tmp_path):
 import subprocess,sys
 child_dir=tmp_path/"crash"
 script="from analysis.d6.real_execution_calibration_v1.offline import Simulation; import io,os; s=Simulation("+repr(str(child_dir))+",console=io.StringIO()); s.cycle('residual'); os._exit(9)"
 result=subprocess.run([sys.executable,"-B",str(Path(__file__).with_name("crash_fixture.py")),str(child_dir)],cwd=Path(__file__).resolve().parents[3],capture_output=True,timeout=15)
 assert result.returncode==9,result.stderr.decode()
 journal=next(child_dir.glob("SIMULATION_LEDGER*"))
 r=recover_prefix(journal)
 assert r["problem"] is None and r["last_checkpoint"]["report"]["open_exposure"]=={"SIM_TOKEN":"25.0"}
 assert not r["resume_allowed"]

def test_logging_failure_prevents_next_entry(tmp_path):
 s=sim(tmp_path)
 try:
  s.log.failed=True
  with pytest.raises(OSError):s.cycle()
  assert s.ledger.stop and not s.exchange.orders
 finally:s.finish()

