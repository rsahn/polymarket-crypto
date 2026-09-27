import json,types,asyncio,ast,copy
from pathlib import Path
import pytest
from analysis.d6.causal_capture_24h_v1.collector import Journal,read_journal,recover,BookCapture,storage_preflight,source_seal,build_v1,Fixed25Ledger
ROOT=Path(__file__).resolve().parents[3]
def books(ts=100):return [dict(event_type='book',asset_id=t,timestamp=str(ts),hash=t+str(ts),bids=[{'price':'.49','size':'100'}],asks=[{'price':'.5','size':'100'}]) for t in ['u','d']]
def fixture(tmp_path):
 j=Journal(tmp_path/'capture',session='fixture');b=BookCapture(j);b.activate('m','c',{'UP':'u','DOWN':'d'},100000);return j,b

def test_event_identity_depth_same_content_new_event_and_isolation(tmp_path):
 j,b=fixture(tmp_path);a=b.ingest(books(),101);ids=a['_causal_states'].copy()
 x=b.ingest(dict(event_type='book',asset_id='u',timestamp='102',hash='new',bids=[{'price':'.49','size':'100'}],asks=[{'price':'.5','size':'100'}]),103)
 assert x['up']['asks']==a['up']['asks'];assert x['_causal_states']['u']!=ids['u'];assert x['_causal_states']['d']==ids['d']
 assert b.full_depth('u')['asks']==[(.5,100.)]
 j.close();rows=list(read_journal(tmp_path/'capture'));assert [r['seq'] for r in rows]==list(range(len(rows)))

def test_rotation_future_and_sequence_rejection(tmp_path):
 j,b=fixture(tmp_path);b.ingest(books(),101)
 with pytest.raises(ValueError,match='FUTURE'):b.ingest(books(200),150)
 b.activate('m2','c2',{'UP':'v','DOWN':'w'},200000);assert not b.states
 b.ingest(books(201),202);assert not b.states
 with pytest.raises(ValueError):j.append('CONTROL',{},seq=0)
 j.close()

def test_journal_recovery_checkpoint_torn_and_new_restart(tmp_path):
 j,b=fixture(tmp_path);b.ingest(books(),101);j.checkpoint({'note':'state reference only'});j.close()
 r=recover(tmp_path/'capture');assert r['complete_prefix'] and r['last_checkpoint'] is not None
 with pytest.raises(FileExistsError):Journal(tmp_path/'capture',session='fixture')
 data=(tmp_path/'capture').read_bytes();(tmp_path/'torn').write_bytes(data[:-3])
 with pytest.raises(ValueError,match='TORN'):recover(tmp_path/'torn')
 (tmp_path/'changed').write_bytes(data[:30]+bytes([data[30]^1])+data[31:])
 with pytest.raises(ValueError):recover(tmp_path/'changed')

def test_quota_and_os_disk_full_fail_closed(tmp_path,monkeypatch):
 j=Journal(tmp_path/'small',session='s',limits={'CONTROL':1})
 with pytest.raises(OSError):j.append('CONTROL',{'x':1})
 assert j.failed;j.close()
 j=Journal(tmp_path/'io',session='s')
 def fail(*args):raise OSError(28,'disk full')
 monkeypatch.setattr(j,'_write',fail)
 with pytest.raises(OSError):j.append('CONTROL',{})
 assert j.failed;j.close()

def test_storage_and_hashes(tmp_path):
 p=storage_preflight(0);assert p['status']=='CAPTURE_24H_STORAGE_BLOCKED';assert p['additional_bytes_required']==p['required_bytes']
 assert storage_preflight(p['required_bytes'])['status']=='PASS'
 s=source_seal(ROOT);s.verify(ROOT)
 assert 'analysis/run_d6_paper_live.py' in s.hashes
 assert 'analysis/d6/prospective_24h_v1/PROTOCOL.json' in s.hashes

def test_fixed25_only():
 l=Fixed25Ledger();assert l.sizes(100)=={'fixed_25':25};assert l.sizes(2)=={'fixed_25':2}

