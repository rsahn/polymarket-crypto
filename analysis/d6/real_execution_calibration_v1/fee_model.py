"""Exact parameterized fee arithmetic. Fixture model, NEVER a live fee certificate.
SDK 0.11 formula: C*r*(p*(1-p))**exponent. Builder: C*p*bps/10000.
Native debit currency, rounding and applicability require their own evidence.
"""
from fractions import Fraction
from decimal import Decimal
from .binding_consumer import require
from .core import digest

SCHEMA='PARAMETERIZED_TRADING_FEES/1'
def number(v):
    require(type(v) in (str,int,Decimal),'FEE_EXACT_NUMBER_REQUIRED')
    d=Decimal(v);require(d.is_finite() and d>=0 and len(d.as_tuple().digits)<=100 and abs(d.adjusted())<=100,'FEE_NUMBER_RANGE')
    return Fraction(d)
def text(v):
    # All reported fees are quantized rational decimal amounts, not float approximations.
    n,d=v.numerator,v.denominator;places=0
    while d%2==0:d//=2;places+=1
    fives=0
    while d%5==0:d//=5;fives+=1
    require(d==1,'NONTERMINATING_FEE_OUTPUT');places=max(places,fives)
    units=v*10**places;require(units.denominator==1,'FEE_OUTPUT_SCALE')
    if not places:return str(units.numerator)
    s=str(units.numerator).rjust(places+1,'0');return (s[:-places]+'.'+s[-places:]).rstrip('0').rstrip('.')
def quantize(v,q,mode):
    x=v/q;n,r=divmod(x.numerator,x.denominator)
    if mode=='CEIL':n+=int(r>0)
    elif mode=='NEAREST_EVEN':n+=int(2*r>x.denominator or (2*r==x.denominator and n%2==1))
    elif mode!='FLOOR':raise ValueError('ROUNDING_UNSUPPORTED')
    return n*q

def platform_parameters_from_json(body):
    import json
    require(type(body) is str and len(body)<=65536,'FEE_PARAMETER_BODY')
    def unique(pairs):
        out={}
        for k,v in pairs:
            require(k not in out,'DUPLICATE_FEE_PARAMETER');out[k]=v
        return out
    raw=json.loads(body,parse_float=Decimal,object_pairs_hook=unique)
    require(type(raw) is dict and type(raw.get('fd')) is dict and 'r' in raw['fd'] and 'e' in raw['fd'],'FEE_PARAMETER_PRESENCE_UNKNOWN')
    rate=number(raw['fd']['r']);exponent=number(raw['fd']['e'])
    require(rate<=1 and exponent.denominator==1 and 0<=exponent<=8,'FEE_PARAMETER_RANGE_UNSUPPORTED')
    return dict(rate=text(rate),rate_unit='FRACTION',exponent=int(exponent),parameter_source='EXPLICIT_RAW_CLOB_FD',native_units=None,rounding=None,live_applicable=False)

def normalize_builder_rates(values,representation):
    require(representation in ('WIRE_BPS','SDK_FRACTIONS'),'BUILDER_RATE_REPRESENTATION_UNKNOWN')
    rates={}
    for role in ('maker','taker'):
        key='builder_'+role+'_fee_rate_bps' if representation=='WIRE_BPS' else role
        v=number(values[key]);limit=10000 if representation=='WIRE_BPS' else 1
        require(v<=limit,'BUILDER_RATE_RANGE')
        rates['builder_'+role+'_bps']=text(v if representation=='WIRE_BPS' else v*10000)
    return {**rates,'builder_rate_unit':'BPS'}

def validate_profile(p):
    from .log_schema import public_asset
    require(public_asset(p.get('outcome_token')),'OUTCOME_SHARE_ASSET_UNKNOWN')
    require(p.get('schema')==SCHEMA and p.get('applicability')=='FIXTURE_ONLY','FEE_PROFILE_NOT_QUALIFIED')
    require(p.get('formula')=='C_RATE_P1MP_POWER' and p.get('rate_unit')=='FRACTION','FEE_FORMULA_OR_RATE_UNIT_UNKNOWN')
    e=p.get('exponent');require(type(e) is int and 0<=e<=8,'FRACTIONAL_OR_UNKNOWN_EXPONENT_UNSUPPORTED')
    require(number(p['rate'])<=1 and type(p.get('taker_only')) is bool,'FEE_RATE_OR_ROLE_UNKNOWN')
    require(p.get('formula_currency') in ('USDC','pUSD') and p.get('settlement_currency') in ('USDC','pUSD'),'FEE_CURRENCY_UNKNOWN')
    if p['formula_currency']!=p['settlement_currency']:
        require(p.get('conversion_basis')=='EXPLICIT_FIXTURE_CONVERSION_NOT_LIVE','USDC_PUSD_MAPPING_UNPROVEN')
        require(number(p['conversion_upper'])>0,'CURRENCY_CONVERSION_UNKNOWN')
    else:require(number(p['conversion_upper'])==1,'SAME_CURRENCY_CONVERSION')
    require(type(p.get('builder_attached')) is bool and p.get('builder_rate_unit')=='BPS','BUILDER_PRESENCE_OR_UNIT_UNKNOWN')
    for k in ('builder_maker_bps','builder_taker_bps'):require(number(p[k])<=10000,'BUILDER_BPS_UNKNOWN')
    if not p['builder_attached']:require(number(p['builder_maker_bps'])==number(p['builder_taker_bps'])==0,'UNATTACHED_BUILDER_CONTRADICTION')
    require(p.get('rounding_mode') in ('FLOOR','CEIL','NEAREST_EVEN') and p.get('rounding_scope')=='PER_FILL_PER_COMPONENT' and p.get('rounding_stage')=='NATIVE_AFTER_CONVERSION','FEE_ROUNDING_UNKNOWN')
    for unit in ('cash','shares'):require(0<number(p[unit+'_quantum'])<=1,'FEE_QUANTUM_UNKNOWN')
    for side in ('BUY','SELL'):
        for component in ('platform','builder'):require(p['debits'][side][component] in ('cash','shares'),'NATIVE_FEE_UNIT_UNKNOWN')
    require(p.get('extra_components')=='NONE_IN_FIXTURE','ADDITIONAL_FEES_UNKNOWN')
    return p

