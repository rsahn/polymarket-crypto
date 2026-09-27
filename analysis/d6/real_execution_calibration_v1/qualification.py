"""Independent verifier boundary. Structured evidence is not itself trusted."""
import copy
from dataclasses import dataclass
from .core import dec,digest
from .schemas import authenticate,integer,hash256,identifiers,frontier,text
from types import MappingProxyType

@dataclass(frozen=True)
class FeeRisk:
    cash_collateral: str
    outcome_shares: str
    collateral_per_share_upper: str | None
    source_digest: str
    market: str
    valid_until_ms: int
    epoch: str = 'UNQUALIFIED'
    def conservative_cash(self,now_ms):
        hash256(self.source_digest);text(self.market);integer(now_ms)
        cash,shares=dec(self.cash_collateral),dec(self.outcome_shares)
        if type(self.valid_until_ms) is not int or now_ms>self.valid_until_ms or not self.market or len(self.source_digest)!=64:raise ValueError('FEE_PROVENANCE_INVALID')
        if shares and self.collateral_per_share_upper is None:raise ValueError('FEE_UNITS_UNQUALIFIED')
        return cash+shares*dec(self.collateral_per_share_upper or '0')
    def validate_exit_policy(self,current,now_ms):
        current.conservative_cash(now_ms)
        if current.market!=self.market or current.epoch!=self.epoch:raise ValueError('EXIT_FEE_EPOCH_CHANGED')
        if dec(current.cash_collateral)>dec(self.cash_collateral) or dec(current.outcome_shares)>dec(self.outcome_shares):raise ValueError('EXIT_FEE_RESERVATION_INSUFFICIENT')
        if current.conservative_cash(now_ms)>self.conservative_cash(min(now_ms,self.valid_until_ms)):raise ValueError('EXIT_FEE_RESERVATION_INSUFFICIENT')

    def observed_cash(self,cash,shares,now_ms):
        # Expiry gates NEW reservations, not accounting of delayed fills under frozen policy.
        self.conservative_cash(min(now_ms,self.valid_until_ms))
        if dec(shares) and self.collateral_per_share_upper is None:raise ValueError('FEE_UNITS_UNQUALIFIED')
        return dec(cash)+dec(shares)*dec(self.collateral_per_share_upper or '0')

