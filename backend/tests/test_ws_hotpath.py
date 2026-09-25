from app.live.readonly_book_stream import StreamBook
from app.live.production_readonly import BookStateSource

def test_ingest_does_not_materialize_decision_snapshot(monkeypatch):
    s=StreamBook('m','c',('a','b'),5000,clock=lambda:1000);s.connected_generation()
    def forbidden(*a):raise AssertionError('FULL_SNAPSHOT_COPY_IN_HOT_PATH')
    monkeypatch.setattr(BookStateSource,'read',forbidden)
    for t in ('a','b'):
        s.ingest(dict(event_type='book',market='c',asset_id=t,timestamp='1000',bids=[dict(price='.4',size='1')],asks=[dict(price='.6',size='1')]))
    assert s.diagnostics['resync_complete_generation']==1

def test_decision_snapshot_remains_detached_and_sync_matches_base():
    s=StreamBook('m','c',('a','b'),5000,clock=lambda:1000);s.connected_generation()
    for t in ('a','b'):
        s.ingest(dict(event_type='book',market='c',asset_id=t,timestamp='1000',bids=[dict(price='.4',size='1')],asks=[dict(price='.6',size='1')]))
        assert (s.connected and len(s.books)==2)==BookStateSource.read(s)['synchronized']
    old=s.read()
    s.ingest(dict(event_type='price_change',market='c',timestamp='1000',price_changes=[dict(asset_id='a',side='BUY',price='.4',size='2')]))
    assert str(old['books']['a']['bids'][0][1])=='1'
    assert str(s.read()['books']['a']['bids'][0][1])=='2'
    old['books'].clear()
    assert s.read()['available']
