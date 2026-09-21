# D5.1 prospective protocol, fixed before smoke

Historical D5 FAIL, its gate, reports and timestamps remain unchanged. This new protocol is not a re-audit under easier historical criteria.

Smoke: NEW database, SHADOW/NO_TRADE500, at least 1200 s useful coverage on all three feeds; request 1320 s to cover startup and rotation. Both 5m and 15m must rotate at least once; multiple 5m rotations expected. Natural reconnects counted, none forced. No orders/fills/inventory. Full integrity/FK/identity/expiry/token/anchor/provenance and two independent NoTrade replays required. All source and derived timestamp fields checked against TEMPORAL_CONTRACT.md.

Gaps: preserve every interval, classify STARTUP_GAP, SHUTDOWN_GAP, TRANSITION_GAP, RECONNECT_GAP, INTERNAL_FEED_GAP, plus overlapping reconnect flag. INTERNAL/RECONNECT >5000 ms fail. Startup/shutdown >10000 ms fail. A transition is admissible only with independently verified old expiry, chronological next market boundary, matching duration and identity, activation/rotation evidence, no premature switch and <=10000 ms. The 10 s boundary budget is declared prospectively for discovery/subscription/initialization; it does not imply continuous coverage. Mark the whole interval unavailable for causal features/trading. Unverified or >10s transition fails. Record per-market and per-feed raw gaps as well as classification; never relabel arbitrary silence as rotation.

Clock: two independent references time.windows.com and time.cloudflare.com; >=3 NTP samples each, full request/response evidence, UTC/local timestamps and monotonic timing, offset, round-trip delay and server dispersion retained. All absolute offsets <=100 ms and server dispersion <=50 ms; packet validity and sane delay required. Two complete successful checks >=30 s apart before collection. W32Time Running, source nonempty, last sync error 0, last successful sync age <=3600 s. Probe before, every 5 min, and after; retain every failure. Missing/failed evidence blocks the quality gate, not raw timestamp rewriting. Fresh synchronization is deliberately required after the stale-sync historical finding. Never infer continuous accuracy between probes.

Stopping: explicit stop-event request produces STOPPED_BY_USER_CLEAN only after tasks shut down, buffers commit and zero open anchors; ordinary duration completion STOPPED. Unexpected task or cleanup error remains FAILED. No relabeling of historical KeyboardInterrupt.

Storage: lossless compressed payloads initially, depth preserved; no sampling/drop to save space. Reserve >=5 GiB; forecast smoke footprint and verify free space before launch. More compact lossless storage can be validated separately before a longer collection.

Criteria must be frozen with code SHA and protocol SHA before each launch. Tests must cover 5m/15m transitions and all failure branches. A 20-minute PASS validates instrumentation only, never statistical D6 sufficiency.
