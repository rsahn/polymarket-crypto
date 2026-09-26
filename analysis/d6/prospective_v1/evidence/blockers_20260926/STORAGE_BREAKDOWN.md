# STORAGE_BREAKDOWN

Source immutable: data\d51\d51_smoke_20260922_194254.db

Physical rows below are additive; bytes include SQLite pages, cells, free space and overflow assigned to each object. Required flags describe retained logical information, not a requirement to retain its SQLite representation. All rows are preserved by the candidate archive.

| SOURCE | BYTES | PERCENT | EVENT_COUNT | BYTES_PER_EVENT | REQUIRED_FOR_REPRODUCIBILITY | REQUIRED_FOR_LEDGER | REQUIRED_FOR_SIGNAL | REQUIRED_FOR_AUDIT |
|---|---:|---:|---:|---:|---|---|---|---|
| sqlite_schema | 12288 | 0.000256% | N/A | N/A | LOGICAL schema retained; physical rebuildable | NO | NO | YES structure |
| schema_info | 4096 | 0.000085% | 1 | 4096.000000 | YES metadata | YES identity | YES identity | YES |
| sessions | 4096 | 0.000085% | 1 | 4096.000000 | YES metadata | YES identity | YES identity | YES |
| sqlite_autoindex_sessions_1 | 4096 | 0.000085% | N/A | N/A | LOGICAL schema retained; physical rebuildable | NO | NO | YES structure |
| markets | 61440 | 0.001280% | 9 | 6826.666667 | YES metadata | YES identity | YES identity | YES |
| sqlite_autoindex_markets_1 | 4096 | 0.000085% | N/A | N/A | LOGICAL schema retained; physical rebuildable | NO | NO | YES structure |
| sqlite_autoindex_markets_2 | 4096 | 0.000085% | N/A | N/A | LOGICAL schema retained; physical rebuildable | NO | NO | YES structure |
| sqlite_autoindex_markets_3 | 4096 | 0.000085% | N/A | N/A | LOGICAL schema retained; physical rebuildable | NO | NO | YES structure |
| events | 2551357440 | 53.145933% | 1336887 | 1908.431633 | YES | YES | YES | YES |
| sqlite_sequence | 4096 | 0.000085% | 2 | 2048.000000 | LOGICAL schema retained; physical rebuildable | NO | NO | YES structure |
| idx_d5_events_session | 75018240 | 1.562664% | N/A | N/A | LOGICAL schema retained; physical rebuildable | NO | NO | YES structure |
| idx_d5_events_market | 56524800 | 1.177437% | N/A | N/A | LOGICAL schema retained; physical rebuildable | NO | NO | YES structure |
| book_sides | 2058412032 | 42.877657% | 2631230 | 782.300305 | YES (derived representation retained) | YES depth | NO | YES |
| sqlite_autoindex_book_sides_1 | 48062464 | 1.001163% | N/A | N/A | LOGICAL schema retained; physical rebuildable | NO | NO | YES structure |
| anchors | 10231808 | 0.213133% | 5156 | 1984.446858 | YES captured features | NO direct V1 dependency | NOT V1 BTC source | YES |
| sqlite_autoindex_anchors_1 | 94208 | 0.001962% | N/A | N/A | LOGICAL schema retained; physical rebuildable | NO | NO | YES structure |
| hedge_attempts | 4096 | 0.000085% | 0 | N/A | LOGICAL schema retained; physical rebuildable | NO | NO | YES structure |
| idx_d5_anchor_lifecycle | 851968 | 0.017747% | N/A | N/A | LOGICAL schema retained; physical rebuildable | NO | NO | YES structure |
| SQLITE_BYTE_LOCK_PAGE | 4096 | 0.000085% | N/A | N/A | LOGICAL schema retained; physical rebuildable | NO | NO | YES structure |
| UNATTRIBUTED | 0 | 0.000000% | N/A | N/A | LOGICAL schema retained; physical rebuildable | NO | NO | YES structure |

Total: **4,800,663,552 bytes**; unattributed pages: **0**.

## Non-additive logical payload measurements

These stored-column bytes are subsets of the physical tables. They must NOT be added to the table totals.

