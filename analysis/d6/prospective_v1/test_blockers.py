import json,os,sqlite3,tempfile,unittest,zlib
from pathlib import Path
from .storage_audit import physical_pages,breakdown

class StorageAuditTests(unittest.TestCase):
    def test_physical_pages_including_overflow_and_indexes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"new.db";c=sqlite3.connect(p)
            c.execute("create table x(id integer primary key, value blob)")
            c.execute("create index ix on x(value)")
            c.executemany("insert into x(value) values(?)",[(os.urandom(6000),) for _ in range(100)])
            c.commit();c.close()
            r=physical_pages(p)
            self.assertEqual(r["by_object"]["UNATTRIBUTED"],0)
            self.assertEqual(sum(r["by_object"].values()),p.stat().st_size)
            self.assertGreater(r["by_object"]["x"],0);self.assertGreater(r["by_object"]["ix"],0)

from .archive_codec import Codec,ArchiveWriter,stream_archive,row_fingerprint
from unittest.mock import patch

class ArchiveTests(unittest.TestCase):
    def test_lossless_values(self):
        c=Codec()
        values=[None,0,2**62,-0.,1.23456789012345,"ÃƒÆ’Ã‚Â©",b"raw",
                zlib.compress(b'{"book":[[0.5,23]]}',1),zlib.compress(b"other",9)]
        for v in values:
            self.assertEqual(row_fingerprint("x",[v]),row_fingerprint("x",[c.decode(c.encode(v))]))
    def test_streaming_roundtrip_and_bounded_cache(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"new.pva";w=ArchiveWriter(p);c=Codec(limit=4096)
            for i in range(2000):w.append(["x",[i,c.encode(zlib.compress(str(i).encode(),1))]])
            w.close()
            count=0
            for table,row in stream_archive(p):
                self.assertEqual(c.decode(row[1]),zlib.compress(str(row[0]).encode(),1));count+=1
            self.assertEqual(count,2000);self.assertLessEqual(c.cache_bytes,4096)
    def test_corruption_and_partial_write(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"new.pva";w=ArchiveWriter(p);w.append(["x",[1]]);w.close()
            p.write_bytes(p.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError,"TORN"):list(stream_archive(p))
    def test_disk_full_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"new.pva";w=ArchiveWriter(p);w.append(["x",[1]])
            with patch("os.fsync",side_effect=OSError("disk full")):
                with self.assertRaises(OSError):w.flush()
            self.assertTrue(w.poisoned);w.close()
            with self.assertRaisesRegex(ValueError,"TORN"):list(stream_archive(p))

import ast,asyncio,types
from .observability_v2 import observed_tree,strip_observations,ObservationRecorder,revision_hash

class ObservabilityTests(unittest.TestCase):
    def source(self):
        return (Path(__file__).resolve().parents[3]/"analysis/run_d6_paper_live.py").read_text()
    def test_only_added_observations_structurally(self):
        old=ast.parse(self.source());new=observed_tree(self.source())
        self.assertEqual(ast.dump(old,include_attributes=False),
                         ast.dump(strip_observations(new),include_attributes=False))
    def run_fixture(self,instrumented,mode):
        source=self.source();tree=observed_tree(source) if instrumented else ast.parse(source)
        functions=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
                   and n.name in ("fill","liquidate","execute_signal")]
        latest={"5m":{"market_slug":"same","up":{"asks":[[.5,30],[.6,20]],"bids":[[.49,100]]}}}
        log=[];sleep_log=[];recorder=ObservationRecorder()
        class Ledger:
            portfolios={"FIXED25":types.SimpleNamespace(capital=500)}
            def sizes(self,x):return {"FIXED25":25}
            def record_skip(self,x):log.append(("skip",x))
            def record_fill(self,*x):log.append(("fill",x))
            def snapshot(self):log.append(("snapshot",))
        async def sleep(seconds):
            sleep_log.append(seconds)
            if len(sleep_log)==2:
                if mode=="no_exit":latest["5m"]["up"]["bids"]=[]
                elif mode=="partial":latest["5m"]["up"]["bids"]=[[.49,10]]
                elif mode=="rotation":latest["5m"]["market_slug"]="changed"
        env={"a":types.SimpleNamespace(latency_ms=250,hold_ms=500),
             "asyncio":types.SimpleNamespace(sleep=sleep),"ledger":Ledger(),"latest":latest,
             "_prospective_observe":recorder}
        exec(compile(ast.Module(body=functions,type_ignores=[]),"<differential-v1>","exec"),env)
        asyncio.run(env["execute_signal"](1,.001,"UP"))
        return log,sleep_log,recorder
    def test_differential_normal_partial_no_exit_rotation(self):
        for mode in ("normal","partial","no_exit","rotation"):
            with self.subTest(mode=mode):
                old=self.run_fixture(False,mode);new=self.run_fixture(True,mode)
                self.assertEqual(old[:2],new[:2])
                self.assertFalse(new[2].failed)
                self.assertTrue(any(x["kind"]=="ENTRY_RESULT" for x in new[2].events))
    def test_entry_now_visible_on_no_exit_depth(self):
        _,_,r=self.run_fixture(True,"no_exit")
        kinds=[x["kind"] for x in r.events]
        self.assertLess(kinds.index("ENTRY_RESULT"),kinds.index("SKIP"))
        self.assertEqual(next(x for x in r.events if x["kind"]=="ENTRY_RESULT")["payload"]["cost"],25)
    def test_snapshot_does_not_alias_v1(self):
        r=ObservationRecorder();p={"depth":[[.5,2]]};r("BOOK",p)
        p["depth"][0][1]=0
        self.assertEqual(r.events[0]["payload"]["depth"][0][1],2)
    def test_overflow_does_not_change_economics(self):
        r=ObservationRecorder(1);r("a",{});r("b",{})
        self.assertTrue(r.failed);self.assertEqual(len(r.events),1)

from .fee_diagnostics import diagnose_market,ambiguity_example
from .core import BookTape,dec
from .engine import FeeQualification

class FeeEvidenceTests(unittest.TestCase):
    def test_both_tokens_and_unknown_rounding_stay_blocked(self):
        g={"id":"m","conditionId":"c","clobTokenIds":["u","d"],"feesEnabled":True,
           "feeSchedule":{"rate":".07","exponent":1,"takerOnly":True}}
        c={"c":"c","v":"v1","fd":{"r":".07","e":1,"to":True},"t":[{"t":"u"},{"t":"d"}]}
        rows=diagnose_market(g,c,"https://gamma-api.polymarket.com/markets/m","fixture")
        self.assertEqual(len(rows),2)
        self.assertTrue(all(x["public_sources_agree"] for x in rows))
        self.assertTrue(all(x["qualification_status"]=="MARKET_FEE_UNQUALIFIED" for x in rows))
    def test_partial_multiple_fill_ambiguity_is_not_qualification(self):
        r=ambiguity_example()
        self.assertNotEqual(r["two_fills_round_each_half_even"],r["two_fills_aggregate_then_half_even"])
        self.assertEqual(r["production_rule"],"UNPROVEN")
    def test_never_zero_fallback(self):
        f=FeeQualification.from_evidence({},"unknown",source="",version="")
        with self.assertRaisesRegex(ValueError,"UNQUALIFIED"):f.fee(1,".5")
    def test_sdk_provision_formula_is_not_match_rounding(self):
        from decimal import Decimal
        import polymarket
        p=Path(polymarket.__file__).parent/"_internal/actions/orders/market.py"
        tree=ast.parse(p.read_text(encoding="utf-8"))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="adjust_buy_amount_for_fees")
        env={"Decimal":Decimal,"PlatformFeeInfo":object}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),"<official-sdk-pure-function>","exec"),env)
        for q in ("0.002","0.004","50"):
            amount=Decimal(q)*Decimal(".5")
            actual=env["adjust_buy_amount_for_fees"](amount=amount,price=Decimal(".5"),
                max_spend=amount,fee=types.SimpleNamespace(rate=Decimal(".07"),exponent=1))
            self.assertEqual(actual,amount/(1+Decimal(".07")*Decimal(".5")))
        # No client, network, order signing or posting is instantiated.

