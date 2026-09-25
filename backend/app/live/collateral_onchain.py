"""Pinned public Polygon JSON-RPC reads. No signer, transaction or arbitrary eth_call."""
import json
import re
import time
import hashlib
from decimal import Decimal
import urllib.request
import urllib.error
from urllib.parse import urlsplit
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


def rpc_error_metadata(error):
    """Classify untrusted provider text without retaining it or error.data."""
    result={'error_category':'UNCLASSIFIED_RPC_ERROR'}
    if not isinstance(error,dict):return result
    code=error.get('code')
    if type(code) is int and -(2**31)<=code<2**31:result['rpc_error_code']=code
    message=error.get('message')
    text=message.lower() if isinstance(message,str) else ''
    if code==-32601 or 'method not found' in text:category='METHOD_UNAVAILABLE'
    elif code==-32602:category='INVALID_PARAMS'
    elif 'rate limit' in text or 'too many requests' in text:category='RATE_LIMIT'
    elif any(x in text for x in ('upgrade','paid plan','free tier','subscription')):category='PLAN_RESTRICTION'
    elif 'range' in text and any(x in text for x in ('limit','maximum','exceed','large')):category='RANGE_LIMIT'
    elif any(x in text for x in ('missing trie','historical state','archive')):category='ARCHIVE_UNAVAILABLE'
    elif 'not supported' in text or 'unsupported' in text:category='METHOD_UNSUPPORTED'
    else:category='UNCLASSIFIED_RPC_ERROR'
    result['error_category']=category
    result['classification_basis']='PROVIDER_ERROR_CODE_OR_MESSAGE_PATTERN_NOT_INDEPENDENTLY_VERIFIED'
    return result


def http_error_metadata(response,request_id):
    """Bounded diagnostic only: never accept an HTTP error as a read result."""
    try:
        raw=response.read(16385)
        if len(raw)>16384:return {'http_error_body_status':'OVERSIZED'}
        try:value=json.loads(raw)
        except (ValueError,UnicodeError):return {'http_error_body_status':'NON_JSON'}
        if not isinstance(value,dict):return {'http_error_body_status':'UNRECOGNIZED_JSON'}
        if 'id' in value and value['id'] is not None and (type(value['id']) is not int or value['id']!=request_id):
            return {'http_error_body_status':'RESPONSE_ID_MISMATCH'}
        error=value.get('error')
        if isinstance(error,str):error={'message':error}
        if not isinstance(error,dict):
            if isinstance(value.get('message'),str):error={'message':value['message']}
            else:return {'http_error_body_status':'UNRECOGNIZED_JSON'}
        return {'http_error_body_status':'JSON_ERROR_CLASSIFIED',
                'error_response_id_matches':type(value.get('id')) is int and value['id']==request_id,
                'provider_error':rpc_error_metadata(error)}
    except Exception:return {'http_error_body_status':'BODY_READ_FAILED'}


def validate_rpc_endpoint(value):
    try:
        if not isinstance(value,str) or not value or any(c.isspace() or ord(c)<32 or ord(c)==127 for c in value):raise ValueError()
        url=urlsplit(value)
        if url.scheme!='https' or not url.hostname or url.username is not None or url.password is not None or url.fragment or '#' in value or '\\' in value:raise ValueError()
        if url.port is not None and not 1<=url.port<=65535:raise ValueError()
    except Exception:raise ValueError('POLYGON_ARCHIVE_RPC_URL_INVALID') from None
    return value


class PublicRPC:
    def __init__(self,wallet,*,endpoint=RPC,allow_finalized=False):
        if not re.fullmatch('0x[0-9a-fA-F]{40}',wallet):raise ValueError('WALLET')
        self._endpoint=validate_rpc_endpoint(endpoint)
        import threading
        self._counter_lock=threading.Lock()
        self.wallet=wallet;self.calls=[];self.counter=0
        self.allow_finalized=allow_finalized is True
    def call(self,method,params):
        block=lambda s:isinstance(s,str) and re.fullmatch('0x[0-9a-fA-F]+',s)
        valid=(method=='eth_chainId' and params==[])
        valid|=(method=='eth_getBlockByNumber' and len(params)==2 and (params[0]=='latest' or (self.allow_finalized and params[0]=='finalized') or bool(block(params[0]))) and params[1] is False)
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
        with self._counter_lock:
            self.counter+=1
            request_id=self.counter
        payload={'jsonrpc':'2.0','id':request_id,'method':method,'params':params}
        request=urllib.request.Request(self._endpoint,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','User-Agent':'Mozilla/5.0'},method='POST')
        cpu_started=time.thread_time_ns()
        entry={'rpc_method':method,'id':request_id,'started_ms':time.time_ns()//1000000}
        if method=='eth_getLogs':
            entry.update(from_block=int(params[0]['fromBlock'],16),to_block=int(params[0]['toBlock'],16))
        try:
            with urllib.request.build_opener(NoRedirect()).open(request,timeout=10) as response:
                entry['http_status']=response.status
                raw=response.read(1000001)
                entry['response_received_ms']=time.time_ns()//1000000
                if response.status!=200:
                    entry['error_category']='HTTP_ERROR';raise ValueError()
                if len(raw)>1000000:
                    entry['error_category']='RESPONSE_TOO_LARGE';raise ValueError()
                value=json.loads(raw)
                entry['parse_complete_ms']=time.time_ns()//1000000
            if not isinstance(value,dict) or value.get('jsonrpc')!='2.0' or type(value.get('id')) is not int or value['id']!=request_id:
                entry['error_category']='RPC_ENVELOPE_INVALID';raise ValueError()
            if 'error' in value:
                entry.update(rpc_error_metadata(value['error']));raise ValueError()
            if 'result' not in value:
                entry['error_category']='RPC_RESULT_MISSING';raise ValueError()
            entry['status']='PASS';return value['result']
        except Exception as exc:
            if isinstance(exc,urllib.error.HTTPError):
                entry.update(http_status=exc.code,error_category='HTTP_ERROR')
                entry.update(http_error_metadata(exc,request_id))
                exc.close()
            elif isinstance(exc,TimeoutError) or (isinstance(exc,urllib.error.URLError) and isinstance(exc.reason,TimeoutError)):
                entry['error_category']='TIMEOUT'
            elif isinstance(exc,urllib.error.URLError):entry['error_category']='CONNECTION_ERROR'
            elif isinstance(exc,json.JSONDecodeError):entry['error_category']='INVALID_JSON'
            entry.setdefault('error_category','UNCLASSIFIED_READ_ERROR')
            entry['status']='FAILED';raise RuntimeError('PUBLIC_RPC_READ_FAILED') from None
        finally:
            entry['thread_cpu_ms']=(time.thread_time_ns()-cpu_started)/1000000
            entry['finished_ms']=time.time_ns()//1000000
            entry['elapsed_ms']=entry['finished_ms']-entry['started_ms']
            self.calls.append(entry)


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
