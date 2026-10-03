"""Nested schemas for externally sourced records. Unknown fields never reach sinks."""
from .core import dec
import re

def public_asset(value):
    return type(value) is str and re.fullmatch(r"(?:0|[1-9][0-9]{0,77})",value) is not None and int(value)<2**256

BOOK={'valid','ws_healthy','market','token','book_state_id','source_ms','receive_ms','asks','bids','generation'}
FILL={'trade_id','order_id','token','market','side','price','shares','cash_fee','share_fee','fee_evidence','exchange_ts_ms','receive_ts_ms','transaction_hash'}
SNAP={'source_record_digest','account','observed_ms','cash','positions','open_orders','trade_ids','terminal_order_ids','inventory_proven','cash_proven','orders_complete','trades_complete','positions_complete','atomic_frontier','scope','session','collateral','baseline_digest','experiment_trade_ids','ancestor_frontiers'}
SHADOW={'opportunity_id','market','token','direction','signal_receive_ts','signal_decision_ts','signal_source_ts','btc_move','btc_lookback_evidence','actual_selected_book','selected_book','actual_entry_observation_ts','expected_entry_price','expected_quantity','expected_vwap','expected_fill','expected_entry_cost','expected_residual','expected_fee','fee_status','expected_exit_behavior','strategy_hashes','expected_proceeds','expected_sold','exit_due_ms','actual_exit_observation_ms'}

def project(value,fields,tokens):
    if not isinstance(value,dict):return {}
    result={}
    for k,v in value.items():
        if k not in fields:continue
        if k=='token':result[k]=v if type(v) is str and v in tokens else '[REDACTED]'
        elif k in ('book','actual_selected_book','selected_book'):result[k]=project(v,BOOK,tokens)
        elif k=='fee_evidence':result[k]=project(v,{'cash_effect_proven','share_effect_proven','effect_digest'},tokens)
        elif k=='positions':
            if not isinstance(v,dict):raise ValueError('POSITIONS_SCHEMA')
            if any(t not in tokens and not public_asset(t) for t in v):raise ValueError('UNSAFE_ASSET_ID')
            result[k]={t:str(dec(q)) for t,q in v.items()}
        elif k=='atomic_frontier':result[k]=project(v,{'sequence','digest'},tokens)
        elif k=='ancestor_frontiers':result[k]=[project(x,{'sequence','digest'},tokens) for x in v] if isinstance(v,list) else []
        elif k=='btc_lookback_evidence':result[k]=[project(x,{'source_ms','receive_ms','price'},tokens) for x in v] if isinstance(v,list) else []
        elif k=='expected_exit_behavior':result[k]=project(v,{'hold_ms','depth'},tokens)
        elif k=='strategy_hashes':
            from .v1_binding import verify
            allowed=verify();result[k]={name:h for name,h in v.items() if name in allowed and h==allowed[name]} if isinstance(v,dict) else {}
        elif k in ('asks','bids'):
            result[k]=[[str(dec(p)),str(dec(q))] for p,q in v] if isinstance(v,list) else []
        elif isinstance(v,dict):continue
        elif isinstance(v,(list,tuple)):
            result[k]=[x for x in v if type(x) in (str,int,float,bool) or x is None]
        elif type(v) in (str,int,float,bool) or v is None:result[k]=v
    return result

def nested_payload(kind,payload,tokens):
    out=dict(payload)
    for key,fields in (('snapshot',SNAP),('fill',FILL),('shadow',SHADOW),('book',BOOK)):
        if key in out:out[key]=project(out[key],fields,tokens)
    if kind=='DURABLE_INTENT' and 'token' in out:out['token']=out['token'] if out['token'] in tokens else '[REDACTED]'
    return out
