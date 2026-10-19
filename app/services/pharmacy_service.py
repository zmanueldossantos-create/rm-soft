"""
Farmácia (capability PHARMACY, app.core.capabilities): the medicines of a pharmacy and their managed list of
pharmaceutical forms.

A medicine is a product with, on top of the usual sheet:
- its active substance (DCI): the counter finds every brand of it ("paracetamol" -> Ben-u-ron, Panadol...);
- its pharmaceutical form (Comprimido, Xarope... - the GESTOR's list) and its dosage (500 mg);
- its dispensing regime: LIVRE (MNSRM), RECEITA (MSRM) or RECEITA_ESPECIAL (psychotropics and narcotics) - what the
  sale will ask (livraison 2);
- "conservar no frio", a plain indication shown at the counter.
It is always followed by stock, lot and expiry (FEFO, an expired lot is never sold): forced here, whatever the form
sends. Only a company with the Farmácia capability (one of its granted modules gives it) may have medicines - read
from its modules whatever ENFORCE_CAPABILITIES says, so a Bar never sees the medicine fields.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pharmaceutical_form import PharmaceuticalForm

PHARMACY = "PHARMACY"
DISPENSING_REGIMES = ("LIVRE", "RECEITA", "RECEITA_ESPECIAL")
# The AGT exemption motive of medicines (CIVA art. 12.º nº1 b), annex 9.1 of the AGT documentation) - only PROPOSED
# by the product form when "Medicamento" is ticked: the motive itself is data (vat_codes), the GESTOR may change it.
MEDICINE_EXEMPTION_CODE = "M11"


class MedicineError(Exception):
    """A medicine sheet that cannot be saved (missing substance, unknown form, company without the Farmácia)."""


class PharmaceuticalFormNotFoundError(Exception):
    pass


class PharmaceuticalFormAlreadyExistsError(Exception):
    pass


async def pharmacy_enabled(db: AsyncSession, company_id: uuid.UUID) -> bool:
    """True when one of the company's granted, enabled, active modules gives the Farmácia capability."""
    from app.services.sector_service import get_company_capabilities  # lazy: sector_service imports permission_service
    return PHARMACY in await get_company_capabilities(db, company_id)


def _clean(value: str | None) -> str | None:
    cleaned = " ".join((value or "").split())
    return cleaned or None


async def medicine_fields(
    db: AsyncSession, company_id: uuid.UUID, *, is_medicine: bool, active_substance: str | None,
    pharmaceutical_form_id: uuid.UUID | None, dosage: str | None, dispensing_regime: str | None, cold_storage: bool,
    is_raw_material: bool, current_form_id: uuid.UUID | None = None,
) -> dict:
    """
    The pharmacy fields to save on a product, checked. A product that is not a medicine carries none of them; a
    medicine needs its substance and its dispensing regime, an active form of the company (the one it already has is
    kept even if deactivated since), and is followed by stock, lot and expiry.
    """
    if not is_medicine:
        return {"is_medicine": False, "active_substance": None, "pharmaceutical_form_id": None, "dosage": None,
                "dispensing_regime": None, "cold_storage": False}
    if not await pharmacy_enabled(db, company_id):
        raise MedicineError("A empresa não tem o setor Farmácia: um produto não pode ser marcado como medicamento")
    if is_raw_material:
        raise MedicineError("Uma matéria-prima não pode ser um medicamento")
    substance = _clean(active_substance)
    if substance is None:
        raise MedicineError("A substância ativa (DCI) é obrigatória para um medicamento")
    if dispensing_regime not in DISPENSING_REGIMES:
        raise MedicineError("Indique o regime de dispensa do medicamento (venda livre, receita médica ou receita especial)")
    if pharmaceutical_form_id is not None:
        form = (await db.execute(select(PharmaceuticalForm).where(
            PharmaceuticalForm.id == pharmaceutical_form_id, PharmaceuticalForm.company_id == company_id,
        ))).scalar_one_or_none()
        if form is None or (not form.is_active and pharmaceutical_form_id != current_form_id):
            raise MedicineError("Forma farmacêutica inválida ou inativa")
    return {
        "is_medicine": True, "active_substance": substance, "pharmaceutical_form_id": pharmaceutical_form_id,
        "dosage": _clean(dosage), "dispensing_regime": dispensing_regime, "cold_storage": bool(cold_storage),
        # always followed: the lot and the expiry are asked at every entry, the first to expire is sold first
        "managed_by_stock": True, "managed_by_batch": True, "managed_by_expiry": True,
    }


