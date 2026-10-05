"""Read-only supplemental evidence; resumes archived ranges, never submits transactions."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import time
from eth_utils import keccak
from scan_deposit_session_history import RPC, WALLET, digest, decode

ROOT = Path(__file__).resolve().parent
START, END = 94331195, 94902121
BEACON = '0x7a18edfe055488a3128f01f563e5b479d92ffc3a'
FORWARDER = '0x6dd7b5ea91608c60cd4a1944432cc30ee5a6d1ca'
IMPL = '0xf7f27c29e60fe6325bef8da7f93250353d2e3294'
SECONDARY = 'https://polygon.api.onfinality.io/public'
PRIMARY = 'https://tenderly.rpc.polygon.community'

def normalize(rows):
    fields = ('address', 'topics', 'data', 'blockHash', 'blockNumber',
              'transactionHash', 'transactionIndex', 'logIndex', 'removed')
    return sorted([{k:r[k] for k in fields} for r in rows],
                  key=lambda r:(int(r['blockNumber'],16),int(r['logIndex'],16)))

def validate(item, lo, hi, address):
    if item['from_block'] != lo or item['to_block'] != hi or item['sha256'] != digest(item['logs']):
        raise ValueError('CHECKPOINT_INTEGRITY')
    rows=item['logs']; seen=set()
    if not isinstance(rows,list) or len(rows)>=10000:raise ValueError('LOG_CAP_OR_SCHEMA')
    for row in rows:
        if row['address'].lower()!=address or row['removed'] is not False or not lo<=int(row['blockNumber'],16)<=hi:
            raise ValueError('LOG_SCOPE')
        key=(row['blockHash'],row['logIndex'])
        if key in seen:raise ValueError('DUPLICATE_LOG')
        seen.add(key)
    return rows

def resume_range(folder, url, address, lo, hi):
    path=folder/f'range_{lo}_{hi}.json'
    if path.exists():
        item=json.loads(path.read_text(encoding='utf-8'));validate(item,lo,hi,address)
        return item
    rpc=RPC(url)
    if url==SECONDARY:time.sleep(7)
    try:
        rows=rpc.call('eth_getLogs',[dict(address=address,fromBlock=hex(lo),toBlock=hex(hi))])
        item=dict(from_block=lo,to_block=hi,sha256=digest(rows),count=len(rows),logs=rows,provider=url)
        validate(item,lo,hi,address)
        with path.open('x',encoding='utf-8') as f:json.dump(item,f,indent=2)
        return item
    except Exception as exc:
        return dict(from_block=lo,to_block=hi,error_type=type(exc).__name__)

def run(mode):
    secondary=mode=='secondary'
    folder=ROOT/('session_history_onfinality_20261003' if secondary else 'session_beacon_history_20261003')
    folder.mkdir(exist_ok=True)
    url=SECONDARY if secondary else PRIMARY
    address=WALLET if secondary else BEACON
    rpc=RPC(url)
    if rpc.call('eth_chainId',[])!='0x89':raise ValueError('CHAIN')
    anchor=rpc.call('eth_getBlockByNumber',[hex(END),False])
    expected=json.loads((ROOT/'session_history_tail_20261003.json').read_text())['anchor_hash']
    if anchor['hash']!=expected:raise ValueError('ANCHOR')
    ranges=[(lo,min(lo+4999,END)) for lo in range(START,END+1,5000)]
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=1 if secondary else 3) as pool:
        pending={pool.submit(resume_range,folder,url,address,lo,hi):(lo,hi) for lo,hi in ranges}
        for future in concurrent.futures.as_completed(pending):
            results.append(future.result())
            summary=[{k:v for k,v in r.items() if k!='logs'} for r in sorted(results,key=lambda r:r['from_block'])]
            (folder/'resume_progress.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
            print(json.dumps(dict(mode=mode,completed=len(results),failed=sum('error_type' in r for r in results))),flush=True)
    complete=all('error_type' not in r for r in results)
    report=dict(mode=mode,from_block=START,to_block=END,anchor_hash=expected,
        range_coverage_complete=complete,failed_ranges=[r for r in results if 'error_type' in r],
        observed_ms=time.time_ns()//1000000,read_only=True)
    logs=[row for r in results for row in r.get('logs',[])]
    if secondary:
        primary=[]
        for path in sorted((ROOT/'session_history_tenderly_20261003').glob('range_*.json')):
            item=json.loads(path.read_text());primary.extend(validate(item,item['from_block'],item['to_block'],WALLET))
        primary.extend(json.loads((ROOT/'session_history_tail_20261003.json').read_text())['logs'])
        report.update(primary_secondary_results_identical=complete and normalize(primary)==normalize(logs),
            primary_logs=len(primary),secondary_logs=len(logs),
            secondary_normalized_digest=digest(normalize(logs)),primary_normalized_digest=digest(normalize(primary)))
    else:
        report.update(logs=normalize(logs),upgrade_events=[r for r in logs if r['topics'][0]=='0x'+keccak(text='Upgraded(address)').hex()])
        code_records=[]
        for address in (WALLET,BEACON,FORWARDER,IMPL):
            for block in (START,END):
                code=rpc.call('eth_getCode',[address,hex(block)])
                code_records.append(dict(address=address,block=block,code=code,keccak256='0x'+keccak(bytes.fromhex(code[2:])).hex()))
        (folder/'code_records.json').write_text(json.dumps(code_records,indent=2),encoding='utf-8')
        report['implementation_calls']=[dict(block=b,value=rpc.call('eth_call',[dict(to=BEACON,data='0x5c60da1b'),hex(b)])) for b in (START,END)]
        report['all_mutation_paths_proven']=False
    if secondary:time.sleep(7)
    if rpc.call('eth_getBlockByNumber',[hex(END),False])['hash']!=expected:raise ValueError('ANCHOR_CHANGED')
    (folder/'supplement_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('logs','upgrade_events')}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('secondary','beacon'))
    run(p.parse_args().mode)
