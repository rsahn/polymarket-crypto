"""Synthetic fixtures only. Never reads a prospective dataset."""
import copy
import errno
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from .core import digest, file_hash, Seal, write_once
from .journal import DurableEventJournal, read_journal
from .engine import FeeQualification, ProspectiveEventAdapter
from .sealed import SealedDataset
from .evaluator import confidence_bound
from .preflight import storage_estimate

IDENTITY = dict(strategy_hash="s"*64, runner_hash="r"*64, dataset_session_id="synthetic", partition="TRAIN")
def event(kind="SIGNAL", n=1, **kw):
    return dict(event_id=str(n), kind=kind, market_id="m", token_id="t",
                direction="UP", source_ts=n, recv_ts=n, decision_ts=n,
                event_ts=n, book_ts=None, price=None, qty=None,
                notional=None, fee=None, trade_id="trade", **kw)
def fee():
    return FeeQualification.from_evidence(
        {"id":"m", "clobTokenIds":["t"], "feesEnabled":True,
         "feeSchedule":{"rate":"0.07","exponent":1,"takerOnly":True}},
        "t", source="https://gamma-api.polymarket.com/markets/slug/synthetic",
        version="SYNTHETIC", rounding="ROUND_HALF_EVEN_5DP",
        rounding_evidence="SYNTHETIC_FIXTURE_ONLY", synthetic=True)

class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"events.jsonl"
    def journal(self):
        j=DurableEventJournal(self.path, IDENTITY); self.addCleanup(j.close); return j
    def test_append_fsync_recovery(self):
        j=self.journal()
        with patch("os.fsync", wraps=os.fsync) as sync:
            j.append(event()); self.assertGreater(sync.call_count,0)
        j.close(); k=self.journal()
        self.assertEqual(len(k.records),1); k.append(event(n=2))
        self.assertEqual(len(read_journal(self.path, IDENTITY)),2)
    def test_duplicate(self):
        j=self.journal(); j.append(event())
        with self.assertRaisesRegex(ValueError,"DUPLICATE"): j.append(event())
    def test_clock_regression(self):
        j=self.journal(); j.append(event(n=3))
        with self.assertRaisesRegex(ValueError,"REGRESSION"): j.append(event(n=2))
    def test_future(self):
        j=self.journal(); e=event(); e["source_ts"]=2
        with self.assertRaisesRegex(ValueError,"TIMESTAMP"): j.append(e)
    def test_partition(self):
        j=self.journal(); e=event(); e["partition"]="OOS"
        with self.assertRaisesRegex(ValueError,"IDENTITY"): j.append(e)
    def test_sequence_gap(self):
        j=self.journal(); j.append(event()); j.close()
        row=json.loads(self.path.read_text()); row["sequence"]=2
        row.pop("event_hash"); row["event_hash"]=digest(row)
        self.path.write_text(json.dumps(row)+"\n")
        with self.assertRaisesRegex(ValueError,"SEQUENCE"): self.journal()
    def test_hash_corruption(self):
        j=self.journal(); j.append(event()); j.close()
        self.path.write_text(self.path.read_text().replace('"kind":"SIGNAL"','"kind":"MARK"'))
        with self.assertRaisesRegex(ValueError,"HASH"): self.journal()
    def test_partial_write_recovery_fails_closed(self):
        j=self.journal(); j.append(event()); j.close()
        with self.path.open("ab") as f: f.write(b'{"torn"')
        before=self.path.read_bytes()
        with self.assertRaisesRegex(ValueError,"TORN"): self.journal()
        self.assertEqual(self.path.read_bytes(),before)
    def test_disk_full_poisoned(self):
        j=self.journal()
        with patch("os.fsync", side_effect=OSError(errno.ENOSPC,"full")):
            with self.assertRaises(OSError): j.append(event())
        with self.assertRaisesRegex(ValueError,"POISON"): j.append(event(n=2))
    def test_second_writer_rejected(self):
        j=self.journal()
        with self.assertRaises((OSError,ValueError)): self.journal()

