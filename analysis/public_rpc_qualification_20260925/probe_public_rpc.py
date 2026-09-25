"""Bounded public-only alternative-provider experiment. No local state writes."""
import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'backend')]
from app.live.collateral_onchain import PublicRPC,CTF
from app.live.genesis_ledger import expected_wallet
from eth_utils import keccak
rpc=PublicRPC(expected_wallet(),pooled=True)
report={'scope':'PUBLIC_RPC_PROBE_ONLY_NO_READINESS_NO_CREDENTIALS','provider':'https://polygon.drpc.org','runs':[]}
try:
    assert rpc.call('eth_chainId',[])=='0x89'
    time.sleep(.2)
    head=rpc.call('eth_getBlockByNumber',['latest',False]);end=int(head['number'],16)
    signatures=['0x'+keccak(text=s).hex() for s in ('TransferSingle(address,address,address,uint256,uint256)','TransferBatch(address,address,address,uint256[],uint256[])')]
    for size in (10,1,10,1):
        time.sleep(.2)
        rows=rpc.call('eth_getLogs',[dict(address=CTF,fromBlock=hex(end-size+1),toBlock=hex(end),topics=[signatures,None,None,'0x'+rpc.wallet[2:].lower().rjust(64,'0')])])
        report['runs'].append(dict(blocks=size,elapsed_ms=rpc.calls[-1]['elapsed_ms'],rows=len(rows) if isinstance(rows,list) else None))
    time.sleep(.2)
    again=rpc.call('eth_getBlockByNumber',[hex(end),False])
    report['fixed_hash_unchanged']=again['hash']==head['hash']
except Exception:
    report['status']='BLOCKED_NO_FALLBACK'
finally:
    report['rpc_calls']=rpc.calls
    rpc.close()
print(json.dumps(report,indent=2))
