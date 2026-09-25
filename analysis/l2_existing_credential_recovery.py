"""Preview-only L2_EXISTING_CREDENTIAL_RECOVERY. Execution is NOT implemented.
Reads one explicitly configured PUBLIC signer address, never .env or a private key.
"""
import argparse
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from app.live.l2_recovery_preparation import Plan,preview


def main(argv=None):
    parser=argparse.ArgumentParser(description="Offline preview only; no recovery execution available")
    parser.add_argument("--preview",action="store_true",required=True)
    parser.parse_args(argv)
    signer=os.environ.get("L2_RECOVERY_EXPECTED_SIGNER")
    # Only public preview fields are ever emitted. No generic exception logging.
    print(json.dumps(preview(signer),indent=2))
    try:Plan(signer)
    except ValueError:return 2
    if any(os.environ.get(n,"false").strip().lower()!="false" for n in ("REAL_ORDERS_ENABLED","LIVE_EXECUTION_ARMED")):return 3
    return 0

if __name__=="__main__":raise SystemExit(main())
