from dataclasses import dataclass

@dataclass
class PairState:
    up_qty: float = 0
    down_qty: float = 0
    up_cost: float = 0
    down_cost: float = 0

    @property
    def paired_qty(self): return min(self.up_qty, self.down_qty)

    @property
    def directional_up(self): return max(self.up_qty-self.down_qty, 0)

    @property
    def directional_down(self): return max(self.down_qty-self.up_qty, 0)

def pair_cost(up_price: float, down_price: float) -> float:
    return up_price + down_price

def pair_edge(up_price: float, down_price: float, friction: float = 0.0) -> float:
    return 1.0 - pair_cost(up_price, down_price) - friction
