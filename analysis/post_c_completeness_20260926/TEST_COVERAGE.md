# Test evidence

RED.log: 25 failures / 19 passed. Includes a genuine regression: legacy same-head witness returned current=true. New diagnostic tests initially fail because the diagnostic module does not exist.
GREEN.log: 44 passed after correction.
GREEN_INTEGRATION.log: 101 passed, covering legacy evaluator, diagnostics, fixed-boundary acquisition, catchup and worker reports.
FULL_SUITE.log: first broader run exposed a typo in the new integration test (runner instead of run); preserved. See FULL_SUITE_FINAL.log for corrected final result.

Requested cases 1-6: new claim tests plus existing fixed-boundary and legacy same-head tests. 7-8: fixed-boundary coverage-gap/hash-change tests and diagnostic no-upgrade cases. 9: scanner removed-log rejection in the existing suite plus diagnostic false. 10-12: existing account pagination/auth/clock failures and diagnostic no-upgrade cases. 13: NOT IMPLEMENTABLE as a positive test with these sources; all asserted-complete/fabricated-watermark inputs remain false. No synthetic fixture is accepted as an authenticated remote completeness proof. 14: 500 and 1300 cannot create proof. 15-17: protected SHA256 checks, runtime harness flags=false, three transport hard locks and zero SDK monetary attempts.

The diagnostic tests are not presented as proof of an implemented positive protocol. Result B deliberately has no positive verification path. No external data stream was replayed and no OOS result was generated.
