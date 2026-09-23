"""Live execution boundary. Real submission is deliberately disabled by default."""
import os,time
from dataclasses import dataclass
from .risk import RiskManager

@dataclass(frozen=True)
class OrderIntent:
    signal_id:str; market_slug:str; token_id:str; side:str; notional:float

class LiveExecutor:
    def __init__(self, risk=None):
        self.risk=risk or RiskManager()
        self.real_enabled=os.getenv("REAL_ORDERS_ENABLED","false").lower()=="true"

    async def submit(self,intent,*,bankroll,open_positions,session_pnl):
        ok,reasons=self.risk.approve(notional=intent.notional,bankroll=bankroll,
            open_positions=open_positions,session_pnl=session_pnl)
        event={"ts_ms":int(time.time()*1000),"signal_id":intent.signal_id,
          "market_slug":intent.market_slug,"token_id":intent.token_id,"side":intent.side,
          "notional":intent.notional,"risk_ok":ok,"risk_reasons":reasons,
          "real_orders_enabled":self.real_enabled}
        if not ok:return {**event,"status":"RISK_REJECT"}
        if not self.real_enabled:return {**event,"status":"DRY_RUN"}
        # Safety boundary: API wiring will be added only after OOS validation.
        return {**event,"status":"LIVE_NOT_WIRED"}
