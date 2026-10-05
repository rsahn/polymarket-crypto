"""Public RPC GET-state/log scanner. Never signs or sends a transaction.

Coverage is relative to an explicit code-onset boundary and trusted RPC responses;
it is not a certificate that every historical implementation emitted this ABI.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request
from eth_utils import keccak

WALLET = '0x871d37b430c42ddbd0bbd37c29c02a2974109de9'
ENDPOINTS = ('https://polygon-bor-rpc.publicnode.com', 'https://polygon.drpc.org',
    'https://tenderly.rpc.polygon.community', 'https://polygon.api.onfinality.io/public',
    'https://polygon-public.nodies.app')
EVENTS = { '0x'+keccak(text=s).hex(): name for name,s in (
    ('authorized','SessionSignerAuthorized(address,uint256)'),
    ('revoked','SessionSignerRevoked(address)'),
    ('emergency_revoked','SessionSignerRevokedEmergency(address)'))}

def digest(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

class RPC:
    def __init__(self,url):
        if url not in ENDPOINTS: raise ValueError('ENDPOINT')
        self.url=url; self.sequence=0
    def call(self,method,params):
        if method not in ('eth_chainId','eth_getCode','eth_getBlockByNumber','eth_getLogs','eth_call','eth_getTransactionReceipt'):
            raise ValueError('READ_ONLY_METHOD')
        for attempt in range(3):
            try:return self._read(method,params)
            except Exception:
                if attempt==2:raise
                time.sleep(1)
    def _read(self,method,params):
        self.sequence+=1
        q=urllib.request.Request(self.url,data=json.dumps(dict(jsonrpc='2.0',id=self.sequence,method=method,params=params)).encode(),
            headers={'Content-Type':'application/json','User-Agent':'Mozilla/5.0'})
        with urllib.request.build_opener(NoRedirect()).open(q,timeout=12) as r: raw=r.read(8*1024**2+1)
        if len(raw)>8*1024**2: raise ValueError('RESPONSE_SIZE')
        d=json.loads(raw)
        if d.get('id')!=self.sequence or 'error' in d or 'result' not in d: raise ValueError('RPC_ERROR')
        return d['result']

def decode(row):
    topics=row.get('topics',[])
    if not topics or topics[0] not in EVENTS: return None
    kind=EVENTS[topics[0]]
    if len(topics)!=2 or len(topics[1])!=66 or int(topics[1][2:26],16)!=0: raise ValueError('EVENT_TOPICS')
    if len(row['data'])!=(66 if kind=='authorized' else 2): raise ValueError('EVENT_DATA')
    return dict(kind=kind,signer='0x'+topics[1][-40:].lower(),
        valid_until=int(row['data'],16) if kind=='authorized' else None,
        block=int(row['blockNumber'],16),block_hash=row['blockHash'],
        transaction=row['transactionHash'],transaction_index=int(row['transactionIndex'],16),
        log_index=int(row['logIndex'],16))

def scan(rpc,start,end,folder):
    manifest=[]; logs=[]; seen=set()
    for lo in range(start,end+1,5000):
        hi=min(lo+4999,end)
        rows=None
        for attempt in range(3):
            try:
                rows=rpc.call('eth_getLogs',[dict(address=WALLET,fromBlock=hex(lo),toBlock=hex(hi))]);break
            except Exception:
                if attempt==2: raise
                time.sleep(1)
        if type(rows) is not list or len(rows)>=10000: raise ValueError('LOG_RESPONSE_OR_POSSIBLE_CAP')
        for row in rows:
            if row.get('address','').lower()!=WALLET or row.get('removed') is not False or not lo<=int(row['blockNumber'],16)<=hi:
                raise ValueError('LOG_SCOPE')
            key=(row['blockHash'],row['logIndex'])
            if key in seen: raise ValueError('DUPLICATE_LOG')
            seen.add(key);decode(row)
        item=dict(from_block=lo,to_block=hi,count=len(rows),sha256=digest(rows),logs=rows)
        with (folder/f'range_{lo}_{hi}.json').open('x',encoding='utf-8') as f: json.dump(item,f,indent=2)
        manifest.append({k:v for k,v in item.items() if k!='logs'});logs.extend(rows)
        (folder/'coverage_progress.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print(json.dumps(dict(through=hi,target=end,logs=len(logs))),flush=True)
        time.sleep(.2)
    return manifest,logs

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-directory',required=True)
    p.add_argument('--start-block',type=int,default=94331195)
    p.add_argument('--rpc',choices=ENDPOINTS,default=ENDPOINTS[1])
    p.add_argument('--end-block',type=int)
    args=p.parse_args();folder=Path(args.output_directory);folder.mkdir(exist_ok=False)
    rpc=RPC(args.rpc); boundary=RPC(ENDPOINTS[1])
    result=dict(wallet=WALLET,submit_allowed=False,all_authorizations_covered_from_wallet_genesis=False,
        source_abi_binding_verified=False,non_terminal_legacy_trades='UNPROVEN',start_block=args.start_block,
        rpc=rpc.url,independent_provider_crosscheck=False)
    try:
        if rpc.call('eth_chainId',[])!='0x89' or boundary.call('eth_chainId',[])!='0x89': raise ValueError('CHAIN')
        head=boundary.call('eth_getBlockByNumber',['finalized',False]);end=int(head['number'],16)
        if args.end_block is not None:
            if not args.start_block<=args.end_block<=end:raise ValueError('FINALIZED_RANGE')
            end=args.end_block;head=boundary.call('eth_getBlockByNumber',[hex(end),False])
        result.update(end_block=end,end_hash=head['hash'],block_timestamp=int(head['timestamp'],16))
        before=boundary.call('eth_getCode',[WALLET,hex(args.start_block-1)])
        after=boundary.call('eth_getCode',[WALLET,hex(args.start_block)])
        if before!='0x' or not after or after=='0x':raise ValueError('CODE_ONSET_MISMATCH')
        result['code_onset_verified']=True
        other=rpc.call('eth_getBlockByNumber',[hex(end),False])
        if other['hash']!=head['hash']:raise ValueError('PROVIDER_ANCHOR_MISMATCH')
        manifest,logs=scan(rpc,args.start_block,end,folder)
        result.update(range_coverage_complete=True,manifest_digest=digest(manifest),wallet_log_count=len(logs))
        events=sorted(filter(None,(decode(row) for row in logs)),key=lambda x:(x['block'],x['transaction_index'],x['log_index']))
        result['events']=events;signers={}
        for e in events:
            signers.setdefault(e['signer'],dict(authorizations=[],revocations=[]))['authorizations' if e['kind']=='authorized' else 'revocations'].append(e)
        for signer,r in signers.items():
            data='0x'+keccak(text='sessionSignerAuthorizedUntil(address)').hex()[:8]+signer[2:].rjust(64,'0')
            values=[provider.call('eth_call',[dict(to=WALLET,data=data),hex(end)]) for provider in (rpc,boundary)]
            if any(type(v) is not str or len(v)!=66 for v in values) or values[0]!=values[1]:raise ValueError('AUTHORIZATION_STATE_MISMATCH')
            r['authorized_until_at_anchor']=int(values[0],16)
            r['state_at_anchor']='REVOKED_OR_ZERO' if int(values[0],16)==0 else 'EXPIRED' if int(values[0],16)<=result['block_timestamp'] else 'AUTHORIZED'
            r['scopes_onchain']='NOT_IN_EVENT_ABI'
        result['signers']=signers;result['historical_event_signer_count']=len(signers)
        receipts={}
        for row in logs:
            if decode(row) is None and int(row['blockNumber'],16)!=args.start_block:continue
            tx=row['transactionHash']
            if tx not in receipts:
                receipt=boundary.call('eth_getTransactionReceipt',[tx])
                if receipt['blockHash']!=row['blockHash'] or receipt['status']!='0x1':raise ValueError('RECEIPT')
                receipts[tx]=receipt
            fields=('address','topics','data','blockHash','transactionHash','logIndex')
            if not any(all(row.get(k)==r.get(k) for k in fields) for r in receipts[tx]['logs']):raise ValueError('RECEIPT_LOG_MISSING')
        (folder/'receipts.json').write_text(json.dumps(receipts,indent=2),encoding='utf-8')
        for provider in (rpc,boundary):
            if provider.call('eth_getBlockByNumber',[hex(end),False])['hash']!=head['hash']:raise ValueError('ANCHOR_CHANGED')
        result['status']='PASS_RPC_LOG_ENUMERATION_NOT_IMPLEMENTATION_COMPLETENESS'
        result['limitations']=['Code onset is not a proof of no earlier deployment/redeployment.',
            'Historical implementation ABI and exhaustive emission semantics not verified.',
            'RPC range completeness relies on provider; matched receipts do not prove absence of omitted logs.',
            'Fixed finalized anchor does not include later authorizations; active API comparison is separate.']
    except Exception as exc:
        result.update(status='BLOCKED_PARTIAL',error_type=type(exc).__name__)
    (folder/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
    return 0 if result.get('status','').startswith('PASS') else 2

if __name__=='__main__':raise SystemExit(main())
