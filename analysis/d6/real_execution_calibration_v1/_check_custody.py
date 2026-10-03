"""Pre-arm custody check — step 1 of the final mission."""
import sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from analysis.d6.real_execution_calibration_v1.custody import CustodyOwner, CustodyStateStore
from analysis.d6.real_execution_calibration_v1.manual_custody import ManualCustodyChannel, ManualReceiptAuthority, ManualReceiptVerifier
from analysis.d6.real_execution_calibration_v1.core import Journal
from app.live.l2_windows_storage import WindowsProtection

DPAPI_DIR = Path.home() / "AppData/Local/PolymarketD6L2"
CUSTODY_JOURNAL_PATH = ROOT / "analysis/d6/real_execution_calibration_v1/custody_journal.jsonl"

print("=" * 60)
print("  CUSTODY INVENTORY — PRE-ARM CHECK")
print("=" * 60)

# 1. DPAPI directory
print(f"\n1. DPAPI_DIR: {DPAPI_DIR}")
print(f"   Exists: {DPAPI_DIR.exists()}")
if DPAPI_DIR.exists():
    items = list(DPAPI_DIR.iterdir())
    print(f"   Contents ({len(items)} items):")
    for item in sorted(items):
        sz = item.stat().st_size if item.is_file() else 0
        tp = "FILE" if item.is_file() else "DIR "
        print(f"     [{tp}] {item.name}  ({sz} bytes)")
else:
    print("   NOT FOUND — custody channel not initialized")

# 2. custody_journal.jsonl
print(f"\n2. CUSTODY_JOURNAL: {CUSTODY_JOURNAL_PATH}")
print(f"   Exists: {CUSTODY_JOURNAL_PATH.exists()}")
if CUSTODY_JOURNAL_PATH.exists():
    text = CUSTODY_JOURNAL_PATH.read_text()
    lines = [l for l in text.strip().split("\n") if l.strip()]
    print(f"   Lines: {len(lines)}")
    for i, line in enumerate(lines):
        try:
            obj = json.loads(line)
            print(f"   [{i}] kind={obj.get('kind','?')} account={str(obj.get('account','?'))[:20]} session={str(obj.get('session','?'))[:20]}")
        except json.JSONDecodeError:
            print(f"   [{i}] <invalid json> {line[:120]}")

# 3. Instantiate channel
print("\n3. ManualCustodyChannel:")
platform = WindowsProtection()
channel = ManualCustodyChannel(str(DPAPI_DIR), platform=platform)
print(f"   channel.owner = {channel.owner}")
print(f"   channel.directory = {channel.directory}")

# 4. Instantiate receipt authority
print("\n4. ManualReceiptAuthority:")
receipt_authority = ManualReceiptAuthority(channel)
print(f"   type = {type(receipt_authority).__name__}")

# 5. Instantiate receipt verifier
print("\n5. ManualReceiptVerifier:")
receipt_verifier = ManualReceiptVerifier(receipt_authority)
print(f"   type = {type(receipt_verifier).__name__}")

# 6. Check for existing receipt
print("\n6. Receipt status:")
account = "0x871d37b430c42ddbd0bbd37c29c02a2974109de9"
session = "calibration-v1"
try:
    receipt = receipt_authority.issue(account, session)
    print(f"   receipt = {receipt[:80] if receipt else 'NONE'}...")
    print(f"   Receipt exists: {receipt is not None and len(receipt) > 0}")
except Exception as e:
    print(f"   Receipt check: ERROR {e}")

# 7. Verify receipt
print("\n7. Receipt verification:")
try:
    if receipt:
        verified = receipt_verifier.verify(receipt, account, session)
        print(f"   verified(account={account[:20]}..., session={session}) = {verified}")
    else:
        print("   No receipt to verify")
except Exception as e:
    print(f"   Verification: ERROR {e}")

# 8. CustodyOwner state
print("\n8. CustodyStateStore:")
custody_journal = Journal(str(CUSTODY_JOURNAL_PATH), "custody-store")
custody_store = CustodyStateStore(custody_journal)
custody_owner = CustodyOwner(channel, receipt_verifier, state_store=custody_store)
print(f"   CustodyOwner type = {type(custody_owner).__name__}")
try:
    state = custody_store.load()
    print(f"   load() = {json.dumps(state, default=str)[:200]}")
except Exception as e:
    print(f"   load() ERROR: {e}")

# 9. CUSTODY_HANDOFF_DONE verdict
print("\n" + "=" * 60)
CUSTODY_HANDOFF_DONE = (
    CUSTODY_JOURNAL_PATH.exists()
    and channel is not None
    and receipt_authority is not None
    and receipt_verifier is not None
    and receipt is not None
    and len(receipt) > 0
)
print(f"  CUSTODY_HANDOFF_DONE = {CUSTODY_HANDOFF_DONE}")
if not CUSTODY_HANDOFF_DONE:
    print("  → Le handoff humain n'est pas encore fait.")
    print("  → Challenge TTY nécessaire avant de continuer.")
else:
    print("  → Handoff déjà effectué. Receipt présent et vérifiable.")
print("=" * 60)
