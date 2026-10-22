"""
Creates the RM SOFT licence keys - ONCE, on the platform's machine:

    python -m app.tools.license_keys

  - the private key is added to .env (LICENSE_PRIVATE_KEY=...): it signs the licences; never commit .env, never send it;
  - the public key is written in app/core/license_key.py: commit it - every installation checks the licences with it.

Refused when a public key exists already: a new pair would make every licence issued invalid (--force to do it anyway).
Nothing secret is printed.
"""
import base64
import re
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parent.parent.parent
KEY_FILE = ROOT / "app" / "core" / "license_key.py"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def main(argv: list[str]) -> int:
    env_file = ROOT / ".env"
    text = KEY_FILE.read_text(encoding="utf-8")
    if re.search(r'PUBLIC_KEY = "[^"]+"', text) and "--force" not in argv:
        print("Já existe uma chave pública em app/core/license_key.py - nada foi alterado.")
        print("Uma nova chave invalida TODAS as licenças emitidas. Para a criar mesmo assim: --force")
        return 1
    if env_file.exists() and "LICENSE_PRIVATE_KEY=" in env_file.read_text(encoding="utf-8") and "--force" not in argv:
        print("O .env já tem LICENSE_PRIVATE_KEY - nada foi alterado (--force para substituir).")
        return 1
    private = Ed25519PrivateKey.generate()
    private_b64 = _b64(private.private_bytes_raw())
    public_b64 = _b64(private.public_key().public_bytes_raw())

    lines = [line for line in (env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else [])
             if not line.startswith("LICENSE_PRIVATE_KEY=")]
    lines.append("LICENSE_PRIVATE_KEY=" + private_b64)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    KEY_FILE.write_text(re.sub(r'PUBLIC_KEY = "[^"]*"', f'PUBLIC_KEY = "{public_b64}"', text), encoding="utf-8")
    print("Chave privada guardada no .env (LICENSE_PRIVATE_KEY) - não a envie a ninguém, não a ponha no git.")
    print("Chave pública escrita em app/core/license_key.py - faça commit deste ficheiro.")
    print("Reinicie o backend: o botão «Gerar licença» fica disponível no separador Contrato.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
