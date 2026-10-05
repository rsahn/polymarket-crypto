"""Read-only bounded transfer/receipt reconstruction, separate from account certification."""
import concurrent.futures
from collections import defaultdict
import json
from pathlib import Path
from eth_abi import decode
from eth_utils import keccak
from scan_deposit_session_history import RPC,WALLET,digest

BASE=Path(__file__).resolve().parent/'legacy_chain_reconciliation_20261003'
START=94331195
COLLATERAL='0xc011a7e12a19f7b1f670d46f03b03f3342e82dfb'
TRANSFER='0x'+keccak(text='Transfer(address,address,uint256)').hex()
SINGLE='0x'+keccak(text='TransferSingle(address,address,address,uint256,uint256)').hex()
BATCH='0x'+keccak(text='TransferBatch(address,address,address,uint256[],uint256[])').hex()
PAD='0x'+WALLET[2:].rjust(64,'0')

def changes(rows):
    cash=0;positions=defaultdict(int)
    for r in rows:
        t=r['topics'];raw=bytes.fromhex(r['data'][2:])
        if t[0]==TRANSFER:
            if r['address'].lower()!=COLLATERAL or len(t)!=3 or len(raw)!=32:raise ValueError('CASH_LOG')
            amount=int.from_bytes(raw,'big');cash+=amount*(int(t[2].lower()==PAD)-int(t[1].lower()==PAD))
        elif t[0] in (SINGLE,BATCH):
            if len(t)!=4:raise ValueError('POSITION_LOG')
            if t[0]==SINGLE:
                token,amount=decode(['uint256','uint256'],raw);ids,amounts=[token],[amount]
            else:ids,amounts=decode(['uint256[]','uint256[]'],raw)
            if len(ids)!=len(amounts):raise ValueError('POSITION_ARRAY_LENGTH')
            sign=int(t[3].lower()==PAD)-int(t[2].lower()==PAD)
            for token,amount in zip(ids,amounts):positions[(r['address'].lower(),str(token))]+=amount*sign
        else:raise ValueError('UNEXPECTED_TOPIC')
    return cash,dict(positions)

def main():
    BASE.mkdir(exist_ok=True);rpc=RPC('https://tenderly.rpc.polygon.community')
    anchorfile=BASE/'anchor.json'
    if anchorfile.exists():anchor=json.loads(anchorfile.read_text())
    else:
        anchor=rpc.call('eth_getBlockByNumber',['finalized',False]);anchorfile.write_text(json.dumps(anchor),encoding='utf-8')
    end=int(anchor['number'],16)
    queries={
        'cash_out':dict(address=COLLATERAL,topics=[TRANSFER,PAD]),
        'cash_in':dict(address=COLLATERAL,topics=[TRANSFER,None,PAD]),
        'position_out':dict(topics=[[SINGLE,BATCH],None,PAD]),
        'position_in':dict(topics=[[SINGLE,BATCH],None,None,PAD])}
    def read(job):
        name,lo,hi=job;path=BASE/f'{name}_{lo}_{hi}.json'
        if path.exists():item=json.loads(path.read_text())
        else:
            r=RPC('https://tenderly.rpc.polygon.community')
            rows=r.call('eth_getLogs',[dict(**queries[name],fromBlock=hex(lo),toBlock=hex(hi))])
            item=dict(name=name,from_block=lo,to_block=hi,logs=rows,sha256=digest(rows))
            if len(rows)>=10000:raise ValueError('POSSIBLE_CAP')
            path.write_text(json.dumps(item,indent=2),encoding='utf-8')
        if item['sha256']!=digest(item['logs']):raise ValueError('CHECKPOINT_HASH')
        for row in item['logs']:
            if row['removed'] is not False or not lo<=int(row['blockNumber'],16)<=hi:raise ValueError('LOG_SCOPE')
            t=row['topics'];q=queries[name]
            if 'address' in q and row['address'].lower()!=q['address']:raise ValueError('LOG_ADDRESS')
            for i,want in enumerate(q['topics']):
                if want is not None and t[i] not in (want if isinstance(want,list) else [want]):raise ValueError('LOG_TOPIC')
        return item
    jobs=[(name,lo,min(lo+4999,end)) for lo in range(START,end+1,5000) for name in queries]
    items=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for i,item in enumerate(pool.map(read,jobs),1):
            items.append(item)
            if i%40==0:print(json.dumps(dict(completed=i,total=len(jobs))),flush=True)
    unique={}
    for item in items:
        for row in item['logs']:
            k=(row['blockHash'],row['logIndex'])
            if k in unique and unique[k]!=row:raise ValueError('CONFLICTING_LOG')
            unique[k]=row
    rows=sorted(unique.values(),key=lambda r:(int(r['blockNumber'],16),int(r['logIndex'],16)))
    cashdelta,posdelta=changes(rows)
    def balance(token,block,tokenid=None):
        data=('0x70a08231'+WALLET[2:].rjust(64,'0')) if tokenid is None else ('0x00fdd58e'+WALLET[2:].rjust(64,'0')+hex(int(tokenid))[2:].rjust(64,'0'))
        return int(rpc.call('eth_call',[dict(to=token,data=data),hex(block)]),16)
    initial=balance(COLLATERAL,START-1);final=balance(COLLATERAL,end)
    positions=[]
    for (token,tid),delta in posdelta.items():
        before=balance(token,START-1,tid);after=balance(token,end,tid)
        positions.append(dict(contract=token,token_id=tid,before=before,delta=delta,after=after,reconciled=before+delta==after))
    receipts=[]
    for tx in sorted(set(r['transactionHash'] for r in rows)):
        receipt=rpc.call('eth_getTransactionReceipt',[tx]);block=rpc.call('eth_getBlockByNumber',[receipt['blockNumber'],False])
        if receipt['status']!='0x1' or block['hash']!=receipt['blockHash'] or int(receipt['blockNumber'],16)>end:raise ValueError('RECEIPT_FINALITY')
        for row in [r for r in rows if r['transactionHash']==tx]:
            fields=('address','topics','data','blockHash','transactionHash','logIndex')
            if not any(all(row[k]==v[k] for k in fields) for v in receipt['logs']):raise ValueError('RECEIPT_LOG')
        (BASE/(tx+'.json')).write_text(json.dumps(receipt,indent=2),encoding='utf-8');receipts.append(tx)
    if rpc.call('eth_getBlockByNumber',[anchor['number'],False])['hash']!=anchor['hash']:raise ValueError('ANCHOR_CHANGED')
    report=dict(from_block=START,to_block=end,anchor_hash=anchor['hash'],complete_requested_ranges=True,
        transfer_logs=len(rows),cash_before=initial,cash_delta=cashdelta,cash_after=final,
        cash_reconciled=initial+cashdelta==final,positions=positions,verified_receipts=receipts,
        settlement_reconciliation_proven=False,
        limitations=['Transfer reconstruction does not prove absence of pending off-chain settlements.',
            'Position IDs received before wallet deployment are outside this log interval.',
            'No independent fee liability ledger or atomic CLOB/chain snapshot.'])
    (BASE/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)

if __name__=='__main__':main()
