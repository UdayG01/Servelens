#!/usr/bin/env python3
"""
Servelens license generator — run this on the vendor/developer machine only.

First-time setup (generates RSA-2048 key pair):
  python tools/generate_license.py --init

Issue a license to a client:
  python tools/generate_license.py --client-id acme --issued-to "ACME Corp" --expiry 2027-12-31

The generated config/license.json is sent to the client.
The private key in tools/keys/ MUST never leave the developer machine.
"""

import argparse
import base64
import json
import os
import sys
from datetime import date

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(TOOLS_DIR)
KEYS_DIR = os.path.join(TOOLS_DIR, "keys")
PRIVATE_KEY_PATH = os.path.join(KEYS_DIR, "private_key.pem")
PUBLIC_KEY_PATH = os.path.join(KEYS_DIR, "public_key.pem")
CONFIG_PUBKEY_PATH = os.path.join(BASE_DIR, "config", "license_pubkey.pem")


def generate_keys() -> None:
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    os.makedirs(KEYS_DIR, exist_ok=True)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    with open(PRIVATE_KEY_PATH, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    os.chmod(PRIVATE_KEY_PATH, 0o600)

    pub_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    with open(PUBLIC_KEY_PATH, "wb") as f:
        f.write(pub_pem)

    os.makedirs(os.path.dirname(CONFIG_PUBKEY_PATH), exist_ok=True)
    with open(CONFIG_PUBKEY_PATH, "wb") as f:
        f.write(pub_pem)

    print("RSA-2048 key pair generated:")
    print(f"  Private key : {PRIVATE_KEY_PATH}")
    print(f"               ^^^ KEEP SECRET — never share or commit ^^^")
    print(f"  Public key  : {PUBLIC_KEY_PATH}")
    print(f"  App pubkey  : {CONFIG_PUBKEY_PATH}  (deploy this with the app)")


def _load_private_key():
    if not os.path.exists(PRIVATE_KEY_PATH):
        print(f"ERROR: Private key not found at {PRIVATE_KEY_PATH}")
        print("Run:  python tools/generate_license.py --init")
        sys.exit(1)

    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    with open(PRIVATE_KEY_PATH, "rb") as f:
        return load_pem_private_key(f.read(), password=None)


def _canonical_payload(data: dict) -> bytes:
    fields = {k: v for k, v in data.items() if k != "signature"}
    return json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()


def generate_license(client_id: str, issued_to: str, expiry: str, output_path: str) -> None:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    try:
        expiry_date = date.fromisoformat(expiry)
    except ValueError:
        print(f"ERROR: Invalid date '{expiry}'. Use YYYY-MM-DD format.")
        sys.exit(1)

    private_key = _load_private_key()

    payload = {
        "client_id": client_id,
        "issued_to": issued_to,
        "issued_date": date.today().isoformat(),
        "expiry_date": expiry_date.isoformat(),
    }

    signature = private_key.sign(_canonical_payload(payload), padding.PKCS1v15(), hashes.SHA256())
    license_data = {**payload, "signature": base64.b64encode(signature).decode()}

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(license_data, f, indent=2)

    days = (expiry_date - date.today()).days
    print(f"License written to: {output_path}")
    print(f"  Client ID  : {client_id}")
    print(f"  Issued to  : {issued_to}")
    print(f"  Issued     : {date.today()}")
    print(f"  Expires    : {expiry_date}  ({days} days remaining)")
    print()
    print("Send the client:")
    print(f"  {output_path}")
    print(f"  {CONFIG_PUBKEY_PATH}")
    print("They must place both files in the app's config/ directory.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Servelens license generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--init", action="store_true",
                        help="Generate RSA key pair (run once on first setup)")
    parser.add_argument("--client-id", metavar="ID",
                        help="Unique slug for this client (e.g. acme-corp)")
    parser.add_argument("--issued-to", metavar="NAME",
                        help="Human-readable client/company name")
    parser.add_argument("--expiry", metavar="YYYY-MM-DD",
                        help="License expiry date")
    parser.add_argument("--output", metavar="PATH",
                        default=os.path.join(BASE_DIR, "config", "license.json"),
                        help="Output path for the license file (default: config/license.json)")

    args = parser.parse_args()

    if args.init:
        if os.path.exists(PRIVATE_KEY_PATH):
            ans = input(f"Key pair already exists in {KEYS_DIR}. Overwrite? [y/N] ").strip()
            if ans.lower() != "y":
                print("Aborted.")
                sys.exit(0)
        generate_keys()
        print()
        print("Next step — issue a license:")
        print('  python tools/generate_license.py --client-id <id> --issued-to "<name>" --expiry <YYYY-MM-DD>')
        return

    if args.client_id and args.issued_to and args.expiry:
        generate_license(args.client_id, args.issued_to, args.expiry, args.output)
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
