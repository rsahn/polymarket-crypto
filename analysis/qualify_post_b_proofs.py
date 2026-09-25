"""Manual public-only evidence probe. Never grants readiness or edits Genesis."""
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'backend'))
from app.live.collateral_onchain import PublicRPC,validate_rpc_endpoint
from app.live.genesis_ledger import read_genesis,expected_wallet
from app.live.ctf_inventory_probe import scan_ctf
from app.live.production_readonly import now_ms
from app.live.deposit_qualification import write_report
from analysis.qualify_post_genesis import load_inventory_cursor,discover_book


def header(value):
    if not isinstance(value,dict):raise ValueError('HEADER')
    if not all(isinstance(value.get(k),str) and re.fullmatch('0x[0-9a-fA-F]+',value[k]) for k in ('number','timestamp')):
        raise ValueError('HEADER')
    if not isinstance(value.get('hash'),str) or not re.fullmatch('0x[0-9a-fA-F]{64}',value['hash']):raise ValueError('HEADER')
    return {'number':int(value['number'],16),'hash':value['hash'].lower(),'timestamp':int(value['timestamp'],16)}


def qualify_finalized(rpc):
    started=now_ms()
    try:
        if rpc.call('eth_chainId',[])!='0x89':raise ValueError()
        b=header(rpc.call('eth_getBlockByNumber',['finalized',False]))
        h=header(rpc.call('eth_getBlockByNumber',['latest',False]))
        check=header(rpc.call('eth_getBlockByNumber',[hex(b['number']),False]))
        second=header(rpc.call('eth_getBlockByNumber',['finalized',False]))
        if h['number']<b['number'] or check!=b or second['number']<b['number']:raise ValueError()
        if second['number']==b['number'] and second!=b:raise ValueError()
        if any(x['timestamp']*1000>started for x in (b,h,check)):raise ValueError()
        return dict(status='PASS_PROVIDER_FINALIZED_READ',chain_id=137,anchor=b,
                    observed_ms=started,finished_ms=now_ms(),independent_consensus_proven=False)
    except Exception:raise ValueError('FINALIZED_UNPROVEN') from None


def evaluate_post_b(e,*,now):
    r=dict(current_inventory_proven=False,ready_for_arm=False,submit_allowed=False,
           reason='POST_B_SCHEMA_INVALID',scope='IDENTIFIED_CTF_AT_HEAD_WITNESS_ONLY')
    fail=lambda reason:{**r,'reason':reason}
    try:
        if e.get('anchored_inventory_proven') is not True:return fail('ANCHORED_INVENTORY_UNPROVEN')
        for k in ('anchor_number','tail_end','witness_number','generation','scan_observed_ms','witness_observed_ms','anchor_observed_ms'):
            if type(e[k]) is not int or e[k]<0:return r
        if type(now) is not int or e['generation']<1:return r
        for k in ('anchor_hash','anchor_rechecked_hash','tail_hash','witness_hash'):
            if not isinstance(e[k],str) or not re.fullmatch('0x[0-9a-f]{64}',e[k]):return r
        if e['anchor_hash']!=e['anchor_rechecked_hash']:return fail('ANCHOR_REORG')
        if e['tail_end']<e['anchor_number']:return r
        if e['witness_number']>e['tail_end']:return fail('POST_B_TAIL_ADVANCED')
        if e['witness_number']<e['tail_end'] or e['witness_hash']!=e['tail_hash']:return fail('TAIL_REORG')
        expected=e['anchor_number']+1
        for start,end in e['ranges']:
            if type(start) is not int or type(end) is not int or start!=expected or end<start or end>e['tail_end']:
                return fail('TAIL_GAP_OR_OVERLAP')
            expected=end+1
        if expected!=e['tail_end']+1:return fail('TAIL_GAP_OR_OVERLAP')
        if e['tail_complete'] is not True:return fail('TAIL_INCOMPLETE')
        account=e['account']
        if set(account)!={'balance','orders','trades','positions'}:return fail('ACCOUNT_GENERATION_PARTIAL')
        for p in account.values():
            if p.get('complete') is not True or type(p.get('generation')) is not int or p['generation']!=e['generation']:
                return fail('ACCOUNT_GENERATION_PARTIAL')
        times=[e['witness_observed_ms'],e['anchor_observed_ms']]+[p['observed_ms'] for p in account.values()]
        if any(type(t) is not int or not 0<=now-t<=500 for t in times):return fail('GENERATION_STALE_500MS')
        if e['scan_observed_ms']>min(times):return fail('ACQUISITION_ORDER_INVALID')
        return {**r,'current_inventory_proven':True,'reason':'SCOPED_HEAD_WITNESS_PROVEN',
                'scan_observed_ms':e['scan_observed_ms'],'witness_observed_ms':e['witness_observed_ms']}
    except (KeyError,ValueError,TypeError,AttributeError):return r


def fixed_scan(rpc,previous,target):
    """Single bounded range, no head reselection and no Genesis fallback."""
    check=header(rpc.call('eth_getBlockByNumber',[hex(previous['to_block']),False]))
    if check['hash']!=previous['block_hash']:raise ValueError('CURSOR_REORG')
    end=target['number'];start=previous['to_block']+1
    if end<previous['to_block']:raise ValueError('CURSOR_AHEAD_OF_FINALIZED')
    if end==previous['to_block']:
        if target['hash']!=previous['block_hash']:raise ValueError('CURSOR_REORG')
        return previous,[]
    captured={};started=now_ms()
    result=scan_ctf(rpc,start,end,set(previous['balances']),capture=captured)
    if result['status']!='PASS_SCOPED_READS' or result['block_hash']!=target['hash']:raise ValueError('TAIL_SCAN_FAILED')
    if result['events_count'] or any(int(v) for v in captured['balances'].values()):raise ValueError('RECOVERY_REQUIRED')
    ranges=[[i,min(i+rpc.log_window-1,end)] for i in range(start,end+1,rpc.log_window)]
    return {**result,'balances':captured['balances'],'observed_ms':started},ranges


