"""Validate raw CLOB trades BEFORE SDK coercion. Filters are never attribution proof."""
import re
from datetime import datetime,timezone
from decimal import Decimal
from .log_schema import public_asset

class TradeScopeError(ValueError):
    def __init__(self,reason):self.reason=reason;super().__init__(reason)

def require(ok,reason):
    if not ok:raise TradeScopeError(reason)

def address(value):
    require(type(value) is str and re.fullmatch(r'0x[0-9a-fA-F]{40}',value) is not None,'TRADE_ADDRESS_SCHEMA')
    return value.lower()

def identifier(value):
    require(type(value) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',value) is not None,'TRADE_ORDER_OR_ID_SCHEMA')
    return value

def amount(value):
    require(type(value) in (str,int) and re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',str(value)) is not None and len(str(value))<=100,'TRADE_AMOUNT_SCHEMA')
    return Decimal(str(value))

def stamp_us(value):
    if type(value) is int or (type(value) is str and re.fullmatch(r'(?:0|[1-9][0-9]{0,10})',value)):
        require(0<=int(value)<10**11,'TRADE_TIMESTAMP_SCHEMA');return int(value)*1000000
    require(type(value) is str and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})',value) is not None,'TRADE_TIMESTAMP_SCHEMA')
    try:
        d=datetime.fromisoformat(value.replace('Z','+00:00'))-datetime(1970,1,1,tzinfo=timezone.utc)
        return (d.days*86400+d.seconds)*1000000+d.microseconds
    except (ValueError,OverflowError):raise TradeScopeError('TRADE_TIMESTAMP_SCHEMA') from None

def token(row,tokens):
    value=row.get('asset_id',row.get('token_id'))
    require(public_asset(value),'TRADE_TOKEN_SCHEMA')
    require('asset_id' not in row or 'token_id' not in row or row['asset_id']==row['token_id'],'TRADE_TOKEN_ALIAS_CONFLICT')
    require(value in tokens,'TRADE_FOREIGN_ASSET');return value

def validate_trade(raw,*,account,market,tokens,start_seconds,expiry_ms,received_ms):
    require(type(raw) is dict,'TRADE_ROW_SCHEMA')
    try:
        tid=identifier(raw['id']);who=address(account);identifier(raw['owner'])
        require(type(raw['bucket_index']) is int and 0<=raw['bucket_index']<2**31,'TRADE_BUCKET_SCHEMA')
        require(type(raw['market']) is str and re.fullmatch(r'0x[0-9a-fA-F]{64}',raw['market']) is not None,'TRADE_MARKET_SCHEMA')
        require(raw['market'].lower()==market.lower(),'TRADE_FOREIGN_MARKET')
        require('condition_id' not in raw or raw['condition_id']==raw['market'],'TRADE_MARKET_ALIAS_CONFLICT')
        matched=stamp_us(raw['match_time']);updated=stamp_us(raw['last_update'])
        require(start_seconds*1000000<=matched<expiry_ms*1000 and matched<=received_ms*1000,'TRADE_OUTSIDE_WINDOW')
        require(matched<=updated<=received_ms*1000,'TRADE_UPDATE_WINDOW')
        top_token=token(raw,tokens);top_address=address(raw['maker_address'])
        require(type(raw['outcome']) is str and raw['outcome'].upper()==('UP' if top_token==tokens[0] else 'DOWN'),'TRADE_OUTCOME_SCHEMA')
        role=raw['trader_side'];require(type(role) is str and role in ('MAKER','TAKER'),'TRADE_ROLE_UNKNOWN')
        side=raw['side'];require(type(side) is str and side in ('BUY','SELL'),'TRADE_SIDE_SCHEMA')
        size=amount(raw['size']);require(size>0 and 0<amount(raw['price'])<1,'TRADE_AMOUNT_RANGE')
        amount(raw['fee_rate_bps'])
        status=raw['status'];require(type(status) is str and status in ('MATCHED','MINED','CONFIRMED','RETRYING','FAILED'),'TRADE_STATUS_UNKNOWN')
        taker=identifier(raw['taker_order_id']);makers=raw['maker_orders']
        require(type(makers) is list and 0<len(makers)<=128,'TRADE_MAKER_LIST_SCHEMA')
        seen=set();own=[]
        for m in makers:
            require(type(m) is dict,'TRADE_MAKER_SCHEMA')
            oid=identifier(m['order_id']);ma=address(m['maker_address']);mt=token(m,tokens);identifier(m['owner'])
            require(type(m['outcome']) is str and m['outcome'].upper()==('UP' if mt==tokens[0] else 'DOWN'),'TRADE_OUTCOME_SCHEMA')
            require(oid not in seen and oid!=taker,'TRADE_AMBIGUOUS_ORDER');seen.add(oid)
            require(type(m['side']) is str and m['side'] in ('BUY','SELL'),'TRADE_SIDE_SCHEMA')
            require(0<amount(m['price'])<1 and 0<amount(m['matched_amount'])<=size,'TRADE_AMOUNT_RANGE')
            if m.get('fee_rate_bps') is not None:amount(m['fee_rate_bps'])
            if ma==who:own.append((oid,mt,m['side']))
        # The top-level address is accepted as taker attribution ONLY with explicit
        # TAKER role and no own maker leg. Maker attribution requires a unique leg.
        if role=='TAKER':
            require(top_address==who,'TRADE_FOREIGN_ACCOUNT')
            require(not own,'TRADE_AMBIGUOUS_ROLE');oid=taker;selected_token=top_token;selected_side=side
        else:
            require(len(own)>0,'TRADE_FOREIGN_ACCOUNT');require(len(own)==1,'TRADE_AMBIGUOUS_ROLE')
            oid,selected_token,selected_side=own[0]
        if 'taker_address' in raw:
            explicit_taker=address(raw['taker_address'])
            require(explicit_taker==who if role=='TAKER' else explicit_taker!=who,'TRADE_AMBIGUOUS_ROLE')
        tx=raw['transaction_hash']
        if tx=='':
            require(status not in ('MINED','CONFIRMED'),'TRADE_TRANSACTION_MISSING');tx=None
        else:
            require(type(tx) is str and re.fullmatch(r'0x[0-9a-fA-F]{64}',tx) is not None and int(tx[2:],16)!=0,'TRADE_TRANSACTION_SCHEMA');tx=tx.lower()
        selected_row=raw if role=='TAKER' else next(m for m in makers if m['order_id']==oid)
        return dict(trade_id=tid,order_id=oid,account=who,role=role,market=market,token=selected_token,side=selected_side,price=str(amount(selected_row['price'])),shares=str(amount(selected_row['size' if role=='TAKER' else 'matched_amount'])),cash_fee=None,share_fee=None,matched_us=matched,status=status,transaction_hash=tx if status in ('MINED','CONFIRMED') else None)
    except KeyError:raise TradeScopeError('TRADE_REQUIRED_FIELD_MISSING') from None

async def collect_scoped_trades(client,*,account,market,tokens,start_seconds,expiry_ms,clock):
    from polymarket._internal.actions import account as a
    from .observation_collector import bounded_pages
    accepted=[];seen=set();failed_index=None
    before=len(getattr(client.clob,'observations',[]))
    context=dict(account=account,market=market,tokens=tokens,start_seconds=start_seconds,expiry_ms=expiry_ms)
    def parse(payload):
        nonlocal failed_index
        failed_index=None
        require(type(payload) is dict and type(payload.get('data')) is list,'TRADE_PAGE_SCHEMA')
        require(len(accepted)+len(payload['data'])<=200,'TRADE_ITEM_LIMIT')
        received_ms=clock()
        for raw in payload['data']:
            failed_index=len(accepted)
            row=validate_trade(raw,received_ms=received_ms,**context)
            require(row['trade_id'] not in seen,'TRADE_DUPLICATE_ID');seen.add(row['trade_id']);accepted.append(row)
        failed_index=None
        return a.parse_account_trades_page(payload)
    def provenance():
        observed=getattr(client.clob,'observations',[])[before:]
        return dict(validation_source='RAW_CLOB_BEFORE_SDK_COERCION',market=market,window_start_seconds=start_seconds,window_end_ms=expiry_ms,response_digests=[r['response_digest'] for r in observed if r.get('endpoint')=='https://clob.polymarket.com/data/trades' and type(r.get('response_digest')) is str and re.fullmatch('[0-9a-f]{64}',r['response_digest'])])
    try:
        pagesource=client._pages(lambda **kw:a.build_list_account_trades_request(market=market,after=str(start_seconds),**kw),parse)
        values,complete,pages=await bounded_pages(pagesource)
        require(len(values)==len(accepted),'TRADE_VALIDATION_PATH_BYPASSED')
        statuses={}
        for row in accepted:statuses[row['status']]=statuses.get(row['status'],0)+1
        return dict(status='OBSERVED_ATTRIBUTED',count=len(accepted),count_scope='VALIDATED_RETURNED_ROWS_ONLY',pages=pages,pagination_complete=complete,scope='CREDENTIAL_SELECTED_MARKET_SINCE_SLOT_START',status_counts=statuses,complete=False,atomic_frontier=None,settlement_finality_proven=False,fee_effects_proven=False,provenance=provenance()),accepted
    except Exception as exc:
        return dict(status='BLOCKED',reason=exc.reason if isinstance(exc,TradeScopeError) else 'TRADE_RESPONSE_OR_PAGINATION_UNQUALIFIED',failed_row_index=failed_index,count=None,pagination_complete=False,complete=False,receipt_candidates_allowed=False,provenance=provenance()),[]
