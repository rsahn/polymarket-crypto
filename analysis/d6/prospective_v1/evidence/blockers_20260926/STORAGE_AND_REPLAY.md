# Technical storage and replay qualification

**STORAGE_UNQUALIFIED / REPLAY_CAPACITY_UNPROVEN**

Measurement covers the complete immutable 1,320.0542836000677-second capture, without collecting new network data or opening a real economic partition. It is an offline technical conversion and exhaustive replay, not a live ingest throughput certification.

| Measurement | Value |
|---|---:|
| source_db_bytes | 4800663552 |
| bytes_written | 336113918 |
| source_observation_seconds | 1320.0542836000677 |
| encoding_wall_seconds | 633.2449435000308 |
| bytes_per_source_second | 254621.285030299 |
| db_to_archive_ratio | 14.28284666271987 |
| rows | 3973286 |
| frame_hash_and_header_overhead | 447701 |
| replay_seconds | 252.69512189994566 |
| replay_rows_per_second | 15723.635542015798 |
| process_peak_rss_bytes | 79486976 |
| projected_168h_bytes | 153994953187 |
| required_bytes_lower_bound | 369587887649 |
| free_bytes_after_smoke | 47701286912 |
| additional_bytes_lower_bound | 321886600737 |

Logical input and restored row SHA-256: `9b62642be7ae706a09637a8dd27f662e5ce2d0f96cdc259dcf76e711f92f0e30`.

The comparison preserves every typed table value in row order, the original compressed BLOB bytes, timestamps, repeated books and schema DDL. It does not claim byte-identical SQLite page layout or certify a portable cross-zlib re-encoder. Codec/runtime versions are recorded in INSTRUMENTATION_IDENTITY.json. Both complete streams match under the measured runtime.

No destructive sampling, dropped observation, economic aggregation or historical database rewrite occurred. All source information is preserved; missing original entry/fee observations cannot be invented by compression.

Archive framing/footer overhead is measured above. It is not the prospective event journal. journal_allowance=UNPROVEN, checkpoint_allowance=UNPROVEN. The required-space formula remains ceil((2*projected_168h_bytes + journal_allowance + checkpoint_allowance)*1.2).

The archive-only planning shortfall at measurement time is **321,886,600,737 bytes = 321.886600737 GB = 0.321886600737 TB** (decimal units). This is a lower bound, NOT the exact total for a qualified future experiment. Additional audit side files are not silently included in or assumed to equal zero in that total.

The projected workload includes captured 5m and 15m traffic. It is not a measured future 5m-only week. No source/DB/side file was deleted to create free space; archive bytes occupy additional disk.

## Existing journal and state-copy measurement

New synthetic MARK-only journals, no strategy and no real partition. The schema requires a partition label; TRAIN here is a fixture label only. Each append was flushed/fsynced. After replay, every accounting row matched by canonical SHA-256.

| Events | Journal bytes | Median copy ms | Observe ms | Recovery events/s | Adapter replay s | Process peak RSS bytes |
|---:|---:|---:|---:|---:|---:|---:|
| 101 | 54789 | 1.378800 | 2.911200 | 6374.613 | 0.001372 | 22376448 |
| 1001 | 548895 | 10.568700 | 15.140400 | 20586.245 | 0.014657 | 26664960 |
| 5001 | 2768895 | 59.670400 | 61.115800 | 24476.959 | 0.075882 | 45551616 |

State copies were measured at 100/1,000/5,000 existing events, followed by one normal observe; the table's event counts include that final observation. Preparing valid history via append+_apply avoids spending quadratic time only to measure the already identified full-copy cost. Production observe itself is unchanged and separately timed.

Current journal.records, IDs and adapter.accounting retain O(N) history; observe deep-copies the accumulated state. The probe confirms growing per-event cost. Streaming archive replay is bounded by frame/cache budgets, while the economic adapter and journal recovery are still unbounded in history size. The small synthetic recovery PASS is not a weekly replay qualification.

Recovery of a complete archive passed; truncated frames/footer and fsync failure are tested to reject rather than repair. No claim of hardware power-loss certification or crash-resume collector integration is made.
