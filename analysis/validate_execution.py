"""Offline pytest harness: production monetary calls forbidden, no external sockets."""
from pathlib import Path
import ipaddress
import json
import os
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"backend"))
os.environ["REAL_ORDERS_ENABLED"]="false"
os.environ["LIVE_EXECUTION_ARMED"]="false"
os.environ["PYTHONDONTWRITEBYTECODE"]="1"
blocked=[]

def audit(event,args):
    if event!="socket.connect":return
    address=args[1]
    # asyncio Windows self-pipes use loopback sockets; public connections are forbidden.
    host=address[0] if isinstance(address,tuple) else ""
    try:local=ipaddress.ip_address(host).is_loopback
    except ValueError:local=False
    if not local:
        blocked.append("EXTERNAL_SOCKET_BLOCKED")
        raise RuntimeError("OFFLINE_TESTS_ONLY")


def main():
    sys.addaudithook(audit)
    from app.live.clob_transport import LiveClobTransport
    original={name:getattr(LiveClobTransport,name) for name in ("submit_limit","submit_exit_limit","cancel_order")}
    calls=[]
    # Keep lock regression tests meaningful; wrap original locked methods and count attempts.
    for name,method in original.items():
        def wrap(name,method):
            async def locked(self,*args,**kwargs):
                calls.append(name)
                return await method(self,*args,**kwargs)
            return locked
        setattr(LiveClobTransport,name,wrap(name,method))
    sdk_attempts=[]
    sdk_patched=[]
    try:
        import polymarket
        for class_name in ("AsyncSecureClient","SecureClient"):
            cls=getattr(polymarket,class_name,None)
            if cls is None:continue
            for name in ("place_limit_order","place_market_order","post_order","post_orders","cancel_order","cancel_orders","cancel_all","create_limit_order"):
                if not hasattr(cls,name):continue
                def forbidden(*args,**kwargs):
                    sdk_attempts.append("SDK_MONETARY_CALL_BLOCKED")
                    raise AssertionError("SDK_MONETARY_CALL_BLOCKED")
                setattr(cls,name,forbidden)
                sdk_patched.append(class_name+"."+name)
    except ImportError:pass
    import pytest
    code=pytest.main([*sys.argv[1:],"-p","no:cacheprovider","--tb=short","-q"])
    print("OFFLINE_PROOF "+json.dumps(dict(external_connections_blocked=len(blocked),
        production_transport_lock_tests=len(calls),real_orders_enabled=os.environ["REAL_ORDERS_ENABLED"],
        live_execution_armed=os.environ["LIVE_EXECUTION_ARMED"],sdk_monetary_attempts=len(sdk_attempts),sdk_methods_guarded=len(sdk_patched))))
    return code

if __name__=="__main__":raise SystemExit(main())
