"""
Business logic for the 8 platform-wide base catalogs (Paises, Moedas,
Provincias, Municipios, Bancos, Metodos de Pagamento, Condicoes de
Pagamento, Codigos IVA) - all SUPER_ADMIN managed, all company-agnostic.
See discussion on the "Configuracoes" admin screen (cards per category).
"""
import re
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.country import Country
from app.models.currency import Currency
from app.models.province import Province
from app.models.municipality import Municipality
from app.models.bank import Bank
from app.models.denomination import Denomination
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.payment_term import PaymentTerm
from app.models.vat_code import VatCode
from app.models.document_type import DocumentType
from app.models.movement_type import MovementType
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.models.withholding_tax import WithholdingTax


class CatalogItemNotFoundError(Exception):
    pass


# ---------- Country ----------

async def list_countries(db: AsyncSession) -> list[Country]:
    result = await db.execute(select(Country).order_by(Country.name))
    return list(result.scalars().all())


async def create_country(db: AsyncSession, code: str, name: str) -> Country:
    country = Country(code=code, name=name)
    db.add(country)
    await db.commit()
    await db.refresh(country)
    return country


async def update_country(db: AsyncSession, country_id: uuid.UUID, code: str, name: str) -> Country:
    result = await db.execute(select(Country).where(Country.id == country_id))
    country = result.scalar_one_or_none()
    if country is None:
        raise CatalogItemNotFoundError("Pais nao encontrado")
    country.code = code
    country.name = name
    await db.commit()
    await db.refresh(country)
    return country


async def toggle_country(db: AsyncSession, country_id: uuid.UUID) -> Country:
    result = await db.execute(select(Country).where(Country.id == country_id))
    country = result.scalar_one_or_none()
    if country is None:
        raise CatalogItemNotFoundError("Pais nao encontrado")
    country.is_active = not country.is_active
    await db.commit()
    await db.refresh(country)
    return country


# ---------- Currency ----------

async def list_currencies(db: AsyncSession) -> list[Currency]:
    result = await db.execute(select(Currency).order_by(Currency.name))
    return list(result.scalars().all())


async def create_currency(db: AsyncSession, code: str, name: str, symbol: str | None) -> Currency:
    currency = Currency(code=code, name=name, symbol=symbol)
    db.add(currency)
    await db.commit()
    await db.refresh(currency)
    return currency


async def update_currency(db: AsyncSession, currency_id: uuid.UUID, code: str, name: str, symbol: str | None) -> Currency:
    result = await db.execute(select(Currency).where(Currency.id == currency_id))
    currency = result.scalar_one_or_none()
    if currency is None:
        raise CatalogItemNotFoundError("Moeda nao encontrada")
    currency.code = code
    currency.name = name
    currency.symbol = symbol
    await db.commit()
    await db.refresh(currency)
    return currency


async def toggle_currency(db: AsyncSession, currency_id: uuid.UUID) -> Currency:
    result = await db.execute(select(Currency).where(Currency.id == currency_id))
    currency = result.scalar_one_or_none()
    if currency is None:
        raise CatalogItemNotFoundError("Moeda nao encontrada")
    currency.is_active = not currency.is_active
    await db.commit()
    await db.refresh(currency)
    return currency


# ---------- Province ----------

async def list_provinces(db: AsyncSession, country_id: uuid.UUID | None = None) -> list[Province]:
    query = select(Province)
    if country_id is not None:
        query = query.where(Province.country_id == country_id)
    result = await db.execute(query.order_by(Province.name))
    return list(result.scalars().all())


async def create_province(db: AsyncSession, country_id: uuid.UUID, name: str) -> Province:
    province = Province(country_id=country_id, name=name)
    db.add(province)
    await db.commit()
    await db.refresh(province)
    return province


async def update_province(db: AsyncSession, province_id: uuid.UUID, country_id: uuid.UUID, name: str) -> Province:
    result = await db.execute(select(Province).where(Province.id == province_id))
    province = result.scalar_one_or_none()
    if province is None:
        raise CatalogItemNotFoundError("Provincia nao encontrada")
    province.country_id = country_id
    province.name = name
    await db.commit()
    await db.refresh(province)
    return province


async def toggle_province(db: AsyncSession, province_id: uuid.UUID) -> Province:
    result = await db.execute(select(Province).where(Province.id == province_id))
    province = result.scalar_one_or_none()
    if province is None:
        raise CatalogItemNotFoundError("Provincia nao encontrada")
    province.is_active = not province.is_active
    await db.commit()
    await db.refresh(province)
    return province


