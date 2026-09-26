"""Strict read-only reconciliation of an untouched forward genesis.
Unmodelled D6 activity is rejected, never assigned invented PnL or fees.
"""
from decimal import Decimal
from .temporal_contract import inventory_stale_reason as stale_reason, RECONCILIATION_GUARD_MS, SESSION_RISK_GUARD_MS, ACCOUNT_READ_GUARD_MS
from .production_readonly import fresh


def evaluate_baseline(prior,remote,*,now):
    blocked=lambda reason:{'phase':'BLOCKED','reconciled':False,'reason':reason}
    recovery=lambda reason:{'phase':'RECOVERY_REQUIRED','reconciled':False,'reason':reason}
    try:
        if prior.get('integrity_verified') is not True:return blocked('LEDGER_INTEGRITY_UNPROVEN')
        if prior.get('phase')!='GENESIS_RECONCILED':return recovery('LOCAL_RECOVERY_REQUIRED')
        if prior['event_count']!=0:return recovery('LEDGER_ACTIVITY_REQUIRES_EXPLICIT_EVENT_PROJECTION')
        base=prior['snapshot']
        if remote.get('complete') is not True:return blocked('REMOTE_SCOPE_INCOMPLETE')
        if remote['wallet'].lower()!=base['wallet'].lower():return recovery('WALLET_MISMATCH')
        if remote['balance_raw']!=base['collateral']['balance_raw']:return recovery('COLLATERAL_DELTA_UNEXPLAINED')
        if any(remote[n] for n in ('orders','trades','positions')) or remote['events_count']!=0:
            return recovery('REMOTE_ACTIVITY_UNEXPLAINED')
        if not set(base['conditional_assets']['balances'])<=set(remote['balances']):return blocked('KNOWN_ASSET_NOT_OBSERVED')
        if any(not isinstance(v,str) or not v.isdigit() for v in remote['balances'].values()):return blocked('BALANCE_SCHEMA')
        if any(int(v)>0 for v in remote['balances'].values()):return recovery('CONDITIONAL_INVENTORY_UNEXPLAINED')
        if not fresh(remote['observed_ms'],now,RECONCILIATION_GUARD_MS):return blocked(stale_reason('RECONCILIATION'))
        raw=remote['balance_raw']
        if not isinstance(raw,str) or not raw.isdigit():return blocked('COLLATERAL_SCHEMA')
        return {'phase':'RECONCILED','reconciled':True,'observed_ms':remote['observed_ms'],
                'cash_collateral':str(Decimal(raw)/1000000),'collateral_symbol':'pUSD',
                'reserved_collateral':'0','net_pnl':'0','fees_collateral':'0','exposure_collateral':'0',
                'open_positions':0,'scope':'D6_FORWARD_LEDGER_SCOPED_BASELINE',
                'provenance':'UNCHANGED_GENESIS_CASH_AND_NO_LOCAL_OR_REMOTE_ACTIVITY',
                'prior_history_globally_known':False}
    except (KeyError,ValueError,TypeError,AttributeError):return blocked('RECONCILIATION_SCHEMA_INVALID')


class ObservationSource:
    def __init__(self,value):self.value=value
    def read(self):return dict(self.value)


class ForwardSessionRiskSource:
    def __init__(self,reconciliation,clock):self.reconciliation=reconciliation;self.clock=clock
    def read(self):
        r=self.reconciliation
        if r.get('reconciled') is not True or not fresh(r['observed_ms'],self.clock(),SESSION_RISK_GUARD_MS):
            return {'available':False,'reason':'SESSION_LEDGER_UNRECONCILED_OR_STALE'}
        return {**r,'available':True,'session_pnl':r['net_pnl'],
                'allow':Decimal(r['cash_collateral'])-Decimal(r['reserved_collateral'])>=25 and r['open_positions']==0}


def validate_generation(generation, now):
    """All five observations belong to one sealed acquisition, at original times.
    The on-chain watermark is evidence, never refreshed by sealing the envelope.
    """
    result={'complete':False,'reason':'GENERATION_PARTIAL_OR_INVALID','evaluated_ms':now}
    try:
        g=generation;parts=g['components'];required={'balance','orders','trades','positions','inventory'}
        if type(g['id']) is not int or g['id']<1 or set(parts)!=required:return result
        w=g['watermark']
        if type(w['block_number']) is not int or w['block_number']<0:return result
        for value in (g['ledger_hash'],w['block_hash']):
            if not isinstance(value,str) or len(value.removeprefix('0x'))!=64:return result
            int(value.removeprefix('0x'),16)
        if any(p.get('generation')!=g['id'] or p.get('complete') is not True for p in parts.values()):return result
        ages={n:now-p['observed_ms'] for n,p in parts.items()}
        if any(type(p['observed_ms']) is not int for p in parts.values()):return result
        stale=[n for n,p in parts.items() if not fresh(p['observed_ms'],now,ACCOUNT_READ_GUARD_MS)]
        return {**result,'id':g['id'],'watermark':dict(w),'component_age_ms':ages,
                'complete':not stale,'reason':'GENERATION_FRESH' if not stale else stale_reason('GENERATION'),
                'stale_components':sorted(stale)}
    except (KeyError,ValueError,TypeError,AttributeError):return result
