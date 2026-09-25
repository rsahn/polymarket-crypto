"""Pinned public Polygon JSON-RPC reads. No signer, transaction or arbitrary eth_call."""
import json
import re
import time
import hashlib
from decimal import Decimal
import urllib.request
from .network_readonly import NoRedirect

RPC='https://polygon.drpc.org'
CONTRACT='0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB'
CTF='0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
PROVENANCE='https://docs.polygon.technology/pos/reference/rpc-endpoints'


def uint_word(value):
    if not isinstance(value,str) or not re.fullmatch('0x[0-9a-fA-F]{64}',value):raise ValueError('ABI_UINT')
    return int(value,16)


def symbol_string(value):
    if not isinstance(value,str) or not re.fullmatch('0x(?:[0-9a-fA-F]{2})+',value):raise ValueError('ABI_STRING')
    raw=bytes.fromhex(value[2:])
    if len(raw)<96 or int.from_bytes(raw[:32])!=32:raise ValueError('ABI_OFFSET')
    n=int.from_bytes(raw[32:64])
    if not 1<=n<=32 or len(raw)!=96 or any(raw[64+n:]):raise ValueError('ABI_LENGTH')
    result=raw[64:64+n].decode('ascii')
    if result!='pUSD':raise ValueError('SYMBOL_MISMATCH')
    return result


class PublicRPC:
    def __init__(self,wallet):
        if not re.fullmatch('0x[0-9a-fA-F]{40}',wallet):raise ValueError('WALLET')
        self.wallet=wallet;self.calls=[];self.counter=0
    def call(self,method,params):
        block=lambda s:isinstance(s,str) and re.fullmatch('0x[0-9a-fA-F]+',s)
        valid=(method=='eth_chainId' and params==[])
        valid|=(method=='eth_getBlockByNumber' and len(params)==2 and (params[0]=='latest' or block(params[0])) and params[1] is False)
        valid|=(method=='eth_getCode' and len(params)==2 and params[0] in (CONTRACT,CTF,self.wallet) and bool(block(params[1])))
        if method=='eth_call' and len(params)==2 and isinstance(params[0],dict) and set(params[0])=={'to','data'} and block(params[1]):
            target,data=params[0]['to'],params[0]['data']
            allowed={'0x313ce567','0x95d89b41','0x70a08231'+self.wallet[2:].lower().rjust(64,'0')}
            valid=(target==CONTRACT and data in allowed)
            if target==CTF:
                valid=bool(re.fullmatch('0x00fdd58e'+self.wallet[2:].lower().rjust(64,'0')+'[0-9a-f]{64}',data))
        if method=='eth_getLogs' and len(params)==1 and isinstance(params[0],dict):
            from eth_utils import keccak
            q=params[0];topics=q.get('topics',[])
            signatures=['0x'+keccak(text=x).hex() for x in ('TransferSingle(address,address,address,uint256,uint256)','TransferBatch(address,address,address,uint256[],uint256[])')]
            valid=(set(q)=={'address','fromBlock','toBlock','topics'} and q['address']==CTF
                   and bool(block(q['fromBlock'])) and bool(block(q['toBlock']))
                   and 0<=int(q['toBlock'],16)-int(q['fromBlock'],16)<500
                   and topics==[signatures,None,None,'0x'+self.wallet[2:].lower().rjust(64,'0')])
        if not valid:raise ValueError('RPC_METHOD_OR_PARAMS_FORBIDDEN')
        self.counter+=1
        payload={'jsonrpc':'2.0','id':self.counter,'method':method,'params':params}
        request=urllib.request.Request(RPC,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','User-Agent':'Mozilla/5.0'},method='POST')
        entry={'rpc_method':method,'id':self.counter,'started_ms':time.time_ns()//1000000}
        try:
            with urllib.request.build_opener(NoRedirect()).open(request,timeout=10) as response:
                raw=response.read(1000001)
                if response.status!=200 or len(raw)>1000000:raise ValueError()
                value=json.loads(raw)
            if not isinstance(value,dict) or value.get('jsonrpc')!='2.0' or type(value.get('id')) is not int or value['id']!=self.counter or 'error' in value or 'result' not in value:raise ValueError()
            entry['status']='PASS';return value['result']
        except Exception:
            entry['status']='FAILED';raise RuntimeError('PUBLIC_RPC_READ_FAILED') from None
        finally:self.calls.append(entry)


def qualify_collateral(rpc,*,clock=time.time):
    report={'status':'BLOCKED','contract':CONTRACT,'rpc':RPC,'rpc_provenance':PROVENANCE,
            'symbol_verified':False,'decimals_verified':False,'account_binding_verified':False,'conversion_allowed':False}
    try:
        from polymarket._internal.environment import PRODUCTION_CONFIG as env
        if env.collateral_token!=CONTRACT or env.chain_id!=137 or env.rpc_url!=RPC:raise ValueError()
        if rpc.call('eth_chainId',[])!='0x89':raise ValueError()
        head=rpc.call('eth_getBlockByNumber',['latest',False]);block=head['number']
        if not re.fullmatch('0x[0-9a-fA-F]{64}',head['hash']) or not 0<=clock()-int(head['timestamp'],16)<=120:raise ValueError()
        for address in (CONTRACT,rpc.wallet):
            code=rpc.call('eth_getCode',[address,block])
            if not isinstance(code,str) or not re.fullmatch('0x(?:[0-9a-fA-F]{2})+',code) or int(code[2:],16)==0:raise ValueError()
            if address==CONTRACT:report['code_sha256']=hashlib.sha256(bytes.fromhex(code[2:])).hexdigest()
        def call(data):return rpc.call('eth_call',[{'to':CONTRACT,'data':data},block])
        decimals=uint_word(call('0x313ce567'));symbol=symbol_string(call('0x95d89b41'))
        if decimals!=6:raise ValueError()
        balance=uint_word(call('0x70a08231'+rpc.wallet[2:].lower().rjust(64,'0')))
        again=rpc.call('eth_getBlockByNumber',[block,False])
        if again['hash']!=head['hash']:raise ValueError()
        report.update(status='PASS_ONCHAIN_IDENTITY',chain_id=137,block_number=block,block_hash=head['hash'],
            observed_ms=int(clock()*1000),symbol=symbol,decimals=decimals,code_present=True,
            symbol_verified=True,decimals_verified=True,onchain_balance_raw=str(balance),
            mapping_provenance=['SDK 0.11.0 PRODUCTION_CONFIG.collateral_token','https://docs.polymarket.com/resources/contracts','https://docs.polymarket.com/concepts/pusd'])
    except Exception:report['reason']='RPC_CHAIN_CODE_ABI_METADATA_OR_BLOCK_INCONSISTENT'
    return report


def bind_collateral(report,before,after):
    result=dict(report)
    if report.get('status')=='PASS_ONCHAIN_IDENTITY' and re.fullmatch('[0-9]+',str(before)) and int(before)>0 and str(before)==str(after)==report.get('onchain_balance_raw'):
        result.update(account_binding_verified=True,conversion_allowed=True,
            binding_scope='OFFICIAL_MAPPING_PLUS_BEACON_BALANCE_CORROBORATION_BETWEEN_TWO_TYPE3_READS',
            balance_human=format(Decimal(before)/Decimal(10**6),'.6f'),balance_unit='pUSD')
    else:result['binding_reason']='IDENTITY_OR_CONTEMPORANEOUS_BALANCE_MATCH_MISSING'
    return result
