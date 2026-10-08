"""Simulation engine — tracks fake positions and resolves them against real market outcomes.

No real orders, no blockchain transactions. Uses gamma-api to check resolution prices.
Reports PnL as if trades were real.
"""
import asyncio, json, time, urllib.request
from decimal import Decimal
from pathlib import Path


class ResolutionChecker:
    """Polls gamma-api to check resolved market prices."""

    GAMMA_API = "https://gamma-api.polymarket.com"

    @staticmethod
    def get_outcome_prices(condition_id: str, market_slug: str = None) -> tuple:
        """Return (up_price, down_price) for a resolved market, or (None, None).
        
        Uses market_slug for precise lookup (condition_id is ambiguous in gamma-api).
        Falls back to condition_id if slug not available.
        """
        if market_slug:
            url = f"{ResolutionChecker.GAMMA_API}/markets?slug={market_slug}"
        else:
            url = f"{ResolutionChecker.GAMMA_API}/markets?condition_id={condition_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read(100000))
            if not data:
                return None, None
            # markets?slug= returns the event, extract first market
            items = data
            if isinstance(items, list) and len(items) > 0:
                first = items[0]
                if "markets" in first:
                    # It's an event, use first market
                    markets = first.get("markets", [])
                    if markets:
                        m = markets[0]
                    else:
                        return None, None
                else:
                    m = first
            else:
                return None, None
            prices = json.loads(m.get("outcomePrices", '["?","?"]'))
            closed = m.get("closed", False)
            p0, p1 = float(prices[0]), float(prices[1])
            # Resolved if officially closed OR if prices are strongly directional (>0.9 or <0.1)
            # Chainlink TWAP markets resolve immediately after end date
            if closed or p0 > 0.9 or p1 > 0.9 or p0 < 0.1 or p1 < 0.1:
                return p0, p1
            return None, None
        except Exception:
            return None, None

    @staticmethod
    def get_market_by_slug(slug: str) -> dict:
        """Get market data by event slug."""
        url = f"{ResolutionChecker.GAMMA_API}/events?slug={slug}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read(100000))
            if data and data[0].get("markets"):
                return data[0]
        except Exception:
            pass
        return {}


class SimulatedPosition:
    """One simulated trade — bought tokens, waiting for resolution."""

    def __init__(self, opportunity_id, slot_key, token, side,
                 entry_price, shares, cost, condition_id, market_slug,
                 entry_ms, predicted_direction):
        self.opportunity_id = opportunity_id
        self.slot_key = slot_key
        self.token = token
        self.side = side          # 'BUY' or 'SELL' signal
        self.entry_price = entry_price
        self.shares = shares
        self.cost = cost
        self.condition_id = condition_id
        self.market_slug = market_slug
        self.entry_ms = entry_ms
        self.predicted_direction = predicted_direction  # 'UP' or 'DOWN'
        self.resolved = False
        self.exit_price = None
        self.pnl = Decimal("0")
        self.resolved_at = None

    def __repr__(self):
        status = "RESOLVED" if self.resolved else "PENDING"
        return (f"<SimPos {self.slot_key} {self.predicted_direction} "
                f"@{self.entry_price:.4f} {self.shares:.2f}sh ${self.cost:.2f} "
                f"{status} PnL={self.pnl:.2f}>")


