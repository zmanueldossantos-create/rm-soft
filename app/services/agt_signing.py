"""
The JWS signatures of the AGT's Faturação Eletrónica (RS256 - RSA + SHA-256, compact serialization):
- jwsSoftwareSignature: the software's identity (softwareInfoDetail), signed with the PRODUCER's key (RM SOFT) - the
  same text for the same identity, so it is computed once on the platform and only the text travels;
- jwsDocumentSignature and jwsSignature: a document and a call, signed with the TAXPAYER's key (issued by the AGT,
  on the taxpayer's portal).

The signed object is the JSON itself (never the fields put together), canonical: no spaces, no line breaks, double
quotes, the keys in the order of the AGT's specification. Base64URL without «=».
"""
import base64
import hashlib
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

HEADER = {"alg": "RS256", "typ": "JWT"}
MIN_BITS = 2048


class AgtKeyError(Exception):
    """A key that cannot be used - the message is shown as it is."""


def canonical(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def clean_pem(text: str | None) -> str:
    """The key as pasted: also accepts the AGT's file format (between triple quotes, «\\n» written out)."""
    text = (text or "").strip().strip('"').strip("'").strip()
    if "\\n" in text and "\n" not in text:
        text = text.replace("\\n", "\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines) + "\n" if lines else ""


def load_private_key(pem: str) -> rsa.RSAPrivateKey:
    try:
        key = serialization.load_pem_private_key(clean_pem(pem).encode(), password=None)
    except (ValueError, TypeError):
        raise AgtKeyError("Chave privada inválida - cole o texto completo, de «-----BEGIN PRIVATE KEY-----» "
                          "a «-----END PRIVATE KEY-----»")
    if not isinstance(key, rsa.RSAPrivateKey):
        raise AgtKeyError("A chave tem de ser RSA")
    if key.key_size < MIN_BITS:
        raise AgtKeyError(f"Chave RSA demasiado curta ({key.key_size} bits) - mínimo {MIN_BITS}")
    return key


def key_info(pem: str) -> dict:
    """What a screen may show of a private key: its size and the fingerprint of its PUBLIC half."""
    public = load_private_key(pem).public_key()
    der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    digest = hashlib.sha256(der).hexdigest()[:16].upper()
    return {"bits": public.key_size, "fingerprint": ":".join(digest[i:i + 4] for i in range(0, 16, 4))}


def public_pem(pem: str) -> str:
    return load_private_key(pem).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def sign(payload: dict, pem: str) -> str:
    """header.payload.signature (RS256) of the object as it is (its keys in the order given)."""
    key = load_private_key(pem)
    signing_input = b64url(canonical(HEADER)) + "." + b64url(canonical(payload))
    signature = key.sign(signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return signing_input + "." + b64url(signature)


def payload_of(token: str | None) -> dict | None:
    """The object a JWS carries (read without any key) - None when the text is not a JWS."""
    try:
        header, payload, signature = (token or "").strip().split(".")
        value = json.loads(_unb64url(payload))
        return value if isinstance(value, dict) else None
    except (ValueError, TypeError):
        return None


def verify(token: str, public_key_pem: str) -> bool:
    """For the tests and the checks: is this JWS signed by the private half of this public key?"""
    try:
        header, payload, signature = token.split(".")
        key = serialization.load_pem_public_key(public_key_pem.encode())
        key.verify(_unb64url(signature), (header + "." + payload).encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
        return True
    except (ValueError, InvalidSignature):
        return False
