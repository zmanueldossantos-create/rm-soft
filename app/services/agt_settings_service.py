"""
The settings of the Faturação Eletrónica (AGT):
- on the platform (SUPER_ADMIN): the environment (Homologação / Produção), the producer's access (Basic Auth, the
  password encrypted), the software's identity (softwareInfoDetail) and its signature (jwsSoftwareSignature). The
  producer's private key is kept on the RM SOFT platform only: there it signs the identity again whenever the identity
  changes; a client's server (local installation) receives the signature's text alone, pasted by our technician;
- on each company: the taxpayer's private key, issued by the AGT on the taxpayer's portal, encrypted (never shown again:
  a screen sees its size and the fingerprint of its public half).
"""
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secret_box import decrypt_secret, encrypt_secret
from app.models.agt_test_taxpayer import AgtTestTaxpayer
from app.models.company import Company
from app.models.platform_settings import PlatformSettings
from app.services import agt_signing
from app.services.platform_settings_service import get_or_create_platform_settings

ENVIRONMENTS = {"HOMOLOGACAO": "https://sifphml.minfin.gov.ao", "PRODUCAO": "https://sifp.minfin.gov.ao"}


class AgtSettingsError(Exception):
    """Refused - the message is shown as it is."""


# ------------------------------------------------------------------------------------------------- the software

def software_detail(platform: PlatformSettings) -> dict | None:
    """softwareInfoDetail, in the AGT's order - None while a part is missing."""
    detail = {"productId": (platform.agt_product_id or "").strip(),
              "productVersion": (platform.product_version or "").strip(),
              "softwareValidationNumber": (platform.software_validation_number or "").strip()}
    if not all(detail.values()):
        return None
    if platform.agt_signature_version is not None:
        detail["signatureVersion"] = platform.agt_signature_version
    return detail


def signature_status(platform: PlatformSettings) -> str:
    """OK | EM_FALTA (no signature, or the identity is incomplete) | DESATUALIZADA (it signs another identity)."""
    detail = software_detail(platform)
    if detail is None or not platform.agt_software_signature:
        return "EM_FALTA"
    return "OK" if agt_signing.payload_of(platform.agt_software_signature) == detail else "DESATUALIZADA"


def refresh_software_signature(platform: PlatformSettings) -> None:
    """With the producer's key here (the platform): the identity signed again - called whenever a part of it changes."""
    key = decrypt_secret(platform.agt_software_key_encrypted)
    detail = software_detail(platform)
    if key and detail:
        platform.agt_software_signature = agt_signing.sign(detail, key)


def platform_view(platform: PlatformSettings) -> dict:
    key = decrypt_secret(platform.agt_software_key_encrypted)
    password = decrypt_secret(platform.agt_password_encrypted)
    return {
        "environment": platform.agt_environment,
        "base_url": ENVIRONMENTS.get(platform.agt_environment),
        "username": platform.agt_username,
        "has_password": bool(password),
        "password_hint": "••••••••" if password else None,  # nothing of a password is shown
        "product_id": platform.agt_product_id,
        "product_version": platform.product_version,
        "software_validation_number": platform.software_validation_number,
        "signature_version": platform.agt_signature_version,
        "has_software_key": bool(key),
        "software_key": agt_signing.key_info(key) if key else None,
        "software_public_key": agt_signing.public_pem(key) if key else None,  # given to the AGT (portal do parceiro)
        "software_signature": platform.agt_software_signature,
        "signature_status": signature_status(platform),
        "signed_detail": software_detail(platform),
    }


