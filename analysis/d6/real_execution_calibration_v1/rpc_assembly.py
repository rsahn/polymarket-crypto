"""Explicit opt-in read-only composition. No import-time I/O, activation or credentials."""
import asyncio,copy,hashlib,http.client,json,time
from urllib.parse import urlsplit
from .binding_consumer import require
from .bounded_rpc import BoundedRPC
from .bounded_acquisition import acquire,verify_native_bundle
from .bounded_reconciliation import local_journal,SCHEMA,SCOPE
from .core import digest
from .native_v2 import COMMIT

class HTTPSReadOnly:
    def __init__(self,*,endpoint,approved_endpoint,max_calls,deadline_ms,clock,connection_factory=http.client.HTTPSConnection,max_bytes=1048576):
        u=urlsplit(endpoint)
        require(endpoint==approved_endpoint and u.scheme=='https' and u.hostname and not u.username and not u.password and not u.query and not u.fragment,'HTTP_ENDPOINT_APPROVAL')
        require(type(max_calls) is int and 1<=max_calls<=256 and type(deadline_ms) is int and type(max_bytes) is int and 1024<=max_bytes<=2097152,'HTTP_BUDGET')
        self.endpoint=endpoint;self.u=u;self.remaining=max_calls;self.deadline=deadline_ms;self.clock=clock;self.factory=connection_factory;self.max_bytes=max_bytes;self.validator=None;self.mono_end=time.monotonic()+max(0,(deadline_ms-clock())/1000)
    def _request(self,endpoint,request):
        require(endpoint==self.endpoint and self.validator is not None,'HTTP_CONTEXT')
        require(type(request) is dict and set(request)=={'jsonrpc','id','method','params'} and request['jsonrpc']=='2.0' and type(request['id']) is int,'HTTP_RPC_ENVELOPE')
        self.validator(request['method'],request['params'])
        left=min(self.deadline-self.clock(),(self.mono_end-time.monotonic())*1000);require(left>0 and self.remaining>0,'HTTP_BUDGET_EXHAUSTED');self.remaining-=1
        c=self.factory(self.u.hostname,port=self.u.port or 443,timeout=min(2,left/1000))
        try:
            c.request('POST',self.u.path or '/',body=json.dumps(request,separators=(',',':')).encode(),headers={'Content-Type':'application/json','Accept':'application/json','Connection':'close'})
            r=c.getresponse();require(r.status==200,'HTTP_STATUS_OR_REDIRECT')
            require(r.getheader('Content-Encoding','identity')=='identity' and r.getheader('Content-Type','').split(';')[0].strip()=='application/json','HTTP_ENCODING_TYPE')
            chunks=[];size=0;mono=time.monotonic();wall_budget=min(2,left/1000)
            while True:
                remaining=min((self.deadline-self.clock())/1000,wall_budget-(time.monotonic()-mono))
                require(remaining>0,'HTTP_READ_DEADLINE')
                if getattr(c,'sock',None) is not None:c.sock.settimeout(remaining)
                chunk=r.read1(min(65536,self.max_bytes+1-size))
                if not chunk:break
                chunks.append(chunk);size+=len(chunk);require(size<=self.max_bytes,'HTTP_SIZE')
            data=b''.join(chunks);require(self.clock()<self.deadline,'HTTP_SIZE_OR_DEADLINE')
            def unique(pairs):
                d={}
                for k,v in pairs:require(k not in d,'DUPLICATE_JSON_FIELD');d[k]=v
                return d
            return json.loads(data,object_pairs_hook=unique,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('JSON_CONSTANT')))
        finally:c.close()
    async def __call__(self,endpoint,request):
        # A socket thread cannot be killed safely. Keep ownership until its bounded socket work ends.
        task=asyncio.create_task(asyncio.to_thread(self._request,endpoint,copy.deepcopy(request)))
        cancelled=False
        while True:
            try:
                value=await asyncio.shield(task)
                if cancelled:raise asyncio.CancelledError()
                return value
            except asyncio.CancelledError:
                cancelled=True
                if task.done():
                    try:task.result()
                    except BaseException:pass
                    raise

