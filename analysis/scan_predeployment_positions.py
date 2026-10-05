"""Resume incoming ERC1155 logs to the counterfactual wallet before deployment.

Only public read-only RPC calls. A complete empty interval rules out receipts of
standard event-emitting ERC1155 positions; no conclusion about off-chain orders.
"""
import concurrent.futures
import json
from pathlib import Path
import time
from scan_deposit_session_history import RPC,digest
from reconcile_legacy_chain import START,SINGLE,BATCH,PAD

BASE=Path(__file__).resolve().parent/'predeployment_positions_20261003'
PROVIDER='https://tenderly.rpc.polygon.community'

def validate(item,lo,hi):
    if item['from_block']!=lo or item['to_block']!=hi or item['sha256']!=digest(item['logs']):raise ValueError('CHECKPOINT')
    if type(item['logs']) is not list or len(item['logs'])>=10000:raise ValueError('CAP_OR_SCHEMA')
    seen=set()
    for row in item['logs']:
        if row['removed'] is not False or not lo<=int(row['blockNumber'],16)<=hi or row['topics'][0] not in (SINGLE,BATCH) or len(row['topics'])!=4 or row['topics'][3].lower()!=PAD:raise ValueError('LOG_SCOPE')
        key=(row['blockHash'],row['logIndex'])
        if key in seen:raise ValueError('DUPLICATE')
        seen.add(key)
    return item

def fetch(bounds):
    lo,hi=bounds;path=BASE/f'range_{lo:09d}_{hi:09d}.json'
    if path.exists():return validate(json.loads(path.read_text()),lo,hi)
    try:
        rpc=RPC(PROVIDER)
        rows=rpc.call('eth_getLogs',[dict(fromBlock=hex(lo),toBlock=hex(hi),topics=[[SINGLE,BATCH],None,None,PAD])])
        item=validate(dict(from_block=lo,to_block=hi,logs=rows,sha256=digest(rows)),lo,hi)
        with path.open('x',encoding='utf-8') as f:json.dump(item,f)
        return item
    except Exception as exc:return dict(from_block=lo,to_block=hi,error_type=type(exc).__name__)

def main():
    BASE.mkdir(exist_ok=True);rpc=RPC(PROVIDER)
    if rpc.call('eth_chainId',[])!='0x89':raise ValueError('CHAIN')
    anchor=rpc.call('eth_getBlockByNumber',[hex(START-1),False])
    # Provider explicitly reports maxAllowedRange=30000. No original session range is rescanned.
    ranges=[(lo,min(lo+29999,START-1)) for lo in range(0,START,30000)]
    summary=[];logs=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for i,item in enumerate(pool.map(fetch,ranges),1):
            logs.extend(item.get('logs',[]));summary.append({k:v for k,v in item.items() if k!='logs'})
            if i%50==0 or i==len(ranges):
                (BASE/'progress.json').write_text(json.dumps(summary),encoding='utf-8')
                print(json.dumps(dict(completed=i,total=len(ranges),failed=sum('error_type' in s for s in summary),logs=len(logs))),flush=True)
    if rpc.call('eth_getBlockByNumber',[hex(START-1),False])['hash']!=anchor['hash']:raise ValueError('ANCHOR_CHANGED')
    complete=all('error_type' not in s for s in summary)
    report=dict(provider=PROVIDER,from_block=0,to_block=START-1,anchor_hash=anchor['hash'],
        incoming_erc1155_logs=logs,coverage_complete=complete,zero_predeployment_standard_erc1155_receipts_proven=complete and not logs,
        failed_ranges=[s for s in summary if 'error_type' in s],manifest_digest=digest(summary),observed_ms=time.time_ns()//1000000,
        limitations=['Trusted canonical RPC log completeness and standard ERC1155 mandatory transfer event semantics.',
            'Not a statement about pending off-chain settlements, malicious nonstandard token contracts, or authorizations.'])
    (BASE/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))

if __name__=='__main__':main()
