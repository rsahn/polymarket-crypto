"""Bounded incoming CTF event discovery; does NOT prove global wallet coverage."""
from .collateral_onchain import CTF,uint_word


def scan_ctf(rpc,start,end,known,*,capture=None):
    from eth_utils import keccak
    from eth_abi import decode
    report={'complete':False,'status':'BLOCKED','contract':CTF,'from_block':start,'to_block':end,
            'global_coverage_proven':False,'scope':'CTF_INCOMING_EVENTS_REQUESTED_RANGE_ONLY'}
    try:
        if type(start) is not int or type(end) is not int or not 0<=start<=end or end-start>=50000:raise ValueError()
        window=getattr(rpc,'log_window',500)
        if type(window) is not int or not 1<=window<=500:raise ValueError()
        if rpc.call('eth_chainId',[])!='0x89':raise ValueError()
        block=hex(end);anchor=rpc.call('eth_getBlockByNumber',[block,False])
        if anchor['number']!=block:raise ValueError()
        code=rpc.call('eth_getCode',[CTF,block])
        if code in ('0x','0x00') or not code.startswith('0x'):raise ValueError()
        sigs=['0x'+keccak(text=x).hex() for x in ('TransferSingle(address,address,address,uint256,uint256)','TransferBatch(address,address,address,uint256[],uint256[])')]
        wallet_topic='0x'+rpc.wallet[2:].lower().rjust(64,'0');assets=set(known);seen=set()
        for low in range(start,end+1,window):
            high=min(low+window-1,end)
            rows=rpc.call('eth_getLogs',[{'address':CTF,'fromBlock':hex(low),'toBlock':hex(high),'topics':[sigs,None,None,wallet_topic]}])
            if not isinstance(rows,list) or len(rows)>=10000:raise ValueError()
            for row in rows:
                if row.get('removed') is not False or row['address'].lower()!=CTF.lower() or len(row['topics'])!=4 or row['topics'][3].lower()!=wallet_topic:raise ValueError()
                if not low<=int(row['blockNumber'],16)<=high:raise ValueError()
                key=(row['transactionHash'],row['logIndex'])
                if key in seen:raise ValueError()
                seen.add(key);raw=bytes.fromhex(row['data'][2:])
                if row['topics'][0]==sigs[0]:ids=[decode(['uint256','uint256'],raw)[0]]
                elif row['topics'][0]==sigs[1]:
                    ids,quantities=decode(['uint256[]','uint256[]'],raw)
                    if len(ids)!=len(quantities):raise ValueError()
                else:raise ValueError()
                assets.update(str(x) for x in ids)
                if len(assets)>10000:raise ValueError()
        nonzero=0;balances={}
        for token in sorted(assets):
            if not token.isdigit() or not 0<=int(token)<2**256:raise ValueError()
            data='0x00fdd58e'+rpc.wallet[2:].lower().rjust(64,'0')+hex(int(token))[2:].rjust(64,'0')
            raw=uint_word(rpc.call('eth_call',[{'to':CTF,'data':data},block]));balances[token]=str(raw);nonzero+=raw>0
        if rpc.call('eth_getBlockByNumber',[block,False])['hash']!=anchor['hash']:raise ValueError()
        if capture is not None:capture.update(balances=balances)
        report.update(status='PASS_SCOPED_READS',events_count=len(seen),assets_checked=len(assets),nonzero_assets=nonzero,
            discovered_outside_local_journal=len(assets-set(known)),block_hash=anchor['hash'],
            blockers=['DEPLOYMENT_START_AND_ARCHIVE_COMPLETENESS_NOT_ATTESTED','OTHER_POSITION_PROTOCOLS_NOT_COVERED','CREDENTIAL_ORDER_SCOPE_NOT_GLOBAL'])
    except Exception:report['reason']='CTF_READ_RANGE_SCHEMA_OR_CHAIN_FAILED'
    return report
