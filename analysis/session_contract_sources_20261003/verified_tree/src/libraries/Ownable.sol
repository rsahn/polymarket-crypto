// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.13;

import {EIP712} from "@solady/src/utils/EIP712.sol";

import {Errors} from "@deposit-wallet/src/Errors.sol";
import {Events} from "@deposit-wallet/src/Events.sol";
import {SignatureVerifierLib} from "@deposit-wallet/src/libraries/SignatureVerifierLib.sol";

/// @title Ownable
/// @author Polymarket
/// @notice Two-step ownership management with EIP-712 signature-based handover.
/// @dev Ownership transfers require the new owner to sign an `OwnershipHandover` EIP-712 message.
///      This prevents accidental transfers to addresses that cannot interact with the wallet.
///      Storage uses custom slots to avoid collisions in proxy-based deployments.
abstract contract Ownable is EIP712, Errors, Events {
    /*--------------------------------------------------------------
                                 STATE
    --------------------------------------------------------------*/

    /// @dev Storage slot for the owner address. keccak256("DepositWallet.owner") - 1
    bytes32 internal constant _OWNER_SLOT = bytes32(uint256(keccak256("DepositWallet.owner")) - 1);

    /// @dev Storage slot for the pending owner address. keccak256("DepositWallet.pendingOwner") - 1
    bytes32 internal constant _PENDING_OWNER_SLOT =
        bytes32(uint256(keccak256("DepositWallet.pendingOwner")) - 1);

    /// @dev Storage slot for the deadline by which the pending owner must complete the handover.
    bytes32 internal constant _PENDING_OWNER_DEADLINE_SLOT =
        bytes32(uint256(keccak256("DepositWallet.pendingOwnerDeadline")) - 1);

    /// @dev Storage slot for the per-handover replay nonce.
    bytes32 internal constant _PENDING_OWNER_NONCE_SLOT =
        bytes32(uint256(keccak256("DepositWallet.pendingOwnerNonce")) - 1);

    /// @dev EIP-712 typehash for the `OwnershipHandover` struct.
    bytes32 private constant _OWNERSHIP_HANDOVER_TYPEHASH =
        keccak256("OwnershipHandover(address newOwner,uint256 nonce)");

    /*--------------------------------------------------------------
                                  VIEW
    --------------------------------------------------------------*/

    /// @notice Returns the current owner of the wallet.
    /// @return result The owner address.
    function owner() public view virtual returns (address result) {
        bytes32 slot = _OWNER_SLOT;
        assembly {
            result := sload(slot)
        }
    }

    /// @notice Returns the pending owner awaiting handover completion.
    /// @return result The pending owner address, or `address(0)` if none.
    function pendingOwner() public view virtual returns (address result) {
        bytes32 slot = _PENDING_OWNER_SLOT;
        assembly {
            result := sload(slot)
        }
    }

    /// @notice Returns the deadline by which the pending owner must complete the handover.
    /// @return result The acceptance-deadline timestamp, or zero if no handover is pending.
    function pendingOwnerDeadline() public view virtual returns (uint256 result) {
        bytes32 slot = _PENDING_OWNER_DEADLINE_SLOT;
        assembly {
            result := sload(slot)
        }
    }

    /// @notice Returns the per-handover nonce embedded in the EIP-712 signature.
    /// @dev Increments on every `_transferOwnership` call. The pending owner must sign over the
    ///      current value; any older value yields an invalid signature.
    /// @return result The current handover nonce.
    function pendingOwnerNonce() public view virtual returns (uint256 result) {
        bytes32 slot = _PENDING_OWNER_NONCE_SLOT;
        assembly {
            result := sload(slot)
        }
    }

    /*--------------------------------------------------------------
                              INTERNAL
    --------------------------------------------------------------*/

    /// @notice Sets the initial owner of the wallet.
    /// @dev Should only be called once during initialization.
    /// @param _newOwner The address to set as the initial owner.
    function _initializeOwner(address _newOwner) internal virtual {
        require(_newOwner != address(0), InvalidOwner());

        bytes32 slot = _OWNER_SLOT;

        assembly {
            sstore(slot, _newOwner)
        }

        emit OwnershipTransferred(address(0), _newOwner);
    }

    /// @notice Replaces the current owner with a new address.
    /// @param _newOwner The address of the new owner.
    function _setOwner(address _newOwner) internal virtual {
        address oldOwner = owner();
        bytes32 slot = _OWNER_SLOT;

        assembly {
            sstore(slot, _newOwner)
        }

        emit OwnershipTransferred(oldOwner, _newOwner);
    }

    /// @notice Stores a new pending owner address.
    /// @param _pendingOwner The address to set as the pending owner.
    function _setPendingOwner(address _pendingOwner) internal virtual {
        bytes32 slot = _PENDING_OWNER_SLOT;

        assembly {
            sstore(slot, _pendingOwner)
        }
    }

    /// @notice Stores the deadline by which the pending owner must complete the handover.
    /// @param _deadline The deadline timestamp, or zero to clear.
    function _setPendingOwnerDeadline(uint256 _deadline) internal virtual {
        bytes32 slot = _PENDING_OWNER_DEADLINE_SLOT;

        assembly {
            sstore(slot, _deadline)
        }
    }

    /// @notice Bumps the per-handover nonce by one.
    /// @return next The post-increment nonce value embedded in the next signed digest.
    function _incrementPendingOwnerNonce() internal virtual returns (uint256 next) {
        bytes32 slot = _PENDING_OWNER_NONCE_SLOT;

        assembly {
            next := add(sload(slot), 1)
            sstore(slot, next)
        }
    }

    /// @notice Reverts if `msg.sender` is not the current owner.
    function _checkOwner() internal view virtual {
        require(msg.sender == owner(), Unauthorized());
    }

    /*--------------------------------------------------------------
                           OWNERSHIP HANDOVER
    --------------------------------------------------------------*/

    /// @notice Initiates a two-step ownership transfer to `_newOwner`.
    /// @dev Records the pending owner, stores the on-chain acceptance deadline, and bumps the
    ///      per-handover nonce. The bump invalidates any previously issued handover signature.
    ///      Emits {OwnershipHandoverRequested}.
    /// @param _newOwner The proposed new owner (must be nonzero and distinct from the current
    ///                  owner and this contract).
    /// @param _deadline The timestamp by which the pending owner must complete the handover
    ///                  (must be `>= block.timestamp`).
    function _transferOwnership(address _newOwner, uint256 _deadline) internal virtual {
        require(
            _newOwner != address(0) && _newOwner != owner() && _newOwner != address(this),
            InvalidOwner()
        );
        require(block.timestamp <= _deadline, Expired());

        _setPendingOwner(_newOwner);
        _setPendingOwnerDeadline(_deadline);
        uint256 newNonce = _incrementPendingOwnerNonce();

        emit OwnershipHandoverRequested(_newOwner, _deadline, newNonce);
    }

    /// @notice Cancels any pending ownership handover.
    /// @dev Clears the pending owner and acceptance deadline. The handover nonce is intentionally
    ///      not bumped here — replay safety is already provided by the bump on the next
    ///      `_transferOwnership` call combined with the `pendingOwner != 0` gate.
    function _cancelOwnershipHandover() internal virtual {
        address pending = pendingOwner();

        require(pending != address(0), NoPendingOwner());

        _setPendingOwner(address(0));
        _setPendingOwnerDeadline(0);

        emit OwnershipHandoverCanceled(pending);
    }

    /// @notice Completes a two-step ownership handover using an EIP-712 signature from the
    ///         pending owner.
    /// @dev Validates that a handover is pending, the on-chain acceptance deadline has not
    ///      elapsed, and the signature is valid for the pending owner (ECDSA or ERC-1271) over
    ///      `OwnershipHandover(newOwner, nonce)` using the current nonce. On success, transfers
    ///      ownership and clears the pending-owner state.
    /// @param _signature The EIP-712 signature from the pending owner.
    function _completeOwnershipHandover(bytes calldata _signature) internal virtual {
        address pending = pendingOwner();

        require(pending != address(0), NoPendingOwner());
        require(block.timestamp <= pendingOwnerDeadline(), Expired());

        bytes32 structHash =
            keccak256(abi.encode(_OWNERSHIP_HANDOVER_TYPEHASH, pending, pendingOwnerNonce()));
        bytes32 digest = _hashTypedData(structHash);

        require(
            SignatureVerifierLib.isValidSignatureNow(pending, digest, _signature),
            InvalidSignature()
        );

        address previousOwner = owner();

        _setPendingOwner(address(0));
        _setPendingOwnerDeadline(0);
        _setOwner(pending);

        emit OwnershipHandoverCompleted(previousOwner, pending);
    }
}
