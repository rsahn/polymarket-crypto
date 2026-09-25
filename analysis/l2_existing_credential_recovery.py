"""Offline preview only. No recovery, signing or credential loading is implemented."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.live.l2_recovery_preparation import Plan, preview


class PublicArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's default error can echo arbitrary secret-bearing arguments.
        self.exit(2, "Invalid arguments: only --preview and --output are supported.\n")


def main(argv=None):
    parser = PublicArgumentParser(description="Offline preview only; recovery unavailable")
    parser.add_argument("--preview", action="store_true", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "L2_RECOVERY_PREVIEW.json")
    args = parser.parse_args(argv)
    signer = os.environ.get("L2_RECOVERY_EXPECTED_SIGNER")
    report = json.dumps(preview(signer), indent=2) + "\n"
    status = 0
    try:
        Plan(signer)
    except ValueError:
        status = 2
    if any(os.environ.get(n, "false").strip().lower() != "false"
           for n in ("REAL_ORDERS_ENABLED", "LIVE_EXECUTION_ARMED")):
        status = 3
    try:
        # Exclusive creation: never replace an existing report or follow its symlink.
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write(report)
    except OSError:
        return 4
    print(report, end="")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
