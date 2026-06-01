import base64
import json
import os
from dataclasses import dataclass
from datetime import date
from enum import Enum

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LICENSE_PATH = os.path.join(BASE_DIR, "config", "license.json")
PUBKEY_PATH = os.path.join(BASE_DIR, "config", "license_pubkey.pem")


class LicenseStatus(str, Enum):
    VALID = "valid"
    EXPIRED = "expired"
    INVALID = "invalid"


@dataclass
class LicenseInfo:
    status: LicenseStatus = LicenseStatus.INVALID
    client_id: str = ""
    issued_to: str = ""
    issued_date: str = ""
    expiry_date: str = ""
    max_users: int = 0
    days_remaining: int = 0
    message: str = "No license loaded"

    def as_dict(self) -> dict:
        return {
            "status": self.status.value,
            "client_id": self.client_id,
            "issued_to": self.issued_to,
            "issued_date": self.issued_date,
            "expiry_date": self.expiry_date,
            "max_users": self.max_users,
            "days_remaining": self.days_remaining,
            "message": self.message,
        }


def _canonical_payload(data: dict) -> bytes:
    fields = {k: v for k, v in data.items() if k != "signature"}
    return json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()


def load_license() -> LicenseInfo:
    if not os.path.exists(PUBKEY_PATH):
        return LicenseInfo(message="Verification key not found")

    if not os.path.exists(LICENSE_PATH):
        return LicenseInfo(message="License file not found (config/license.json missing)")

    try:
        with open(LICENSE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return LicenseInfo(message=f"Cannot read license file: {e}")

    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        from cryptography.exceptions import InvalidSignature

        with open(PUBKEY_PATH, "rb") as f:
            pub_key = load_pem_public_key(f.read())
        sig = base64.b64decode(data["signature"])
        payload = _canonical_payload(data)
        pub_key.verify(sig, payload, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        return LicenseInfo(message="License signature is invalid — file may have been tampered with")
    except Exception as e:
        return LicenseInfo(message=f"License verification error: {e}")

    try:
        expiry = date.fromisoformat(data["expiry_date"])
        days_remaining = (expiry - date.today()).days
    except Exception as e:
        return LicenseInfo(message=f"Invalid expiry date in license: {e}")

    status = LicenseStatus.VALID if days_remaining >= 0 else LicenseStatus.EXPIRED
    msg = "" if status == LicenseStatus.VALID else f"License expired on {data['expiry_date']}"

    return LicenseInfo(
        status=status,
        client_id=data.get("client_id", ""),
        issued_to=data.get("issued_to", ""),
        issued_date=data.get("issued_date", ""),
        expiry_date=data.get("expiry_date", ""),
        max_users=data.get("max_users", 0),
        days_remaining=max(0, days_remaining),
        message=msg,
    )
