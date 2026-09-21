import unittest,tempfile,sqlite3
from pathlib import Path
from contextlib import closing
from app.d5.store import Store
from app.d5.identity import MarketIdentity
from app.d5.quality51 import supplement
from test_d5 import snapshot

class GapEvidenceTests(unittest.TestCase):
    def check(self,duration,verified):
        interval=300000 if duration=='5m' else 900000
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'new.db';store=Store(path,compress_payloads=True)
            a=MarketIdentity(duration,'old','ca','ua','da',interval)
            b=MarketIdentity(duration,'new','cb','ub','db',2*interval)
            for m in (a,b):store.market(m,{})
            for m,t,g in [(a,interval-1000,1),(b,interval+5000,2)]:
                if m==b and verified:store.event('ROTATION',{'previous_slug':'old','next_slug':'new'},received_ts_ms=interval,available_ts_ms=interval)
                store.event('ACTIVATE',{},identity=m,generation=g,received_ts_ms=t,available_ts_ms=t)
                s=snapshot(m,t,timestamp_contract='D5.1',wire_event_ts_ms=t,book_state_source_ts_ms=t,source_metadata=[{'timestamp':t}])
                for side in ('up','down'):s[side]['received_ts_ms']=t
                store.book(s,m,g,t)
            sid=store.session_id;store.close()
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:r=supplement(db,sid,interval-1000,interval+5000)
            transitions=[x for x in r['gaps'] if x['kind']=='TRANSITION_GAP']
            self.assertEqual(len(transitions),1);self.assertEqual(transitions[0]['gap_ms'],6000)
            self.assertEqual(transitions[0]['transition_verified'],verified)
            self.assertEqual(transitions[0]['failure'],None if verified else 'UNVERIFIED_TRANSITION')
            self.assertNotIn('SQL_SIDE_METADATA_MISMATCH',r['failures'])
    def test_expiry_rotation_evidence_5m(self):self.check('5m',True)
    def test_expiry_rotation_evidence_15m(self):self.check('15m',True)
    def test_changed_slug_without_rotation_evidence_is_not_excused(self):self.check('5m',False)
