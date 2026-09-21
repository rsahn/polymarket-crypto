"""Full source SHA-256 attestation after the review exits; no database connection."""
import pathlib,json,hashlib,time,datetime,os,argparse
from run_accelerated import process_alive
from app.d5 import quality
from app.d5.store import code_version

def write(path,value):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2),encoding='utf-8');tmp.replace(path)
def verify(review,reference):
 review=pathlib.Path(review).resolve();reference=pathlib.Path(reference).resolve();progress=json.loads((review/'progress.json').read_text(encoding='utf-8'))
 if progress['status']=='RUNNING' or process_alive(progress['pid']):raise RuntimeError('Wait for current review to exit before hashing')
 if (review/'SOURCE_HASH_VERIFICATION.json').exists():raise FileExistsError('Attestation already exists; preserve it')
 checkpoint=review/'hash_progress.json'
 if checkpoint.exists():
  old=json.loads(checkpoint.read_text())
  if old.get('status')=='RUNNING' and process_alive(old['pid']):raise RuntimeError('Hash already active')
 manifest=json.loads((review/'RUN_MANIFEST.json').read_text(encoding='utf-8'));ref=json.loads(reference.read_text(encoding='utf-8'));source=pathlib.Path(manifest['source']).resolve();before=(source.stat().st_size,source.stat().st_mtime_ns)
 if source!=pathlib.Path(ref['source']).resolve() or list(before)!=[ref['source_bytes'],ref['source_mtime_ns']]:raise RuntimeError('Source reference identity/stat mismatch')
 wal=pathlib.Path(str(source)+'-wal')
 if wal.exists() and wal.stat().st_size:raise RuntimeError('Nonempty WAL: cannot attest only DB bytes')
 started=time.monotonic();last=0.;done=0;digest=hashlib.sha256()
 def update(status):
  elapsed=time.monotonic()-started;write(checkpoint,{'pid':os.getpid(),'status':status,'phase':'FULL_SOURCE_SHA256','bytes_processed':done,'total_bytes':before[0],'bytes_per_second':done/max(elapsed,.001),'percent':100*done/before[0],'elapsed_seconds':elapsed,'updated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
 update('RUNNING')
 try:
  with source.open('rb') as stream:
   while chunk:=stream.read(4*1024*1024):
    digest.update(chunk);done+=len(chunk)
    if time.monotonic()-last>2:update('RUNNING');last=time.monotonic()
  actual=digest.hexdigest();after=(source.stat().st_size,source.stat().st_mtime_ns)
  code={n:hashlib.sha256((pathlib.Path(__file__).parent/n).read_bytes()).hexdigest()==manifest['code_files'][n] for n in ('audit_next.py','acceleration.py','sqlite_tuning.py','tuned_review.py')}
  code['quality.py']=hashlib.sha256(pathlib.Path(quality.__file__).read_bytes()).hexdigest()==manifest['quality_sha256']
  audit=json.loads((review/'AUDIT_NEXT_REPORT.json').read_text());code['collection_code']=code_version()==audit['SESSION']['code_version']
  checks={'sha256_matches_reference':actual==ref['source_sha256'],'source_stat_unchanged':before==after,'source_matches_review_stat':list(before)==manifest['source_stat_before'],'complete_read':done==before[0],'wal_empty':not wal.exists() or wal.stat().st_size==0,'code_hashes':code}
  okay=all(v for k,v in checks.items() if k!='code_hashes') and all(code.values())
  result={'status':'PASS' if okay else 'FAIL','source':str(source),'source_sha256':actual,'expected_sha256':ref['source_sha256'],'reference_manifest':str(reference),'reference_manifest_sha256':hashlib.sha256(reference.read_bytes()).hexdigest(),'checks':checks,'duration_seconds':time.monotonic()-started,'note':'Attests completed auditor reuse and unchanged source; does not replace integrity, FK, quality or replay checks.'}
  with (review/'SOURCE_HASH_VERIFICATION.json').open('x') as f:json.dump(result,f,indent=2)
  update('COMPLETE');return result
 except BaseException as exc:
  update('ERROR');raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--review',required=True,type=pathlib.Path);p.add_argument('--reference',required=True,type=pathlib.Path);a=p.parse_args();print(json.dumps(verify(a.review,a.reference)))
