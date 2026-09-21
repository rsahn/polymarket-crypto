import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.collectors.polymarket_ws import PolymarketOrderbookCollector
from app.d5.features import BTCFeatures
from app.d5.audit import audit
from app.d5.identity import MarketIdentity, assert_shadow
from app.d5.observer import Observer
from app.d5.replay import Decision, DemoAlternating, PaperExecutor, Replay, replay_database
from app.d5.store import Store, encode
from app.paper.c3_observer import C3ShadowObserver


def identity(name='A', **kwargs):
    return MarketIdentity(**dict(market_duration='5m',market_slug=name,condition_id='condition_'+name,
                                  token_up=name+'_UP',token_down=name+'_DOWN',expiry_ts_ms=100000,**kwargs))


def snapshot(m, ts=1000, **kw):
    return {**m.fields(),'market_key':m.market_duration,'token_ids':{'UP':m.token_up,'DOWN':m.token_down},
            'event_ts_ms':ts,'received_ts_ms':ts,'recv_ts_ms':ts,'wire_hash':str(ts),
            'up':{'token_id':m.token_up,'bid':.4,'ask':.45,'bid_qty':10.,'ask_qty':10.,
                  'bids':[[.4,10.]],'asks':[[.45,10.]],'event_ts_ms':ts},
            'down':{'token_id':m.token_down,'bid':.5,'ask':.55,'bid_qty':10.,'ask_qty':10.,
                    'bids':[[.5,10.]],'asks':[[.55,10.]],'event_ts_ms':ts},**kw}