class RuntimeArtifactVerifier:
    """Trust pins must come from independently approved origin, not this artifact itself."""
    def __init__(self,*,trusted_manifests):self.trusted=copy.deepcopy(trusted_manifests)
    def __call__(self,artifact):
        try:
            origin=artifact['origin'];expected=self.trusted[origin]
            require(type(expected) is str and len(expected)==64 and digest(artifact)==expected,'ARTIFACT_TRUST_PIN')
            require(artifact['source_commit']==COMMIT and artifact['kind']=='EXACT_NONPROXY_RUNTIME' and artifact['unresolved_immutables']==[],'ARTIFACT_BUILD_SCOPE')
            build=artifact['build_provenance']
            for k in ('compiler_version','compiler_settings','source_sha256','dependencies','libraries','constructor_immutables'):require(k in build,'ARTIFACT_BUILD_INCOMPLETE')
            require(build['compiler_version']=='0.8.30' and type(build['source_sha256']) is dict and bool(build['source_sha256']),'ARTIFACT_COMPILER_SOURCE')
            sources=artifact['source_contents'];require(set(sources)==set(build['source_sha256']),'ARTIFACT_SOURCE_SET')
            for path,content in sources.items():require(hashlib.sha256(content.encode()).hexdigest()==build['source_sha256'][path],'ARTIFACT_SOURCE_DIGEST')
            require(hashlib.sha256(bytes.fromhex(artifact['runtime_code'][2:])).hexdigest()==artifact['runtime_sha256'],'ARTIFACT_RUNTIME_DIGEST')
            return True
        except (KeyError,ValueError,TypeError):return False

