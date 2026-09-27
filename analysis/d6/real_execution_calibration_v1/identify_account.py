"""Narrow authorized Polygon read RPC + balance GET corroboration. Never execution."""
import asyncio,json,os,re,time,urllib.request,urllib.error
from pathlib import Path
from .compare_accounts import ROOT,EOA,D6,CLOB,DiagnosticGET,ReadBudget,confirm_candidates,safe_reason
from .core import digest
from app.live.collateral_onchain import RPC,CONTRACT,NoRedirect,validate_rpc_endpoint,uint_word,http_error_metadata,rpc_error_metadata

META={'0x313ce567','0x95d89b41','0x06fdde03'}
BALANCES={'0x70a08231'+a[2:].rjust(64,'0'):a for a in (EOA,D6)}
def quantity(value):
    if type(value) is not str or not re.fullmatch('0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)',value):raise ValueError('RPC_QUANTITY')
    return int(value,16)

def block_record(raw):
    if type(raw) is not dict or type(raw.get('hash')) is not str or not re.fullmatch('0x[0-9a-fA-F]{64}',raw['hash']):raise ValueError('BLOCK_SCHEMA')
    n=quantity(raw['number']);stamp=quantity(raw['timestamp'])
    if not 0<=time.time()-stamp<=120:raise ValueError('BLOCK_NOT_FRESH')
    return dict(number=n,number_hex=raw['number'],hash=raw['hash'].lower(),timestamp_ms=stamp*1000)

