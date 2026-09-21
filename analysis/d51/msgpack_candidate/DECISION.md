# Binary codec candidate not adopted

5,000 existing technical BOOK payloads, three alternated timing pairs. Median guarded MessagePack+zlib 1.088642 s versus JSON+zlib 0.685110 s. Encoded bytes 6,653,060 versus 5,243,262. Decoded canonical equality and signed-zero/binary64 tests PASS. Rejects nonfinite values and oversized integers explicitly. No production schema, decoder, dependencies or source database changed.

Not adopted: slower and larger on this sample. This does not prove all binary storage architectures inferior; recursive validation and binary-float compression cost are included. No full persistence/audit/replay validation claimed. Installation wheel provenance is in ../msgpack_candidate_install.json.

Next direction: examine separation of synchronous receive/normalize/observe/store work. A candidate must preserve receipt timestamp at ingress, distinct processing/availability times, generation fences, ordered stop/drain, bounded queues with explicit overflow failure, no frame dropping, and deterministic replay. Do not silently move availability backwards or treat queue ingestion as durable storage. Benchmark end-to-end CPU and queue lag before another prospective run.
