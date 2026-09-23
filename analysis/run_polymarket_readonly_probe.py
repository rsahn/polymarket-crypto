import asyncio,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"backend"))
from app.live.polymarket_readonly import PolymarketReadOnly
async def run():
 p=PolymarketReadOnly()
 try:print(json.dumps(await p.connect(),indent=2))
 finally:await p.close()
if __name__=="__main__":asyncio.run(run())
