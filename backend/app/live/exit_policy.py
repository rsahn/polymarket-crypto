"""BTC V1 exit: consume current bids after the existing hold; never invent a fill.
The slippage cap is an explicit execution constraint, not a signal change.
"""
from decimal import Decimal, ROUND_CEILING
from .production_readonly import number,fresh


def plan_exit(book,*,token_id,market_slug,confirmed_shares,requested_shares,tick_size,max_slippage_bps,now_ms):
    rejected=dict(state="EXIT_REQUIRED",can_close=False,quantity="0")
    try:
        held,requested,tick,slip=map(number,(confirmed_shares,requested_shares,tick_size,max_slippage_bps))
        if not 0<requested<=held or not 0<tick<1 or not 0<=slip<=100:raise ValueError("EXIT_LIMITS")
        if book.get("available") is not True or book.get("connected") is not True or book.get("book_synced") is not True:
            raise ValueError("BOOK_UNAVAILABLE")
        if book.get("market_slug")!=market_slug or not fresh(book["observed_ms"],now_ms):raise ValueError("BOOK_IDENTITY_OR_AGE")
        side=book["books"][token_id]
        if not fresh(side["observed_ms"],now_ms):raise ValueError("STALE_SIDE")
        bids=side["bids"]
        if not bids:raise ValueError("NO_LIQUIDITY")
        best=number(bids[0][0]);floor=(best*(1-slip/10000)/tick).to_integral_value(rounding=ROUND_CEILING)*tick
        quantity=Decimal(0);proceeds=Decimal(0);last=Decimal(1)
        for price,size in bids:
            price,size=number(price),number(size)
            if not 0<price<1 or size<=0 or price>last:raise ValueError("INVALID_BIDS")
            last=price
            if price<floor:break
            take=min(size,requested-quantity);quantity+=take;proceeds+=take*price
            if quantity==requested:break
        if quantity==0:raise ValueError("NO_LIQUIDITY_WITHIN_SLIPPAGE")
        return dict(state="EXIT_PLANNED",can_close=False,quantity=str(quantity),limit_price=str(floor),
            expected_vwap=str(proceeds/quantity),remaining_shares=str(held-quantity),max_slippage_bps=str(slip),
            observed_ms=book["observed_ms"],generation=book["generation"])
    except (KeyError,TypeError,ValueError,ArithmeticError):return rejected
