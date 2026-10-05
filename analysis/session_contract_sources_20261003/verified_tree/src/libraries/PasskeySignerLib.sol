// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.13;

import {P256} from "@openzeppelin/contracts/utils/cryptography/P256.sol";
import {WebAuthn} from "@deposit-wallet/src/libraries/WebAuthnNative.sol";

/// @title PasskeySignerLib
/// @author Polymarket
/// @notice Helpers for P-256 passkey identifiers and WebAuthn assertion verification.
library PasskeySignerLib {
    /// @notice Returns the identifier for a P-256 public key.
    function id(bytes32 _x, bytes32 _y) internal pure returns (bytes32) {
        return keccak256(bytes.concat(_x, _y));
    }

    /// @notice Returns whether the coordinates form a valid P-256 public key.
    function isValidPublicKey(bytes32 _x, bytes32 _y) internal pure returns (bool) {
        return P256.isValidPublicKey(_x, _y);
    }

    /// @notice Verifies a WebAuthn assertion against a digest and P-256 public key.
    /// @dev User presence is required by OpenZeppelin. User verification is intentionally optional.
    function verify(bytes32 _hash, bytes32 _x, bytes32 _y, bytes calldata _signature)
        internal
        view
        returns (bool)
    {
        (bool decoded, WebAuthn.WebAuthnAuth calldata auth) = WebAuthn.tryDecodeAuth(_signature);
        return decoded && WebAuthn.verify(bytes.concat(_hash), auth, _x, _y, false);
    }
}
