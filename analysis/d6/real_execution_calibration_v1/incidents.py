"""Independent, owner-only DPAPI incident archive; never export with public logs."""
import hashlib,os,sys,traceback,uuid,marshal,base64
from pathlib import Path
from .core import encoded

class IncidentStore:
    def __init__(self,directory,protection=None):
        from app.live.l2_windows_storage import WindowsProtection
        self.protection=protection or WindowsProtection();self.directory=Path(directory)
        self.protection.create_private_directory(self.directory)
        self.used=0
    def capture(self,exc,stage):
        record=dict(stage=stage,exception_type=type(exc).__name__,message=str(exc),traceback=''.join(traceback.format_exception(exc)),frames=[])
        tb=exc.__traceback__
        while tb:
            p=Path(tb.tb_frame.f_code.co_filename)
            record['frames'].append(dict(path=str(p),line=tb.tb_lineno,function=tb.tb_frame.f_code.co_name,executed_code_b64=base64.b64encode(marshal.dumps(tb.tb_frame.f_code)).decode(),source_sha256=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None))
            tb=tb.tb_next
        raw=encoded(record).encode()
        if len(raw)>1024**2 or self.used+len(raw)>64*1024**2:raise OSError('INCIDENT_QUOTA')
        encrypted=self.protection.protect(raw);identifier=uuid.uuid4().hex
        with (self.directory/(identifier+'.dpapi')).open('xb',buffering=0) as f:
            view=memoryview(encrypted)
            while view:
                n=f.write(view)
                if not n:raise OSError('INCIDENT_SHORT_WRITE')
                view=view[n:]
            os.fsync(f.fileno())
        self.used+=len(raw)
        return identifier

def capture(ledger,exc,stage):
    store=getattr(ledger,'incident_store',None)
    if store is None:return None
    try:return store.capture(exc,stage)
    except BaseException as failure:
        ledger.stop=True;ledger.stop_new_entries=True;ledger.reconciled=False
        ledger.incident_failure=failure
        try:sys.stderr.write('D6_INCIDENT_CAPTURE_FAILED:'+type(failure).__name__+'\n');sys.stderr.flush()
        except Exception:pass
        return None
