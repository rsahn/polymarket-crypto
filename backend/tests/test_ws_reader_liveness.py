import asyncio,json
import pytest
from app.live.readonly_book_stream import StreamBook


def book(t,ts):return dict(event_type='book',market='c',asset_id=t,timestamp=str(ts),bids=[dict(price='.4',size='1')],asks=[dict(price='.6',size='1')])


def test_stale_during_processing_does_not_stop_reader_before_full_resync():
    clock=[1000];seen=[]
    class S(StreamBook):
        def update(self,*a):
            if a[3]==500:clock[0]=1001
            return super().update(*a)
    s=S('m','c',('a','b'),5000,clock=lambda:clock[0])
    class Socket:
        index=0
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def send(self,*a):pass
        async def recv(self):
            self.index+=1
            if self.index==1:return json.dumps(book('a',500))
            if self.index==2:
                seen.append(s.read());clock[0]=1100;return json.dumps(book('a',1100))
            if self.index==3:return json.dumps(book('b',1100))
            seen.append(s.read());raise asyncio.CancelledError()
    async def go():
        with pytest.raises(asyncio.CancelledError):await s.run(connect_factory=lambda *a,**k:Socket())
    asyncio.run(go())
    assert len(seen)==2 and not seen[0]['available']
    assert seen[1]['available'] and seen[1]['generation']==1
    assert seen[0]['diagnostics']['freshness_cause']=='LOCAL_PROCESSING_DELAY'
