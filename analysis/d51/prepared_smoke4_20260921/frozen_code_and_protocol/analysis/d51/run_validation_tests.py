import datetime,hashlib,json,os,pathlib,re,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[2]
tag=sys.argv[1];assert re.fullmatch(r'[a-zA-Z0-9_]+',tag)
suites=['backend/tests','analysis/d5/auditor_next','analysis/d6/tests','analysis/d6/pipeline','analysis/d6/research','analysis/d6/paper_runtime','analysis','analysis/d51']
results=[]
for suite in suites:
 env=dict(os.environ);env['PYTHONPATH']=os.pathsep.join(str(ROOT/p) for p in ['backend','backend/tests',suite,'analysis/d6/vendor','analysis/d6'])
 pattern='test_c3_d4_analysis.py' if suite=='analysis' else 'test_*.py'
 log=ROOT/'analysis/d51'/f"{tag}_{suite.replace('/','_')}_tests.log"
 start=time.perf_counter()
 with log.open('x',encoding='utf-8') as f:r=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',suite,'-p',pattern,'-v'],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
 text=log.read_text();matches=re.findall(r'Ran (\d+) tests?',text)
 row=dict(suite=suite,exit_code=r.returncode,count=int(matches[-1]) if matches else None,seconds=time.perf_counter()-start,log=log.name);results.append(row);print(json.dumps(row),flush=True)
paths=[p for folder in ('backend/app','backend/tests') for p in (ROOT/folder).rglob('*') if p.suffix in ('.py','.sql')]+list((ROOT/'analysis/d5/auditor_next').glob('*.py'))+[ROOT/'analysis/d51/run_smoke.py',pathlib.Path(__file__).resolve()]
report=dict(captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),suites=results,all_passed=all(x['exit_code']==0 and x['count'] is not None for x in results),total_tests=sum(x['count'] or 0 for x in results),code_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
with (ROOT/'analysis/d51'/f'TEST_RESULTS_{tag}.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
if not report['all_passed']:raise SystemExit(1)
