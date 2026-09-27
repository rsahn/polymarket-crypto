"""Closure delta: synthetic only, no strategy, collection or real partition."""
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from .core import digest,encode,dec
from .engine import ProspectiveEventAdapter
from .journal import read_journal
from .disk_replay import replay_disk,materialize,Store,DiskMap,DiskSet,DiskBooks,DiskList
from .test_harness import IDENTITY,fee,event
from .test_blocker_contracts import complete_synthetic_journal,snapshot


def chain(events):
    previous='0'*64
    for i,e in enumerate(events):
        e=dict(e); e.update(IDENTITY,sequence=i,previous_event_hash=previous)
        e['event_hash']=digest(e); previous=e['event_hash']; yield e


def write_rows(p,rows):
    with Path(p).open('x',encoding='utf-8') as f:
        for row in rows: f.write(encode(row)+'\n')


class DiskRecoveryTests(unittest.TestCase):
    def compare(self,d,rows,label):
        p=d/(label+'.jsonl');write_rows(p,rows)
        reference=ProspectiveEventAdapter(SimpleNamespace(records=read_journal(p,IDENTITY)),{('m','t'):fee()},synthetic=True)
        a,m,s=replay_disk(p,IDENTITY,{('m','t'):fee()},d/(label+'.db'),d/(label+'-ids.db'),synthetic=True)
        try:
            self.assertEqual(digest(snapshot(reference)),digest(materialize(a)))
            self.assertEqual(m['last_sequence'],len(rows)-1)
            self.assertEqual(m['last_hash'],rows[-1]['event_hash'] if rows else '0'*64)
            self.assertEqual(m['identity'],IDENTITY)
            with self.assertRaisesRegex(ValueError,'OFFLINE'): a.observe(event())
        finally:s.close()
    def test_complete_prefixes_partial_fees_and_restart(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);_,rows=complete_synthetic_journal(d/'fixture')
            for n in [0,4,8,14,16,18,20]:
                with self.subTest(n=n):self.compare(d,rows[:n],str(n))
            self.compare(d,rows,'restart-from-source')
    def test_old_book_asof_and_delayed_fee_reference(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);_,rows=complete_synthetic_journal(d/'fixture')
            plain=[{k:v for k,v in r.items() if k not in ('event_hash','previous_event_hash','sequence')} for r in rows]
            # Same-content later books must remain in ordered history.
            b=dict(plain[3],event_id='other-book',source_ts=4,recv_ts=4,decision_ts=4,event_ts=4)
            plain.insert(4,b)
            self.compare(d,list(chain(plain)),'same-content-distinct-book')
    def test_reference_and_disk_reject_invalid_fee_oversell_and_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);_,rows=complete_synthetic_journal(d/'fixture')
            for label,index,change in [('fee',5,{'fee':'9'}),('depth',4,{'qty':'999','notional':'499.5','fee':str(fee().fee('999','.5'))}),('duplicate',2,{'event_id':'1'})]:
                with self.subTest(label=label):
                    altered=[{k:v for k,v in r.items() if k not in ('event_hash','previous_event_hash','sequence')} for r in rows]
                    altered[index].update(change); p=d/label; write_rows(p,chain(altered))
                    with self.assertRaises(ValueError):
                        ProspectiveEventAdapter(SimpleNamespace(records=read_journal(p,IDENTITY)),{('m','t'):fee()},synthetic=True)
                    with self.assertRaises(ValueError):
                        replay_disk(p,IDENTITY,{('m','t'):fee()},d/(label+'.db'),d/(label+'ids.db'),synthetic=True)
    def test_containers_preserve_alias_equality_order_and_write_through(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(Path(d)/'db')
            try:
                m=DiskMap(s,'test');m[1]={'qty':dec('1.5')};m[True]['qty']-=dec('.5')
                self.assertEqual(m[dec('1.0')]['qty'],1);self.assertEqual(list(m),[1])
                m['second']={'qty':dec('2')}
                for value in m.values():value['qty']=dec('0')
                self.assertEqual([v['qty'] for v in m.values()],[0,0])
                ids=DiskSet(s,'ids');ids.add(('t',1));self.assertIn(('t',True),ids)
                books=DiskBooks(s);books.setdefault('t',[]).append({'available_ts_ms':1})
                books.setdefault('t',[]).append({'available_ts_ms':3})
                self.assertEqual([r['available_ts_ms'] for r in reversed(books['t'])],[3,1])
                self.assertEqual(next(r for r in reversed(books['t']) if r['available_ts_ms']<=2)['available_ts_ms'],1)
                with self.assertRaises(ValueError):books['t']=[]
            finally:s.close()
    def test_large_history_is_disk_resident(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);p=d/'source';write_rows(p,chain(event('MARK',n=i+1,net_unit_marks={}) for i in range(12000)))
            a,m,s=replay_disk(p,IDENTITY,{},d/'db',d/'ids')
            try:
                self.assertEqual(len(a.accounting),12000);self.assertIsInstance(a.accounting,DiskList)
                self.assertIsInstance(a.states,DiskMap);self.assertEqual(a.ledger.cash,500)
                self.assertEqual(len(a.journal.records),0)
            finally:s.close()
    def test_existing_scratch_and_torn_source_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);p=d/'source';p.write_text('{')
            with self.assertRaisesRegex(ValueError,'TORN'): replay_disk(p,IDENTITY,{},d/'db',d/'ids')
            before=(d/'db').read_bytes()
            with self.assertRaises(FileExistsError): replay_disk(p,IDENTITY,{},d/'db',d/'newids')
            self.assertEqual((d/'db').read_bytes(),before);self.assertEqual(p.read_text(),'{')

