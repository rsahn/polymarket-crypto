"""Offline ABI interpretation, never deployment authentication or a fee quote."""
import re
from eth_utils import keccak
from .core import digest
from .binding_consumer import require
COMMIT='ccc0596074f4dfd62c944fbca4de252893b82b4b'
SCHEMA='CTF_V2_NATIVE_RECEIPT/1'
EXCHANGES={'0xe111180000d2663c0091e4f400237545b87b996b','0xe2222d279d744050d28e00520010520000310f59'}
COLLATERAL='0xc011a7e12a19f7b1f670d46f03b03f3342e82dfb'
ASSET='0x4d97dcd97ec945f40cf65f87097ace5ea0476045'
def topic(s):return '0x'+keccak(text=s).hex()
FILLED=topic('OrderFilled(bytes32,address,address,uint8,uint256,uint256,uint256,uint256,bytes32,bytes32)')
MATCHED=topic('OrdersMatched(bytes32,address,uint8,uint256,uint256,uint256)')
TRANSFER=topic('Transfer(address,address,uint256)')
SINGLE=topic('TransferSingle(address,address,address,uint256,uint256)')
BATCH=topic('TransferBatch(address,address,address,uint256[],uint256[])')
def hx(v,n):
    require(type(v) is str and re.fullmatch('0x[0-9a-fA-F]{'+str(n*2)+'}',v) is not None,'ABI_HEX');return v.lower()
def addr(v):return hx(v,20)
def address_word(v):
    v=hx(v,32);require(v[2:26]=='0'*24,'ABI_ADDRESS_PADDING');return '0x'+v[-40:]
def uinthex(v):
    require(type(v) is str and re.fullmatch('0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)',v) is not None and len(v)<=66,'RPC_UINT');return int(v,16)
def words(v,n=None):
    require(type(v) is str and len(v)<=26000 and re.fullmatch('0x(?:[0-9a-fA-F]{64})*',v) is not None,'ABI_DATA')
    out=[int(v[i:i+64],16) for i in range(2,len(v),64)]
    require(n is None or len(out)==n,'ABI_LENGTH');return out

