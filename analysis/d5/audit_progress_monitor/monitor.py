"""External read-only process monitor. Never opens D5 SQLite or changes target process."""
import ctypes,datetime,json,os,pathlib,time
from ctypes import wintypes as w
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[2]
STATUS=ROOT/'analysis/d5/stop_3h_20260920/controller_status.json'
REVIEW=ROOT/'analysis/d5/3h_20260920_124822_review'
TARGET=12408
class IO(ctypes.Structure):
    _fields_=[(n,ctypes.c_ulonglong) for n in ('read_operations','write_operations','other_operations','read_bytes','write_bytes','other_bytes')]
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
k.GetProcessIoCounters.argtypes=[w.HANDLE,ctypes.POINTER(IO)]
k.GetProcessTimes.argtypes=[w.HANDLE,*[ctypes.POINTER(w.FILETIME)]*4]
k.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD]
k.CloseHandle.argtypes=[w.HANDLE]
def read_json(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}
def atomic(path,text):
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(text,encoding='utf-8');temp.replace(path)
def main():
    with (HERE/'monitor.lock').open('x') as f:f.write(str(os.getpid()))
    h=k.OpenProcess(0x1000|0x100000,False,TARGET)
    if not h:raise ctypes.WinError(ctypes.get_last_error())
    previous=None
    try:
        while True:
            now=datetime.datetime.now(datetime.timezone.utc); mono=time.monotonic()
            alive=k.WaitForSingleObject(h,0)==258
            io=IO();ts=[w.FILETIME() for _ in range(4)]
            if not k.GetProcessIoCounters(h,ctypes.byref(io)):raise ctypes.WinError(ctypes.get_last_error())
            if not k.GetProcessTimes(h,*[ctypes.byref(t) for t in ts]):raise ctypes.WinError(ctypes.get_last_error())
            cpu=sum((t.dwHighDateTime<<32)+t.dwLowDateTime for t in ts[2:])/1e7
            state=read_json(STATUS);report=read_json(REVIEW/'DATA_QUALITY_REPORT.json')
            total=report.get('TOTAL_EVENTS');phase=state.get('phase','UNKNOWN')
            replay_n=state.get('replay');events=state.get('events_replayed') if phase=='REPLAY' else None
            percent=100*events/total if events is not None and total else None
            elapsed=(now-datetime.datetime(2026,9,20,13,51,10,128218,tzinfo=datetime.timezone.utc)).total_seconds()
            row={'monitor_pid':os.getpid(),'target_pid':TARGET,'updated_utc':now.isoformat(),'target_alive':alive,'phase':phase,'review_elapsed_seconds':round(elapsed,1),'cpu_seconds':cpu,'read_bytes':io.read_bytes,'write_bytes':io.write_bytes,'read_operations':io.read_operations,'audit_percent':None,'audit_rows_processed':None,'replay_number':replay_n,'replay_events_processed':events,'total_events':total,'replay_percent':percent,'remaining_seconds':None,'read_MBs':None,'write_MBs':None,'cpu_percent_one_core':None,'note':'Process I/O includes OS cache; cumulative counters include controller lifetime. Audit percentage and ETA are unknown. Replay progress comes from existing status.'}
            if previous:
                dt=mono-previous[0]
                row.update(read_MBs=round((io.read_bytes-previous[1])/dt/1e6,3),write_MBs=round((io.write_bytes-previous[2])/dt/1e6,3),cpu_percent_one_core=round(100*(cpu-previous[3])/dt,2))
            previous=(mono,io.read_bytes,io.write_bytes,cpu)
            atomic(HERE/'progress.json',json.dumps(row,indent=2))
            with (HERE/'samples.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
            duration=str(datetime.timedelta(seconds=int(max(0,elapsed))))
            md=f'# Compteur D5 — surveillance externe\n\nActualisé : {now.astimezone().isoformat(timespec="seconds")} (toutes les 15 secondes).\n\n'
            md+=f'- PID audité : {TARGET} ; actif : {alive}\n- Phase : {phase}\n- Temps depuis le début de la revue : {duration}\n- CPU cumulé du processus : {cpu:.2f} s\n- CPU sur le dernier intervalle : {row["cpu_percent_one_core"]} % d’un cœur\n- Lectures cumulées du processus : {io.read_bytes/1e9:.3f} Go\n- Débit de lecture : {row["read_MBs"]} Mo/s\n- Débit d’écriture : {row["write_MBs"]} Mo/s\n- Audit : pourcentage et lignes traitées inconnus\n'
            if percent is not None:md+=f'- Replay {replay_n} : {events:,} / {total:,} événements ({percent:.2f} %)\n'
            else:md+='- Replays : aucun compteur actif disponible\n'
            md+='- Temps restant : inconnu\n\nLes compteurs I/O incluent les lectures en cache et ne représentent pas des lignes validées. Aucun accès à SQLite, signal ou modification du processus audité. Le moniteur s’arrête à la fin du processus cible.\n'
            atomic(HERE/'PROGRESS.md',md)
            if not alive:break
            time.sleep(15)
    finally:k.CloseHandle(h)
if __name__=='__main__':main()
