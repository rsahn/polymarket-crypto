from app.live.clob_transport import extract_order_id,normalize_order_status

def test_extract_order_id():
 assert extract_order_id({"response":{"order_id":"abc"}})=="abc"
 assert extract_order_id({"response":{}}) is None

def test_unknown_status_fails_closed():
 x=normalize_order_status({"response":{"foo":"bar"}})
 assert x["known"] is False

def test_status_sizes():
 x=normalize_order_status({"response":{"status":"LIVE","original_size":"10","size_matched":"4"}})
 assert x["known"] and x["filled_size"]==4 and x["remaining_size"]==6