@pytest.mark.parametrize('mode',['normal','partial','no_exit_depth','no_exit_book','rotation','no_entry_depth'])
def test_differential_entry_exit_residual_and_linkage(tmp_path,mode):
 outputs=[]
 for observed in (False,True):
  folder=tmp_path/str(observed);folder.mkdir();j,b=fixture(folder);snap=b.ingest(books(),101)
  latest={'5m':snap};ledger=Fixed25Ledger();ticks=[1000]
  def clock():ticks[0]+=1;return ticks[0]
  calls=[]
  async def sleep(delay):
   calls.append(delay)
   if len(calls)==1 and mode=='no_entry_depth':latest['5m']=copy.deepcopy(snap);latest['5m']['up']['asks']=[]
   if len(calls)==2:
    if mode=='partial':latest['5m']=copy.deepcopy(snap);latest['5m']['up']['bids']=[(.49,10.)]
    elif mode=='no_exit_book':latest.clear()
    elif mode=='rotation':latest['5m']={**snap,'market_slug':'other'}
    elif mode=='no_exit_depth':latest['5m']=copy.deepcopy(snap);latest['5m']['up']['bids']=[]
  engine=build_v1(ROOT,j,ledger,latest,clock=clock,sleep=sleep,instrumented=observed)
  asyncio.run(engine['execute_signal'](1000,.001,'UP'));j.close()
  outputs.append((ledger.results,ledger.capital,calls))
  if observed:
   rows=list(read_journal(folder/'capture'));kinds=[r['payload'].get('kind') for r in rows if r['bucket']=='CAUSAL']
   assert 'ENTRY_BOOK' in kinds
   if mode!='no_entry_depth':assert 'ENTRY_RESULT' in kinds
   if mode=='no_exit_depth':
    assert 'SKIP' in kinds
    skip=next(r['payload']['payload'] for r in rows if r['bucket']=='CAUSAL' and r['payload']['kind']=='SKIP')
    assert skip['residual_shares']==50
   if mode=='partial':
    exit=next(r['payload']['payload'] for r in rows if r['bucket']=='CAUSAL' and r['payload']['kind']=='EXIT_RESULT')
    assert exit['sold']==10 and exit['exit_residual_shares']==40
 assert outputs[0]==outputs[1]


def test_reconstruction_depth_delta_and_decision_bound(tmp_path):
 from analysis.d6.causal_capture_24h_v1.collector import reconstruct_state
 j,b=fixture(tmp_path);raw=books();raw[0]['asks']=[{'price':str(.5+i*.001),'size':'2'} for i in range(25)]
 a=b.ingest(raw,101);first=a['_causal_states']['u'];decision=j.seq
 b.ingest({'event_type':'price_change','timestamp':'102','price_changes':[{'asset_id':'u','price':'.5','size':'9','side':'SELL','hash':'delta'}]},103)
 second=b.states['u'];j.close()
 recovered=reconstruct_state(tmp_path/'capture',first,before_sequence=decision)
 assert len(recovered['full_depth']['asks'])==25
 assert len(recovered['v1_view']['asks'])==20
 assert reconstruct_state(tmp_path/'capture',second)['full_depth']['asks'][0]==(.5,9.)
 with pytest.raises(ValueError,match='NOT_OBSERVABLE'):reconstruct_state(tmp_path/'capture',second,before_sequence=decision)

def test_ingress_bounds_and_preflight_prevent_network(tmp_path,monkeypatch):
 from analysis.d6.causal_capture_24h_v1 import runner
 q=runner.Ingress()
 with pytest.raises(BufferError):q.put('BOOK',{'x':'x'*(runner.MAX_WIRE+1)})
 for i in range(1024):q.put('BTC',{'x':i},i)
 with pytest.raises(BufferError):q.put('BTC',{})
 assert asyncio.run(q.get())[:2]==('BTC',{'x':0})
 monkeypatch.setattr(runner.shutil,'disk_usage',lambda p:types.SimpleNamespace(free=0))
 dest=ROOT/'analysis/d6/causal_capture_24h_v1/never_created_capture'
 with pytest.raises(RuntimeError,match='CAPTURE_24H_STORAGE_BLOCKED'):asyncio.run(runner.capture(dest))
 assert not dest.exists()

def test_checkpoint_link_and_flush_failure(tmp_path,monkeypatch):
 j,b=fixture(tmp_path);j.append('CHECKPOINT',{'previous_seq':999,'previous_hash':'bad'});j.close()
 with pytest.raises(ValueError,match='CHECKPOINT_LINK'):recover(tmp_path/'capture')
 j=Journal(tmp_path/'flush',session='s');j.append('RAW',{'x':1})
 def fail(*a):raise OSError('fsync failure')
 with monkeypatch.context() as m:
  m.setattr('os.fsync',fail)
  with pytest.raises(OSError):j.flush()
 assert j.failed;j.close()

def test_task_failure_supervised_and_clock_rejected(tmp_path):
 j,b=fixture(tmp_path);snap=b.ingest(books(),101);l=Fixed25Ledger();engine=build_v1(ROOT,j,l,{'5m':snap},clock=lambda:50)
 async def run():
  await engine['on_btc'](types.SimpleNamespace(price=100.,recv_ts_ms=1000,event_ts_ms=999))
  await engine['on_btc'](types.SimpleNamespace(price=100.1,recv_ts_ms=1250,event_ts_ms=1249))
  await asyncio.gather(*engine['pending'],return_exceptions=True);await asyncio.sleep(0)
 asyncio.run(run());assert engine['failures'];assert 'FUTURE_DECISION_BOOK' in str(engine['failures'][0]);j.close()

def test_strategy_hash_guard(monkeypatch):
 from analysis.d6.causal_capture_24h_v1 import runner
 monkeypatch.setitem(runner.EXPECTED,'analysis/run_d6_paper_live.py','0'*64)
 with pytest.raises(ValueError,match='HASH_CHANGED'):runner.checked_seal()


