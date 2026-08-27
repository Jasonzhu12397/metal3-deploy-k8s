"""
Symmetric (reversible) encryption for the one class of secret this app
actually needs to read back later: stored BMC credentials, so an operator
doesn't have to re-type them to recreate a Kubernetes Secret that got
deleted, or to rotate/inspect what's on file.

This is a fundamentally different problem from user login passwords
(core/security.py / services/auth.py), which are hashed one-way with
bcrypt and never need to be recovered -- only verified. BMC credentials
have to come back out as plaintext eventually, because this app has to
hand them to the Kubernetes API as a Secret's actual value. Hashing them
would make that impossible; that's why this is a separate module using a
completely different primitive (Fernet symmetric encryption, not bcrypt).

Key management is the entire security property here: BMC_ENCRYPTION_KEY
must live outside this database (env var / mounted Secret / KMS) --
storing the key next to the ciphertext it decrypts is equivalent to no
encryption at all. Losing the key means every previously-encrypted
credential becomes permanently unrecoverable (there is no backdoor, by
design); rotating it requires decrypting every row with the old key and
re-encrypting with the new one before the old key can be discarded (see
`rotate_key` below).
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import get_settings


class EncryptionKeyNotConfigured(RuntimeError):
    """Raised instead of silently storing plaintext or refusing to start.
    Registering a BareMetalHost without BMC_ENCRYPTION_KEY set should fail
    loudly at the point credentials would be encrypted, not fall back to
    some weaker default."""


def _get_fernet() -> Fernet | MultiFernet:
    settings = get_settings()
    keys = [k.strip() for k in (settings.BMC_ENCRYPTION_KEY or "").split(",") if k.strip()]
    if not keys:
        raise EncryptionKeyNotConfigured(
            "BMC_ENCRYPTION_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"` "
            "and set it in the environment (never commit it, never store it in this database). "
            "See INSTALL.md for details."
        )
    # A comma-separated list lets you rotate keys without a hard cutover:
    # put the new key first (used for all new encryption) and keep the old
    # key(s) after it (still accepted for decrypting rows not yet
    # re-encrypted) -- see rotate_key().
    try:
        fernets = [Fernet(k.encode()) for k in keys]
    except ValueError as exc:
        raise EncryptionKeyNotConfigured(
            "BMC_ENCRYPTION_KEY is set but isn't a valid Fernet key "
            "(must be 32 url-safe base64-encoded bytes, i.e. exactly what "
            "Fernet.generate_key() produces)."
        ) from exc
    return fernets[0] if len(fernets) == 1 else MultiFernet(fernets)


def encrypt_secret(plaintext: str) -> str:
    """Returns ciphertext safe to store in a text column. Always encrypts
    with the *first* configured key."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Raises EncryptionKeyNotConfigured if no key is set, or
    cryptography.fernet.InvalidToken if the ciphertext doesn't match any
    configured key (wrong/rotated-away key, or corrupted data) -- callers
    should let InvalidToken propagate as a clear 5xx rather than quietly
    treating it as "no credentials stored"; those are different failure
    modes and conflating them hides a real operational problem."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def rotate_key(ciphertext: str, old_and_new_keys: list[str]) -> str:
    """Re-encrypts a single value under the first key in
    `old_and_new_keys`, given it can be decrypted by *any* key in that
    list. Callers doing a real rotation should: (1) set
    BMC_ENCRYPTION_KEY to "new_key,old_key", (2) run this over every
    stored credential to re-encrypt under new_key, (3) once all rows are
    migrated, set BMC_ENCRYPTION_KEY to just "new_key" and discard the old
    one. Exists as a named, tested operation rather than leaving key
    rotation as an exercise for whoever needs it under pressure later."""
    fernets = [Fernet(k.encode()) for k in old_and_new_keys]
    multi = MultiFernet(fernets)
    plaintext = multi.decrypt(ciphertext.encode())
    return fernets[0].encrypt(plaintext).decode()


__all__ = ["encrypt_secret", "decrypt_secret", "rotate_key", "EncryptionKeyNotConfigured", "InvalidToken"]