# ---------- Municipality ----------

async def list_municipalities(db: AsyncSession, province_id: uuid.UUID | None = None) -> list[Municipality]:
    query = select(Municipality)
    if province_id is not None:
        query = query.where(Municipality.province_id == province_id)
    result = await db.execute(query.order_by(Municipality.name))
    return list(result.scalars().all())


async def create_municipality(db: AsyncSession, province_id: uuid.UUID, name: str) -> Municipality:
    municipality = Municipality(province_id=province_id, name=name)
    db.add(municipality)
    await db.commit()
    await db.refresh(municipality)
    return municipality


async def update_municipality(db: AsyncSession, municipality_id: uuid.UUID, province_id: uuid.UUID, name: str) -> Municipality:
    result = await db.execute(select(Municipality).where(Municipality.id == municipality_id))
    municipality = result.scalar_one_or_none()
    if municipality is None:
        raise CatalogItemNotFoundError("Municipio nao encontrado")
    municipality.province_id = province_id
    municipality.name = name
    await db.commit()
    await db.refresh(municipality)
    return municipality


async def toggle_municipality(db: AsyncSession, municipality_id: uuid.UUID) -> Municipality:
    result = await db.execute(select(Municipality).where(Municipality.id == municipality_id))
    municipality = result.scalar_one_or_none()
    if municipality is None:
        raise CatalogItemNotFoundError("Municipio nao encontrado")
    municipality.is_active = not municipality.is_active
    await db.commit()
    await db.refresh(municipality)
    return municipality


# ---------- Bank ----------

async def list_banks(db: AsyncSession) -> list[Bank]:
    result = await db.execute(select(Bank).order_by(Bank.acronym))
    return list(result.scalars().all())


async def create_bank(db: AsyncSession, acronym: str, full_name: str) -> Bank:
    bank = Bank(acronym=acronym, full_name=full_name)
    db.add(bank)
    await db.commit()
    await db.refresh(bank)
    return bank


async def update_bank(db: AsyncSession, bank_id: uuid.UUID, acronym: str, full_name: str) -> Bank:
    result = await db.execute(select(Bank).where(Bank.id == bank_id))
    bank = result.scalar_one_or_none()
    if bank is None:
        raise CatalogItemNotFoundError("Banco nao encontrado")
    bank.acronym = acronym
    bank.full_name = full_name
    await db.commit()
    await db.refresh(bank)
    return bank


async def toggle_bank(db: AsyncSession, bank_id: uuid.UUID) -> Bank:
    result = await db.execute(select(Bank).where(Bank.id == bank_id))
    bank = result.scalar_one_or_none()
    if bank is None:
        raise CatalogItemNotFoundError("Banco nao encontrado")
    bank.is_active = not bank.is_active
    await db.commit()
    await db.refresh(bank)
    return bank


async def list_denominations_catalog(db: AsyncSession) -> list[Denomination]:
    result = await db.execute(select(Denomination).order_by(Denomination.denomination_type, Denomination.value.desc()))
    return list(result.scalars().all())


