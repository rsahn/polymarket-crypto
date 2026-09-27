"""Interactive, local-only synthetic custody drill. No production authority registration."""
import argparse,asyncio,sys,time,secrets
from contextlib import contextmanager
from pathlib import Path
from .core import Journal,CalibrationLedger,digest
from .manual_custody import ManualCustodyChannel,ManualReceiptAuthority,ManualReceiptVerifier,read_document,write_document
PREFIX='DRILL-NO-MONEY-'
class DrillChannel(ManualCustodyChannel):
    owner='DRILL-OPERATOR-NOT-PRODUCTION'
    def challenge(self,request):
        if not request['experiment_id'].startswith(PREFIX) or request['account']!='DRILL-SYNTHETIC-ACCOUNT':raise ValueError('DRILL_ONLY')
        return super().challenge(request)
class DrillHost:
    def __init__(self,channel):
        self.channel=channel;self.directory=channel.directory;self.path=self.directory/'DRILL-state.json'
        self.verifier=ManualReceiptVerifier(ManualReceiptAuthority(channel))
    @contextmanager
    def lock(self):
        lock=self.directory/'DRILL-writer.lock'
        try:fd=lock.open('xb')
        except FileExistsError:raise ValueError('DRILL_WRITER_BUSY_OR_CRASH_LOCK_REVIEW')
        try:yield
        finally:fd.close();lock.unlink()
    def state(self):
        value=read_document(self.path)
        if value.get('schema')!='DRILL-STATE/1' or not value['experiment_id'].startswith(PREFIX):raise ValueError('DRILL_STATE')
        return value
    def save(self,value):
        import os
        tmp=self.directory/('DRILL-temp-'+secrets.token_hex(8));write_document(tmp,value);os.replace(tmp,self.path)
    def init(self):
        if self.path.exists():raise ValueError('DRILL_ALREADY_EXISTS')
        self.save(dict(schema='DRILL-STATE/1',experiment_id=PREFIX+secrets.token_hex(8),revision=0,status='UNACCEPTED',monitor_ticks=0))
    def request(self):
        s=self.state();exposure=dict(test_data_only=True,cash_currency='FICTIONAL',positions={'DRILL-TOKEN':str(s['revision']+1)},orders={'DRILL-UNKNOWN-INTENT':{'remote_id':None,'future_results':'UNKNOWN_SYNTHETIC'}},revision=s['revision'])
        h=digest(exposure)
        return dict(account='DRILL-SYNTHETIC-ACCOUNT',experiment_id=s['experiment_id'],exposure=exposure,exposure_digest=h,exposure_revision=h,journal_sequence=s['revision'])
    def change(self):
        with self.lock():
            s=self.state();s.update(revision=s['revision']+1,status='UNACCEPTED');self.save(s);return self.channel.challenge(self.request())
    async def tick(self):
        s=self.state();r=self.request();receipt=await self.channel.accept(r)
        valid=await self.verifier.verify(receipt,r)
        # Recheck revision after any asynchronous verification.
        with self.lock():
            if self.request()!=r:valid=False
            s=self.state();s['monitor_ticks']+=1;s['status']='DRILL_ACCEPTED_ONLY' if valid else 'UNACCEPTED';self.save(s)
            return s
    async def monitor(self):
        try:
            while True:
                print(await self.tick(),flush=True);await asyncio.sleep(2)
        finally:
            with self.lock():
                s=self.state();s['monitor_stopped']=True;self.save(s)

def main():
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'backend'))
    p=argparse.ArgumentParser(description='DRILL ONLY: synthetic, no money, no network')
    p.add_argument('--directory',required=True);p.add_argument('action',choices=['init','host','change','recover','accept']);p.add_argument('--challenge')
    a=p.parse_args()
    if not sys.stdin.isatty():raise ValueError('ACTUAL_OPERATOR_TTY_REQUIRED')
    if Path(a.directory).name!='DRILL-NO-MONEY':raise ValueError('DEDICATED_DRILL_DIRECTORY_REQUIRED')
    channel=DrillChannel(a.directory);host=DrillHost(channel)
    if a.action=='init':
        if input('Type CREATE SYNTHETIC DRILL (no real custody): ')!='CREATE SYNTHETIC DRILL':raise ValueError('NOT_CONFIRMED')
        host.init();print(channel.challenge(host.request()))
    elif a.action=='host':asyncio.run(host.monitor())
    elif a.action=='change':print(host.change())
    elif a.action=='recover':print(host.state());print(host.request());print('DRILL recovery only; never rearms or retries anything.')
    else:
        if a.challenge!=digest(host.request()):raise ValueError('STALE_DRILL_REQUEST')
        channel.accept_interactively(a.challenge)
if __name__=='__main__':main()
