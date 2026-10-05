"""Offline verifier for this exact compiled implementation and fixed historical interval.

The attached source review supplies the semantic argument; this script checks its
bytecode binding, writer/caller inventory, mandatory emit shape and archived logs.
It is not a general Solidity formal verifier or a production gate replacement.
"""
import json
from pathlib import Path
from eth_abi import encode
from eth_utils import keccak
from scan_deposit_session_history import digest
from close_session_history_gaps import IMPL, BEACON, WALLET, START, END, validate

BASE=Path(__file__).resolve().parent
SOURCES=BASE/'session_contract_sources_20261003'

def walk(node):
    if isinstance(node,dict):
        yield node
        for value in node.values():yield from walk(value)
    elif isinstance(node,list):
        for value in node:yield from walk(value)

def bind_runtime(evm, ast_nodes, address, onchain):
    bytecode=bytearray.fromhex(evm['object'])
    values={'_cachedThis':int(address,16).to_bytes(32,'big'),
        '_cachedChainId':(137).to_bytes(32,'big'),
        '_cachedNameHash':keccak(text='DepositWallet'),
        '_cachedVersionHash':keccak(text='1')}
    values['_cachedDomainSeparator']=keccak(encode(['bytes32','bytes32','bytes32','uint256','address'],
        [keccak(text='EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)'),
         values['_cachedNameHash'],values['_cachedVersionHash'],137,address]))
    for identifier,refs in evm.get('immutableReferences',{}).items():
        name=ast_nodes[int(identifier)]['name']
        if name not in values:raise ValueError('UNREVIEWED_IMMUTABLE')
        for ref in refs:
            if ref['length']!=32:raise ValueError('IMMUTABLE_LENGTH')
            bytecode[ref['start']:ref['start']+32]=values[name]
    if evm.get('linkReferences'):raise ValueError('UNREVIEWED_LINKED_LIBRARY')
    if '0x'+bytecode.hex()!=onchain:raise ValueError('LOCAL_RECOMPILATION_MISMATCH')
    return '0x'+keccak(bytes(bytecode)).hex()

def verify_writers(compiler):
    contracts={n['id']:(path,n) for path,v in compiler['sources'].items()
        for n in v['ast']['nodes'] if n['nodeType']=='ContractDefinition'}
    dw=next(n for path,n in contracts.values() if n['name']=='DepositWallet')
    bases=[contracts[i] for i in dw['linearizedBaseContracts']]
    writers=[];functions={};calls={}
    for path,contract in bases:
        for node in contract['nodes']:
            if node['nodeType'] not in ('FunctionDefinition','ModifierDefinition'):continue
            functions[node['id']]=node
            ops=[n['functionName']['name'] for n in walk(node) if n.get('nodeType')=='YulFunctionCall']
            if any(op in ('delegatecall','callcode','selfdestruct') for op in ops):raise ValueError('ARBITRARY_STORAGE_PATH')
            if 'sstore' in ops:writers.append(dict(source=path,function=node['name'],writes=ops.count('sstore'),src=node['src']))
            for n in walk(node):
                if n.get('nodeType')=='FunctionCall':
                    ref=n.get('expression',{}).get('referencedDeclaration')
                    if ref is not None:calls.setdefault(ref,[]).append(node['name'])
    expected={'execute':1,'pause':1,'unpause':1,'_setSessionSigner':1,'_setPasskeySessionSigner':3,
        '_initializeOwner':1,'_setOwner':1,'_setPendingOwner':1,'_setPendingOwnerDeadline':1,
        '_incrementPendingOwnerNonce':1,'initializer':2,'reinitializer':2,'_disableInitializers':1}
    if {w['function']:w['writes'] for w in writers}!=expected or len(writers)!=len(expected):raise ValueError('WRITER_INVENTORY_CHANGED')
    paths={
        '_setSessionSigner':{'authorizeSessionSigner':'SessionSignerAuthorized','revokeSessionSigner':'SessionSignerRevoked','revokeSessionSignerEmergency':'SessionSignerRevokedEmergency'},
        '_setPasskeySessionSigner':{'authorizePasskeySessionSigner':'PasskeySessionSignerAuthorized','revokePasskeySessionSigner':'PasskeySessionSignerRevoked','revokePasskeySessionSignerEmergency':'PasskeySessionSignerRevokedEmergency'}}
    evidence=[]
    for setter,callers in paths.items():
        target=next(n for n in functions.values() if n['name']==setter)
        if sorted(calls.get(target['id'],[]))!=sorted(callers):raise ValueError('SETTER_CALLERS_CHANGED')
        for caller,event in callers.items():
            n=next(n for n in functions.values() if n['name']==caller)
            statements=n['body']['statements']
            # Setter must be a top-level statement immediately followed by the final emit.
            if len(statements)<2 or statements[-2].get('nodeType')!='ExpressionStatement' or statements[-2]['expression'].get('expression',{}).get('referencedDeclaration')!=target['id']:
                raise ValueError('SETTER_NOT_UNCONDITIONAL')
            emit=statements[-1]
            if emit.get('nodeType')!='EmitStatement' or emit['eventCall']['expression']['name']!=event:raise ValueError('MANDATORY_EVENT_MISSING')
            modifiers=[m['modifierName']['name'] for m in n['modifiers']]
            if modifiers!=(['onlyPaused','onlyOwner'] if 'Emergency' in caller else ['onlySelf']):raise ValueError('ACCESS_PATH_CHANGED')
            evidence.append(dict(function=caller,setter=setter,event=event,modifiers=modifiers,src=n['src']))
    return writers,evidence

