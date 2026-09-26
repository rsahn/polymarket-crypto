from app.live.shadow_calibration import ShadowCalibration


def test_market_metrics_and_ages_never_mean_a_fill():
    c=ShadowCalibration(shares=5,capacity=8)
    c.book('m',1,0,source_ms=1000,received_ms=1010,decision_ms=1020,bids=[(.4,10)],asks=[(.5,3),(.6,2)])
    c.book('m',1,0,source_ms=1100,received_ms=1120,decision_ms=1130,bids=[(.41,10)],asks=[(.52,5)])
    rows=c.report()['book_samples']
    assert rows[0]['hypothetical_buy_price']==.54
    assert round(rows[0]['hypothetical_slippage_bps'],5)==800
    assert rows[1]['update_interval_ms']==110
    assert round(rows[1]['best_ask_movement'],6)==.02
    assert rows[1]['book_age_ms']==30
    assert c.report()['real_fills']==0


def test_boundaries_insufficient_depth_and_overflow():
    c=ShadowCalibration(shares=5,capacity=2)
    for gen in (1,2,3):c.book('m',gen,0,source_ms=1000,received_ms=1010,decision_ms=1020,bids=[],asks=[(.5,2)])
    r=c.report();assert r['dropped_samples']==1
    assert all(x['hypothetical_buy_price'] is None and x['update_interval_ms'] is None for x in r['book_samples'])
    assert r['selection_bias']=='ACCEPTED_BOOKS_ONLY_WITH_EXPLICIT_REJECTION_COUNTS'


def test_generation_keeps_missing_signal_unknown_and_original_ages():
    c=ShadowCalibration(shares=5)
    c.generation(7,2000,{'book':1900,'balance':1000,'orders':1100,'positions':1200,'inventory':900},signal=None)
    r=c.report()['generations'][0]
    assert r['book_age_ms']==100 and r['balance_age_ms']==1000 and r['inventory_proof_age_ms']==1100
    assert r['signal_age_ms'] is None and r['signal_status']=='NOT_OBSERVED'
    assert not c.report()['sla_calibrated'] and not c.report()['submit_allowed']


def test_signal_tap_asof_is_not_retimed_or_matched_across_generations():
    c=ShadowCalibration(shares=5)
    c.book('m',1,0,source_ms=1000,received_ms=1010,decision_ms=1020,bids=[(.4,5)],asks=[(.5,5)])
    c.signal('m',1,0,source_ms=1030,received_ms=1040,decision_ms=1050)
    c.signal('m',2,0,source_ms=1030,received_ms=1040,decision_ms=1050)
    rows=c.report()['signal_samples']
    assert rows[0]['book_age_at_signal_ms']==50 and rows[0]['signal_age_ms']==20
    assert rows[1]['book_age_at_signal_ms'] is None


def test_real_stream_hook_records_metrics_and_rejections_without_ids():
    import json
    import pytest
    from app.live.shadow_calibration import calibration_session,current_calibration
    from app.live.readonly_book_stream import StreamBook
    c=ShadowCalibration(shares=5)
    now=[1020]
    with calibration_session(c):
        s=StreamBook('PRIVATE_MARKET_SENTINEL','condition',('a','b'),5000,clock=lambda:now[0])
    assert current_calibration() is None
    s.connected_generation()
    event=dict(event_type='book',market='condition',asset_id='a',timestamp='1000',
        bids=[dict(price='.4',size='10')],asks=[dict(price='.5',size='10')])
    s.ingest(event,wire_received_ms=1010)
    r=c.report()
    assert len(r['book_samples'])==1 and r['instrumentation_errors']==0
    assert r['book_samples'][0]['sample_stage']=='BOOK_PROCESSING_OBSERVATION'
    assert not r['book_samples'][0]['decision_is_execution']
    assert 'PRIVATE_MARKET_SENTINEL' not in json.dumps(r)
    now[0]=2000
    with pytest.raises(ValueError,match='STALE_WIRE_EVENT'):s.ingest(event,wire_received_ms=1990)
    assert c.report()['rejection_counts']=={'STALE_WIRE_EVENT':1}
    assert not s.read()['fresh']


def test_manual_shadow_mode_captures_context_and_never_uses_write_capable_mode(monkeypatch,tmp_path,capsys):
    import json
    import analysis.qualify_post_genesis as q
    from app.live.shadow_calibration import current_calibration
    calls=[]
    async def run(target,*,health_contract):
        assert target and health_contract
        calls.append(True)
        current_calibration().generation(1,2000,dict(book=1900,balance=1000))
        return dict(submit_allowed=False,ready_for_arm=False)
    monkeypatch.setattr(q,'run',run)
    monkeypatch.setattr(q,'ROOT',tmp_path)
    monkeypatch.setattr(q.sys,'argv',['probe','--target-machine','--shadow-calibration','--calibration-shares','5'])
    assert q.main()==2 and not calls and not list(tmp_path.iterdir())
    monkeypatch.setattr(q.sys,'argv',['probe','--target-machine','--health-contract','--shadow-calibration','--calibration-shares','5'])
    q.main()
    result=json.loads(next(tmp_path.glob('D6_POST_GENESIS_READINESS_*.json')).read_text())
    assert result['shadow_calibration']['generations'][0]['balance_age_ms']==1000
    assert result['shadow_calibration']['generations'][0]['signal_age_ms'] is None
    assert not result['shadow_calibration']['sla_calibrated'] and not result['submit_allowed']
    assert current_calibration() is None
    capsys.readouterr()
