// SPDX-License-Identifier: BUSL-1.1
pragma solidity 0.8.34;

import {ERC1271} from "@solady/src/accounts/ERC1271.sol";
import {Receiver} from "@solady/src/accounts/Receiver.sol";
import {ERC1155} from "@solady/src/tokens/ERC1155.sol";
import {Initializable} from "@solady/src/utils/Initializable.sol";
import {SafeTransferLib} from "@solady/src/utils/SafeTransferLib.sol";

import {DepositWalletBeacon} from "@deposit-wallet/src/DepositWalletBeacon.sol";
import {DepositWalletFactory} from "@deposit-wallet/src/DepositWalletFactory.sol";
import {IDepositWallet} from "@deposit-wallet/src/interfaces/IDepositWallet.sol";
import {Ownable} from "@deposit-wallet/src/libraries/Ownable.sol";
import {PasskeySignerLib} from "@deposit-wallet/src/libraries/PasskeySignerLib.sol";
import {SignatureVerifierLib} from "@deposit-wallet/src/libraries/SignatureVerifierLib.sol";
import {
    SessionSignerLib,
    SessionEnvelopeStatus,
    SESSION_SIGNER_KIND_SECP256K1,
    SESSION_SIGNER_KIND_P256
} from "@deposit-wallet/src/libraries/SessionSignerLib.sol";
import {
    Batch,
    Call,
    WalletLib,
    ERC1271_MAGIC_VALUE,
    ERC1271_INVALID_VALUE
} from "@deposit-wallet/src/libraries/WalletLib.sol";

/// @title IBeaconForwarder
/// @author Polymarket
/// @notice Minimal interface for {BeaconForwarder}
interface IBeaconForwarder {
    function BEACON() external view returns (address);
}

