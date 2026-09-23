"""Fail-closed Polymarket geographic eligibility gate."""
import json,urllib.request

class GeoBlockGate:
    URL="https://polymarket.com/api/geoblock"
    def check(self,timeout=5):
        try:
            req=urllib.request.Request(self.URL,headers={"User-Agent":"polymarket-crypto/1.0"})
            with urllib.request.urlopen(req,timeout=timeout) as r:
                o=json.loads(r.read().decode("utf-8"))
            blocked=o.get("blocked")
            if blocked is not False:
                return {"allowed":False,"reason":"GEO_BLOCKED_OR_UNKNOWN","geo":o}
            return {"allowed":True,"reason":None,"geo":o}
        except Exception as exc:
            return {"allowed":False,"reason":"GEO_CHECK_FAILED","error":type(exc).__name__}
