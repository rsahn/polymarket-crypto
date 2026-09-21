import unittest,copy
from app.d5.protocol51 import classify_gap,gap_failure,ntp_gate
from app.d5.clock51 import parse_w32time,decode_packet,stamp

class ProtocolTests(unittest.TestCase):
    def test_rotations_5m_15m_and_reconnect(self):
        for duration in ('5m','15m'):
            a=dict(slug=duration+'-old',generation=1); b=dict(slug=duration+'-new',generation=2)
            self.assertEqual(classify_gap(a,b),'TRANSITION_GAP')
            self.assertIsNone(gap_failure('TRANSITION_GAP',6000,transition_verified=True))
            self.assertEqual(gap_failure('TRANSITION_GAP',6000),'UNVERIFIED_TRANSITION')
            self.assertIsNotNone(gap_failure('TRANSITION_GAP',10001,transition_verified=True))
            b['slug']=a['slug'];self.assertEqual(classify_gap(a,b),'RECONNECT_GAP')
            self.assertIsNotNone(gap_failure('RECONNECT_GAP',5001))
            b['generation']=1;self.assertEqual(classify_gap(a,b),'INTERNAL_FEED_GAP')
            self.assertIsNotNone(gap_failure('INTERNAL_FEED_GAP',5001))
    def test_boundaries_and_negative(self):
        self.assertEqual(classify_gap(None,None,start=True),'STARTUP_GAP')
        self.assertEqual(classify_gap(None,None,stop=True),'SHUTDOWN_GAP')
        self.assertIsNotNone(gap_failure('STARTUP_GAP',10001))
        self.assertIsNotNone(gap_failure('SHUTDOWN_GAP',10001))
        self.assertEqual(gap_failure('INTERNAL_FEED_GAP',-1),'RECEIVE_CLOCK_REGRESSION')
    def test_clock_fail_closed(self):
        s=dict(references={n:dict(valid=True,samples=[dict(offset_ms=20,dispersion_ms=2,delay_ms=30)]*3) for n in ('time.windows.com','time.cloudflare.com')},w32time=dict(service='Running',source='test',last_sync_error=0,last_sync_age_seconds=20))
        self.assertEqual(ntp_gate(s),[])
        s['w32time']['last_sync_error']=2;self.assertIn('W32TIME_SYNC_ERROR',ntp_gate(s))
        s['w32time']['last_sync_age_seconds']=4000;self.assertIn('W32TIME_STALE_SYNC',ntp_gate(s))
        s['references']['time.windows.com']['samples']=[];self.assertTrue(any('MISSING' in x for x in ntp_gate(s)))
    def test_french_status(self):
        s=parse_w32time('Source: time.windows.com\nErreur lors de la derniere synchronisation: 2 (obsolete)\nDuree ecoulee depuis: 4000.2s','Running')
        self.assertEqual(s['last_sync_error'],2);self.assertEqual(s['last_sync_age_seconds'],4000.2)
    def test_ntp_origin_and_offset(self):
        t=1700000000.;orig=stamp(t);p=bytearray(48);p[0]=0x24;p[1]=2;p[24:32]=orig;p[32:40]=stamp(t+.020);p[40:48]=stamp(t+.021)
        r=decode_packet(p,orig,t,t+.011,.011);self.assertAlmostEqual(r['offset_ms'],15,places=2)
        with self.assertRaises(ValueError):decode_packet(p,stamp(t+1),t,t+.011,.011)
        p[0]=0xe4
        with self.assertRaises(ValueError):decode_packet(p,orig,t,t+.011,.011)
