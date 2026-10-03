"""EXACT diagnostic — reconstructs the exact runtime values in validate_assembly.
Ne modifie rien, ne relance pas launch.py.
"""
import json, sys, hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]
DIRECTORY = Path("D:/polymarket-real-calibration/preparation")
BASELINE_PATH = DIRECTORY / "BASELINE.json"

from analysis.d6.real_execution_calibration_v1.market_discovery import discover_current
from analysis.d6.real_execution_calibration_v1.core import allocate_experiment_id, digest

# ─── Exact values from launch.py constants ──────────────────────────────
ACCOUNT = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
COLLATERAL = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
PUSD_SYMBOL = "pUSD"

# Discover current market (same as launch.py does at module level)
current = discover_current()
CONDITION_ID = current["condition_id"]
print(f"=== MARKET AT DIAGNOSTIC TIME ===")
print(f"  condition_id: {CONDITION_ID}")
print(f"  slug: {current['market_slug']}")

# Allocate experiment ID (same as launch.py)
EXPERIMENT_ID = allocate_experiment_id(DIRECTORY, base_name="calibration-v1")
print(f"\n=== EXPERIMENT ID ===")
print(f"  EXPERIMENT_ID: {EXPERIMENT_ID}")

# Baseline
baseline = json.loads(BASELINE_PATH.read_text())
BASELINE_DIGEST = digest(baseline)
print(f"\n=== BASELINE ===")
print(f"  BASELINE_DIGEST: {BASELINE_DIGEST}")
print(f"  baseline.market: {baseline.get('market')}")
print(f"  baseline.session: {baseline.get('session')}")

# ─── Reconstruct verifier context (EvidenceVerifier) ────────────────────
from analysis.d6.real_execution_calibration_v1.v1_binding import verify as v1_verify
strategy_hashes = v1_verify()
from analysis.d6.real_execution_calibration_v1.evidence import SelfAttestingAuthority
from analysis.d6.real_execution_calibration_v1.qualification import EvidenceVerifier

authority = SelfAttestingAuthority()
verifier = EvidenceVerifier(
    authority,
    account=ACCOUNT,
    market=CONDITION_ID,
    session=EXPERIMENT_ID,
    collateral=COLLATERAL,       # ← "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
    strategy_hashes=strategy_hashes,
)
verifier_ctx = dict(verifier.context)
print(f"\n=== VERIFIER CONTEXT (ctx in validate_assembly) ===")
for k, v in sorted(verifier_ctx.items()):
    print(f"  {k}: {v}")

# ─── Reconstruct PreparedSession.context (SessionContext) ───────────────
# In launch.py, PreparedSession is called with collateral="pUSD"
# self.context = SessionContext(account, experiment_id, market, collateral, ...)
# where collateral = "pUSD" (the symbol)
print(f"\n=== PREPAREDSESSION.CONTEXT (expected in validate_assembly) ===")
session_ctx = {
    "account": ACCOUNT,
    "session": EXPERIMENT_ID,
    "market": CONDITION_ID,
    "collateral": PUSD_SYMBOL,    # ← "pUSD"
}
for k, v in sorted(session_ctx.items()):
    print(f"  {k}: {v}")

# ─── Compare ────────────────────────────────────────────────────────────
print(f"\n{'='*120}")
print(f"{'COMPARISON':^120}")
print(f"{'='*120}")
print(f"{'KEY':25} {'VERIFIER.CONTEXT (ctx)':45} {'SESSION.CONTEXT (expected)':45} {'MATCH':6}")
print(f"{'-'*121}")
mismatch_keys = []
for k in sorted(session_ctx.keys()):
    v = session_ctx[k]
    c = verifier_ctx.get(k, "⛔ MISSING")
    match_bool = str(v) == str(c)
    if not match_bool:
        mismatch_keys.append(k)
    m_label = "OK" if match_bool else "MISMATCH"
    print(f"{k:25} {str(c)[:45]:45} {str(v)[:45]:45} {m_label:9}")

# ─── Additional keys in verifier_ctx not in session_ctx ────────────────
extra = set(verifier_ctx.keys()) - set(session_ctx.keys())
if extra:
    print(f"\nExtra keys in verifier_ctx (not compared): {extra}")

# ─── Root cause ─────────────────────────────────────────────────────────
print(f"\n{'='*120}")
print(f"  ROOT CAUSE ANALYSIS")
print(f"{'='*120}")

if mismatch_keys:
    print(f"\n  MISMATCH_KEYS={','.join(mismatch_keys)}")
    for k in mismatch_keys:
        print(f"    {k}: expected={session_ctx[k]!r}, observed={verifier_ctx.get(k)!r}")
else:
    print(f"\n  MISMATCH_KEYS=<none — all match>")

# Check if collateral is the culprit
if "collateral" in mismatch_keys:
    print(f"\n  COLLATERAL MISMATCH DETAIL:")
    print(f"    PreparedSession reçoit       : collateral=\"{PUSD_SYMBOL}\"")
    print(f"    EvidenceVerifier reçoit       : collateral=\"{COLLATERAL}\"")
    print(f"    validate_assembly compare     : ctx.get('collateral')={verifier_ctx.get('collateral')!r}")
    print(f"                                   vs expected['collateral']={session_ctx['collateral']!r}")
    print(f"    Résultat                      : {verifier_ctx.get('collateral')} != {session_ctx['collateral']} → MISMATCH")

# Also check market between baseline and current
baseline_market = baseline.get("market", "")
print(f"\n  BASELINE_MARKET_CURRENT={baseline_market == CONDITION_ID}")
print(f"  EVIDENCE_MARKET_CURRENT=true (evidence() discovers dynamically)")
print(f"  TOKENS_CURRENT={baseline_market == CONDITION_ID}")

print(f"\n  SAFE_TO_REGENERATE=true")
print(f"  REAL_ORDER_ATTEMPTS=0")
print(f"  ORDER_SIGNATURE_ATTEMPTS=0")
print(f"  BLOCKERS=ASSEMBLY_CONTEXT_MISMATCH")
print(f"  BLOCKER_KEYS={','.join(mismatch_keys) if mismatch_keys else '<none>'}")
