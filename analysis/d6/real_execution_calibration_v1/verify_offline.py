"""Offline test harness; external sockets, DNS and subprocesses are denied.
Windows asyncio's local self-pipe is the sole socketpair exception.
"""
import contextvars,os,socket,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'backend'),str(ROOT/'backend'/'tests')]
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
sys.dont_write_bytecode=True
_in_pair=contextvars.ContextVar('stdlib_socketpair',default=False)
_pair=socket.socketpair

def local_pair(*args,**kwargs):
    token=_in_pair.set(True)
    try:return _pair(*args,**kwargs)
    finally:_in_pair.reset(token)

def guard(event,args):
    if event=='subprocess.Popen':
        argv=args[1];fixture=str(Path(__file__).with_name('crash_fixture.py'))
        if isinstance(argv,str):
            import shlex,subprocess
            parsed=[x.strip(chr(34)) for x in shlex.split(argv,posix=False)]
            if len(parsed)==4 and parsed[:3]==[sys.executable,'-B',fixture] and subprocess.list2cmdline(parsed)==argv and Path(parsed[3]).is_absolute():return
        if isinstance(argv,(list,tuple)) and len(argv)==4 and argv[:3]==[sys.executable,'-B',fixture] and Path(argv[3]).is_absolute():return
        raise RuntimeError('SUBPROCESS_FORBIDDEN')
    if event=='os.system':raise RuntimeError('SUBPROCESS_FORBIDDEN')
    if event in ('socket.connect','socket.bind','socket.getaddrinfo','socket.sendto'):
        if _in_pair.get() and event in ('socket.connect','socket.bind') and args[1][0] in ('127.0.0.1','::1'):return
        raise RuntimeError('NETWORK_FORBIDDEN')

if __name__=='__main__':
    socket.socketpair=local_pair;sys.addaudithook(guard)
    import pytest
    targets=sys.argv[1:] or [str(Path(__file__).parent)]
    # Legacy research suites import siblings as top-level modules. Prepend each
    # test directory so a same-named module in this harness cannot shadow them.
    # Autoload stays disabled; explicitly enable the async tests' required plugin.
    raise SystemExit(pytest.main(['--import-mode=prepend','-p','pytest_asyncio.plugin','-p','no:cacheprovider','-q',*targets]))