async def assemble(path,*,endpoint,approved_endpoint,transactions,blocks,context,source_records,source_authority,expected_operator,clock,deadline_ms,max_calls,log_queries=(),artifacts=None,trusted_manifests=None,connection_factory=http.client.HTTPSConnection,reader_plan=None,provider_identity=None,fixture_only=False):
    """Concrete HTTP->RPC->receipt/code/log->envelope->acquire path.
    Authenticated baseline/closing/finality/coverage inputs remain external evidence;
    transport observations never certify their own completeness or artifact authenticity.
    """
    local=local_journal(path);ctx=copy.deepcopy(context)
    require(type(context.get('market_expiry_ms',deadline_ms)) is int,'MARKET_EXPIRY_TYPE')
    deadline_ms=min(deadline_ms,context.get('market_expiry_ms',deadline_ms));ctx['deadline_ms']=deadline_ms
    http=HTTPSReadOnly(endpoint=endpoint,approved_endpoint=approved_endpoint,max_calls=max_calls,deadline_ms=deadline_ms,clock=clock,connection_factory=connection_factory)
    rpc=BoundedRPC(transport=http,endpoint=endpoint,allowed_endpoints=[approved_endpoint],transactions=transactions,blocks=blocks,clock=clock,deadline_ms=deadline_ms)
    http.validator=rpc.validate
    records=copy.deepcopy(source_records);observations={};generated={};readers=None
    if reader_plan is not None:
        from .concrete_readers import ConcreteReaders
        readers=ConcreteReaders(rpc,account=local['init']['account'],tokens=ctx['tokens'],market=ctx['market'],**reader_plan)
    def envelope(kind,payload):
        r=dict(kind=kind,chain_id=137,scope=SCOPE,account=local['init']['account'],experiment=local['experiment'],payload=payload,source_digest=digest(payload),observation_only=True,provider_identity=provider_identity,fixture_only=fixture_only)
        generated[kind]=copy.deepcopy(r);return r
    async def receipts(c):
        rows=[]
        for tx in transactions:
            require(clock()<min(deadline_ms,c.get('market_expiry_ms',deadline_ms)),'ASSEMBLY_DEADLINE')
            rows.append(await rpc.receipt(tx))
        observations['receipts']=rows
        return envelope('receipts',{'receipts':rows})
    async def executions(c):
        base=records.get('executions')
        require(base is not None,'EXECUTION_CORRELATION_UNKNOWN')
        payload=copy.deepcopy(base['payload']);deployments={}
        verifier=RuntimeArtifactVerifier(trusted_manifests=trusted_manifests or {})
        for row in observations.get('receipts',[]):
            r=row['receipt'];tx=r['transactionHash'];artifact=(artifacts or {}).get(tx)
            require(artifact is not None,'AUTHENTICATED_RUNTIME_ARTIFACT_MISSING')
            deployments[tx]=await rpc.deployment(exchange=artifact['exchange'],block=int(r['blockNumber'],16),artifact=artifact,artifact_verifier=verifier)
        payload['deployments']=deployments
        verify_native_bundle(local,{'executions':payload,'receipts':{'receipts':observations.get('receipts',[])}})
        return envelope('executions',payload)
    # REQUIRED evaluates executions before receipts; materialize receipts within executions lazily.
    async def execution_reader(c):
        await receipts(c)
        return await executions(c)
    async def receipt_reader(c):
        if 'receipts' not in generated:await receipts(c)
        return copy.deepcopy(generated['receipts'])
    async def coverage_reader(c):
        observations['logs']=[]
        for query in log_queries:
            require(clock()<min(deadline_ms,c.get('market_expiry_ms',deadline_ms)),'ASSEMBLY_DEADLINE')
            observations['logs'].append(await rpc.logs(**query))
        # No source coverage proof is upgraded by an empty or successful query.
        require('coverage' in records,'COVERAGE_UNKNOWN');return copy.deepcopy(records['coverage'])
    providers={}
    for k in records:providers[k]=lambda c,k=k:copy.deepcopy(records[k])
    providers.update(executions=execution_reader,receipts=receipt_reader,coverage=coverage_reader)
    if readers is not None:
        async def baseline(c):
            original=copy.deepcopy(records.get('baseline'))
            require(source_authority.verify(original,role='source') is True,'BASELINE_SOURCE_UNTRUSTED')
            p=original['payload']
            require(p['block_number']==readers.lo and p['block_hash']==blocks[readers.lo],'BASELINE_BLOCK_BINDING')
            require(all(p['observed_ms']<=o['send_intent_ms'] for o in local['orders'].values()),'BASELINE_NOT_PRE_INTENT')
            later=await readers.snapshot(readers.lo)
            for key in ('chain_id','collateral_contract','asset_contract','cash_raw','assets_raw','block_number','block_hash'):
                require(p[key]==later[key],'BASELINE_CORROBORATION_MISMATCH')
            observations['baseline_corroboration']=later
            # Original authenticated acquisition times retained; later read never backdated.
            return original
        async def closing(c):return envelope('closing',await readers.snapshot(readers.hi))
        async def finality(c):
            require(source_authority.verify(copy.deepcopy(records.get('finality')),role='source') is True,'FINALITY_SOURCE_UNTRUSTED')
            return envelope('finality',await readers.finality(records.get('finality',{}).get('payload')))
        async def terminal(c):return envelope('terminal_orders',readers.terminal(records.get('terminal_orders',{}).get('payload',{}).get('orders'),{o['order_id']:o for o in local['orders'].values() if o['order_id']}))
        async def coverage(c):
            require(source_authority.verify(copy.deepcopy(records.get('coverage')),role='source') is True,'COVERAGE_SOURCE_UNTRUSTED')
            await coverage_reader(c)
            await receipts(c)
            return envelope('coverage',readers.coverage(records.get('coverage',{}).get('payload'),observations['logs'],observations['receipts']))
        providers.update(baseline=baseline,closing=closing,finality=finality,terminal_orders=terminal,coverage=coverage)
    class Authority:
        def verify(self,r):
            # Generated observations are intentionally NOT trusted qualification records.
            # They require an independent source authority to authenticate the exact content.
            return source_authority.verify(copy.deepcopy(r))
    try:
        result=await acquire(path,providers=providers,authorized_kinds=list(providers),context=ctx,authority=Authority(),expected_operator=expected_operator,clock=clock)
    except (ValueError,KeyError,TimeoutError,OSError) as exc:
        result=dict(verdict=dict(status='UNKNOWN_CUSTODY_REQUIRED',blockers=[str(exc)],submit_allowed=False),submit_allowed=False)
    return dict(result=result,observations=observations,remaining_calls=http.remaining,submit_allowed=False)