class PersistentDepthTests(unittest.TestCase):
    def test_multiple_opportunities_same_observation_partial_remaining_recovery(self):
        observations=[("a","t",1,1,1,[[.5,10]],[[.49,10]]),
                      ("b","t",2,2,2,[[.5,10]],[[.49,10]])]
        tape=BookTape();tape.observe(*observations[0])
        first=tape.sweep("t","BUY",6,1)
        tape.observe(*observations[1]);second=tape.sweep("t","BUY",6,2)
        self.assertEqual(first,[(dec(".5"),dec(6))]);self.assertEqual(second,[(dec(".5"),dec(4))])
        restored=BookTape();restored.observe(*observations[0]);restored.sweep("t","BUY",6,1)
        restored.observe(*observations[1]);restored.sweep("t","BUY",4,2)
        self.assertEqual(restored.depth,tape.depth)
        self.assertEqual(restored.sweep("t","BUY",25,2),[])

class SignalDifferentialTests(unittest.TestCase):
    def run_signals(self,instrumented):
        from collections import deque
        source=(Path(__file__).resolve().parents[3]/"analysis/run_d6_paper_live.py").read_text()
        tree=observed_tree(source) if instrumented else ast.parse(source)
        callback=next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=="on_btc")
        wrapper=ast.parse("def bind():\n last_signal=-10**18\n return None").body[0]
        wrapper.body[-1:]=[callback,ast.parse("return on_btc").body[0]]
        signals=[];executions=[];pending=set();recorder=ObservationRecorder()
        async def execute_signal(*args):executions.append(args)
        env={"btc":deque(maxlen=4096),"ledger":types.SimpleNamespace(record_signal=lambda x:signals.append(x)),
             "dryrun":None,"staged":None,"latest":{},"pending":pending,"asyncio":asyncio,
             "execute_signal":execute_signal,"_prospective_observe":recorder}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper],type_ignores=[])),"<signals-differential>","exec"),env)
        cb=env["bind"]()
        async def run():
            for ts,price in [(0,100),(100,100.01),(200,100.1),(300,99),(1200,100),(1300,99.9),(1400,100.5),(2400,100),(2500,100.1)]:
                await cb(types.SimpleNamespace(recv_ts_ms=ts,price=price))
                await asyncio.sleep(0)
            if pending:await asyncio.gather(*pending)
        asyncio.run(run())
        return signals,executions,recorder
    def test_signal_direction_order_cooldown_equivalence(self):
        old=self.run_signals(False);new=self.run_signals(True)
        self.assertEqual(old[:2],new[:2])
        self.assertEqual([s["side"] for s in new[0]],["UP","DOWN","UP"])
        self.assertEqual([x["payload"]["signal_ts"] for x in new[2].events if x["kind"]=="SIGNAL"],[200,1300,2500])

