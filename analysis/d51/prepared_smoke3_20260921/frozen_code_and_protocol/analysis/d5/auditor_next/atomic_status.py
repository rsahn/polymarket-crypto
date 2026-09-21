"""Atomic JSON status writes with bounded retries for transient Windows reader locks."""
import json,time

def write_status(path,value):
 tmp=path.with_suffix('.tmp')
 tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
 for attempt in range(30):
  try:
   tmp.replace(path)
   return
  except PermissionError:
   if attempt==29:raise
   time.sleep(.1)

def detail_mapping(value):
 return value if isinstance(value,dict) else {}
