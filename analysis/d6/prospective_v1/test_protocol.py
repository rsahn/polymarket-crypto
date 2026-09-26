"""Synthetic only: never imports a collector or opens historical data."""
import json, tempfile, unittest
from pathlib import Path
from decimal import Decimal as D
from analysis.d6.prospective_v1.core import (
    Ledger, FeePolicy, BookTape, Seal, PartitionPlan, AccessGate, digest, write_once,
)

class LedgerTests(unittest.TestCase):
    def policy(self):
        return FeePolicy("0.07", "official-fixture", "2026-09-26", "fixture-hash", True)
    def test_fee_reference(self):
        self.assertEqual(self.policy().fee("100", ".5"), D("1.75000"))
    def test_unknown_fee_blocks(self):
        with self.assertRaisesRegex(ValueError, "NET_EDGE_UNQUALIFIABLE"):
            FeePolicy("0.07", "", "", "", False).fee(10, ".5")
    def test_partial_multiple_fills_and_conservation(self):
        l=Ledger(self.policy()); l.reserve("a", "25")
        l.buy("f1", "a", "u", "10", ".5", 100)
        l.buy("f2", "a", "u", "10", ".6", 101)
        l.release("a")
        l.sell("f3", "u", "5", ".7", 102)
        x=l.mark({"u": ".5"})
        self.assertEqual(l.positions["u"]["qty"], D(15))
        self.assertEqual(x["equity"], x["initial"]+x["realized"]+x["unrealized"])
        self.assertGreater(x["fees"], 0)
    def test_no_fill_releases_cash(self):
        l=Ledger(self.policy());l.reserve("a",25);l.release("a")
        self.assertEqual(l.available, D(500))
    def test_no_exit_does_not_erase_entry(self):
        l=Ledger(self.policy());l.reserve("a",25);l.buy("x","a","u",10,".5",10);l.release("a")
        x=l.mark({})
        self.assertEqual(x["status"], "UNRESOLVED_POSITION")
        self.assertIsNone(x["equity"])
        self.assertEqual(l.positions["u"]["qty"],D(10))
    def test_settlement_and_duplicate(self):
        l=Ledger(self.policy());l.reserve("a",25);l.buy("x","a","u",10,".5",10);l.release("a")
        l.settle("s","u","1",20,20,"official-resolution")
        self.assertEqual(l.mark({})["status"],"COMPLETE")
        with self.assertRaises(ValueError):l.settle("s","u","1",20,20,"official-resolution")
    def test_future_and_out_of_order_rejected_without_mutation(self):
        l=Ledger(self.policy());l.reserve("a",25);l.buy("x","a","u",10,".5",10)
        before=(l.cash,dict(l.reservations),l.positions["u"].copy())
        with self.assertRaises(ValueError):l.buy("y","a","u",1,".5",9)
        self.assertEqual(before,(l.cash,l.reservations,l.positions["u"]))
        with self.assertRaises(ValueError):l.settle("s","u",1,11,12,"resolution")
    def test_duplicate_fill_and_reservation(self):
        l=Ledger(self.policy());l.reserve("a",25);l.buy("x","a","u",10,".5",10)
        with self.assertRaises(ValueError):l.buy("x","a","u",10,".5",11)
        with self.assertRaises(ValueError):l.reserve("a",25)
        with self.assertRaises(ValueError):l.reserve("b",500)
    def test_insufficient_cash_or_position(self):
        l=Ledger(self.policy());l.reserve("a",1)
        with self.assertRaises(ValueError):l.buy("x","a","u",10,".5",10)
        with self.assertRaises(ValueError):l.sell("s","u",1,".5",10)

class CausalTests(unittest.TestCase):
    def test_book_no_future_and_duplicate(self):
        b=BookTape()
        b.observe("e1","u",10,11,12,[[".5",10]],[[".4",10]])
        self.assertIsNone(b.at("u",11))
        self.assertEqual(b.at("u",12)["event_id"],"e1")
        with self.assertRaises(ValueError):b.observe("e1","u",10,11,12,[],[])
        with self.assertRaises(ValueError):b.observe("e2","u",15,14,14,[],[])
        with self.assertRaises(ValueError):b.observe("e3","u",9,10,11,[],[])
    def test_depth_not_refreshed_by_duplicate_snapshot(self):
        b=BookTape()
        b.observe("1","u",1,1,1,[[".5",10]],[[".4",10]])
        self.assertEqual(b.sweep("u","BUY",8,1),[(D(".5"),D(8))])
        b.observe("2","u",2,2,2,[[".5",10]],[[".4",10]])
        self.assertEqual(b.sweep("u","BUY",8,2),[(D(".5"),D(2))])
        b.observe("3","u",3,3,3,[[".5",12]],[[".4",10]])
        self.assertEqual(b.sweep("u","BUY",8,3),[(D(".5"),D(2))])

