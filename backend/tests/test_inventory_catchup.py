import json
import pytest
from app.live.inventory_catchup import CatchupRPC, catch_up, validate_checkpoint, CatchupBlocked
from app.live.ctf_inventory_probe import scan_ctf

H=lambda n:'0x'+format(n,'064x')
class RPC:
 wallet='0x'+'1'*40
 log_window=10
 def __init__(self):self.calls=[];self.fail=None;self.max_range=10;self.mismatch=False;self.removed=False
 def call(self,m,p):
  row=dict(rpc_method=m,status='PASS',elapsed_ms=1);self.calls.append(row)
  if self.fail:
   category,self.fail=self.fail,None;row.update(status='FAILED',error_category=category,http_status=429 if category=='RATE_LIMIT' else 503)
   raise RuntimeError('DO_NOT_LEAK_PROVIDER_SECRET')
  if m=='eth_chainId':return '0x89'
  if m=='eth_getCode':return '0x12'
  if m=='eth_getBlockByNumber':
   n=int(p[0],16);return dict(number=p[0],hash=H(n+1 if self.mismatch else n),timestamp='0x1')
  if m=='eth_getLogs':
   q=p[0];lo,hi=int(q['fromBlock'],16),int(q['toBlock'],16);row.update(from_block=lo,to_block=hi)
   if hi-lo+1>self.max_range:
    row.update(status='FAILED',error_category='RANGE_LIMIT');raise RuntimeError('SECRET')
   return [{'removed':True}] if self.removed else []
  raise AssertionError(m)

def prior():return dict(snapshot_sha256='g'*64,snapshot=dict(block_number=10,block_hash=H(10),wallet='0x'+'1'*40))
def cursor():return dict(status='PASS_SCOPED_READS',from_block=11,to_block=20,block_hash=H(20),balances={},events_count=0,assets_checked=0,observed_ms=1)
def wrapped(r):
 clock=[0.]
 def sleep(s):clock[0]+=s
 return CatchupRPC(r,clock=lambda:clock[0],sleep=sleep)

def test_scan_large_range_has_exact_local_reason_without_rpc():
 r=RPC();out=scan_ctf(r,21,50021,set())
 assert out['diagnostics']['cause']=='SCAN_TOTAL_BLOCK_LIMIT'
 assert not r.calls

@pytest.mark.parametrize('end',[25,10521,50521])
def test_consecutive_catchup_and_large_bootstrap(tmp_path,end):
 r=wrapped(RPC());report=catch_up(r,prior(),cursor(),dict(number=end,hash=H(end)),root=tmp_path)
 assert report['status']=='PASS_SCOPED_CATCHUP'
 assert report['cursor_end']==end and report['inventory_through_C_proven']
 assert not report['current_inventory_proven'] and not report['SYSTEM_READY'] and not report['submit_allowed']
 assert report['ranges_completed']==report['ranges_planned']
 files=sorted((tmp_path/'runtime/d6_inventory_cursors').glob('*.json'))
 assert files
 for p in files:validate_checkpoint(json.loads(p.read_text()),prior())
 assert report['backlog_blocks']==end-20

def test_reorg_never_checkpoints(tmp_path):
 raw=RPC();raw.mismatch=True
 r=catch_up(wrapped(raw),prior(),cursor(),dict(number=25,hash=H(25)),root=tmp_path)
 assert r['TAIL_SCAN_ROOT_CAUSE']=='CURSOR_REORG_OR_CONFLICT'
 assert not list(tmp_path.rglob('*.json'))

@pytest.mark.parametrize('category',['RATE_LIMIT','TIMEOUT','CONNECTION_ERROR'])
def test_bounded_transient_retry(category):
 raw=RPC();raw.fail=category;r=wrapped(raw)
 assert r.call('eth_chainId',[])=='0x89'
 assert r.retries==1 and r.waited>=.2
 assert 'SECRET' not in json.dumps(r.report())

def test_range_limit_split_preserves_cover():
 raw=RPC();raw.max_range=3;r=wrapped(raw)
 q=dict(address='ctf',fromBlock=hex(21),toBlock=hex(30),topics=[])
 assert r.call('eth_getLogs',[q])==[]
 ok=[(c['from_block'],c['to_block']) for c in raw.calls if c['status']=='PASS']
 expected=21
 for lo,hi in ok:assert lo==expected;expected=hi+1
 assert expected==31 and r.splits>0

