"""One-off evidence runner, not runtime code. Reuses existing network-denied harness."""
import os,sys,runpy,time,asyncio,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
# Block real secret/config reads in addition to harness network/process denial.
def secrets_guard(event,args):
    if event=='open' and isinstance(args[0],(str,bytes)):
        p=Path(os.fsdecode(args[0]));name=p.name.lower()
        if name=='.env' or name.startswith('.env.') or name in ('credentials.json','secrets.json'):raise RuntimeError('SECRET_FILE_READ_DENIED')
sys.addaudithook(secrets_guard)
latencies=[]
for _ in range(10):
    async def sample():
        start=time.perf_counter();await asyncio.to_thread(lambda:None);return (time.perf_counter()-start)*1000
    latencies.append(asyncio.run(sample()))
print('COLD_THREAD_ROUNDTRIP_MS='+json.dumps(latencies),flush=True)
files=[];excluded=[]
for p in ROOT.rglob('test*.py'):
    rel=p.relative_to(ROOT).as_posix()
    if any(x in rel for x in ('/vendor/','/frozen_code_and_protocol/','/code_at_review/','/node_modules/','/.venv/','/_archive/')):
        excluded.append(rel);continue
    files.append(rel)
report=Path(__file__).with_name('repo_test_inventory.json')
report.write_text(json.dumps(dict(included=files,excluded=excluded,reason='Third-party vendor tests and immutable historical snapshots/archive, not active first-party suite'),indent=2))
print('FIRST_PARTY_TEST_FILES='+str(len(files))+' EXCLUDED='+str(len(excluded)),flush=True)
sys.argv=['verify_offline.py',*files,'--continue-on-collection-errors']
runpy.run_path(str(ROOT/'analysis/d6/real_execution_calibration_v1/verify_offline.py'),run_name='__main__')
