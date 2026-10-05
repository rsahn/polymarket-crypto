// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.13;

/// @title Errors
/// @author Polymarket
/// @notice Custom errors shared across DepositWallet contracts.
abstract contract Errors {
    /// @notice Thrown when the caller is not authorized to perform the action.
    error Unauthorized();

    /// @notice Thrown when the provided owner address is invalid (e.g., zero address).
    error InvalidOwner();

    /// @notice Thrown when an ownership handover is expected but none is pending.
    error NoPendingOwner();

    /// @notice Thrown when a deadline has passed.
    error Expired();

    /// @notice Thrown when a signature fails verification.
    error InvalidSignature();

    /// @notice Thrown when the caller is not the factory contract.
    error OnlyFactory();

    /// @notice Thrown when a low-level call within a batch execution fails.
    error BatchCallFailed(uint256 index, address target, bytes result);

    /// @notice Thrown when a function restricted to self-calls is invoked externally.
    error OnlySelf();

    /// @notice Thrown when a batch contains zero calls.
    error EmptyBatch();

    /// @notice Thrown when the batch nonce does not match the wallet's current nonce.
    error InvalidNonce();

    /// @notice Thrown when the batch's wallet address does not match the executing wallet.
    error InvalidWallet();

    /// @notice Legacy error retained for ABI compatibility.
    error SessionSignerUnauthorized();

    /// @notice Thrown when a session signer attempts to call the wallet itself.
    error SessionSignerSelfCallNotAllowed();

    /// @notice Thrown when a session signer attempts to call the beacon — toggling the wallet's
    ///         beacon-upgrade pin is an owner-only privilege.
    error SessionSignerCannotCallBeacon();

    /// @notice Thrown when the supplied coordinates are not a valid P-256 public key.
    error InvalidPasskeyPublicKey(bytes32 x, bytes32 y);

    /// @notice Thrown when the zero address is provided where a non-zero address is required.
    error ZeroAddress();

    /// @notice Thrown when the provided `validUntil` timestamp is not in the future.
    error InvalidValidUntil();

    /// @notice Thrown when a paused-only function is called while the wallet is not paused.
    error NotPaused();

    /// @notice Thrown when the timelock delay has not elapsed since the wallet was paused.
    error TimelockInsufficientDelay();

    /// @notice Thrown when the wallet cannot resolve its beacon from on-proxy state — i.e., the
    ///         ERC-1967 beacon slot is empty AND the ERC-1967 implementation slot is either empty
    ///         or points at an address with no code.
    error BeaconUnresolvable();
}
