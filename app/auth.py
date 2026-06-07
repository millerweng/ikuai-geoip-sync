from __future__ import annotations

import json
import logging
import os
import secrets
import threading
from pathlib import Path

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

log = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
AUTH_FILE = DATA_DIR / "auth.json"

_SESSION_TTL = 86400 * 30  # 30 days
_lock = threading.Lock()
_signer: TimestampSigner | None = None
_pw_hash: bytes | None = None


def _load() -> None:
    global _signer, _pw_hash
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if AUTH_FILE.exists():
        try:
            data = json.loads(AUTH_FILE.read_text())
            _pw_hash = data.get("pw_hash", "").encode() or None
            secret = data.get("secret", "")
        except Exception:
            log.exception("failed to load auth.json")
            _pw_hash = None
            secret = ""
    else:
        _pw_hash = None
        secret = ""

    if not secret:
        secret = secrets.token_hex(32)
        _save_secret(secret)

    _signer = TimestampSigner(secret)


def _save_secret(secret: str) -> None:
    existing: dict = {}
    if AUTH_FILE.exists():
        try:
            existing = json.loads(AUTH_FILE.read_text())
        except Exception:
            pass
    existing["secret"] = secret
    AUTH_FILE.write_text(json.dumps(existing, indent=2))


def is_password_set() -> bool:
    with _lock:
        return bool(_pw_hash)


def set_password(plain: str) -> None:
    global _pw_hash
    if not plain or len(plain) < 6:
        raise ValueError("password must be at least 6 characters")
    hashed = bcrypt.hashpw(plain.encode(), bcrypt.gensalt())
    with _lock:
        _pw_hash = hashed
        data: dict = {}
        if AUTH_FILE.exists():
            try:
                data = json.loads(AUTH_FILE.read_text())
            except Exception:
                pass
        data["pw_hash"] = hashed.decode()
        AUTH_FILE.write_text(json.dumps(data, indent=2))
    log.info("admin password updated")


def verify_password(plain: str) -> bool:
    with _lock:
        if not _pw_hash:
            return False
        return bcrypt.checkpw(plain.encode(), _pw_hash)


def make_session_token() -> str:
    assert _signer is not None
    return _signer.sign("admin").decode()


def validate_session_token(token: str) -> bool:
    assert _signer is not None
    try:
        _signer.unsign(token, max_age=_SESSION_TTL)
        return True
    except (BadSignature, SignatureExpired):
        return False


_load()
