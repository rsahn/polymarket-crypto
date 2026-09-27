
"""Additional round-trip contracts; fixtures only, no real partition or feed."""
import ast,json,tempfile,unittest
from contextlib import ExitStack
from pathlib import Path
from .archive_codec import ArchiveWriter,Codec,stream_archive
from .core import digest,encode,dec
from .engine import FeeQualification,ProspectiveEventAdapter
from .journal import DurableEventJournal
from .test_harness import event,fee,IDENTITY

def complete_synthetic_journal(path):
    j=DurableEventJournal(path,IDENTITY)
    try:
        a=ProspectiveEventAdapter(j,{("m","t"):fee()},synthetic=True)
        def emit(kind,**kw):
            e=event(kind,len(j.records)+1);e.update(kw);a.observe(e);return e["event_id"]
        emit("SIGNAL");emit("ENTRY_INTENT",notional="25");emit("CASH_RESERVED",notional="25")
        levels=dict(asks=[[".5","20"],[".6","10"]],bids=[[".49","20"],[".48","10"]],book_ts=4)
        emit("ENTRY_BOOK",**levels)
        for qty,price in (("6",".5"),("4",".6")):
            charged=str(fee().fee(qty,price))
            fill_id=emit("ENTRY_PARTIAL_FILL",qty=qty,price=price,notional=str(dec(qty)*dec(price)),fee=charged)
            emit("FEE",fill_event_id=fill_id,fee=charged)
        emit("CASH_RELEASED");emit("POSITION_OPEN",qty="10")
        emit("MARK",net_unit_marks={"t":".48"});emit("EXIT_INTENT")
        emit("EXIT_BOOK",**levels)
        emit("EXIT_PARTIAL_FILL",qty="4",price=".49",notional="1.96",fee=str(fee().fee("4",".49")))
        emit("EXIT_NO_FILL");emit("POSITION_RESIDUAL",qty="6")
        emit("MARK",net_unit_marks={"t":".47"})
        emit("POSITION_SETTLED",payout="1",source="SYNTHETIC_CONFIRMED_RESOLUTION",available_ts=1)
        emit("MARK",net_unit_marks={});emit("SESSION_END")
        return snapshot(a),j.records
    finally:j.close()

def snapshot(a):
    depth=[[token,side,str(price),str(visible),str(remaining)]
           for (token,side),levels in sorted(a.tape.depth.items())
           for price,(visible,remaining) in sorted(levels.items())]
    return dict(mark=a.ledger.mark(a.marks),fills=a.ledger.events,states=a.states,
        accounting=a.accounting,books=a.tape.books,depth=depth,ended=a.ended,
        fee_annotations=sorted(a.fee_annotations))

def roundtrip(directory):
    directory=Path(directory);source=directory/"synthetic_source.jsonl"
    before,records=complete_synthetic_journal(source)
    archive=directory/"synthetic.pva";c=Codec();w=ArchiveWriter(archive)
    try:
        with source.open("rb") as f:
            for line in f:w.append(["journal",[c.encode(line)]])
    finally:w.close()
    restored=directory/"synthetic_restored.jsonl";decoder=Codec()
    with restored.open("xb") as f:
        for table,row in stream_archive(archive):
            if table!="journal":raise ValueError("WRONG_TABLE")
            f.write(decoder.decode(row[0]))
    with ExitStack() as cleanup:
        j=DurableEventJournal(restored,IDENTITY);cleanup.callback(j.close)
        recovered=ProspectiveEventAdapter(j,{("m","t"):fee()},synthetic=True)
        after=snapshot(recovered)
        if source.read_bytes()!=restored.read_bytes():raise ValueError("JOURNAL_BYTES_CHANGED")
        if records!=j.records or digest(before)!=digest(after):raise ValueError("LEDGER_ROUNDTRIP")
    return dict(status="SYNTHETIC_JOURNAL_LEDGER_ROUNDTRIP_PASS",events=len(records),
        before_sha256=digest(before),after_sha256=digest(after),journal_sha256=__import__("hashlib").sha256(source.read_bytes()).hexdigest(),
        raw_journal_bytes=source.stat().st_size,archive_bytes=archive.stat().st_size,
        timestamps_partition_identity_order_books_fills_fees_residuals_preserved=True,
        final_ledger=before["mark"],final_depth=before["depth"],production_fee_qualified=False,
        real_partition_opened=False)

class CompleteRoundtripTests(unittest.TestCase):
    def test_events_books_multilevel_fills_fees_residual_settlement_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            r=roundtrip(d)
            self.assertEqual(r["before_sha256"],r["after_sha256"])
            self.assertEqual(r["final_ledger"]["status"],"COMPLETE")
            self.assertEqual(r["final_ledger"]["reserved"],0)
            self.assertGreater(r["final_ledger"]["fees"],0)
            self.assertEqual(r["events"],20)
            self.assertFalse(r["production_fee_qualified"])

class FeeBoundaryContracts(unittest.TestCase):
    def test_real_market_both_tokens_all_boundaries_block_without_exact_rule(self):
        path=Path(__file__).parent/"evidence/blockers_20260926/FEE_SOURCE_AUDIT.json"
        evidence=json.loads(path.read_text());market=evidence["requests"][0]
        for token in json.loads(market["data"]["clobTokenIds"]):
            f=FeeQualification.from_evidence(market["data"],token,source=market["url"],
                version=evidence["retrieved_at"])
            for qty,price in (("50",".5"),(".002",".5"),(".004",".5"),("6",".49"),("4",".51"),("1",".01"),("1",".99")):
                with self.subTest(token=token,qty=qty,price=price):
                    self.assertEqual(f.qualification_status,"MARKET_FEE_UNQUALIFIED")
                    with self.assertRaisesRegex(ValueError,"MARKET_FEE_UNQUALIFIED"):f.fee(qty,price)

class DepthCompatibilityContracts(unittest.TestCase):
    def test_unchanged_v1_fills_conflict_with_persistent_depth_contract(self):
        from .core import BookTape
        source=(Path(__file__).resolve().parents[3]/"analysis/run_d6_paper_live.py").read_text()
        fn=next(n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.FunctionDef) and n.name=="fill")
        env={};exec(compile(ast.Module(body=[fn],type_ignores=[]),"<unchanged-v1-fill>","exec"),env)
        book=[[.5,50]]
        first=env["fill"](book,25);second=env["fill"](book,25)
        self.assertEqual(first,second);self.assertEqual(first[1],50);self.assertEqual(book,[[.5,50]])
        tape=BookTape();tape.observe("one","t",1,1,1,book,[])
        self.assertEqual(tape.sweep("t","BUY",50,1),[(dec(".5"),dec(50))])
        tape.observe("two","t",2,2,2,book,[])
        self.assertEqual(tape.sweep("t","BUY",50,2),[])
        # Both contracts cannot produce identical accepted second fills.
        # No silent resizing, dropping or fabricated replenishment is allowed.