class AdditionalEquivalenceTests(unittest.TestCase):
    def test_rotation_multiple_tokens_and_delayed_annotations(self):
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);_,rows=complete_synthetic_journal(d/'fixture');events=[]
            for cycle,token in enumerate(['t','other','t']):
                for r in rows[:-1]:
                    e={k:v for k,v in r.items() if k not in ('event_hash','previous_event_hash','sequence')}
                    e['event_id']=f'{cycle}-{e["event_id"]}';e['trade_id']=f'trade-{cycle}';e['token_id']=token
                    for k in ['source_ts','recv_ts','decision_ts','event_ts']:e[k]+=cycle*30
                    if e.get('fill_event_id'):e['fill_event_id']=f'{cycle}-{e["fill_event_id"]}'
                    if e.get('net_unit_marks'):e['net_unit_marks']={token:next(iter(e['net_unit_marks'].values()))}
                    events.append(e)
            # FEE may legally refer to an old fill while another trade is current.
            annotations=[e for e in events if e['kind']=='FEE'];events=[e for e in events if e['kind']!='FEE']
            for i,e in enumerate(annotations):
                e=dict(e,trade_id='trade-2',token_id='t')
                for k in ['source_ts','recv_ts','decision_ts','event_ts']:e[k]=100+i
                events.append(e)
            p=d/'rows';write_rows(p,chain(events));fees={('m','t'):fee(),('m','other'):replace(fee(),token_id='other')}
            ref=ProspectiveEventAdapter(SimpleNamespace(records=read_journal(p,IDENTITY)),fees,synthetic=True)
            a,meta,s=replay_disk(p,IDENTITY,fees,d/'db',d/'ids',synthetic=True)
            try:self.assertEqual(digest(snapshot(ref)),digest(materialize(a)))
            finally:s.close()

class IdentityReconstructionTests(unittest.TestCase):
    def test_identical_content_new_event_token_isolation_and_nonbook(self):
        import sqlite3
        from .closure_identity import identities
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture.db';db=sqlite3.connect(p)
            db.execute('create table events(event_id integer,generation integer,market_slug text,payload_json text,kind text,market_duration text)')
            q=lambda t,n:dict(token_id=t,event_ts_ms=n,received_ts_ms=n,source_hash='h'+str(n),sequence=None,bids=[['.4','50']],asks=[['.5','50']])
            states=[(q('u',1),q('d',1),[dict(event_type='book',asset_id=t) for t in ['u','d']]),
                    (q('u',1),q('d',1),[dict(event_type='book',asset_id='u')]),
                    (q('u',3),q('d',1),[dict(event_type='price_change')]),
                    (q('u',3),q('d',1),[dict(event_type='last_trade_price',asset_id='u')])]
            for i,(up,down,metadata) in enumerate(states):
                db.execute('insert into events values(?,1,?,?,?,?)',(i+1,'market',json.dumps(dict(up=up,down=down,source_metadata=metadata,received_ts_ms=i+1)), 'BOOK','5m'))
            db.commit();db.close();r=identities(p);u=[x for x in r['rows'] if x['token']=='u'];down=[x for x in r['rows'] if x['token']=='d']
            self.assertEqual(u[0]['depth_fingerprint'],u[1]['depth_fingerprint'])
            self.assertNotEqual(u[0]['book_state_id'],u[1]['book_state_id'])
            self.assertTrue(u[1]['same_content_but_new_event'])
            self.assertNotEqual(u[1]['book_state_id'],u[2]['book_state_id'])
            self.assertEqual(u[2]['book_state_id'],u[3]['book_state_id'])
            self.assertEqual(len(set(x['book_state_id'] for x in down)),1)
            self.assertNotEqual(u[2]['observation_id'],u[3]['observation_id'])
            self.assertEqual(u[0]['next_book_state_id'],u[1]['book_state_id'])
