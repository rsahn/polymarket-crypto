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