def component_values(p,side,role,q,price):
    validate_profile(p);require(side in ('BUY','SELL') and role in ('MAKER','TAKER'),'FEE_ROLE_SIDE')
    require(0<price<1,'PRICE_DOMAIN')
    rate=number(p['rate']) if role=='TAKER' or not p['taker_only'] else Fraction(0)
    platform=q*rate*(price*(1-price))**p['exponent']*number(p['conversion_upper'])
    builder=q*price*number(p['builder_'+role.lower()+'_bps'])/10000
    return {'platform':platform,'builder':builder}

def fill_fee(p,*,side,role,shares,price):
    q=number(shares);price=number(price);require(q>0,'EMPTY_FILL')
    values=component_values(p,side,role,q,price);totals={'cash':Fraction(0),'shares':Fraction(0)}
    for key,value in values.items():
        unit=p['debits'][side][key];native=value if unit=='cash' else value/price
        totals[unit]+=quantize(native,number(p[unit+'_quantum']),p['rounding_mode'])
    require(totals['shares']<=q and (side!='SELL' or totals['cash']<=q*price),'FEES_EXCEED_FILL_PROCEEDS_OR_SHARES')
    return dict(schema=SCHEMA,scope='FIXTURE_CALCULATION_NOT_SETTLEMENT_EVIDENCE',cash_fee=text(totals['cash']),share_fee=text(totals['shares']),cash_currency=p['settlement_currency'],share_unit='OUTCOME_SHARES',share_token=p['outcome_token'],profile_digest=digest(p),live_applicable=False,actual_fee_proven=False)

def partial_fees(p,fills):
    require(type(fills) is list and 0<len(fills)<=1000,'PARTIAL_FILL_COUNT')
    result=[fill_fee(p,**f) for f in fills]
    return dict(cash_fee=text(sum((number(x['cash_fee']) for x in result),Fraction(0))),share_fee=text(sum((number(x['share_fee']) for x in result),Fraction(0))),fill_count=len(fills),share_token=p['outcome_token'],cash_currency=p['settlement_currency'],live_applicable=False)

def conservative_leg_bound(p,*,side,role,shares_cap,price_min,price_max,max_partials):
    validate_profile(p);lo,hi,q=map(number,(price_min,price_max,shares_cap))
    require(0<lo<=hi<1 and q>0 and type(max_partials) is int and 1<=max_partials<=1000,'UNBOUNDED_PRICE_SIZE_OR_PARTIALS')
    require(side in ('BUY','SELL') and role in ('MAKER','TAKER'),'FEE_ROLE_SIDE')
    peak=min(hi,max(lo,Fraction(1,2)))
    rate=number(p['rate']) if role=='TAKER' or not p['taker_only'] else Fraction(0)
    values={'platform':q*rate*(peak*(1-peak))**p['exponent']*number(p['conversion_upper']), 'builder':q*hi*number(p['builder_'+role.lower()+'_bps'])/10000}
    totals={'cash':Fraction(0),'shares':Fraction(0)}
    for key,cash_bound in values.items():
        unit=p['debits'][side][key];quantum=number(p[unit+'_quantum'])
        native=cash_bound if unit=='cash' else cash_bound/lo
        # Each explicitly supported rounding mode overshoots by < one quantum/component/fill.
        if native:totals[unit]+=quantize(native+max_partials*quantum,quantum,'CEIL')
    return dict(cash_fee_upper=text(totals['cash']),share_fee_upper=text(totals['shares']),cash_currency=p['settlement_currency'],share_token=p['outcome_token'],scope='FIXTURE_BOUND_TRADING_FEES_ONLY_NO_GAS_OR_OTHER_COSTS',live_applicable=False,profile_digest=digest(p))

def round_trip_bound(p,buy,sell,*,share_value_upper):
    require(buy.get('side')=='BUY' and sell.get('side')=='SELL','ROUND_TRIP_SIDES')
    value=number(share_value_upper);require(0<value<=1,'SHARE_TO_COLLATERAL_VALUE_UNKNOWN')
    legs=[conservative_leg_bound(p,**leg) for leg in (buy,sell)]
    cash=sum((number(x['cash_fee_upper']) for x in legs),Fraction(0));shares=sum((number(x['share_fee_upper']) for x in legs),Fraction(0))
    upper=quantize(cash+shares*value,number(p['cash_quantum']),'CEIL')
    return dict(cash_fee_upper=text(cash),share_fee_upper=text(shares),collateral_equivalent_upper=text(upper),share_value_upper=text(value),currency=p['settlement_currency'],share_token=p['outcome_token'],scope='FIXTURE_ROUND_TRIP_BOUND_NOT_A_LIVE_RESERVATION',live_applicable=False,actual_fee_proven=False)
