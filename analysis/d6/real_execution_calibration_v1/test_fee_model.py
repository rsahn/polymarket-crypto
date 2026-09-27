import copy
from decimal import Decimal
from fractions import Fraction
import pytest
from .fee_model import *
from .qualification import FeeRisk

def profile(**kw):
    p=dict(schema=SCHEMA,outcome_token='123',applicability='FIXTURE_ONLY',formula='C_RATE_P1MP_POWER',rate_unit='FRACTION',rate='0.07',exponent=1,taker_only=True,formula_currency='USDC',settlement_currency='USDC',conversion_upper='1',builder_attached=True,builder_rate_unit='BPS',builder_maker_bps='30',builder_taker_bps='100',rounding_mode='CEIL',rounding_scope='PER_FILL_PER_COMPONENT',rounding_stage='NATIVE_AFTER_CONVERSION',cash_quantum='0.00001',shares_quantum='0.000001',extra_components='NONE_IN_FIXTURE',debits={'BUY':{'platform':'cash','builder':'cash'},'SELL':{'platform':'cash','builder':'cash'}})
    p.update(kw);return p

def test_documented_formula_fixture_and_additive_builder():
    p=profile();r=fill_fee(p,side='BUY',role='TAKER',shares='100',price='0.5')
    assert r['cash_fee']=='2.25' and r['share_fee']=='0' and not r['live_applicable']
    r=fill_fee(p,side='SELL',role='MAKER',shares='100',price='0.5')
    assert r['cash_fee']=='0.15'  # maker platform zero, builder not zero

def test_buy_share_debit_vs_sell_cash_are_explicit_fixture_modes():
    p=profile();p['debits']['BUY']['platform']='shares'
    buy=fill_fee(p,side='BUY',role='TAKER',shares='100',price='0.5')
    sell=fill_fee(p,side='SELL',role='TAKER',shares='100',price='0.5')
    assert (buy['cash_fee'],buy['share_fee'])==('0.5','3.5') and (sell['cash_fee'],sell['share_fee'])==('2.25','0')

@pytest.mark.parametrize('field,value',[('rate',True),('rate','NaN'),('rate','-1'),('rate_unit','BPS'),('exponent',1.5),('exponent',True),('rounding_mode',None),('rounding_scope','UNKNOWN'),('builder_attached',None),('builder_rate_unit','FRACTION'),('builder_taker_bps',None),('applicability','LIVE'),('extra_components','UNKNOWN')])
def test_unknown_or_unsupported_inputs_block(field,value):
    p=profile(**{field:value})
    with pytest.raises((ValueError,TypeError,ArithmeticError)):fill_fee(p,side='BUY',role='TAKER',shares='1',price='0.5')

def test_usdc_is_not_silently_pusd():
    p=profile(settlement_currency='pUSD')
    with pytest.raises(ValueError,match='MAPPING'):fill_fee(p,side='BUY',role='TAKER',shares='100',price='0.5')
    p.update(conversion_basis='EXPLICIT_FIXTURE_CONVERSION_NOT_LIVE',conversion_upper='2')
    r=fill_fee(p,side='BUY',role='TAKER',shares='100',price='0.5')
    assert r['cash_fee']=='4' and r['cash_currency']=='pUSD' and not r['live_applicable']

@pytest.mark.parametrize('price',['0','1','-0.1','NaN'])
def test_price_edges_invalid(price):
    with pytest.raises((ValueError,ArithmeticError)):fill_fee(profile(),side='BUY',role='TAKER',shares='1',price=price)

def test_partial_rounding_not_aggregate_rounding():
    p=profile(rate='0.00002',builder_maker_bps='0',builder_taker_bps='0',builder_attached=False)
    f=dict(side='BUY',role='TAKER',shares='1',price='0.5')
    assert partial_fees(p,[f,f])['cash_fee']=='0.00002'
    assert fill_fee(p,**{**f,'shares':'2'})['cash_fee']=='0.00001'
    p['rounding_mode']='FLOOR';assert fill_fee(p,**f)['cash_fee']=='0'
    p['rounding_mode']='NEAREST_EVEN';assert fill_fee(p,**f)['cash_fee']=='0'

