"""Polymarket CLOB order builder/validator. DRY-RUN ONLY."""
from dataclasses import asdict,dataclass
from decimal import Decimal,ROUND_DOWN
import time

@dataclass(frozen=True)
class PreparedOrder:
    signal_id:str;market_slug:str;token_id:str;side:str
    notional:float;limit_price:float;size:float;created_ts_ms:int

class ClobDryRunAdapter:
    def prepare_buy(self,*,signal_id,market_slug,token_id,notional,best_ask,max_slippage_bps=100):
        if not market_slug or not token_id: raise ValueError("missing market/token")
        n=Decimal(str(notional));ask=Decimal(str(best_ask))
        if n<=0 or ask<=0 or ask>=1: raise ValueError("invalid notional/ask")
        cap=ask*(Decimal(1)+Decimal(str(max_slippage_bps))/Decimal(10000))
        cap=min(cap,Decimal("0.99"))
        # Conservative cent tick for dry-run; live adapter must use market tick metadata.
        price=cap.quantize(Decimal("0.01"),rounding=ROUND_DOWN)
        if price<ask: price=ask.quantize(Decimal("0.01"))
        size=(n/price).quantize(Decimal("0.0001"),rounding=ROUND_DOWN)
        return PreparedOrder(signal_id,market_slug,token_id,"BUY",float(n),float(price),float(size),int(time.time()*1000))

    def serialize(self,order):
        return {"mode":"DRY_RUN","submit_allowed":False,"order":asdict(order)}