def test_permanent_error_precise_no_retry(tmp_path):
 raw=RPC();raw.fail='ARCHIVE_UNAVAILABLE';r=wrapped(raw)
 result=catch_up(r,prior(),cursor(),dict(number=25,hash=H(25)),root=tmp_path)
 assert result['TAIL_SCAN_ROOT_CAUSE']=='ARCHIVE_UNAVAILABLE' and r.retries==0
 assert result['cursor_end']==20 and not result['inventory_through_C_proven']

def test_removed_log_no_checkpoint(tmp_path):
 raw=RPC();raw.removed=True
 result=catch_up(wrapped(raw),prior(),cursor(),dict(number=25,hash=H(25)),root=tmp_path)
 assert result['status']=='BLOCKED' and result['cursor_end']==20
 assert not list(tmp_path.rglob('*.json'))

def test_crash_mid_tranche_then_resume(tmp_path):
 raw=RPC();real=raw.call
 def crash(m,p):
  if m=='eth_getLogs' and int(p[0]['fromBlock'],16)>520:raise KeyboardInterrupt()
  return real(m,p)
 raw.call=crash
 with pytest.raises(KeyboardInterrupt):catch_up(wrapped(raw),prior(),cursor(),dict(number=550,hash=H(550)),root=tmp_path)
 files=list(tmp_path.rglob('*.json'));assert len(files)==1
 cp=json.loads(files[0].read_text());validate_checkpoint(cp,prior());old=cp['inventory_incremental']
 assert old['to_block']==520
 result=catch_up(wrapped(RPC()),prior(),old,dict(number=550,hash=H(550)),root=tmp_path)
 assert result['cursor_start']==520 and result['cursor_end']==550

@pytest.mark.parametrize('mutation',['gap','overlap','checksum','binding'])
def test_checkpoint_corruption_blocks(tmp_path,mutation):
 catch_up(wrapped(RPC()),prior(),cursor(),dict(number=35,hash=H(35)),root=tmp_path)
 cp=json.loads(next(tmp_path.rglob('*.json')).read_text())
 if mutation=='binding':cp['genesis_snapshot_sha256']='bad'
 elif mutation=='checksum':cp['inventory_sha256']='bad'
 else:
  cp['inventory_incremental']['catchup_evidence']['ranges'][0][0]+=1 if mutation=='gap' else -1
  from app.live.genesis_ledger import digest
  cp['inventory_sha256']=digest(cp['inventory_incremental'])
 with pytest.raises(CatchupBlocked):validate_checkpoint(cp,prior())


def test_retry_exhaustion_is_bounded():
 raw=RPC()
 def fail(m,p):
  raw.calls.append(dict(status='FAILED',error_category='RATE_LIMIT',http_status=429));raise RuntimeError('SECRET')
 raw.call=fail;r=wrapped(raw)
 with pytest.raises(CatchupBlocked,match='RATE_LIMIT'):r.call('eth_chainId',[])
 assert r.requests==3 and r.retries==2 and r.rate_limits==3

@pytest.mark.parametrize('kind',['gap','overlap'])
def test_scanner_incomplete_cover_never_published(tmp_path,monkeypatch,kind):
 import app.live.inventory_catchup as module
 real=module.scan_ctf
 def bad(*a,**k):
  r=real(*a,**k)
  if kind=='gap':r['diagnostics']['ranges_completed'].pop()
  else:r['diagnostics']['ranges_completed'].append(r['diagnostics']['ranges_completed'][0])
  return r
 monkeypatch.setattr(module,'scan_ctf',bad)
 r=catch_up(wrapped(RPC()),prior(),cursor(),dict(number=35,hash=H(35)),root=tmp_path)
 assert r['TAIL_SCAN_ROOT_CAUSE']=='COVERAGE_GAP_OR_OVERLAP' and r['cursor_end']==20
 assert not list(tmp_path.rglob('*.json'))

def test_v2_resume_loader_verifies_parent_chain(tmp_path):
 from analysis.qualify_post_genesis import save_inventory_cursor,load_inventory_cursor
 save_inventory_cursor(tmp_path,prior(),cursor())
 catch_up(wrapped(RPC()),prior(),cursor(),dict(number=550,hash=H(550)),root=tmp_path)
 assert load_inventory_cursor(tmp_path,prior())['to_block']==550
 parent=next(p for p in tmp_path.rglob('*.json') if p.name.startswith('20_'))
 parent.unlink()  # synthetic test fixture only
 with pytest.raises(ValueError,match='CURSOR_INTEGRITY'):load_inventory_cursor(tmp_path,prior())