class ProtocolTests(unittest.TestCase):
    def test_partition_boundaries_purge_embargo(self):
        p=PartitionPlan(1000,(1000,1000,1000),60)
        self.assertEqual(p.classify(1000,1200,1000,1200),"TRAIN")
        self.assertEqual(p.classify(2060,2200,2060,2200),"VALIDATION")
        self.assertEqual(p.classify(3060,3200,3060,3200),"OOS")
        for row in [(1900,2100,1900,2100),(2000,2100,2000,2100),(3990,4010,3990,4010),(900,1200,900,1200)]:
            self.assertEqual(p.classify(*row),"PURGED")
    def test_hash_mismatches_and_post_freeze(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for name in ("strategy","runner","ledger","dataset"):
                (root/name).write_text(name)
            s=Seal.create(root,["strategy","runner","ledger","dataset"])
            s.verify(root)
            for name in ("strategy","runner","ledger","dataset"):
                (root/name).write_text("changed")
                with self.assertRaisesRegex(ValueError,"HASH_MISMATCH"):s.verify(root)
                (root/name).write_text(name)
    def test_write_once(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"manifest.json";write_once(p,{"frozen":True})
            with self.assertRaises(FileExistsError):write_once(p,{"frozen":False})
    def test_gate_order_fail_and_oos_rerun(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/"code").write_text("fixed")
            seal=Seal.create(root,["code"]);g=AccessGate(root/"access",root,seal,"dataset-sha")
            with self.assertRaises(ValueError):g.open("OOS","dataset-sha",{"cut":1})
            g.open("TRAIN","dataset-sha",{"cut":1});g.finish("TRAIN","PASS",{"metrics_hash":"t"})
            g.open("VALIDATION","dataset-sha",{"cut":1});g.finish("VALIDATION","PASS",{"metrics_hash":"v"})
            g.open("OOS","dataset-sha",{"cut":1});g.finish("OOS","PASS",{"metrics_hash":"o"})
            with self.assertRaises(FileExistsError):g.open("OOS","dataset-sha",{"cut":1})
    def test_failed_train_blocks_validation(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/"code").write_text("fixed")
            g=AccessGate(root/"access",root,Seal.create(root,["code"]),"data")
            g.open("TRAIN","data",{});g.finish("TRAIN","FAIL",{})
            with self.assertRaises(ValueError):g.open("VALIDATION","data",{})
    def test_dataset_hash_before_access_and_crash_consumes_access(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/"code").write_text("fixed")
            g=AccessGate(root/"access",root,Seal.create(root,["code"]),"data")
            with self.assertRaisesRegex(ValueError,"DATASET_HASH_MISMATCH"):g.open("TRAIN","bad",{})
            g.open("TRAIN","data",{})
            with self.assertRaises(FileExistsError):g.open("TRAIN","data",{})


class AdditionalGuards(unittest.TestCase):
    def test_flags_fail_closed(self):
        from unittest.mock import patch
        from analysis.d6.prospective_v1.core import safety
        for name in ("REAL_ORDERS_ENABLED","LIVE_EXECUTION_ARMED"):
            with patch.dict("os.environ",{name:"true"}):
                with self.assertRaisesRegex(ValueError,"LIVE_FORBIDDEN"):safety()
    def test_invalid_fills_do_not_mutate(self):
        l=Ledger(FeePolicy("0.07","fixture","v","hash",True));l.reserve("a",25)
        for q,p in [(0,".5"),(-1,".5"),(1,"NaN"),(1,"1.1")]:
            with self.assertRaises((ValueError,ArithmeticError)):l.buy("x","a","u",q,p,10)
            self.assertEqual(l.cash,D(500));self.assertFalse(l.events)
    def test_concurrent_exclusive_access(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/"code").write_text("fixed")
            g=AccessGate(root/"gate",root,Seal.create(root,["code"]),"data")
            def attempt(_):
                try:g.open("TRAIN","data",{});return True
                except FileExistsError:return False
            with ThreadPoolExecutor(max_workers=4) as pool:
                self.assertEqual(sum(pool.map(attempt,range(8))),1)
    def test_no_partial_state_on_bad_book(self):
        b=BookTape();b.observe("one","u",1,1,1,[[".5",5]],[[".4",5]])
        with self.assertRaises(ValueError):b.observe("two","u",2,2,2,[[".5",5]],[["2",5]])
        self.assertEqual(b.at("u",2)["event_id"],"one")
    def test_validation_failure_blocks_oos(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/"code").write_text("fixed")
            g=AccessGate(root/"access",root,Seal.create(root,["code"]),"data")
            g.open("TRAIN","data",{});g.finish("TRAIN","PASS",{})
            g.open("VALIDATION","data",{});g.finish("VALIDATION","FAIL",{})
            with self.assertRaises(ValueError):g.open("OOS","data",{})
    def test_changed_code_after_open_blocks_result(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/"code").write_text("fixed")
            g=AccessGate(root/"access",root,Seal.create(root,["code"]),"data");g.open("TRAIN","data",{})
            (root/"code").write_text("changed")
            with self.assertRaisesRegex(ValueError,"HASH_MISMATCH"):g.finish("TRAIN","PASS",{})
    def test_identity_guard_stops_preparation_before_output(self):
        from analysis.d6.prospective_v1.prepare import prepare
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/"analysis/d6/paper_live.py";p.parent.mkdir(parents=True);p.write_text("wrong")
            with self.assertRaisesRegex(ValueError,"STRATEGY_IDENTITY_CHANGED"):prepare(root,root/"analysis/d6/prospective_v1/evidence")
            self.assertFalse((root/"analysis/d6/prospective_v1/evidence").exists())
    def test_pnl_positive_alone_is_not_pass(self):
        from analysis.d6.prospective_v1.core import qualification
        c=json.loads((Path(__file__).parent/"criteria.json").read_text())
        self.assertEqual(qualification({"net_pnl":100},c),"INCONCLUSIVE")
        s={g:True for g in c["data_gates"]}
        s.update(opportunities=100,filled_entries=100,markets_with_fills=50,active_6h_blocks=8,coverage=1,
                 gross_pnl=10,net_pnl=8,net_without_best_market=2,expectancy_lower=".01",
                 expectancy_lower_sensitivity=".01",max_drawdown_fraction=".1")
        self.assertEqual(qualification(s,c),"PASS")
        s["expectancy_lower"]="-0.1";self.assertEqual(qualification(s,c),"FAIL")
        s["filled_entries"]=1;self.assertEqual(qualification(s,c),"INCONCLUSIVE")

if __name__=="__main__":unittest.main()
