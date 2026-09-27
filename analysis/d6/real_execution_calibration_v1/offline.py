"""Offline fixtures only. No SDK, signatures, credentials, sockets or live-mode option."""
from __future__ import annotations
import argparse, copy, datetime as dt, io, json, os, re, sys, threading, time, uuid
from decimal import Decimal
from pathlib import Path
from .core import CalibrationLedger, Journal, dec, digest, encoded
from .v1_binding import verify

MODE = "SIMULATION_ONLY"
ROTATION_SECONDS = 7200
# Logs reject arbitrary strings containing credentials, not merely sensitive keys.
SAFE_EVENTS = {"INIT","RECONCILIATION_OBSERVATION","RECONCILED","SHADOW_SEALED",
 "RESERVE","DURABLE_INTENT","ACK_RESPONSE","FILL_OBSERVATION","ORDER_TERMINAL_OBSERVATION",
 "STOP","CHECKPOINT","SIMULATION_START","SIMULATION_COMPLETE","ROTATION","SHADOW_COMPARISON"}
SENSITIVE = ("secret","privatekey","signature","credential","authorization","apikey","passphrase","seedphrase")

def sanitize(value):
    if isinstance(value, dict):
        return {str(k): "[REDACTED]" if any(s in re.sub(r"[^a-z]", "", str(k).lower()) for s in SENSITIVE)
                else sanitize(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)): return [sanitize(v) for v in value]
    if isinstance(value, str):
        if re.search(r"(?i)(bearer\s|0x[0-9a-f]{64,}|-----BEGIN .*PRIVATE KEY|(?:secret|password|credential|signature|private.key|api.key)\s*[:=])",value):
            return "[REDACTED]"
    return value

def durable(path, value):
    data=(encoded(sanitize(value))+"\n").encode()
    with Path(path).open("xb", buffering=0) as f:
        view=memoryview(data)
        while view:
            n=f.write(view)
            if not n: raise OSError("SHORT_WRITE")
            view=view[n:]
        os.fsync(f.fileno())

class RotatingLog:
    """Independent timer rotates even with no messages; every record is fsynced."""
    def __init__(self, directory, session, *, console=None, clock=time.monotonic,
                 utc=lambda:dt.datetime.now(dt.timezone.utc), background=True):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}",session): raise ValueError("SESSION_INVALID")
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.session=session;self.console=sys.stdout if console is None else console
        self.clock=clock;self.utc=utc;self.started=clock();self.part=0;self.file=None
        self.lock=threading.RLock();self.closed=False;self.failed=False;self.error=None
        self.stop_event=threading.Event();self.thread=None;self.snapshot=None
        self._open()
        if background:
            self.thread=threading.Thread(target=self._timer,daemon=True,name="simulation-log")
            self.thread.start()
    def _open(self):
        stamp=self.utc().strftime("%Y%m%d_%H%M")
        # Part suffix is included in session component; also safe if wall clock moves backwards.
        self.path=self.directory/f"REAL_CALIBRATION_{stamp}_{self.session}-p{self.part:04d}.log"
        self.file=self.path.open("xb",buffering=0)
        os.fsync(self.file.fileno())
    def _timer(self):
        while not self.stop_event.wait(.25):
            try:self.tick()
            except BaseException as exc:
                self.failed=True;self.error=type(exc).__name__;return
    def tick(self):
        with self.lock:
            if self.closed:return
            if self.failed:raise OSError("LOG_FAILED")
            try:
                if self.clock()-self.started>=ROTATION_SECONDS:
                    if self.snapshot is not None:
                        durable(self.directory/f"SIMULATION_REPORT_{self.session}_p{self.part:04d}.json",self.snapshot())
                    self.file.close();self.part+=1;self.started=self.clock();self._open()
            except BaseException:
                self.failed=True;raise
    def encode_record(self,row):return encoded(sanitize({"mode":MODE,**row}))
    def write(self,row):
        with self.lock:
            if self.closed:raise OSError("LOG_CLOSED")
            self.tick()
            try:
                data=(self.encode_record(row)+"\n").encode()
                view=memoryview(data)
                while view:
                    n=self.file.write(view)
                    if not n:raise OSError("SHORT_WRITE")
                    view=view[n:]
                os.fsync(self.file.fileno())
                self.console.write(data.decode());self.console.flush()
            except BaseException:self.failed=True;raise
    def close(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=2)
        with self.lock:
            self.closed=True
            if self.file and not self.file.closed:self.file.close()

class LoggedJournal(Journal):
    def __init__(self,path,session,log):
        self.log=log
        super().__init__(path,session)
    def project_shadow(self,shadow):return sanitize(shadow)
    def append(self,kind,payload):
        if kind not in SAFE_EVENTS:raise ValueError("EVENT_NOT_ALLOWED")
        # Log failures poison the ledger before any simulated submission.
        if self.log.failed: self.failed=True;raise OSError("LOG_FAILED")
        try:
            row=super().append(kind,sanitize(payload))
            self.log.write(row);return row
        except BaseException:self.failed=True;raise

