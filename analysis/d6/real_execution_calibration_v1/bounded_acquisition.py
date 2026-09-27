"""No clients, credentials or network defaults. Provider invocation requires explicit authorization."""
import copy,inspect,time,asyncio
from .bounded_reconciliation import REQUIRED,SCHEMA,SCOPE,evaluate
from .core import digest
from .binding_consumer import require
async def acquire(path,*,providers,authorized_kinds,context,authority,expected_operator,clock=lambda:time.time_ns()//1000000,monotonic=time.monotonic):
    require(type(providers) is dict and set(providers)<=set(REQUIRED),'PROVIDER_SCOPE')
    require(set(providers)<=set(authorized_kinds),'PROVIDER_NOT_AUTHORIZED')
    bundle=dict(schema=SCHEMA,scope=SCOPE,market=context['market'],tokens=copy.deepcopy(context['tokens']))
    started=clock();require(type(started) is int,'CLOCK_TYPE')
    limits=[]
    for key in ('deadline_ms','market_expiry_ms'):
        if key in context:
            require(type(context[key]) is int,'DEADLINE_TYPE');limits.append((key,context[key]))
    mono_started=monotonic()
    total_budget=min((limit-started for _,limit in limits),default=5000)
    missing=[];deadline_blockers=[]
    for kind in REQUIRED:
        if kind not in providers:missing.append(kind);continue
        stamp=clock();require(type(stamp) is int and stamp>=started,'CLOCK_REGRESSION')
        deadline_blockers=[key.upper()+'_CROSSED' for key,limit in limits if stamp>=limit]
        if deadline_blockers:break
        elapsed=(monotonic()-mono_started)*1000
        require(0<=elapsed,'MONOTONIC_REGRESSION')
        remaining=min(min((limit-stamp for _,limit in limits),default=5000),total_budget-elapsed)
        require(remaining>0,'ACQUISITION_BUDGET_EXHAUSTED')
        call_context=copy.deepcopy(context);call_context['remaining_budget_ms']=remaining
        result=providers[kind](call_context)
        if inspect.isawaitable(result):
            # wait_for requests cooperative cancellation and owns the task until it ends.
            # It cannot forcibly interrupt a cancellation-suppressing provider.
            result=await asyncio.wait_for(result,remaining/1000)
        # Providers supply original provenance envelopes; bridge never attests/reseals them.
        require(type(result) is dict and result.get('kind')==kind and result.get('source_digest')==digest(result.get('payload')),'PROVIDER_RECORD')
        bundle[kind]=copy.deepcopy(result)
    if not deadline_blockers:require((monotonic()-mono_started)*1000<=max(0,total_budget),'ACQUISITION_BUDGET_EXHAUSTED')
    completed=clock();require(type(completed) is int and completed>=started,'CLOCK_REGRESSION')
    verdict=evaluate(path,bundle,authority=authority,now_ms=completed,expected_operator=expected_operator)
    for key,limit in limits:
        if completed>=limit:
            verdict['blockers'].append(key.upper()+'_CROSSED');verdict['status']='UNKNOWN_CUSTODY_REQUIRED'
    return dict(bundle=bundle,verdict=verdict,missing_records=missing,submit_allowed=False)

def verify_native_bundle(local,records):
    from .native_v2 import decode,SCHEMA as NATIVE
    executions=records['executions'];bindings=executions.get('order_hash_bindings',{})
    require(type(bindings) is dict and bindings,'LOCAL_ORDER_HASH_UNKNOWN')
    intents={}
    for h,cid in bindings.items():
        require(cid in local['orders'],'HASH_BINDING_FOREIGN_CLIENT');o=local['orders'][cid]
        # Exact durable payload binding, not a signed post-hoc assertion of native effects.
        require(o.get('order_id')==h,'HASH_NOT_IN_DURABLE_ACK')
        intents[h]={**o,'account':local['init']['account']}
    decoded={}
    deployments=executions.get('deployments',{})
    for row in records['receipts']['receipts']:
        r=row['receipt'];tx=r['transactionHash'];require(tx in deployments,'DEPLOYMENT_APPLICABILITY_UNKNOWN')
        d=decode(r,account=local['init']['account'],intents=intents,deployment=deployments[tx])
        for f in d['fills']:decoded[(tx,f['index'])]=f
    used=set()
    for f in executions['fills']:
        proof=f.get('native_effect_provenance',{});indices=proof.get('log_indices')
        require(type(indices) is list and len(indices)==1,'ONE_NATIVE_FILL_EVENT_REQUIRED')
        key=(f['transaction_hash'],indices[0]);require(key in decoded and key not in used,'NATIVE_EVENT_MISSING_OR_REUSED');used.add(key)
        e=decoded[key]
        require(all(f[k]==e[k] for k in ('order_id','side','token','notional_raw','gross_shares_raw','cash_fee_raw','share_fee_raw')),'DECODED_EFFECT_DISAGREEMENT')
    require(used==set(decoded),'UNRECONCILED_NATIVE_EVENT')
