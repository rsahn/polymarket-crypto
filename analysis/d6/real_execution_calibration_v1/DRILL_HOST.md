# Local no-money DRILL host — human invocation only

No production authority is registered. Uses synthetic account/token/cash and a separate DRILL owner identity. It cannot query an account, submit/cancel/sign or arm. No real challenge or receipt has been created during implementation; temporary fixtures do not establish attendance.

From repository root, in an actual operator terminal, choose a new protected directory ending exactly **DRILL-NO-MONEY**. Do not reuse production custody state. Substitute the same approved directory for <directory> below.

1. Initialize only while present:
   python -B -m analysis.d6.real_execution_calibration_v1.drill_host --directory "<directory>" init
   Enter CREATE SYNTHETIC DRILL only after reading the warning. It produces a synthetic unknown-intent request, not an actual exposure handoff.
2. In terminal A, run bounded-by-human foreground monitoring:
   python -B -m analysis.d6.real_execution_calibration_v1.drill_host --directory "<directory>" host
   No scheduler/service/background launch. Status stays UNACCEPTED until a genuine interactive DRILL acceptance.
3. In independent terminal B:
   python -B -m analysis.d6.real_execution_calibration_v1.drill_host --directory "<directory>" recover
   Explain synthetic exposure, unknown remote ID and future-results responsibility. Stop only terminal A with Ctrl+C; recovery files remain readable. Restart A manually if desired.
4. Change the synthetic revision with action **change**. The old request/receipt must not satisfy the new revision. Do not erase evidence or fabricate a receipt.
5. If the operator chooses to accept this DRILL only, use action **accept --challenge <actual current DRILL challenge id>**. Review and type the exact displayed interactive phrase yourself. Piped input, stale revision and replay writes are rejected. No command or phrase is executed by the assistant on your behalf.
6. Observe DRILL_ACCEPTED_ONLY in A, then change again and verify UNACCEPTED. Record actual response times and verifier outcomes separately. None of this proves real custody or approves trading.

Concurrent state writers use an exclusive DRILL lock; contention fails closed. After an OS kill leaving DRILL-writer.lock, inspect/recover read-only first and confirm no host remains before the operator archives the abandoned fixture directory and starts a new drill. Do not remove a potentially live writer lock blindly. Recovery never automatically resumes a monitor.
