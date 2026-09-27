# Historical source qualification, 2026-09-27

Verdict: **DATA_SOURCE_QUALIFICATION_INCOMPLETE (E)**. No source passes FULL_DEPTH_CAUSAL for BTC V1. No bulk archive, account, paid access or monetary SDK used. Source qualification did not inspect PnL.

| Provider / official | Dataset / classification | Retention and exact dates | Granularity / clocks / order | Depth / completeness | Cost / access |
|---|---|---|---|---|---|
| Binance, official | Public spot aggTrades/trades; TRADES_ONLY | Daily/monthly archives; requested 2026-09-18 08:55:42 UTC returned three aggregate trades through public REST | Trade IDs and trade timestamps; archive spot timestamps since 2025 are microseconds; REST default ms | No Polymarket depth; no original local arrival clocks or inter-feed order | Public, no key for this GET; rate limits |
| Polymarket, official | CLOB prices-history; PRICE_ONLY / INSUFFICIENT_TIMESTAMP_RESOLUTION | Time-range price query documented; exact local dates not probed because schema is already insufficient | Price samples, fidelity in minutes; no depth update sequence | No historical depth in this response | Public data endpoints; no historical-depth SLA identified |
| Polymarket, official | GET book and real-time market feed; UNKNOWN_COMPLETENESS as historical source | Current book and ongoing events; no documented replay endpoint found in inspected pages | Token, book hash, timestamps, snapshots/updates | Current depth available; cannot retrieve original September 18 decision observations through a current snapshot | Public; not a retrospective capture service |
| Polygon / Polymarket data resources, official | On-chain settlement/trade activity; TRADES_ONLY | Chain history, subject to RPC/indexer access | Block/transaction/log order, not original off-chain receive/decision order | Cannot recover unfilled resting liquidity or off-chain cancellations from settlement logs alone | Provider-specific access/cost; no account queried |
| PMXT, nonofficial venue archive | v2 Parquet snapshot/update candidate; UNKNOWN_COMPLETENESS | Hourly objects; published index shows dates, not proof of requested September 18/22 objects | Documented ms source timestamp and timestamp_received, sorted by market/asset/receive; ties and global sequence not qualified | Potential depth; v2 advertises improved coverage/redundancy, not a proven zero-gap guarantee for our tokens | Free CC BY 4.0 archive; bounded requests returned 404/403; no subscription purchased |
| Tardis, independent provider | Crypto tick/L2 archive; UNKNOWN_COMPLETENESS for Polymarket | Inspected exchange coverage did not establish Polymarket or exact required dates | Local timestamp grouping for L2; venue-specific clocks | Useful Binance candidate, not evidence of available Polymarket depth | Subscription/access dependent; no key or purchase; exact quote not established |

Sources consulted in priority order:

- [Polymarket Institute data guide](https://institute.polymarket.com/data): distinguishes market metadata, current pricing, price history and trade activity. It does not supply the missing original decision-book timeline.
- [Official prices and order books](https://docs.polymarket.com/market-data/prices-order-books) and [real-time data](https://docs.polymarket.com/market-data/realtime-data): current-state/API and live feed capability is not historical completeness.
- [Official blockchain data resources](https://docs.polymarket.com/resources/blockchain-data): on-chain analytics scope; insufficiency for original off-chain book selection is our inference.
- [Binance public archive specification](https://github.com/binance/binance-public-data) and [spot REST specification](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md): aggregate trade price/time/ID can support a subsecond price reconstruction. Trade time T does not recreate websocket event E or local receive time, so substitution in the frozen V1 remains unqualified. One-second candles cannot resolve a 250 ms lookback.
- [PMXT v2 schema](https://archive.pmxt.dev/docs/v2-data-overview), [archive index](https://archive.pmxt.dev/Polymarket/v2), [license/index](https://archive.pmxt.dev/Polymarket): primary search-index content was available; direct documentation fetches timed out. Hourly files do not imply one-hour event resolution. Actual object probes are preserved below.
- [Tardis coverage](https://docs.tardis.dev/faq/general), [CSV description](https://docs.tardis.dev/downloadable-csv-files).

## Minimal reconstruction attempt

`EXTERNAL_MINIMAL_REQUESTS.json` records Range requests for PMXT 2026-09-18T09 (local Binance period) and 2026-09-22T19 (local full-depth capture overlap): both HTTP 404. `EXTERNAL_MINIMAL_REQUESTS_2.json` records the documentation example 2026-04-17T12: HTTP 403. These outcomes are access/object failures, not proof that no archive exists anywhere. No authentication bypass was attempted.

Result: **RECONSTRUCTION_BLOCKED_NO_ACCESSIBLE_BOOK_SAMPLE**. Book match, best bid/ask match, depth match, event-order match, timestamp difference and missing-event count are **UNKNOWN**, not zero or PASS. Arbitrary-time entry/exit lookups could not be tested. No provider passed a reconstruction check.

The Binance one-second request returned HTTP 200 and three aggregate trades, preserved verbatim (365-byte response). This proves minimal historical availability at the exact date, not a complete 24h download or original local signal timing.

A/B/C are therefore unsupported. D would prematurely assert that external recovery is exhausted; E accurately records the missing accessible Polymarket sample and unknown completeness. Further qualification needs an accessible small book interval for the specific tokens/dates, then source/receive-order and depth comparisons. No new capture command is supplied under E.
