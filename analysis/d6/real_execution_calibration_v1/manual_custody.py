"""Manual requesting-owner acceptance. Never auto-accept, trade, or sign an order.
Trust boundary: owner-only Windows filesystem + explicit operator terminal action;
not cryptographic nonrepudiation against another process running as that same user.
"""
import asyncio,json,os,sys,time,secrets,subprocess
from pathlib import Path
from .core import digest,encoded

def private_acl(path,sid):
    command="$ErrorActionPreference='Stop'; $p=([Console]::In.ReadToEnd() | ConvertFrom-Json); $a=Get-Acl -LiteralPath $p; @{owner=$a.GetOwner([System.Security.Principal.SecurityIdentifier]).Value; rules=@($a.GetAccessRules($true,$true,[System.Security.Principal.SecurityIdentifier]) | ForEach-Object { @{sid=$_.IdentityReference.Value; type=$_.AccessControlType.ToString(); rights=[int]$_.FileSystemRights} })} | ConvertTo-Json -Depth 4"
    result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',command],input=json.dumps(str(path)),capture_output=True,text=True,timeout=15)
    if result.returncode:raise ValueError('CUSTODY_ACL_UNAVAILABLE')
    value=json.loads(result.stdout)
    if value['owner']!=sid or not value['rules'] or any(r['sid']!=sid or r['type']!='Allow' or r['rights']!=2032127 for r in value['rules']):raise ValueError('CUSTODY_ACL_INVALID')

def no_links(path):
    for p in (path,*path.parents):
        if p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()):raise ValueError('CUSTODY_REPARSE_POINT')

def read_document(path):
    no_links(path)
    with path.open('rb') as f:raw=f.read(1024**2+1)
    if len(raw)>1024**2:raise ValueError('CUSTODY_DOCUMENT_BOUND')
    def unique(items):
        d={}
        for k,v in items:
            if k in d:raise ValueError('DUPLICATE_CUSTODY_FIELD')
            d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=unique)

def write_document(path,value):
    no_links(path);data=(encoded(value)+'\n').encode()
    if len(data)>1024**2:raise ValueError('CUSTODY_DOCUMENT_BOUND')
    with path.open('xb',buffering=0) as f:
        view=memoryview(data)
        while view:
            n=f.write(view)
            if not n:raise OSError('SHORT_WRITE')
            view=view[n:]
        os.fsync(f.fileno())

