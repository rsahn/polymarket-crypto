"""Only explicitly authorized read RPCs; no eth_chainId/getCode/send/sign calls."""
import json,re,time,urllib.request,urllib.error
from app.live.collateral_onchain import PublicRPC,CONTRACT,CTF,NoRedirect,uint_word,symbol_string
from app.live.preparation_rpc import PreparationRPC

class ReceiptRPC(PublicRPC):
    def __init__(self,wallet,*,receipt_ids=(),**kw):
        super().__init__(wallet,allow_finalized=True,**kw)
        if len(receipt_ids)>2 or any(not re.fullmatch('0x[0-9a-fA-F]{64}',t) for t in receipt_ids):raise ValueError('RECEIPT_SCOPE')
        self.receipt_ids=frozenset(receipt_ids)
    def call(self,method,params):
        if method not in ('eth_call','eth_getLogs','eth_getBlockByNumber','eth_getTransactionReceipt'):raise ValueError('READ_RPC_FORBIDDEN')
        if self.counter>=20:raise ValueError('RPC_REQUEST_BUDGET')
        if method!='eth_getTransactionReceipt':return super().call(method,params)
        if type(params) is not list or len(params)!=1 or params[0] not in self.receipt_ids:raise ValueError('RECEIPT_NOT_OBSERVED_IN_SELECTED_TRADES')
        self.counter+=1;identifier=self.counter;entry=dict(rpc_method=method,id=identifier,started_ms=time.time_ns()//1000000)
        request=urllib.request.Request(self._endpoint,data=json.dumps(dict(jsonrpc='2.0',id=identifier,method=method,params=params)).encode(),headers={'Content-Type':'application/json'},method='POST')
        try:
            with urllib.request.build_opener(NoRedirect()).open(request,timeout=10) as response:
                entry['http_status']=response.status;raw=response.read(1000001)
            if len(raw)>1000000:raise ValueError('RPC_SIZE')
            value=json.loads(raw)
            if value.get('jsonrpc')!='2.0' or type(value.get('id')) is not int or value['id']!=identifier or 'error' in value:raise ValueError('RPC_ENVELOPE')
            entry['status']='PASS';return value['result']
        except Exception as exc:
            entry['status']='FAILED'
            if isinstance(exc,urllib.error.HTTPError):entry['http_status']=exc.code;exc.close()
            raise RuntimeError('READ_ONLY_RECEIPT_FAILED') from None
        finally:entry['finished_ms']=time.time_ns()//1000000;self.calls.append(entry)

def observe_chain(wallet,txs,endpoint=None,tokens=()):
    from .core import digest
    from app.live.collateral_onchain import RPC
    raw=ReceiptRPC(wallet,receipt_ids=txs,endpoint=endpoint or RPC);rpc=PreparationRPC(raw,budget_seconds=90)
    report=dict(status='BLOCKED',chain_identity='CONFIGURED_POLYGON_NOT_RPC_CHAINID_VERIFIED',rpc_endpoint='EXISTING_PROCESS_CONFIGURATION' if endpoint else 'REPOSITORY_PUBLIC_DEFAULT',current_inventory_proven=False,fee_effects_proven=False,round_trip_fee_bound=None,receipts=[])
    try:
        head=rpc.call('eth_getBlockByNumber',['finalized',False]);block=head['number'];height=int(block,16)
        if not re.fullmatch('0x[0-9a-fA-F]{64}',head['hash']):raise ValueError('BLOCK_HASH')
        if not 0<=time.time()-int(head['timestamp'],16)<=600:raise ValueError('FINALIZED_BLOCK_AGE')
        call=lambda data,b=block:rpc.call('eth_call',[{'to':CONTRACT,'data':data},b])
        symbol=symbol_string(call('0x95d89b41'));decimals=uint_word(call('0x313ce567'))
        if decimals!=6:raise ValueError('COLLATERAL_DECIMALS')
        data='0x70a08231'+wallet[2:].lower().rjust(64,'0');balance=uint_word(call(data))
        token_balances={}
        if len(tokens)>2 or any(not re.fullmatch('[0-9]{1,78}',t) or int(t)>=2**256 for t in tokens):raise ValueError('TOKEN_READ_SCOPE')
        for token in tokens:
            payload='0x00fdd58e'+wallet[2:].lower().rjust(64,'0')+hex(int(token))[2:].rjust(64,'0')
            token_balances[token]=str(uint_word(rpc.call('eth_call',[{'to':CTF,'data':payload},block])))
        report['selected_token_balances_raw_at_existing_CTF']=token_balances
        report['asset_contract_binding']='CTF_SCOPED_READ_NOT_PROOF_OF_V2_OR_GLOBAL_ASSET_UNIVERSE'
        from eth_utils import keccak
        signatures=['0x'+keccak(text=s).hex() for s in ('TransferSingle(address,address,address,uint256,uint256)','TransferBatch(address,address,address,uint256[],uint256[])')]
        logs=rpc.call('eth_getLogs',[dict(address=CTF,fromBlock=hex(max(0,height-19)),toBlock=block,topics=[signatures,None,None,'0x'+wallet[2:].lower().rjust(64,'0')])])
        if not isinstance(logs,list) or len(logs)>=10000:raise ValueError('LOGS_TRUNCATED')
        seen=set()
        for l in logs:
            key=(l['transactionHash'],l['logIndex'])
            if key in seen or l.get('removed') is not False or l['address'].lower()!=CTF.lower() or not max(0,height-19)<=int(l['blockNumber'],16)<=height or l['topics'][3].lower()!='0x'+wallet[2:].lower().rjust(64,'0'):raise ValueError('LOG_SCOPE')
            seen.add(key)
        if rpc.call('eth_getBlockByNumber',[block,False])['hash']!=head['hash']:raise ValueError('ANCHOR_REORG')
        report.update(status='OBSERVED_PINNED_READS',anchor_number=height,anchor_hash=head['hash'],anchor_timestamp_ms=int(head['timestamp'],16)*1000,collateral_symbol=symbol,collateral_decimals=decimals,collateral_balance_raw=str(balance),incoming_ctf_log_count=len(logs),incoming_ctf_log_digest=digest(logs),log_scope='LAST_20_FINALIZED_BLOCKS_INCOMING_CTF_ONLY',canonical_recheck=True)
        for tx in txs:
            receipt=rpc.call('eth_getTransactionReceipt',[tx])
            item=dict(transaction_hash=tx,status='UNKNOWN',fee_effects_proven=False)
            if receipt and receipt.get('transactionHash','').lower()==tx.lower() and receipt.get('status')=='0x1':
                n=int(receipt['blockNumber'],16);canonical=rpc.call('eth_getBlockByNumber',[hex(n),False])
                if n<=height and canonical['hash']==receipt['blockHash']:
                    before=uint_word(call(data,hex(n-1)));after=uint_word(call(data,hex(n)))
                    from app.live.cash_evidence import reconcile_cash_delta
                    # A receipt can explain a block delta only if there were no other relevant movements.
                    previous=rpc.call('eth_getBlockByNumber',[hex(n-1),False])
                    stamp=time.time_ns()//1000000
                    evidence=dict(chain_id=137,wallet=wallet,collateral_contract=CONTRACT,before=dict(block_number=n-1,block_hash=previous['hash'],balance_raw=str(before)),after=dict(block_number=n,block_hash=canonical['hash'],balance_raw=str(after),observed_ms=stamp),canonical_blocks={str(n-1):previous['hash'],str(n):canonical['hash']},canonical_observed_ms=stamp,receipts=[dict(observed_ms=stamp,receipt=receipt)])
                    cash=reconcile_cash_delta(evidence,expected_wallet=wallet,expected_contract=CONTRACT,expected_transactions=[tx],now_ms=stamp)
                    item.update(status='SUCCESS_IN_PROVIDER_FINALIZED_CHAIN',receipt_digest=digest(receipt),cash_receipt_reconciliation=cash,shares_and_per_order_fees='UNATTRIBUTED_NOT_INFERRED_FROM_GAS_OR_FEE_RATE')
            report['receipts'].append(item)
        if not txs:report['settlement']='NO_SELECTED_MARKET_TRADE_TRANSACTION_TO_QUALIFY'
    except Exception as exc:
        report['blocker']=type(exc).__name__;report['status']='PARTIAL_READS_BLOCKED' if report.get('canonical_recheck') else 'BLOCKED'
    finally:report.update(requests=raw.calls,pacing=rpc.report(),finished_ms=time.time_ns()//1000000);raw.close()
    return report