class Simulator:
    """Manages all simulated positions and resolves them on market closure."""

    def __init__(self, starting_cash=Decimal("100.00")):
        self.cash = starting_cash
        self.starting_cash = starting_cash
        self.positions = []  # list of SimulatedPosition
        self.closed_positions = []  # resolved positions
        self.total_pnl = Decimal("0")
        self.wins = 0
        self.losses = 0
        self.total_trades = 0
        self.pending_resolution = {}  # condition_id -> list of positions

    def open_position(self, slot_key, side, entry_price, shares, cost,
                      condition_id, market_slug, token):
        """Record a new simulated position."""
        predicted = "UP" if side == "BUY" else "DOWN"
        pos = SimulatedPosition(
            opportunity_id=f"sim:{slot_key}:{int(time.time()*1000)}",
            slot_key=slot_key, token=token, side=side,
            entry_price=entry_price, shares=shares, cost=cost,
            condition_id=condition_id, market_slug=market_slug,
            entry_ms=int(time.time()*1000),
            predicted_direction=predicted,
        )
        self.positions.append(pos)
        self.total_trades += 1
        self.cash -= cost

        # Group by condition_id for resolution checking
        if condition_id not in self.pending_resolution:
            self.pending_resolution[condition_id] = []
        self.pending_resolution[condition_id].append(pos)

        return pos

    def check_resolutions(self, max_check=5):
        """Poll gamma-api for resolved markets. Returns list of just-resolved positions."""
        resolved_now = []
        checked = 0
        for cond_id, pos_list in list(self.pending_resolution.items()):
            if checked >= max_check:
                break
            checked += 1
            # Use the first position's market_slug for precise resolution lookup
            slug = pos_list[0].market_slug if pos_list else None
            up_price, down_price = ResolutionChecker.get_outcome_prices(cond_id, slug)
            if up_price is None:
                continue  # Not resolved yet

            # Market is resolved
            for pos in pos_list:
                if pos.resolved:
                    continue
                # Determine payout based on predicted direction
                if pos.predicted_direction == "UP":
                    pos.exit_price = Decimal(str(up_price))
                else:
                    pos.exit_price = Decimal(str(down_price))

                pos.resolved = True
                pos.resolved_at = int(time.time() * 1000)

                # PnL = (exit_value - cost) where exit_value = shares * exit_price
                exit_value = Decimal(str(pos.shares)) * pos.exit_price
                pos.pnl = exit_value - pos.cost
                self.total_pnl += pos.pnl

                # CREDIT CASH: return the full exit value (cost basis + profit)
                # At entry: self.cash -= cost
                # At resolution: self.cash += exit_value (shares * exit_price)
                # This restores the original cost basis PLUS any profit
                self.cash += exit_value

                if pos.pnl > 0:
                    self.wins += 1
                else:
                    self.losses += 1

                self.closed_positions.append(pos)
                resolved_now.append(pos)

            # Remove from pending
            del self.pending_resolution[cond_id]

        return resolved_now

    def summary(self):
        """Return a summary string."""
        win_rate = (self.wins / (self.wins + self.losses) * 100) if (self.wins + self.losses) > 0 else 0
        return (
            f"\n{'='*60}\n"
            f"  SIMULATION SUMMARY\n"
            f"{'='*60}\n"
            f"  Starting cash:  ${float(self.starting_cash):.2f}\n"
            f"  Current cash:   ${float(self.cash):.2f}\n"
            f"  Total PnL:      ${float(self.total_pnl):.2f}\n"
            f"  Total value:    ${float(self.cash + self.total_pnl):.2f}\n"
            f"  Trades:         {self.total_trades}\n"
            f"  Wins:           {self.wins}\n"
            f"  Losses:         {self.losses}\n"
            f"  Win rate:       {win_rate:.1f}%\n"
            f"  Open positions: {len(self.positions) - len(self.closed_positions)}\n"
            f"{'='*60}"
        )

    def print_positions(self):
        """Print all positions."""
        for p in self.closed_positions:
            direction = "WIN" if p.pnl > 0 else "LOSS"
            print(f"  {direction} {p.slot_key} {p.predicted_direction} "
                  f"entry=${float(p.entry_price):.4f} "
                  f"exit=${float(p.exit_price):.4f} "
                  f"PnL=${float(p.pnl):+.2f}")
        for p in self.positions:
            if not p.resolved:
                print(f"  PENDING {p.slot_key} {p.predicted_direction} "
                      f"entry=${float(p.entry_price):.4f} "
                      f"{float(p.shares):.2f}sh PENDING")
