"""Pinned P-256 identities; signatures use WebCrypto's IEEE P1363 r||s encoding."""

import base64
import ctypes
import hashlib
import json
import math
import os
import secrets
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)

from .settings import atomic_json


def b64(value: bytes):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def unb64(value: str):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def public_jwk(key):
    n = key.public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": b64(n.x.to_bytes(32, "big")),
        "y": b64(n.y.to_bytes(32, "big")),
    }


def load_public(jwk):
    if (
        jwk.get("kty") != "EC"
        or jwk.get("crv") != "P-256"
        or "d" in jwk
        or any(not isinstance(jwk.get(k), str) or len(jwk[k]) != 43 for k in ("x", "y"))
    ):
        raise ValueError("Invalid device public key")
    return ec.EllipticCurvePublicNumbers(
        int.from_bytes(unb64(jwk["x"]), "big"),
        int.from_bytes(unb64(jwk["y"]), "big"),
        ec.SECP256R1(),
    ).public_key()


def key_id(jwk):
    return hashlib.sha256(
        json.dumps(public_jwk(load_public(jwk)), sort_keys=True).encode()
    ).hexdigest()


def verify(envelope, jwk):
    payload, signature = envelope["payload"], unb64(envelope["signature"])
    if not isinstance(payload, str) or len(payload) > 120000 or len(signature) != 64:
        raise ValueError("Invalid signed message")
    der = encode_dss_signature(
        int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
    )
    load_public(jwk).verify(der, payload.encode(), ec.ECDSA(hashes.SHA256()))
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("Invalid message")
    return value


def protect(raw: bytes, decrypt=False):
    """Windows user-scoped DPAPI. Unix development uses owner-only files."""
    if os.name != "nt":
        return raw

    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_char))]

    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    blob_pointer = ctypes.POINTER(Blob)
    crypt.CryptProtectData.argtypes = [
        blob_pointer,
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        blob_pointer,
    ]
    crypt.CryptUnprotectData.argtypes = [
        blob_pointer,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        blob_pointer,
    ]
    crypt.CryptProtectData.restype = crypt.CryptUnprotectData.restype = ctypes.c_int
    if decrypt:
        ok = crypt.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)
        )
    else:
        ok = crypt.CryptProtectData(
            ctypes.byref(source), "Deskpad identity", None, None, None, 1, ctypes.byref(target)
        )
    if not ok:
        raise OSError("Could not access Windows-protected Deskpad identity")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


class Identity:
    def __init__(self, directory: Path):
        self.path = directory / "identity.json"
        if self.path.exists():
            state = json.loads(
                protect(unb64(json.loads(self.path.read_text())["protected"]), decrypt=True)
            )
            self.private = serialization.load_der_private_key(
                unb64(state["private"]), password=None
            )
            self.room, self.owner, self.gate = state["room"], state["owner"], state["gate"]
        else:
            self.private = ec.generate_private_key(ec.SECP256R1())
            self.room, self.owner, self.gate = (secrets.token_urlsafe(32) for _ in range(3))
            raw = self.private.private_bytes(
                serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            # Protect all transport credentials together on Windows as well.
            state = {
                "private": b64(raw),
                "room": self.room,
                "owner": self.owner,
                "gate": self.gate,
            }
            atomic_json(self.path, {"protected": b64(protect(json.dumps(state).encode()))})
            if os.name != "nt":
                self.path.chmod(0o600)
        self.public = public_jwk(self.private.public_key())
        self.devices_path = directory / "remote-devices.json"
        self.devices = (
            json.loads(self.devices_path.read_text()) if self.devices_path.exists() else {}
        )
        self.invite = secrets.token_urlsafe(32)
        self.invite_until = time.time() + 600
        self.seen = {}

    def sign(self, value):
        payload = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        der = self.private.sign(payload.encode(), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        return {"payload": payload, "signature": b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))}

    def check(self, envelope):
        jwk = envelope["key"]
        value = verify(envelope, jwk)
        now = time.time()
        timestamp = value.get("time", 0)
        if (
            not isinstance(timestamp, (int, float))
            or not math.isfinite(timestamp)
            or abs(timestamp - now) > 90
        ):
            raise ValueError("Device clock differs or request expired")
        nonce = value.get("nonce")
        if not isinstance(nonce, str) or not 16 <= len(nonce) <= 128:
            raise ValueError("Invalid request nonce")
        self.seen = {k: expiry for k, expiry in self.seen.items() if expiry > now}
        if nonce in self.seen or len(self.seen) >= 2048:
            raise ValueError("Repeated request")
        self.seen[nonce] = now + 180
        return key_id(jwk), public_jwk(load_public(jwk)), value

    def approve(self, identifier, public, name):
        if len(self.devices) >= 32 and identifier not in self.devices:
            raise ValueError("Remove an approved device first (maximum 32)")
        self.devices[identifier] = {"key": public, "name": str(name)[:64], "approved": time.time()}
        atomic_json(self.devices_path, self.devices)

    def revoke(self, identifier):
        self.devices.pop(identifier, None)
        atomic_json(self.devices_path, self.devices)

    def pairing_code(self, jwk):
        return hashlib.sha256((key_id(self.public) + key_id(jwk)).encode()).hexdigest()[:8].upper()