def abi_text(raw):
    if type(raw) is not str or not re.fullmatch('0x(?:[0-9a-fA-F]{2})+',raw):raise ValueError('ABI_TEXT')
    b=bytes.fromhex(raw[2:])
    if len(b)<96 or int.from_bytes(b[:32])!=32:raise ValueError('ABI_TEXT_OFFSET')
    n=int.from_bytes(b[32:64]);size=64+((n+31)//32)*32
    if not 1<=n<=96 or len(b)!=size or any(b[64+n:]):raise ValueError('ABI_TEXT_LENGTH')
    text=b[64:64+n].decode('ascii')
    if not re.fullmatch('[A-Za-z0-9 .()_-]{1,96}',text):raise ValueError('ABI_TEXT_CONTENT')
    return text

class PinnedCashRPC:
    def __init__(self,endpoint=RPC):
        self._endpoint=validate_rpc_endpoint(endpoint);self.pin=None;self.calls=[];self.failed=False;self.next_start=0
    def call(self,method,params):
        if self.failed:raise ValueError('RPC_HALTED_AFTER_FAILURE')
        valid=type(params) is list and method=='eth_chainId' and params==[]
        if type(params) is list and method=='eth_getBlockByNumber':valid=len(params)==2 and params[1] is False and params[0]==('latest' if self.pin is None else self.pin['number_hex'])
        if type(params) is list and method=='eth_call':
            valid=self.pin is not None and len(params)==2 and type(params[0]) is dict and set(params[0])=={'to','data'} and params[0]['to']==CONTRACT and type(params[0]['data']) is str and params[0]['data'] in META|set(BALANCES) and params[1]==self.pin['number_hex']
        if not valid:raise ValueError('PINNED_RPC_METHOD_OR_PARAMS_FORBIDDEN')
        if len(self.calls)>=10:raise ValueError('RPC_BUDGET')
        time.sleep(max(0,self.next_start-time.monotonic()));self.next_start=time.monotonic()+.3
        i=len(self.calls)+1;entry=dict(id=i,rpc_method=method,started_ms=time.time_ns()//1000000)
        if method=='eth_call':entry.update(contract=CONTRACT,selector=params[0]['data'][:10],account=BALANCES.get(params[0]['data']),block=self.pin['number_hex'])
        req=urllib.request.Request(self._endpoint,data=json.dumps(dict(jsonrpc='2.0',id=i,method=method,params=params)).encode(),headers={'Content-Type':'application/json','User-Agent':'Mozilla/5.0'},method='POST')
        try:
            with urllib.request.build_opener(NoRedirect()).open(req,timeout=10) as response:
                entry['http_status']=response.status;body=response.read(1000001)
            if entry['http_status']!=200 or len(body)>1000000:raise ValueError('RPC_HTTP_OR_SIZE')
            value=json.loads(body)
            if type(value) is not dict or value.get('jsonrpc')!='2.0' or type(value.get('id')) is not int or value['id']!=i:raise ValueError('RPC_ENVELOPE')
            if 'error' in value:entry.update(rpc_error_metadata(value['error']));raise ValueError('RPC_ERROR')
            if 'result' not in value:raise ValueError('RPC_NO_RESULT')
            entry.update(status='PASS',result_digest=digest(value['result']));return value['result']
        except Exception as exc:
            self.failed=True;entry.update(status='FAILED',reason=safe_reason(exc))
            if isinstance(exc,urllib.error.HTTPError):entry.update(http_status=exc.code,**http_error_metadata(exc,i));exc.close()
            raise RuntimeError('PINNED_RPC_READ_FAILED') from None
        finally:entry['finished_ms']=time.time_ns()//1000000;self.calls.append(entry)

def read_cash(rpc):
    result=dict(status='BLOCKED',contract=CONTRACT,started_ms=time.time_ns()//1000000,provider_trust='EXISTING_HTTPS_RPC_NOT_INDEPENDENT_CONSENSUS_PROOF')
    try:
        chain=quantity(rpc.call('eth_chainId',[]))
        if chain!=137:raise ValueError('WRONG_CHAIN')
        block=block_record(rpc.call('eth_getBlockByNumber',['latest',False]));rpc.pin=block
        call=lambda data:rpc.call('eth_call',[{'to':CONTRACT,'data':data},block['number_hex']])
        symbol=abi_text(call('0x95d89b41'));decimals=uint_word(call('0x313ce567'));name=abi_text(call('0x06fdde03'))
        if symbol!='pUSD' or decimals!=6:raise ValueError('COLLATERAL_METADATA_DISAGREEMENT')
        balances={a:str(uint_word(call(data))) for data,a in BALANCES.items()}
        again=block_record(rpc.call('eth_getBlockByNumber',[block['number_hex'],False]))
        if again!=block:raise ValueError('BLOCK_HASH_OR_HEADER_CHANGED')
        result.update(status='PINNED_CASH_OBSERVED',chain_id=chain,block=block,block_hash_rechecked=True,symbol=symbol,decimals=decimals,name=name,balances_raw=balances,balance_scope='THIS_COLLATERAL_AT_ONE_EXPLICIT_BLOCK_ONLY',positions_proven=False,orders_complete=False)
    except Exception as exc:result['reason']=safe_reason(exc)
    result.update(finished_ms=time.time_ns()//1000000,requests=rpc.calls);return result

def assess(report):
    c=report.get('chain',{});reasons=[]
    if c.get('status')!='PINNED_CASH_OBSERVED' or c.get('chain_id')!=137 or not c.get('block_hash_rechecked') or c.get('contract')!=CONTRACT or c.get('symbol')!='pUSD' or c.get('decimals')!=6:reasons.append('PINNED_COLLATERAL_EVIDENCE_UNQUALIFIED')
    positive=[]
    for wallet in (EOA,D6):
        b=report.get('before',{}).get(wallet);a=report.get('after',{}).get(wallet);onchain=c.get('balances_raw',{}).get(wallet)
        if type(onchain) is not str or not re.fullmatch('[0-9]+',onchain) or b!=onchain or a!=onchain:reasons.append('BALANCE_CORROBORATION_FAILED:'+wallet)
        elif int(onchain)>0:positive.append(wallet)
    if len(positive)!=1:reasons.append('BOTH_FUNDED_OR_NEITHER_UNIQUELY_FUNDED')
    if report.get('identity',{}).get('artifact_identity_confirmed') is not True or report.get('identity',{}).get('genesis_identity_confirmed') is not True:reasons.append('IDENTITY_UNVERIFIED')
    if c.get('block') and not 0<=report['finished_ms']-c['block']['timestamp_ms']<=120000:reasons.append('CASH_EVIDENCE_STALE')
    return dict(status='CALIBRATION_BLOCKED' if reasons else 'ACCOUNT_IDENTIFIED',reconciliation_account=None if reasons else positive[0],signer=EOA,blockers=reasons,calibration_ready=False,submit_allowed=False,scope='ECONOMIC_COLLATERAL_ACCOUNT_IDENTITY_NOT_EXECUTION_READINESS')

async def identify(root):
    from app.live.l2_existing_reader import load_existing
    from polymarket._internal.environment import PRODUCTION_CONFIG as env
    from polymarket._internal.actions import account as a
    from polymarket._internal.hmac import build_hmac_signature
    from .selection import inspect_selection
    report=dict(mode='AUTHORIZED_PINNED_CASH_ACCOUNT_IDENTIFICATION',started_ms=time.time_ns()//1000000,before={},after={},submit_allowed=False)
    creds=None;transport=None;audit=[]
    try:
        report['identity']=confirm_candidates(root)
        previous=json.loads((root/'analysis/d6/real_execution_calibration_v1/evidence/candidate_comparison_1790512511137/comparison.json').read_text())
        for wallet in (EOA,D6):
            if previous['candidates'][wallet]['balance_first']['collateral_contract']!=CONTRACT:raise ValueError('ARTIFACT_CONTRACT_CONFLICT')
        if env.collateral_token!=CONTRACT or env.chain_id!=137:raise ValueError('SDK_CONTRACT_CONFLICT')
        report['contract_confirmed_from_existing_artifacts']=True
        report['startup_selection']=inspect_selection(root)
        creds,report['storage']=load_existing(root)
        if not creds or report['storage'].get('storage_validated') is not True:raise ValueError('CREDENTIALS_UNAVAILABLE')
        async def headers(path):
            if path not in ('/time','/balance-allowance'):raise ValueError('GET_SCOPE')
            if path=='/time':return {}
            stamp=int(time.time());return {'POLY_ADDRESS':EOA,'POLY_API_KEY':creds['apiKey'],'POLY_PASSPHRASE':creds['passphrase'],'POLY_TIMESTAMP':str(stamp),'POLY_SIGNATURE':build_hmac_signature(secret=creds['secret'],timestamp=stamp,method='GET',path=path,body=None)}
        budget=ReadBudget(limit=5,interval=.35)
        public=DiagnosticGET(CLOB,('/time',),budget=budget,audit=audit)
        try:server=await public.get_json('/time')
        finally:public.close()
        if type(server) is not int or abs(server-time.time())>5:raise ValueError('CLOCK_PREFLIGHT')
        transport=DiagnosticGET(CLOB,('/balance-allowance',),budget=budget,audit=audit,headers=headers)
        async def balances(destination):
            for context in report['identity']['contexts']:
                path,params=a.build_balance_allowance_request(asset_type='COLLATERAL',signature_type=context['balance_get_signature_type'])
                raw=await transport.get_json(path,params=params);value=raw.get('balance') if type(raw) is dict else None
                if type(value) is not str or not re.fullmatch('[0-9]+',value):raise ValueError('GET_BALANCE_SCHEMA')
                destination[context['account']]=value
        await balances(report['before'])
        endpoint=os.environ.get('POLYGON_ARCHIVE_RPC_URL') or RPC
        report['rpc_provider']='EXISTING_CONFIGURED_PROVIDER' if os.environ.get('POLYGON_ARCHIVE_RPC_URL') else 'EXISTING_REPOSITORY_PUBLIC_DEFAULT'
        report['chain']=await asyncio.to_thread(read_cash,PinnedCashRPC(endpoint))
        if report['chain']['status']=='PINNED_CASH_OBSERVED':await balances(report['after'])
        report['finished_ms']=time.time_ns()//1000000;report['verdict']=assess(report)
        if report['verdict']['status']=='ACCOUNT_IDENTIFIED':
            wallet=report['verdict']['reconciliation_account'];st=0 if wallet==EOA else 3
            configured=report['startup_selection']['selectors'].get('READONLY_SIGNATURE_TYPE',[])
            report['explicit_context']=dict(reconciliation_account=wallet,signer=EOA,signature_type=st,configured_signature_types=configured,signature_type_conflict=any(x['value']!=str(st) for x in configured),legacy_eoa_readonly_signature_type=0,legacy_eoa_context_conflict=(st!=0),legacy_context_source='analysis/qualify_stored_l2.py EOA signer/wallet configuration',global_configuration_changed=False,execution_guard_preserved=True)
    except Exception as exc:report['verdict']=dict(status='CALIBRATION_BLOCKED',reconciliation_account=None,signer=EOA,reason=safe_reason(exc),calibration_ready=False,submit_allowed=False)
    finally:
        report['finished_ms']=time.time_ns()//1000000;report['get_requests']=audit
        report['get_provenance']=transport.observations if transport else []
        if transport:transport.close()
        if creds:
            if any(v in json.dumps(report) for v in creds.values()):report={'verdict':{'status':'CALIBRATION_BLOCKED','reason':'SECRET_REPORT_GUARD'},'submit_allowed':False}
            creds.clear()
    return report

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--authorized-pinned-rpc',action='store_true');args=p.parse_args()
    if not args.authorized_pinned_rpc:raise SystemExit('Explicit narrowly allowlisted read-RPC authorization required')
    report=asyncio.run(identify(ROOT));folder=Path(__file__).parent/'evidence'/('account_identity_'+str(time.time_ns()//1000000));folder.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        with (folder/name).open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    save('evidence.json',report)
    if report['verdict']['status']=='ACCOUNT_IDENTIFIED':
        save('reconciliation_binding.json',dict(status='ACCOUNT_IDENTIFIED',**report['explicit_context'],collateral_contract=CONTRACT,chain_id=137,source_evidence='evidence.json',source_digest=digest(report),block=report['chain']['block'],observed_ms=report['finished_ms'],cash_observation_valid_until_ms=report['finished_ms']+5000,scope='EXPLICIT_RECONCILIATION_IDENTITY_ONLY_REACQUIRE_CASH_FOR_LIVE_USE',calibration_ready=False,submit_allowed=False,automatic_startup_override=False))
    print(json.dumps({'artifact':str(folder/'evidence.json'),'verdict':report['verdict'],'get_count':len(report.get('get_requests',[])),'rpc_post_count':len(report.get('chain',{}).get('requests',[]))}))
if __name__=='__main__':main()
