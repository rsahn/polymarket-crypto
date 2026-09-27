"""Offline-testable RPC adapter. No HTTP implementation, credentials or implicit calls.
An injected transport is capability-bearing; actual RPC use needs separate approval.
"""
import asyncio,copy,re,time
from urllib.parse import urlsplit
from eth_utils import keccak
from .binding_consumer import require
from .core import digest
from .native_v2 import hx,addr,uinthex,COMMIT,SCHEMA,EXCHANGES,COLLATERAL,ASSET,FILLED,MATCHED,TRANSFER,SINGLE,BATCH

class BoundedRPC:
    def __init__(self,*,transport,endpoint,allowed_endpoints,transactions,blocks,clock=lambda:time.time_ns()//1000000,timeout_seconds=2,max_logs=500,max_span=32,monotonic=time.monotonic,deadline_ms=None,call_allowlist=()):
        u=urlsplit(endpoint)
        require(endpoint in allowed_endpoints and u.scheme=='https' and u.hostname and not u.username and not u.password and not u.fragment and not u.query,'RPC_ENDPOINT')
        require(callable(transport),'EXPLICIT_TRANSPORT_REQUIRED')
        require(type(blocks) is dict and 1<=len(blocks)<=256 and all(type(n) is int and n>=0 and hx(h,32)==h for n,h in blocks.items()),'PINNED_BLOCKS_REQUIRED')
        require(type(transactions) is list and len(transactions)<=1000 and len(set(transactions))==len(transactions),'TX_SCOPE')
        self.transactions={hx(t,32) for t in transactions};self.blocks=copy.deepcopy(blocks)
        require(type(max_logs) is int and 1<=max_logs<=1000 and type(max_span) is int and 1<=max_span<=32 and type(timeout_seconds) in (int,float) and 0<timeout_seconds<=5,'RPC_BOUNDS')
        self.deadline=deadline_ms;self.mono_end=monotonic()+max(0,(deadline_ms-clock())/1000) if deadline_ms is not None else None;self.call_allowlist=copy.deepcopy(list(call_allowlist));self.monotonic=monotonic;self.transport=transport;self.endpoint=endpoint;self.clock=clock;self.timeout=timeout_seconds;self.max_logs=max_logs;self.max_span=max_span;self.seq=0
    def validate(self,method,p):
        require(type(p) is list,'RPC_PARAMS')
        if method=='eth_chainId':require(p==[],'CHAIN_PARAMS')
        elif method=='eth_getBlockByNumber':require(len(p)==2 and p[1] is False and uinthex(p[0]) in self.blocks,'BLOCK_ALLOWLIST')
        elif method=='eth_getTransactionReceipt':require(len(p)==1 and p[0] in self.transactions,'TX_ALLOWLIST')
        elif method=='eth_getCode':require(len(p)==2 and addr(p[0]) in EXCHANGES and uinthex(p[1]) in self.blocks,'CODE_ALLOWLIST')
        elif method=='eth_call':require(p in self.call_allowlist,'ETH_CALL_NOT_ALLOWLISTED')
        elif method=='eth_getLogs':
            require(len(p)==1 and type(p[0]) is dict and set(p[0])=={'fromBlock','toBlock','address','topics'},'LOG_FILTER')
            f=p[0];lo,hi=uinthex(f['fromBlock']),uinthex(f['toBlock'])
            require(lo<=hi and hi-lo+1<=self.max_span and all(n in self.blocks for n in range(lo,hi+1)),'LOG_RANGE')
            require(addr(f['address']) in EXCHANGES|{COLLATERAL,ASSET} and type(f['topics']) is list and len(f['topics'])==1 and f['topics'][0] in {FILLED,MATCHED,TRANSFER,SINGLE,BATCH},'LOG_ALLOWLIST')
        else:raise ValueError('RPC_METHOD_NOT_ALLOWED')
    async def call(self,method,params):
        if self.deadline is not None:require(self.clock()<self.deadline and self.monotonic()<self.mono_end,'RPC_SHARED_DEADLINE')
        self.validate(method,params);start=self.clock();require(type(start) is int,'CLOCK_TYPE');self.seq+=1;mono=self.monotonic()
        req=dict(jsonrpc='2.0',id=self.seq,method=method,params=copy.deepcopy(params))
        response=await asyncio.wait_for(self.transport(self.endpoint,copy.deepcopy(req)),self.timeout)
        end=self.clock();require(type(end) is int and start<=end and end-start<=self.timeout*1000 and 0<=self.monotonic()-mono<=self.timeout,'RPC_LATE_OR_CLOCK_STEP')
        require(type(response) is dict and set(response)=={'jsonrpc','id','result'} and response['jsonrpc']=='2.0' and type(response['id']) is int and response['id']==req['id'],'RPC_RESPONSE')
        value=response['result']
        if method=='eth_call':hx(value,32)
        elif method=='eth_chainId':require(uinthex(value)==137,'RPC_CHAIN')
        elif method=='eth_getCode':require(type(value) is str and len(value)<=100000 and re.fullmatch('0x(?:[0-9a-fA-F]{2})*',value) is not None,'RPC_CODE_TYPE')
        elif method=='eth_getBlockByNumber':
            require(type(value) is dict and uinthex(value['number'])==uinthex(params[0]) and hx(value['hash'],32)==self.blocks[uinthex(params[0])],'CANONICAL_HASH_MISMATCH')
        elif method=='eth_getTransactionReceipt':require(type(value) is dict and hx(value['transactionHash'],32)==params[0],'RPC_RECEIPT_TYPE')
        elif method=='eth_getLogs':require(type(value) is list and len(value)<self.max_logs,'LOG_TRUNCATION_UNKNOWN')
        return dict(read_start_ms=start,observed_ms=end,payload=copy.deepcopy(value))
    async def canonical(self,n):
        r=await self.call('eth_getBlockByNumber',[hex(n),False]);b=r['payload']
        require(type(b) is dict and uinthex(b['number'])==n and hx(b['hash'],32)==self.blocks[n],'CANONICAL_HASH_MISMATCH');return r
    def log(self,l):
        require(type(l) is dict and l.get('removed') is False,'REMOVED_OR_LOG_SCHEMA')
        n=uinthex(l['blockNumber']);require(n in self.blocks and hx(l['blockHash'],32)==self.blocks[n],'LOG_CANONICAL')
        hx(l['transactionHash'],32);uinthex(l['logIndex']);addr(l['address'])
        require(type(l['topics']) is list and 1<=len(l['topics'])<=4,'LOG_TOPICS')
        for t in l['topics']:hx(t,32)
        require(type(l['data']) is str and len(l['data'])<=26000 and re.fullmatch('0x(?:[0-9a-fA-F]{2})*',l['data']) is not None,'LOG_DATA')
    async def receipt(self,tx):
        start=self.clock();r=await self.call('eth_getTransactionReceipt',[tx]);v=r['payload']
        require(type(v) is dict and hx(v['transactionHash'],32)==tx and v['status']=='0x1','RECEIPT_TX_STATUS')
        n=uinthex(v['blockNumber']);require(n in self.blocks and hx(v['blockHash'],32)==self.blocks[n],'RECEIPT_BLOCK')
        require(type(v['logs']) is list and len(v['logs'])<self.max_logs,'RECEIPT_LOG_BOUND');seen=set()
        for l in v['logs']:
            self.log(l);i=uinthex(l['logIndex']);require(i not in seen and l['transactionHash']==tx and l['blockHash']==v['blockHash'] and uinthex(l['blockNumber'])==n,'RECEIPT_LOG_CONTEXT');seen.add(i)
        check=await self.canonical(n)
        return dict(receipt=v,receipt_digest=digest(v),read_start_ms=start,observed_ms=check['observed_ms'],source_observation=r,canonical_recheck=check,finality_proven=False)
    async def logs(self,*,address,topic,lo,hi):
        require(type(lo) is int and type(hi) is int and lo<=hi and hi-lo<256,'TOTAL_LOG_RANGE')
        rows=[];pages=[];seen=set();start=self.clock()
        for first in range(lo,hi+1,self.max_span):
            last=min(hi,first+self.max_span-1)
            page=await self.call('eth_getLogs',[dict(address=address,topics=[topic],fromBlock=hex(first),toBlock=hex(last))])
            values=page['payload'];require(type(values) is list and len(values)<self.max_logs,'LOG_TRUNCATION_UNKNOWN')
            for l in values:
                self.log(l);key=(l['transactionHash'],uinthex(l['logIndex']))
                require(key not in seen and first<=uinthex(l['blockNumber'])<=last and addr(l['address'])==addr(address) and l['topics'][0]==topic,'LOG_FILTER_OR_DUPLICATE');seen.add(key);rows.append(l)
            pages.append(page)
        for n in range(lo,hi+1):await self.canonical(n)
        return dict(logs=rows,pages=pages,read_start_ms=start,observed_ms=self.clock(),queried_range_complete=True,coverage_proven=False,limitation='RPC_MAY_OMIT_LOGS_NO_INDEPENDENT_COMPLETENESS_PROOF')
    async def deployment(self,*,exchange,block,artifact,artifact_verifier):
        # Artifact authenticity/compiler/immutables must be independently verified BEFORE code read.
        require(type(artifact) is dict and callable(artifact_verifier) and artifact_verifier(copy.deepcopy(artifact)) is True,'VERIFIED_RUNTIME_ARTIFACT_MISSING')
        require(artifact.get('source_commit')==COMMIT and artifact.get('chain_id')==137 and artifact.get('exchange')==exchange and artifact.get('kind')=='EXACT_NONPROXY_RUNTIME' and artifact.get('unresolved_immutables')==[],'RUNTIME_ARTIFACT_UNSUPPORTED')
        if artifact.get('fixture_only') is not True:
            require(type(artifact.get('build_provenance')) is dict and bool(artifact['build_provenance']),'RUNTIME_BUILD_PROVENANCE_MISSING')
        expected=artifact['runtime_code'];require(type(expected) is str and re.fullmatch('0x(?:[0-9a-fA-F]{2})+',expected) is not None and len(expected)<=100000,'EXPECTED_RUNTIME_CODE')
        chain=await self.call('eth_chainId',[]);require(chain['payload']=='0x89','RPC_CHAIN')
        before=await self.canonical(block);code=await self.call('eth_getCode',[exchange,hex(block)]);after=await self.canonical(block)
        require(code['payload']==expected,'RUNTIME_BYTECODE_MISMATCH')
        return dict(version=SCHEMA,source_commit=COMMIT,chain_id=137,exchange=exchange,collateral=COLLATERAL,asset=ASSET,applicability='FIXTURE_ONLY' if artifact.get('fixture_only') is True else 'VERIFIED_DEPLOYMENT_AT_BLOCK',block_hash=self.blocks[block],block_number=block,bytecode_verified=True,runtime_code_hash='0x'+keccak(bytes.fromhex(expected[2:])).hex(),artifact_digest=digest(artifact),read_start_ms=before['read_start_ms'],observed_ms=after['observed_ms'])
    def provider(self,kind,reader):
        """Explicit bridge callback, no attestation factory; reader returns original qualified envelope."""
        from .bounded_reconciliation import REQUIRED
        require(kind in REQUIRED and callable(reader),'BRIDGE_PROVIDER')
        async def invoke(context):return await reader(self,copy.deepcopy(context))
        return invoke
