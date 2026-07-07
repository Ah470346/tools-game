"""
security/license.py

Handles offline cryptographic license key validation using digital signatures (Ed25519)
without online server authentication checks.
"""

import base64
import json
import logging
import time
from typing import Dict, Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

logger = logging.getLogger(__name__)


class LicenseError(Exception):
    """Exception raised for license validation errors."""
    pass


class LicenseChecker:
    """
    Validates license structures and checks expiry, digital signature, and hardware IDs offline.
    """

    def __init__(self, public_key_hex: str) -> None:
        """
        Initializes the LicenseChecker with verification public key.
        
        Args:
            public_key_hex (str): The hex-encoded Ed25519 public key.
        """
        self.public_key_hex = public_key_hex
        try:
            self._public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        except Exception as e:
            logger.error("Failed to load public key: %s", e)
            self._public_key = None

    def verify_key(self, key_string: str, current_hwid: str) -> bool:
        """
        Validates the signature and fields inside the license key.

        Args:
            key_string (str): The base64-encoded digital license key code.
            current_hwid (str): The current machine's HWID to bind against.

        Returns:
            bool: True if key is signed and valid.

        Raises:
            LicenseError: If the key is invalid, tampered, expired, or tied to another machine.
        """
        if not self._public_key:
            raise LicenseError("System Error: Public key is missing or invalid.")

        try:
            # 1. Decode Base64 wrapper
            decoded_json = base64.b64decode(key_string).decode('utf-8')
            license_data: Dict[str, Any] = json.loads(decoded_json)
        except Exception:
            raise LicenseError("License key format is invalid.")

        signature_hex = license_data.get("signature")
        payload = license_data.get("payload")

        if not signature_hex or not payload:
            raise LicenseError("License key is missing signature or payload.")

        # 2. Verify Signature
        try:
            signature_bytes = bytes.fromhex(signature_hex)
            payload_bytes = json.dumps(payload, sort_keys=True).encode('utf-8')
            self._public_key.verify(signature_bytes, payload_bytes)
        except InvalidSignature:
            raise LicenseError("License signature is invalid or tampered.")
        except Exception as e:
            raise LicenseError(f"Verification error: {e}")

        # 3. Verify Hardware ID
        licensed_hwid = payload.get("hwid")
        if licensed_hwid and licensed_hwid != current_hwid:
            raise LicenseError("License key is bound to a different machine (HWID mismatch).")

        # 4. Verify Expiration
        expiry_ts = payload.get("expiry")
        if expiry_ts:
            current_ts = time.time()
            if current_ts > expiry_ts:
                raise LicenseError("License key has expired.")

        return True