async def create_denomination(db: AsyncSession, currency_id: uuid.UUID, value: float, denomination_type: str) -> Denomination:
    existing = await db.execute(
        select(Denomination).where(
            Denomination.currency_id == currency_id,
            Denomination.value == value,
            Denomination.denomination_type == denomination_type,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise CatalogItemNotFoundError("Esta denominacao ja existe para esta moeda")
    denomination = Denomination(currency_id=currency_id, value=value, denomination_type=denomination_type)
    db.add(denomination)
    await db.commit()
    await db.refresh(denomination)
    return denomination


async def update_denomination(db: AsyncSession, denomination_id: uuid.UUID, currency_id: uuid.UUID, value: float, denomination_type: str) -> Denomination:
    result = await db.execute(select(Denomination).where(Denomination.id == denomination_id))
    denomination = result.scalar_one_or_none()
    if denomination is None:
        raise CatalogItemNotFoundError("Denominacao nao encontrada")
    denomination.currency_id = currency_id
    denomination.value = value
    denomination.denomination_type = denomination_type
    await db.commit()
    await db.refresh(denomination)
    return denomination


async def toggle_denomination(db: AsyncSession, denomination_id: uuid.UUID) -> Denomination:
    result = await db.execute(select(Denomination).where(Denomination.id == denomination_id))
    denomination = result.scalar_one_or_none()
    if denomination is None:
        raise CatalogItemNotFoundError("Denominacao nao encontrada")
    denomination.is_active = not denomination.is_active
    await db.commit()
    await db.refresh(denomination)
    return denomination


# ---------- PaymentMethodCatalog ----------

async def list_payment_methods(db: AsyncSession) -> list[PaymentMethodCatalog]:
    result = await db.execute(select(PaymentMethodCatalog).order_by(PaymentMethodCatalog.code))
    return list(result.scalars().all())


async def create_payment_method(db: AsyncSession, code: str, name: str, allows_payment: bool, allows_receipt: bool, is_cash: bool = False, uses_bank_account: bool = False) -> PaymentMethodCatalog:
    method = PaymentMethodCatalog(code=code, name=name, allows_payment=allows_payment, allows_receipt=allows_receipt, is_cash=is_cash, uses_bank_account=uses_bank_account)
    db.add(method)
    await db.commit()
    await db.refresh(method)
    return method


async def update_payment_method(db: AsyncSession, method_id: uuid.UUID, code: str, name: str, allows_payment: bool, allows_receipt: bool, is_cash: bool = False, uses_bank_account: bool = False) -> PaymentMethodCatalog:
    result = await db.execute(select(PaymentMethodCatalog).where(PaymentMethodCatalog.id == method_id))
    method = result.scalar_one_or_none()
    if method is None:
        raise CatalogItemNotFoundError("Metodo de pagamento nao encontrado")
    method.code = code
    method.name = name
    method.allows_payment = allows_payment
    method.allows_receipt = allows_receipt
    method.is_cash = is_cash
    method.uses_bank_account = uses_bank_account
    await db.commit()
    await db.refresh(method)
    return method


async def toggle_payment_method(db: AsyncSession, method_id: uuid.UUID) -> PaymentMethodCatalog:
    result = await db.execute(select(PaymentMethodCatalog).where(PaymentMethodCatalog.id == method_id))
    method = result.scalar_one_or_none()
    if method is None:
        raise CatalogItemNotFoundError("Metodo de pagamento nao encontrado")
    method.is_active = not method.is_active
    await db.commit()
    await db.refresh(method)
    return method


# ---------- PaymentTerm ----------

async def list_payment_terms(db: AsyncSession) -> list[PaymentTerm]:
    result = await db.execute(select(PaymentTerm).order_by(PaymentTerm.name))
    return list(result.scalars().all())


async def create_payment_term(db: AsyncSession, name: str, fixed_days: bool, days: int, months_fixed_day: int, discount: float) -> PaymentTerm:
    term = PaymentTerm(name=name, fixed_days=fixed_days, days=days, months_fixed_day=months_fixed_day, discount=discount)
    db.add(term)
    await db.commit()
    await db.refresh(term)
    return term


async def update_payment_term(db: AsyncSession, term_id: uuid.UUID, name: str, fixed_days: bool, days: int, months_fixed_day: int, discount: float) -> PaymentTerm:
    result = await db.execute(select(PaymentTerm).where(PaymentTerm.id == term_id))
    term = result.scalar_one_or_none()
    if term is None:
        raise CatalogItemNotFoundError("Condicao de pagamento nao encontrada")
    term.name = name
    term.fixed_days = fixed_days
    term.days = days
    term.months_fixed_day = months_fixed_day
    term.discount = discount
    await db.commit()
    await db.refresh(term)
    return term


async def toggle_payment_term(db: AsyncSession, term_id: uuid.UUID) -> PaymentTerm:
    result = await db.execute(select(PaymentTerm).where(PaymentTerm.id == term_id))
    term = result.scalar_one_or_none()
    if term is None:
        raise CatalogItemNotFoundError("Condicao de pagamento nao encontrada")
    term.is_active = not term.is_active
    await db.commit()
    await db.refresh(term)
    return term


# ---------- VatCode ----------

class ExemptionMotiveInvalidError(Exception):
    """An exemption motive the SAF-T would reject (XSD: code M + 2 digits, official reason of 6 to 60 characters)."""


def check_exemption_motive(code: str | None, name: str | None) -> None:
    """THE SAF-T rule of an exemption motive - the catalog is its only source, copied on each exempt line when issued."""
    if not re.fullmatch(r"M[0-9]{2}", code or ""):
        raise ExemptionMotiveInvalidError("O codigo do motivo de isencao deve ter o formato M seguido de 2 algarismos (ex.: M11)")
    if not 6 <= len((name or "").strip()) <= 60:
        raise ExemptionMotiveInvalidError("A mencao legal do motivo de isencao deve ter entre 6 e 60 caracteres (limite do SAF-T)")


async def list_vat_codes(db: AsyncSession) -> list[VatCode]:
    result = await db.execute(select(VatCode).order_by(VatCode.code))
    return list(result.scalars().all())


async def create_vat_code(
    db: AsyncSession, code: str, name: str, rate: float, country_id: uuid.UUID,
    valid_from: date, valid_until: date | None, observations: str | None,
) -> VatCode:
    check_exemption_motive(code, name)
    vat_code = VatCode(
        code=code, name=name, rate=rate, country_id=country_id,
        valid_from=valid_from, valid_until=valid_until, observations=observations,
    )
    db.add(vat_code)
    await db.commit()
    await db.refresh(vat_code)
    return vat_code


async def update_vat_code(
    db: AsyncSession, vat_code_id: uuid.UUID, code: str, name: str, rate: float, country_id: uuid.UUID,
    valid_from: date, valid_until: date | None, observations: str | None,
) -> VatCode:
    check_exemption_motive(code, name)
    result = await db.execute(select(VatCode).where(VatCode.id == vat_code_id))
    vat_code = result.scalar_one_or_none()
    if vat_code is None:
        raise CatalogItemNotFoundError("Codigo IVA nao encontrado")
    vat_code.code = code
    vat_code.name = name
    vat_code.rate = rate
    vat_code.country_id = country_id
    vat_code.valid_from = valid_from
    vat_code.valid_until = valid_until
    vat_code.observations = observations
    await db.commit()
    await db.refresh(vat_code)
    return vat_code


async def toggle_vat_code(db: AsyncSession, vat_code_id: uuid.UUID) -> VatCode:
    result = await db.execute(select(VatCode).where(VatCode.id == vat_code_id))
    vat_code = result.scalar_one_or_none()
    if vat_code is None:
        raise CatalogItemNotFoundError("Codigo IVA nao encontrado")
    vat_code.is_active = not vat_code.is_active
    await db.commit()
    await db.refresh(vat_code)
    return vat_code


# ---------- DocumentType ----------

# Rules of a document type: all editable by the super admin.
RULE_NAMES = (
    "saft_section", "revenue_sign", "requires_origin", "has_lines", "paid_on_issue", "sent_to_agt", "deducts_stock",
    "accepts_credit_note", "accepts_debit_note", "accepts_receipt", "convertible", "issuable_in_invoices", "issuable_at_pos",
)


def _apply_rules(item: DocumentType, rules: dict | None) -> None:
    for key, value in (rules or {}).items():
        if key in RULE_NAMES:
            setattr(item, key, value)


async def list_document_types(db: AsyncSession) -> list[DocumentType]:
    result = await db.execute(select(DocumentType).order_by(DocumentType.code))
    return list(result.scalars().all())


async def create_document_type(
    db: AsyncSession, code: str, name: str, area: str | None = None,
    electronic_eligible: bool = False, is_fiscal: bool = True, rules: dict | None = None,
    description: str | None = None,
) -> DocumentType:
    item = DocumentType(code=code, name=name, description=description, area=area, electronic_eligible=electronic_eligible, is_fiscal=is_fiscal)
    _apply_rules(item, rules)  # a new type is never locked: every rule is editable
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def update_document_type(
    db: AsyncSession, item_id: uuid.UUID, code: str, name: str, area: str | None = None,
    electronic_eligible: bool = False, is_fiscal: bool = True, rules: dict | None = None,
    description: str | None = None,
) -> DocumentType:
    # Always read the row as it is in the database: the lock must not depend on a cached copy.
    result = await db.execute(
        select(DocumentType).where(DocumentType.id == item_id).execution_options(populate_existing=True)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise CatalogItemNotFoundError("Tipo de documento nao encontrado")
    item.code = code
    item.name = name
    item.description = description
    item.area = area
    item.electronic_eligible = electronic_eligible
    item.is_fiscal = is_fiscal
    _apply_rules(item, rules)
    await db.commit()
    await db.refresh(item)
    return item


async def toggle_document_type(db: AsyncSession, item_id: uuid.UUID) -> DocumentType:
    result = await db.execute(select(DocumentType).where(DocumentType.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise CatalogItemNotFoundError("Tipo de documento nao encontrado")
    item.is_active = not item.is_active
    await db.commit()
    await db.refresh(item)
    return item


# ---------- MovementType ----------

async def list_movement_types(db: AsyncSession) -> list[MovementType]:
    result = await db.execute(select(MovementType).order_by(MovementType.code))
    return list(result.scalars().all())


async def create_movement_type(
    db: AsyncSession, code: str, name: str, direction: str, is_auto: bool = False, description: str | None = None,
) -> MovementType:
    item = MovementType(code=code, name=name, direction=direction, is_auto=is_auto, description=description)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def update_movement_type(
    db: AsyncSession, item_id: uuid.UUID, code: str, name: str, direction: str,
    is_auto: bool = False, description: str | None = None,
) -> MovementType:
    result = await db.execute(select(MovementType).where(MovementType.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise CatalogItemNotFoundError("Tipo de movimento nao encontrado")
    item.code = code
    item.name = name
    item.direction = direction
    item.is_auto = is_auto
    item.description = description
    await db.commit()
    await db.refresh(item)
    return item


async def toggle_movement_type(db: AsyncSession, item_id: uuid.UUID) -> MovementType:
    result = await db.execute(select(MovementType).where(MovementType.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise CatalogItemNotFoundError("Tipo de movimento nao encontrado")
    item.is_active = not item.is_active
    await db.commit()
    await db.refresh(item)
    return item


# ---------- UnitOfMeasureCatalog ----------

async def list_units(db: AsyncSession) -> list[UnitOfMeasureCatalog]:
    result = await db.execute(select(UnitOfMeasureCatalog).order_by(UnitOfMeasureCatalog.code))
    return list(result.scalars().all())


async def create_unit(db: AsyncSession, code: str, name: str, fixed_factor: float | None = None, is_fractional: bool = False) -> UnitOfMeasureCatalog:
    item = UnitOfMeasureCatalog(code=code, name=name, fixed_factor=fixed_factor if fixed_factor and fixed_factor > 0 else None, is_fractional=is_fractional)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def update_unit(db: AsyncSession, item_id: uuid.UUID, code: str, name: str, fixed_factor: float | None = None, is_fractional: bool = False) -> UnitOfMeasureCatalog:
    result = await db.execute(select(UnitOfMeasureCatalog).where(UnitOfMeasureCatalog.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise CatalogItemNotFoundError("Unidade nao encontrada")
    item.code = code
    item.name = name
    item.fixed_factor = fixed_factor if fixed_factor and fixed_factor > 0 else None
    item.is_fractional = is_fractional
    await db.commit()
    await db.refresh(item)
    return item


async def toggle_unit(db: AsyncSession, item_id: uuid.UUID) -> UnitOfMeasureCatalog:
    result = await db.execute(select(UnitOfMeasureCatalog).where(UnitOfMeasureCatalog.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise CatalogItemNotFoundError("Unidade nao encontrada")
    item.is_active = not item.is_active
    await db.commit()
    await db.refresh(item)
    return item


# ---------- WithholdingTax ----------

async def list_withholding_taxes(db: AsyncSession) -> list[WithholdingTax]:
    result = await db.execute(select(WithholdingTax).order_by(WithholdingTax.name))
    return list(result.scalars().all())


async def create_withholding_tax(db: AsyncSession, name: str, rate: float, tax_type: str | None = None) -> WithholdingTax:
    item = WithholdingTax(name=name, rate=rate, tax_type=tax_type)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def update_withholding_tax(db: AsyncSession, item_id: uuid.UUID, name: str, rate: float, tax_type: str | None = None) -> WithholdingTax:
    result = await db.execute(select(WithholdingTax).where(WithholdingTax.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise CatalogItemNotFoundError("Retencao nao encontrada")
    item.name = name
    item.rate = rate
    if tax_type is not None:  # a client that does not send the type keeps the one already set
        item.tax_type = tax_type
    await db.commit()
    await db.refresh(item)
    return item


async def toggle_withholding_tax(db: AsyncSession, item_id: uuid.UUID) -> WithholdingTax:
    result = await db.execute(select(WithholdingTax).where(WithholdingTax.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise CatalogItemNotFoundError("Retencao nao encontrada")
    item.is_active = not item.is_active
    await db.commit()
    await db.refresh(item)
    return item