class SimulatedExchange:
    """Independent account state. Never derives its balance/positions from the ledger."""
    def __init__(self):
        self.cash=Decimal(100);self.positions={};self.trades=[];self.orders=[]
    def snapshot(self):
        return {"account":"SIMULATED_ACCOUNT","cash":str(self.cash),
            "positions":{k:str(v) for k,v in self.positions.items() if v},
            "observed_ms":1000,"open_orders":[],"terminal_order_ids":self.orders.copy(),
            "trade_ids":self.trades.copy(),**{k:True for k in
            ("inventory_proven","cash_proven","orders_complete","trades_complete","positions_complete")}}
    def execute(self,cid,side,requested,ratio):
        q=dec(requested)*dec(ratio)
        if q>dec(requested):raise ValueError("RATIO_INVALID")
        price=Decimal(".5") if side=="BUY" else Decimal(".49")
        oid="SIM-"+cid;fills=[]
        if q:
            fee=Decimal(".1");tid=oid+"-fill"
            if side=="BUY":self.cash-=q*price+fee;self.positions["SIM_TOKEN"]=self.positions.get("SIM_TOKEN",Decimal(0))+q
            else:
                if q>self.positions.get("SIM_TOKEN",Decimal(0)):raise ValueError("SIM_OVERSOLD")
                self.cash+=q*price-fee;self.positions["SIM_TOKEN"]-=q
            self.trades.append(tid)
            fills=[{"trade_id":tid,"order_id":oid,"token":"SIM_TOKEN","market":"SIM_MARKET",
                "side":side,"price":str(price),"shares":str(q),"cash_fee":str(fee),"share_fee":"0",
                "fee_evidence":{"cash_effect_proven":True,"share_effect_proven":True,"provenance":"SYNTHETIC_FIXED_FEE"},
                "exchange_ts_ms":999,"receive_ts_ms":1000}]
        self.orders.append(oid)
        return {"ok":True,"order_id":oid},fills,("FILLED" if q==dec(requested) else "CANCELED"),q

def recover_prefix(path):
    """Read-only recovery of verified prefix. Never repair, truncate or resume a journal."""
    previous="0"*64;rows=[];session=None;problem=None
    with Path(path).open("rb") as f:
        while True:
            line=f.readline(1024**2+1)
            if not line:break
            if len(line)>1024**2 or not line.endswith(b"\n"):problem="TORN_TAIL";break
            try:
                row=json.loads(line);h=row.pop("hash")
                if session is None:session=row["experiment_id"]
                if row["seq"]!=len(rows) or row["previous"]!=previous or row["experiment_id"]!=session or digest(row)!=h:
                    raise ValueError()
                row["hash"]=h;rows.append(row);previous=h
            except (ValueError,KeyError,TypeError):problem="CORRUPTION";break
    return {"mode":MODE,"verified_records":len(rows),"problem":problem,
        "last_checkpoint":next((r["payload"] for r in reversed(rows) if r["kind"]=="CHECKPOINT"),None),
        "verified_evidence":rows,"STOP_NEW_ENTRIES":True,"armed":False,"resume_allowed":False,
        "exposure_known":False}

