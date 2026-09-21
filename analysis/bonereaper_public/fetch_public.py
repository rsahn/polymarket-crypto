from pathlib import Path
import urllib.request,urllib.error,urllib.parse,json,datetime,hashlib,time,re
ROOT=Path(__file__).resolve().parent
RAW=ROOT/'raw'; RAW.mkdir(exist_ok=True)
ADDRESS='0xcd30457c790d8b35a08bcf3f894ad6bb52bc2dd0'
def fetch(label,url,params=None):
 if params: url+='?'+urllib.parse.urlencode(params)
 path=RAW/(label+'.body')
 if path.exists(): return path.read_bytes()
 for attempt in range(3):
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json,text/html'})
   with urllib.request.urlopen(req,timeout=30) as response: body=response.read(); status=response.status; headers=dict(response.headers)
   break
  except urllib.error.HTTPError as e:
   body=e.read();status=e.code;headers=dict(e.headers)
   if e.code not in (429,500,502,503,504):break
   time.sleep(2+attempt*3)
 meta={'url':url,'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':status,'headers':headers,'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)}
 path.write_bytes(body); (RAW/(label+'.meta.json')).write_text(json.dumps(meta,indent=2),encoding='utf-8')
 if status!=200: print('HTTP',status,label,flush=True)
 return body
def get(label,url,params=None):return json.loads(fetch(label,url,params))
if __name__=='__main__':
 html=fetch('profile','https://polymarket.com/fr/@bonereaper').decode()
 matches=[]
 for m in re.finditer(ADDRESS,html,re.I):matches.append(html[max(0,m.start()-250):m.end()+250])
 (ROOT/'identity_excerpts.json').write_text(json.dumps(matches,indent=2),encoding='utf-8')
 print('address matches',len(matches)); print(json.dumps(matches[:3])[:3500])
 profile=get('gamma_profile','https://gamma-api.polymarket.com/public-profile',{'address':ADDRESS})
 print('gamma',profile)
 rows=get('probe_activity','https://data-api.polymarket.com/activity',{'user':ADDRESS,'limit':500})
 print('probe',len(rows),rows[0]['timestamp'],rows[-1]['timestamp']);print('types',sorted(set(x['type'] for x in rows)))
 start=int(datetime.datetime(2026,9,19,tzinfo=datetime.timezone.utc).timestamp());end=start+86400-1
 rows=get('probe_day','https://data-api.polymarket.com/activity',{'user':ADDRESS,'limit':500,'start':start,'end':end,'sortDirection':'ASC'})
 print('day',len(rows),rows[0]['timestamp'] if rows else None,rows[-1]['timestamp'] if rows else None)
