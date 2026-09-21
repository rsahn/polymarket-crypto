import asyncio,json,os,time
from pathlib import Path
p=Path(__file__).parent
async def main():
    (p/'synthetic_ready.json').write_text(json.dumps({'pid':os.getpid()}))
    try:
        await asyncio.sleep(120)
    finally:
        await asyncio.sleep(.1)
        (p/'synthetic_closed.json').write_text(json.dumps({'finally_executed':True,'time':time.time()}))
try:
    asyncio.run(main())
except KeyboardInterrupt:
    (p/'synthetic_interrupted.json').write_text(json.dumps({'KeyboardInterrupt':True}))
