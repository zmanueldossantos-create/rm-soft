"""
Licença de uma instalação local - a file signed by RM SOFT that says what one company may use on ONE server.

  RM SOFT (the platform, which holds the private key: LICENSE_PRIVATE_KEY, never in the code) makes the file from the
  company's contract and the installation code the client's server shows ("Gerar licença").
  The client's server (LICENSE_REQUIRED=true) checks the signature with the public key written in the code
  (app/core/license_key.py), without internet: the plan, the limits, the options and the dates then come from the
  licence, never from the database - a changed file or a changed database no longer matches its signature.

A licence is valid only for its company (NIF) on its server (installation code): copied to another server it is
refused. The server's 9 workstations open the application in a browser - they need nothing.

The file: "RMSOFT-LICENCA-1." + base64url(JSON) + "." + base64url(Ed25519 signature of the JSON bytes).
"""
import base64
import hashlib
import json
import os
import platform
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

PREFIX = "RMSOFT-LICENCA-1."


class LicenseError(Exception):
    """Raised when a licence file is refused (unreadable, signature, another company, another server) - PT-PT."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ------------------------------------------------------------------------------------------------- the server's code

def _machine_identity() -> str:
    """Something only this machine has: Linux /etc/machine-id (Docker: mount the host's), Windows MachineGuid. Else
    a random identity kept in a file next to the application (weaker: copied with the folder).
    RMSOFT_MACHINE_ID first: Docker Desktop on a Windows server, where the container cannot read the host's registry -
    the installation kit (docker/cliente/instalar.ps1) writes the host's MachineGuid there."""
    given = (os.getenv("RMSOFT_MACHINE_ID") or "").strip()
    if given:
        return given
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            value = Path(path).read_text().strip()
            if value:
                return value
        except OSError:
            pass
    if platform.system() == "Windows":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                return str(winreg.QueryValueEx(key, "MachineGuid")[0])
        except OSError:
            pass
    keep = Path(os.getenv("RMSOFT_INSTALLATION_FILE", ".rmsoft_installation"))
    if not keep.exists():
        keep.write_text(uuid.uuid4().hex)
    return keep.read_text().strip()


def installation_code() -> str:
    """The code this server shows, to be sent to RM SOFT: XXXX-XXXX-XXXX-XXXX (derived, the identity itself is never
    shown)."""
    digest = hashlib.sha256(("rm-soft-installation:" + _machine_identity()).encode()).hexdigest()[:16].upper()
    return "-".join(digest[i:i + 4] for i in range(0, 16, 4))


def normalize_code(code: str) -> str:
    raw = "".join(ch for ch in (code or "").upper() if ch.isalnum())
    if len(raw) != 16 or any(ch not in "0123456789ABCDEF" for ch in raw):
        raise LicenseError("Código de instalação inválido (16 caracteres, ex.: 3F2A-91C0-7B4E-D218)")
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


# ------------------------------------------------------------------------------------------------- signing, checking

def _public_key() -> Ed25519PublicKey | None:
    from app.core import license_key
    raw = (license_key.PUBLIC_KEY or "").strip()
    return Ed25519PublicKey.from_public_bytes(_unb64(raw)) if raw else None


def _private_key() -> Ed25519PrivateKey | None:
    from app.core.config import get_settings
    raw = (get_settings().LICENSE_PRIVATE_KEY or "").strip()
    return Ed25519PrivateKey.from_private_bytes(_unb64(raw)) if raw else None


def can_sign() -> bool:
    """This server holds the private key (the RM SOFT platform) and it matches the public key in the code."""
    private, public = _private_key(), _public_key()
    if private is None or public is None:
        return False
    return private.public_key().public_bytes_raw() == public.public_bytes_raw()


def sign_license(data: dict) -> str:
    private = _private_key()
    if private is None or not can_sign():
        raise LicenseError("Este servidor não tem a chave de licenças da RM SOFT (LICENSE_PRIVATE_KEY)")
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return PREFIX + _b64(payload) + "." + _b64(private.sign(payload))


def read_license(text: str) -> dict:
    """The licence's content once its signature is checked - LicenseError otherwise."""
    public = _public_key()
    if public is None:
        raise LicenseError("Esta versão não tem a chave pública das licenças - contacte a RM SOFT")
    text = "".join((text or "").split())  # pasted from an email: line breaks and spaces do not matter
    if not text.startswith(PREFIX) or text.count(".") != 2:
        raise LicenseError("Este ficheiro não é uma licença RM SOFT")
    body, signature = text[len(PREFIX):].split(".")
    try:
        payload = _unb64(body)
        public.verify(_unb64(signature), payload)
        return json.loads(payload)
    except (InvalidSignature, ValueError):
        raise LicenseError("Licença inválida: a assinatura não corresponde (ficheiro alterado ou não emitido pela RM SOFT)")
