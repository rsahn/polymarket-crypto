"""Public, offline request diagnostics: no credentials or client construction."""
from urllib.parse import urlencode
from polymarket._internal.actions.account import build_balance_allowance_request
from polymarket._internal.actions.data import list_positions_spec
from polymarket._internal.environment import PRODUCTION_CONFIG as env
from polymarket._internal.wallet import (classify_account,signature_type_for,
    derive_uups_deposit_wallet_address,derive_beacon_deposit_wallet_address)


def mask(address):return address[:6]+'...'+address[-4:]


def request_diagnostics(signer,wallet):
    identity=classify_account(signer=signer,wallet=wallet,config=env.wallet_derivation)
    current_type=signature_type_for(identity.wallet_type)
    path,current=build_balance_allowance_request(asset_type='COLLATERAL',signature_type=current_type)
    _,historical=build_balance_allowance_request(asset_type='COLLATERAL',signature_type=3)
    spec=list_positions_spec(user=wallet,full_history=True,include_archived=True,filter_type='TOKENS',filter_amount=0)
    params={**spec.base_params,'limit':100}
    public_params={k:(mask(v) if k=='user' else str(v).lower() if type(v) is bool else v) for k,v in params.items()}
    return {'environment':'production','chain_id':env.chain_id,'sdk_version':'0.11.0',
        'signer_masked':mask(signer),'configured_wallet_masked':mask(wallet),
        'balance_current':{'method':'GET','endpoint':path,'query':current,'wallet_kind':identity.wallet_type,
            'signer_header_source':'confirmed signer, POLY_ADDRESS','wallet_query_sent':False,'spender_query_sent':False,
            'asset_id_sent':False,'token_id_sent':False},
        'balance_historical_code':{'method':'GET','endpoint':path,'query':historical,
            'wallet_kind':'DEPOSIT_WALLET','wallet_resolution':'wallet omitted: legacy UUPS if deployed, otherwise beacon',
            'resolved_wallet_historically_proven':False,'raw_balance_user_reported':'109160000',
            'signer_header_source':'same signer, POLY_ADDRESS','wallet_query_sent':False,'spender_query_sent':False,
            'asset_id_sent':False,'token_id_sent':False},
        'deposit_candidates_public_computation_only':{
            'legacy_masked':mask(derive_uups_deposit_wallet_address(signer,env.wallet_derivation)),
            'beacon_masked':mask(derive_beacon_deposit_wallet_address(signer,env.wallet_derivation)),
            'deployment_or_balance_verified':False},
        'spender_selected_from_response':env.standard_exchange,
        'collateral_contract_sdk':env.collateral_token,
        'balance_zero_does_not_explain_historical_balance':current_type!=3,
        'positions':{'endpoint':spec.path,'first_page_query_redacted':public_params,
            'sdk_and_corrected_boolean_wire':'include_archived=true','previous_boolean_wire':'include_archived=True',
            'full_history_sent':False,'pagination':'opaque cursor; initial limit=100',
            'http_400_root_cause_confirmed':False},
        'collateral_proof':{'symbol_source':'official documentation identifies SDK contract as pUSD',
            'symbol_verified_onchain':False,'decimals_verified_onchain':False,'account_binding_verified':False,
            'reason':'CLOB response has balance/allowances, no contract/decimals/account binding attestation; no on-chain read performed',
            'conversion_allowed':False}}
