"""polymarket-client 0.11.0 raw CLOB trade boundary.
CONFIRMED/fee_rate_bps alone never prove final cash/share fee effects.
A separately authenticated effect record is mandatory for each raw trade.
"""
from .core import dec,digest
from .schemas import authenticate,integer,text

def normalize_trade(raw,intent,effect,authority,*,account,session,receive_ms):
    if type(raw) is not dict or type(effect) is not dict:raise ValueError('RAW_TRADE_SCHEMA')
    authenticate(authority,effect)
    for k,v in dict(raw_digest=digest(raw),account=account,session=session,order_id=intent['order_id'],trade_id=raw['id']).items():
        if effect.get(k)!=v:raise ValueError('EFFECT_BINDING')
    if effect.get('finality')!='FINAL' or raw['status']!='CONFIRMED':raise ValueError('SETTLEMENT_UNPROVEN')
    if effect.get('cash_effect_proven') is not True or effect.get('share_effect_proven') is not True:raise ValueError('FEE_EFFECT_UNPROVEN')
    oid=intent['order_id'];role=raw['trader_side'];makers=raw['maker_orders']
    if type(makers) is not list:raise ValueError('MAKER_LIST_SCHEMA')
    matches=[m for m in makers if m.get('order_id')==oid]
    if role=='TAKER':
        if raw['taker_order_id']!=oid or matches:raise ValueError('AMBIGUOUS_TRADE_ATTRIBUTION')
        row=raw;qty=raw['size']
    elif role=='MAKER':
        if raw['taker_order_id']==oid or len(matches)!=1:raise ValueError('AMBIGUOUS_TRADE_ATTRIBUTION')
        row=matches[0];qty=row['matched_amount']
        if row['maker_address'].lower()!=account.lower():raise ValueError('MAKER_IDENTITY')
    else:raise ValueError('TRADE_ROLE_UNKNOWN')
    token=row.get('asset_id',row.get('token_id'))
    if raw['market']!=intent['market'] or token!=intent['token'] or row['side']!=intent['side']:raise ValueError('TRADE_INTENT_IDENTITY')
    stamp=effect['exchange_ts_ms'];integer(stamp);integer(receive_ms)
    if not stamp<=receive_ms:raise ValueError('TRADE_CLOCK')
    if not 0<dec(row['price'])<1 or dec(qty)<=0:raise ValueError('TRADE_AMOUNT')
    return dict(trade_id=text(raw['id']),order_id=oid,token=token,market=intent['market'],side=intent['side'],price=str(dec(row['price'])),shares=str(dec(qty)),cash_fee=str(dec(effect['cash_fee'])),share_fee=str(dec(effect['share_fee'])),fee_evidence=dict(cash_effect_proven=True,share_effect_proven=True,effect_digest=digest(effect)),exchange_ts_ms=stamp,receive_ts_ms=receive_ms)
