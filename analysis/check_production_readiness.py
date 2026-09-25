"""Unconfigured read-only readiness report; no SDK construction or network I/O.
Applications may inject the inspected read-only sources into ProductionReadinessCheck.
An absent binding remains a blocker. This command never loads wallet credentials.
"""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from app.live.readiness import ProductionReadinessCheck

if __name__=="__main__":
    report=asyncio.run(ProductionReadinessCheck().run())
    report["integration_status"]="UNBOUND_NOT_READY_FOR_LIVE"
    print(json.dumps(report,indent=2))