class D5DataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'d5_test.db')
        self.o=Observer(self.store)
        self.a,self.b=identity(),identity('B')
        self.o.activate(self.a,1,0)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def anchor(self):
        eid=self.o.observe(self.a,1,snapshot(self.a),{},1000)
        aid=self.store.db.execute("SELECT anchor_id FROM anchors WHERE first_side='DOWN'").fetchone()[0]
        return eid,aid

    def test_rotation_cannot_hedge_old_anchor(self):
        _,aid=self.anchor()
        self.o.activate(self.b,2,16000)
        eid=self.o.observe(self.b,2,snapshot(self.b,16000),{},16000)
        self.assertEqual(self.o.attempt_hedge(aid,eid,snapshot(self.b,16000),'UP'),'CROSS_MARKET_REJECT')
        self.assertNotIn(self.a.key,self.o.anchors)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM hedge_attempts WHERE status='ACCEPT'").fetchone()[0],0)

    def test_identity_components_each_rejected(self):
        eid,aid=self.anchor()
        for field in ('market_slug','condition_id','token_up','token_down'):
            s=snapshot(self.a,16000); s[field]='FOREIGN'
            self.assertEqual(self.o.attempt_hedge(aid,eid,s,'UP'),'CROSS_MARKET_REJECT')
        s=snapshot(self.a,16000); s['up']['token_id']='B_UP'
        self.assertEqual(self.o.attempt_hedge(aid,eid,s,'UP'),'CROSS_MARKET_REJECT')

    def test_t0_anchor_persisted_without_any_future_book(self):
        self.anchor()
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM anchors').fetchone()[0],2)
        self.o.expire(100000)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM anchors WHERE status='OPEN'").fetchone()[0],0)

    def test_post_expiry_anchor_rejected(self):
        self.assertIsNone(self.o.observe(self.a,1,snapshot(self.a,100000),{},100000))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM anchors').fetchone()[0],0)

    def test_window_and_token_of_same_market(self):
        _,aid=self.anchor()
        s=snapshot(self.a,16000)
        eid=self.o.observe(self.a,1,s,{},16000)
        self.assertEqual(self.o.attempt_hedge(aid,eid,s,'UP',min_delay_ms=15000,max_delay_ms=30000),'ACCEPT')
        self.assertEqual(self.o.attempt_hedge(aid,eid,snapshot(self.a,40000),'UP',max_delay_ms=30000),'OUTSIDE_WINDOW')

    def test_reconnect_and_stale_generation(self):
        self.anchor()
        self.o.activate(self.a,2,2000)
        self.assertNotIn(self.a.key,self.o.anchors)
        self.assertIsNone(self.o.observe(self.a,1,snapshot(self.a,3000),{},3000))
        self.assertIsNotNone(self.o.observe(self.a,2,snapshot(self.a,3000),{},3000))

    def test_double_and_out_of_order_snapshots(self):
        self.anchor()
        self.assertIsNone(self.o.observe(self.a,1,snapshot(self.a),{},1000))
        self.assertIsNone(self.o.observe(self.a,1,snapshot(self.a,900),{},1001))
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM events WHERE kind='BOOK'").fetchone()[0],1)

    def test_database_token_constraint(self):
        eid,_=self.anchor()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.db.execute('INSERT INTO book_sides VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (eid,'UP','FOREIGN',1000,1000,.4,.5,1.,1.,.1,'[]','[]',None,None))

    def test_immutable_market_mapping(self):
        wrong=MarketIdentity('5m','A','condition_A','B_UP','B_DOWN',100000)
        with self.assertRaises(ValueError): self.store.market(wrong,{})

    def test_legacy_observer_rotation_is_fixed(self):
        old=C3ShadowObserver(Path(self.tmp.name)/'compatibility.db')
        old.observe(snapshot(self.a),None,1000)
        anchor=next(a for a in old.anchors[self.a.key] if a.first_side=='DOWN')
        old.observe(snapshot(self.b,16000),None,16000)
        self.assertNotIn(self.a.key,old.anchors)
        old._persist(anchor,16000,snapshot(self.b,16000)['up'],snapshot(self.b,16000))
        self.assertEqual(old.observations,0)
        self.assertIn('CROSS_MARKET_REJECT',old.rejections)

    def test_database_replay_deterministic(self):
        for ts in (1000,2000,3000,4000):
            self.o.observe(self.a,1,snapshot(self.a,ts),{},ts)
        self.store.flush()
        a=replay_database(self.store.path,self.store.session_id,DemoAlternating())
        b=replay_database(self.store.path,self.store.session_id,DemoAlternating())
        self.assertEqual(encode(a),encode(b))

    def test_empty_or_single_feed_cannot_validate_smoke(self):
        self.store.flush()
        empty=audit(self.store.path)
        self.assertFalse(empty['SMOKE_VALIDATED'])
        self.anchor(); self.store.flush()
        result=audit(self.store.path)
        self.assertEqual(result['ROWS'],1)
        self.assertEqual(result['CROSS_MARKET_VIOLATIONS'],0)
        self.assertFalse(result['SMOKE_VALIDATED'])

    def test_failed_fill_does_not_erase_inventory(self):
        executor=PaperExecutor(); executor.update_book(self.a,snapshot(self.a))
        executor.execute(self.a,Decision('BUY_UP',2),1000,1)
        b=snapshot(self.a,2000); b['down']['ask_qty']=0; b['down']['asks']=[]
        executor.update_book(self.a,b)
        self.assertEqual(executor.execute(self.a,Decision('BUY_DOWN',2),2000,2),[])
        self.assertEqual(executor.positions[self.a.key].up_qty,2)
        self.assertAlmostEqual(executor.cash,499.1)


class D5ExecutionTests(unittest.TestCase):
    def test_shares_cash_partial_and_no_reuse_of_depth(self):
        e=PaperExecutor(capital=1.)
        m=identity(); b=snapshot(m)
        e.update_book(m,b)
        f=e.execute(m,Decision('BUY_UP',10),1000,1)
        self.assertAlmostEqual(sum(x['fill_qty'] for x in f),1/.45)
        self.assertAlmostEqual(e.cash,0.)
        self.assertEqual(e.execute(m,Decision('BUY_DOWN',10),2000,2),[])
        self.assertAlmostEqual(e.positions[m.key].up_qty,1/.45)

    def test_sell_only_owned_shares_at_real_bid_depth(self):
        e=PaperExecutor(); m=identity(); e.update_book(m,snapshot(m))
        e.execute(m,Decision('BUY_UP',2),1000,1)
        e.execute(m,Decision('REDUCE_UP',10),2000,2)
        self.assertEqual(e.positions[m.key].up_qty,0)
        self.assertAlmostEqual(e.cash,499.9)
        self.assertAlmostEqual(e.positions[m.key].realized_pnl,-.1)

    def test_same_book_does_not_replenish_simulated_consumption(self):
        e=PaperExecutor(); m=identity(); b=snapshot(m)
        e.update_book(m,b); e.execute(m,Decision('BUY_UP',10),1000,1)
        e.update_book(m,b)
        self.assertEqual(e.execute(m,Decision('BUY_UP',10),2000,2),[])

    def test_expiry_does_not_refund_or_invent_resolution(self):
        class Buy:
            def on_event(self,c): return Decision('BUY_UP',1) if c['kind']=='BOOK' else Decision('WAIT')
        r=Replay(Buy()); m=identity()
        r.process({'event_id':1,'available_ts_ms':1000,'kind':'BOOK','identity':m.fields(),'payload':snapshot(m)})
        r.process({'event_id':2,'available_ts_ms':100000,'kind':'EXPIRE','identity':m.fields(),'payload':{}})
        metrics=r.results()['metrics']
        self.assertEqual(metrics['status'],'UNRESOLVED_DIRECTIONAL_EXPOSURE')
        self.assertIsNone(metrics['PnL'])
        self.assertAlmostEqual(metrics['final_cash'],499.55)
        self.assertEqual(metrics['time_unhedged_ms'],99000)

    def test_verified_settlement_and_double_settlement(self):
        e=PaperExecutor(); m=identity(); e.update_book(m,snapshot(m))
        e.execute(m,Decision('BUY_UP',2),1000,1)
        e.execute(m,Decision('BUY_DOWN',1),2000,2)
        before=e.cash
        self.assertAlmostEqual(before,498.55)
        e.settle(m,'DOWN'); self.assertAlmostEqual(e.cash,499.55)
        e.settle(m,'DOWN'); self.assertAlmostEqual(e.cash,499.55)

    def test_fee_and_slippage_accounting(self):
        e=PaperExecutor(fee_rate=.01,friction_per_share=.005,slippage=.01)
        m=identity(); e.update_book(m,snapshot(m))
        e.execute(m,Decision('BUY_UP',1),1000,1)
        self.assertAlmostEqual(e.cash,500-.46-.0046-.005)
        self.assertAlmostEqual(e.fees,.0096)
        self.assertAlmostEqual(e.slippage_paid,.01)

    def test_future_tick_never_enters_features(self):
        f=BTCFeatures()
        f.update(1000,{'recv_ts_ms':1000,'event_ts_ms':1000,'price':100.})
        f.update(2000,{'recv_ts_ms':2000,'event_ts_ms':2000,'price':101.})
        self.assertEqual(f.at(1500)['btc_price'],100.)
        self.assertIsNone(f.at(1500)['btc_return_1000ms'])
        self.assertAlmostEqual(f.at(2000)['btc_return_1000ms'],.01)

    def test_live_modes_always_rejected(self):
        for config in ({'LIVE_TRADING':'true'},{'MODE':'live'},{'TRADING_MODE':'real'},{'SEND_REAL_ORDERS':'yes'}):
            with self.assertRaises(RuntimeError): assert_shadow(config)
        assert_shadow({'MODE':'paper'})


class D5WebsocketTests(unittest.TestCase):
    def book(self,ts=1000):
        return [{'asset_id':token,'timestamp':ts,'bids':[{'price':.4,'size':1}],
                 'asks':[{'price':.6,'size':1}]} for token in ('A_UP','A_DOWN')]

    def test_reconnect_clears_bbo_and_depth(self):
        c=PolymarketOrderbookCollector('5m',{'UP':'A_UP','DOWN':'A_DOWN'},None)
        c.normalize_snapshot(self.book())
        c._authoritative_top['A_UP']={'bid':.9,'ask':.99}
        c._reset_connection_state()
        self.assertEqual(c._authoritative_top,{})
        self.assertEqual(c._books,{})
        self.assertEqual(c.normalize_snapshot(self.book(2000))['up']['ask'],.6)

    def test_source_order_and_duplicates(self):
        c=PolymarketOrderbookCollector('5m',{'UP':'A_UP','DOWN':'A_DOWN'},None)
        c.normalize_snapshot(self.book(2000))
        self.assertEqual(c.normalize_snapshot(self.book(1000))['reject_reason'],'OUT_OF_ORDER')
        self.assertEqual(c.normalize_snapshot(self.book(2000))['reject_reason'],'DUPLICATE_EVENT')

    def test_envelope_token_id_and_hash_preserved(self):
        c=PolymarketOrderbookCollector('5m',{'UP':'A_UP','DOWN':'A_DOWN'},None)
        events=[{'topic':'market','type':'book','payload':{**r,'tokenId':r['asset_id']}}
                for r in self.book(1000)]
        for e in events: del e['payload']['asset_id']
        c.normalize_snapshot(events)
        result=c.normalize_snapshot({'topic':'market','type':'price_change','payload':{
            'timestamp':2000,'priceChanges':[{'tokenId':'A_UP','price':.41,'size':2,'side':'BUY','hash':'source_hash'}]}})
        self.assertEqual(result['up']['bid'],.41)
        self.assertEqual(result['up']['source_hash'],'source_hash')


if __name__=='__main__': unittest.main()
