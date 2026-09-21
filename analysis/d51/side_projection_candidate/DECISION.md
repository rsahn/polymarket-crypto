# Candidate not adopted

77,477 normalized snapshots exactly equal. Synthetic snapshot isolation, invalidation, reset and rejection test PASS.

Candidate 46.440 s versus reference 46.343 s. Normalization 12.794 s versus 12.315 s. No demonstrated speed benefit, so do not integrate or launch another smoke for this candidate. Backend and source databases unchanged. Technical results and databases retained.

Next target: reduce repeated payload/depth serialization in Store, or decouple durable raw capture from derived normalization with an explicit temporal and crash-recovery contract. Benchmark exact data preservation first; no timestamp changes, frame dropping or forced reconnection.
