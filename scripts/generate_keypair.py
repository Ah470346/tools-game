"""
scripts/generate_keypair.py

Utility script for the seller to generate a new Ed25519 Private/Public key pair.
The private key is used to sign licenses, and the public key is embedded in the bot
source code to verify those licenses.

Run this script ONCE per product distribution.
KEEP THE PRIVATE KEY SECRET.
"""

import os
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

def main():
    print("Generating new Ed25519 Keypair...")
    
    # Generate private key
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # Extract raw bytes
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    
    priv_hex = private_bytes.hex()
    pub_hex = public_bytes.hex()
    
    print("\n" + "="*50)
    print("PRIVATE KEY (Keep this secret!):")
    print(priv_hex)
    print("="*50)
    
    print("\n" + "="*50)
    print("PUBLIC KEY (Embed this in your bot code):")
    print(pub_hex)
    print("="*50)
    
    # Optionally save to file
    with open("license_keys.txt", "w") as f:
        f.write("PRIVATE_KEY=" + priv_hex + "\n")
        f.write("PUBLIC_KEY=" + pub_hex + "\n")
    
    print("\nKeys saved to 'license_keys.txt'. Make sure to not commit this file to version control!")

if __name__ == "__main__":
    main()
