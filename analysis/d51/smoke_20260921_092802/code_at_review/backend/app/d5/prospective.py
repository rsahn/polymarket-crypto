"""Bounded, detached SHADOW collection followed only by data quality and two NoTrade replays."""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import shutil
import subprocess
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from .identity import assert_shadow
from .live import run
from .store import code_version


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, payload):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload,indent=2,allow_nan=False),encoding='utf-8')
    temporary.replace(path)


def clock_snapshot():
    commands = [['w32tm','/query','/status','/verbose'],
                ['w32tm','/stripchart','/computer:time.windows.com','/samples:3','/period:1','/dataonly'],
                ['w32tm','/stripchart','/computer:time.cloudflare.com','/samples:3','/period:1','/dataonly']]
    result={'captured_utc':utc_now(),'wall_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns(),'commands':[]}
    for command in commands:
        try:
            proc=subprocess.run(command,capture_output=True,text=True,errors='replace',timeout=20)
            result['commands'].append({'command':command,'exit_code':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr})
        except (OSError,subprocess.TimeoutExpired) as exc:
            result['commands'].append({'command':command,'error':str(exc)})
    return result


def validate_paths(db, output, seconds, test_run):
    if seconds < 86400 and not test_run:
        raise ValueError('Production collection requires at least 86400 seconds')
    if seconds <= 0 or seconds != seconds or seconds == float('inf'):
        raise ValueError('Finite positive collection duration required')
    if db.exists() or output.exists():
        raise FileExistsError('A NEW database and NEW output directory are required')
    import re
    pattern = r'd5_test_24h_\d{8}_\d{6}\.db' if test_run else r'd5_live_24h_\d{8}_\d{6}\.db'
    if not re.fullmatch(pattern,db.name):
        raise ValueError('Database must use the explicit D5 prospective filename')
    if not db.parent.is_dir() or not output.parent.is_dir():
        raise ValueError('Parent directories must be prepared before launch')


async def collect(db, seconds, reserve, progress, output):
    async def clock_monitor():
        while True:
            await asyncio.sleep(3600)
            sample=await asyncio.to_thread(clock_snapshot)
            atomic_json(output/f'clock_{time.time_ns()}.json',sample)
    monitor=asyncio.create_task(clock_monitor())
    try:
        return await run(SimpleNamespace(db=db,seconds=seconds,reconnect_after=0,
                        compress_payloads=True,min_free_bytes=reserve,on_progress=progress))
    finally:
        monitor.cancel()
        await asyncio.gather(monitor,return_exceptions=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--seconds',type=float,default=86520)
    parser.add_argument('--test-run',action='store_true',help='Infrastructure test only; never a production validation')
    parser.add_argument('--min-free-gib',type=float,default=5)
    args=parser.parse_args(argv)
    assert_shadow()
    db,output=args.db.resolve(),args.out.resolve()
    validate_paths(db,output,args.seconds,args.test_run)
    reserve=int(args.min_free_gib*1024**3)
    if reserve < 1024**3 or shutil.disk_usage(db.parent).free < reserve:
        raise ValueError('Insufficient disk reserve')
    output.mkdir(exist_ok=False)
    # Exclusive reservation guarantees that an old database can never be reopened.
    fd=os.open(db,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    os.close(fd)
    state={'pid':os.getpid(),'database':str(db),'output':str(output),'mode':'SHADOW',
           'strategy':'NO_TRADE','capital':500,'orders':0,'fills':0,'inventory':0,
           'research_allowed':False,'requested_seconds':args.seconds,'test_run':args.test_run,
           'started_utc':utc_now(),'phase':'PREPARING','code_version':code_version()}
    def update(changes):
        state.update(changes)
        state['updated_utc']=utc_now()
        atomic_json(output/'status.json',state)
    awake=False
    try:
        if os.name=='nt':
            awake=bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
            if not awake:
                raise OSError('Unable to request system wakefulness for the collection')
        update({'keep_awake':awake})
        atomic_json(output/'clock_before.json',clock_snapshot())
        update({'phase':'COLLECTING','collection_started_utc':utc_now(),
                'expected_collection_end_utc':datetime.fromtimestamp(time.time()+args.seconds,timezone.utc).isoformat()})
        result=asyncio.run(collect(db,args.seconds,reserve,update,output))
        update({'phase':'DATA_QUALITY','collection':result,'elapsed_seconds':result['collection_seconds'],
                'counts':result['counts'],'collection_ended_utc':utc_now()})
        atomic_json(output/'clock_after.json',clock_snapshot())
        # Import and execute review only after the writer has closed the database.
        from .quality import review
        report=review(db,output,result['session_id'],minimum_seconds=86400,
                      progress=update,final_code_version=code_version())
        update({'phase':'COMPLETE' if report['QUALITY_REVIEW_PASSED'] else 'QUALITY_REVIEW_BLOCKED',
                'quality_review_passed':report['QUALITY_REVIEW_PASSED'],
                'quality_failures':report['QUALITY_FAILURES'],'replay_hashes_equal':report['REPLAY_HASHES_EQUAL'],
                'final_report':str(output/'FINAL_DATA_QUALITY_REPORT.md'),'finished_utc':utc_now()})
        return 0 if report['QUALITY_REVIEW_PASSED'] or args.test_run else 2
    except BaseException as exc:
        update({'phase':'FAILED','error':str(exc),'traceback':traceback.format_exc(),'failed_utc':utc_now()})
        raise
    finally:
        if awake:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            update({'keep_awake':False})


if __name__=='__main__':
    raise SystemExit(main())
