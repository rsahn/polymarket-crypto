from dataclasses import dataclass

@dataclass
class PaperFill:
    side: str
    qty: float
    price: float
    fee: float
    slippage: float

class PaperExecutor:
    def __init__(self, capital=20.0, max_unhedged=2.0):
        self.capital = capital
        self.max_unhedged = max_unhedged
        self.fills: list[PaperFill] = []

    def simulate_buy(self, side: str, ask: float, ask_qty: float, requested_qty: float, fee_rate=0.0, slippage=0.0):
        qty = min(requested_qty, ask_qty)
        px = min(1.0, ask + slippage)
        notional = qty * px
        if qty <= 0 or notional > self.capital: return None
        fee = notional * fee_rate
        if notional + fee > self.capital: return None
        self.capital -= notional + fee
        fill = PaperFill(side, qty, px, fee, slippage)
        self.fills.append(fill)
        return fill