async def save_platform(db: AsyncSession, environment: str, username: str | None, password: str | None,
                        product_id: str | None, signature_version: int | None, software_key: str | None,
                        software_signature: str | None) -> dict:
    """password / software_key: None keeps the one saved, "" removes it. software_signature: only used without the
    producer's key (a client's server) - with the key, the signature is always computed here."""
    if environment not in ENVIRONMENTS:
        raise AgtSettingsError("Ambiente AGT inválido")
    if signature_version is not None and signature_version < 0:
        raise AgtSettingsError("Versão da assinatura inválida")
    platform = await get_or_create_platform_settings(db)
    platform.agt_environment = environment
    platform.agt_username = (username or "").strip() or None
    if password is not None:
        platform.agt_password_encrypted = encrypt_secret(password) if password else None
    platform.agt_product_id = (product_id or "").strip() or None
    platform.agt_signature_version = signature_version
    if software_key is not None:
        if software_key.strip():
            agt_signing.load_private_key(software_key)  # refused here when it cannot sign
            platform.agt_software_key_encrypted = encrypt_secret(agt_signing.clean_pem(software_key))
        else:
            platform.agt_software_key_encrypted = None
    if decrypt_secret(platform.agt_software_key_encrypted):
        refresh_software_signature(platform)
    elif software_signature is not None:
        text = software_signature.strip()
        if text and agt_signing.payload_of(text) is None:
            raise AgtSettingsError("Assinatura do software inválida - cole o texto completo dado pela RM SOFT "
                                   "(três partes separadas por pontos)")
        platform.agt_software_signature = text or None
    await db.commit()
    return platform_view(platform)


async def generate_software_key(db: AsyncSession, replace: bool = False) -> dict:
    """The producer's key pair (RSA 2048), made here on the platform: the private half kept encrypted, the public half
    shown to be registered on the AGT's portal do parceiro. Refused when one exists (replace: a new pair - the AGT
    must then receive the new public key, and every client's server the new signature)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    platform = await get_or_create_platform_settings(db)
    if decrypt_secret(platform.agt_software_key_encrypted) and not replace:
        raise AgtSettingsError("Já existe uma chave do produtor - gerar outra obriga a registar a nova chave pública "
                               "na AGT e a dar a nova assinatura a todos os servidores dos clientes")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    platform.agt_software_key_encrypted = encrypt_secret(pem)
    refresh_software_signature(platform)
    await db.commit()
    return platform_view(platform)


# ------------------------------------------------------------------------------------------------- the test NIFs

_TEST_ENTRY = re.compile(r"(\d{9,15})\s+([^\t\n\"]+?)\s*\"*\s*(-----BEGIN (?:RSA )?PRIVATE KEY-----.+?-----END (?:RSA )?PRIVATE KEY-----)",
                         re.S)


def parse_test_file(text: str) -> list[dict]:
    """The AGT's TEST_NIF file as pasted: NIF, name, private key (the public key after it is not needed)."""
    entries = []
    for nif, name, pem in _TEST_ENTRY.findall((text or "").replace("\r", "")):
        entries.append({"nif": nif, "name": name.strip(), "private_key": pem})
    return entries


def _test_view(row: AgtTestTaxpayer) -> dict:
    key = decrypt_secret(row.private_key_encrypted)
    return {"nif": row.nif, "name": row.name, "key": agt_signing.key_info(key) if key else None}


async def list_test_taxpayers(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(select(AgtTestTaxpayer).order_by(AgtTestTaxpayer.nif))).scalars().all()
    return [_test_view(r) for r in rows]


async def import_test_taxpayers(db: AsyncSession, text: str) -> dict:
    """Adds (or replaces the key of) every NIF found in the pasted TEST_NIF file - or in one «NIF name key» entry."""
    entries = parse_test_file(text)
    if not entries:
        raise AgtSettingsError("Nenhum NIF de teste encontrado - cole o conteúdo do ficheiro TEST_NIF da AGT "
                               "(NIF, nome e chave privada)")
    for entry in entries:
        try:
            agt_signing.load_private_key(entry["private_key"])
        except agt_signing.AgtKeyError as e:
            raise AgtSettingsError(f"NIF {entry['nif']}: {e}")
    for entry in entries:
        row = (await db.execute(select(AgtTestTaxpayer).where(AgtTestTaxpayer.nif == entry["nif"]))).scalar_one_or_none()
        if row is None:
            row = AgtTestTaxpayer(nif=entry["nif"], name=entry["name"][:200], private_key_encrypted="")
            db.add(row)
        row.name = entry["name"][:200]
        row.private_key_encrypted = encrypt_secret(agt_signing.clean_pem(entry["private_key"]))
    await db.commit()
    return {"imported": len(entries), "items": await list_test_taxpayers(db)}