def decode(receipt,*,account,intents,deployment):
    """intents maps immutable orderHash to local identity; no fee allocation from transfers.
    deployment is a separately authenticated applicability record supplied by the caller.
    Matching summaries are checked but never counted as additional fills.
    """
    account=addr(account);exchange=addr(deployment['exchange'])
    require(deployment.get('version')==SCHEMA and deployment.get('source_commit')==COMMIT and type(deployment.get('chain_id')) is int and deployment['chain_id']==137 and exchange in EXCHANGES,'V2_APPLICABILITY_UNKNOWN')
    require(addr(deployment['collateral'])==COLLATERAL and addr(deployment['asset'])==ASSET,'V2_CONTRACT_MAPPING')
    require(len({o['client_id'] for o in intents.values()})==len(intents),'ORDER_HASH_ALIAS')
    require(deployment.get('applicability') in ('FIXTURE_ONLY','VERIFIED_DEPLOYMENT_AT_BLOCK'),'V2_DEPLOYMENT_UNPROVEN')
    require(type(intents) is dict and intents,'LOCAL_HASH_BINDING_REQUIRED')
    for h,o in intents.items():
        require(h==hx(h,32) and addr(o['account'])==account and o['side'] in ('BUY','SELL') and type(o['token']) is str and o['token'].isdigit(),'LOCAL_HASH_IDENTITY')
    tx=hx(receipt['transactionHash'],32);block=hx(receipt['blockHash'],32);number=uinthex(receipt['blockNumber'])
    require(receipt['status']=='0x1','RECEIPT_FAILED')
    if deployment['applicability']=='VERIFIED_DEPLOYMENT_AT_BLOCK':
        require(deployment.get('block_hash')==block and deployment.get('block_number')==number and deployment.get('bytecode_verified') is True,'DEPLOYMENT_BLOCK_BINDING')
        hx(deployment['runtime_code_hash'],32)
    logs=receipt['logs'];require(type(logs) is list and len(logs)<=10000,'LOG_BOUND')
    indices=set();events=[];summaries=[];cash=0;assets={};transfer_indices=[]
    for l in logs:
        i=uinthex(l['logIndex']);require(i not in indices,'DUPLICATE_LOG');indices.add(i)
        require(l.get('removed') is False and hx(l['transactionHash'],32)==tx and hx(l['blockHash'],32)==block and uinthex(l['blockNumber'])==number,'REORG_OR_LOG_CONTEXT')
        a=addr(l['address']);ts=l['topics'];require(type(ts) is list and 1<=len(ts)<=4,'ABI_TOPICS');ts=[hx(t,32) for t in ts]
        if ts[0] in (FILLED,MATCHED):
            require(a==exchange,'UNKNOWN_EXCHANGE_EVENT')
            if ts[0]==FILLED:
                require(len(ts)==4,'FILLED_TOPICS');w=words(l['data'],7)
                require(w[0] in (0,1) and w[1]>0 and w[2]>0 and w[3]>0,'FILLED_VALUES')
                maker,taker=address_word(ts[2]),address_word(ts[3]);side=('BUY','SELL')[w[0]]
                n,q=(w[2],w[3]) if side=='BUY' else (w[3],w[2])
                require(side=='BUY' or w[4]<=n,'FEE_EXCEEDS_PROCEEDS')
                events.append(dict(hash=ts[1],maker=maker,taker=taker,side=side,token=str(w[1]),notional_raw=str(n),gross_shares_raw=str(q),cash_fee_raw=str(w[4]),share_fee_raw='0',index=i,wire=w[:4],builder='0x'+format(w[5],'064x'),metadata='0x'+format(w[6],'064x')))
            else:
                require(len(ts)==3,'MATCHED_TOPICS');summaries.append((ts[1],address_word(ts[2]),words(l['data'],4),i))
        elif a==COLLATERAL and ts[0]==TRANSFER:
            require(len(ts)==3,'TRANSFER_TOPICS');src,dst=address_word(ts[1]),address_word(ts[2]);v=words(l['data'],1)[0]
            if account in (src,dst):cash+=(int(dst==account)-int(src==account))*v;transfer_indices.append(i)
        elif a==ASSET and ts[0] in (SINGLE,BATCH):
            require(len(ts)==4,'CTF_TOPICS');address_word(ts[1]);src,dst=address_word(ts[2]),address_word(ts[3]);w=words(l['data'])
            if ts[0]==SINGLE:require(len(w)==2,'SINGLE_LENGTH');pairs=[(w[0],w[1])]
            else:
                require(len(w)>=4 and w[0]==64,'BATCH_OFFSET');n=w[2]
                require(0<n<=200 and w[1]==32*(3+n) and len(w)==4+2*n and w[3+n]==n,'BATCH_LENGTH');pairs=list(zip(w[3:3+n],w[4+n:]))
                require(len({t for t,v in pairs})==n,'DUPLICATE_BATCH_TOKEN')
            if account in (src,dst):
                transfer_indices.append(i)
                for t,v in pairs:assets[str(t)]=assets.get(str(t),0)+(int(dst==account)-int(src==account))*v
        elif ts[0] in (TRANSFER,SINGLE,BATCH):
            # Foreign asset transfers involving the account cannot disappear through netting.
            positions=ts[1:] if ts[0]==TRANSFER else ts[2:]
            require(all(address_word(t)!=account for t in positions),'FOREIGN_TRANSFER_ASSET')
    # Each taker summary immediately follows its OrderFilled in this pinned implementation.
    summary_indices=set()
    for h,m,w,i in summaries:
        candidates=[e for e in events if e['index']==i-1 and e['hash']==h and e['maker']==m and e['wire']==w and e['taker']==exchange]
        require(len(candidates)==1,'MATCHED_FILL_PAIR');summary_indices.add(candidates[0]['index'])
    require(all((e['index'] in summary_indices)==(e['taker']==exchange) for e in events),'TAKER_SUMMARY_MISSING')
    own=[];expected_cash=0;expected_assets={}
    for e in events:
        if e['maker']!=account:
            require(e['hash'] not in intents,'FOREIGN_ORDER_OWNER');continue # own address as counterparty is not another own fill
        require(e['hash'] in intents,'UNATTRIBUTED_ACCOUNT_ORDER');o=intents[e['hash']]
        require(e['side']==o['side'] and e['token']==o['token'],'ORDER_TOKEN_SIDE')
        require(e['maker']!=e['taker'],'SELF_MATCH_UNSUPPORTED')
        n,q,f=(int(e[k]) for k in ('notional_raw','gross_shares_raw','cash_fee_raw'))
        expected_cash+=-n-f if e['side']=='BUY' else n-f
        expected_assets[e['token']]=expected_assets.get(e['token'],0)+(q if e['side']=='BUY' else -q)
        own.append({**e,'order_id':o['order_id'],'client_id':o['client_id'],'role':'TAKER' if e['index'] in summary_indices else 'MAKER'})
    require(own,'NO_LOCAL_ORDER_FILL')
    require(set(assets)<=set(expected_assets) and cash==expected_cash and all(assets.get(t,0)==v for t,v in expected_assets.items()),'NATIVE_TRANSFER_MISMATCH')
    return dict(schema=SCHEMA,source_commit=COMMIT,receipt_digest=digest(receipt),transaction_hash=tx,block_hash=block,block_number=number,fills=own,cash_delta_raw=str(cash),asset_deltas_raw={t:str(v) for t,v in assets.items()},transfer_log_indices=transfer_indices,applicability=deployment['applicability'],finality_proven=False,submit_allowed=False)