def public_inventory(rpc,prior,cursor,qualified):
    b=qualified['anchor']
    original=prior['snapshot']
    if header(rpc.call('eth_getBlockByNumber',[hex(original['block_number']),False]))['hash']!=original['block_hash']:
        raise ValueError('GENESIS_ANCHOR_CHANGED')
    if cursor['events_count'] or any(int(v) for v in cursor['balances'].values()):raise ValueError('RECOVERY_REQUIRED')
    anchored,pre_ranges=fixed_scan(rpc,cursor,b)
    h=header(rpc.call('eth_getBlockByNumber',['latest',False]))
    tail,ranges=fixed_scan(rpc,anchored,h)
    witness_start=now_ms();w=header(rpc.call('eth_getBlockByNumber',['latest',False]))
    anchor_start=now_ms();check=header(rpc.call('eth_getBlockByNumber',[hex(b['number']),False]))
    e=dict(anchored_inventory_proven=True,anchor_number=b['number'],anchor_hash=b['hash'],anchor_rechecked_hash=check['hash'],
           tail_end=h['number'],tail_hash=h['hash'],ranges=ranges,tail_complete=True,
           witness_number=w['number'],witness_hash=w['hash'],scan_observed_ms=tail['observed_ms'],
           witness_observed_ms=witness_start,anchor_observed_ms=anchor_start,generation=1,account={})
    return dict(cursor_previous=cursor['to_block'],anchor_catchup_ranges=pre_ranges,
                proof=e,evaluation=evaluate_post_b(e,now=now_ms()),
                account_status='NOT_ACQUIRED_PUBLIC_PROOF_PHASE',attempts=1)


async def capture_ws(audit):
    book=None;task=None
    try:
        book=await discover_book(audit);task=asyncio.create_task(book.run())
        # Bounded observation only; no reconnect or parser acceptance changes.
        stop=asyncio.get_running_loop().time()+30
        while asyncio.get_running_loop().time()<stop and not task.done():
            if book.diagnostics.get('regression_event'):break
            await asyncio.sleep(.05)
        snapshot=book.read()
        return {k:snapshot[k] for k in ('state','available','connected','synchronized','fresh','reason','diagnostics','messages_received')}
    except Exception:return {'status':'BLOCKED','reason':'PUBLIC_WS_CAPTURE_FAILED'}
    finally:
        if task:
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass


async def run(target=False):
    flags={k:os.getenv(k,'false').strip().lower() for k in ('REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED')}
    report=dict(phase='D6_POST_B_AND_WS_PROOFS',flags=flags,ready_for_arm=False,submit_allowed=False,
                credentials_loaded=False,private_key_loaded=False,genesis_created=False,
                finalized={'status':'NOT_RUN'},inventory={'status':'NOT_RUN'},book={'status':'NOT_RUN'})
    if not target or any(v!='false' for v in flags.values()):
        report['reason']='TARGET_WITH_FLAGS_FALSE_REQUIRED';return report
    rpc=None;audit=[];ws_task=None
    try:
        endpoint=validate_rpc_endpoint(os.getenv('POLYGON_ARCHIVE_RPC_URL'))
        prior=read_genesis(ROOT/'runtime/d6_genesis.db')
        rpc=PublicRPC(expected_wallet(),endpoint=endpoint,allow_finalized=True);rpc.log_window=10
        # WS is independent of provider finalized support and uses no credentials.
        ws_task=asyncio.create_task(capture_ws(audit))
        try:
            qualified=await asyncio.to_thread(qualify_finalized,rpc);report['finalized']=qualified
        except ValueError:
            report['finalized']={'status':'BLOCKED','reason':'FINALIZED_UNPROVEN'}
        if report['finalized']['status']=='PASS_PROVIDER_FINALIZED_READ':
            try:
                cursor=load_inventory_cursor(ROOT,prior)
                report['inventory']=await asyncio.to_thread(public_inventory,rpc,prior,cursor,qualified)
            except Exception as exc:
                allowed={'CURSOR_REORG','CURSOR_AHEAD_OF_FINALIZED','TAIL_SCAN_FAILED','RECOVERY_REQUIRED',
                         'GENESIS_ANCHOR_CHANGED','INVENTORY_CURSOR_REQUIRED','CURSOR_INTEGRITY','CURSOR_CONFLICT'}
                reason=exc.args[0] if exc.args and isinstance(exc.args[0],str) and exc.args[0] in allowed else 'PUBLIC_INVENTORY_PROOF_FAILED'
                report['inventory']={'status':'BLOCKED','reason':reason}
        report['book']=await ws_task
        report['genesis_unchanged']=read_genesis(ROOT/'runtime/d6_genesis.db')['last_hash']==prior['last_hash']
    except Exception:report['reason']='LOCAL_CONFIGURATION_OR_PROOF_FAILED'
    finally:
        if ws_task and not ws_task.done():
            ws_task.cancel()
            try:await ws_task
            except asyncio.CancelledError:pass
        report['rpc_calls']=rpc.calls if rpc else [];report['get_requests']=audit
    report['status']='EVIDENCE_ONLY_NOT_READY'
    return report


def main():
    if sys.argv[1:]!=['--target-machine']:return 2
    report=asyncio.run(run(True))
    path=ROOT/('D6_POST_B_WS_PROOFS_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')+'.json')
    write_report(path,report);print(json.dumps(report,indent=2));print('REPORT_FILE='+path.name)


if __name__=='__main__':raise SystemExit(main())
