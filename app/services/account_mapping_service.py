"""
Contabilidade - «Contas por operação» and the sub-accounts the system makes (app.data.account_operations).

  - list_mappings / set_mapping: the account of the company's chart each kind of operation goes to; any account of the
    chart may be chosen (a company with its own chart maps its own codes), a «parent» takes the sub-accounts;
  - apply_suggestions: every operation still without an account gets the suggested PGC account, when the chart has
    it (after the PGC is loaded, or on demand) - an operation already set is never changed;
  - sync_subaccounts: one sub-account per bank account (under the national or foreign currency parent), per till and
    cofre, per customer (national or foreign; never the Consumidor final) and per supplier - each one created once,
    numbered after the parent's last sub-account (43.1 -> 43.1.1, 43.1.2...), named after the entity, and linked to it
    (AccountLink). Customers and suppliers only when the company keeps one sub-account each (the settings).
"""
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.account_operations import OPERATIONS, OPERATIONS_BY_KEY
from app.models.account import Account, AccountingSettings, AccountLink, AccountMapping
from app.services.chart_of_accounts_service import ChartError, level_of

log = logging.getLogger(__name__)


async def _accounts(db: AsyncSession, company_id: uuid.UUID) -> dict[uuid.UUID, Account]:
    return {a.id: a for a in (await db.execute(select(Account).where(Account.company_id == company_id))).scalars().all()}


async def _mappings(db: AsyncSession, company_id: uuid.UUID) -> dict[str, AccountMapping]:
    rows = (await db.execute(select(AccountMapping).where(AccountMapping.company_id == company_id))).scalars().all()
    return {m.operation: m for m in rows}


async def _settings(db: AsyncSession, company_id: uuid.UUID) -> AccountingSettings:
    settings = await db.get(AccountingSettings, company_id)
    if settings is None:
        settings = AccountingSettings(company_id=company_id)
        db.add(settings)
        await db.flush()
    return settings


async def _with_children(db: AsyncSession, company_id: uuid.UUID) -> set[uuid.UUID]:
    """The accounts that have sub-accounts (an entry never lands on them)."""
    return set((await db.execute(select(Account.parent_id).where(
        Account.company_id == company_id, Account.parent_id.is_not(None)).distinct())).scalars().all())


async def _postable(db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID) -> Account:
    """An active last-level account of the company: the one the entries of an operation, a reason or a stock type
    land on (a parent account is refused here rather than every entry waiting in «Por integrar»)."""
    account = (await db.execute(select(Account).where(
        Account.id == account_id, Account.company_id == company_id))).scalar_one_or_none()
    if account is None or not account.is_active:
        raise ChartError("Conta não encontrada ou inativa")
    if account.id in await _with_children(db, company_id):
        raise ChartError(f"A conta {account.code} tem subcontas - escolha uma conta de último nível "
                         "(crie uma subconta no Plano de contas, se preciso)")
    return account


