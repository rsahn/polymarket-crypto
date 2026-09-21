"""Read-only public NTP probes. Never changes the Windows clock."""
import socket,struct,time,subprocess,datetime
HOSTS=('time.windows.com','time.cloudflare.com');EPOCH=2208988800

def probe(host):
 request=bytearray(48);request[0]=0x23;t1=time.time();ntp=t1+EPOCH
 request[40:48]=struct.pack('!II',int(ntp),int((ntp-int(ntp))*2**32));mono=time.monotonic()
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
  sock.settimeout(4);sock.sendto(request,(host,123));response,address=sock.recvfrom(512);t4=time.time();elapsed=time.monotonic()-mono
 if len(response)<48 or response[24:32]!=request[40:48] or response[0]&7!=4 or response[0]>>6==3 or not 1<=response[1]<=15:raise RuntimeError('INVALID_NTP_REPLY')
 def stamp(i):
  sec,frac=struct.unpack('!II',response[i:i+8]);return sec-EPOCH+frac/2**32
 t2,t3=stamp(32),stamp(40)
 if abs((t4-t1)-elapsed)>.05:raise RuntimeError('CLOCK_JUMP_DURING_PROBE')
 return {'host':host,'server_ip':address[0],'t1':t1,'t2':t2,'t3':t3,'t4':t4,'offset_ms':((t2-t1)+(t3-t4))*500,'delay_ms':((t4-t1)-(t3-t2))*1000,'raw_response_hex':response.hex()}

def check():
 service=subprocess.run(['powershell','-NoProfile','-Command','(Get-Service -Name W32Time).Status.ToString()'],capture_output=True,text=True,timeout=10)
 result={'observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'w32time':service.stdout.strip(),'probes':[],'passed':False}
 for _ in range(2):
  for host in HOSTS:
   try:result['probes'].append(probe(host))
   except Exception as exc:result['probes'].append({'host':host,'error':repr(exc)})
  time.sleep(.25)
 result['passed']=result['w32time']=='Running' and len(result['probes'])==4 and all('offset_ms' in p and abs(p['offset_ms'])<=100 for p in result['probes'])
 return result
