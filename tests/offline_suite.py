"""Active first-party offline suites, isolated per directory. No production credentials/network.
Child bootstrap installs guards before pytest/application imports. No generic shell permission.
"""
import os,sys,json,subprocess,tempfile,contextvars,socket,runpy,hashlib,ast,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SELF=Path(__file__).resolve()
BASE=ROOT/'analysis/d6/real_execution_calibration_v1'
OUT=Path(os.environ.get('D6_TEST_OUTPUT',str(BASE/'evidence/native_v2')))
CRASH=BASE/'crash_fixture.py'
CRASH_SHA256='89ef1de7151ea143a9ae69e15655f48bbe26b26788aca8a4801669bba6b8d411'
JOURNAL_CODE="""import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from analysis.d6.prospective_v1.journal import DurableEventJournal
import json
j=DurableEventJournal(sys.argv[2],json.loads(sys.argv[3]))
j.append(json.loads(sys.argv[4]))
os._exit(17)
"""
ACL_READER="""$ErrorActionPreference='Stop'; $p=([Console]::In.ReadToEnd() | ConvertFrom-Json); $d=[System.IO.Directory]::GetAccessControl($p); $f=[System.IO.File]::GetAccessControl([System.IO.Path]::Combine($p,'credential.dpapi')); @{protected=$d.AreAccessRulesProtected; rules=@($d.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]) | ForEach-Object { @{sid=$_.IdentityReference.Value; type=$_.AccessControlType.ToString(); rights=[int]$_.FileSystemRights} }); file_rules=@($f.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]) | ForEach-Object { @{sid=$_.IdentityReference.Value; type=$_.AccessControlType.ToString(); rights=[int]$_.FileSystemRights} })} | ConvertTo-Json -Depth 4"""
ACL_TEST="$p=([Console]::In.ReadToEnd() | ConvertFrom-Json); $a=[System.IO.Directory]::GetAccessControl($p); @{protected=$a.AreAccessRulesProtected; rules=@($a.Access | ForEach-Object { @{sid=$_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value; type=$_.AccessControlType.ToString()} })} | ConvertTo-Json -Depth 4"
ENV_KEYS={'SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','LOCALAPPDATA','APPDATA','USERPROFILE','USERNAME','TEMP','TMP','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE'}
def clean_env(temp):
    e={k:v for k,v in os.environ.items() if k.upper() in ENV_KEYS}
    e.update(TEMP=str(temp),TMP=str(temp),PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',PYTHONDONTWRITEBYTECODE='1')
    return e

def inside(path,root):
    p=Path(path).absolute()
    if not p.resolve().is_relative_to(Path(root).resolve()):return False
    return not any(x.is_symlink() or (hasattr(x,'is_junction') and x.is_junction()) for x in (p,*p.parents))

def install(temp):
    temp=Path(temp).resolve();git_exe=shutil.which('git');powershell_exe=str(Path(os.environ['SYSTEMROOT'])/'System32/WindowsPowerShell/v1.0/powershell.exe');original_run=subprocess.run;original_popen=subprocess.Popen
    original_pair=socket.socketpair;pair=contextvars.ContextVar('pair',default=False);approved=contextvars.ContextVar('approved',default=False);acl_ok=contextvars.ContextVar('acl',default=False)
    def guarded_pair(*a,**kw):
        token=pair.set(True)
        try:return original_pair(*a,**kw)
        finally:pair.reset(token)
    socket.socketpair=guarded_pair
    def audit(event,args):
        if event=='subprocess.Popen' and not approved.get():raise RuntimeError('SUBPROCESS_FORBIDDEN')
        if event in ('os.system','os.posix_spawn','os.spawn','os.exec','os.startfile','os.startfile/2'):raise RuntimeError('SUBPROCESS_FORBIDDEN')
        if event in ('socket.connect','socket.bind','socket.getaddrinfo','socket.sendto'):
            if pair.get() and event in ('socket.connect','socket.bind') and args[1][0] in ('127.0.0.1','::1'):return
            raise RuntimeError('NETWORK_FORBIDDEN')
        if event=='open' and isinstance(args[0],(str,bytes)):
            p=Path(os.fsdecode(args[0]));name=p.name.lower()
            if (name=='.env' or name.startswith('.env.') or name.endswith('.dpapi') or name in ('credentials.json','secrets.json')) and not inside(p,temp):raise RuntimeError('REAL_SECRET_FILE_FORBIDDEN')
    sys.addaudithook(audit)
    class SafePopen(original_popen):
        def __init__(self,args,*a,**kw):
            if kw.get('shell') or kw.get('executable') is not None or isinstance(args,(str,bytes)) or a:raise RuntimeError('SUBPROCESS_SHAPE_FORBIDDEN')
            cmd=list(map(str,args));cwd=Path(kw.get('cwd') or os.getcwd()).resolve()
            allowed=False
            if cmd==['git','rev-parse','HEAD'] and (cwd==ROOT or inside(cwd,temp)) and git_exe:
                cmd[0]=git_exe;allowed=True
            elif len(cmd)==5 and cmd[:4]==['powershell','-NoProfile','-NonInteractive','-Command'] and cmd[4] in (ACL_READER,ACL_TEST) and acl_ok.get():
                cmd[0]=powershell_exe;allowed=True
            elif len(cmd)>=4 and Path(cmd[0]).resolve()==Path(sys.executable).resolve() and cmd[1]=='-B':
                if cmd[2]==str(CRASH) and len(cmd)==4 and inside(cmd[3],temp) and hashlib.sha256(CRASH.read_bytes()).hexdigest()==CRASH_SHA256:
                    cmd=[sys.executable,'-B',str(SELF),'--crash',str(temp),cmd[3]];allowed=True
                elif cmd[2]=='-c' and len(cmd)==8 and cmd[3]==JOURNAL_CODE and Path(cmd[4]).resolve()==ROOT and inside(cmd[5],temp):
                    cmd=[sys.executable,'-B',str(SELF),'--journal',str(temp),*cmd[4:]];allowed=True
            if not allowed:raise RuntimeError('SUBPROCESS_NOT_AUDITED')
            kw['env']=clean_env(temp)
            token=approved.set(True)
            try:super().__init__(cmd,**kw)
            finally:approved.reset(token)
    def safe_run(*a,**kw):
        cmd=kw.get('args',a[0] if a else [])
        is_acl=isinstance(cmd,(list,tuple)) and len(cmd)==5 and cmd[:4]==['powershell','-NoProfile','-NonInteractive','-Command']
        if is_acl:
            try:p=json.loads(kw.get('input',''))
            except Exception:raise RuntimeError('ACL_PATH_REQUIRED')
            if not isinstance(p,str) or not inside(p,temp):raise RuntimeError('ACL_NONFIXTURE_PATH')
            token=acl_ok.set(True)
            try:return original_run(*a,**kw)
            finally:acl_ok.reset(token)
        return original_run(*a,**kw)
    subprocess.Popen=SafePopen;subprocess.run=safe_run

def inventory():
    included=[];excluded=[]
    for p in ROOT.rglob('test*.py'):
        rel=p.relative_to(ROOT).as_posix()
        if any(x in p.parts for x in ('vendor','frozen_code_and_protocol','code_at_review','node_modules','.venv','_archive')):excluded.append(rel)
        else:included.append(rel)
    return sorted(included),sorted(excluded)

def main():
    if len(sys.argv)>1 and sys.argv[1] in ('--child','--crash','--journal'):
        mode,temp=sys.argv[1:3];os.environ.clear();os.environ.update(clean_env_saved)
        tempfile.tempdir=temp;sys.dont_write_bytecode=True;install(temp)
        sys.path[:0]=[str(ROOT),str(ROOT/'backend'),str(ROOT/'backend/tests')]
        if mode=='--crash':
            if hashlib.sha256(CRASH.read_bytes()).hexdigest()!=CRASH_SHA256:raise RuntimeError('CRASH_FIXTURE_CHANGED')
            sys.argv=[str(CRASH),sys.argv[3]];runpy.run_path(str(CRASH),run_name='__main__');return
        if mode=='--journal':
            sys.argv=['-c',*sys.argv[3:]];exec(compile(JOURNAL_CODE,'<audited-journal-crash>','exec'),{'__name__':'__main__'});return
        group=sys.argv[3];files=json.loads(sys.argv[4])
        allowed_files=set(inventory()[0])
        if not all(f in allowed_files and Path(f).parent.as_posix()==group for f in files):raise RuntimeError('TEST_INVENTORY_SCOPE')
        sys.path.insert(0,str(ROOT/group))
        import pytest
        raise SystemExit(pytest.main(['-v' if group=='backend/tests' else '-q','-o','faulthandler_timeout=30','--import-mode=importlib','-p','no:cacheprovider','-p','pytest_asyncio.plugin','--basetemp',str(Path(temp)/'pytest'),*files]))
    included,excluded=inventory();groups={}
    for f in included:groups.setdefault(Path(f).parent.as_posix(),[]).append(f)
    selected=sys.argv[1:]
    if selected:
        if any(k not in groups for k in selected):raise ValueError('UNKNOWN_SUITE_GROUP')
        groups={k:v for k,v in groups.items() if k in selected}
    OUT.mkdir(exist_ok=True,parents=True)
    (OUT/'active_suite_inventory.json').write_text(json.dumps(dict(included=included,excluded=excluded,groups=list(groups)),indent=2))
    results=[]
    for i,(group,files) in enumerate(groups.items()):
        # Parent orchestrator never imports application/test code. Children scrub environment and guard first.
        with tempfile.TemporaryDirectory(prefix='d6-audited-tests-') as temp:
            cmd=[sys.executable,'-B',str(SELF),'--child',temp,group,json.dumps(files)]
            try:r=subprocess.run(cmd,cwd=ROOT,env=clean_env(temp),capture_output=True,text=True,errors='replace',timeout=180)
            except subprocess.TimeoutExpired as exc:
                output=(exc.stdout or b'')+(exc.stderr or b'')
                (OUT/('active_group_'+str(i)+'.txt')).write_bytes(output if isinstance(output,bytes) else output.encode())
                results.append(dict(group=group,exit='TIMEOUT'));print(group,'TIMEOUT',flush=True);continue
            output=r.stdout+r.stderr;(OUT/('active_group_'+str(i)+'.txt')).write_text(output,encoding='utf-8')
            tail='\n'.join(output.splitlines()[-8:]);print(group,r.returncode,tail,flush=True)
            results.append(dict(group=group,exit=r.returncode,report='active_group_'+str(i)+'.txt',tail=tail))
    (OUT/'active_suite_results.json').write_text(json.dumps(results,indent=2))
    raise SystemExit(int(any(r['exit']!=0 for r in results)))
if __name__=='__main__':
    clean_env_saved=clean_env(sys.argv[2]) if len(sys.argv)>2 and sys.argv[1].startswith('--') else {}
    main()
