// SPDX-License-Identifier: BUSL-1.1
pragma solidity 0.8.34;

import {OwnableRoles} from "@solady/src/auth/OwnableRoles.sol";
import {Initializable} from "@solady/src/utils/Initializable.sol";
import {LibClone} from "@solady/src/utils/LibClone.sol";
import {UUPSUpgradeable} from "@solady/src/utils/UUPSUpgradeable.sol";

import {Errors} from "@deposit-wallet/src/Errors.sol";
import {IDepositWallet, Batch} from "@deposit-wallet/src/interfaces/IDepositWallet.sol";

/// @notice Minimal interface for resolving a beacon's current implementation.
interface IBeacon {
    /// @notice Returns the implementation the beacon currently resolves to.
    function implementation() external view returns (address);
}

/// @title DepositWalletFactoryErrors
/// @author Polymarket
/// @notice Custom errors for {DepositWalletFactory}.
abstract contract DepositWalletFactoryErrors {
    /// @notice Thrown when the caller does not have the admin role.
    error OnlyAdmin();

    /// @notice Thrown when the caller does not have the operator role.
    error OnlyOperator();

    /// @notice Thrown when the caller does not have the legacy-deployer role.
    error OnlyLegacyDeployer();

    /// @notice Thrown when paired input arrays have mismatched lengths.
    error ArrayLengthMismatch();

    /// @notice Thrown when an implementation has not been authorized.
    /// @dev Deprecated post-migration; only thrown by the legacy {setImplementation} surface.
    error ImplementationNotAuthorized();

    /// @notice Thrown when the provided timelock delay is zero or exceeds the maximum.
    error InvalidTimelockDelay();

    /// @notice Thrown when a deploy target (the beacon, its resolved implementation, or the
    ///         legacy implementation) has no code.
    /// @dev Fail-closed guard: deploying a proxy whose implementation/beacon is code-less would
    ///      let `initialize` silently succeed as a delegatecall to an empty account, minting an
    ///      ownerless wallet that anyone could later seize.
    error ImplementationNotDeployed();
}

/// @title DepositWalletFactoryEvents
/// @author Polymarket
/// @notice Events emitted by {DepositWalletFactory}.
abstract contract DepositWalletFactoryEvents {
    /// @notice Emitted when a wallet implementation is added to the authorized set.
    /// @dev Deprecated post-migration; only emitted while the legacy upgrade surface is in use
    ///      (e.g., authorizing {BeaconForwarder}).
    /// @param implementation The address of the authorized implementation.
    event ImplementationAuthorized(address indexed implementation);

    /// @notice Emitted when the default wallet implementation is updated.
    /// @dev Deprecated; the legacy slot-0 `implementation` pointer is no longer consulted by
    ///      {DepositWalletFactory.deploy}.
    /// @param Implementation The address of the new default implementation.
    event ImplementationSet(address Implementation);

    /// @notice Emitted when a wallet implementation is removed from the authorized set.
    /// @dev Deprecated post-migration; only emitted while the legacy upgrade surface is in use.
    /// @param implementation The address of the unauthorized implementation.
    event ImplementationUnauthorized(address indexed implementation);

    /// @notice Emitted when the timelock delay is updated.
    /// @param timelockDelay The new timelock delay in seconds.
    event TimelockDelaySet(uint256 timelockDelay);

    /// @notice Emitted when a new deposit wallet is deployed.
    /// @param wallet The address of the newly deployed wallet proxy.
    /// @param owner The initial owner of the wallet.
    /// @param id The unique identifier assigned to the wallet.
    /// @param implementation The address embedded in the proxy: the beacon for beacon-shape
    ///                       wallets, or the legacy implementation for legacy-shape wallets.
    event WalletDeployed(
        address indexed wallet, address indexed owner, bytes32 indexed id, address implementation
    );
}

