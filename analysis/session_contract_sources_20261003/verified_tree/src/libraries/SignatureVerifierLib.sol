// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.13;

import {ECDSA} from "@solady/src/utils/ECDSA.sol";

import {ERC1271_MAGIC_VALUE} from "@deposit-wallet/src/libraries/WalletLib.sol";

/// @title IERC1271
/// @author Polymarket
/// @notice Minimal ERC-1271 interface used to encode the `isValidSignature` staticcall.
/// @dev EIP-1271 defines the magic value as `bytes4(keccak256("isValidSignature(bytes32,bytes)"))`,
///      so the selector of this function and `ERC1271_MAGIC_VALUE` are the same constant.
interface IERC1271 {
    /// @notice Returns the ERC-1271 magic value when `_signature` is valid for `_hash`.
    /// @param _hash The digest that was signed.
    /// @param _signature The signature payload.
    /// @return The ERC-1271 magic value (`0x1626ba7e`) if the signature is valid.
    function isValidSignature(bytes32 _hash, bytes calldata _signature)
        external
        view
        returns (bytes4);
}

/// @title SignatureVerifierLib
/// @author Polymarket
/// @notice Verifies a signature for an address-based signer via ECDSA or ERC-1271.
/// @dev ECDSA recovery is attempted first so that externally owned accounts — including EIP-7702
///      delegated accounts, whose raw keys remain valid at the protocol level — never lose the
///      ability to sign with their key. When ECDSA does not match and the signer has code,
///      verification falls back to an ERC-1271 `isValidSignature` staticcall on the signer.
///      Counterfactual (ERC-6492) contract signers are not supported: the signer contract must
///      be deployed at verification time.
library SignatureVerifierLib {
    /// @notice Returns whether `_signature` is valid for `_signer` over `_hash`.
    /// @dev The ERC-1271 staticcall is never performed on the verifying contract itself, so a
    ///      wallet configured as its own signer cannot enter a self-referential validation loop.
    ///      A contract signer must return exactly the ERC-1271 magic value, left-aligned in a
    ///      single word; reverts, wrong magic, and malformed return data all verify as false.
    ///      Returndata copying is capped at one word to prevent return-data gas griefing.
    /// @param _signer The expected signer (EOA or deployed ERC-1271 contract).
    /// @param _hash The digest that was signed.
    /// @param _signature A 64/65-byte ECDSA signature or an ERC-1271 payload for `_signer`.
    /// @return Whether the signature is valid for `_signer`.
    function isValidSignatureNow(address _signer, bytes32 _hash, bytes calldata _signature)
        internal
        view
        returns (bool)
    {
        if (_signer == address(0)) return false;

        if (_signature.length == 64 || _signature.length == 65) {
            if (ECDSA.tryRecoverCalldata(_hash, _signature) == _signer) return true;
        }

        if (_signer == address(this) || _signer.code.length == 0) return false;

        bytes memory callData = abi.encodeCall(IERC1271.isValidSignature, (_hash, _signature));
        bool success;
        bytes32 result;
        assembly ("memory-safe") {
            success := staticcall(gas(), _signer, add(callData, 0x20), mload(callData), 0x00, 0x20)
            success := and(success, eq(returndatasize(), 0x20))
            result := mload(0x00)
        }
        return success && result == bytes32(ERC1271_MAGIC_VALUE);
    }
}
