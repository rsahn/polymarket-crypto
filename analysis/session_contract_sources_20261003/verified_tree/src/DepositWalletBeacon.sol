// SPDX-License-Identifier: BUSL-1.1
pragma solidity 0.8.34;

import {IDepositWallet} from "@deposit-wallet/src/interfaces/IDepositWallet.sol";

/// @title DepositWalletBeacon
/// @author Polymarket
/// @notice Implementation pointer for every {DepositWallet} beacon proxy. Owner is expected to be
///         a timelock.
///
/// @dev Note:
/// - The implementation is intended to be used with ERC1967 beacon proxies.
///   See: `LibClone.deployDeterministicERC1967BeaconProxy` and related functions.
/// - For gas efficiency, the ownership functionality is baked into this contract.
///
/// @dev Lifted near-verbatim from Solady's UpgradeableBeacon at commit
///      `acd959aa4bd04720d640bf4e6a5c71037510cc4b`
///      (https://github.com/Vectorized/solady/blob/acd959aa4bd04720d640bf4e6a5c71037510cc4b/src/utils/UpgradeableBeacon.sol).
/// Solady's storage slots, errors, events, assembly, and modifier are preserved unchanged
///      so auditors can diff against upstream. Polymarket-specific deltas, all marked inline:
///        1. {_setImplementation} runs Solady's verbatim assembly, then probes
///           `walletInterfaceId()` on the candidate. A failed probe reverts the surrounding
///           transaction, unwinding the SSTORE and the {Upgraded} log emitted by the assembly.
///        2. {implementation} adds per-`msg.sender` dispatch — opted-out callers receive their
///           pinned implementation; everyone else reads Solady's slot value.
///        3. New {optOut} / {optIn} self-call entrypoints update `pinnedImplementation`.
///        4. New {defaultImplementation} view exposes the slot value bypassing per-caller
///           dispatch (for indexers and the timelock UI).
///      The `pinnedImplementation` mapping lives at Solidity slot 0; Solady's `uint72` slot
///      constants live in a disjoint namespace, so there is no collision.
contract DepositWalletBeacon {
    /*´:°•.°+.*•´.*:˚.°*.˚•´.°:°•.°•.*•´.*:˚.°*.˚•´.°:°•.°+.*•´.*:*/
    /*                       CUSTOM ERRORS                        */
    /*.•°:°.´+˚.*°.˚:*.´•*.+°.•°:´*.´•*.•°.•°:°.´:•˚°.*°.˚:*.´+°.•*/

    /// @dev The new implementation is not a deployed contract.
    error NewImplementationHasNoCode();

    /// @dev The caller is not authorized to perform the operation.
    error Unauthorized();

    /// @dev The `newOwner` cannot be the zero address.
    error NewOwnerIsZeroAddress();

    /// @dev Polymarket addition. The candidate implementation does not return the expected
    ///      `walletInterfaceId()` magic.
    error InvalidWalletInterfaceId();

    /*´:°•.°+.*•´.*:˚.°*.˚•´.°:°•.°•.*•´.*:˚.°*.˚•´.°:°•.°+.*•´.*:*/
    /*                           EVENTS                           */
    /*.•°:°.´+˚.*°.˚:*.´•*.+°.•°:´*.´•*.•°.•°:°.´:•˚°.*°.˚:*.´+°.•*/

    /// @dev Emitted when the proxy's implementation is upgraded.
    event Upgraded(address indexed implementation);

    /// @dev The ownership is transferred from `oldOwner` to `newOwner`.
    /// This event is intentionally kept the same as OpenZeppelin's Ownable to be
    /// compatible with indexers and [EIP-173](https://eips.ethereum.org/EIPS/eip-173),
    /// despite it not being as lightweight as a single argument event.
    event OwnershipTransferred(address indexed oldOwner, address indexed newOwner);

    /// @dev Polymarket addition. Emitted when a wallet opts out of beacon upgrades.
    event OptedOut(address indexed wallet, address indexed pinnedImpl);

    /// @dev Polymarket addition. Emitted when a wallet rejoins the upgrade cohort. The second
    ///      indexed arg is the default implementation the wallet will follow on its next call.
    event OptedIn(address indexed wallet, address indexed currentImpl);

    /// @dev `keccak256(bytes("Upgraded(address)"))`.
    uint256 private constant _UPGRADED_EVENT_SIGNATURE =
        0xbc7cd75a20ee27fd9adebab32041f755214dbc6bffa90cc0225b39da2e5c2d3b;

    /// @dev `keccak256(bytes("OwnershipTransferred(address,address)"))`.
    uint256 private constant _OWNERSHIP_TRANSFERRED_EVENT_SIGNATURE =
        0x8be0079c531659141344cd1fd0a4f28419497f9722a3daafe3b4186f6b6457e0;

    /*´:°•.°+.*•´.*:˚.°*.˚•´.°:°•.°•.*•´.*:˚.°*.˚•´.°:°•.°+.*•´.*:*/
    /*                          STORAGE                           */
    /*.•°:°.´+˚.*°.˚:*.´•*.+°.•°:´*.´•*.•°.•°:°.´:•˚°.*°.˚:*.´+°.•*/

    /// @dev The storage slot for the implementation address.
    /// `uint72(bytes9(keccak256("_UPGRADEABLE_BEACON_IMPLEMENTATION_SLOT")))`.
    uint256 internal constant _UPGRADEABLE_BEACON_IMPLEMENTATION_SLOT = 0x911c5a209f08d5ec5e;

    /// @dev The storage slot for the owner address.
    /// `uint72(bytes9(keccak256("_UPGRADEABLE_BEACON_OWNER_SLOT")))`.
    uint256 internal constant _UPGRADEABLE_BEACON_OWNER_SLOT = 0x4343a0dc92ed22dbfc;

    /// @dev Polymarket addition. Magic returned by every accepted implementation.
    bytes32 public constant EXPECTED_WALLET_INTERFACE_ID = keccak256("Polymarket.DepositWallet");

    /// @dev Polymarket addition. Per-wallet pinned implementation. Zero = follow default.
    ///      Lives at Solidity slot 0; disjoint from Solady's `uint72` slot constants.
    mapping(address wallet => address pinnedImpl) public pinnedImplementation;

    /*´:°•.°+.*•´.*:˚.°*.˚•´.°:°•.°•.*•´.*:˚.°*.˚•´.°:°•.°+.*•´.*:*/
    /*                        CONSTRUCTOR                         */
    /*.•°:°.´+˚.*°.˚:*.´•*.+°.•°:´*.´•*.•°.•°:°.´:•˚°.*°.˚:*.´+°.•*/

    constructor(address initialOwner, address initialImplementation) payable {
        // We don't need to check if `initialOwner` is the zero address here,
        // as some use cases may not want the beacon to be owned.
        _setOwner(initialOwner);
        _setImplementation(initialImplementation);
    }

    /*´:°•.°+.*•´.*:˚.°*.˚•´.°:°•.°•.*•´.*:˚.°*.˚•´.°:°•.°+.*•´.*:*/
    /*               UPGRADEABLE BEACON OPERATIONS                */
    /*.•°:°.´+˚.*°.˚:*.´•*.+°.•°:´*.´•*.•°.•°:°.´:•˚°.*°.˚:*.´+°.•*/

    /// @dev Sets the implementation directly without authorization guard.
    /// Polymarket modification: probe `walletInterfaceId()` after Solady's verbatim assembly.
    /// The probe runs on the candidate address; a mismatch reverts and unwinds the SSTORE +
    /// {Upgraded} log emitted by the assembly.
    function _setImplementation(address newImplementation) internal virtual {
        assembly ("memory-safe") {
            newImplementation := shr(96, shl(96, newImplementation)) // Clean the upper 96 bits.
            if iszero(extcodesize(newImplementation)) {
                mstore(0x00, 0x6d3e283b) // `NewImplementationHasNoCode()`.
                revert(0x1c, 0x04)
            }
            // Store the implementation.
            sstore(_UPGRADEABLE_BEACON_IMPLEMENTATION_SLOT, newImplementation)
            // Emit the {Upgraded} event.
            log2(codesize(), 0x00, _UPGRADED_EVENT_SIGNATURE, newImplementation)
        }
        _checkWalletInterfaceId(newImplementation);
    }

    /// @dev Sets the owner directly without authorization guard.
    function _setOwner(address newOwner) internal virtual {
        assembly ("memory-safe") {
            newOwner := shr(96, shl(96, newOwner)) // Clean the upper 96 bits.
            let oldOwner := sload(_UPGRADEABLE_BEACON_OWNER_SLOT)
            sstore(_UPGRADEABLE_BEACON_OWNER_SLOT, newOwner) // Store the owner.
            // Emit the {OwnershipTransferred} event.
            log3(codesize(), 0x00, _OWNERSHIP_TRANSFERRED_EVENT_SIGNATURE, oldOwner, newOwner)
        }
    }

    /// @dev Returns the implementation stored in the beacon.
    /// See: https://eips.ethereum.org/EIPS/eip-1967#beacon-contract-address
    /// Polymarket modification: per-`msg.sender` dispatch — opted-out callers receive their
    /// pinned implementation; everyone else reads Solady's slot value.
    function implementation() public view returns (address result) {
        address pinned = pinnedImplementation[msg.sender];
        if (pinned != address(0)) return pinned;
        assembly ("memory-safe") {
            result := sload(_UPGRADEABLE_BEACON_IMPLEMENTATION_SLOT)
        }
    }

    /// @dev Returns the owner of the beacon.
    function owner() public view returns (address result) {
        assembly ("memory-safe") {
            result := sload(_UPGRADEABLE_BEACON_OWNER_SLOT)
        }
    }

    /// @dev Allows the owner to upgrade the implementation.
    function upgradeTo(address newImplementation) public virtual onlyOwner {
        _setImplementation(newImplementation);
    }

    /// @dev Allows the owner to transfer the ownership to `newOwner`.
    function transferOwnership(address newOwner) public virtual onlyOwner {
        assembly ("memory-safe") {
            if iszero(shl(96, newOwner)) {
                mstore(0x00, 0x7448fbae) // `NewOwnerIsZeroAddress()`.
                revert(0x1c, 0x04)
            }
        }
        _setOwner(newOwner);
    }

    /// @dev Allows the owner to renounce their ownership.
    function renounceOwnership() public virtual onlyOwner {
        _setOwner(address(0));
    }

    /// @dev Throws if the sender is not the owner.
    function _checkOwner() internal view virtual {
        assembly ("memory-safe") {
            // If the caller is not the stored owner, revert.
            if iszero(eq(caller(), sload(_UPGRADEABLE_BEACON_OWNER_SLOT))) {
                mstore(0x00, 0x82b42900) // `Unauthorized()`.
                revert(0x1c, 0x04)
            }
        }
    }

    /*´:°•.°+.*•´.*:˚.°*.˚•´.°:°•.°•.*•´.*:˚.°*.˚•´.°:°•.°+.*•´.*:*/
    /*                         MODIFIERS                          */
    /*.•°:°.´+˚.*°.˚:*.´•*.+°.•°:´*.´•*.•°.•°:°.´:•˚°.*°.˚:*.´+°.•*/

    /// @dev Marks a function as only callable by the owner.
    modifier onlyOwner() virtual {
        _checkOwner();
        _;
    }

    /*´:°•.°+.*•´.*:˚.°*.˚•´.°:°•.°•.*•´.*:˚.°*.˚•´.°:°•.°+.*•´.*:*/
    /*                    POLYMARKET ADDITIONS                    */
    /*.•°:°.´+˚.*°.˚:*.´•*.+°.•°:´*.´•*.•°.•°:°.´:•˚°.*°.˚:*.´+°.•*/

    /// @notice Returns the default implementation, ignoring per-caller dispatch.
    /// @dev Indexers and the timelock UI should read this rather than {implementation} to
    ///      retrieve the global default regardless of the caller.
    function defaultImplementation() public view returns (address result) {
        assembly ("memory-safe") {
            result := sload(_UPGRADEABLE_BEACON_IMPLEMENTATION_SLOT)
        }
    }

    /// @notice Opts the calling wallet out of beacon upgrades.
    /// @dev Snapshots the current default implementation into `pinnedImplementation[msg.sender]`.
    ///      Subsequent calls from the wallet route to that snapshot regardless of further
    ///      `upgradeTo` calls. NOT idempotent: if the default implementation has changed since
    ///      the last `optOut`, calling again bumps the pin to the new default without requiring
    ///      an intermediate `optIn`. This is intentional — it lets wallets adopt a newer version
    ///      while staying opted out of automatic upgrades.
    function optOut() external {
        address current = defaultImplementation();
        pinnedImplementation[msg.sender] = current;
        emit OptedOut(msg.sender, current);
    }

    /// @notice Clears the calling wallet's pin and rejoins the upgrade cohort.
    function optIn() external {
        delete pinnedImplementation[msg.sender];
        emit OptedIn(msg.sender, defaultImplementation());
    }

    /// @dev Reverts if `_implementation` does not return {EXPECTED_WALLET_INTERFACE_ID} from
    ///      `walletInterfaceId()`. Also catches no-code addresses (staticcall to empty returns
    ///      no data and fails the length check).
    function _checkWalletInterfaceId(address _implementation) internal view {
        (bool ok, bytes memory ret) = _implementation.staticcall(
            abi.encodeWithSelector(IDepositWallet.walletInterfaceId.selector)
        );
        if (!(ok && ret.length == 32 && abi.decode(ret, (bytes32)) == EXPECTED_WALLET_INTERFACE_ID))
        {
            revert InvalidWalletInterfaceId();
        }
    }
}