class EngineTests(unittest.TestCase):
    setUp=JournalTests.setUp
    journal=JournalTests.journal
    def adapter(self):
        return ProspectiveEventAdapter(self.journal(), {("m","t"):fee()}, synthetic=True)
    def feed(self,a,kind,**payload):
        n=len(a.journal.records)+1
        e=event(kind,n); e.update(payload); old=copy.deepcopy(e)
        a.observe(e); self.assertEqual(e,old)
    def entry(self,a):
        self.feed(a,"SIGNAL")
        self.feed(a,"ENTRY_INTENT",notional="25")
        self.feed(a,"CASH_RESERVED",notional="25")
        self.feed(a,"ENTRY_BOOK",asks=[[".5","20"]],bids=[[".49","20"]],book_ts=4)
        self.feed(a,"ENTRY_PARTIAL_FILL",price=".5",qty="10",notional="5",fee=".17500")
    def test_partial_residual_fee_equity(self):
        a=self.adapter(); self.entry(a)
        self.assertEqual(a.ledger.positions["t"]["qty"],10)
        self.assertEqual(str(a.ledger.fees),"0.17500")
        self.feed(a,"CASH_RELEASED")
        self.feed(a,"EXIT_INTENT")
        self.feed(a,"EXIT_BOOK",asks=[[".5","20"]],bids=[[".49","20"]],book_ts=8)
        self.feed(a,"EXIT_PARTIAL_FILL",price=".49",qty="4",notional="1.96",fee=".06997")
        self.feed(a,"POSITION_RESIDUAL",qty="6")
        self.assertEqual(a.ledger.mark({})["status"],"UNRESOLVED_POSITION")
        m=a.ledger.mark({"t":".48"})
        self.assertEqual(m["equity"],m["initial"]+m["realized"]+m["unrealized"])
    def test_no_exit_survives_restart(self):
        a=self.adapter(); self.entry(a); self.feed(a,"CASH_RELEASED")
        self.feed(a,"EXIT_INTENT"); self.feed(a,"EXIT_NO_FILL")
        a.journal.close()
        b=ProspectiveEventAdapter(self.journal(),{("m","t"):fee()},synthetic=True)
        self.assertEqual(b.ledger.mark({})["unresolved"],["t"])
        self.assertEqual(b.tape.depth["t","BUY"][__import__("decimal").Decimal(".5")][1],10)
    def test_settlement(self):
        a=self.adapter(); self.entry(a); self.feed(a,"CASH_RELEASED")
        self.feed(a,"POSITION_SETTLED",payout=1,available_ts=7,source="synthetic")
        self.assertEqual(a.ledger.mark({})["status"],"COMPLETE")
        self.assertEqual(str(a.ledger.cash),"504.82500")
    def test_no_fill(self):
        a=self.adapter(); self.feed(a,"SIGNAL"); self.feed(a,"ENTRY_INTENT",notional="25")
        self.feed(a,"ENTRY_NO_FILL")
        self.assertEqual(a.ledger.cash,500)
    def test_callback_order(self):
        a=self.adapter()
        with self.assertRaisesRegex(ValueError,"ORDER"): self.feed(a,"ENTRY_INTENT",notional="25")
        self.assertEqual(len(a.journal.records),0)
    def test_exact_observed_fill_not_repriced(self):
        a=self.adapter(); self.entry(a)
        with self.assertRaisesRegex(ValueError,"LIQUIDITY"):
            self.feed(a,"ENTRY_FILL",price=".5",qty="11",fee=".19250",notional="5.5")
    def test_no_mutation_on_disk_failure(self):
        a=self.adapter()
        with patch("os.fsync",side_effect=OSError("full")):
            with self.assertRaises(OSError): self.feed(a,"SIGNAL")
        self.assertEqual(a.states,{})
    def test_real_fee_unknown_blocks(self):
        a=self.adapter(); a.synthetic=False
        with self.assertRaisesRegex(ValueError,"FEE"): self.feed(a,"SIGNAL")

class FeeTests(unittest.TestCase):
    def test_supported_fixture(self):
        f=fee(); self.assertEqual(f.qualification_status,"SYNTHETIC_ONLY")
        self.assertEqual(str(f.fee("50",".5")),"0.87500")
    def test_unknown_market_blocked(self):
        f=FeeQualification.from_evidence({},"t",source="",version="")
        self.assertEqual(f.qualification_status,"MARKET_FEE_UNQUALIFIED")
        with self.assertRaises(ValueError): f.fee(1,".5")
    def test_rounding_not_inferred(self):
        f=FeeQualification.from_evidence({"id":"m","clobTokenIds":["t"],"feesEnabled":True,
            "feeSchedule":{"rate":".07","exponent":1,"takerOnly":True}},"t",
            source="https://gamma-api.polymarket.com/markets/1",version="today")
        self.assertEqual(f.qualification_status,"MARKET_FEE_UNQUALIFIED")
    def test_rounding_tie(self):
        f=fee(); self.assertEqual(f.fee("0.002",".5"),__import__("decimal").Decimal(".00004"))

class SealedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); (self.root/"code").write_text("synthetic")
        self.seal=Seal.create(self.root,["code"])
        self.manifest={"synthetic":True,"session":"synthetic","start":0,"duration_hours":[72,48,48],
                       "embargo_ms":60000,"seal_hash":self.seal.hash,"markets":{"m":"TRAIN"}}
        write_once(self.root/"manifest.json",self.manifest)
        self.d=SealedDataset(self.root,self.root,self.seal,file_hash(self.root/"manifest.json"),synthetic=True)
    def partition(self,split):
        (self.root/(split+".jsonl")).write_bytes(b"")
        self.d.seal_partition(split,10**12)
    def test_train_seal_required(self):
        with self.assertRaises(ValueError): self.d.load("TRAIN")
    def test_train_fail_blocks_validation(self):
        self.partition("TRAIN"); self.d.load("TRAIN")
        self.d.gate.finish("TRAIN","FAIL",{})
        self.partition("VALIDATION")
        with self.assertRaises(ValueError): self.d.freeze("VALIDATION")
    def test_validation_fail_blocks_oos(self):
        self.partition("TRAIN"); self.d.load("TRAIN"); self.d.gate.finish("TRAIN","PASS",{})
        self.partition("VALIDATION"); self.d.freeze("VALIDATION"); self.d.load("VALIDATION")
        self.d.gate.finish("VALIDATION","FAIL",{})
        self.partition("OOS")
        with self.assertRaises(ValueError): self.d.freeze("OOS")
    def test_oos_access_crash_second_access(self):
        for split in ("TRAIN","VALIDATION"):
            self.partition(split)
            if split!="TRAIN": self.d.freeze(split)
            self.d.load(split); self.d.gate.finish(split,"PASS",{})
        self.partition("OOS"); self.d.freeze("OOS")
        self.assertEqual(self.d.load("OOS"),[])
        with self.assertRaises(FileExistsError): self.d.load("OOS")
    def test_dependency_hash_mismatch(self):
        self.partition("TRAIN"); (self.root/"code").write_text("changed")
        with self.assertRaisesRegex(ValueError,"HASH"): self.d.load("TRAIN")
    def test_manifest_mismatch(self):
        self.partition("TRAIN"); (self.root/"manifest.json").write_text("{}")
        with self.assertRaisesRegex(ValueError,"MANIFEST"): self.d.load("TRAIN")
    def test_closed_data_mutated(self):
        self.partition("TRAIN"); (self.root/"TRAIN.jsonl").write_text("{}")
        with self.assertRaisesRegex(ValueError,"HASH"): self.d.load("TRAIN")

class StatisticsStorageTests(unittest.TestCase):
    def test_deterministic_bootstrap(self):
        args=([(1,1)]*72,6,100,20260926,".025")
        self.assertEqual(confidence_bound(*args),1)
        self.assertEqual(confidence_bound(*args),confidence_bound(*args))
    def test_zero_denominator_inconclusive(self):
        self.assertIsNone(confidence_bound([(0,0)]*72,6,100,1,".025"))
    def test_insufficient_blocks(self):
        self.assertIsNone(confidence_bound([(1,1)]*6,12,100,1,".025"))
    def test_disk_estimate_real_units(self):
        s=storage_estimate(4800663552,"1320.0542836000677",48000000000)
        self.assertGreater(s["dataset_bytes"],2000000000000)
        self.assertIn("DISK_SPACE_INSUFFICIENT",s["reasons"])

