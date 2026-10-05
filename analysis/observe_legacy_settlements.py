"""GET-only authenticated settlement inventory with protected original responses."""
import asyncio
from collections import Counter
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'analysis'),str(ROOT/'backend')]
from app.live.network_readonly import GetOnlyTransport
from app.live.l2_existing_reader import load_existing, EXPECTED
from app.live.l2_windows_storage import WindowsProtection
from polymarket._internal.hmac import build_hmac_signature
from scan_deposit_session_history import RPC, WALLET, digest

TERMINAL={'CONFIRMED','FAILED'}
KNOWN=TERMINAL|{'MATCHED','MINED','RETRYING'}

def statuses(rows):
    counts=Counter({s:0 for s in KNOWN})
    ids=set()
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('id'),str):
            raise ValueError('TRADE_SCHEMA_OR_UNKNOWN_STATUS')
        state=row.get('status')
        aliases={**{s:s for s in KNOWN},**{'TRADE_STATUS_'+s:s for s in KNOWN}}
        if not isinstance(state,str) or state not in aliases:raise ValueError('TRADE_SCHEMA_OR_UNKNOWN_STATUS')
        if row['id'] in ids:raise ValueError('DUPLICATE_TRADE')
        ids.add(row['id']);counts[aliases[state]]+=1
    return dict(counts)

async def observe():
    credentials,_=load_existing(ROOT)
    if not credentials:raise ValueError('EXISTING_CREDENTIALS_UNAVAILABLE')
    protection=WindowsProtection()
    private=Path('D:/polymarket-real-calibration')/('legacy-settlement-'+str(time.time_ns()))
    protection.create_private_directory(private)
    audit=[];public_pages={}
    def archive(name,raw):
        (private/(name+'.dpapi')).write_bytes(protection.protect(json.dumps(raw).encode()))
        return digest(raw)
    async def headers(path):
        ts=int(time.time())
        return {'POLY_ADDRESS':EXPECTED,'POLY_API_KEY':credentials['apiKey'],
            'POLY_PASSPHRASE':credentials['passphrase'],'POLY_TIMESTAMP':str(ts),
            'POLY_SIGNATURE':build_hmac_signature(secret=credentials['secret'],timestamp=ts,method='GET',path=path,body=None)}
    clob=GetOnlyTransport('https://clob.polymarket.com',{'/data/trades','/data/orders','/balance-allowance'},headers=headers,audit=audit)
    data=GetOnlyTransport('https://data-api.polymarket.com',{'/positions','/activity'},audit=audit)
    async def pages(name,transport,path,params,clob_paging):
        rows=[];hashes=[];seen=set()
        for i in range(100):
            raw=await transport.get_json(path,params=params);hashes.append(archive(name+'_'+str(i),raw))
            part=raw['data'] if clob_paging else raw
            if not isinstance(part,list):raise ValueError('PAGE_SCHEMA')
            rows.extend(part)
            if clob_paging:
                cursor=raw['next_cursor']
                if cursor=='LTE=':break
                if not isinstance(cursor,str) or not cursor or cursor in seen:raise ValueError('CURSOR')
                seen.add(cursor);params={**params,'next_cursor':cursor}
            else:
                if len(part)<500:break
                params={**params,'offset':(i+1)*500}
        else:raise ValueError('PAGINATION_NOT_EXHAUSTED')
        public_pages[name]=dict(count=len(rows),pages_sha256=hashes,pagination_exhausted=True)
        return rows
    result=dict(wallet=WALLET,observed_ms=time.time_ns()//1000000,private_archive=str(private),
        read_only=True,settlement_reconciliation_proven=False,wallet_wide_coverage_proven=False)
    collected={}
    for name,t,p,params,cursor in (
        ('trades',clob,'/data/trades',{},True),
        ('orders',clob,'/data/orders',{},True),
        ('positions',data,'/positions',dict(user=WALLET,sizeThreshold=0,limit=500,offset=0),False),
        ('activity',data,'/activity',dict(user=WALLET,limit=500,offset=0),False)):
        try:collected[name]=await pages(name,t,p,params,cursor)
        except Exception as exc:public_pages[name]=dict(status='UNPROVEN',error_type=type(exc).__name__)
    if 'trades' in collected:
        result['trade_status_counts']=statuses(collected['trades'])
        result['non_terminal_accessible_count']=sum(v for k,v in result['trade_status_counts'].items() if k not in TERMINAL)
    try:
        cash=await clob.get_json('/balance-allowance',params=dict(asset_type='COLLATERAL',signature_type=3))
        result['clob_cash']=dict(balance_raw=cash['balance'],sha256=archive('cash',cash))
    except Exception as exc:result['clob_cash']=dict(error_type=type(exc).__name__)
    rpc=RPC('https://tenderly.rpc.polygon.community')
    try:
        anchor=await asyncio.to_thread(rpc.call,'eth_getBlockByNumber',['finalized',False])
        result['chain_anchor']={k:anchor[k] for k in ('number','hash','timestamp')}
        balance=await asyncio.to_thread(rpc.call,'eth_call',[dict(to='0xc011a7e12a19f7b1f670d46f03b03f3342e82dfb',data='0x70a08231'+WALLET[2:].rjust(64,'0')),anchor['number']])
        result['chain_cash_raw']=str(int(balance,16))
        result['cash_values_equal']=str(result.get('clob_cash',{}).get('balance_raw'))==result['chain_cash_raw']
        hashes=set()
        for name in ('trades','activity'):
            for row in collected.get(name,[]):
                tx=row.get('transaction_hash') or row.get('transactionHash')
                if isinstance(tx,str) and len(tx)==66 and tx.startswith('0x'):hashes.add(tx)
        receipts=[]
        for tx in sorted(hashes):
            receipt=await asyncio.to_thread(rpc.call,'eth_getTransactionReceipt',[tx]);archive('receipt_'+tx,receipt)
            if receipt is None:receipts.append(dict(transaction=tx,status='UNPROVEN'));continue
            block=await asyncio.to_thread(rpc.call,'eth_getBlockByNumber',[receipt['blockNumber'],False])
            receipts.append(dict(transaction=tx,status=receipt['status'],block=receipt['blockNumber'],
                canonical=block['hash']==receipt['blockHash'],finalized=int(receipt['blockNumber'],16)<=int(anchor['number'],16),logs=len(receipt['logs'])))
        result['receipt_checks']=receipts
    except Exception as exc:result['chain_error_type']=type(exc).__name__
    result.update(pages=public_pages,network_audit=audit,
        limitations=['Credential view is not independently certified wallet-wide.',
        'Finalized receipts establish settlement of listed transactions, not absence of unlisted pending trades.',
        'Cash equality at different observations does not establish an atomic common cut or complete historical fee accounting.'])
    return result

if __name__=='__main__':
    result=asyncio.run(observe())
    target=ROOT/'analysis'/('legacy_settlement_observation_'+str(result['observed_ms'])+'.json')
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
