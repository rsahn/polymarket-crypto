# Narrow expiry-fixture correction and final verification

## Audit BEFORE correction

The 5 ms in test_rpc_assembly.py's market-expiry scenario is a synthetic hypothesis: wall clock NOW+5, advanced +10 by the mocked receipt block-recheck response. It was not derived from a production latency requirement. Runtime component limits are separately bounded (HTTP/RPC approximately 2 s, outer request 5000 ms in this fixture, with effective market expiry shortening that budget). The test incorrectly mixed a frozen injected wall clock with real HTTP monotonic deadlines, RPC/acquire default-captured monotonic functions, real asyncio timer clock and actual thread startup. Thus a real 5 ms execution budget could expire BEFORE the first mock request, producing zero calls instead of the intended two. That is fail-closed runtime behavior, not a runtime safety defect.

No git history/diff was available for this untracked test file (git ls-files/diff produced no entry). Available prior QA reproduced zero calls both isolated and in-suite. Independent cold-thread roundtrip measurement in this pass: first 4.028100 ms, subsequent nine 0.216500–0.295300 ms (raw measurements retained in repo_guarded_results.txt). This measurement is NOT the failing test's elapsed time, not a hard upper bound and does not itself prove a >5 ms delay; it shows startup consumes a substantial fraction before remaining fixture work. The directly evidenced error is mismatched clock domains/host-dependent scheduling, not an invented exact failure latency.

## Minimal test-only correction

Only test_market_expiry_inside_receipt_recheck_stops_deployment changed: wall, HTTP monotonic, captured-default RPC/acquire monotonic and the instance asyncio loop timer now use the same controlled clock. Original +5 ms boundary and explicit +10 ms step retained, no larger constant. Guards remain intact. Parameterized pre-expired case asserts zero HTTP calls; intended crossing asserts exactly receipt and block-recheck, then no deployment RPC and blocked verdict. Runtime files/limits unchanged.

Repeated targeted runs: 5 consecutive runs, each 2 passed (1.50/0.75/0.81/0.88/0.73 s test execution times, NOT component deadline values). Prior mandatory bounded suite: **586 passed in 19.13s**. Broad active repository run separately inventoried and executed with network/subprocess-denied harness plus secret-file read denial; see final results below and repo_test_inventory.json for exact exclusions. No claim that bounded suite is the full repository.

## Runtime/deployment proof status

Previously established D6 economic account versus EOA signer identity is not rescinded or re-proven here. That economic binding is DISTINCT from unproven exchange runtime/source/build applicability. Existing source commit/digests and deployment address manifest inspected. Prior GitHub rate limit/Polygonscan 403 were not retried or evaded. One independent Sourcify full_match metadata lookup for chain137/E111 returned404; this only establishes that requested artifact was unavailable, not universal absence. No authenticated exact per-address runtime/build/immutable artifact was obtained. Existing forge/solc absence remains; no installation/build/config work. No real RPC performed merely to hash unmatched bytecode; no account/receipt/log/financial eth_call needed or invoked. Missing proof remains exact authenticated runtime tied to pinned compiler/settings/libraries/constructor substitutions and canonical deployed-bytecode comparison.

## Prepared operator drill (NOT performed)

Preflight: Windows Python3.13, powershell.exe and icacls.exe available. Existing parent **C:\Users\Ramy\Documents** checked; dedicated **C:\Users\Ramy\Documents\DRILL-NO-MONEY** does not exist. No directory, challenge or receipt created by this preparation. Existing host will enforce TTY and current-user ACL; actual successful directory ACL creation is not claimed.

In actual operator PowerShell, from repository root:

    Set-Location 'C:\Users\Ramy\Documents\polymarket-crypto'
    python -B -m analysis.d6.real_execution_calibration_v1.drill_host --directory 'C:\Users\Ramy\Documents\DRILL-NO-MONEY' init

Human reviews and types CREATE SYNTHETIC DRILL themselves. Then terminal A:

    python -B -m analysis.d6.real_execution_calibration_v1.drill_host --directory 'C:\Users\Ramy\Documents\DRILL-NO-MONEY' host

Independent terminal B, same repository:

    python -B -m analysis.d6.real_execution_calibration_v1.drill_host --directory 'C:\Users\Ramy\Documents\DRILL-NO-MONEY' recover
    python -B -m analysis.d6.real_execution_calibration_v1.drill_host --directory 'C:\Users\Ramy\Documents\DRILL-NO-MONEY' change

Only if the human chooses synthetic custody, run action accept with --challenge <actual current DRILL challenge id> and type its displayed phrase themselves. No placeholder ID or scripted acceptance. Ctrl+C stops only the foreground synthetic host; recover remains read-only. No real exposure/trading action or production authority registration. Parent independent QA precedes operator instruction delivery.

## Broad repository result (NOT green)

Completed with existing network/subprocess-denied harness and extra secret-file guard: **1362 passed, 77 failed, 14 collection errors, 34 warnings, 49 subtests passed in 74.68s**, exit1. Exact output: repo_guarded_results.txt. Exact inventory: repo_test_inventory.json (136 included active first-party files;1290 vendor/immutable historical snapshot test files excluded with full paths). No active first-party test files were silently dropped on failure. Broad execution is not the bounded suite.

Reported failure classes include SUBPROCESS_FORBIDDEN (deliberate guard), SECRET_FILE_READ_DENIED affecting synthetic .env fixtures, Windows file-in-use cleanup, missing local analysis-module imports under importlib mode and assertions outside requested fixture scope. These are reported, NOT repaired or labeled all preexisting/harmless. Full test report lists every failing node. No guard relaxed, no install or unrelated fix.

Only production-adjacent source edit this pass is the expiry test; runtime modules untouched. Evidence runner/report artifacts added within existing scoped evidence. Pre-existing tracked modifications remain unchanged by this patch.