class Simulation:
    def __init__(self,directory,*,console=None,background=True,clock=time.monotonic,utc=lambda:dt.datetime.now(dt.timezone.utc)):
        verify()
        self.directory=Path(directory);self.session="sim-"+uuid.uuid4().hex
        self.log=RotatingLog(directory,self.session,console=console,background=background,clock=clock,utc=utc)
        self.lock=threading.RLock();self.comparisons=[];self.exchange=SimulatedExchange()
        self.journal=LoggedJournal(self.directory/f"SIMULATION_LEDGER_{self.session}.jsonl",self.session,self.log)
        self.ledger=CalibrationLedger(self.journal,"SIMULATED_ACCOUNT",100)
        self.log.snapshot=self.report
        self.reconcile()
    def reconcile(self):
        return self.ledger.reconcile(self.exchange.snapshot(),1000)
    def kill(self,reason):
        with self.lock:
            self.ledger.halt(reason);self.publish()
    def guard(self):
        try:
            for _ in Journal.read(self.journal.path):pass
        except (ValueError,KeyError,TypeError,OSError):
            self.ledger.stop=True;self.ledger.reconciled=False;self.journal.failed=True
            self.ledger.reasons.append("LEDGER_CORRUPTION")
            raise ValueError("LEDGER_CORRUPTION")
        if self.log.failed or self.journal.failed:
            self.ledger.stop=True;self.ledger.reconciled=False
            raise OSError("SIMULATION_STORAGE_FAILED")
        if (self.directory/"STOP_NEW_ENTRIES").exists() and not self.ledger.stop:
            self.kill("MANUAL_KILL")
    def order(self,cid,side,q,ratio):
        self.guard()
        price=".5" if side=="BUY" else ".49"
        book={"mode":MODE,"market":"SIM_MARKET","token":"SIM_TOKEN","asks":[[".5","100"]],"bids":[[".49","100"]]}
        expected={"book":book,"expected_price":price,"expected_qty":str(q),
            "expected_fill":"FULL_SYNTHETIC_DEPTH","expected_fee":".1",
            "expected_exit":"SIMULATED_SELL_AFTER_ENTRY_RECONCILIATION"}
        self.ledger.emit("SHADOW_COMPARISON",{"phase":"SEALED_BEFORE_SIMULATED_ORDER","client_id":cid,"expected":expected,"sha256":digest(expected)})
        self.ledger.intent(cid,side,"SIM_TOKEN","SIM_MARKET",price,str(q),str(dec(price)*dec(q)),book,1000)
        ack,fills,status,qty=self.exchange.execute(cid,side,q,ratio)
        if not self.ledger.ack(cid,ack,1000):return
        for fill in fills:
            if not self.ledger.fill(cid,fill):return
        if not self.ledger.terminal(cid,status,str(qty)):return
        self.reconcile()
        comparison={"client_id":cid,"expected":expected,"actual_qty":str(qty),"actual_fee":".1" if qty else "0",
                    "unfilled_qty":str(dec(q)-qty),"mode":MODE}
        self.comparisons.append(comparison);self.ledger.emit("SHADOW_COMPARISON",comparison)
    def cycle(self,scenario="full",notional="25"):
        with self.lock:
            self.guard()
            op="op"+uuid.uuid4().hex
            self.ledger.seal_shadow(op,{"market":"SIM_MARKET","token":"SIM_TOKEN","mode":MODE})
            self.ledger.reserve(op,notional,"1")
            self.order(op+"-buy","BUY",dec(notional)/Decimal(".5"),"0" if scenario=="no-fill" else ".5" if scenario=="partial" else "1")
            if scenario=="mismatch":
                self.exchange.cash-=Decimal(1);self.reconcile()
            if scenario=="kill":self.kill("MANUAL_KILL")
            if self.ledger.reconciled and self.ledger.positions.get("SIM_TOKEN",0):
                self.order(op+"-sell","SELL",self.ledger.positions["SIM_TOKEN"],".5" if scenario=="residual" else "1")
                if self.ledger.positions.get("SIM_TOKEN",0):self.kill("RESIDUAL_REQUIRES_OPERATOR_HANDOFF")
            self.ledger.checkpoint();self.publish()
    def report(self):
        # Timer uses cached immutable snapshot published under the operation lock by finish/cycle.
        # It must never acquire ledger lock while holding log lock (avoid inversion).
        return copy.deepcopy(getattr(self,"published",{"mode":MODE,"status":"INITIALIZING","armed":False}))
    def publish(self):
        self.published={"mode":MODE,"ledger":self.ledger.report(),"orders":copy.deepcopy(self.ledger.orders),
            "ACKs":sum(o["order_id"] is not None for o in self.ledger.orders.values()),
            "exits":sum(o["side"]=="SELL" for o in self.ledger.orders.values()),
            "shadow_vs_real_label":"SIMULATED_COMPARISON_ONLY","differences":copy.deepcopy(self.comparisons),
            "real_execution_ready":False,"armed":False}
    def finish(self):
        try:
            self.publish()
            durable(self.directory/f"SIMULATION_FINAL_{self.session}.json",self.report())
        finally:self.journal.close();self.log.close()

def deny_network(event,args):
    if event in ("socket.connect","socket.getaddrinfo","socket.bind"):
        raise RuntimeError("SIMULATION_NETWORK_FORBIDDEN")

def main():
    p=argparse.ArgumentParser(description="Offline synthetic calibration; never real orders.")
    p.add_argument("--output",type=Path,default=Path("D:/polymarket-real-calibration/simulation"))
    p.add_argument("--scenario",choices=["full","partial","no-fill","kill","mismatch","residual"],default="full")
    p.add_argument("--recover",type=Path)
    a=p.parse_args()
    sys.addaudithook(deny_network)
    if a.recover:
        print(encoded(recover_prefix(a.recover)));return 0
    sim=Simulation(a.output)
    try:
        sim.cycle(a.scenario);sim.publish()
        print(encoded({"mode":MODE,"session":sim.session,"report":sim.ledger.report()}),flush=True)
        return 0
    except BaseException:
        sim.ledger.stop=True
        raise
    finally:sim.finish()

if __name__=="__main__":raise SystemExit(main())

