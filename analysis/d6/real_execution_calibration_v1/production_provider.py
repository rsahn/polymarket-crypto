"""Read-only inbox from an independently operated signed-evidence producer.

The producer publishes complete JSON files by atomic rename. No credentials or
network routes are needed by this consumer. Files are never treated as trusted
until ProductionAuthority and all semantic validators accept their contents.
"""
import asyncio,json,hashlib,re
from pathlib import Path

class EvidenceInbox:
    MAX_BYTES=8*1024**2
    def __init__(self,directory):
        self.directory=Path(directory).resolve(strict=True)
        if not self.directory.is_dir():raise ValueError('EVIDENCE_DIRECTORY')
        if any((p/'.git').exists() for p in (self.directory,*self.directory.parents)):
            raise ValueError('EVIDENCE_INBOX_MUST_BE_OUTSIDE_GIT')
    def read(self,name):
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*\.json',name):raise ValueError('EVIDENCE_FILENAME')
        p=self.directory/name
        if p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()):raise ValueError('EVIDENCE_LINK')
        with p.open('rb') as f:raw=f.read(self.MAX_BYTES+1)
        if len(raw)>self.MAX_BYTES:raise ValueError('EVIDENCE_SIZE')
        def unique(pairs):
            result={}
            for key,value in pairs:
                if key in result:raise ValueError('DUPLICATE_EVIDENCE_KEY')
                result[key]=value
            return result
        return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda value:(_ for _ in ()).throw(ValueError('NONFINITE_EVIDENCE')))
    def qualification(self):return self.read('qualification.json')
    def baseline(self):return self.read('baseline.json')
    async def snapshot(self):return await asyncio.to_thread(self.read,'snapshot.json')
    async def execution(self,order_id):
        name='execution-'+hashlib.sha256(order_id.encode()).hexdigest()+'.json'
        while True:
            try:return await asyncio.to_thread(self.read,name)
            except FileNotFoundError:await asyncio.sleep(.05)  # source owns the 5s deadline
    async def next_market(self):
        spec=await asyncio.to_thread(self.read,'next_market.json')
        return spec,self.qualification