def test_signal_differential_identity_direction_cooldown_and_links(tmp_path):
 from analysis.d6.causal_capture_24h_v1.collector import reconstruct_state
 outputs=[]
 for observed in (False,True):
  folder=tmp_path/str(observed);folder.mkdir();j,b=fixture(folder);snap=b.ingest(books(),101);signals=[];l=Fixed25Ledger();l.record_signal=lambda r:signals.append(r.copy());clock=[1000];sleeps=[]
  async def sleep(d):sleeps.append(d)
  engine=build_v1(ROOT,j,l,{'5m':snap},clock=lambda:clock[0],sleep=sleep,instrumented=observed)
  async def run():
   for t,p in [(1000,100),(1249,100.049),(1250,100.051),(1400,100.3),(2000,100.3),(2250,100.0),(2501,102),(2600,102.01)]:
    clock[0]=t
    await engine['on_btc'](types.SimpleNamespace(price=p,recv_ts_ms=t,event_ts_ms=t-1))
    if engine['pending']:await asyncio.gather(*engine['pending'])
   assert not engine['failures']
  asyncio.run(run());j.close();outputs.append((signals,l.results,l.capital,sleeps))
  assert [x['side'] for x in signals]==['UP','DOWN']
  if observed:
   rows=list(read_journal(folder/'capture'));causal=[r for r in rows if r['bucket']=='CAUSAL'];sr=[r['payload'] for r in causal if r['payload']['kind']=='SIGNAL']
   assert len({r['opportunity_id'] for r in sr})==2
   assert all(r['payload']['signal_source_ts']==r['payload']['signal_receive_ts']-1 for r in sr)
   for r in causal:
    k=r['payload']['kind'];p=r['payload']['payload']
    if k in ('ENTRY_BOOK','EXIT_BOOK'):
     side='entry' if k=='ENTRY_BOOK' else 'exit';state=reconstruct_state(folder/'capture',p['actual_'+side+'_book_state_id'],r['seq'])
     assert state['metadata']['view_sha256']==p['selected_v1_view_sha256']
     assert p[side+'_book_source_ts']<=p[side+'_book_receive_ts']<=p['actual_'+side+'_observation_ts']
 assert outputs[0]==outputs[1]

@pytest.mark.parametrize('failure',[False,True])
def test_runner_offline_shutdown_and_feed_failure(tmp_path,monkeypatch,failure):
 from analysis.d6.causal_capture_24h_v1 import runner
 monkeypatch.setattr(runner,'build_v1',lambda root,*a,**kw:build_v1(ROOT,*a,**kw))
 monkeypatch.setattr(runner,'ROOT',tmp_path);monkeypatch.setattr(runner,'DURATION',.01)
 seal=types.SimpleNamespace(hashes={},hash='fixture-only',verify=lambda p:None)
 monkeypatch.setattr(runner,'checked_seal',lambda:seal)
 monkeypatch.setattr(runner,'storage_preflight',lambda x:{'status':'PASS','fixture':True})
 async def clock():return {'fixture_only':True}
 monkeypatch.setattr(runner,'clock_evidence',clock)
 async def feed(q):
  q.put('ACTIVATE',{'slug':'m','metadata':{'conditionId':'c'},'token_ids':{'UP':'u','DOWN':'d'},'expiry_ts_ms':100000},101)
  q.put('BOOK',books(),102)
  if failure:raise OSError('fixture feed failed')
  await asyncio.sleep(10)
 async def idle(q):await asyncio.sleep(10)
 monkeypatch.setattr(runner,'binance',idle);monkeypatch.setattr(runner,'polymarket',feed)
 destination=tmp_path/'session'
 if failure:
  with pytest.raises(OSError,match='fixture feed failed'):asyncio.run(runner.capture(destination))
 else:asyncio.run(runner.capture(destination))
 status=json.loads((destination/'FINAL_STATUS.json').read_text())
 assert not status['admissible'] and not status['complete_24h_proven']
 assert status['status']==('INCOMPLETE' if failure else 'DURATION_REACHED_REQUIRES_ADMISSIBILITY_AUDIT')
 assert recover(destination/'capture.frames')['complete_prefix']

def test_clock_gate_rejects_missing_evidence(monkeypatch):
 from analysis.d6.causal_capture_24h_v1 import runner
 monkeypatch.setattr('app.d5.clock51.snapshot',lambda:{})
 with pytest.raises(ValueError,match='CLOCK_QUALIFICATION_FAILED'):asyncio.run(runner.clock_evidence())


def test_enveloped_future_source_rejected(tmp_path):
 j,b=fixture(tmp_path);b.ingest(books(),101)
 event={'topic':'market','type':'book','payload':{**books(200)[0]}}
 with pytest.raises(ValueError,match='FUTURE_SOURCE_TIMESTAMP'):b.ingest(event,150)
 j.close()
