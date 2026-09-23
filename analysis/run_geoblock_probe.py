import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"backend"))
from app.live.geoblock import GeoBlockGate
if __name__=="__main__":
 r=GeoBlockGate().check()
 # Do not print IP returned by provider.
 if "geo" in r and isinstance(r["geo"],dict):r["geo"].pop("ip",None)
 print(json.dumps(r,indent=2))
