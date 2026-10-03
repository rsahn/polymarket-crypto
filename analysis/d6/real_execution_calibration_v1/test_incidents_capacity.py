import asyncio,ctypes,json,os
import pytest
from .incidents import IncidentStore
from .test_runtime_qualification import fixture,drive
from .capacity import require_capacity,REQUIRED_FREE_BYTES,QUOTA_BYTES,PROJECTED_BYTES,MAX_RECORD_BYTES
from .core import Journal

def decrypt(store,path):
    from app.live.l2_windows_storage import Blob
    platform=store.protection;data=path.read_bytes()
    buffer=(ctypes.c_ubyte*len(data)).from_buffer_copy(data);incoming=Blob(len(data),buffer);outgoing=Blob()
    platform.crypt.CryptUnprotectData.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(Blob)]
    try:
        assert platform.crypt.CryptUnprotectData(ctypes.byref(incoming),None,None,None,None,1,ctypes.byref(outgoing))
        return json.loads(ctypes.string_at(outgoing.data,outgoing.size))
    finally:
        if outgoing.data:platform.kernel.LocalFree(outgoing.data)

@pytest.mark.parametrize('journal_failure',[False,True])
def test_incident_original_message_and_executed_code_survive(tmp_path,monkeypatch,journal_failure):
    c,l,now,log,calls=fixture(tmp_path/'run',logged=True)
    l.incident_store=IncidentStore(tmp_path/'private-incidents')
    original=ValueError('unknown equivalent run0088 trigger secret-canary')
    async def failure():raise original
    c.account_source.snapshot=failure
    if journal_failure:
        original_append=l.journal.append
        def append(kind,payload):
            if kind=='STOP' and payload['reason']=='CALIBRATION_EXCEPTION':raise OSError('equivalent run0089 journal disk error')
            return original_append(kind,payload)
        monkeypatch.setattr(l.journal,'append',append)
    try:
        with pytest.raises(OSError if journal_failure else ValueError):asyncio.run(drive(c,now))
        files=list(l.incident_store.directory.glob('*.dpapi'))
        records=[decrypt(l.incident_store,p) for p in files]
        assert any(r['message']==str(original) and r['exception_type']=='ValueError' and r['frames'] and all(f['executed_code_b64'] for f in r['frames']) for r in records)
        if journal_failure:assert any(r['stage']=='JOURNAL_APPEND' and r['exception_type']=='OSError' for r in records)
        assert all(b'secret-canary' not in p.read_bytes() for p in files)
        assert 'secret-canary' not in l.journal.path.read_text()
        assert l.stop and l.report()['STOP_NEW_ENTRIES'] and not calls
    finally:l.journal.close();log.close()

def test_incident_archive_failure_blocks_entries_preserves_original(tmp_path,monkeypatch):
    from .incidents import capture
    c,l,*_=fixture(tmp_path)
    class Store:
        def capture(self,*a):raise OSError('storage unavailable')
    l.incident_store=Store()
    assert capture(l,ValueError('original'),'test') is None
    assert l.stop and l.stop_new_entries and not l.reconciled
    assert isinstance(l.incident_failure,OSError)
    l.journal.close()

@pytest.mark.parametrize('free,valid',[(REQUIRED_FREE_BYTES,True),(REQUIRED_FREE_BYTES-1,False),(0,False)])
def test_capacity_preflight(tmp_path,monkeypatch,free,valid):
    from types import SimpleNamespace
    monkeypatch.setattr('shutil.disk_usage',lambda p:SimpleNamespace(free=free))
    if valid:assert require_capacity(tmp_path)['quota_bytes_per_sink']>=PROJECTED_BYTES*1.5
    else:
        with pytest.raises(ValueError,match='STORAGE_72H'):require_capacity(tmp_path)

@pytest.mark.parametrize('quota,record_limit',[(100,MAX_RECORD_BYTES),(QUOTA_BYTES,100)])
def test_journal_capacity_overflow_fails_closed(tmp_path,quota,record_limit):
    j=Journal(tmp_path/'j','s',max_bytes=quota,max_record_bytes=record_limit)
    with pytest.raises(OSError,match='JOURNAL_QUOTA'):j.append('TEST',{'data':'x'*150})
    assert j.failed and j.seq==0 and j.bytes==0
    j.close()


def test_log_rotation_over_72h_retains_all_records(tmp_path):
    import io,time
    from .live_logging import LiveLog,LoggedJournal
    now=[0]
    log=LiveLog(tmp_path/'logs','capacity',background=False,console=io.StringIO(),clock=lambda:now[0],max_bytes=QUOTA_BYTES)
    j=LoggedJournal(tmp_path/'journal','capacity',log,max_bytes=QUOTA_BYTES,max_record_bytes=MAX_RECORD_BYTES)
    start=time.monotonic()
    try:
        for hour in range(73):
            now[0]=hour*3600
            j.append('RECONCILED',dict(CALIBRATION_ACCOUNT_RECONCILED=True,decision_ms=now[0]*1000,D6_current_inventory_proven=False))
        assert log.part==14 and len(list(log.directory.glob('*.log')))==15
        assert len(list(Journal.read(j.path)))==73
        assert sum(len(p.read_text().splitlines()) for p in log.directory.glob('*.log'))==73
        print('PHYSICAL_JOURNAL_AND_LOG_SAMPLE='+json.dumps(dict(records=73,fsync='each append, unmodified',rotations=14,logical_seconds=259200,wall_seconds=time.monotonic()-start,journal_bytes=j.bytes,log_bytes=log.total_bytes,quota_per_sink=QUOTA_BYTES)))
    finally:j.close();log.close()
