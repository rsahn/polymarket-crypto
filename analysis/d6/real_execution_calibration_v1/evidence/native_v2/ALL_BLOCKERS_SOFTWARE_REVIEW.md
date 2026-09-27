# Active-repository validation repair — software stage

## Prior failure classification and concrete fixes

- L2 fixture returned None because blanket SUBPROCESS_FORBIDDEN prevented its actual read-only ACL verification. No weakening of load_existing, permissions or DPAPI validation. The narrowly permitted fixture ACL command now executes and the original assertion passes.
- Paper-runtime clock_guard AttributeError and 14 collection ModuleNotFoundErrors were import-root/module-name collisions in the broad one-process importlib harness, not evidence of missing runtime guard logic. Each active test directory now runs in a clean guarded interpreter with its local import root plus repository/backend/test support roots. No strategy V1 source or fingerprint edited.
- Store initialization could leak an open SQLite connection when provenance lookup raised after connection creation. Store.__init__ now closes and rethrows every initialization exception; no swallowed failure, no successful fallback. Regression injects provenance failure and immediately unlinks the DB on Windows.
- Synthetic .env files are allowed ONLY within the newly created per-child fixture root with existing symlink/junction chain checks; actual repository/home secret files remain denied. This distinguishes fixture names from production secrets rather than dropping the protection.

## Protected readonly_book_stream hash migration

The historical BASELINE.json is UNCHANGED. Original SHA256 remains 813005e2221209c97728e68a4ca8c47f7a863286c87f2eee0231cca6ccdd0441. Current pre-existing source is c116359e8e498752c4350956b60bd77c5c0bc454dd4dd75209cebfd996d7924c.

Audit found exactly FOUR additive lines after successful token update: assign this event's received_ms and derive per-token book_state_id from condition/generation/token/event/source/receipt context. They do not alter branches, synchronization, market identity validation, risk/ready/arm/submit flags, genesis, BTC or strategy rules. They preserve causal provenance needed by already-reviewed readers; deleting them just to match an old hash would remove that evidence.

backend/tests/protected_book_migration.py is an explicit test provenance migration, not a new runtime safety exception. It accepts historical bytes OR only the exact current hash AND exact insertion location/content; removing that exact delta must reconstruct the original protected bytes and original historical hash. ALL other protected files remain exact original hashes. Added tests reject mutations to controls/metadata/bytes/path/hash. Thus no arbitrary new hash is blessed and original safety content remains byte-identical. Parent independent QA must review this migration before acceptance; no production file modified here.

## Audited offline suite mechanism

tests/offline_suite.py inventories all active first-party test*.py, excludes vendor/immutable historical snapshots/archive with exact paths, and executes each directory in a separate child. Child guards install BEFORE pytest/application imports. Environment is scrubbed to OS/interpreter essentials; no signer/API keys inherited. Pytest plugin autoload disabled, bytecode/cache writes disabled, fresh per-child temp root; original temp directory cleanup is retained.

Network connect/bind/DNS/sendto remains denied, except scoped stdlib Windows loop self-pipe socketpair. os.system/shell/string subprocess commands denied. Exact allowed external commands:
1. git rev-parse HEAD with repository cwd (read-only provenance, no arbitrary git verbs);
2. TWO audited PowerShell ACL-query scripts, exact text, NoProfile/NonInteractive, JSON stdin restricted to nonlinked paths under that child's new fixture root. No credential content or production paths;
3. exact existing calibration crash fixture or exact prospective journal-crash code, rerouted through this guarded bootstrap BEFORE importing application code, fixture output path confined, environment scrubbed, no arbitrary -c.
All other child launches fail. Parent orchestrator executes only its own known guarded bootstrap for inventoried groups, does not import application/test code. Real credential file reads outside controlled fixtures stay denied. Adversarial tests exercise network, arbitrary code/shell, nonfixture ACL, secret file, environment scrub and linked-path rejection.

