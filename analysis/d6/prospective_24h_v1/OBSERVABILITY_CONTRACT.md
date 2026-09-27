# Minimum future evidence, not an adopted runner

Status: REAL_V1_BINDING_NOT_QUALIFIED. OBSERVABILITY_V1_R1 is not adopted. No economic or capture runner is enabled in this version.

Each opportunity must link an immutable signal observation, source/receive/available clocks, scheduled entry due, actual entry decision clock and **actual_entry_book_state_id**, actual exit decision clock and **actual_exit_book_state_id**. Book states require market/slug/token/side/generation, local sequence, source event identity, source timestamp, receive timestamp, exact retained bid/ask levels and depth consumed by the existing simulation. Snapshot content hashes alone do not prove a new event or replenishment. Opposite-token updates cannot invent a fresh state for this token.

Record intent, entry/exit decisions, partial/no fills, each simulated fill, residual positions, rotations, errors, session end and qualified fee policy/evidence links. Entry must remain recorded when exit book is absent or a rotation interrupts exit. Never infer actual selection from nominal signal+250 ms or exit+500 ms. Record scheduling and observed execution separately; never retime stored events.

Source availability and local decision binding are separate requirements. A richer historical venue timeline may still fail to reproduce this collector's inter-feed scheduling. Counterfactual depth replenishment remains a policy requiring separate evidence; do not choose A/B/C from PnL or merely from snapshot co-presence.

If a future source audit returns NEW_24H_CAUSAL_CAPTURE_REQUIRED, implement and validate a public NO_TRADE capture of 24h with this contract, no monetary SDK or key, exclusive new output files and bounded storage. Do not launch in this mission. Do not present a command for a runner that has not been qualified.