/// @title DepositWalletFactory
/// @author Polymarket
/// @notice Factory contract for deploying and managing DepositWallets. Deploys ERC-1967
///         beacon proxies going forward, and can also deploy legacy ERC-1967 (UUPS-shaped)
///         wallets at the exact deterministic addresses the pre-beacon factory used.
/// @dev Uses a four-tier role model:
///      - **Owner**: can add/remove admins, manage implementations, and authorize UUPS upgrades
///                   of the factory itself.
///      - **Admin** (ROLE_0): can add/remove operators and legacy deployers, and configure the
///                   timelock delay.
///      - **Operator** (ROLE_1): can deploy beacon-shape wallets and proxy batch executions.
///      - **Legacy deployer** (ROLE_2): can deploy legacy-shape wallets via {deployLegacy}.
///
///      Two deploy paths, fed identical `args`/`salt`:
///      - {deploy} produces an ERC-1967 beacon proxy bound to {BEACON}.
///      - {deployLegacy} produces a plain ERC-1967 proxy embedding {LEGACY_IMPL}. This reproduces
///        the exact addresses the pre-beacon factory derived, because the address depends only on
///        (this factory's address, the embedded implementation, the Solady proxy template, the
///        id) — never on this factory's own bytecode. It exists for ids whose legacy address has
///        already been handed out, and for cross-chain recovery: deployed at the canonical
///        factory address on another chain, it mints a wallet at the identical address a user's
///        Polygon deposit wallet occupies.
///
///      Both paths fail closed: they revert unless the embedded implementation/beacon already
///      holds code, so a misordered rollout cannot mint ownerless, seizable wallets.
///
///      Storage slots 0/1/2 (`implementation`, `timelockDelay`, `authorizedImplementation`) are
///      preserved from prior versions so this contract can be installed as a UUPS upgrade on the
///      live factory proxy without corrupting state.
contract DepositWalletFactory is
    OwnableRoles,
    Initializable,
    UUPSUpgradeable,
    DepositWalletFactoryErrors,
    DepositWalletFactoryEvents
{
    /*--------------------------------------------------------------
                                 STATE
    --------------------------------------------------------------*/

    /// @notice Legacy default wallet implementation pointer.
    /// @dev Deprecated; not consulted by {deploy} or {deployLegacy}. Retained only to preserve
    ///      slot 0 of the live factory proxy so this contract can be installed via UUPS upgrade
    ///      in place.
    address public implementation;

    /// @notice The delay in seconds that must elapse after pausing before the owner can
    ///         execute paused-only operations on a wallet.
    uint256 public timelockDelay;

    /// @notice Tracks which implementation addresses are authorized for legacy UUPS upgrades.
    /// @dev Legacy-shape wallets gate their `upgrade` self-call on this mapping. Used during the
    ///      migration window to authorize {BeaconForwarder} so existing UUPS wallets can opt into
    ///      the beacon. Will be deprecated after the migration window closes.
    mapping(address => bool) public authorizedImplementation;

    /*--------------------------------------------------------------
                              CONSTANTS
    --------------------------------------------------------------*/

    /// @notice The maximum allowed timelock delay (7 days).
    uint256 public constant MAX_TIMELOCK_DELAY = 7 days;

    /*--------------------------------------------------------------
                              IMMUTABLES
    --------------------------------------------------------------*/

    /// @notice The beacon that resolves the implementation for beacon-shape wallets.
    address public immutable BEACON;

    /// @notice The implementation embedded in legacy-shape (ERC-1967, UUPS) wallets.
    /// @dev Set to the live legacy DepositWallet implementation so {deployLegacy} reproduces the
    ///      exact wallet addresses the pre-beacon factory deployed.
    address public immutable LEGACY_IMPL;

    /*--------------------------------------------------------------
                              CONSTRUCTOR
    --------------------------------------------------------------*/

    /// @dev Sets the beacon and legacy implementation, then disables initializers on the
    ///      implementation contract.
    /// @param _beacon The beacon contract address for beacon-shape wallets.
    /// @param _legacyImpl The legacy implementation address embedded in legacy-shape wallets.
    constructor(address _beacon, address _legacyImpl) {
        require(_beacon != address(0), Errors.ZeroAddress());
        require(_legacyImpl != address(0), Errors.ZeroAddress());
        BEACON = _beacon;
        LEGACY_IMPL = _legacyImpl;
        _disableInitializers();
    }

    /*--------------------------------------------------------------
                              INITIALIZER
    --------------------------------------------------------------*/

    /// @notice Initializes the factory with an owner, admin, and timelock delay.
    /// @param _owner The address to set as the factory owner.
    /// @param _admin The address to grant the initial admin role.
    /// @param _timelockDelay The initial timelock delay in seconds.
    function initialize(address _owner, address _admin, uint256 _timelockDelay)
        external
        initializer
    {
        require(_owner != address(0), Errors.ZeroAddress());
        require(_admin != address(0), Errors.ZeroAddress());
        _initializeOwner(_owner);
        _setRoles(_admin, _ROLE_0);
        _setTimelockDelay(_timelockDelay);
    }

    /*--------------------------------------------------------------
                               MODIFIERS
    --------------------------------------------------------------*/

    /// @dev Restricts access to addresses with the admin role (ROLE_0).
    modifier onlyAdmin() {
        require(hasAnyRole(msg.sender, _ROLE_0), OnlyAdmin());
        _;
    }

    /// @dev Restricts access to addresses with the operator role (ROLE_1).
    modifier onlyOperator() {
        require(hasAnyRole(msg.sender, _ROLE_1), OnlyOperator());
        _;
    }

    /// @dev Restricts access to addresses with the legacy-deployer role (ROLE_2).
    modifier onlyLegacyDeployer() {
        require(hasAnyRole(msg.sender, _ROLE_2), OnlyLegacyDeployer());
        _;
    }

    /*--------------------------------------------------------------
                                  VIEW
    --------------------------------------------------------------*/

    /// @notice Returns whether the given address has the admin role.
    /// @param _admin The address to check.
    /// @return True if the address is an admin.
    function isAdmin(address _admin) external view returns (bool) {
        return hasAnyRole(_admin, _ROLE_0);
    }

    /// @notice Returns whether the given address has the operator role.
    /// @param _operator The address to check.
    /// @return True if the address is an operator.
    function isOperator(address _operator) external view returns (bool) {
        return hasAnyRole(_operator, _ROLE_1);
    }

    /// @notice Returns whether the given address has the legacy-deployer role.
    /// @param _legacyDeployer The address to check.
    /// @return True if the address is a legacy deployer.
    function isLegacyDeployer(address _legacyDeployer) external view returns (bool) {
        return hasAnyRole(_legacyDeployer, _ROLE_2);
    }

    /// @notice Predicts the deterministic address of a wallet before deployment.
    /// @dev Deprecated; retained for ABI compatibility. The first argument is ignored — wallets
    ///      are now beacon proxies bound to {BEACON}. Prefer {predictWalletAddress(bytes32)}.
    /// @param _id The unique identifier for the wallet.
    /// @return The predicted wallet proxy address.
    function predictWalletAddress(address, bytes32 _id) external view returns (address) {
        return _predictWalletAddress(_id);
    }

    /// @notice Predicts the deterministic address of a beacon-proxy wallet before deployment.
    /// @dev This returns the address derived from the beacon-proxy template. For the address of a
    ///      legacy-shape (ERC-1967, UUPS) wallet, use {predictLegacyWalletAddress} — the two
    ///      shapes live at different deterministic addresses because the proxy bytecode (and
    ///      therefore the CREATE2 derivation) differs.
    /// @param _id The unique identifier for the wallet.
    /// @return The predicted beacon-proxy wallet address.
    function predictWalletAddress(bytes32 _id) external view returns (address) {
        return _predictWalletAddress(_id);
    }

    /// @notice Predicts the deterministic address of a legacy-shape (ERC-1967) wallet before
    ///         deployment.
    /// @dev This matches the address the pre-beacon factory assigned to a wallet with the same
    ///      `_id` — including, on other chains, the address of the user's Polygon wallet —
    ///      enabling cross-chain recovery at the identical address.
    /// @param _id The unique identifier for the wallet.
    /// @return The predicted legacy wallet address.
    function predictLegacyWalletAddress(bytes32 _id) external view returns (address) {
        bytes memory args = abi.encode(address(this), _id);

        return LibClone.predictDeterministicAddressERC1967(
            LEGACY_IMPL, args, keccak256(args), address(this)
        );
    }

    /*--------------------------------------------------------------
                             ONLY OPERATOR
    --------------------------------------------------------------*/

    /// @notice Deploys one or more beacon-shape deposit wallets with deterministic addresses.
    /// @dev It is the operator's responsibility to ensure that each `_id` is unique.
    ///      Duplicate IDs will cause the deployment to revert because the deterministic
    ///      address is already occupied. Note: beacon-shape and legacy-shape wallets for the
    ///      same `_id` live at DIFFERENT addresses (different proxy template), so they never
    ///      collide; the operator must dedupe IDs across both shapes off-chain.
    /// @param _owners The initial owner addresses for each wallet.
    /// @param _ids The unique identifiers for each wallet.
    function deploy(address[] calldata _owners, bytes32[] calldata _ids) external onlyOperator {
        require(_owners.length == _ids.length, ArrayLengthMismatch());

        // Fail closed: require both the beacon AND its resolved implementation to hold code.
        // A beacon-proxy delegatecalls the beacon's resolved implementation, so checking only the
        // beacon address would let a beacon resolving to a code-less implementation slip through,
        // turning `initialize` into a silent no-op delegatecall and minting an ownerless wallet.
        require(BEACON.code.length != 0, ImplementationNotDeployed());
        require(IBeacon(BEACON).implementation().code.length != 0, ImplementationNotDeployed());

        for (uint256 i; i < _owners.length; ++i) {
            bytes memory args = abi.encode(address(this), _ids[i]);

            address wallet =
                LibClone.deployDeterministicERC1967BeaconProxy(BEACON, args, keccak256(args));

            IDepositWallet(wallet).initialize(_owners[i]);

            emit WalletDeployed(wallet, _owners[i], _ids[i], BEACON);
        }
    }

    /// @notice Proxies batch execution to one or more wallets.
    /// @dev Each batch is forwarded to its target wallet's `execute` function. Works for both
    ///      wallet shapes (the `Batch` layout is identical across the legacy and current
    ///      implementations).
    /// @param _batches The batches to execute.
    /// @param _signatures The corresponding signatures for each batch.
    function proxy(Batch[] calldata _batches, bytes[] calldata _signatures) external onlyOperator {
        require(_batches.length == _signatures.length, ArrayLengthMismatch());
        for (uint256 i; i < _batches.length; ++i) {
            IDepositWallet(_batches[i].wallet).execute(_batches[i], _signatures[i]);
        }
    }

    /*--------------------------------------------------------------
                          ONLY LEGACY DEPLOYER
    --------------------------------------------------------------*/

    /// @notice Deploys one or more legacy-shape (ERC-1967, UUPS) deposit wallets with
    ///         deterministic addresses that match the pre-beacon factory's derivation.
    /// @dev Restricted to the legacy-deployer role (ROLE_2), granted independently of the
    ///      operator role. Used for ids whose legacy address has already been handed out, and for
    ///      cross-chain recovery: a wallet deployed here lands at the same address the user's
    ///      Polygon deposit wallet occupies. The resulting wallet runs {LEGACY_IMPL} (the V1
    ///      implementation). See {deploy} for the ID-uniqueness and cross-shape notes.
    /// @param _owners The initial owner addresses for each wallet.
    /// @param _ids The unique identifiers for each wallet.
    function deployLegacy(address[] calldata _owners, bytes32[] calldata _ids)
        external
        onlyLegacyDeployer
    {
        require(_owners.length == _ids.length, ArrayLengthMismatch());

        // Fail closed: a code-less legacy implementation would mint ownerless wallets.
        require(LEGACY_IMPL.code.length != 0, ImplementationNotDeployed());

        for (uint256 i; i < _owners.length; ++i) {
            bytes memory args = abi.encode(address(this), _ids[i]);

            address wallet = LibClone.deployDeterministicERC1967(LEGACY_IMPL, args, keccak256(args));

            IDepositWallet(wallet).initialize(_owners[i]);

            emit WalletDeployed(wallet, _owners[i], _ids[i], LEGACY_IMPL);
        }
    }

    /*--------------------------------------------------------------
                               ONLY ADMIN
    --------------------------------------------------------------*/

    /// @notice Grants the operator role to an address.
    /// @param _operator The address to grant the operator role.
    function addOperator(address _operator) external onlyAdmin {
        _grantRoles(_operator, _ROLE_1);
    }

    /// @notice Removes the operator role from an address.
    /// @param _operator The address to remove the operator role from.
    function removeOperator(address _operator) external onlyAdmin {
        _removeRoles(_operator, _ROLE_1);
    }

    /// @notice Grants the legacy-deployer role to an address.
    /// @param _legacyDeployer The address to grant the legacy-deployer role.
    function addLegacyDeployer(address _legacyDeployer) external onlyAdmin {
        _grantRoles(_legacyDeployer, _ROLE_2);
    }

    /// @notice Removes the legacy-deployer role from an address.
    /// @param _legacyDeployer The address to remove the legacy-deployer role from.
    function removeLegacyDeployer(address _legacyDeployer) external onlyAdmin {
        _removeRoles(_legacyDeployer, _ROLE_2);
    }

    /// @notice Sets the timelock delay for paused wallet operations.
    /// @param _timelockDelay The new timelock delay in seconds.
    function setTimelockDelay(uint256 _timelockDelay) external onlyAdmin {
        _setTimelockDelay(_timelockDelay);
    }

    /*--------------------------------------------------------------
                               ONLY OWNER
    --------------------------------------------------------------*/

    /// @notice Grants the admin role to an address.
    /// @param _admin The address to grant the admin role.
    function addAdmin(address _admin) external onlyOwner {
        _grantRoles(_admin, _ROLE_0);
    }

    /// @notice Removes the admin role from an address.
    /// @param _admin The address to remove the admin role from.
    function removeAdmin(address _admin) external onlyOwner {
        _removeRoles(_admin, _ROLE_0);
    }

    /// @notice Sets the legacy slot-0 implementation pointer.
    /// @dev Deprecated; retained for ABI compatibility. Has no effect on {deploy} (which uses
    ///      {BEACON}) or {deployLegacy} (which uses {LEGACY_IMPL}).
    /// @param _implementation The new default implementation address.
    function setImplementation(address _implementation) external onlyOwner {
        _setImplementation(_implementation);
    }

    /// @notice Authorizes an implementation address for legacy UUPS upgrades.
    /// @dev Used during the migration window to authorize {BeaconForwarder}; will be deprecated
    ///      after the migration window closes.
    /// @param _implementation The implementation address to authorize.
    function authorizeImplementation(address _implementation) external onlyOwner {
        require(_implementation != address(0), Errors.ZeroAddress());
        authorizedImplementation[_implementation] = true;

        emit ImplementationAuthorized(_implementation);
    }

    /// @notice Removes an implementation address from the authorized set.
    /// @dev Used during the migration window; will be deprecated after the window closes.
    /// @param _implementation The implementation address to unauthorize.
    function unauthorizeImplementation(address _implementation) external onlyOwner {
        authorizedImplementation[_implementation] = false;

        emit ImplementationUnauthorized(_implementation);
    }

    /*--------------------------------------------------------------
                               INTERNAL
    --------------------------------------------------------------*/

    /// @dev Authorizes UUPS upgrades of the factory. Restricted to the owner.
    function _authorizeUpgrade(address) internal override onlyOwner {}

    /// @notice Writes the legacy slot-0 implementation pointer.
    /// @dev Deprecated; retained for ABI compatibility. Slot 0 is no longer consulted by
    ///      {deploy}.
    /// @param _implementation The new default implementation address (must be authorized).
    function _setImplementation(address _implementation) internal {
        require(authorizedImplementation[_implementation], ImplementationNotAuthorized());
        implementation = _implementation;

        emit ImplementationSet(_implementation);
    }

    /// @notice Sets the timelock delay for paused wallet operations.
    /// @param _timelockDelay The new timelock delay in seconds.
    function _setTimelockDelay(uint256 _timelockDelay) internal {
        require(_timelockDelay > 0 && _timelockDelay <= MAX_TIMELOCK_DELAY, InvalidTimelockDelay());
        timelockDelay = _timelockDelay;

        emit TimelockDelaySet(_timelockDelay);
    }

    /// @notice Computes the deterministic address of a wallet bound to {BEACON}.
    /// @param _id The unique identifier for the wallet.
    /// @return The predicted wallet proxy address.
    function _predictWalletAddress(bytes32 _id) internal view returns (address) {
        bytes memory args = abi.encode(address(this), _id);

        return LibClone.predictDeterministicAddressERC1967BeaconProxy(
            BEACON, args, keccak256(args), address(this)
        );
    }
}