class ManualCustodyChannel:
    owner='requesting-owner'
    def __init__(self,directory,*,clock=lambda:time.time_ns()//1000000,platform=None,acl=private_acl):
        if platform is None:
            from app.live.l2_windows_storage import WindowsProtection
            platform=WindowsProtection()
        self.directory=Path(directory).absolute();self.clock=clock;self.sid=platform.sid;self.acl=acl
        no_links(self.directory)
        if not self.directory.exists():platform.create_private_directory(self.directory)
        acl(self.directory,self.sid)
    def challenge(self,request):
        if request['exposure_digest']!=digest(request['exposure']) or request['exposure_revision']!=request['exposure_digest']:raise ValueError('CUSTODY_EXPOSURE_BINDING')
        key=digest(request);path=self.directory/(key+'.challenge.json')
        if not path.exists():
            write_document(path,dict(schema='manual-custody/v1',challenge_id=key,nonce=secrets.token_hex(16),owner=self.owner,owner_sid=self.sid,created_ms=self.clock(),valid_until_ms=self.clock()+600000,request=request,scope='ALL_LISTED_EXPOSURE_INTENTS_UNKNOWNS_AND_FUTURE_RESULTS',acceptance_required=True))
        value=read_document(path)
        active=self.directory/'active-challenge.json'
        if not active.exists() or read_document(active).get('challenge_id')!=key:
            temp=self.directory/(key+'.pointer-'+secrets.token_hex(4))
            write_document(temp,dict(challenge_id=key,exposure_digest=request['exposure_digest']))
            no_links(active);os.replace(temp,active)
        if value['request']!=request or value['owner_sid']!=self.sid:raise ValueError('CUSTODY_CHALLENGE_CHANGED')
        return value
    def request_expired(self,request):
        key=digest(request);path=self.directory/(key+'.challenge.json')
        return path.exists() and not (self.directory/(key+'.receipt.json')).exists() and self.clock()>read_document(path)['valid_until_ms']
    async def accept(self,request):
        challenge=self.challenge(request);path=self.directory/(challenge['challenge_id']+'.receipt.json')
        if not path.exists():return None
        return read_document(path)
    def accept_interactively(self,challenge_id):
        # Only the requesting human runs this command. Agent consent is NOT a receipt.
        if not sys.stdin.isatty():raise ValueError('OPERATOR_INTERACTIVE_TERMINAL_REQUIRED')
        if len(challenge_id)!=64 or any(c not in '0123456789abcdef' for c in challenge_id):raise ValueError('CHALLENGE_ID')
        path=self.directory/(challenge_id+'.challenge.json');self.acl(path,self.sid);c=read_document(path)
        if c['challenge_id']!=challenge_id or c['owner_sid']!=self.sid or self.clock()>c['valid_until_ms']:raise ValueError('STALE_OR_FOREIGN_CHALLENGE')
        r=c['request']
        if digest(r)!=challenge_id or digest(r['exposure'])!=r['exposure_digest']:raise ValueError('CHALLENGE_TAMPERED')
        print(encoded(c))
        phrase='ACCEPT CUSTODY '+r['experiment_id']+' '+r['exposure_digest']+' '+c['nonce']
        print('Review all exposure, local intents, unknown results and future corrections. Assume monitoring/recovery responsibility outside the bot process. Type exactly: '+phrase)
        if input()!=phrase:raise ValueError('OPERATOR_DID_NOT_ACCEPT')
        if self.clock()>c['valid_until_ms']:raise ValueError('CHALLENGE_EXPIRED')
        # Re-read after user input; never accept changed challenge content.
        if read_document(path)!=c or read_document(self.directory/'active-challenge.json')['challenge_id']!=challenge_id:raise ValueError('CHALLENGE_CHANGED_DURING_ACCEPTANCE')
        receipt={k:r[k] for k in ('account','experiment_id','exposure_digest','journal_sequence')}
        receipt.update(owner=self.owner,receipt_id=challenge_id,challenge_id=challenge_id,challenge_digest=digest(c),owner_sid=self.sid,accepted_ms=self.clock(),future_result_client_ids=sorted(r['exposure']['orders']),acceptance_mode='EXPLICIT_OPERATOR_TTY',responsibility=c['scope'])
        write_document(self.directory/(challenge_id+'.receipt.json'),receipt)
        return receipt

class ManualReceiptAuthority:
    def __init__(self,channel):self.channel=channel
    async def verify_durable(self,receipt):
        task=asyncio.create_task(self._verify_durable(receipt))
        while True:
            try:return await asyncio.shield(task)
            except asyncio.CancelledError:
                # Keep ACL subprocess/thread work owned until its fixed timeout.
                if task.done():return task.result()
    async def _verify_durable(self,receipt):
        try:
            key=receipt['challenge_id']
            if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):return False
            cp=self.channel.directory/(key+'.challenge.json');rp=self.channel.directory/(key+'.receipt.json')
            await asyncio.to_thread(self.channel.acl,cp,self.channel.sid);await asyncio.to_thread(self.channel.acl,rp,self.channel.sid)
            c=read_document(cp);r=c['request'];stored=read_document(rp)
            return (stored==receipt and receipt['receipt_id']==key==digest(r) and receipt['challenge_digest']==digest(c) and receipt['owner_sid']==c['owner_sid']==self.channel.sid and receipt['owner']==c['owner']==self.channel.owner and receipt['acceptance_mode']=='EXPLICIT_OPERATOR_TTY' and receipt['responsibility']==c['scope'] and type(receipt['accepted_ms']) is int and c['created_ms']<=receipt['accepted_ms']<=c['valid_until_ms'] and all(receipt[k]==r[k] for k in ('account','experiment_id','exposure_digest','journal_sequence')) and sorted(receipt['future_result_client_ids'])==sorted(r['exposure']['orders']) and digest(r['exposure'])==r['exposure_digest'])
        except (KeyError,ValueError,OSError,TypeError,subprocess.SubprocessError):return False

class ManualReceiptVerifier:
    """Durable manual acceptance covers the exact state/future results until transfer.
    Challenge has an acceptance deadline; responsibility does not expire in 5 s.
    """
    def __init__(self,authority):self.authority=authority;self.owner=authority.channel.owner
    async def verify(self,receipt,request):
        if not isinstance(receipt,dict):return False
        if receipt.get('challenge_id')!=digest(request):return False
        if any(receipt.get(k)!=request[k] for k in ('account','experiment_id','exposure_digest','journal_sequence')):return False
        if receipt.get('owner')!=self.owner or type(receipt.get('accepted_ms')) is not int or receipt['accepted_ms']>self.authority.channel.clock():return False
        if await self.authority.verify_durable(receipt) is not True:return False
        return True  # idempotent verification; CustodyStateStore owns transfer state

def main():
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'backend'))
    import argparse
    parser=argparse.ArgumentParser(description='Manual owner custody acceptance ONLY; no trading APIs.')
    parser.add_argument('--directory',required=True)
    mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--accept');mode.add_argument('--watch',action='store_true');args=parser.parse_args()
    channel=ManualCustodyChannel(args.directory)
    if args.watch:
        if not sys.stdin.isatty():raise ValueError('OPERATOR_INTERACTIVE_TERMINAL_REQUIRED')
        last=None
        print('WATCH ONLY. No acceptance is automatic. Keep this terminal outside the bot process.')
        while True:
            path=channel.directory/'active-challenge.json'
            if path.exists():
                active=read_document(path);key=active['challenge_id']
                if key!=last:
                    print('New custody request: '+key+' ; review with --accept '+key);last=key
            time.sleep(2)
    else:
        receipt=channel.accept_interactively(args.accept)
        print('Custody acceptance durably recorded: '+receipt['receipt_id'])

if __name__=='__main__':main()
