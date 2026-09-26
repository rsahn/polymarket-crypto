"""Semantic diagnostics, not execution permission. All uncalibrated domains block.
Existing execution and fixed-C protections remain independently enforced.
"""
from decimal import Decimal, InvalidOperation

BOOK_MAX_AGE_MS = 500
SIGNAL_MAX_AGE_MS = 500  # retained controller guard, not the V1 lookback
GEOBLOCK_MAX_AGE_MS = 60000


def domain_policy(name):
    limits={'book':BOOK_MAX_AGE_MS,'signal':SIGNAL_MAX_AGE_MS,'geoblock':GEOBLOCK_MAX_AGE_MS}
    if name in ('authentication','transport','recovery'):
        return dict(limit_ms=None,calibration='STRUCTURAL_INVARIANT',justification='IDENTITY_STATE_AND_SEQUENCE')
    if name=='inventory':
        return dict(limit_ms=None,calibration='COMPLETENESS_UNPROVEN',justification='NO_COMMON_POST_C_COMPLETENESS_WATERMARK')
    return dict(limit_ms=limits.get(name),calibration='CONSERVATIVE_EXISTING_POLICY' if name in limits else 'UNCALIBRATED',
        justification='RETAINED_NOT_EMPIRICALLY_CALIBRATED' if name in limits else 'NO_JUSTIFIED_TEMPORAL_SLA')


def age_ms(observed,now):
    if type(observed) is not int or type(now) is not int or observed<0 or observed>now:return None
    return now-observed


def within(observed,now,limit):
    age=age_ms(observed,now)
    return age is not None and age<=limit


def generation_structure(g,now,ledger_hash=None):
    """Identity/completeness of supplied observations, NEVER remote atomicity."""
    result=dict(complete=False,reason='GENERATION_IDENTITY_OR_COVERAGE_INVALID',scope='STRUCTURAL_ONLY')
    try:
        if ledger_hash is not None and g.get('ledger_hash')!=ledger_hash:return result
        parts=g['components'];required={'balance','orders','trades','positions','inventory'}
        if type(g['id']) is not int or g['id']<1 or set(parts)!=required:return result
        w=g['watermark']
        if type(w['block_number']) is not int or w['block_number']<0:return result
        for value in (g['ledger_hash'],w['block_hash']):
            if not isinstance(value,str) or len(value.removeprefix('0x'))!=64:return result
            int(value.removeprefix('0x'),16)
        valid={n:type(p.get('generation')) is int and p.get('generation')==g['id'] and p.get('complete') is True and age_ms(p.get('observed_ms'),now) is not None for n,p in parts.items()}
        return {**result,'complete':all(valid.values()),'component_valid':valid,'id':g['id'],
                'reason':'GENERATION_STRUCTURALLY_COHERENT' if all(valid.values()) else result['reason']}
    except (KeyError,TypeError,ValueError,AttributeError):return result


