from dataclasses import dataclass

@dataclass(frozen=True)
class RiskLimits:
    bankroll_cap: float = 100.0
    max_order_notional: float = 25.0
    max_open_positions: int = 1
    session_loss_limit: float = 25.0

class RiskManager:
    def __init__(self, limits=RiskLimits()):
        self.limits=limits
    def approve(self, *, notional, bankroll, open_positions, session_pnl):
        reasons=[]
        if notional<=0 or notional>self.limits.max_order_notional: reasons.append("ORDER_NOTIONAL")
        if bankroll>self.limits.bankroll_cap: reasons.append("BANKROLL_CAP")
        if open_positions>=self.limits.max_open_positions: reasons.append("OPEN_POSITION_LIMIT")
        if session_pnl<=-self.limits.session_loss_limit: reasons.append("SESSION_LOSS_LIMIT")
        return (not reasons,reasons)
