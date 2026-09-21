from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class PaperFill:
    trade_id: str
    leg: int
    side: str
    requested_qty: float
    filled_qty: float
    observed_ask: float
    price: float
    notional: float
    fee: float
    slippage_per_contract: float
    slippage_cost: float
    timestamp_ms: int

    @property
    def partial(self) -> bool:
        return self.filled_qty + 1e-12 < self.requested_qty


@dataclass
class PaperTrade:
    trade_id: str
    market_id: str
    market_duration: str
    strategy: str
    opened_at_ms: int
    status: str = "OPEN"
    up_qty: float = 0.0
    down_qty: float = 0.0
    up_cost: float = 0.0
    down_cost: float = 0.0
    fees: float = 0.0
    slippage_cost: float = 0.0
    closed_at_ms: Optional[int] = None
    hedge_eligible_at_ms: Optional[int] = None
    hedge_deadline_ms: Optional[int] = None
    first_side: Optional[str] = None
    fills: list[PaperFill] = field(default_factory=list)

    @property
    def paired_qty(self) -> float:
        return min(self.up_qty, self.down_qty)

    @property
    def unhedged_qty(self) -> float:
        return abs(self.up_qty - self.down_qty)

    @property
    def hedge_status(self) -> str:
        if self.up_qty <= 0 and self.down_qty <= 0:
            return "NONE"
        if self.up_qty > 0 and self.down_qty > 0:
            return "FULLY_HEDGED" if self.unhedged_qty <= 1e-9 else "PARTIAL_HEDGE"
        return "UNHEDGED"

    @property
    def gross_pnl_if_settled(self) -> float:
        q = self.paired_qty
        if q <= 0:
            return 0.0
        up_avg = self.up_cost / self.up_qty if self.up_qty else 0.0
        down_avg = self.down_cost / self.down_qty if self.down_qty else 0.0
        return q * (1.0 - up_avg - down_avg)

    @property
    def net_pnl_if_settled(self) -> float:
        return self.gross_pnl_if_settled - self.fees


class PaperExecutor:
    # Conservative top-of-book simulator: no hidden depth and no real orders.
    def __init__(self, capital=500.0, max_unhedged=2.0, fee_rate=0.0, slippage=0.0):
        self.initial_capital = float(capital)
        self.cash = float(capital)
        self.max_unhedged = float(max_unhedged)
        self.default_fee_rate = float(fee_rate)
        self.default_slippage = float(slippage)
        self.fills: list[PaperFill] = []

    @property
    def capital(self):
        return self.cash

    def simulate_buy(self, *, trade_id, leg, side, ask, ask_qty, requested_qty,
                     timestamp_ms, fee_rate=None, slippage=None):
        try:
            ask = float(ask)
            ask_qty = max(0.0, float(ask_qty))
            requested_qty = max(0.0, float(requested_qty))
        except (TypeError, ValueError):
            return None
        if not (0.0 < ask <= 1.0) or ask_qty <= 0 or requested_qty <= 0:
            return None

        fee_rate = self.default_fee_rate if fee_rate is None else max(0.0, float(fee_rate))
        slip = self.default_slippage if slippage is None else max(0.0, float(slippage))
        px = min(1.0, ask + slip)
        unit_cash = px * (1.0 + fee_rate)
        qty = min(requested_qty, ask_qty, self.cash / unit_cash)
        if qty <= 1e-12:
            return None

        notional = qty * px
        fee = notional * fee_rate
        slippage_cost = qty * max(0.0, px - ask)
        self.cash -= notional + fee

        fill = PaperFill(
            trade_id, int(leg), str(side).upper(), requested_qty, qty, ask, px,
            notional, fee, max(0.0, px - ask), slippage_cost, int(timestamp_ms)
        )
        self.fills.append(fill)
        return fill

    def apply_fill(self, trade: PaperTrade, fill: PaperFill):
        if fill.trade_id != trade.trade_id:
            raise ValueError("fill/trade mismatch")
        if fill.side == "UP":
            trade.up_qty += fill.filled_qty
            trade.up_cost += fill.notional
        elif fill.side == "DOWN":
            trade.down_qty += fill.filled_qty
            trade.down_cost += fill.notional
        else:
            raise ValueError(f"unsupported side: {fill.side}")
        trade.fees += fill.fee
        trade.slippage_cost += fill.slippage_cost
        trade.fills.append(fill)


    def refund_unfilled_trade(self, trade: PaperTrade) -> None:
        """No-op placeholder: fills consume cash; unfilled requested qty never did."""

    def settle_guaranteed_pair(self, trade: PaperTrade) -> float:
        """Return guaranteed net PnL for the paired quantity only.

        This does not resolve any directional residual inventory.
        """
        return trade.net_pnl_if_settled