class V1ObservabilityTests(unittest.TestCase):
    def test_original_hashes_unchanged(self):
        from .prepare import EXPECTED
        root=Path(__file__).resolve().parents[3]
        for name,wanted in EXPECTED.items():
            self.assertEqual(file_hash(root/name),wanted)
    def test_v1_loses_entry_observation_on_no_exit_depth(self):
        # Execute the unchanged AST of execute_signal on a synthetic event loop.
        # Do not import or run the real collector.
        import ast,asyncio,types
        root=Path(__file__).resolve().parents[3]
        tree=ast.parse((root/"analysis/run_d6_paper_live.py").read_text())
        functions=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
                   and n.name in ("fill","liquidate","execute_signal")]
        calls=[]; entry_calls=[]; latest={"5m":{"market_slug":"synthetic","up":{"asks":[[.5,100]],"bids":[[.49,100]]}}}
        class FakeLedger:
            portfolios={"FIXED25":types.SimpleNamespace(capital=500)}
            def sizes(self,x): return {"FIXED25":25}
            def record_skip(self,e):calls.append(("skip",e))
            def record_fill(self,*a):calls.append(("fill",a))
            def snapshot(self):pass
        sleeps=[]
        async def sleep(seconds):
            sleeps.append(seconds)
            if len(sleeps)==2:
                latest["5m"]={"market_slug":"synthetic","up":{"asks":[[.5,100]],"bids":[]}}
        env={"asyncio":types.SimpleNamespace(sleep=sleep),"a":types.SimpleNamespace(latency_ms=250,hold_ms=500),
             "latest":latest,"ledger":FakeLedger()}
        exec(compile(ast.Module(body=functions,type_ignores=[]),"<unchanged-v1-fixture>","exec"),env)
        original=env["fill"]
        def observed(*args):
            result=original(*args); entry_calls.append(result);return result
        env["fill"]=observed
        asyncio.run(env["execute_signal"](1,.001,"UP"))
        self.assertEqual(sleeps,[.25,.5])
        self.assertEqual(entry_calls[0][:2],(25.,50.))
        self.assertEqual([x[0] for x in calls],["skip"])
        self.assertEqual(calls[0][1]["reason"],"NO_EXIT_DEPTH")
    def test_v1_reuses_depth_on_repeated_fill(self):
        import ast
        root=Path(__file__).resolve().parents[3]
        tree=ast.parse((root/"analysis/run_d6_paper_live.py").read_text())
        f=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="fill")
        env={};exec(compile(ast.Module(body=[f],type_ignores=[]),"<unchanged-fill>","exec"),env)
        asks=[[.5,50]]
        self.assertEqual(env["fill"](asks,25),env["fill"](asks,25))
        self.assertEqual(asks,[[.5,50]])