def test_bound_covers_grid_extremes_exponents_and_partials():
    for exponent in (0,1,2,4):
        for side in ('BUY','SELL'):
            p=profile(exponent=exponent);p['debits']['BUY']['platform']='shares'
            b=conservative_leg_bound(p,side=side,role='TAKER',shares_cap='100',price_min='0.01',price_max='0.99',max_partials=10)
            for price in ('0.01','0.1','0.49','0.5','0.9','0.99'):
                if exponent==0 and side=='BUY' and price=='0.01':continue  # fixture fees exceed bought shares, explicitly rejected
                if exponent==0 and side=='SELL' and price=='0.01':continue
                fees=partial_fees(p,[dict(side=side,role='TAKER',shares='10',price=price)]*10)
                assert number(fees['cash_fee'])<=number(b['cash_fee_upper']) and number(fees['share_fee'])<=number(b['share_fee_upper'])

def test_unknown_partial_count_and_zero_price_floor_cannot_bound():
    args=dict(side='BUY',role='TAKER',shares_cap='100',price_min='0.1',price_max='0.9',max_partials=10)
    for change in ({'max_partials':None},{'max_partials':True},{'max_partials':0},{'price_min':'0'}):
        with pytest.raises(ValueError):conservative_leg_bound(profile(),**{**args,**change})

def test_round_trip_is_dimensioned_and_preserves_existing_risk_conversion():
    p=profile();p['debits']['BUY']['platform']='shares'
    leg=dict(role='TAKER',shares_cap='10',price_min='0.4',price_max='0.6',max_partials=5)
    b=round_trip_bound(p,{**leg,'side':'BUY'},{**leg,'side':'SELL'},share_value_upper='1')
    risk=FeeRisk(b['cash_fee_upper'],b['share_fee_upper'],b['share_value_upper'],'a'*64,'fixture-market',1000,'FIXTURE_ONLY')
    assert risk.conservative_cash(1)<=Decimal(b['collateral_equivalent_upper']) and not b['live_applicable']
    with pytest.raises(ValueError):FeeRisk('0','1',None,'a'*64,'fixture',1000).conservative_cash(1)

def test_sdk_builder_fractions_not_divided_by_bps_twice():
    from polymarket.models.clob.builder import BuilderFeeRates
    wire={'builder_maker_fee_rate_bps':'30','builder_taker_fee_rate_bps':'100'}
    parsed=BuilderFeeRates.model_validate(wire)
    assert parsed.taker==Decimal('0.01')
    assert normalize_builder_rates(wire,'WIRE_BPS')==normalize_builder_rates({'maker':parsed.maker,'taker':parsed.taker},'SDK_FRACTIONS')

def test_raw_sdk_fd_preserves_decimal_lexeme_without_guessing_native_rules():
    r=platform_parameters_from_json('{"fd":{"r":0.070000000000000001,"e":1.0}}')
    assert r['rate']=='0.070000000000000001' and r['exponent']==1 and r['rounding'] is None and r['native_units'] is None

@pytest.mark.parametrize('body',['{}','{"fd":null}','{"base_fee":1000}','{"fd":{"r":0.07}}','{"fd":{"r":0.07,"e":1.5}}','{"fd":{"r":0.07,"r":0,"e":1}}'])
def test_missing_legacy_ambiguous_or_fractional_fee_parameters_do_not_default_zero(body):
    with pytest.raises((ValueError,ArithmeticError)):platform_parameters_from_json(body)

def test_share_fee_asset_is_explicit_and_unknown_asset_blocks():
    p=profile();r=fill_fee(p,side='BUY',role='TAKER',shares='1',price='0.5')
    assert r['share_token']=='123'
    p['outcome_token']=None
    with pytest.raises(ValueError,match='ASSET_UNKNOWN'):fill_fee(p,side='BUY',role='TAKER',shares='1',price='0.5')
