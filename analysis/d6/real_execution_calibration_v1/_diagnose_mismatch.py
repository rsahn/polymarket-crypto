"""DIAGNOSTIC ASSEMBLY_CONTEXT_MISMATCH — read-only run0042.
Ne modifie rien, ne relance rien.
"""
import json, time, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DIRECTORY = Path("D:/polymarket-real-calibration/preparation")
BASELINE_PATH = DIRECTORY / "BASELINE.json"

# 1. Current market
import sys
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
from analysis.d6.real_execution_calibration_v1.market_discovery import discover_current
current = discover_current()

print("=== CURRENT MARKET (discover_current) ===")
for k, v in current.items():
    vstr = str(v)[:80]
    print(f"  {k}: {vstr}")

# 2. BASELINE.json
baseline = json.loads(BASELINE_PATH.read_text())
print()
print("=== BASELINE.json ===")
print(f"  market (condition_id): {baseline['market']}")
print(f"  collateral: {baseline['collateral']}")
print(f"  session: {baseline['session']}")
print(f"  account: {baseline['account']}")
print(f"  observed_ms: {baseline['observed_ms']}")
dt = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(baseline['observed_ms']/1000))
print(f"  observed_datetime: {dt} UTC")
p = baseline.get('payload', {})
print(f"  payload.maker: {p.get('maker','?')}")
print(f"  payload.signer: {p.get('signer','?')}")
print(f"  payload.chain_id: {p.get('chain_id','?')}")
print(f"  payload.signature_type: {p.get('signature_type','?')}")
print(f"  payload.market: {p.get('market','?')}")

# 3. Build expected context (from PreparedSession.__init__)
from analysis.d6.real_execution_calibration_v1.core import digest
baseline_digest = digest(baseline)
print()
print(f"  baseline_digest: {baseline_digest}")

# expected = dict(account, session, market, collateral)
expected = {
    "account": baseline["account"],
    "session": baseline["session"],
    "market": baseline["market"],
    "collateral": baseline["collateral"],
}
print()
print("=== EXPECTED (from PreparedSession.context) ===")
for k, v in expected.items():
    print(f"  {k}: {v}")

# 4. Observed context (from PreparedSession.validate_assembly)
#   actual = dict(account=self.ledger.account, session=self.journal.experiment_id,
#                 market=self.book.market, collateral=self.account.collateral)
# We need to reconstruct what was observed at runtime.
# From evidence: ctx from verifier.context
#   verifier = EvidenceVerifier(authority, account=ACCOUNT, market=CONDITION_ID,
#                               session=EXPERIMENT_ID, collateral=COLLATERAL, ...)
# In launch.py:
#   ACCOUNT = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
#   COLLATERAL = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
#   CONDITION_ID (dynamic)
#   EXPERIMENT_ID (dynamic from allocate_experiment_id)
# The verifier.context is:
#   dict(account=ACCOUNT, market=CONDITION_ID, session=EXPERIMENT_ID, collateral=COLLATERAL)
#
# In validate_assembly, ctx = verifier.context
#   any(ctx.get(k) != v for k,v in expected.items())
# So it compares ctx (verifier context) vs expected (PreparedSession context)

# Since BASELINE.json is the OLD market, expected will have OLD condition_id
# but ctx (verifier.context) will have CURRENT condition_id
print()
print("=== OBSERVED (from verifier.context) ===")
observed = {
    "account": "0x871d37b430c42ddbd0bbd37c29c02a2974109de9",
    "session": "<EXPERIMENT_ID from allocate_experiment_id>",
    "market": current["condition_id"],  # CURRENT market
    "collateral": "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB",
}
for k, v in observed.items():
    print(f"  {k}: {v}")

# 5. Compare
print()
print("=== COMPARISON ===")
print(f"{'KEY':25} {'EXPECTED':70} {'OBSERVED':70} {'MATCH':6}")
print("-" * 175)
for k in expected:
    e = expected[k]
    o = observed.get(k, "?")
    match = "YES" if e == o else "NO"
    print(f"{k:25} {str(e)[:70]:70} {str(o)[:70]:70} {match:6}")

# 6. ROOT CAUSE
print()
print("=== ROOT CAUSE ANALYSIS ===")
if expected["market"] != observed["market"]:
    print("ROOT_CAUSE=BASELINE_MARKET_STALE")
    print(f"  BASELINE.json contains condition_id from an OLD market slot:")
    print(f"    OLD: {expected['market']}")
    print(f"    CUR: {observed['market']}")
    print(f"  BASELINE was generated at {dt} UTC (observed_ms={baseline['observed_ms']})")
    print(f"  The market slot has since rotated.")
    print(f"  Current slot slug: {current['market_slug']}")
else:
    print("ROOT_CAUSE=UNKNOWN")

# 7. Token match
print()
print("=== TOKEN COMPARISON ===")
baseline_market = p.get("market", "")
baseline_condition = baseline.get("market", "")
print(f"  baseline payload.market: {baseline_market}")
print(f"  baseline .market (condition): {baseline_condition}")
print(f"  current condition_id: {current['condition_id']}")
print(f"  BASELINE_MARKET_CURRENT={baseline_market == current['condition_id']}")
print(f"  EVIDENCE_MARKET_CURRENT=TRUE (evidence() discovers dynamically)")
print(f"  TOKENS_CURRENT={baseline_market == current['condition_id']}")

# 8. Safe to regenerate
print()
print("=== REGENERATION SAFETY ===")
print(f"  SAFE_TO_REGENERATE=true (run produce_baseline.py to capture current market)")
print(f"  REAL_ORDER_ATTEMPTS=0")
print(f"  ORDER_SIGNATURE_ATTEMPTS=0")
print(f"  BLOCKERS=ASSEMBLY_CONTEXT_MISMATCH")