class AdditionalTests(unittest.TestCase):
    setUp=JournalTests.setUp
    journal=JournalTests.journal
    adapter=EngineTests.adapter
    feed=EngineTests.feed
    entry=EngineTests.entry
    def test_fsync_crash_process_recovery(self):
        import subprocess,sys
        code="""import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from analysis.d6.prospective_v1.journal import DurableEventJournal
import json
j=DurableEventJournal(sys.argv[2],json.loads(sys.argv[3]))
j.append(json.loads(sys.argv[4]))
os._exit(17)
"""
        root=Path(__file__).resolve().parents[3]
        result=subprocess.run([sys.executable,"-B","-c",code,str(root),str(self.path),json.dumps(IDENTITY),json.dumps(event())],
                              capture_output=True,text=True)
        self.assertEqual(result.returncode,17,result.stderr)
        j=self.journal(); self.assertEqual(len(j.records),1)
    def test_short_write_detected_preserved(self):
        j=self.journal(); actual=j.file
        class ShortWriter:
            def write(self,data): return actual.write(data[:11])
            def close(self):actual.close()
        j.file=ShortWriter()
        with self.assertRaisesRegex(OSError,"PARTIAL_WRITE"):j.append(event())
        j.close()
        with self.assertRaisesRegex(ValueError,"TORN"):self.journal()
    def test_fee_annotation_no_double_debit(self):
        a=self.adapter();self.entry(a)
        before=a.ledger.cash
        self.feed(a,"FEE",fee=".17500",fill_event_id="5")
        self.assertEqual(before,a.ledger.cash)
        with self.assertRaisesRegex(ValueError,"FEE_REFERENCE"):
            self.feed(a,"FEE",fee=".17500",fill_event_id="5")
    def test_oversell_other_trade_rejected(self):
        a=self.adapter();self.entry(a)
        self.feed(a,"EXIT_INTENT")
        self.feed(a,"EXIT_BOOK",asks=[[".5","20"]],bids=[[".49","20"]],book_ts=7)
        with self.assertRaisesRegex(ValueError,"OVERSELL"):
            self.feed(a,"EXIT_FILL",price=".49",qty="11",notional="5.39",fee=".19242")
    def test_evaluator_unresolved_inconclusive(self):
        from .evaluator import evaluate
        a=self.adapter();self.entry(a);self.feed(a,"SESSION_END")
        criteria=json.loads(Path(__file__).with_name("criteria.json").read_text())
        r=evaluate(a,criteria,0,72*3600000,{k:True for k in criteria["data_gates"]},1,1)
        self.assertEqual(r["verdict"],"INCONCLUSIVE")
        self.assertEqual(r["economic_status"],"PARTITION_ECONOMIC_RESULT_INCOMPLETE")
    def test_evaluator_complete_accounting(self):
        from .evaluator import evaluate
        a=self.adapter();self.entry(a)
        # Every economic observation needs an equity mark at the same time.
        e=event("MARK",6);e.update(event_ts=5,decision_ts=5,source_ts=5,recv_ts=5,
                                  net_unit_marks={"t":".48"})
        a.observe(e)
        self.feed(a,"CASH_RELEASED")
        self.feed(a,"POSITION_SETTLED",payout=1,available_ts=8,source="synthetic")
        e=event("MARK",9);e.update(event_ts=8,decision_ts=8,source_ts=8,recv_ts=8,net_unit_marks={})
        a.observe(e);self.feed(a,"SESSION_END")
        criteria=json.loads(Path(__file__).with_name("criteria.json").read_text())
        r=evaluate(a,criteria,0,72*3600000,{k:True for k in criteria["data_gates"]},1,1)
        self.assertEqual(r["net_pnl"],__import__("decimal").Decimal("4.82500"))
        self.assertEqual(r["gross_pnl"],5)
        self.assertEqual(r["closed_trades"],1)
        self.assertEqual(r["verdict"],"INCONCLUSIVE") # fixed minima unchanged
        self.assertTrue(r["FULL_LEDGER_RECONCILIATION"])
    def test_t0_blocked_then_exact_boundaries(self):
        from .sealed import planned_boundaries
        with self.assertRaises(ValueError):planned_boundaries(123,False)
        b=planned_boundaries(123,True)
        self.assertEqual(b["T0"]%300000,0)
        self.assertEqual(b["OOS_END"]-b["T0"],168*3600000)
    def test_whole_market_purge_and_embargo(self):
        from .core import PartitionPlan
        p=PartitionPlan(0,(72*3600000,48*3600000,48*3600000),60000)
        end=72*3600000
        self.assertEqual(p.classify(end-300000,end,end-300250,end+500),"PURGED")
        self.assertEqual(p.classify(end,end+300000,end,end+300000),"PURGED")
        self.assertEqual(p.classify(end+300000,end+600000,end+299750,end+600000),"VALIDATION")
    def test_no_market_default_zero(self):
        f=FeeQualification.from_evidence({"id":"m","clobTokenIds":["t"],"feesEnabled":False},"t",
            source="https://gamma-api.polymarket.com/markets/m",version="synthetic")
        with self.assertRaises(ValueError):f.fee(1,".5")

class AdditionalSealTests(unittest.TestCase):
    setUp=SealedTests.setUp
    partition=SealedTests.partition
    def test_criteria_strategy_runner_mismatch(self):
        for name in ("criteria","strategy","runner"):
            with self.subTest(name=name):
                (self.root/name).write_text("before")
                sealed=Seal.create(self.root,[name]); (self.root/name).write_text("after")
                with self.assertRaisesRegex(ValueError,"HASH"): sealed.verify(self.root)
    def test_train_early_close(self):
        (self.root/"TRAIN.jsonl").write_bytes(b"")
        with self.assertRaisesRegex(ValueError,"NOT_CLOSED"): self.d.seal_partition("TRAIN",1)
    def test_freeze_tamper_blocks(self):
        self.partition("TRAIN");self.d.load("TRAIN");self.d.gate.finish("TRAIN","PASS",{})
        self.partition("VALIDATION");self.d.freeze("VALIDATION")
        (self.root/"VALIDATION_FREEZE.json").write_text("{}")
        with self.assertRaisesRegex(ValueError,"FREEZE"):self.d.load("VALIDATION")
        self.assertFalse((self.root/"VALIDATION_FIRST_ACCESS.json").exists())
    def test_parse_crash_consumes_access(self):
        (self.root/"TRAIN.jsonl").write_text("not-json\n")
        self.d.seal_partition("TRAIN",10**12)
        with self.assertRaises(ValueError):self.d.load("TRAIN")
        self.assertTrue((self.root/"TRAIN_FIRST_ACCESS.json").exists())
        with self.assertRaises(FileExistsError):self.d.load("TRAIN")
    def test_real_loader_unconditionally_fenced(self):
        with self.assertRaisesRegex(ValueError,"REAL_V1_BINDING"):
            SealedDataset(self.root,self.root,self.seal,file_hash(self.root/"manifest.json"),synthetic=False)

