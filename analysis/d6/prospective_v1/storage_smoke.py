"""Technical archive/replay smoke over an immutable captured observation window.

No strategy execution, economic metrics, partition opening or network access.
"""
import argparse,hashlib,json,os,shutil,time
from pathlib import Path
from .archive_codec import Codec,ArchiveWriter,stream_archive,row_fingerprint,HEADER
from .storage_audit import readonly
from .core import safety

def peak_rss():
    if os.name=="nt":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_=[("cb",wintypes.DWORD),("PageFaultCount",wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in
                ("PeakWorkingSetSize","WorkingSetSize","QuotaPeakPagedPoolUsage","QuotaPagedPoolUsage",
                 "QuotaPeakNonPagedPoolUsage","QuotaNonPagedPoolUsage","PagefileUsage","PeakPagefileUsage")]
        m=Counters();m.cb=ctypes.sizeof(m)
        kernel=ctypes.WinDLL("kernel32");kernel.GetCurrentProcess.restype=wintypes.HANDLE
        psapi=ctypes.WinDLL("psapi")
        psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(m),m.cb):
            raise ctypes.WinError()
        return m.PeakWorkingSetSize
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024

def smoke(source,out,source_duration):
    safety();source=Path(source).resolve();out=Path(out).resolve()
    before=(source.stat().st_size,source.stat().st_mtime_ns)
    out.mkdir(parents=True,exist_ok=False);archive=out/"capture.pva"
    c=readonly(source);codec=Codec();writer=ArchiveWriter(archive)
    expected=hashlib.sha256();counts={};total=0;start=time.perf_counter()
    try:
        schema=c.execute("select type,name,tbl_name,sql from sqlite_master order by type,name").fetchall()
        writer.append(["SCHEMA",schema])
        tables=[n for n, in c.execute("select name from sqlite_master where type='table' order by name")]
        for table in tables:
            counts[table]=0
            for row in c.execute('select * from "'+table.replace('"','""')+'" order by rowid'):
                expected.update(row_fingerprint(table,row))
                writer.append([table,[codec.encode(v) for v in row]])
                counts[table]+=1;total+=1
                if total%100000==0:
                    progress={"phase":"ENCODE","rows":total,"table":table,"elapsed":time.perf_counter()-start,
                              "written":archive.stat().st_size,"peak_rss":peak_rss()}
                    (out/"progress.json").write_text(json.dumps(progress),encoding="utf-8")
                    print(json.dumps(progress),flush=True)
        writer.close()
    finally:
        c.close()
        if not writer.closed:
            writer.poisoned=True;writer.close()
    encoding_seconds=time.perf_counter()-start;encoding_peak=peak_rss()
    recovered=hashlib.sha256();replayed=0;decoder=Codec();replay_start=time.perf_counter()
    for table,row in stream_archive(archive):
        if table=="SCHEMA":
            if row!=[list(x) for x in schema]:raise ValueError("SCHEMA_ROUNDTRIP_MISMATCH")
            continue
        values=[decoder.decode(v) for v in row]
        recovered.update(row_fingerprint(table,values));replayed+=1
        if replayed%100000==0:
            print(json.dumps({"phase":"REPLAY","rows":replayed,"elapsed":time.perf_counter()-replay_start,
                              "peak_rss":peak_rss()}),flush=True)
    replay_seconds=time.perf_counter()-replay_start
    if recovered.hexdigest()!=expected.hexdigest() or replayed!=total:raise ValueError("LOSSLESS_REPLAY_MISMATCH")
    if before!=(source.stat().st_size,source.stat().st_mtime_ns):raise ValueError("SOURCE_CHANGED")
    size=archive.stat().st_size
    projection=__import__("math").ceil(size/source_duration*168*3600)
    reserve=__import__("math").ceil(projection*2.4)
    free=shutil.disk_usage(out).free
    result={"status":"LOSSLESS_TECHNICAL_REPLAY_PASS","source":str(source),"archive":str(archive),
        "source_observation_seconds":source_duration,"new_network_collection":False,
        "encoding_wall_seconds":encoding_seconds,"bytes_written":size,"raw_framed_bytes":writer.raw_bytes,
        "bytes_per_source_second":size/source_duration,"source_db_bytes":before[0],
        "db_to_archive_ratio":before[0]/size,"rows":total,"counts":counts,
        "logical_input_sha256":expected.hexdigest(),"replayed_sha256":recovered.hexdigest(),
        "source_stat_unchanged":True,"frame_hash_and_header_overhead":(writer.frames+1)*HEADER.size+5,
        "journal_allowance":None,"checkpoint_allowance":None,
        "replay_seconds":replay_seconds,"replay_rows_per_second":replayed/replay_seconds,
        "encoding_peak_rss_bytes":encoding_peak,"process_peak_rss_bytes":peak_rss(),
        "projected_168h_bytes":projection,"engineering_factor":"2 * 1.2",
        "required_bytes_lower_bound":reserve,"free_bytes_after_smoke":free,
        "additional_bytes_lower_bound":max(0,reserve-free),"storage_status":"STORAGE_UNQUALIFIED",
        "replay_status":"ARCHIVE_STREAMING_PASS_ECONOMIC_REPLAY_UNQUALIFIED",
        "partition_opened":False,"economic_metrics_computed":False,**safety()}
    (out/"RESULT.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    p.add_argument("--source-seconds",type=float,required=True);a=p.parse_args()
    print(json.dumps(smoke(a.source,a.out,a.source_seconds),indent=2))
if __name__=="__main__":main()