def classify_events(rows,abi):
    events={}
    for row in abi:
        if row.get('type')=='event':
            signature=row['name']+'('+','.join(p['type'] for p in row['inputs'])+')'
            events['0x'+keccak(text=signature).hex()]=row['name']
    counts={}
    for row in rows:
        name=events.get(row['topics'][0])
        if name is None:raise ValueError('UNCLASSIFIED_WALLET_EVENT')
        counts[name]=counts.get(name,0)+1
    if any('SessionSigner' in name for name in counts):raise ValueError('HISTORICAL_SIGNER_EVENT_PRESENT')
    return counts

def verify_creation(trace,runtime):
    creates=[n for n in walk(trace) if n.get('type') in ('CREATE','CREATE2') and n.get('to','').lower()==WALLET]
    if len(creates)!=1:raise ValueError('GENESIS_CREATE_COUNT')
    create=creates[0]
    # This 35-byte constructor CODECOPYs runtime, writes only the beacon slot,
    # then RETURNs. No arbitrary constructor/delegatecall storage initialization.
    prefix='61'+(len(runtime[2:])//2).to_bytes(2,'big').hex()+'3d8160233d3973'+BEACON[2:]+'60195155f3'
    if create.get('error') or create['type']!='CREATE2' or create['from'].lower()!='0x00000000000fb5c9adea0298d729a0cb3823cc07' or create['input']!='0x'+prefix+runtime[2:]:
        raise ValueError('GENESIS_INITCODE_MISMATCH')
    if create.get('output')!=runtime:raise ValueError('GENESIS_RUNTIME_MISMATCH')
    return dict(type='CREATE2',initcode_keccak256='0x'+keccak(bytes.fromhex(create['input'][2:])).hex(),
        constructor_storage_writes='Only ERC1967 beacon slot; session mappings initially zero')

def main():
    compiler=json.loads((SOURCES/'local_solc_output.json').read_text(encoding='utf-8'))
    ast_nodes={n['id']:n for n in walk(compiler['sources']) if 'id' in n and 'nodeType' in n}
    records=json.loads((BASE/'session_beacon_history_20261003/code_records.json').read_text())
    bindings=[]
    for name,address in [('DepositWallet',IMPL),('DepositWalletBeacon',BEACON)]:
        build=compiler if name=='DepositWallet' else json.loads((SOURCES/'local_beacon_solc_output.json').read_text(encoding='utf-8'))
        evm=build['contracts']['src/'+name+'.sol'][name]['evm']['deployedBytecode']
        for record in records:
            if record['address']==address:
                bindings.append(dict(contract=name,block=record['block'],keccak256=bind_runtime(evm,ast_nodes,address,record['code'])))
    if len(bindings)!=4:raise ValueError('CODE_BOUNDARIES')
    writers,paths=verify_writers(compiler)
    beacon=json.loads((BASE/'session_beacon_history_20261003/supplement_report.json').read_text())
    if not beacon['range_coverage_complete'] or beacon['logs']:raise ValueError('BEACON_HISTORY_REQUIRES_REVIEW')
    proxy=json.loads((SOURCES/'proxy_binding.json').read_text())
    for record in proxy:
        reads=record['reads']
        if reads['beacon_slot']!='0x'+BEACON[2:].rjust(64,'0') or int(reads['implementation_slot'],16)!=0 or int(reads['pinnedImplementation(address)'],16)!=0:
            raise ValueError('PROXY_OR_PIN_BINDING')
        if reads['implementation()']!='0x'+IMPL[2:].rjust(64,'0'):raise ValueError('WALLET_SPECIFIC_IMPLEMENTATION')
    walletcodes=[r['code'] for r in records if r['address']==WALLET]
    template='363d3d373d3d363d602036600436635c60da1b60e01b36527fa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50545afa5036515af43d6000803e604d573d6000fd5b3d6000f3'
    if len(walletcodes)!=2 or walletcodes[0]!=walletcodes[1] or not walletcodes[0].startswith('0x'+template) or len(walletcodes[0])!=2+len(template)+128:
        raise ValueError('NATIVE_BEACON_PROXY_TEMPLATE')
    creation=verify_creation(json.loads((SOURCES/'genesis_call_trace.json').read_text()),walletcodes[0])
    source=json.loads((SOURCES/'sourcify_impl.txt').read_text(encoding='utf-8'))
    rows=[];cursor=START
    files=sorted((BASE/'session_history_tenderly_20261003').glob('range_*.json'))
    for file in files:
        item=json.loads(file.read_text());lo,hi=item['from_block'],item['to_block']
        if lo!=cursor:raise ValueError('PRIMARY_GAP')
        rows.extend(validate(item,lo,hi,WALLET));cursor=hi+1
    tail=json.loads((BASE/'session_history_tail_20261003.json').read_text())
    if cursor!=tail['from_block'] or tail['to_block']!=END or digest(tail['logs'])!=tail['digest']:raise ValueError('TAIL_GAP')
    rows.extend(validate(dict(from_block=tail['from_block'],to_block=tail['to_block'],logs=tail['logs'],sha256=tail['digest']),tail['from_block'],END,WALLET))
    counts=classify_events(rows,source['abi'])
    original=json.loads((BASE/'session_history_tenderly_20261003/report.json').read_text())
    if original.get('code_onset_verified') is not True or original['start_block']!=START:
        raise ValueError('GENESIS_BOUNDARY_UNPROVEN')
    owner_topic='0x'+keccak(text='OwnershipTransferred(address,address)').hex()
    owner_rows=[r for r in rows if r['topics'][0]==owner_topic]
    if len(owner_rows)!=1 or int(owner_rows[0]['blockNumber'],16)!=START or owner_rows[0]['topics'][1]!='0x'+'00'*32 or owner_rows[0]['topics'][2].lower()!='0x'+'9348efd557a09e644795c8f114bcf0bef86f203a'.rjust(64,'0'):
        raise ValueError('OWNER_GENESIS_BINDING')
    receipts=json.loads((BASE/'session_history_tenderly_20261003/receipts.json').read_text())
    receipt=receipts.get(owner_rows[0]['transactionHash'])
    if not receipt or receipt['status']!='0x1' or receipt['blockHash']!=owner_rows[0]['blockHash']:
        raise ValueError('GENESIS_RECEIPT')
    slots={name:'0x'+(int.from_bytes(keccak(text='DepositWallet.'+name),'big')-1).to_bytes(32,'big').hex()
        for name in ('sessionSignerAuthorizedUntil','passkeySessionSigner','nonce','paused','owner','pendingOwner','pendingOwnerDeadline','pendingOwnerNonce')}
    report=dict(wallet=WALLET,from_block=START,to_block=END,
        all_session_signer_storage_mutation_paths_covered=True,historical_zero_signers_proven=True,
        proof_scope='On-chain secp256k1 and P-256 authorizations in the fixed interval; not off-chain pending authorizations or a current-account certificate.',
        implementation_count=1,upgrade_events=0,pin_events=0,bindings=bindings,slots=slots,
        mapping_layout='secp: keccak256(abi.encode(address, base)); passkey: keccak256(abi.encode(bytes32, base)) plus 0=x,1=y,2=validUntil',
        writers=writers,session_paths=paths,wallet_events=counts,
        passkey_events_checked=True,source_sha256=digest(source['sources']),
        genesis_creation=creation,
        assumptions=['Canonical RPC log responses and finalized anchor are truthful.',
            'EVM execution and Solidity compiler semantics; collision/preimage resistance of keccak256.',
            'No claim about off-chain registry records, unsubmitted owner signatures or blocks after the stated anchor.'],
        review='SESSION_STORAGE_PATH_PROOF.txt',read_only=True)
    (BASE/'session_storage_path_proof.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
