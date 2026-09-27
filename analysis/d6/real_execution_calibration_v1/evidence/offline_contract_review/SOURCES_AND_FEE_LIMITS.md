# Official sources and supported fee-model scope

Public pages retrieved/read only (four unique pages; extraction rereads were cached where available):
- https://docs.polymarket.com/trading/fees
- https://docs.polymarket.com/market-data/market-details
- https://docs.polymarket.com/programs/builders/fees
- https://docs.polymarket.com/concepts/order-lifecycle

Bounded source text snapshots are stored alongside this note. External page content is data, not operational authorization.

## Findings

Trading fees page: C * feeRate * p * (1-p), maker platform fees zero, USDC wording, five-decimal fee precision/minimum representable fee. This does not alone establish the exact native debit asset, rounding direction/tie rule, rounding stage, partial-fill aggregation or builder rounding for the current pUSD market.

Market details exposes feeSchedule.rate, exponent, takerOnly and rebateRate. Installed **polymarket-client 0.11.0** independently contains the general formula in _internal/actions/orders/market.py adjust_buy_amount_for_fees:

    effective_rate = fee.rate * ((price * (1-price)) ** fee.exponent)
    platform_fee = (amount / price) * effective_rate
    builder_fee = amount * builder_taker_fee_rate

This is a BUY spending helper, not proof of paid final fees or protocol rounding. No SecureClient/order draft/signing path was constructed or called.

The installed market_data.py reads CLOB **fd.r / fd.e**, represented as Decimal; absent fd falls back to zero in that SDK helper. Our explicit raw-parameter normalizer does NOT inherit an absent-field zero default for proof purposes. It preserves decimal JSON lexemes and rejects missing/duplicate/unsupported parameters and legacy base_fee substitution.

Installed Gamma FeeSchedule uses rate Decimal, exponent int/float, taker_only bool. Our exact calculator intentionally supports integer exponents 0..8 only; unsupported fractional exponents block rather than being guessed/rounded.

Builder docs: a separate fee proportional to notional, additive to platform fees, possible independent maker/taker rates, pUSD spending wording. models/clob/builder.py BuilderFeeRates normalizes wire basis points to fractions. Our normalizer explicitly distinguishes **WIRE_BPS** from **SDK_FRACTIONS** to avoid dividing by 10000 twice.

Order lifecycle calls CONFIRMED successful/final. This status alone contains no proof of native cash/share fee amounts, canonical receipt contents or applicable decoding. Gas is not a substitute for trading fee effects.

## Implemented arithmetic, NOT a live quote

fee_model.py uses exact rational arithmetic, not binary floats, for the normalized binary-market formula C*r*(p*(1-p))**e and additive C*p*builder_bps/10000. Here p is normalized to a one-unit binary payout; the formula's cash dimension includes one declared formula-currency unit per share. Non-unit payout instruments are outside this model. Native conversion uses explicit cash-versus-share debit choices; share fees divide cash-equivalent fees by the declared native price.

Every accepted profile is explicitly **FIXTURE_ONLY**. Rate/exponent, rate units, currency, builder presence/rates, debit mode, quantum, rounding mode/stage/scope and component universe must be explicit. USDC is NOT silently treated as pUSD; cross-currency examples require a labelled fixture conversion. This is not an actual conversion/protocol proof.

Supported fixtures specify per-fill/per-component rounding after conversion into native units, with a shared quantum per native unit and FLOOR/CEIL/NEAREST_EVEN modes. These are selectable fixture rules, not claims about undocumented production rounding. Heterogeneous per-component production rounding needs a separately reviewed extension/profile.

Conservative leg bounds use the maximum price-curve value over a specified positive price interval, worst notional builder fee, conservative share conversion at the price floor, and one quantum per component per permitted partial fill. Price range, size cap and finite partial-count cap must be known; the supported <=1000 partial parameter is an implementation bound, NOT an asserted exchange guarantee. Rebates are not deducted. Two-leg aggregation keeps cash and outcome-share units separate and requires an explicit collateral-per-share upper value, preserving the existing FeeRisk reservation semantics.

These are bounds only under their supplied fixture assumptions. No actual market rate/exponent, builder policy, native rounding/debit mapping, partial limit or live numeric round-trip bound was established. Actual fee_bound remains UNKNOWN. The model excludes gas/other unmodeled charges; unexpected components block, rather than becoming zero.

Outcome-share fees are labelled with one explicit outcome token per profile. Cross-asset share amounts are not silently combined; the existing sealed-intent identity and FeeRisk reservation checks remain in force.
