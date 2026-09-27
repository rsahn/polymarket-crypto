"""Read only explicitly public selectors; never load dotenv into the environment."""
import os,re
from pathlib import Path

KEYS={'POLYMARKET_WALLET_ADDRESS','READONLY_SIGNER_ADDRESS','READONLY_SIGNATURE_TYPE','REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED','MARKET_SLUG','POLYMARKET_MARKET_SLUG','CONDITION_ID','TOKEN_UP','TOKEN_DOWN'}
def inspect_selection(root,environ=None,account_choice=None):
    environ=os.environ if environ is None else environ
    found={};problems=[]
    def add(k,v,source):
        v=v.strip().strip('"'+chr(39))
        if k in ('REAL_ORDERS_ENABLED','LIVE_EXECUTION_ARMED'):
            if v.lower()!='false':problems.append('LIVE_FLAG_NOT_FALSE:'+source+':'+k)
        elif 'ADDRESS' in k:
            if not re.fullmatch(r'0x[0-9a-fA-F]{40}',v):problems.append('INVALID_PUBLIC_ADDRESS:'+k);return
            v=v.lower()
        elif k=='READONLY_SIGNATURE_TYPE':
            if v not in ('0','1','2','3'):problems.append('INVALID_SIGNATURE_TYPE');return
        elif k=='CONDITION_ID':
            if not re.fullmatch(r'0x[0-9a-fA-F]{64}',v):problems.append('INVALID_CONDITION');return
        elif k.startswith('TOKEN_'):
            if not re.fullmatch(r'[0-9]{1,78}',v):problems.append('INVALID_TOKEN');return
        elif not re.fullmatch(r'btc-updown-5m-[0-9]{10}',v):problems.append('NON_V1_MARKET_SELECTOR');return
        found.setdefault(k,[]).append({'source':source,'value':v})
    path=Path(root)/'.env'
    if path.exists():
        with path.open(encoding='utf-8-sig') as handle:
            for line in handle:
                k=line.partition('=')[0].strip()
                if k in KEYS:add(k,line.partition('=')[2],'.env')
    for k in KEYS:
        if k in environ:add(k,environ[k],'process')
    for k,items in found.items():
        if len({i['value'] for i in items})>1:problems.append('CONFLICTING_SELECTOR:'+k)
    wallets={r['value'] for r in found.get('POLYMARKET_WALLET_ADDRESS',[])}
    from app.live.l2_existing_reader import EXPECTED
    from app.live.genesis_ledger import expected_wallet
    allowed_accounts={EXPECTED.lower(),expected_wallet().lower()}
    if any(wallet not in allowed_accounts for wallet in wallets):problems.append('CONFIG_WALLET_NOT_BOUND_TO_EXISTING_SIGNER')
    signers={r['value'] for r in found.get('READONLY_SIGNER_ADDRESS',[])}
    if signers and signers!={EXPECTED.lower()}:problems.append('CONFIG_SIGNER_DIFFERS_FROM_EXISTING_CREDENTIAL_SIGNER')
    if not wallets:problems.append('NO_EXPLICIT_ACCOUNT_SELECTOR')
    slugs={r['value'] for k in ('MARKET_SLUG','POLYMARKET_MARKET_SLUG') for r in found.get(k,[])}
    if len(slugs)>1:problems.append('CONFLICTING_MARKET_SLUGS')
    runtime_account=None
    genesis=Path(root)/'runtime'/'d6_genesis.db'
    if genesis.exists():
        try:
            from app.live.genesis_ledger import read_genesis
            prior=read_genesis(genesis)
            runtime_account=dict(source='runtime/d6_genesis.db (validated read-only)',wallet=prior['snapshot']['wallet'].lower(),snapshot_digest=prior.get('snapshot_sha256'),phase=prior['phase'])
            if wallets!={runtime_account['wallet']}:problems.append('CONFIG_EOA_AND_CANONICAL_D6_WALLET_CONFLICT_REQUIRES_OWNER_CHOICE')
        except Exception:problems.append('CANONICAL_D6_ACCOUNT_SELECTION_UNVERIFIED')
    selected_wallet=next(iter(wallets)) if len(wallets)==1 else None
    if account_choice not in (None,'configured-eoa','canonical-d6'):problems.append('INVALID_EXPLICIT_ACCOUNT_CHOICE')
    if account_choice=='canonical-d6':
        if runtime_account:selected_wallet=runtime_account['wallet']
        else:problems.append('CANONICAL_ACCOUNT_UNAVAILABLE')
    if account_choice in ('configured-eoa','canonical-d6'):
        problems=[p for p in problems if p!='CONFIG_EOA_AND_CANONICAL_D6_WALLET_CONFLICT_REQUIRES_OWNER_CHOICE']
    expected_signature='0' if selected_wallet==EXPECTED.lower() else '3'
    if any(r['value']!=expected_signature for r in found.get('READONLY_SIGNATURE_TYPE',[])):problems.append('CONFIG_SIGNATURE_TYPE_CONFLICT_WITH_SELECTED_ACCOUNT')
    return dict(selectors=found,canonical_runtime_account=runtime_account,selected_wallet=selected_wallet,explicit_read_only_account_choice=account_choice,blockers=problems,existing_storage_signer=EXPECTED.lower(),market_policy='V1_BTC_5M_CURRENT_SLOT_FROM_EXISTING_QUALIFY_POST_GENESIS',selection_ready=not problems)