async def pharmacy_context(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """What the product form needs: is the Farmácia on, the forms to choose from, and the medicine exemption motive
    to propose (None when the platform has no active M11)."""
    from app.models.vat_code import VatCode
    enabled = await pharmacy_enabled(db, company_id)
    motive = None
    if enabled:
        row = (await db.execute(select(VatCode).where(
            VatCode.code == MEDICINE_EXEMPTION_CODE, VatCode.is_active.is_(True),
        ))).scalars().first()
        if row is not None:
            motive = {"id": str(row.id), "code": row.code, "name": row.name}
    return {"enabled": enabled, "medicine_exemption": motive,
            "forms": [{"id": str(f.id), "name": f.name, "is_active": f.is_active}
                      for f in await list_forms(db, company_id)] if enabled else []}


# ---------- The managed list of pharmaceutical forms

async def list_forms(db: AsyncSession, company_id: uuid.UUID) -> list[PharmaceuticalForm]:
    return list((await db.execute(
        select(PharmaceuticalForm).where(PharmaceuticalForm.company_id == company_id).order_by(PharmaceuticalForm.name)
    )).scalars().all())


async def _check_name_free(db: AsyncSession, company_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None) -> str:
    cleaned = _clean(name)
    if cleaned is None:
        raise MedicineError("O nome da forma farmacêutica é obrigatório")
    query = select(PharmaceuticalForm.id).where(
        PharmaceuticalForm.company_id == company_id, func.lower(PharmaceuticalForm.name) == cleaned.lower())
    if exclude_id is not None:
        query = query.where(PharmaceuticalForm.id != exclude_id)
    if (await db.execute(query)).first() is not None:
        raise PharmaceuticalFormAlreadyExistsError(f"Já existe uma forma farmacêutica chamada '{cleaned}'")
    return cleaned


async def create_form(db: AsyncSession, company_id: uuid.UUID, name: str) -> PharmaceuticalForm:
    form = PharmaceuticalForm(company_id=company_id, name=await _check_name_free(db, company_id, name))
    db.add(form)
    await db.commit()
    await db.refresh(form)
    return form


async def _get_form(db: AsyncSession, company_id: uuid.UUID, form_id: uuid.UUID) -> PharmaceuticalForm:
    form = (await db.execute(select(PharmaceuticalForm).where(
        PharmaceuticalForm.id == form_id, PharmaceuticalForm.company_id == company_id,
    ))).scalar_one_or_none()
    if form is None:
        raise PharmaceuticalFormNotFoundError("Forma farmacêutica não encontrada")
    return form


async def update_form(db: AsyncSession, company_id: uuid.UUID, form_id: uuid.UUID, name: str) -> PharmaceuticalForm:
    form = await _get_form(db, company_id, form_id)
    form.name = await _check_name_free(db, company_id, name, exclude_id=form_id)
    await db.commit()
    await db.refresh(form)
    return form


async def toggle_form(db: AsyncSession, company_id: uuid.UUID, form_id: uuid.UUID) -> PharmaceuticalForm:
    """Deactivated, a form is no longer offered; the medicines that have it keep it."""
    form = await _get_form(db, company_id, form_id)
    form.is_active = not form.is_active
    await db.commit()
    await db.refresh(form)
    return form