async def list_mappings(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """Every operation with its account (or none), its suggestion, and the sub-account options."""
    accounts = await _accounts(db, company_id)
    mappings = await _mappings(db, company_id)
    settings = await db.get(AccountingSettings, company_id)
    parents = await _with_children(db, company_id)
    rows = []
    for op in OPERATIONS:
        mapping = mappings.get(op.key)
        account = accounts.get(mapping.account_id) if mapping else None
        rows.append({
            "key": op.key, "group": op.group, "label": op.label, "kind": op.kind, "suggestion": op.suggestion,
            "account_id": account.id if account else None,
            "account_code": account.code if account else None, "account_name": account.name if account else None,
            # set on an account with sub-accounts (an older choice): its entries would wait - to be changed
            "not_last_level": bool(account and op.kind != "parent" and account.id in parents),
        })
    from app.models.cash_movement_reason import CashMovementReason
    from app.services.supplier_payment_service import PAYMENT_REASON, REVERSAL_REASON
    reasons = (await db.execute(select(CashMovementReason).where(
        CashMovementReason.company_id == company_id, CashMovementReason.name.not_in([PAYMENT_REASON, REVERSAL_REASON]))
        .order_by(CashMovementReason.direction, CashMovementReason.name))).scalars().all()
    from app.models.account import StockTypeAccount
    from app.models.movement_type import MovementType as StockMovementTypeCatalog
    type_accounts = {t.movement_type_id: t.account_id for t in (await db.execute(
        select(StockTypeAccount).where(StockTypeAccount.company_id == company_id))).scalars().all()}
    stock_types = (await db.execute(select(StockMovementTypeCatalog).where(StockMovementTypeCatalog.is_auto.is_(False))
                                    .order_by(StockMovementTypeCatalog.direction, StockMovementTypeCatalog.code))).scalars().all()
    return {
        "operations": rows,
        "inventory_system": settings.inventory_system if settings else "PERMANENTE",
        # the stock movement types typed by hand: the other side of the stock (the automatic ones follow the purchases)
        "stock_types": [{
            "id": t.id, "code": t.code, "name": t.name, "direction": t.direction.value, "is_active": t.is_active,
            "account_id": type_accounts.get(t.id) if type_accounts.get(t.id) in accounts else None,
        } for t in stock_types],
        # the treasury reasons (the supplier payments' own are posted with the payment): the account of each one
        "reasons": [{
            "id": r.id, "name": r.name, "direction": r.direction.value, "for_cash": r.for_cash, "for_bank": r.for_bank,
            "is_active": r.is_active, "account_id": r.account_id if r.account_id in accounts else None,
        } for r in reasons],
        "subaccount_per_customer": settings.subaccount_per_customer if settings else True,
        "subaccount_per_supplier": settings.subaccount_per_supplier if settings else True,
    }


async def set_mapping(db: AsyncSession, company_id: uuid.UUID, key: str, account_id: uuid.UUID | None) -> None:
    if key not in OPERATIONS_BY_KEY:
        raise ChartError("Operação desconhecida")
    mappings = await _mappings(db, company_id)
    if account_id is None:
        if key in mappings:
            await db.delete(mappings[key])
        await db.commit()
        return
    if OPERATIONS_BY_KEY[key].kind == "parent":  # the parent of the sub-accounts the system makes
        account = (await db.execute(select(Account).where(
            Account.id == account_id, Account.company_id == company_id))).scalar_one_or_none()
        if account is None or not account.is_active:
            raise ChartError("Conta não encontrada ou inativa")
    else:
        account = await _postable(db, company_id, account_id)
    if key in mappings:
        mappings[key].account_id = account.id
    else:
        db.add(AccountMapping(company_id=company_id, operation=key, account_id=account.id))
    await db.commit()
    if OPERATIONS_BY_KEY[key].kind == "parent":  # a parent now set: the sub-accounts waiting for it
        await sync_subaccounts(db, company_id)


async def set_reason_account(db: AsyncSession, company_id: uuid.UUID, reason_id: uuid.UUID, account_id: uuid.UUID | None) -> None:
    """The account a treasury reason's movements go to (None: none yet - its movements wait in «Por integrar»)."""
    from app.models.cash_movement_reason import CashMovementReason
    reason = (await db.execute(select(CashMovementReason).where(
        CashMovementReason.id == reason_id, CashMovementReason.company_id == company_id))).scalar_one_or_none()
    if reason is None:
        raise ChartError("Motivo não encontrado")
    if account_id is not None:
        await _postable(db, company_id, account_id)
    reason.account_id = account_id
    await db.commit()


async def set_stock_type_account(db: AsyncSession, company_id: uuid.UUID, movement_type_id: uuid.UUID,
                                 account_id: uuid.UUID | None) -> None:
    """The account a stock movement type's documents go to (None: none - they wait in «Por integrar»)."""
    from app.models.account import StockTypeAccount
    from app.models.movement_type import MovementType as StockMovementTypeCatalog
    if await db.get(StockMovementTypeCatalog, movement_type_id) is None:
        raise ChartError("Tipo de movimento não encontrado")
    row = (await db.execute(select(StockTypeAccount).where(
        StockTypeAccount.company_id == company_id, StockTypeAccount.movement_type_id == movement_type_id))).scalar_one_or_none()
    if account_id is None:
        if row is not None:
            await db.delete(row)
        await db.commit()
        return
    account = await _postable(db, company_id, account_id)
    if row is None:
        db.add(StockTypeAccount(company_id=company_id, movement_type_id=movement_type_id, account_id=account.id))
    else:
        row.account_id = account.id
    await db.commit()


async def set_inventory_system(db: AsyncSession, company_id: uuid.UUID, system: str) -> None:
    if system not in ("PERMANENTE", "INTERMITENTE"):
        raise ChartError("Escolha o inventário permanente ou intermitente")
    settings = await _settings(db, company_id)
    settings.inventory_system = system
    await db.commit()


async def set_options(db: AsyncSession, company_id: uuid.UUID, per_customer: bool, per_supplier: bool) -> None:
    settings = await _settings(db, company_id)
    settings.subaccount_per_customer, settings.subaccount_per_supplier = per_customer, per_supplier
    await db.commit()
    await sync_subaccounts(db, company_id)


async def apply_suggestions(db: AsyncSession, company_id: uuid.UUID, commit: bool = True) -> int:
    """The suggested PGC account for every operation still without one, when the chart has that code - and, but for
    the parents of the system's sub-accounts, when it is a last-level one (26 in the PGC has 26.9: the accountant
    creates and chooses 26.1). Returns how many operations were set."""
    by_code = {a.code: a for a in (await _accounts(db, company_id)).values() if a.is_active}
    parents = await _with_children(db, company_id)
    mappings = await _mappings(db, company_id)
    done = 0
    for op in OPERATIONS:
        if op.key in mappings or not op.suggestion or op.suggestion not in by_code:
            continue
        if op.kind != "parent" and by_code[op.suggestion].id in parents:
            continue
        db.add(AccountMapping(company_id=company_id, operation=op.key, account_id=by_code[op.suggestion].id))
        done += 1
    if commit:
        await db.commit()
        await sync_subaccounts(db, company_id)
    return done


# ---------- the sub-accounts made by the system ----------

async def _entities(db: AsyncSession, company_id: uuid.UUID, settings: AccountingSettings) -> list[tuple[str, uuid.UUID, str, str]]:
    """(kind, entity id, name of its sub-account, operation of its parent), in a stable order."""
    from app.models.activity import Activity
    from app.models.bank import Bank
    from app.models.company_bank_account import CompanyBankAccount
    from app.models.country import Country
    from app.models.currency import Currency
    from app.models.customer import Customer
    from app.models.point_of_sale import PointOfSale
    from app.models.supplier import Supplier
    out = []
    for account, acronym, currency in (await db.execute(
        select(CompanyBankAccount, Bank.acronym, Currency.code)
        .join(Bank, Bank.id == CompanyBankAccount.bank_id).join(Currency, Currency.id == CompanyBankAccount.currency_id)
        .where(CompanyBankAccount.company_id == company_id).order_by(CompanyBankAccount.created_at)
    )).all():
        parent = "PARENT_BANKS_NATIONAL" if currency == "AOA" else "PARENT_BANKS_FOREIGN"
        out.append(("BANK", account.id, f"{acronym} · {account.account_number}", parent))
    for pos, activity_name in (await db.execute(
        select(PointOfSale, Activity.name).join(Activity, Activity.id == PointOfSale.activity_id)
        .where(PointOfSale.company_id == company_id).order_by(PointOfSale.created_at)
    )).all():
        out.append(("TILL", pos.id, f"{pos.name} ({activity_name})", "PARENT_TILLS"))
    if settings.subaccount_per_customer:
        for customer, country in (await db.execute(
            select(Customer, Country.code).outerjoin(Country, Country.id == Customer.country_id)
            .where(Customer.company_id == company_id, Customer.is_final_consumer.is_(False)).order_by(Customer.created_at)
        )).all():
            foreign = country is not None and country.upper() != "AO"
            out.append(("CUSTOMER", customer.id, f"{customer.name} ({customer.nif})"[:200],
                        "PARENT_CUSTOMERS_FOREIGN" if foreign else "PARENT_CUSTOMERS_NATIONAL"))
    if settings.subaccount_per_supplier:
        for supplier in (await db.execute(
            select(Supplier).where(Supplier.company_id == company_id).order_by(Supplier.created_at)
        )).scalars().all():
            out.append(("SUPPLIER", supplier.id, (supplier.name + (f" ({supplier.nif})" if supplier.nif else ""))[:200],
                        "PARENT_SUPPLIERS"))
    return out


async def _new_subaccount(db: AsyncSession, company_id: uuid.UUID, parent: Account, name: str, used_codes: set[str]) -> Account:
    """The next sub-account of parent (43.1 -> 43.1.1, 43.1.2...) - flushed, its code added to used_codes."""
    last = max((int(c.rsplit(".", 1)[1]) for c in used_codes if c.startswith(parent.code + ".")
                and c.count(".") == parent.code.count(".") + 1), default=0)
    if last >= 9999:
        raise ChartError(f"A conta {parent.code} já tem 9999 subcontas")
    code = f"{parent.code}.{last + 1}"
    account = Account(company_id=company_id, code=code, name=name, parent_id=parent.id, level=level_of(code), is_active=True)
    db.add(account)
    await db.flush()
    used_codes.add(code)
    return account


async def sync_subaccounts(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """Creates the sub-accounts still missing - see the module docstring. Returns {created, missing_parent: [labels]}:
    the entities whose parent operation has no account yet are left for later."""
    settings = await _settings(db, company_id)
    accounts = await _accounts(db, company_id)
    mappings = await _mappings(db, company_id)
    linked = {(l.entity_kind, l.entity_id) for l in (await db.execute(
        select(AccountLink).where(AccountLink.company_id == company_id))).scalars().all()}
    used_codes = {a.code for a in accounts.values()}
    from app.services.chart_of_accounts_service import accounts_with_entries
    with_entries = await accounts_with_entries(db, company_id)
    created, missing = 0, set()
    for kind, entity_id, name, parent_op in await _entities(db, company_id, settings):
        if (kind, entity_id) in linked:
            continue
        mapping = mappings.get(parent_op)
        parent = accounts.get(mapping.account_id) if mapping else None
        if parent is None:
            missing.add(OPERATIONS_BY_KEY[parent_op].label)
            continue
        if parent.id in with_entries:  # an account with entries never gets sub-accounts: choose another parent
            missing.add(f"{OPERATIONS_BY_KEY[parent_op].label} (a conta {parent.code} já tem lançamentos)")
            continue
        account = await _new_subaccount(db, company_id, parent, name, used_codes)
        db.add(AccountLink(company_id=company_id, entity_kind=kind, entity_id=entity_id, account_id=account.id))
        created += 1
    # the customers without a sub-account of their own (Consumidor final, sales without a customer): one sub-account
    # «Consumidor final» under the national customers, set as their account - the accountant may choose another
    national = mappings.get("PARENT_CUSTOMERS_NATIONAL")
    national = accounts.get(national.account_id) if national else None
    if (settings.subaccount_per_customer and "CUSTOMERS_GENERIC" not in mappings and national is not None
            and national.id not in with_entries):
        account = await _new_subaccount(db, company_id, national, "Consumidor final", used_codes)
        db.add(AccountMapping(company_id=company_id, operation="CUSTOMERS_GENERIC", account_id=account.id))
        created += 1
    await db.commit()
    return {"created": created, "missing_parent": sorted(missing)}


async def accounts_in_use(db: AsyncSession, company_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """The accounts the chart must keep: account id -> why (an operation, or the sub-account of an entity)."""
    used = {}
    for m in (await _mappings(db, company_id)).values():
        op = OPERATIONS_BY_KEY.get(m.operation)
        used[m.account_id] = "está em Contas por operação" + (f" ({op.label})" if op else "")
    for link in (await db.execute(select(AccountLink).where(AccountLink.company_id == company_id))).scalars().all():
        used[link.account_id] = "é a subconta de " + {"BANK": "uma conta bancária", "TILL": "uma caixa",
                                                       "CUSTOMER": "um cliente", "SUPPLIER": "um fornecedor"}[link.entity_kind]
    from app.models.cash_movement_reason import CashMovementReason
    for reason_name, account_id in (await db.execute(select(CashMovementReason.name, CashMovementReason.account_id).where(
            CashMovementReason.company_id == company_id, CashMovementReason.account_id.is_not(None)))).all():
        used[account_id] = f"é a conta do motivo de tesouraria «{reason_name}»"
    from app.models.account import StockTypeAccount
    for account_id in (await db.execute(select(StockTypeAccount.account_id).where(
            StockTypeAccount.company_id == company_id))).scalars().all():
        used[account_id] = "é a conta de um tipo de movimento de stock"
    from app.services.chart_of_accounts_service import accounts_with_entries
    for account_id in await accounts_with_entries(db, company_id):
        used[account_id] = "tem lançamentos"
    return used


async def sync_after_create(db: AsyncSession, company_id: uuid.UUID, created=None) -> None:
    """Called once a bank account, till, customer or supplier is saved: its sub-account at once, when the company's
    chart is started. Never blocks the creation - a failure is logged, the sub-account is made by the next sync.
    created: the saved object, refreshed after the sync's commit (its caller still reads it)."""
    settings = await db.get(AccountingSettings, company_id)
    if settings is None or settings.chart_source is None:
        return
    try:
        await sync_subaccounts(db, company_id)
    except Exception:  # noqa: BLE001
        log.exception("sub-accounts not synced for company %s", company_id)
        await db.rollback()
    if created is not None:
        await db.refresh(created)