async def delete_test_taxpayer(db: AsyncSession, nif: str) -> list[dict]:
    row = (await db.execute(select(AgtTestTaxpayer).where(AgtTestTaxpayer.nif == nif))).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.commit()
    return await list_test_taxpayers(db)


# ------------------------------------------------------------------------------------------------- the taxpayer

def company_key(company: Company) -> str | None:
    return decrypt_secret(company.agt_private_key_encrypted)


async def issuer(db: AsyncSession, platform: PlatformSettings, company: Company) -> tuple[str, str | None, bool]:
    """Who the calls go out as: (NIF, private key, is_test). In Homologação, a company that picked a test NIF sends as
    that NIF with its key; otherwise (and always in Produção) as itself, with its own key."""
    test_nif = getattr(company, "agt_test_nif", None)
    if platform.agt_environment == "HOMOLOGACAO" and test_nif:
        row = (await db.execute(select(AgtTestTaxpayer).where(AgtTestTaxpayer.nif == test_nif))).scalar_one_or_none()
        if row is not None:
            return row.nif, decrypt_secret(row.private_key_encrypted), True
    return company.nif.strip(), company_key(company), False


def missing_parts(platform: PlatformSettings, key: str | None = "", check_key: bool = False) -> list[str]:
    """What still lacks before a call to the AGT can be made (empty: ready). check_key: the issuer's key is needed."""
    missing = []
    if not platform.agt_username or not decrypt_secret(platform.agt_password_encrypted):
        missing.append("Credenciais de acesso à AGT (plataforma RM SOFT)")
    status = signature_status(platform)
    if status == "EM_FALTA":
        missing.append("Identificação e assinatura do software (plataforma RM SOFT)")
    elif status == "DESATUALIZADA":
        missing.append("Assinatura do software desatualizada (a identificação mudou - gere-a de novo na plataforma)")
    if check_key and not key:
        missing.append("Chave privada do contribuinte (portal da AGT)")
    return missing


async def company_view(db: AsyncSession, company: Company) -> dict:
    platform = await get_or_create_platform_settings(db)
    own_key = company_key(company)
    nif, key, is_test = await issuer(db, platform, company)
    homologation = platform.agt_environment == "HOMOLOGACAO"
    return {
        "nif": company.nif,
        "issuance_mode": company.issuance_mode.value if hasattr(company.issuance_mode, "value") else company.issuance_mode,
        "environment": platform.agt_environment,
        "has_key": bool(own_key),
        "key": agt_signing.key_info(own_key) if own_key else None,
        # Homologação: the test NIFs offered, the one picked, and the NIF the calls go out as now
        "test_nifs": [{"nif": t["nif"], "name": t["name"]} for t in await list_test_taxpayers(db)] if homologation else [],
        "test_nif": company.agt_test_nif if homologation else None,
        "sending_as": nif,
        "sending_as_test": is_test,
        "missing": missing_parts(platform, key, check_key=True),
    }


async def save_company_test_nif(db: AsyncSession, company: Company, nif: str | None) -> dict:
    """The test NIF this company sends as in Homologação (None: its own NIF)."""
    nif = (nif or "").strip() or None
    if nif is not None:
        exists = (await db.execute(select(AgtTestTaxpayer.id).where(AgtTestTaxpayer.nif == nif))).scalar_one_or_none()
        if exists is None:
            raise AgtSettingsError("NIF de teste desconhecido")
    company.agt_test_nif = nif
    await db.commit()
    return await company_view(db, company)


async def save_company_key(db: AsyncSession, company: Company, pem: str | None) -> dict:
    """pem empty: the key is removed."""
    if (pem or "").strip():
        agt_signing.load_private_key(pem)
        company.agt_private_key_encrypted = encrypt_secret(agt_signing.clean_pem(pem))
    else:
        company.agt_private_key_encrypted = None
    await db.commit()
    return await company_view(db, company)