class EvaluatorDecisionTests(unittest.TestCase):
    def test_prespecified_green_then_negative_fails(self):
        from .evaluator import evaluate
        import types
        criteria=json.loads(Path(__file__).with_name("criteria.json").read_text())
        def fixture(sign):
            rows=[]; accounting=[]; cash=__import__("decimal").Decimal(500)
            for i in range(144):
                t=(i//2)*3600000+(i%2)*1000+1
                for kind in ("SIGNAL","ENTRY_FILL","EXIT_FILL","MARK"):
                    row=event(kind,len(rows)+1); row.update(event_ts=t,trade_id=str(i),market_id="m"+str(i))
                    delta=sign if kind=="EXIT_FILL" else 0
                    cash+=delta
                    rows.append(row);accounting.append({"event_ts":t,"kind":kind,"net_delta":delta,
                        "fee_delta":0,"equity":cash,"trade_closed":kind=="EXIT_FILL","open_qty":0})
            ledger=types.SimpleNamespace(positions={},reservations={},turnover=0,
                mark=lambda _:{"equity":cash})
            return types.SimpleNamespace(journal=types.SimpleNamespace(records=rows),
                accounting=accounting,ledger=ledger,marks={},ended=True)
        gates={k:True for k in criteria["data_gates"]}
        good=evaluate(fixture(1),criteria,0,72*3600000,gates,144,144)
        bad=evaluate(fixture(-1),criteria,0,72*3600000,gates,144,144)
        self.assertEqual(good["verdict"],"PASS")
        self.assertEqual(good["net_pnl"],144)
        self.assertEqual(good["net_without_best_market"],143)
        self.assertEqual(bad["verdict"],"FAIL")
        self.assertEqual(good["confidence_bound"],1)
    def test_real_data_cannot_be_substituted_for_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/"code").write_text("fixture")
            seal=Seal.create(root,["code"])
            write_once(root/"manifest.json",{"synthetic":False,"seal_hash":seal.hash,
                "duration_hours":[72,48,48],"embargo_ms":60000})
            with self.assertRaisesRegex(ValueError,"REAL_DATA"):
                SealedDataset(root,root,seal,file_hash(root/"manifest.json"),synthetic=True)

class LoaderEvaluatorIntegrationTests(unittest.TestCase):
    def test_loader_evaluator_consumes_and_persists_inconclusive(self):
        from .evaluator import evaluate_partition
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            criteria_path=root/"analysis/d6/prospective_v1/criteria.json"
            criteria_path.parent.mkdir(parents=True)
            criteria_path.write_bytes(Path(__file__).with_name("criteria.json").read_bytes())
            sealed=Seal.create(root,["analysis/d6/prospective_v1/criteria.json"])
            write_once(root/"manifest.json",{"synthetic":True,"session":"synthetic","start":0,
                "duration_hours":[72,48,48],"embargo_ms":60000,"seal_hash":sealed.hash,"markets":{}})
            (root/"TRAIN.jsonl").write_bytes(b"")
            loader=SealedDataset(root,root,sealed,file_hash(root/"manifest.json"),synthetic=True)
            loader.seal_partition("TRAIN",10**12)
            result=evaluate_partition(loader,"TRAIN",{}, {},1,0)
            self.assertEqual(result["verdict"],"INCONCLUSIVE")
            saved=json.loads((root/"TRAIN_RESULT.json").read_text())
            self.assertEqual(saved["verdict"],"INCONCLUSIVE")
            with self.assertRaises(FileExistsError):loader.load("TRAIN")