## Stage boundary

No account/RPC/live calls, secrets, order/cancel/signing/funding/arming, global config/scheduler/install/payment/push. Existing user edits retained. Prior D6 economic identity remains established separately from still-unproven deployed runtime/source/build evidence. Actual artifact/independent provenance trust and human drill remain external evidence/action gaps; this stage does not fake them or launch unattended monitors.

Initial targeted isolated groups: paper_runtime22, pipeline4, prospective_v1 117 (+40 subtests), backend752 (+8 subtests) passed. Separate migration/cleanup focused tests30 passed. Complete active run recorded below when complete; no omitted failures called green.

The initial all-active run exposed the copied historical depth-cache fixture invoking exact git rev-parse HEAD from its newly created temp source tree. The allowlist now admits that SAME read-only command only at repository root or a nonlinked path inside the controlled fixture root; no new executable/verb. Actual executable paths are resolved/pinned before application imports (Git installation and Windows System32 PowerShell), not searched in the child working directory. Parent traversal and symlink/junction escape are rejected. An initially malformed JSON string in the adversarial ACL test was corrected to json.dumps(repository path), preserving the intended nonfixture-path rejection. Complete suite rerun follows these corrections.

Final bootstrap hardening additionally rejects executable overrides and alternate OS spawn/exec/startfile primitives. The existing calibration crash fixture is pinned to SHA256 89ef1de7151ea143a9ae69e15655f48bbe26b26788aca8a4801669bba6b8d411 before launch AND at child entry; its code was inspected. The prospective crash program must equal the exact audited constant and is compiled only after child guards. Child inventory is computed once, not repeatedly per file; allowed file set and directory scope are unchanged.

First complete green active run: all18 groups exit0,1530 tests passed plus98 subtests, three deprecation warnings only. Final all-active rerun after the final harness guards completed exit0; final active_group reports supersede intermediate runs.

## Final result

**1530 passed, 98 subtests passed, 0 failed, 0 collection errors; all18 groups exit0.** Three existing DuckDB deprecation warnings only. Inventory:139 active first-party test files included;1290 vendor/historical snapshot/archive test files explicitly excluded, no active tests excluded. Reproduction: python -B tests/offline_suite.py. Exact evidence: active_suite_inventory.json, active_suite_results.json, active_group_0.txt through active_group_17.txt. Counts re-parsed from final reports, not estimated. All protected artifacts rechecked after execution using the explicit metadata-only migration; historical baseline flags all false. Whitespace check no error, LF/CRLF warnings only.

Software/test repair stage is complete, pending parent independent QA of guard implementation and explicit hash migration. CALIBRATION remains BLOCKED by real authenticated runtime/build/deployment provenance, actual independently qualified production observations/trust pins and actual human drill/acceptance. No live proof or human action manufactured. Existing prepared DRILL path remains unused (parent C:\Users\Ramy\Documents exists, DRILL-NO-MONEY absent on recheck); commands remain in TIMING_FIX_FINAL_REVIEW.md/DRILL_HOST.md. No background monitor launched.

## Evidence stage update — 2026-09-27 16:53Z

Artifact absence is SUPERSEDED: Sourcify v2 returned verified compilation/runtime/deployment records for BOTH documented Polygon exchanges, E111180000d2663C0091e4f400237545B87B996B and e2222d279d744050d28e00520010520000310F59. Five public GET requests: one all-fields response incomplete at provider byte cap (not used as complete evidence), two bounded compilation/deployment/runtime responses and two complete sources responses. No GitHub rate-limit or Polygonscan403 retry/evasion. Web search unavailable; no request from it.

Compiler **solc0.8.34+commit.80d5c536**, optimizer enabled1,000,000 runs, viaIR false, EVM prague, metadata IPFS+CBOR. CTFExchange build; no linked runtime libraries,14 immutable IDs per address and explicit address-specific values/offsets. Both source sets identical; ITrading.sol, Trading.sol, Events.sol, Structs.sol byte hashes exactly equal existing pinned commit-derived files. Full repository/dependency tree equivalence to commit ccc0596074f4dfd62c944fbca4de252893b82b4b is NOT established by four-file matches.