class DurableDepthBlockerTests(unittest.TestCase):
    def test_same_book_multiple_opportunities_restart_rejects_reuse(self):
        from .test_harness import event,fee,IDENTITY
        from .journal import DurableEventJournal
        from .engine import ProspectiveEventAdapter
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as d, ExitStack() as cleanup:
            p=Path(d)/"synthetic.jsonl";j=DurableEventJournal(p,IDENTITY);cleanup.callback(j.close)
            a=ProspectiveEventAdapter(j,{("m","t"):fee()},synthetic=True)
            def emit(kind,trade,**kw):
                e=event(kind,len(a.journal.records)+1);e.update(trade_id=trade,**kw);a.observe(e)
            for trade,qty in (("first","6"),("second","4")):
                emit("SIGNAL",trade);emit("ENTRY_INTENT",trade,notional="25")
                emit("CASH_RESERVED",trade,notional="25")
                emit("ENTRY_BOOK",trade,book_ts=1,asks=[[".5","10"]],bids=[[".49","10"]])
                emit("ENTRY_PARTIAL_FILL",trade,qty=qty,price=".5",
                    notional=str(dec(qty)*dec(".5")),fee=str(fee().fee(qty,".5")))
            j.close();j=DurableEventJournal(p,IDENTITY);cleanup.callback(j.close)
            a=ProspectiveEventAdapter(j,{("m","t"):fee()},synthetic=True)
            emit("SIGNAL","third");emit("ENTRY_INTENT","third",notional="25")
            emit("ENTRY_BOOK","third",book_ts=1,asks=[[".5","10"]],bids=[[".49","10"]])
            n=len(j.records)
            try:
                with self.assertRaisesRegex(ValueError,"PERSISTENT_LIQUIDITY"):
                    emit("ENTRY_FILL","third",qty="1",price=".5",notional=".5",fee=".01750")
                self.assertEqual(len(j.records),n)
                self.assertEqual(a.tape.depth["t","BUY"][dec(".5")][1],0)
            finally:j.close()

class SmokeTests(unittest.TestCase):
    def test_complete_technical_smoke_preserves_source(self):
        from .storage_smoke import smoke
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"source.db";c=sqlite3.connect(p)
            c.execute("create table x(id integer primary key, payload blob)")
            c.executemany("insert into x(payload) values(?)",[(zlib.compress(b"same book",1),)]*50)
            c.commit();c.close()
            original=p.read_bytes()
            r=smoke(p,Path(d)/"output",22)
            self.assertEqual(r["logical_input_sha256"],r["replayed_sha256"])
            self.assertEqual(r["rows"],50);self.assertEqual(p.read_bytes(),original)
            self.assertEqual(r["storage_status"],"STORAGE_UNQUALIFIED")
            self.assertFalse(r["partition_opened"])
