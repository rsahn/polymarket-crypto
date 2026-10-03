import asyncio,copy,time,types
import pytest
from .test_repairs import evidence,Authority
from .core import digest
from .runner import PreparedSession
from .custody import CustodyOwner,ReceiptVerifier
from app.live.readonly_book_stream import StreamBook

@pytest.mark.parametrize('tamper',[False,True])
def test_rotation_requires_fresh_authorized_market_without_resetting_session(tmp_path,monkeypatch,tamper):
    async def case():
        a,v,e=evidence();a.client=object();now=[1000]
        base=a.seal(dict(account='account',session='experiment',collateral='pUSD',atomic_frontier={'sequence':0,'digest':'b'*64},trade_ids=[],valid_until_ms=2000))
        for k,payload in [('account_evidence_adapter_qualified',dict(baseline_digest=digest(base))),('exit_handoff_ready',dict(owner='owner'))]:
            e[k]['payload'].update(payload);e[k]['source_digest']=digest(e[k]['payload']);a.seal(e[k])
        class Source:
            async def snapshot(self):
                return a.seal(dict(account='account',session='experiment',collateral='pUSD',scope='wallet',atomic_frontier={'sequence':1,'digest':'b'*64},ancestor_frontiers=[base['atomic_frontier']],observed_ms=now[0],baseline_digest=digest(base),cash='100',positions={},trade_ids=[],experiment_trade_ids=[],terminal_order_ids=[],open_orders=[],**dict.fromkeys(('inventory_proven','cash_proven','orders_complete','trades_complete','positions_complete'),True)))
        async def stream_run(stream,**kw):
            stream.connected_generation()
            for t in stream.expected_tokens:
                stream.ingest(dict(event_type='book',market=stream.condition,asset_id=t,timestamp=now[0],asks=[dict(price='.5',size='100')],bids=[dict(price='.49',size='100')]))
            await asyncio.Event().wait()
        monkeypatch.setattr(StreamBook,'run',stream_run)
        stream=StreamBook('old','m',('u','d'),2500,clock=lambda:now[0])
        class Channel:pass
        owner=CustodyOwner(Channel(),ReceiptVerifier(a,'owner',clock=lambda:now[0]))
        s=PreparedSession(directory=tmp_path,experiment_id='experiment',account='account',starting_cash='100',account_reader=None,position_reader=None,stream=stream,market='m',tokens={'UP':'u','DOWN':'d'},clock=lambda:now[0],collateral='pUSD',baseline=base,authority=a,evidence_source=Source())
        armed=types.SimpleNamespace(nonce='unchanged',started_monotonic=time.monotonic(),check=lambda *args,**kwargs:None)
        async def rotation():
            new=copy.deepcopy(e)
            for k,r in new.items():
                if isinstance(r,dict):r['market']='new'
            new['market_identity_verified']['payload'].update(condition='new',tokens=['3','4'],outcome_tokens={'UP':'3','DOWN':'4'},expires_ms=9000)
            new['ws_healthy']['payload'].update(tokens=['3','4'],receive_ms=now[0])
            for r in new.values():
                if isinstance(r,dict):r['source_digest']=digest(r['payload']);a.seal(r)
            spec=dict(slug='next',condition_id='new',outcome_tokens={'UP':'3','DOWN':'4'},expiry_ms=9000)
            if tamper:spec['expiry_ms']=10000
            return spec,lambda:new
        async def supervisor(c,signal,books,directory,owner,*,maintenance):
            journal=c.ledger.journal;arm=c.arm;now[0]=1500
            await maintenance()
            assert c.ledger.journal is journal and c.arm is arm and c.arm.nonce=='unchanged'
            assert s.book.market=='new' and s.book.tokens=={'UP':'3','DOWN':'4'}
            assert c.ledger.reconciled and not c.ledger.stop_new_entries
            assert c.ledger.attempts==0 and c.ledger.allocated==0 and not c.ledger.orders
            c.arm.check('experiment')
            return 'rotated'
        monkeypatch.setattr('analysis.d6.real_execution_calibration_v1.supervisor.run',supervisor)
        try:
            task=s.start(client=a.client,verifier=v,evidence=lambda:e,signal_source=object(),custody_owner=owner,confirm=lambda *args,**kwargs:armed,rotation_source=rotation)
            if tamper:
                with pytest.raises(ValueError,match='ROTATION_PROVENANCE'):await task
                assert s.book.market=='m' and s.ledger.stop_new_entries
            else:assert await task=='rotated'
        finally:s.close()
    asyncio.run(case())
