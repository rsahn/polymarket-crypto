# Final historical source qualification

Decision: **NEW_24H_CAUSAL_CAPTURE_REQUIRED**. Historical research is closed for this qualification. No further provider loop is proposed. This means available evidence does not qualify a causal24h source; it does not mean all historical depth products are impossible or every archive row lacks depth.

## Targeted sources

Official Polymarket documentation exposes current books and price history, and separately describes blockchain data. Neither reviewed interface establishes a retrospective full resting-book receive timeline with subsecond observable states. On-chain trades cannot reconstruct unexecuted resting depth. No qualifying official historical full-book archive was identified in the targeted review. Sources: [market data](https://docs.polymarket.com/market-data/prices-order-books), [blockchain data](https://docs.polymarket.com/resources/blockchain-data).

PMXT v2 documentation gives hourly UTC Parquet objects, starting April13T19, with public HTTPS rather than a credential requirement. The documented direct pattern is r2v2.pmxt.dev/polymarket_orderbook_YYYY-MM-DDTHH.parquet. Columns include receive/source millisecond times, market/token IDs, event type, JSON bid/ask arrays and price/size/fee fields. Documented sorting is market/asset/receive time; no explicit sequence column resolves receive-time ties. The catalog supplies actual dates, including September09T17. That exact direct object returned403; the archive-site path failed TLS. No restriction was bypassed. The public SDK repository did not provide a verified archive-export ordering contract. Older404 guesses were not used as the final conclusion. Sources: [v2 overview](https://archive.pmxt.dev/docs/v2-data-overview), [v2 catalog](https://archive.pmxt.dev/Polymarket/v2), [public code](https://github.com/pmxt-dev/pmxt). Request outcomes are preserved in evidence/PMXT_ACCESS.json and PMXT_INDEXED_OBJECT_PROBES.json.

A relevant Pendulum mirror advertises unchanged PMXT v2 files covering April13–August09. Its linked August09T23 object was publicly accessible via validated HTTP206 ranges. It provides a useful schema/reconstruction sample but no overlap with the local September full-depth captures. This mirror was the final bounded fallback, not the start of a provider search. Sources: [format/catalog description](https://archive.pendulumflow.com/formats/v2), [sample object](https://archive.pendulumflow.com/pmxt/v2/polymarket_orderbook_2026-08-09T23.parquet).

## Bounded sample and timeline

YES, sample obtained:4096 rows,6650397 transferred bytes, within32MiB cap. Full remote object507501824 bytes was NOT downloaded. Range locations and individual response hashes are retained. Semantic sample SHA256:c98d255e994d10f26ad41fc9cb427361042498d5d68b1ff5c5d2715b0b246605. Raw rows are in HISTORICAL_SAMPLE.json.zlib; exact16-column schema and measured metrics are in HISTORICAL_BOOK_RECONSTRUCTION_TEST.json.

Schema: timestamp_received and timestamp (UTC millisecond); market(binary66); event_type and asset_id strings; bids/asks JSON strings; price decimal(9,4); size decimal(18,6); side; best_bid/best_ask decimal(9,4); fee_rate_bps uint16; transaction_hash; old_tick_size/new_tick_size decimal(9,4).

The sample spans9 market/token pairs with1754 same-token receive timestamp ties and0 full-book anchors. HISTORICAL_TIMELINE.json reconstructs per-token event timelines and tests the first/last observable boundaries: state_at(T) is UNANCHORED. Changes cannot establish preexisting depth; receive ties lack a verified source tie-breaker. File row order alone is not asserted to equal collector event order. No interpolation, invented initial snapshot or price-history fill is used. The market/token IDs exist, but a verified BTC5m outcome mapping for this sample and decision-local clock correspondence are not established.

Depth available in this sample: **NO** as an anchored reconstructible full book. Vendor schema can carry depth: **YES**. These statements are distinct. events_source=4096. events_local, matched_events, missing_source_events, missing_local_events, best_bid_match, best_ask_match, depth_match, timestamp_delta_ms, ordering_match, token_match and market_match are **null / unmeasurable**, not zero or PASS, because no local overlap exists. No PnL or strategy was invoked for the historical sample.

The accessible sample does not prove state_at(T), original observability at entry/exit, or24h completeness. Direct PMXT access limitations remain documented, but access is not the only issue: accessible mirror evidence itself does not qualify. Therefore the final source decision is new causal capture, not an indefinite access-only state.

The sample tool initially lacked PyArrow in system/venv; the existing analysis/d6/vendor runtime then read the bounded sample successfully. No new package, credential or24h dataset download was required.
