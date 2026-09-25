"""Public code-onset boundary and scoped CTF snapshot for a D6 forward genesis."""
import re
from .ctf_inventory_probe import scan_ctf


def code_onset(rpc,end):
    def present(n):
        code=rpc.call('eth_getCode',[rpc.wallet,hex(n)])
        if not isinstance(code,str) or not re.fullmatch('0x(?:[0-9a-fA-F]{2})*',code):raise ValueError('CODE_SCHEMA')
        return code!='0x'
    if not present(end) or present(0):raise ValueError('CODE_BOUNDARY_UNAVAILABLE')
    lo,hi=0,end
    while hi-lo>1:
        mid=(lo+hi)//2
        if present(mid):hi=mid
        else:lo=mid
    if present(hi-1) or not present(hi):raise ValueError('CODE_BOUNDARY_CHANGED')
    return hi


def conditional_snapshot(rpc,known):
    if rpc.call('eth_chainId',[])!='0x89':raise ValueError('CHAIN')
    head=rpc.call('eth_getBlockByNumber',['latest',False]);end=int(head['number'],16)
    start=code_onset(rpc,end)
    if end-start>=50000:raise ValueError('CTF_RANGE_REQUIRES_REVIEWED_CHUNK_MANIFEST')
    captured={};result=scan_ctf(rpc,start,end,known,capture=captured)
    if result['status']!='PASS_SCOPED_READS':raise ValueError('CTF_FAILED')
    return {**result,'balances':captured['balances'],'start_boundary':'WALLET_CODE_ONSET_READ',
            'boundary_assumption':'NO_CODE_DISAPPEARANCE_OR_COUNTERFACTUAL_CTF_TRANSFERS_COVERED',
            'block_timestamp':int(head['timestamp'],16)}
