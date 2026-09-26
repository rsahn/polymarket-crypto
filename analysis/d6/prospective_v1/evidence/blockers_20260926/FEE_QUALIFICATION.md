# Fee qualification — only demonstrated fee blocker

**MARKET_FEE_UNQUALIFIED for both tokens. No production fee rule admitted.**

Public unauthenticated GET evidence and retrieval timestamps are in FEE_SOURCE_AUDIT.json. Token-by-token assessment is in FEE_QUALIFICATION.json. This proves only the sampled market 4961058, not every future BTC 5m market.

| Property | Evidence / status |
|---|---|
| Market / condition / two tokens | Gamma and CLOB response identities agree |
| Enabled | Gamma feesEnabled=true |
| Rate / exponent | Gamma feeSchedule and CLOB fd agree: 0.07 / 1 |
| Maker / taker | takerOnly=true; published maker fees zero, independent of maker rebates |
| Curve | quantity × 0.07 × price × (1-price), per official fee documentation for this schedule |
| Unit / display precision | Documentation: USD stablecoin-denominated fee, five decimal places; this alone does not establish a match settlement algorithm |
| Exact tie-breaking | UNPROVEN |
| Per-level / per-match / per-order aggregation | UNPROVEN |
| Partial-fill fee allocation and repeated fills | UNPROVEN |
| Buy/sell settlement denomination and deduction implementation needed by exact cash ledger | Not qualified by the pure spend-provision function |
| Production fee fallback | None. Unknown fee raises MARKET_FEE_UNQUALIFIED |

Sources inspected:
- [Official fees](https://docs.polymarket.com/trading/fees)
- [Official market details](https://docs.polymarket.com/market-data/market-details)
- [Gamma market 4961058](https://gamma-api.polymarket.com/markets/4961058)
- Official installed polymarket SDK files and their SHA-256 values are captured in FEE_SOURCE_AUDIT.json.
- [Official SDK fee-spend adjustment](https://github.com/Polymarket/py-sdk/blob/0e00e28365f57ab8fa7c5a7f3f320e77bb36e356/src/polymarket/_internal/actions/orders/market.py)
- [Official CLOB client fee helper](https://github.com/Polymarket/py-clob-client-v2/blob/main/py_clob_client_v2/fees.py)
- [Exchange V2 Fees.sol](https://github.com/Polymarket/ctf-exchange-v2/blob/ccc0596074f4dfd62c944fbca4de252893b82b4b/src/exchange/mixins/Fees.sol)
- [Exchange V2 Trading.sol](https://github.com/Polymarket/ctf-exchange-v2/blob/ccc0596074f4dfd62c944fbca4de252893b82b4b/src/exchange/mixins/Trading.sol)

The pure installed SDK function was extracted by AST and tested without constructing a client: it adjusts buying power using an unrounded provision. Order/math.py ROUND_HALF_EVEN concerns order amounts. Neither proves the exchange's final fee rounding or aggregation.

The inspected exchange V2 contract validates supplied fee amounts against a maximum; Trading.sol receives takerFeeAmount and makerFeeAmounts. This is not proof of the operator's exact curve-to-amount calculation. Moreover the sampled CLOB response reports v="v1"; no deployment binding from this sampled market to the examined V2 contract was established. The V2 code therefore cannot be used as normative proof for this market.

Concrete ambiguity (diagnostic only, not a proposed production rule): two partial fills of 0.002 shares at 0.5 produce raw fees 0.000035 each. Rounding each to five decimals HALF_EVEN yields total 0.00008; aggregating first yields 0.00007. Rounding down each yields 0.00006 total. All differ. No choice is silently adopted.

No order, signature, cancel, allowance update, transaction, private key, or authenticated monetary call was used to obtain this evidence.
