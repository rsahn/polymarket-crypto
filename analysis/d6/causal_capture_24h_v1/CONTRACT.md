# CAUSAL_CAPTURE_V1_R2 — observation contract

Technical NO_TRADE capture only. No PAPER entry point, authenticated client, account reader or monetary API is instantiated. The historical runner supplies only five extracted functions; dryrun/staged bindings are None. This module is not integrated into D6 runtime.

## Immutable bindings

The manifest records session UUID, collector version, strategy/runner/collector/protocol/dependency SHA256 and the combined source seal. Source seal is verified again at shutdown. The historical strategy/runner and 24h protocol are pinned by checked_seal. Partition identity is explicitly unassigned technical session: no TRAIN/VALIDATION/OOS is opened, assigned or evaluated. Existing protocol remains 12h/6h/6h, embargo60s, whole-market purge, FIXED25 BTC UP/DOWN5m. The strategy threshold5bps, lookback250ms, cooldown1000ms, latency250ms and hold500ms retain original statements and arithmetic.

OBSERVABILITY_V1_R1 is reused as an observation transform, extended by one EXIT_WAIT hook. This instrument is separately versioned CAUSAL_CAPTURE_V1_R2, with its own transformed AST SHA256 and file hashes. Stripping observations must reproduce the original AST. Differential fixtures compare original extracted functions against instrumented functions for signals, side, fills, skips, capital and sleep arguments. This proves fixture economic equivalence, not equality of wall-clock scheduling or production throughput. Filesystem work can delay execution; actual clocks reveal that delay.

## Canonical journal

Each frame: uint32 big-endian compressed length, SHA256 of canonical JSON, zlib level1 bytes. JSON includes session, strictly increasing sequence, previous-frame digest, bucket, payload. Raw received JSON values (including available fee metadata) are retained once; full depth is not duplicated into each decision. Numeric strings in market messages remain strings. This is semantic JSON preservation, not preservation of original whitespace or wire byte spelling.

RAW includes BINANCE, POLYMARKET, MARKET_METADATA. BOOK_META links a state identity to the RAW sequence, market/slug/token/generation, source/receive clocks, SHA256 of the original normalized V1 view and SHA256 of full normalizer depth. Existing V1 uses top20; all raw levels remain reconstructible. No A/B/C depth policy is chosen.

ACTIVATE_OR_ROTATE controls identify both token IDs, market and expiry; reconnect activation increments generation and resets normalization state. Raw duplicates remain recorded; identical accepted states retain identity, while changed source metadata can create a new identity even with unchanged depth. Foreign-token messages cannot initialize current tokens. Full-book and price_change semantics remain those of the sealed normalizer, including rejected events. RAW plus controls permits independent reconstruction of these facts.

reconstruct_state(path,state_id,before_sequence) streams the validated chain, replays canonical RAW with the same sealed normalizer, verifies depth/view digests and returns full depth plus V1 view. It rejects a state not present before the decision sequence. This works across rotations without retaining all historical books in RAM.

## Per-opportunity records

| Record | Required facts |
| --- | --- |
| SIGNAL | session-derived opportunity_id; signal_source_ts, signal_receive_ts, signal_decision_ts; side and move |
| ENTRY_INTENT | entry_due_ts = recorded start of historical 250ms wait +250ms |
| ENTRY_BOOK | actual_entry_observation_ts; actual_entry_book_state_id; entry_book_source_ts/receive_ts/sequence; market/slug/token; snapshot RAW sequence; full_depth_reference; selected V1 view digest |
| ENTRY_CALC/FILL_LEVEL/ENTRY_RESULT | FIXED25 budget; per-level price, available, taken shares, ENTRY phase; cost, shares, VWAP, unspent budget and entry residual |
| EXIT_WAIT | exit_due_ts = recorded start of historical hold +500ms |
| EXIT_BOOK | analogous actual exit observation, selected state identity and clocks, depth reference and identity |
| EXIT_CALC/FILL_LEVEL/EXIT_RESULT | requested shares; per-level EXIT phase; proceeds, sold shares, VWAP, explicit residual |
| SKIP | original reason (including NO_BOOK/NO_DEPTH/NO_EXIT_BOOK/NO_EXIT_DEPTH/MARKET_ROTATION); retained entry residual when applicable |

Every causal record carries decision time, opportunity ID, MARKET_FEE_UNQUALIFIED and simulated taker/FIXED25 context. Session joins it to all manifest hashes. Book absent means null identity/depth, not a fabricated book; a skipped entry has no exit observation. Entry/exit book sequence is the actual BOOK_META sequence; snapshot_raw_sequence separately identifies the latest envelope. Repeated reads of the same state keep the same identity. Each decision references what the unchanged V1 actually selected, even across a rotation that later causes SKIP.

Raw discovery metadata and raw fee-bearing events are retained. Missing market fee evidence stays missing; no net edge or fee qualification is asserted.

## Clocks and ordering

Source clocks are never substituted for receive clocks. Local receive order is preserved in the bounded ingress queue; journal sequence additionally orders decisions. Receive and decision regressions reject capture. Future source timestamps, including enveloped market events, and future selected-book receive clocks reject capture. Initial, hourly and final public NTP evidence reuses the existing D5.1 gate: two references, three samples each, offset100ms, dispersion50ms, recent W32Time <=3600s. These checks were fixture-tested, not executed against the network in this mission.

## Failure and recovery

Ingress is bounded to1024 items and8MiB; wire item maximum1MiB. Overflow terminates the run, never discards an item while claiming completeness. Journal records cap at8MiB; bucket byte limits are checked before a write. Writes handle short writes; disk/quota/fsync failures poison the journal. Raw/metadata/causal frames are written immediately and fsynced every32 frames, on checkpoints, during a quiet tail and at close. A power loss may leave a non-durable tail: recovery never treats the prefix as a complete24h capture.

Hourly checkpoints contain verified previous sequence/hash, current book references, pending opportunities and capital needed to interpret historical sizing. Recovery is offline scanning, NOT live resumption; resume_live_allowed=false. A process restart requires a new session/file. No old file is reopened for writing and no timestamps are altered. Torn frames, corrupt hash chains and wrong checkpoint links reject recovery.

Feed and strategy-task exceptions are supervised. Shutdown cancels feeds, drains ingress, awaits pending simulations, verifies hashes and obtains final clock evidence. Any failure leaves INCOMPLETE. Even clean duration expiry remains DURATION_REACHED_REQUIRES_ADMISSIBILITY_AUDIT with admissible=false and complete_24h_proven=false. No automatic D5/D6/PAPER readiness transition exists. If a full disk prevents even FINAL_STATUS, the absence of a clean final record is failure, never PASS.

## Disk gate

See evidence/STORAGE_PREFLIGHT.json. Hard quotas: RAW64GiB, BOOK_META16GiB, CAUSAL8GiB, CHECKPOINT256MiB, CONTROL16MiB. Add1GiB recovery scratch and20percent margin, including tiny manifest/status and filesystem overhead:115017882010 bytes. These are frozen engineering ceilings, not extrapolated certainty about future event rate. A quota hit makes the run incomplete. The prior21999279027-byte archive projection is preserved; only new-observation overhead was measured. No duplicate full-depth payload representation or second24h archive is planned.

No capture command is released while storage is blocked. All admissions, empirical depth selection, fee qualification and economic evaluation remain separate. Existing statistical criteria stay unchanged: 24H_STATISTICAL_DESIGN_REQUIRES_SEPARATE_DECISION.
