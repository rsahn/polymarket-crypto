"""Public code-onset boundary and scoped CTF snapshot for a D6 forward genesis."""
import re
from .ctf_inventory_probe import scan_ctf


class DiscoveryBlocked(ValueError):
    """Only internally selected reason codes and public validated block metadata."""
    def __init__(self, reason, diagnostics=None):
        super().__init__(reason)
        self.reason = reason
        self.diagnostics = dict(diagnostics or {})


def code_onset(rpc,end):
    def present(n):
        code=rpc.call('eth_getCode',[rpc.wallet,hex(n)])
        if not isinstance(code,str) or not re.fullmatch('0x(?:[0-9a-fA-F]{2})*',code):raise DiscoveryBlocked('CODE_SCHEMA')
        return code!='0x'
    if not present(end) or present(0):raise DiscoveryBlocked('CODE_BOUNDARY_UNAVAILABLE')
    lo,hi=0,end
    while hi-lo>1:
        mid=(lo+hi)//2
        if present(mid):hi=mid
        else:lo=mid
    if present(hi-1) or not present(hi):raise DiscoveryBlocked('CODE_BOUNDARY_CHANGED')
    return hi


def conditional_snapshot(rpc,known):
    diagnostics={'logs_started':False}
    stage='CHAIN_OR_HEAD_READ_UNAVAILABLE'
    try:
        if rpc.call('eth_chainId',[])!='0x89':raise DiscoveryBlocked('CHAIN_MISMATCH')
        head=rpc.call('eth_getBlockByNumber',['latest',False])
        end=int(head['number'],16)
        if end<1 or not re.fullmatch('0x[0-9a-fA-F]{64}',head['hash']):
            raise DiscoveryBlocked('HEAD_SCHEMA')
        diagnostics.update(to_block=end,block_hash=head['hash'])
        stage='CODE_BOUNDARY_READ_UNAVAILABLE'
        start=code_onset(rpc,end)
        diagnostics.update(from_block=start,block_count=end-start+1,maximum_blocks=50000)
        if end-start>=50000:
            raise DiscoveryBlocked('CTF_RANGE_REQUIRES_REVIEWED_CHUNK_MANIFEST')
        stage='CTF_SCAN_UNAVAILABLE'
        diagnostics.pop('logs_started')
        captured={};result=scan_ctf(rpc,start,end,known,capture=captured)
        if result['status']!='PASS_SCOPED_READS':raise DiscoveryBlocked('CTF_FAILED')
        return {**result,'balances':captured['balances'],'start_boundary':'WALLET_CODE_ONSET_READ',
                'boundary_assumption':'NO_CODE_DISAPPEARANCE_OR_COUNTERFACTUAL_CTF_TRANSFERS_COVERED',
                'block_timestamp':int(head['timestamp'],16)}
    except DiscoveryBlocked as exc:
        raise DiscoveryBlocked(exc.reason,diagnostics) from None
    except Exception:
        raise DiscoveryBlocked(stage,diagnostics) from None


def segmented_snapshot(rpc,known):
    """Explicit bounded multi-segment policy; fresh terminal balance snapshot.

    Each scan retains its 50,000 block cap / 500 block RPC windows. A single
    catch-up is allowed, never an unbounded moving-head loop. Earlier balances
    only discover IDs; all IDs are re-read at the terminal reference block.
    """
    from .genesis_ledger import digest
    diagnostics={'policy':'CTF_SEGMENTS_V1','maximum_total_blocks':200000,
                 'maximum_segment_blocks':50000,'maximum_catchup_blocks':5000,
                 'chunk_manifest':[]}
    stage='CHAIN_OR_HEAD_READ_UNAVAILABLE'
    def block(tag):
        value=rpc.call('eth_getBlockByNumber',[tag,False])
        n=int(value['number'],16)
        if n<1 or (tag!='latest' and n!=int(tag,16)) or not re.fullmatch('0x[0-9a-fA-F]{64}',value['hash']):
            raise DiscoveryBlocked('HEAD_SCHEMA')
        int(value['timestamp'],16)
        return value,n
    try:
        if rpc.call('eth_chainId',[])!='0x89':raise DiscoveryBlocked('CHAIN_MISMATCH')
        head,end=block('latest')
        stage='CODE_BOUNDARY_READ_UNAVAILABLE'
        start=code_onset(rpc,end)
        diagnostics.update(from_block=start,to_block=end,block_count=end-start+1)
        if not 0<=start<=end or end-start+1>200000:
            raise DiscoveryBlocked('CTF_TOTAL_BUDGET_EXCEEDED')
        # Plan the full initial coverage before issuing any event request.
        plan=[(lo,min(lo+49999,end)) for lo in range(start,end+1,50000)]
        diagnostics['planned_segments']=[{'from_block':a,'to_block':b} for a,b in plan]
        assets=set(known);events=0
        def scan(lo,hi,kind):
            nonlocal events
            captured={}
            result=scan_ctf(rpc,lo,hi,assets,capture=captured)
            if result['status']!='PASS_SCOPED_READS':raise DiscoveryBlocked('CTF_SEGMENT_FAILED')
            assets.update(captured['balances'])
            if len(assets)>10000:raise DiscoveryBlocked('CTF_ASSET_BUDGET_EXCEEDED')
            events+=result['events_count']
            diagnostics['chunk_manifest'].append({'from_block':lo,'to_block':hi,'block_hash':result['block_hash'],'kind':kind})
            return result,captured['balances']
        stage='CTF_SEGMENT_READ_UNAVAILABLE'
        for lo,hi in plan:scan(lo,hi,'DISCOVERY')
        if diagnostics['chunk_manifest'][-1]['block_hash']!=head['hash']:
            raise DiscoveryBlocked('CTF_REFERENCE_CHANGED')
        fresh,terminal=block('latest')
        if terminal<end or terminal-end>5000 or terminal-start+1>200000:
            raise DiscoveryBlocked('CTF_CATCHUP_BUDGET_OR_HEAD_INVALID')
        # If head has not advanced, rescan its single block for a balance refresh.
        result,balances=scan(end+1 if terminal>end else end,terminal,'FINAL_BALANCE_REFRESH')
        if result['block_hash']!=fresh['hash']:raise DiscoveryBlocked('CTF_REFERENCE_CHANGED')
        for item in diagnostics['chunk_manifest']:
            observed,_=block(hex(item['to_block']))
            if observed['hash']!=item['block_hash']:raise DiscoveryBlocked('CTF_REFERENCE_CHANGED')
        manifest=diagnostics['chunk_manifest']
        return {**result,'complete':False,'from_block':start,'to_block':terminal,
                'balances':balances,'events_count':events,'assets_checked':len(assets),
                'discovered_outside_local_journal':len(assets-set(known)),
                'start_boundary':'WALLET_CODE_ONSET_READ','block_timestamp':int(fresh['timestamp'],16),
                'boundary_assumption':'NO_CODE_DISAPPEARANCE_OR_COUNTERFACTUAL_CTF_TRANSFERS_COVERED',
                'chunk_manifest':manifest,'chunk_manifest_sha256':digest(manifest),
                'segment_policy':diagnostics['policy'],
                'events_count_scope':'SUM_OF_SCANS_INCLUDING_POSSIBLE_SINGLE_BLOCK_REFRESH_OVERLAP'}
    except DiscoveryBlocked as exc:
        raise DiscoveryBlocked(exc.reason,diagnostics) from None
    except Exception:
        raise DiscoveryBlocked(stage,diagnostics) from None
