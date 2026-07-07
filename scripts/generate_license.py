"""
scripts/generate_license.py

Utility script for the seller to generate a new offline license key.
It reads the private key, accepts HWID and duration, and produces a base64-encoded license string.
"""

import argparse
import base64
import json
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

def generate_license(private_key_hex: str, hwid: str, days: int) -> str:
    """Generates a base64 license key string."""
    try:
        private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    except Exception as e:
        raise ValueError(f"Invalid private key: {e}")
        
    # Calculate expiry
    expiry_ts = time.time() + (days * 24 * 3600)
    
    payload = {
        "hwid": hwid,
        "expiry": expiry_ts
    }
    
    # Serialize payload to canonical JSON (sorted keys)
    payload_bytes = json.dumps(payload, sort_keys=True).encode('utf-8')
    
    # Sign payload
    signature_bytes = private_key.sign(payload_bytes)
    
    # Construct final license object
    license_data = {
        "payload": payload,
        "signature": signature_bytes.hex()
    }
    
    # Encode to base64
    license_json = json.dumps(license_data)
    license_b64 = base64.b64encode(license_json.encode('utf-8')).decode('utf-8')
    
    return license_b64


def main():
    parser = argparse.ArgumentParser(description="Generate an offline license key.")
    parser.add_argument("--priv", required=True, help="Hex-encoded Ed25519 Private Key")
    parser.add_argument("--hwid", required=True, help="Target Hardware ID (HWID)")
    parser.add_argument("--days", type=int, default=30, help="Number of days the license is valid (default 30)")
    
    args = parser.parse_args()
    
    print(f"Generating {args.days}-day license for HWID: {args.hwid}")
    try:
        lic = generate_license(args.priv, args.hwid, args.days)
        print("\n" + "="*50)
        print("LICENSE KEY (Give this to the user):")
        print(lic)
        print("="*50 + "\n")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
