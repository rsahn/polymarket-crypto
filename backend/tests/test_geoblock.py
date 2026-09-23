import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.live.geoblock import GeoBlockGate

def test_gate_is_fail_closed(monkeypatch):
 def boom(*a,**k):raise TimeoutError()
 monkeypatch.setattr("urllib.request.urlopen",boom)
 r=GeoBlockGate().check()
 assert r["allowed"] is False and r["reason"]=="GEO_CHECK_FAILED"