def assess_domains(values,*,now,local,generation,collateral_unit):
    a,p,b,r,s,g=(values.get(k,{}) for k in ('account','positions','book','risk','signal','geo'))
    local=local if isinstance(local,dict) else {};result={}
    def emit(name,value,valid,failure,*,requires_calibration=True):
        policy=domain_policy(name);stamp=value.get('observed_ms')
        calibrated=policy['calibration']=='STRUCTURAL_INVARIANT' or not requires_calibration
        result[name]=dict(**policy,observed_ms=stamp,age_ms=age_ms(stamp,now),observation_valid=bool(valid),
            ready=bool(valid and calibrated),reason=failure if not valid else name.upper()+'_UNCALIBRATED' if not calibrated else 'INVARIANT_SATISFIED')
    def observed(v):return v.get('available') is True and age_ms(v.get('observed_ms'),now) is not None
    def amount(v):
        try:
            if isinstance(v,bool):return None
            n=Decimal(str(v));return n if n.is_finite() else None
        except (InvalidOperation,ValueError):return None
    emit('transport',b,b.get('connected') is True,'WS_DISCONNECTED',requires_calibration=False)
    book_ok=(b.get('connected') is True and b.get('synchronized',b.get('book_synced')) is True
        and b.get('fresh') is True and within(b.get('observed_ms'),now,BOOK_MAX_AGE_MS)
        and b.get('reason') in (None,'EMPTY_BOOK'))
    ba=age_ms(b.get('observed_ms'),now)
    emit('book',b,book_ok,'BOOK_STALE' if ba is not None and ba>BOOK_MAX_AGE_MS else 'BOOK_INVALID_OR_UNAVAILABLE')
    sa=age_ms(s.get('observed_ms'),now)
    emit('signal',s,observed(s) and s.get('valid') is True and within(s.get('observed_ms'),now,SIGNAL_MAX_AGE_MS),
         'SIGNAL_STALE' if sa is not None and sa>SIGNAL_MAX_AGE_MS else 'SIGNAL_UNAVAILABLE')
    emit('authentication',a,observed(a) and a.get('authenticated') is True,'AUTHENTICATION_INVALID',requires_calibration=False)
    denom=collateral_unit=='USDC' or a.get('collateral_symbol')==collateral_unit
    for name,field in [('balance','balance_usdc' if collateral_unit=='USDC' else 'balance_collateral'),
                       ('allowance','allowance_usdc' if collateral_unit=='USDC' else 'allowance_collateral')]:
        n=amount(a.get(field))
        emit(name,a,observed(a) and a.get('authenticated') is True and denom and n is not None and n>=25,
             'INSUFFICIENT_COLLATERAL_OR_UNKNOWN' if name=='balance' else 'ALLOWANCE_INVALID_OR_UNKNOWN')
    seq=generation_structure(generation,now,local.get('last_hash'))
    parts=seq.get('component_valid',{})
    orders_ok=seq['complete'] and observed(a) and a.get('complete') is True and a.get('pagination_complete') is True and a.get('open_order_ids')==[] and parts.get('orders') is True and parts.get('trades') is True
    emit('orders',a,orders_ok,'OPEN_ORDER_STATE_UNCERTAIN')
    balances=p.get('balances');flat=isinstance(balances,dict) and all(amount(v)==0 for v in balances.values())
    positions_ok=seq['complete'] and observed(p) and p.get('complete') is True and flat and parts.get('positions') is True
    emit('positions',p,positions_ok,'POSITION_STATE_UNCERTAIN')
    # No supplied bool or timeout can replace a supported completeness verifier.
    emit('inventory',p,False,'INVENTORY_UNPROVEN')
    recovery_ok=(local.get('integrity_verified') is True and isinstance(local.get('last_hash'),str)
        and len(local['last_hash'])==64 and all(c in '0123456789abcdef' for c in local['last_hash'].lower()) and local.get('phase') in ('CLOSED','GENESIS_RECONCILED')
        and (local['phase']=='CLOSED' or local.get('reconciled_now') is True))
    emit('recovery',local,recovery_ok,'RECOVERY_STATE_INVALID',requires_calibration=False)
    emit('account_reconciliation',a,orders_ok and positions_ok and recovery_ok and a.get('reconciled') is True and seq['complete'],'ACCOUNT_UNRECONCILED')
    risk_ok=recovery_ok and observed(r) and all(r.get(k) is True for k in ('allow','reconciled','fees_complete','exposure_known','no_unresolved_execution')) and seq['complete']
    emit('session_risk',r,risk_ok,'SESSION_RISK_UNRECONCILED')
    emit('geoblock',g,observed(g) and g.get('blocked') is False and within(g.get('observed_ms'),now,GEOBLOCK_MAX_AGE_MS),
         'GEOBLOCK_UNKNOWN_OR_STALE',requires_calibration=False)
    return result

# Transitional guard budgets. Retained to avoid weakening execution while the
# semantic contract is calibrated. These are NOT justified production SLAs.
ACCOUNT_READ_GUARD_MS = 500
POSITIONS_READ_GUARD_MS = 500
SESSION_RISK_GUARD_MS = 500
RECONCILIATION_GUARD_MS = 500
INVENTORY_OBSERVATION_GUARD_MS = 500
EXECUTION_GEO_GUARD_MS = 500
CASH_EVIDENCE_GUARD_MS = 500

def inventory_observation_limit_ms():return INVENTORY_OBSERVATION_GUARD_MS
def inventory_stale_reason(prefix):return f'{prefix}_STALE_{INVENTORY_OBSERVATION_GUARD_MS}MS'

def retained_guards():
    return {name:dict(limit_ms=value,status='CONSERVATIVE_EXISTING_POLICY',calibrated=False) for name,value in
        [('account',ACCOUNT_READ_GUARD_MS),('positions',POSITIONS_READ_GUARD_MS),('session_risk',SESSION_RISK_GUARD_MS),
         ('reconciliation',RECONCILIATION_GUARD_MS),('inventory_observation',INVENTORY_OBSERVATION_GUARD_MS),
         ('execution_geo',EXECUTION_GEO_GUARD_MS),('cash_evidence',CASH_EVIDENCE_GUARD_MS)]}