# Each check requires semantic evidence, not a pass boolean.
FIELDS={
 'wallet_account_identity_verified':('wallet','maker','signer'),
 'balance_sufficient':('available_cash','required_cash','collateral'),
 'market_identity_verified':('condition','tokens','expires_ms'),
 'sdk_order_path_qualified':('sdk_version','codec_digest','http_attempts','allowance_mutation'),
 'account_evidence_adapter_qualified':('scope','atomic_frontier','baseline_digest','fee_effects'),
 'fee_upper_bound_proven':('cash_collateral','outcome_shares','collateral_per_share_upper','fee_source_digest','coverage','epoch','late_fill_coverage'),
 'exit_handoff_ready':('owner','channel','durable_receipt_probe'),
 'ledger_healthy':('verified_sequence','journal_digest','free_bytes'),
 'kill_switch_tested':('test_digest','new_entries_after_kill','custody_verified'),
 'reconciliation_tested':('test_digest','independent_observations','unknown_events_rejected'),
 'clock_sanity':('offset_ms','uncertainty_ms'),
 'ws_healthy':('state','generation','tokens','receive_ms'),
 'tests_green':('test_digest','failed','passed'),
 'audit_pass':('audit_digest','reviewer','unresolved_critical'),
}
class EvidenceVerifier:
    """authority.verify(record) must authenticate independently stored evidence.
    No default authority. Fixture authorities are explicit dependency injections.
    """
    def __init__(self,authority,*,account,market,session,collateral,strategy_hashes):
        self.authority=authority;self._context=dict(account=account,market=market,session=session,collateral=collateral,strategy_hashes=dict(strategy_hashes))
    @property
    def context(self):return MappingProxyType(copy.deepcopy(self._context))
    def validate(self,check,record,now_ms):
        integer(now_ms)
        if not isinstance(record,dict):raise ValueError('EVIDENCE_ENVELOPE_REQUIRED')
        for k,v in self.context.items():
            if record.get(k)!=v:raise ValueError('EVIDENCE_CONTEXT_'+k)
        for k in ('observed_ms','valid_until_ms'):
            integer(record.get(k))
        if not record['observed_ms']<=now_ms<=record['valid_until_ms'] or now_ms-record['observed_ms']>5000:raise ValueError('EVIDENCE_STALE_OR_FUTURE')
        p=record.get('payload')
        if not isinstance(p,dict) or record.get('source_digest')!=digest(p) or record.get('check')!=check:raise ValueError('EVIDENCE_DIGEST_OR_CHECK')
        authenticate(self.authority,copy.deepcopy(record))
        if any(k not in p for k in FIELDS[check]):raise ValueError('EVIDENCE_FIELDS')
        for k,value in p.items():
            if k.endswith('digest'):hash256(value)
            if k in ('wallet','maker','signer','collateral','condition','sdk_version','scope','fee_effects','owner','channel','durable_receipt_probe','state','reviewer','coverage','epoch'):text(value)
            if k in ('allowance_mutation','custody_verified','independent_observations','unknown_events_rejected','late_fill_coverage') and type(value) is not bool:raise ValueError('BOOLEAN_REQUIRED')
            if k in ('http_attempts','verified_sequence','free_bytes','new_entries_after_kill','uncertainty_ms','generation','receive_ms','failed','passed','unresolved_critical','expires_ms'):integer(value)
            if k=='tokens':identifiers(value)
            if k=='atomic_frontier':frontier(value)
            if k=='offset_ms' and type(value) is not int:raise ValueError('INTEGER_REQUIRED')
        c=self.context
        ok={
         'wallet_account_identity_verified':lambda:p['wallet']==c['account'] and p['maker']==c['account'] and bool(p['signer']),
         'balance_sufficient':lambda:dec(p['available_cash'])>=dec(p['required_cash']) and p['collateral']==c['collateral'],
         'market_identity_verified':lambda:p['condition']==c['market'] and len(set(p['tokens']))==2 and p['expires_ms']>now_ms,
         'sdk_order_path_qualified':lambda:p['sdk_version']=='0.11.0' and len(p['codec_digest'])==64 and p['http_attempts']==1 and p['allowance_mutation'] is False,
         'account_evidence_adapter_qualified':lambda:p['scope']=='wallet' and bool(p['atomic_frontier']) and len(p['baseline_digest'])==64 and p['fee_effects']=='cash_and_shares',
         'fee_upper_bound_proven':lambda:p['coverage']=='ROUND_TRIP_FAK_1BUY_1SELL' and p['late_fill_coverage'] is True and FeeRisk(p['cash_collateral'],p['outcome_shares'],p['collateral_per_share_upper'],p['fee_source_digest'],c['market'],record['valid_until_ms']).conservative_cash(now_ms)>=0,
         'exit_handoff_ready':lambda:bool(p['owner'] and p['channel'] and p['durable_receipt_probe']),
         'ledger_healthy':lambda:type(p['verified_sequence']) is int and p['verified_sequence']>=0 and len(p['journal_digest'])==64 and p['free_bytes']>=512*1024**2,
         'kill_switch_tested':lambda:len(p['test_digest'])==64 and p['new_entries_after_kill']==0 and p['custody_verified'] is True,
         'reconciliation_tested':lambda:len(p['test_digest'])==64 and p['independent_observations'] is True and p['unknown_events_rejected'] is True,
         'clock_sanity':lambda:abs(p['offset_ms'])+p['uncertainty_ms']<=100 and p['uncertainty_ms']>=0,
         'ws_healthy':lambda:p['state']=='SYNCHRONIZED' and type(p['generation']) is int and len(set(p['tokens']))==2 and 0<=now_ms-p['receive_ms']<=1000,
         'tests_green':lambda:len(p['test_digest'])==64 and p['failed']==0 and p['passed']>0,
         'audit_pass':lambda:len(p['audit_digest'])==64 and bool(p['reviewer']) and p['unresolved_critical']==0,
        }[check]()
        if not ok:raise ValueError('CHECK_SEMANTICS_FAILED')
        return copy.deepcopy(p)

def inspect_evidence(record,now_ms,strategy_hashes):
    return 'INDEPENDENT_VERIFIER_REQUIRED'
