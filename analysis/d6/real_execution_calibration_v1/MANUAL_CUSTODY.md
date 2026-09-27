# Manual custody — requesting owner only

Current consent designates the requesting owner. It is NOT an acceptance of any future exposure, proof of availability, or permission to trade. No real challenge/receipt was created during implementation.

## Before any separate live-launch decision

1. The owner chooses a durable local directory outside the bot's lifecycle (D: is the future live session's existing storage requirement). ManualCustodyChannel creates a Windows CurrentUser-only directory and validates ACLs; no new credential is generated. The operator must be the requesting owner using that Windows identity. Trust is the owner's OS/filesystem security domain, not cryptographic nonrepudiation against another process with the same Windows identity.
2. Owner and reviewer perform a clearly labelled DRILL, with a separate DRILL experiment id and no real orders. The owner must show they can inspect the complete exposure, unknown local intents, future-result responsibility, and the recovery files after the bot process is stopped. A fixture test does not replace this operator drill.
3. Keep an operator-owned terminal open independently of the bot. From the repository root, the operator can run:

   python -B -m analysis.d6.real_execution_calibration_v1.manual_custody --directory "<chosen protected custody directory>" --watch

   This watches only; it does not accept anything or send messages externally. Running it is not automatically attested as readiness. The separate launch review must establish attendance and a workable response time. No notifications/destination or always-on service have been assumed.
4. The future composition uses ManualCustodyChannel, ManualReceiptAuthority, ManualReceiptVerifier and CustodyOwner with the existing separate durable CustodyStateStore. Use an ACL-verification timeout appropriate for the local machine (e.g. owner timeout 35 s (two ACL subprocesses are each bounded at 15 s)); this is not a new execution timeout/retry policy. No unattended start/arming wrapper has been added.

## Acceptance of a specific actual exposure, later

The bot writes an immutable challenge containing account/session, the full captured exposure and ALL local intents (including unknown remote order IDs), exact exposure digest/revision, the original journal checkpoint, a public random nonce and acceptance deadline. Monitor-only journal changes keep this same challenge; any exposure change creates a new challenge. The active pointer identifies the latest request. An expired unaccepted request is refreshed with a new public request nonce and the current checkpoint, not auto-accepted.

The HUMAN, not the assistant, runs in another interactive terminal:

   python -B -m analysis.d6.real_execution_calibration_v1.manual_custody --directory "<same directory>" --accept <active challenge id>

The command shows the full document and requires the exact displayed phrase containing experiment, exposure digest and nonce. Review unknowns and ALL future results/corrections before accepting. It refuses piped stdin, mismatched/changed/expired challenge, and an existing receipt. It never creates/cancels/signs an order.

The receipt is fsynced separately. Verification is idempotent for this exact request so a failed local state-store write does not consume the human acceptance; the durable custody state prevents a second transfer or automatic resume. ACL work remains owned even if its waiting task is cancelled. The verifier checks the private-file ACLs, current Windows identity, exact challenge/content, state binding and coverage of every intent. CustodyOwner still rechecks actual exposure immediately before transition. A human's acceptance remains a durable responsibility for that specific state/future-results scope; it is not invalidated just because five seconds pass. A changed state still requires a new acceptance. The bot retains monitoring and cannot call the handoff successful while these checks fail.

## Independent recovery

Keep challenge/receipt files, the live session's journal, and separate custody-state journal. Read them without starting the bot. CalibrationLedger.recover verifies journal/hash/shadow chains and is MANUAL_RECOVERY_ONLY: it never rearms. Unknown POST results are NOT permission to retry an order. Compare the listed account/intents with independently accessed account/trade/position information; incomplete API scope is not proof of flatness. Any later manual trading decision is outside this preparation authorization.

A receipt is acceptance of responsibility, not a magic account monitor. If the bot dies before transfer, the documented owner must use this packet and their account access. If operator access/attendance/recovery has not been demonstrated, live remains BLOCKED. Do not delete receipts to revoke responsibility; arrange an explicit subsequent handoff instead. Old/changed requests do not override the newest exposure. No automatic receipt, proactive external message, or acknowledgement on the owner's behalf is permitted.
