import unittest
from dataclasses import replace
from decimal import Decimal
from synthetic_contract import (Key,Times,Book,asof,lag_value,prior_buys,
    project_features,Gate,require_gate,MarketInterval,split_markets,OOSOnce,microprice,DepthBudget)

K=Key('session','condition','btc-5m-test','5m',1,'up','down')
def book(event=1,stamp=9900,**kw):
    b=Book(K,event,Times(stamp,stamp,stamp),Times(stamp,stamp,stamp),
           Times(stamp,stamp,stamp),9000,11000)
    return replace(b,**kw)

class CausalJoinTests(unittest.TestCase):
    def test_baseline_backward(self):
        self.assertEqual(asof([book(),book(2,9999)],K,'up',10000).event_id,2)
    def test_no_future_nearest_neighbor(self):
        self.assertEqual(asof([book(),book(2,10001)],K,'up',10000).event_id,1)
    def test_each_clock_each_side_future_rejected(self):
        for part in ('envelope','up','down'):
            for clock in ('source','receive','available'):
                with self.subTest(part=part,clock=clock):
                    b=book();bad=replace(getattr(b,part),**{clock:10001})
                    self.assertIsNone(asof([replace(b,**{part:bad})],K,'up',10000))
    def test_each_clock_equality_rejected(self):
        for part in ('envelope','up','down'):
            for clock in ('source','receive','available'):
                b=book();bad=replace(getattr(b,part),**{clock:10000})
                self.assertIsNone(asof([replace(b,**{part:bad})],K,'up',10000))
    def test_missing_source(self):
        self.assertIsNone(asof([book(down=Times(None,9900,9900))],K,'up',10000))
    def test_one_side_stale(self):
        self.assertIsNone(asof([book(down=Times(8000,9900,9900))],K,'up',10000))
    def test_every_identity_dimension(self):
        for field,val in [('session','other'),('condition','other'),('slug','other'),
                          ('duration','15m'),('generation',2),('up_token','x'),('down_token','x')]:
            self.assertIsNone(asof([book(key=replace(K,**{field:val}))],K,'up',10000))
    def test_action_token_wrong(self):
        self.assertIsNone(asof([book()],K,'foreign',10000))
    def test_old_generation_no_fallback(self):
        self.assertIsNone(asof([book()],replace(K,generation=2),'up',10000))
    def test_before_generation_start(self):
        self.assertIsNone(asof([book(generation_start=9950)],K,'up',10000))
    def test_expiry_is_exclusive(self):
        self.assertIsNone(asof([book(expiry=10000)],K,'up',10000))
    def test_gap_flag(self):
        self.assertIsNone(asof([book(clean=False)],K,'up',10000))
    def test_order_and_tie_determinism(self):
        a,b=book(1),book(2)
        self.assertEqual(asof([a,b],K,'up',10000),asof([b,a],K,'up',10000))
        self.assertEqual(asof([b,a],K,'up',10000).event_id,2)
    def test_duplicate_event_ambiguous(self):
        with self.assertRaises(ValueError):asof([book(),book(value=99)],K,'up',10000)
    def test_future_append_invariance(self):
        before=asof([book()],K,'up',10000)
        for t in range(10000,10200,7):
            self.assertEqual(asof([book(),book(2,t,value=999)],K,'up',10000),before)
    def test_lag_has_own_availability_boundary(self):
        a=book(1,9400,value=2);b=book(2,9600,value=100)
        self.assertEqual(lag_value([a,b],K,'up',10000,500),2)
    def test_late_received_history_cannot_repair_lag(self):
        b=book(1,9400,envelope=Times(9400,9600,9600))
        self.assertIsNone(lag_value([b],K,'up',10000,500))
    def test_freshness_exact_boundary(self):
        self.assertIsNotNone(asof([book(1,9000)],K,'up',10000))
        self.assertIsNone(asof([book(1,8999)],K,'up',10000))