Local application of the provider's immutable AND CBOR transformations to recompiled bytes reproduces its recorded onchain runtime exactly (21,037 bytes each). SHA256 E111=3e2ba43e59d19191f0d208e39b1ec16f920bdda30ebfa062330ea9fe8d8363f5; E222=49d7bc11d8ff890bb850d358f6dc36dd3ca63eac5f0cd6811b6033a2938f1646. These are integrity identifiers, not self-created trust. Sourcify reports runtimeMatch/creationMatch=match, NOT an invented exact_match; CBOR replacement is explicit. No local compiler run. Deployment metadata reports blocks84902353/85058176 (transactions retained in artifact JSON), verified April6/7 respectively. This third-party historical verification is not a fresh independently canonical observation or blanket production qualification.

Existing public endpoint https://polygon.drpc.org was called ONCE: eth_chainId([]) returned HTTP403. STOPPED immediately, no retries/alternate routing. Thus **0 completed chain observations,0 eth_getCode,0 block-header reads**. No receipt/log/financial eth_call or monetary methods. Exact failure in deployment_readonly_observation.json.

Available artifacts: sourcify_E111_artifact.json, sourcify_E222_artifact.json, sourcify_E111_sources.json, sourcify_E222_sources.json; sanitized conclusions in artifact_evidence_summary.json. No runtime/software tests/modules/config/pins changed. Remaining decisions: independently approve artifact provenance/source-tree binding (or supply corresponding authenticated full-build provenance); authorize an accessible independent Polygon RPC provider. Proposed budget:5 calls total—eth_chainId1, eth_getBlockByNumber(finalized,false)1, eth_getCode for exactly the two addresses at that returned number2, eth_getBlockByNumber(same number,false)1 for hash recheck. No transaction calls. Do not install compiler unless reviewer explicitly requires a local reproduction; if so exact tool needed is solc0.8.34 with captured settings/dependencies, separately authorized. D6 economic account identity remains unchanged and distinct.

### FINAL human-only drill handoff (CLI inspected, not executed)

Existing parent C:\Users\Ramy\Documents verified; child DRILL-NO-MONEY absent. In an actual PowerShell terminal A:

    Set-Location 'C:\Users\Ramy\Documents\polymarket-crypto'
    $D='C:\Users\Ramy\Documents\DRILL-NO-MONEY'
    python -B -m analysis.d6.real_execution_calibration_v1.drill_host --directory $D init

Human reviews and personally types CREATE SYNTHETIC DRILL. Then foreground, same terminal A:

    python -B -m analysis.d6.real_execution_calibration_v1.drill_host --directory $D host

Independent actual terminal B:

    Set-Location 'C:\Users\Ramy\Documents\polymarket-crypto'
    $D='C:\Users\Ramy\Documents\DRILL-NO-MONEY'
    python -B -m analysis.d6.real_execution_calibration_v1.drill_host --directory $D recover
    python -B -m analysis.d6.real_execution_calibration_v1.drill_host --directory $D change
    $C=Read-Host 'Copy challenge_id from the CURRENT change output'
    python -B -m analysis.d6.real_execution_calibration_v1.drill_host --directory $D accept --challenge $C

Review the printed synthetic exposure/unknown intent and personally type the exact acceptance phrase; challenge deadline10min. No agent typing, piping or fake receipt. Terminal A should show DRILL_ACCEPTED_ONLY. In B run change again and verify A returns UNACCEPTED. Stop A with Ctrl+C; recover in B remains read-only. A collision/crash lock is a fail-closed stop: do not remove it blindly. Attendance/acceptance is a human prerequisite, not a code defect or approval for trading.
