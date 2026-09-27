# Next safe measurement and human-drill procedures

No account query, RPC, order, signature, approval, funding, arming, human challenge or acceptance receipt was produced by this review. These are procedures, not completed qualifications.

## Fine clock — keep the 100 ms threshold

The earlier **1160 ms** uncertainty came from the integer-second time response's resolution plus request duration. It is **not measured oscillator drift**. A small displayed offset is not evidence of a small error bound.

Available local tool inspected, without configuration changes or resynchronization: **w32tm /query /status /verbose**. It reported stratum 5, time.windows.com, no warning, root delay **61.1765 ms**, root dispersion **22.9009 ms**, phase offset **-0.2032 ms**, last-sync age **5.1631821 s**, and nominal precision **119.209 ns/tick**. Root dispersion + half root delay is a **53.48915 ms term**, not a complete certified uncertainty. Nominal tick precision is NOT UTC accuracy, and phase correction is NOT drift. The Windows clock was not declared qualified.

Next procedure, with bounded captures and no trading:

1. Explicitly define the required reference: local UTC accuracy or exchange-relative clock offset. Do not silently substitute one for the other.
2. Inspect existing Windows Time synchronization metadata read-only: source, warning/leap state, stratum, successful-sync age, root delay/dispersion and applicable documented error/drift limits. Do not start/resync/reconfigure a service to manufacture a pass. If source trust or metric semantics cannot support an error bound, remain UNKNOWN.
3. For local timestamping, bracket **GetSystemTimePreciseAsFileTime** reads with **QueryPerformanceCounter** (both are available Windows APIs), record the actual read interval and counter frequency. Resolution alone is not an accuracy certificate. Bound mapping error and detect UTC steps against monotonic elapsed time; discard spans crossing a step or an unbounded slew.
4. A candidate local UTC bound needs justified source/root-distance error, residual phase error where applicable, sample-age/drift allowance and read/mapping error. Do not assume a ppm value or count the same dispersion term twice; first verify Windows/provider semantics.
5. Exchange-relative qualification additionally needs a timestamp with a documented generation point and quantified source accuracy/quantization, known to be generated within the request rather than cached. Existing integer-second /time cannot establish a 100 ms bound. A millisecond websocket event field is not automatically a clock probe: event age, buffering and generation semantics must be bounded. Do not invent a precision query parameter or endpoint.
6. For a legitimate within-request server timestamp interval [S_low,S_high] and local request [t0,t1], the offset interval is **[S_low-t1-error, S_high-t0+error]**. No symmetric-network assumption is required. clock_bounds.py computes this arithmetic only for explicit supported quantization/source contracts; it never emits a clock qualification. Keep the existing worst-error <=100 ms gate unchanged.
7. Multiple samples may only be combined with justified drift/step bounds and mutually consistent intervals. Do not select an attractive low-RTT or small-offset sample while discarding contradictions. Until this evidence exists, the fine-clock gate remains UNKNOWN.

## Actual operator, no-money drill

Existing interfaces are described in MANUAL_CUSTODY.md and implemented in manual_custody.py. This pass did not invoke their challenge/acceptance paths. An isolated reviewed DRILL host composition is still needed; do not repurpose an armed/live launcher.

1. The actual designated operator and reviewer agree on a separate **DRILL-only** session and already approved protected storage location. Use a synthetic journal/exposure, explicit unknown local intent, and no live SDK client or network writer. Verify both real flags remain false. Never use a live exposure packet as a fictional drill.
2. The operator opens an independent terminal under their own Windows identity. The existing watch command is:

   python -B -m analysis.d6.real_execution_calibration_v1.manual_custody --directory "<approved protected DRILL directory>" --watch

   Watching is not acceptance or readiness. Do not run it here on the operator's behalf.
3. The reviewed DRILL host creates a fresh DRILL request only when the operator is present. The operator reads account D6 versus signer EOA, session, complete positions/cash units, unknown intent IDs, possible future results, exposure revision/digest, checkpoint and deadline. The operator explains what is unknown and why an empty API view cannot establish flatness.
4. Stop only the synthetic DRILL host, never an actual trading/account worker. The operator demonstrates independent recovery access to the journal and custody files. Recovery must remain MANUAL_RECOVERY_ONLY and must not replay/retry unknown order outcomes. No trade, cancel, transfer, approve or signing action is part of this drill.
5. If the operator genuinely accepts the DRILL responsibility, the existing interactive command is:

   python -B -m analysis.d6.real_execution_calibration_v1.manual_custody --directory "<same DRILL directory>" --accept <actual active DRILL challenge id>

   The HUMAN must review and enter the actual displayed phrase. Never pipe it, simulate their keystrokes, create a receipt file manually, reuse a fixture receipt, or generate a fake acceptance. No challenge id or receipt is supplied in this document.
6. Demonstrate rejection of expired/changed requests, changed exposure and omitted future-result intents; a new state requires a new genuine request/acceptance. Record observed response time and actual verifier results, not an assistant-authored success assertion.
7. Inventory other possible order producers with the operator without collecting their secrets or modifying them. A declaration is not proof that undisclosed keys/apps cannot act. The bounded contract explicitly retains that limitation and requires observed-window coverage; gaps/foreign activity keep custody and new entries blocked.
8. A successful DRILL is only evidence of that drill. Any later actual exposure needs actual attendance, its own correctly bound human acceptance and separate launch review. No current or future receipt has been generated by this preparation.
