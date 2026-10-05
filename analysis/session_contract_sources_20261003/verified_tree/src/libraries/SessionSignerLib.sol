// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.13;

/// @dev Magic suffix bytes appended to a signature to indicate the presence of a session signer.
/// Mirrors the ERC-6492 magic value to reuse the same detection mechanism.
bytes32 constant SESSION_SIGNER_MAGIC_BYTES =
    0x6492649264926492649264926492649264926492649264926492649264926492;

/// @dev Existing secp256k1 EVM session signer.
uint256 constant SESSION_SIGNER_KIND_SECP256K1 = 0;

/// @dev WebAuthn P-256 (secp256r1) passkey session signer.
uint256 constant SESSION_SIGNER_KIND_P256 = 1;

/// @notice Parse state for a potential session signer envelope.
/// @dev `MalformedEnvelope` is the zero value so an uninitialized status fails closed.
enum SessionEnvelopeStatus {
    MalformedEnvelope,
    NotSessionEnvelope,
    WellFormedEnvelope
}

/// @title SessionSignerLib
/// @author Polymarket
/// @notice Utilities for encoding and decoding session signer signatures.
/// @dev Session signer signatures wrap an inner signature with a signer identifier, signer kind,
///      and trailing magic suffix, following the ERC-6492 envelope format.
library SessionSignerLib {
    /// @notice Decodes a session signer envelope.
    /// @dev A present but malformed envelope is distinguished from a signature with no magic
    ///      suffix so callers never fall back to owner verification. Parsed signer fields are
    ///      exposed only for a fully validated envelope.
    /// @param _signature The raw signature bytes, potentially wrapped with session signer data.
    /// @return status Whether the signature is not an envelope, malformed, or well formed.
    /// @return signerId The EVM address (left-padded) or passkey identifier.
    /// @return signerKind The signer kind discriminator.
    function decodeSessionSigner(bytes calldata _signature)
        internal
        pure
        returns (SessionEnvelopeStatus status, bytes32 signerId, uint256 signerKind)
    {
        if (_signature.length < 0x20) {
            return (SessionEnvelopeStatus.NotSessionEnvelope, bytes32(0), 0);
        }

        bool hasMagic;
        uint256 dynamicOffset;
        uint256 innerLength;
        assembly ("memory-safe") {
            hasMagic := eq(
                calldataload(add(_signature.offset, sub(_signature.length, 0x20))),
                SESSION_SIGNER_MAGIC_BYTES
            )
        }
        if (!hasMagic) {
            return (SessionEnvelopeStatus.NotSessionEnvelope, bytes32(0), 0);
        }
        if (_signature.length < 0xa0) {
            return (SessionEnvelopeStatus.MalformedEnvelope, bytes32(0), 0);
        }

        bytes32 candidateSignerId;
        uint256 candidateSignerKind;
        assembly ("memory-safe") {
            candidateSignerId := calldataload(_signature.offset)
            candidateSignerKind := calldataload(add(_signature.offset, 0x20))
            dynamicOffset := calldataload(add(_signature.offset, 0x40))
            innerLength := calldataload(add(_signature.offset, 0x60))
        }

        if (dynamicOffset != 0x60 || innerLength > type(uint256).max - 0x1f) {
            return (SessionEnvelopeStatus.MalformedEnvelope, bytes32(0), 0);
        }

        uint256 paddedInnerLength = (innerLength + 0x1f) & ~uint256(0x1f);
        if (paddedInnerLength > type(uint256).max - 0xa0) {
            return (SessionEnvelopeStatus.MalformedEnvelope, bytes32(0), 0);
        }
        if (_signature.length != 0xa0 + paddedInnerLength) {
            return (SessionEnvelopeStatus.MalformedEnvelope, bytes32(0), 0);
        }

        if (candidateSignerKind == SESSION_SIGNER_KIND_SECP256K1) {
            if (
                uint256(candidateSignerId) >> 160 == 0
                    && address(uint160(uint256(candidateSignerId))) != address(0)
            ) {
                return (
                    SessionEnvelopeStatus.WellFormedEnvelope, candidateSignerId, candidateSignerKind
                );
            }
        } else if (
            candidateSignerKind == SESSION_SIGNER_KIND_P256 && candidateSignerId != bytes32(0)
        ) {
            return
                (SessionEnvelopeStatus.WellFormedEnvelope, candidateSignerId, candidateSignerKind);
        }

        return (SessionEnvelopeStatus.MalformedEnvelope, bytes32(0), 0);
    }

    /// @notice Returns whether a signature contains a valid session signer envelope.
    function isSessionSignerSignature(bytes calldata _signature) internal pure returns (bool) {
        (SessionEnvelopeStatus status,,) = decodeSessionSigner(_signature);
        return status == SessionEnvelopeStatus.WellFormedEnvelope;
    }

    /// @notice Creates a session signer signature by wrapping an existing signature.
    /// @dev Encodes the session signer address, the secp256k1 signer kind, the inner signature,
    ///      and the magic suffix into a single byte array. Because
    ///      `SESSION_SIGNER_KIND_SECP256K1` is 0, the envelope is byte-identical to the legacy
    ///      format that carried a zero placeholder in the kind slot.
    /// @param _sessionSigner The session signer address to encode.
    /// @param _signature The inner ECDSA signature to wrap.
    /// @return The wrapped session signer signature.
    function getSessionSignerSignature(address _sessionSigner, bytes memory _signature)
        internal
        pure
        returns (bytes memory)
    {
        return bytes.concat(
            abi.encode(_sessionSigner, SESSION_SIGNER_KIND_SECP256K1, _signature),
            SESSION_SIGNER_MAGIC_BYTES
        );
    }

    /// @notice Creates a passkey session signer signature by wrapping a WebAuthn assertion.
    /// @param _passkeyId The passkey identifier (`keccak256(x || y)`).
    /// @param _signature The ABI-encoded WebAuthn assertion, optionally with an ERC-7739 suffix.
    /// @return The wrapped passkey session signer signature.
    function getPasskeySessionSignerSignature(bytes32 _passkeyId, bytes memory _signature)
        internal
        pure
        returns (bytes memory)
    {
        return bytes.concat(
            abi.encode(_passkeyId, SESSION_SIGNER_KIND_P256, _signature), SESSION_SIGNER_MAGIC_BYTES
        );
    }
}