| SOURCE | BYTES | PERCENT OF DB | EVENT_COUNT | BYTES_PER_EVENT | REQUIRED (reproduction / ledger / signal / audit) |
|---|---:|---:|---:|---:|---|
| events ACTIVATE/15m | 1507 | 0.000031% | 4 | 376.750000 | retained / contextual / BTC is signal source / YES |
| events ACTIVATE/5m | 2249 | 0.000047% | 6 | 374.833333 | retained / contextual / BTC is signal source / YES |
| events BOOK/15m | 457791648 | 9.536008% | 433068 | 1057.089529 | retained / contextual / BTC is signal source / YES |
| events BOOK/5m | 938068588 | 19.540394% | 882547 | 1062.910630 | retained / contextual / BTC is signal source / YES |
| events BTC/None | 4409468 | 0.091851% | 19074 | 231.176890 | retained / contextual / BTC is signal source / YES |
| events BTC_CONNECTED/None | 2 | 0.000000% | 1 | 2.000000 | retained / contextual / BTC is signal source / YES |
| events CLOCK_SAMPLE/None | 2640 | 0.000055% | 44 | 60.000000 | retained / contextual / BTC is signal source / YES |
| events COLLECTION_STOP/None | 38 | 0.000001% | 1 | 38.000000 | retained / contextual / BTC is signal source / YES |
| events EXPIRE/15m | 45 | 0.000001% | 2 | 22.500000 | retained / contextual / BTC is signal source / YES |
| events EXPIRE/5m | 110 | 0.000002% | 5 | 22.000000 | retained / contextual / BTC is signal source / YES |
| events RECONNECT/15m | 44 | 0.000001% | 2 | 22.000000 | retained / contextual / BTC is signal source / YES |
| events REJECT/15m | 99124 | 0.002065% | 203 | 488.295567 | retained / contextual / BTC is signal source / YES |
| events REJECT/5m | 1009706 | 0.021033% | 1919 | 526.162585 | retained / contextual / BTC is signal source / YES |
| events ROTATION/None | 699 | 0.000015% | 7 | 99.857143 | retained / contextual / BTC is signal source / YES |
| events SESSION_END/None | 166 | 0.000003% | 1 | 166.000000 | retained / contextual / BTC is signal source / YES |
| events SESSION_END/15m | 22 | 0.000000% | 1 | 22.000000 | retained / contextual / BTC is signal source / YES |
| events SESSION_END/5m | 21 | 0.000000% | 1 | 21.000000 | retained / contextual / BTC is signal source / YES |
| events WS_ERROR/15m | 109 | 0.000002% | 1 | 109.000000 | retained / contextual / BTC is signal source / YES |
| bid depth | 665002341 | 13.852300% | 2631230 | 252.734402 | YES retained / depth if applicable / no BTC source / YES |
| ask depth | 665002343 | 13.852301% | 2631230 | 252.734403 | YES retained / depth if applicable / no BTC source / YES |
| adjacent repeated depth | 220496792 | 4.593048% | 455086 | 484.516755 | YES retained / depth if applicable / no BTC source / YES |
| anchor features | 5780830 | 0.120417% | 5156 | 1121.185027 | YES retained / depth if applicable / no BTC source / YES |

Repeated depth is an exhaustive byte-equality count for consecutive observations per token, not a claim that event clocks or provenance are redundant. No duplicate row was removed.

## Side files outside the 4.8 GB

| SOURCE | BYTES | PERCENT OF DB (outside total) | EVENT_COUNT | BYTES_PER_EVENT | REQUIRED_FOR_REPRODUCIBILITY | REQUIRED_FOR_LEDGER | REQUIRED_FOR_SIGNAL | REQUIRED_FOR_AUDIT |
|---|---:|---:|---|---|---|---|---|
| analysis\d51\smoke_20260922_194254\clock_after_1790100346933927900.json | 9054 | 0.000189% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\clock_during_1790099318792398500.json | 9073 | 0.000189% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\clock_during_1790099623590818000.json | 9075 | 0.000189% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\clock_during_1790099928504760500.json | 9064 | 0.000189% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\clock_during_1790100233243784900.json | 9063 | 0.000189% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\clock_gate_1_1790098979155697100.json | 9061 | 0.000189% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\clock_gate_2_1790099013797897600.json | 9064 | 0.000189% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\COLLECTION_RESULT.json | 980 | 0.000020% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\LAUNCH_MANIFEST.json | 1284 | 0.000027% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\status.json | 4046 | 0.000084% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\review\AUDIT_NEXT_REPORT.json | 9426 | 0.000196% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\review\DATA_QUALITY_REPORT.json | 11062 | 0.000230% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\review\FOREIGN_KEY_CHECK.json | 2 | 0.000000% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\review\INTEGRITY_CHECK.json | 24 | 0.000000% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\review\metadata_projection.db | 1166061568 | 24.289592% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\review\progress.json | 2197 | 0.000046% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\review\progress.jsonl | 2004350 | 0.041752% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\review\REPLAY_1.json | 6509 | 0.000136% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\review\RUN_MANIFEST.json | 2778 | 0.000058% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |
| analysis\d51\smoke_20260922_194254\review\VERDICT.json | 228 | 0.000005% | N/A file | N/A | existing evidence retained | NO direct | NO | YES |

Total side files: 1,168,167,908 bytes.

## Interpretation and boundaries

- Raw BTC wire and raw Polymarket wire are not separate attributable tables in this DB. The measured BTC/BOOK payloads are the stored event representations; calling them complete original network frames would be unproven.
- Books exist both as event payloads and book_sides depth. These are redundant representations, but this candidate preserves both byte-exactly instead of deleting either.
- The measured depth duplicate bytes are a subset of bids/asks, not extra storage.
- SQLite WAL/journal: source admitted only if absent or empty; neither contributes to the measured DB file. Original DB, clocks and side files are untouched.
- JSON/JSONL punctuation overhead is not a standalone DB object. Stored-column lengths above include their serialization. Separating semantic values from punctuation is not required for the lossless decision and no invented byte estimate is used.
- Diagnostics/telemetry include review/progress.jsonl and clock/status reports above. metadata_projection.db alone is 1,166,061,568 bytes, OUTSIDE the 4.8 GB. It is not used or recreated by the archive smoke.
- No prospective journal/checkpoint for a qualified real binding exists in this source capture. Their weekly allowances are UNPROVEN, not zero.
- The archive preserves DDL and every typed SQLite cell, including original compressed BLOB bytes; physical index pages are reconstructible. This proves preservation of captured information, not that missing V1 entry/fee observations existed.
- Original source tables contain both 5m and 15m workload. Weekly projection uses that observed workload and is not presented as measured single-5m storage.
