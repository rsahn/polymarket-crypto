"""Reviewed additive provenance migration, NOT replacement of historical safety hash.
Original source must reconstruct byte-for-byte; only this post-update metadata delta is allowed.
No readiness, risk, BTC, genesis, strategy or order logic may change.
"""
import hashlib
NAME='backend/app/live/readonly_book_stream.py'
OLD='813005e2221209c97728e68a4ca8c47f7a863286c87f2eee0231cca6ccdd0441'
NEW='c116359e8e498752c4350956b60bd77c5c0bc454dd4dd75209cebfd996d7924c'
DELTA=("                    # Causal per-token metadata: never use another token or PONG receipt.\n"
       "                    self.books[token]['receive_ms']=received_ms\n"
       "                    self.books[token]['book_state_id']=hashlib.sha256(\n"
       "                        f'{self.condition}:{self.generation}:{token}:{self.events_seen}:{stamp}:{received_ms}'.encode()).hexdigest()\n").replace('\n','\r\n').encode()
BEFORE=b"                    self.update(token,list(b['bids'].items()),list(b['asks'].items()),stamp,self.generation)\r\n"
AFTER=b'                except ValueError as exc:\r\n'
def protected_match(name,data,expected):
    if hashlib.sha256(data).hexdigest()==expected:return True
    if name!=NAME or expected!=OLD or hashlib.sha256(data).hexdigest()!=NEW:return False
    if data.count(BEFORE+DELTA+AFTER)!=1:return False
    restored=data.replace(BEFORE+DELTA+AFTER,BEFORE+AFTER,1)
    return hashlib.sha256(restored).hexdigest()==expected
