"""Read-only NTP evidence. RFC5905 timestamps; never disciplines the clock."""
import datetime
import json
import locale
import re
import socket
import struct
import subprocess
import time
import unicodedata

EPOCH=2208988800

def stamp(value):
    whole=int(value)+EPOCH
    return struct.pack('!II',whole,int((value-int(value))*2**32))

def unpack(value):
    sec,frac=struct.unpack('!II',value)
    return sec-EPOCH+frac/2**32

def decode_packet(packet, request_stamp, sent, received, elapsed):
    if len(packet)<48: raise ValueError('Short NTP response')
    leap,version,mode=packet[0]>>6,(packet[0]>>3)&7,packet[0]&7
    if leap==3 or version not in (3,4) or mode!=4 or not 1<=packet[1]<=15:
        raise ValueError('Unsynchronized or invalid NTP response')
    if packet[24:32]!=request_stamp: raise ValueError('Origin timestamp mismatch')
    t2,t3=unpack(packet[32:40]),unpack(packet[40:48])
    if t2<=0 or t3<t2: raise ValueError('Invalid server timestamps')
    delay=(received-sent)-(t3-t2)
    if delay < -0.001 or delay>1 or abs((received-sent)-elapsed)>0.01:
        raise ValueError('Invalid delay or local clock step')
    return dict(offset_ms=((t2-sent)+(t3-received))*500,
                delay_ms=delay*1000,dispersion_ms=struct.unpack('!I',packet[8:12])[0]/65536*1000,
                root_delay_ms=struct.unpack('!i',packet[4:8])[0]/65536*1000,
                stratum=packet[1],leap=leap,reference_timestamp=unpack(packet[16:24]),
                t1=sent,t2=t2,t3=t3,t4=received,monotonic_elapsed_seconds=elapsed)

def sample(server):
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.settimeout(4);sock.connect((server,123)); peer=sock.getpeername()
        mono=time.monotonic(); sent=time.time(); st=stamp(sent)
        request=bytes([0x23])+bytes(39)+st
        sock.send(request); packet=sock.recv(4096)
        received=time.time(); elapsed=time.monotonic()-mono
        result=dict(server=server,peer=peer,captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),request_hex=request.hex(),response_hex=packet.hex())
        result.update(decode_packet(packet,st,sent,received,elapsed));return result

def command(args):
    p=subprocess.run(args,capture_output=True,timeout=20)
    encoding='oem' if __import__('os').name=='nt' else locale.getpreferredencoding(False)
    return dict(command=args,exit_code=p.returncode,stdout=p.stdout.decode(encoding,errors='replace'),stderr=p.stderr.decode(encoding,errors='replace'),stdout_hex=p.stdout.hex())

def parse_w32time(text, service):
    normalized=''.join(c for c in unicodedata.normalize('NFKD',text) if not unicodedata.combining(c)).lower()
    result=dict(service=service,source=None,last_sync_error=None,last_sync_age_seconds=None,last_sync_raw=None)
    for line in normalized.splitlines():
        if ':' not in line: continue
        label,value=line.split(':',1); value=value.strip()
        if label.strip()=='source': result['source']=value
        if ('last successful sync time' in label or label.strip()=='heure de la derniere synchronisation reussie'): result['last_sync_raw']=value
        if ('last sync error' in label or 'erreur lors de la derniere synchronisation' in label):
            m=re.match(r'(\d+)',value)
            if m: result['last_sync_error']=int(m.group(1))
        if ('time since last good sync time' in label or 'duree ecoulee depuis' in label):
            m=re.match(r'([\d.,]+)',value)
            if m: result['last_sync_age_seconds']=float(m.group(1).replace(',','.'))
    return result

def snapshot():
    result=dict(captured_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),wall_ns=time.time_ns(),monotonic_ns=time.monotonic_ns(),references={})
    for name in ('time.windows.com','time.cloudflare.com'):
        row=dict(samples=[],errors=[],valid=True)
        for i in range(3):
            try: row['samples'].append(sample(name))
            except Exception as exc: row['errors'].append(str(exc)); row['valid']=False
            if i<2: time.sleep(1)
        result['references'][name]=row
    status=command(['w32tm','/query','/status','/verbose'])
    service=command(['powershell','-NoProfile','-Command','(Get-Service W32Time).Status.ToString()'])
    result['raw_w32time']=status;result['raw_service']=service
    result['w32time']=parse_w32time(status['stdout'],service['stdout'].strip())
    if status['exit_code'] or service['exit_code']: result['w32time']['query_failed']=True;result['w32time']['last_sync_error']=None
    return result