class InventoryAndFeatureTests(unittest.TestCase):
    def ops(self):
        return [{'second':s,'condition':'c','type':'BUY','side':'UP','qty':q}
                for s,q in [(8,3),(9,4),(10,1000),(11,1000)]]
    def test_inventory_excludes_target_second_and_future(self):
        self.assertEqual(prior_buys(self.ops(),'c',10,{'UP':0,'DOWN':0})['UP'],7)
    def test_inventory_does_not_cross_conditions(self):
        self.assertEqual(prior_buys(self.ops(),'other',10,{'UP':0,'DOWN':0})['UP'],0)
    def test_unknown_opening_stays_unknown(self):
        self.assertIsNone(prior_buys(self.ops(),'c',10))
    def test_unreconstructed_burn_stays_unknown(self):
        self.assertIsNone(prior_buys([{'second':9,'condition':'c','type':'REDEEM'}],
                                    'c',10,{'UP':2,'DOWN':2}))
    def test_targets_forbidden(self):
        for name in ('winner','resolution','future_return','next_fill','target_side','target_size','pnl','unknown_column'):
            with self.assertRaises(ValueError):project_features({name:1})
    def test_feature_whitelist(self):
        self.assertEqual(project_features({'up_best_bid':.4}),{'up_best_bid':.4})

class LifecycleTests(unittest.TestCase):
    def test_gate_blocks_every_missing_requirement(self):
        good=Gate(True,True,True,True,'hash','hash');require_gate(good)
        for field in ('writer_closed','manifest_verified','quality_accepted','research_authorized'):
            with self.assertRaises(PermissionError):require_gate(replace(good,**{field:False}))
        for a,b in [('', ''),('a','b')]:
            with self.assertRaises(PermissionError):require_gate(replace(good,replay1=a,replay2=b))
    def test_slug_disjoint_and_boundary_purged(self):
        windows={'TRAIN':(0,100),'VALIDATION':(100,200),'OOS':(200,300)}
        ms=[MarketInterval('a','a',10,80),MarketInterval('b','b',90,120),
            MarketInterval('c','c',120,180),MarketInterval('d','d',220,280)]
        self.assertEqual(split_markets(ms,windows,5),
                         {'a':'TRAIN','b':'PURGED','c':'VALIDATION','d':'OOS'})
    def test_lookback_and_target_horizon_purge(self):
        ws={'TRAIN':(0,100),'VALIDATION':(100,200)}
        self.assertEqual(split_markets([MarketInterval('a','a',80,140)],ws,5)['a'],'PURGED')
    def test_embargo_boundary(self):
        ws={'TRAIN':(0,100)}
        self.assertEqual(split_markets([MarketInterval('a','a',5,94)],ws,5)['a'],'TRAIN')
        self.assertEqual(split_markets([MarketInterval('a','a',5,95)],ws,5)['a'],'PURGED')
    def test_duplicate_slug_or_condition_rejected(self):
        for b in (MarketInterval('a','b',20,30),MarketInterval('b','a',20,30)):
            with self.assertRaises(ValueError):split_markets([MarketInterval('a','a',10,20),b],{'TRAIN':(0,100)},0)
    def test_overlapping_splits_rejected(self):
        with self.assertRaises(ValueError):split_markets([] ,{'TRAIN':(0,100),'OOS':(90,200)},0)
    def test_oos_freeze_before_access_and_once(self):
        o=OOSOnce()
        with self.assertRaises(PermissionError):o.open('a')
        o.freeze('a')
        with self.assertRaises(PermissionError):o.open('b')
        o.open('a')
        with self.assertRaises(PermissionError):o.open('a')
        with self.assertRaises(ValueError):o.freeze('b')

class FormulaAndLiquidityTests(unittest.TestCase):
    def test_microprice_and_invalid_inputs(self):
        self.assertAlmostEqual(microprice(.4,.6,30,10),.55)
        self.assertIsNone(microprice(.7,.6,1,1))
        self.assertIsNone(microprice(.4,.6,0,0))
    def test_depth_budget_not_double_consumed(self):
        d=DepthBudget([(.4,3),(.5,2)])
        q,cash,cost=d.buy(4,10)
        self.assertEqual((q,cost),(Decimal('4'),Decimal('1.7')))
        q,cash,cost=d.buy(4,cash)
        self.assertEqual(q,Decimal('1'))
        self.assertEqual(d.buy(1,cash)[0],0)
    def test_fees_and_cash_never_negative(self):
        d=DepthBudget([(.5,10)])
        q,cash,cost=d.buy(10,1,Decimal('.1'))
        self.assertGreaterEqual(cash,0)
        self.assertLessEqual(cost,1)
        self.assertLess(q,2)
    def test_partial_fill_not_refunded(self):
        d=DepthBudget([(.5,1)])
        q,cash,cost=d.buy(2,2)
        self.assertEqual((q,cash,cost),(Decimal('1'),Decimal('1.5'),Decimal('.5')))

if __name__=='__main__':unittest.main()