/// @title DepositWallet
/// @author Polymarket
/// @notice Minimal smart-contract wallet for deposit operations.
/// @dev Deployed as an ERC-1967 beacon proxy via {DepositWalletFactory}. Supports batch execution
///      of arbitrary calls signed by the owner or an authorized session signer, ERC-1271
///      signature validation, two-step ownership transfers, and an owner-controlled pause
///      mechanism with a timelock for emergency asset recovery.
contract DepositWallet is IDepositWallet, Initializable, Receiver, ERC1271, Ownable {
    using SafeTransferLib for address;
    using SessionSignerLib for bytes;
    using WalletLib for Batch;

    /*--------------------------------------------------------------
                                 STATE
    --------------------------------------------------------------*/

    /// @dev Scratch memory used to pass resolved signer data through Solady's ERC-1271 flow.
    uint256 private constant _ERC1271_SIGNER_MEM_SLOT = 0x80;
    uint256 private constant _ERC1271_SIGNER_KIND_MEM_SLOT = 0xa0;
    uint256 private constant _ERC1271_PASSKEY_X_MEM_SLOT = 0xc0;
    uint256 private constant _ERC1271_PASSKEY_Y_MEM_SLOT = 0xe0;

    /// @dev Storage slot for the replay-protection nonce. keccak256("DepositWallet.nonce") - 1
    bytes32 private constant _NONCE_SLOT = bytes32(uint256(keccak256("DepositWallet.nonce")) - 1);

    /// @dev Storage slot for the paused timestamp. keccak256("DepositWallet.paused") - 1
    bytes32 private constant _PAUSED_SLOT = bytes32(uint256(keccak256("DepositWallet.paused")) - 1);

    /// @dev Base storage slot for the session signer mapping.
    /// keccak256("DepositWallet.sessionSignerAuthorizedUntil") - 1
    bytes32 private constant _SESSION_SIGNER_SLOT =
        bytes32(uint256(keccak256("DepositWallet.sessionSignerAuthorizedUntil")) - 1);

    /// @dev Base storage slot for passkey session signer records.
    /// keccak256("DepositWallet.passkeySessionSigner") - 1
    bytes32 private constant _PASSKEY_SESSION_SIGNER_SLOT =
        bytes32(uint256(keccak256("DepositWallet.passkeySessionSigner")) - 1);

    /// @dev ERC-1967 beacon slot.
    /// `0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50`. Populated on the proxy
    /// at deploy time by {LibClone.deployDeterministicERC1967BeaconProxy}; remains
    ///      empty for legacy UUPS proxies migrated through {BeaconForwarder}.
    bytes32 private constant _ERC1967_BEACON_SLOT =
        bytes32(uint256(keccak256("eip1967.proxy.beacon")) - 1);

    /// @dev ERC-1967 implementation slot.
    /// `0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc`. Empty on native beacon
    /// proxies; points at the {BeaconForwarder} on legacy UUPS proxies
    ///      migrated through the adapter.
    bytes32 private constant _ERC1967_IMPLEMENTATION_SLOT =
        bytes32(uint256(keccak256("eip1967.proxy.implementation")) - 1);

    /// @dev Byte length of the `(address factory, bytes32 id)` immutable args appended to the
    /// proxy bytecode.
    uint256 private constant _IMMUTABLE_ARGS_LENGTH = 64;

    /// @dev Identity magic returned by {walletInterfaceId} and probed by {DepositWalletBeacon}
    ///      when installing a new implementation. Stable; not bumped per release.
    bytes32 private constant _WALLET_INTERFACE_ID = keccak256("Polymarket.DepositWallet");

    /*--------------------------------------------------------------
                               MODIFIERS
    --------------------------------------------------------------*/

    /// @dev Restricts access to the factory contract.
    modifier onlyFactory() {
        require(msg.sender == factory(), OnlyFactory());
        _;
    }

    /// @dev Restricts access to calls originating from the wallet itself (i.e., via batch
    /// execution).
    modifier onlySelf() {
        require(msg.sender == address(this), OnlySelf());
        _;
    }

    /// @dev Enforces that the contract is paused and the timelock delay has elapsed.
    modifier onlyPaused() {
        uint256 pausedAt = paused();
        require(pausedAt != 0, NotPaused());
        require(
            block.timestamp > pausedAt + DepositWalletFactory(factory()).timelockDelay(),
            TimelockInsufficientDelay()
        );
        _;
    }

    /// @dev Restricts access to the wallet owner.
    modifier onlyOwner() {
        _checkOwner();
        _;
    }

    /*--------------------------------------------------------------
                              CONSTRUCTOR
    --------------------------------------------------------------*/

    /// @dev Disables initializers on the implementation contract to prevent misuse.
    constructor() {
        _disableInitializers();
    }

    /*--------------------------------------------------------------
                             INITIALIZER
    --------------------------------------------------------------*/

    /// @notice Initializes the wallet with a designated owner.
    /// @dev This replaces the constructor for upgradeable contracts.
    /// @param _owner The address to set as the wallet owner.
    function initialize(address _owner) external initializer {
        _initializeOwner(_owner);
    }

    /*--------------------------------------------------------------
                                  VIEW
    --------------------------------------------------------------*/

    /// @notice Returns the wallet's current execution nonce.
    /// @return nonce_ The current nonce.
    function nonce() public view returns (uint256 nonce_) {
        bytes32 slot = _NONCE_SLOT;
        assembly ("memory-safe") {
            nonce_ := sload(slot)
        }
    }

    /// @notice Returns the timestamp at which the wallet was paused.
    /// @return paused_ The paused timestamp, or zero if not paused.
    function paused() public view returns (uint256 paused_) {
        bytes32 slot = _PAUSED_SLOT;
        assembly ("memory-safe") {
            paused_ := sload(slot)
        }
    }

    /// @notice Returns the timestamp until which a session signer is authorized.
    /// @param _signer The session signer address to query.
    /// @return validUntil_ The authorization expiry timestamp, or zero if not authorized.
    function sessionSignerAuthorizedUntil(address _signer)
        public
        view
        returns (uint256 validUntil_)
    {
        bytes32 slot = _SESSION_SIGNER_SLOT;
        assembly ("memory-safe") {
            mstore(0x00, _signer)
            mstore(0x20, slot)
            validUntil_ := sload(keccak256(0x00, 0x40))
        }
    }

    /// @notice Returns a passkey session signer's public key and authorization expiry.
    function passkeySessionSigner(bytes32 _passkeyId)
        public
        view
        returns (bytes32 x, bytes32 y, uint256 validUntil)
    {
        bytes32 slot = _PASSKEY_SESSION_SIGNER_SLOT;
        assembly ("memory-safe") {
            mstore(0x00, _passkeyId)
            mstore(0x20, slot)
            let recordSlot := keccak256(0x00, 0x40)
            x := sload(recordSlot)
            y := sload(add(recordSlot, 1))
            validUntil := sload(add(recordSlot, 2))
        }
    }

    /// @notice Returns the unique identifier assigned to this wallet at deployment.
    /// @return The wallet ID decoded from the proxy's immutable args.
    function id() public view returns (bytes32) {
        (, bytes32 id_) = _readImmutableArgs();
        return id_;
    }

    /// @notice Returns the factory contract that deployed this wallet.
    /// @return The factory address decoded from the proxy's immutable args.
    function factory() public view returns (address) {
        (address factory_,) = _readImmutableArgs();
        return factory_;
    }

    /// @notice Returns the current owner of the wallet.
    /// @return result The owner address.
    function owner() public view override(IDepositWallet, Ownable) returns (address result) {
        return Ownable.owner();
    }

    /// @notice Returns the pending owner awaiting handover completion.
    /// @return result The pending owner address, or `address(0)` if none.
    function pendingOwner() public view override(IDepositWallet, Ownable) returns (address result) {
        return Ownable.pendingOwner();
    }

    /// @notice Returns the deadline by which the pending owner must complete the handover.
    /// @return result The acceptance-deadline timestamp, or zero if no handover is pending.
    function pendingOwnerDeadline()
        public
        view
        override(IDepositWallet, Ownable)
        returns (uint256 result)
    {
        return Ownable.pendingOwnerDeadline();
    }

    /// @notice Returns the per-handover nonce embedded in the EIP-712 signature.
    /// @return result The current handover nonce.
    function pendingOwnerNonce()
        public
        view
        override(IDepositWallet, Ownable)
        returns (uint256 result)
    {
        return Ownable.pendingOwnerNonce();
    }

    /// @notice Returns a stable magic identifying this contract as a `DepositWallet`.
    /// @dev Probed by {DepositWalletBeacon} on every implementation install.
    /// @return The wallet identity magic.
    function walletInterfaceId() external pure returns (bytes32) {
        return _WALLET_INTERFACE_ID;
    }

    /*--------------------------------------------------------------
                             ONLY FACTORY
    --------------------------------------------------------------*/

    /// @notice Executes a signed batch of calls through the factory.
    /// @dev Validates the batch (non-empty, correct wallet, nonce, deadline), verifies the EIP-712
    ///      signature against the owner or an authorized session signer, then executes each call
    ///      sequentially. Session signers are prevented from calling the wallet itself.
    /// @param _batch The batch containing the target wallet, nonce, deadline, and calls.
    /// @param _signature The EIP-712 signature authorizing the batch (owner or session signer).
    function execute(Batch calldata _batch, bytes calldata _signature) external onlyFactory {
        require(_batch.calls.length > 0, EmptyBatch());
        require(_batch.wallet == address(this), InvalidWallet());
        uint256 executedNonce;
        bytes32 nonceSlot = _NONCE_SLOT;
        assembly ("memory-safe") {
            executedNonce := sload(nonceSlot)
            sstore(nonceSlot, add(executedNonce, 1))
        }
        require(_batch.nonce == executedNonce, InvalidNonce());
        require(block.timestamp <= _batch.deadline, Expired());

        bytes32 batchHash = _batch.hash();
        bytes32 batchDigest = _hashTypedData(batchHash);

        require(
            isValidSignature(batchDigest, _signature) == ERC1271_MAGIC_VALUE, InvalidSignature()
        );

        bool isSessionSigner = _signature.isSessionSignerSignature();

        // Resolve the beacon once per batch — only needed when the signer is a session signer
        // and we have to enforce the additional guard against beacon calls.
        address beacon = isSessionSigner ? address(_beacon()) : address(0);

        uint256 i;
        for (; i < _batch.calls.length;) {
            require(
                !isSessionSigner || _batch.calls[i].target != address(this),
                SessionSignerSelfCallNotAllowed()
            );
            require(
                !isSessionSigner || _batch.calls[i].target != beacon,
                SessionSignerCannotCallBeacon()
            );

            (bool success, bytes memory result) =
                _batch.calls[i].target.call{value: _batch.calls[i].value}(_batch.calls[i].data);

            require(success, BatchCallFailed(i, _batch.calls[i].target, result));

            emit Execution(
                _batch.calls[i].target, _batch.calls[i].value, _batch.calls[i].data, result
            );

            unchecked {
                ++i;
            }
        }

        emit BatchExecuted(executedNonce);
    }

    /*--------------------------------------------------------------
                               ONLY SELF
    --------------------------------------------------------------*/

    /// @notice Authorizes a session signer until the specified timestamp.
    /// @dev Can only be invoked via batch execution (self-call).
    /// @param _sessionSigner The address to authorize as a session signer.
    /// @param _validUntil The timestamp until which the session signer is valid.
    function authorizeSessionSigner(address _sessionSigner, uint256 _validUntil) external onlySelf {
        require(_sessionSigner != address(0), ZeroAddress());
        require(_validUntil > block.timestamp, InvalidValidUntil());
        _setSessionSigner(_sessionSigner, _validUntil);

        emit SessionSignerAuthorized(_sessionSigner, _validUntil);
    }

    /// @notice Revokes a session signer's authorization.
    /// @dev Can only be invoked via batch execution (self-call).
    /// @param _sessionSigner The session signer address to revoke.
    function revokeSessionSigner(address _sessionSigner) external onlySelf {
        _setSessionSigner(_sessionSigner, 0);

        emit SessionSignerRevoked(_sessionSigner);
    }

    /// @notice Authorizes a P-256 passkey as a session signer.
    function authorizePasskeySessionSigner(bytes32 _x, bytes32 _y, uint256 _validUntil)
        external
        onlySelf
    {
        require(PasskeySignerLib.isValidPublicKey(_x, _y), InvalidPasskeyPublicKey(_x, _y));
        require(_validUntil > block.timestamp, InvalidValidUntil());

        bytes32 passkeyId = PasskeySignerLib.id(_x, _y);
        _setPasskeySessionSigner(passkeyId, _x, _y, _validUntil);

        emit PasskeySessionSignerAuthorized(passkeyId, _x, _y, _validUntil);
    }

    /// @notice Revokes a passkey session signer's authorization.
    function revokePasskeySessionSigner(bytes32 _passkeyId) external onlySelf {
        (bytes32 x, bytes32 y,) = passkeySessionSigner(_passkeyId);
        _setPasskeySessionSigner(_passkeyId, bytes32(0), bytes32(0), 0);

        emit PasskeySessionSignerRevoked(_passkeyId, x, y);
    }

    /// @notice Initiates a two-step ownership transfer to a new owner.
    /// @dev Can only be invoked via batch execution (self-call). Records the on-chain deadline
    ///      by which the pending owner must complete the handover and bumps the per-handover
    ///      nonce, invalidating any previously issued handover signature.
    /// @param _newOwner The proposed new owner, distinct from the current owner and this wallet.
    /// @param _deadline The timestamp by which the pending owner must complete the handover.
    function transferOwnership(address _newOwner, uint256 _deadline) external onlySelf {
        _transferOwnership(_newOwner, _deadline);
    }

    /// @notice Cancels any pending ownership handover.
    /// @dev Can only be invoked via batch execution (self-call).
    function cancelOwnershipHandover() external onlySelf {
        _cancelOwnershipHandover();
    }

    /*--------------------------------------------------------------
                           OWNERSHIP HANDOVER
    --------------------------------------------------------------*/

    /// @notice Completes a pending ownership transfer.
    /// @dev Permissionless — anyone may submit, but the pending owner must have signed an
    ///      EIP-712 `OwnershipHandover(newOwner, nonce)` message using the current
    ///      {pendingOwnerNonce}, and the on-chain {pendingOwnerDeadline} must not have elapsed.
    /// @param _signature The EIP-712 signature from the pending owner.
    function completeOwnershipHandover(bytes calldata _signature) external {
        _completeOwnershipHandover(_signature);
    }

    /*--------------------------------------------------------------
                               ONLY OWNER
    --------------------------------------------------------------*/

    /// @notice Pauses the wallet, recording the current timestamp.
    /// @dev After pausing, the owner must wait for the timelock delay before calling
    ///      paused-only functions (e.g., withdrawals, revocations).
    function pause() external onlyOwner {
        bytes32 slot = _PAUSED_SLOT;
        assembly ("memory-safe") {
            sstore(slot, timestamp())
        }

        emit Paused(block.timestamp);
    }

    /// @notice Unpauses the wallet.
    /// @dev Requires the wallet to be paused and the timelock delay to have elapsed.
    function unpause() external onlyPaused onlyOwner {
        bytes32 slot = _PAUSED_SLOT;
        assembly ("memory-safe") {
            sstore(slot, 0)
        }

        emit Unpaused(block.timestamp);
    }

    /// @notice Withdraws native tokens from the wallet.
    /// @dev Requires the wallet to be paused and the timelock delay to have elapsed.
    /// @param _to The recipient address.
    /// @param _amount The amount of native tokens to withdraw.
    function withdrawNative(address _to, uint256 _amount) external onlyPaused onlyOwner {
        _to.safeTransferETH(_amount);

        emit NativeWithdrawal(_to, _amount);
    }

    /// @notice Withdraws ERC-20 tokens from the wallet.
    /// @dev Requires the wallet to be paused and the timelock delay to have elapsed.
    /// @param _token The ERC-20 token address.
    /// @param _to The recipient address.
    /// @param _amount The amount of tokens to withdraw.
    function withdrawERC20(address _token, address _to, uint256 _amount)
        external
        onlyPaused
        onlyOwner
    {
        _token.safeTransfer(_to, _amount);

        emit ERC20Withdrawal(_token, _to, _amount);
    }

    /// @notice Batch-withdraws ERC-1155 tokens from the wallet.
    /// @dev Requires the wallet to be paused and the timelock delay to have elapsed.
    /// @param _token The ERC-1155 token address.
    /// @param _to The recipient address.
    /// @param _ids The token IDs to withdraw.
    /// @param _amounts The amounts for each token ID.
    function withdrawERC1155(
        address _token,
        address _to,
        uint256[] calldata _ids,
        uint256[] calldata _amounts
    ) external onlyPaused onlyOwner {
        ERC1155(_token).safeBatchTransferFrom(address(this), _to, _ids, _amounts, "");

        emit ERC1155BatchWithdrawal(_token, _to, _ids, _amounts);
    }

    /// @notice Revokes an ERC-20 allowance by setting it to zero.
    /// @dev Requires the wallet to be paused and the timelock delay to have elapsed.
    /// @param _token The ERC-20 token address.
    /// @param _spender The spender whose allowance is revoked.
    function revokeAllowance(address _token, address _spender) external onlyPaused onlyOwner {
        _token.safeApprove(_spender, 0);

        emit AllowanceRevoked(_token, _spender);
    }

    /// @notice Revokes an ERC-1155 operator approval.
    /// @dev Requires the wallet to be paused and the timelock delay to have elapsed.
    /// @param _token The ERC-1155 token address.
    /// @param _operator The operator whose approval is revoked.
    function revokeApprovalForAll(address _token, address _operator) external onlyPaused onlyOwner {
        ERC1155(_token).setApprovalForAll(_operator, false);

        emit ApprovalForAllRevoked(_token, _operator);
    }

    /// @notice Emergency revocation of a session signer by the owner.
    /// @dev Requires the wallet to be paused and the timelock delay to have elapsed.
    /// @param _sessionSigner The session signer to revoke.
    function revokeSessionSignerEmergency(address _sessionSigner) external onlyPaused onlyOwner {
        _setSessionSigner(_sessionSigner, 0);

        emit SessionSignerRevokedEmergency(_sessionSigner);
    }

    /// @notice Emergency revocation of a passkey session signer by the owner.
    function revokePasskeySessionSignerEmergency(bytes32 _passkeyId) external onlyPaused onlyOwner {
        (bytes32 x, bytes32 y,) = passkeySessionSigner(_passkeyId);
        _setPasskeySessionSigner(_passkeyId, bytes32(0), bytes32(0), 0);

        emit PasskeySessionSignerRevokedEmergency(_passkeyId, x, y);
    }

    /// @notice Opts the wallet out of beacon upgrades, pinning it to the current default
    ///         implementation.
    /// @dev Requires the wallet to be paused and the timelock delay to have elapsed. Calls
    ///      {DepositWalletBeacon.optOut} from the wallet proxy's address; the beacon emits the
    ///      {OptedOut} event.
    ///
    ///      WARNING: opting out is a security-bearing decision the wallet owner takes on their
    ///      own behalf. After this call:
    ///        - The wallet permanently follows the implementation that is current at opt-out
    ///          time, regardless of future beacon upgrades.
    ///        - Future security fixes, bug patches, and feature updates published via
    ///          `beacon.upgradeTo(...)` will NOT reach this wallet.
    ///        - If the pinned implementation is later found vulnerable, the wallet stays
    ///          vulnerable. The beacon owner cannot un-pin the wallet — only the wallet owner
    ///          can call {optIn} to rejoin the upgrade cohort.
    ///        - The pause-based exit hatch (`pause` → wait → `withdrawERC20` / etc.) keeps
    ///          working as long as the pinned implementation provides those functions.
    ///      By calling this function the owner acknowledges the above and accepts the risk.
    function optOut() external onlyPaused onlyOwner {
        _beacon().optOut();
    }

    /// @notice Clears the wallet's beacon-upgrade pin, rejoining the upgrade cohort.
    /// @dev Requires the wallet to be paused and the timelock delay to have elapsed. Calls
    ///      {DepositWalletBeacon.optIn} from the wallet proxy's address; the beacon emits the
    ///      {OptedIn} event.
    ///
    ///      WARNING: opting in resubscribes the wallet to beacon-driven upgrades. After this
    ///      call:
    ///        - The wallet's next call delegates through whatever the beacon currently
    ///          publishes as `defaultImplementation()`, immediately, with no further owner
    ///          confirmation.
    ///        - Any future `beacon.upgradeTo(...)` likewise takes effect on this wallet from
    ///          the next call onward, on the timelock's schedule rather than the owner's.
    ///        - Before opting in the owner must understand what the current beacon
    ///          implementation does and verify that it is safe to adopt and will not break any
    ///          functionality this wallet depends on. This is especially important when the
    ///          pinned implementation is several upgrade versions behind the current default —
    ///          the wallet skips every intermediate version and lands directly on the latest,
    ///          so any storage, behavioral, or interface changes accumulated across those
    ///          versions take effect at once.
    ///      By calling this function the owner acknowledges the above and accepts the risk.
    function optIn() external onlyPaused onlyOwner {
        _beacon().optIn();
    }

    /*--------------------------------------------------------------
                               INTERNAL
    --------------------------------------------------------------*/

    /// @dev Resolves the beacon from on-proxy state, decoupled from the factory:
    ///        1. If the ERC-1967 beacon slot is non-zero, this proxy was deployed natively as a
    ///           beacon proxy (via {LibClone.deployDeterministicERC1967BeaconProxy}) and the
    ///           slot stores the beacon address directly.
    ///        2. Otherwise, the ERC-1967 implementation slot is expected to point at a
    ///           {BeaconForwarder}; the forwarder's immutable `BEACON` getter returns the
    ///           beacon address. This is the legacy-migration fallback path.
    function _beacon() internal view returns (DepositWalletBeacon) {
        address resolved;
        bytes32 beaconSlot = _ERC1967_BEACON_SLOT;
        assembly ("memory-safe") {
            resolved := sload(beaconSlot)
        }
        if (resolved != address(0)) {
            return DepositWalletBeacon(resolved);
        }

        address impl;
        bytes32 implSlot = _ERC1967_IMPLEMENTATION_SLOT;
        assembly ("memory-safe") {
            impl := sload(implSlot)
        }
        require(impl.code.length > 0, BeaconUnresolvable());
        return DepositWalletBeacon(IBeaconForwarder(impl).BEACON());
    }

    /// @notice Stores the authorization expiry for a session signer.
    /// @param _signer The session signer address.
    /// @param _validUntil The expiry timestamp (zero to revoke).
    function _setSessionSigner(address _signer, uint256 _validUntil) internal {
        bytes32 slot = _SESSION_SIGNER_SLOT;
        assembly ("memory-safe") {
            mstore(0x00, _signer)
            mstore(0x20, slot)
            sstore(keccak256(0x00, 0x40), _validUntil)
        }
    }

    /// @notice Stores a passkey session signer record.
    function _setPasskeySessionSigner(
        bytes32 _passkeyId,
        bytes32 _x,
        bytes32 _y,
        uint256 _validUntil
    ) internal {
        bytes32 slot = _PASSKEY_SESSION_SIGNER_SLOT;
        assembly ("memory-safe") {
            mstore(0x00, _passkeyId)
            mstore(0x20, slot)
            let recordSlot := keccak256(0x00, 0x40)
            sstore(recordSlot, _x)
            sstore(add(recordSlot, 1), _y)
            sstore(add(recordSlot, 2), _validUntil)
        }
    }

    /// @dev Reads the proxy's immutable args from the tail of its bytecode. Works for both
    ///      ERC-1967 and ERC-1967 beacon proxies, since both templates append args at the end.
    function _readImmutableArgs() internal view returns (address factory_, bytes32 id_) {
        bytes memory args = new bytes(_IMMUTABLE_ARGS_LENGTH);
        address self = address(this);
        assembly ("memory-safe") {
            extcodecopy(
                self,
                add(args, 0x20),
                sub(extcodesize(self), _IMMUTABLE_ARGS_LENGTH),
                _IMMUTABLE_ARGS_LENGTH
            )
        }
        (factory_, id_) = abi.decode(args, (address, bytes32));
    }

    /*--------------------------------------------------------------
                                ERC1271
    --------------------------------------------------------------*/

    /// @notice Validates a signature against the wallet owner or an authorized session signer.
    /// @dev Overrides Solady's ERC-1271 implementation to support session signer signatures.
    ///      The resolved signer is stored in memory at `_ERC1271_SIGNER_MEM_SLOT` so that
    ///      `_erc1271Signer` can return it to the parent verification logic.
    /// @param _hash The hash that was signed.
    /// @param _signature The signature to validate (may contain a session signer wrapper).
    /// @return result `ERC1271_MAGIC_VALUE` if the signature is valid, otherwise reverts or returns
    /// `ERC1271_INVALID_VALUE`.
    function isValidSignature(bytes32 _hash, bytes calldata _signature)
        public
        view
        override(IDepositWallet, ERC1271)
        returns (bytes4 result)
    {
        (SessionEnvelopeStatus envelopeStatus, bytes32 signerId, uint256 signerKind) =
            _signature.decodeSessionSigner();

        address signer;
        bytes32 passkeyX;
        bytes32 passkeyY;
        uint256 validationKind = SESSION_SIGNER_KIND_SECP256K1;

        if (envelopeStatus == SessionEnvelopeStatus.NotSessionEnvelope) {
            signer = owner();
        } else if (
            envelopeStatus == SessionEnvelopeStatus.WellFormedEnvelope
                && signerKind == SESSION_SIGNER_KIND_SECP256K1
        ) {
            signer = address(uint160(uint256(signerId)));
            if (block.timestamp >= sessionSignerAuthorizedUntil(signer)) {
                return ERC1271_INVALID_VALUE;
            }
        } else if (
            envelopeStatus == SessionEnvelopeStatus.WellFormedEnvelope
                && signerKind == SESSION_SIGNER_KIND_P256
        ) {
            uint256 validUntil;
            (passkeyX, passkeyY, validUntil) = passkeySessionSigner(signerId);
            if (block.timestamp >= validUntil) return ERC1271_INVALID_VALUE;
            validationKind = SESSION_SIGNER_KIND_P256;
        } else {
            return ERC1271_INVALID_VALUE;
        }

        assembly {
            mstore(_ERC1271_SIGNER_MEM_SLOT, signer)
            mstore(_ERC1271_SIGNER_KIND_MEM_SLOT, validationKind)
            mstore(_ERC1271_PASSKEY_X_MEM_SLOT, passkeyX)
            mstore(_ERC1271_PASSKEY_Y_MEM_SLOT, passkeyY)
            if lt(mload(0x40), 0x100) { mstore(0x40, 0x100) }
        }

        return super.isValidSignature(_hash, _signature);
    }

    /// @dev Returns the signer address previously stored by `isValidSignature`.
    function _erc1271Signer() internal view virtual override returns (address signer) {
        assembly {
            signer := mload(_ERC1271_SIGNER_MEM_SLOT)
        }
    }

    /// @dev Factory calls use the safe caller path (direct ECDSA verification);
    ///      external callers go through the nested EIP-712 workflow.
    function _erc1271CallerIsSafe() internal view virtual override returns (bool) {
        return msg.sender == factory();
    }

    /// @dev Performs ECDSA, ERC-1271, or WebAuthn verification against the resolved signer.
    ///      Address-based signers (owner and secp256k1-kind session signers) verify via ECDSA
    ///      first, then fall back to an ERC-1271 staticcall when the signer is a contract.
    /// @param hash The digest to verify.
    /// @param signature The ECDSA signature, ERC-1271 payload, or WebAuthn assertion bytes.
    /// @return True if the signature is valid for the current signer.
    function _erc1271IsValidSignatureNowCalldata(bytes32 hash, bytes calldata signature)
        internal
        view
        override
        returns (bool)
    {
        uint256 signerKind;
        bytes32 passkeyX;
        bytes32 passkeyY;
        assembly {
            signerKind := mload(_ERC1271_SIGNER_KIND_MEM_SLOT)
            passkeyX := mload(_ERC1271_PASSKEY_X_MEM_SLOT)
            passkeyY := mload(_ERC1271_PASSKEY_Y_MEM_SLOT)
        }

        if (signerKind == SESSION_SIGNER_KIND_P256) {
            return PasskeySignerLib.verify(hash, passkeyX, passkeyY, signature);
        }

        return SignatureVerifierLib.isValidSignatureNow(_erc1271Signer(), hash, signature);
    }

    /*--------------------------------------------------------------
                                 EIP712
    --------------------------------------------------------------*/

    /// @dev Returns the EIP-712 domain name and version for this wallet.
    function _domainNameAndVersion()
        internal
        view
        virtual
        override
        returns (string memory name, string memory version)
    {
        name = "DepositWallet";
        version = "1";
    }
}
