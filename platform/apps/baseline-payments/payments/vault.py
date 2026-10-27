"""Sealing of NPI values at rest.

This is the demo platform's stand-in for the bank's key service: an
HMAC-SHA256 keystream with an HMAC-SHA256 tag (encrypt-then-MAC), with keys
derived from a fixed demo secret. It is not a production cipher.
"""

import base64
import hashlib
import hmac
import os

DEMO_MASTER_SECRET = b"payments-demo-master-secret-v1"
PREFIX = "llv"
NONCE_BYTES = 16
TAG_BYTES = 32


class SealError(Exception):
    """A sealed value could not be opened: malformed, unknown key version or tampered."""


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks = []
    counter = 0
    while sum(len(block) for block in blocks) < length:
        blocks.append(hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest())
        counter += 1
    return b"".join(blocks)[:length]


def _xor(data: bytes, stream: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, stream))


def is_sealed(value: object) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX) and ":" in value


class Vault:
    def __init__(self, master_secret: bytes = DEMO_MASTER_SECRET, nonce_source=os.urandom) -> None:
        self._master = master_secret
        self._nonce_source = nonce_source
        self._active_version = 1

    @property
    def active_version(self) -> int:
        return self._active_version

    def rotate(self) -> int:
        """Start sealing with a new key version. Older versions can still be opened."""
        self._active_version += 1
        return self._active_version

    def seal(self, plaintext: str) -> str:
        version = self._active_version
        enc_key, mac_key = self._keys(version)
        nonce = self._nonce_source(NONCE_BYTES)
        data = plaintext.encode("utf-8")
        body = _xor(data, _keystream(enc_key, nonce, len(data)))
        tag = self._tag(mac_key, version, nonce, body)
        blob = base64.urlsafe_b64encode(nonce + body + tag).decode("ascii")
        return f"{PREFIX}{version}:{blob}"

    def open(self, sealed: str) -> str:
        version, raw = self._parse(sealed)
        enc_key, mac_key = self._keys(version)
        nonce = raw[:NONCE_BYTES]
        body = raw[NONCE_BYTES:-TAG_BYTES]
        tag = raw[-TAG_BYTES:]
        if not hmac.compare_digest(tag, self._tag(mac_key, version, nonce, body)):
            raise SealError("sealed value failed authentication")
        return _xor(body, _keystream(enc_key, nonce, len(body))).decode("utf-8")

    def version_of(self, sealed: str) -> int:
        return self._parse(sealed)[0]

    def _parse(self, sealed: str) -> tuple[int, bytes]:
        if not is_sealed(sealed):
            raise SealError("value is not sealed")
        head, blob = sealed.split(":", 1)
        version_text = head[len(PREFIX):]
        if not version_text.isdigit():
            raise SealError("malformed key version")
        version = int(version_text)
        if version < 1 or version > self._active_version:
            raise SealError("unknown key version")
        raw = base64.urlsafe_b64decode(blob.encode("ascii"))
        if len(raw) < NONCE_BYTES + TAG_BYTES:
            raise SealError("sealed value is truncated")
        return version, raw

    def _keys(self, version: int) -> tuple[bytes, bytes]:
        label = str(version).encode("ascii")
        enc_key = hmac.new(self._master, b"enc:" + label, hashlib.sha256).digest()
        mac_key = hmac.new(self._master, b"mac:" + label, hashlib.sha256).digest()
        return enc_key, mac_key

    def _tag(self, mac_key: bytes, version: int, nonce: bytes, body: bytes) -> bytes:
        header = f"{PREFIX}{version}:".encode("ascii")
        return hmac.new(mac_key, header + nonce + body, hashlib.sha256).digest()
