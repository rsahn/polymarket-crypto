"""Only three-blocker diagnostics; all journals synthetic, no real partitions."""
import json,sqlite3,tempfile,unittest
from pathlib import Path
from .core import digest,encode
from .depth_empirical import relation,summarize
from .journal import DurableEventJournal,read_journal
from .streaming_replay import stream_journal,replay_stream,DiskIds
from .test_harness import IDENTITY,fee,event
from .test_blocker_contracts import complete_synthetic_journal,snapshot

class DepthEvidenceTests(unittest.TestCase):
    def test_same_metadata_not_proof_of_no_intervening_event(self):
        r=dict(token='t',source_ts=1,receive_ts=2,generation=1,source_hash='h',sequence=None)
        self.assertEqual(relation(r,r),'C')
        for k,v in [('source_ts',2),('source_hash','new'),('generation',2)]:
            with self.subTest(k=k):self.assertEqual(relation(r,{**r,k:v}),'B')
    def test_token_and_unknown_isolation(self):
        r=dict(token='t',source_ts=1,receive_ts=2,generation=1)
        self.assertEqual(relation(r,{**r,'token':'other'}),'C')
        self.assertEqual(relation(r,{**r,'source_ts':None}),'C')
    def test_unknown_never_zero_reuse_rate_or_overlap(self):
        r=summarize([dict(book_identity=None,entry_decision_ts=None)])
        self.assertIsNone(r['same_book_reuse_rate']);self.assertEqual(r['unknown_cases'],1)
        self.assertIsNone(r['overlapping_lifetime_count'])

class StreamingTests(unittest.TestCase):
    def test_full_economic_equivalence_and_open_prefixes(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);path=d/'source.jsonl';before,rows=complete_synthetic_journal(path)
            for end in [8,16,20]:
                with self.subTest(prefix=end):
                    part=d/f'part{end}.jsonl';part.write_text(''.join(encode(x)+'\n' for x in rows[:end]))
                    from .engine import ProspectiveEventAdapter
                    from types import SimpleNamespace
                    reference=ProspectiveEventAdapter(SimpleNamespace(records=read_journal(part,IDENTITY)),{('m','t'):fee()},synthetic=True)
                    actual,meta=replay_stream(part,IDENTITY,{('m','t'):fee()},d/f'idx{end}.db',synthetic=True)
                    self.assertEqual(digest(snapshot(reference)),digest(snapshot(actual)))
                    self.assertEqual(meta['last_hash'],rows[end-1]['event_hash'])
                    self.assertFalse(meta['economic_state_bounded'])
    def test_invalid_chain_partition_torn_and_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);source=d/'source';_,rows=complete_synthetic_journal(source)
            variants={}
            corrupt=json.loads(json.dumps(rows));corrupt[1]['fee']='1';variants['hash']=corrupt
            wrong=json.loads(json.dumps(rows));wrong[1]['partition']='OOS';variants['partition']=wrong
            dup=json.loads(json.dumps(rows[:2]));dup[1]['event_id']=dup[0]['event_id'];dup[1]['event_hash']=digest({k:v for k,v in dup[1].items() if k!='event_hash'});variants['duplicate']=dup
            for name,value in variants.items():
                with self.subTest(name=name):
                    p=d/name;p.write_text(''.join(encode(x)+'\n' for x in value))
                    with self.assertRaises(ValueError):list(stream_journal(p,IDENTITY,d/(name+'.db')))
            p=d/'torn';p.write_text(encode(rows[0]))
            with self.assertRaises(ValueError):list(stream_journal(p,IDENTITY,d/'torn.db'))
    def test_disk_ids_match_numeric_set_equality(self):
        db=sqlite3.connect(':memory:');db.execute('create table ids(id text primary key)')
        try:
            ids=DiskIds(db);ids.add(1)
            self.assertIn(True,ids);self.assertIn(1.0,ids);self.assertNotIn('1',ids)
        finally:db.close()
    def test_scratch_is_exclusive(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'existing';p.write_bytes(b'preserve')
            with self.assertRaises(FileExistsError):list(stream_journal('missing',IDENTITY,p))
            self.assertEqual(p.read_bytes(),b'preserve')
    def test_schema_has_no_finite_serialized_size_bound(self):
        with tempfile.TemporaryDirectory() as d:
            j=DurableEventJournal(Path(d)/'j',IDENTITY)
            try:
                e=event('MARK',1);e.update(net_unit_marks={},diagnostic='x'*1048576)
                row=j.append(e);self.assertGreater(len(encode(row)),1048576)
            finally:j.close()
            rows=list(stream_journal(Path(d)/'j',IDENTITY,Path(d)/'idx'))
            self.assertEqual(rows,[row])


class PipelineSemanticsTests(unittest.TestCase):
    def test_price_change_is_absolute_and_other_token_unchanged(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'backend'))
        from app.collectors.polymarket_ws import PolymarketOrderbookCollector
        c=PolymarketOrderbookCollector('5m',{'UP':'u','DOWN':'d'},lambda *_:None,timestamp_contract='D5.1')
        first=c.normalize_snapshot([dict(event_type='book',asset_id=t,timestamp='1700000000000',hash=t,
            bids=[dict(price='.4',size='50')],asks=[dict(price='.5',size='50')]) for t in ['u','d']])
        nextbook=c.normalize_snapshot(dict(event_type='price_change',timestamp='1700000000100',
            price_changes=[dict(asset_id='u',side='SELL',price='.5',size='50',hash='u2')]))
        self.assertEqual(first['up']['asks'],nextbook['up']['asks'])
        self.assertEqual(first['down'],nextbook['down'])
        self.assertNotEqual(first['up']['source_hash'],nextbook['up']['source_hash'])
        changed=c.normalize_snapshot(dict(event_type='price_change',timestamp='1700000000200',
            price_changes=[dict(asset_id='u',side='SELL',price='.5',size='20',hash='u3')]))
        self.assertEqual(changed['up']['asks'],[(.5,20.)])
    def test_aggregate_ceiling_not_bound_for_multiple_rounded_matches(self):
        from decimal import Decimal as D,ROUND_HALF_UP,ROUND_CEILING
        raw=D('.002')*D('.07')*D('.5')*D('.5');unit=D('.00001')
        per_match=2*raw.quantize(unit,rounding=ROUND_HALF_UP)
        aggregate=(2*raw).quantize(unit,rounding=ROUND_CEILING)
        self.assertGreater(per_match,aggregate)
        # Conditional error bound requires known number N of rounding operations.
        self.assertLessEqual(per_match,2*raw+2*unit)