def test_readiness_routes_large_backlog_without_scanning(monkeypatch):
 import analysis.qualify_post_b_proofs as q
 monkeypatch.setattr(q,'qualify_finalized',lambda r:dict(anchor=dict(number=55000,hash=H(55000))))
 def forbidden(*a,**k):raise AssertionError('readiness must not bootstrap')
 monkeypatch.setattr(q,'scan_ctf',forbidden)
 with pytest.raises(q.TailScanFailure,match='BOOTSTRAP_CATCHUP_REQUIRED') as exc:q.prepare_finalized_inventory(RPC(),prior(),cursor())
 assert exc.value.inventory_catchup['backlog_blocks']==54980
 assert exc.value.inventory_catchup['ranges_completed']==0

def test_future_timeout_override_never_proves_post_c(tmp_path):
 from app.live.freshness_policy import freshness_policy
 with freshness_policy(1300):r=catch_up(wrapped(RPC()),prior(),cursor(),dict(number=25,hash=H(25)),root=tmp_path)
 assert r['inventory_through_C_proven'] and not r['current_inventory_proven']
 assert r['post_C_completeness']=='NO_COMMON_POST_C_COMPLETENESS_WATERMARK'

def test_canonical_recheck_failure_no_checkpoint(tmp_path):
 raw=RPC();real=raw.call;count=[0]
 def reorg(m,p):
  value=real(m,p)
  if m=='eth_getBlockByNumber' and p[0]==hex(25):
   count[0]+=1
   if count[0]>=3:value['hash']=H(26)
  return value
 raw.call=reorg
 r=catch_up(wrapped(raw),prior(),cursor(),dict(number=25,hash=H(25)),root=tmp_path)
 assert r['status']=='BLOCKED' and r['cursor_end']==20
 assert not list(tmp_path.rglob('*.json'))


def test_worker_cycle_genesis_unchanged_no_credentials(tmp_path,monkeypatch):
 import analysis.run_inventory_catchup as q
 from analysis.qualify_post_genesis import save_inventory_cursor
 p=prior();p.update(phase='GENESIS_RECONCILED',event_count=0)
 db=tmp_path/'runtime/d6_genesis.db';db.parent.mkdir();db.write_bytes(b'IMMUTABLE_GENESIS_FIXTURE')
 save_inventory_cursor(tmp_path,p,cursor())
 monkeypatch.setattr(q,'read_genesis',lambda path:p)
 monkeypatch.setattr(q,'expected_wallet',lambda:RPC.wallet)
 raw=RPC();raw.close=lambda:None
 monkeypatch.setattr(q,'PublicRPC',lambda *a,**k:raw)
 monkeypatch.setattr(q,'CatchupRPC',lambda rpc:wrapped(rpc))
 monkeypatch.setattr(q,'qualify_finalized',lambda rpc:dict(anchor=dict(number=25,hash=H(25))))
 r=q.cycle(tmp_path,'https://example.invalid')
 assert r['status']=='PASS_SCOPED_CATCHUP' and r['genesis_unchanged']
 assert not r['private_key_loaded'] and not r['credentials_loaded'] and not r['submit_allowed']
 assert db.read_bytes()==b'IMMUTABLE_GENESIS_FIXTURE'


def test_worker_refuses_live_flags_before_any_io(tmp_path,monkeypatch):
 import analysis.run_inventory_catchup as q
 monkeypatch.setattr(q,'ROOT',tmp_path)
 monkeypatch.setattr(q.sys,'argv',['worker','--bootstrap'])
 monkeypatch.setenv('REAL_ORDERS_ENABLED','true')
 assert q.main()==2 and not list(tmp_path.iterdir())


def test_worker_lock_survives_normal_release_and_excludes_second_writer(tmp_path):
 from analysis.run_inventory_catchup import worker_lock
 with worker_lock(tmp_path):
  with pytest.raises(OSError):
   with worker_lock(tmp_path):pass
 with worker_lock(tmp_path):pass


def test_no_shadow_generation_sample_when_no_generation(monkeypatch):
 import asyncio
 import analysis.qualify_post_genesis as q
 from app.live.shadow_calibration import ShadowCalibration,calibration_session
 recorder=ShadowCalibration(shares=5)
 monkeypatch.setattr(q,'read_genesis',lambda *a:None)
 with calibration_session(recorder):r=asyncio.run(q.run(False,health_contract=True))
 assert not r['generation_created'] and not r['downstream_checks_qualified']
 assert recorder.report()['generations']==[]
