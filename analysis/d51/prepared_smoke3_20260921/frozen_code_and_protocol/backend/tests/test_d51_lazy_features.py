import tempfile,unittest
from pathlib import Path
from app.d5.store import Store,decode
from app.d5.observer import Observer
from app.d5.features import BTCFeatures
from test_d5 import identity,snapshot

class LazyFeaturesTests(unittest.TestCase):
    def test_anchor_features_and_books_equal_eager_reference(self):
        btc=BTCFeatures()
        for t in range(0,10001,37):btc.update(t,dict(price=50000+t%23,recv_ts_ms=t,event_ts_ms=t+3))
        outputs=[];calls=[]
        with tempfile.TemporaryDirectory() as tmp:
            for lazy in (False,True):
                store=Store(Path(tmp)/str(lazy),compress_payloads=True)
                try:
                    o=Observer(store);m=identity();o.activate(m,1,0);counter=[]
                    for t in range(1000,6001,17):
                        def provider(t=t):counter.append(t);return btc.at(t)
                        o.observe(m,1,snapshot(m,t),provider if lazy else provider(),t)
                    anchors=[decode(x[0]) for x in store.db.execute('SELECT features_json FROM anchors ORDER BY anchor_id')]
                    books=[decode(x[0]) for x in store.db.execute("SELECT payload_json FROM events WHERE kind='BOOK' ORDER BY event_id")]
                    outputs.append((anchors,books));calls.append(counter)
                finally:store.close()
        self.assertEqual(outputs[0],outputs[1]);self.assertEqual(len(calls[1]),len(outputs[1][0])//2)
        self.assertLess(len(calls[1]),len(calls[0])//20)
    def test_rejected_snapshot_never_evaluates_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'fixture.db')
            try:
                o=Observer(store);m=identity();o.activate(m,1,0)
                def fail():raise AssertionError('Unused features evaluated')
                s=snapshot(m,1000);s['condition_id']='wrong'
                self.assertIsNone(o.observe(m,1,s,fail,1000))
            finally:store.close()
