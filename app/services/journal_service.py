"""
Contabilidade - the journals (diários) and the entries (lançamentos) typed in them.

  - the journals: the defaults made when the chart is started (ensure_default_journals), then added, renamed,
    deactivated by the company; one with entries is never deleted, a code never changes;
  - an entry is saved as a RASCUNHO (changed or deleted freely; its lines need not balance) or posted (LANCADO):
    at least two lines, debit = credit, every account a last-level active account of the chart, its date in a period
    that takes entries (ABERTO, or FECHO_PARCIAL - the late entries of the soft-closed month; never FECHADO). Posting
    gives the next number of the journal for the year of the date, without gaps («OD 2026/0001»);
  - a posted entry never changes: reverse_entry posts its estorno (the same lines, debit and credit swapped) on a date
    of a period that takes entries, and links the two. An estorno is not reversed itself, an entry only once.
"""
import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.fiscal_period import FiscalPeriod
from app.models.fiscal_year import FiscalYear
from app.models.journal import DEFAULT_JOURNALS, Journal, JournalEntry, JournalEntryLine
from app.services.fiscal_period_service import FECHADO, MONTH_NAMES_PT

CENT = Decimal("0.01")
MAX_LINES = 500


class JournalError(Exception):
    """A journal or an entry that cannot be saved, posted or reversed as asked - the message says why (PT-PT)."""


class JournalNotFoundError(Exception):
    pass


class EntryNotFoundError(Exception):
    pass


# ---------- the journals ----------

async def ensure_default_journals(db: AsyncSession, company_id: uuid.UUID) -> None:
    """The default journals, for a company without any (flush only - its caller commits)."""
    count = (await db.execute(select(func.count(Journal.id)).where(Journal.company_id == company_id))).scalar_one()
    if count:
        return
    for code, name in DEFAULT_JOURNALS:
        db.add(Journal(company_id=company_id, code=code, name=name, is_active=True))
    await db.flush()


async def list_journals(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    rank = {code: i for i, (code, _) in enumerate(DEFAULT_JOURNALS)}  # the defaults in their usual order, then the others
    journals = sorted((await db.execute(select(Journal).where(Journal.company_id == company_id))).scalars().all(),
                      key=lambda j: (rank.get(j.code, len(rank)), j.created_at, j.code))
    counts = dict((await db.execute(
        select(JournalEntry.journal_id, func.count(JournalEntry.id)).where(JournalEntry.company_id == company_id)
        .group_by(JournalEntry.journal_id))).all())
    return [{"id": j.id, "code": j.code, "name": j.name, "is_active": j.is_active, "entries": counts.get(j.id, 0)}
            for j in journals]


async def _journal(db: AsyncSession, company_id: uuid.UUID, journal_id: uuid.UUID, lock: bool = False) -> Journal:
    query = select(Journal).where(Journal.id == journal_id, Journal.company_id == company_id)
    if lock:  # the numbering: one posting at a time per journal
        query = query.with_for_update()
    journal = (await db.execute(query)).scalar_one_or_none()
    if journal is None:
        raise JournalNotFoundError("Diário não encontrado")
    return journal


def _check_journal_fields(code: str, name: str) -> tuple[str, str]:
    code, name = (code or "").strip().upper(), (name or "").strip()
    if not code or len(code) > 10 or not code.replace("-", "").isalnum():
        raise JournalError("Código do diário inválido: até 10 letras ou algarismos (ex.: OD, VND2)")
    if not name:
        raise JournalError("Indique o nome do diário")
    return code, name[:100]


async def create_journal(db: AsyncSession, company_id: uuid.UUID, code: str, name: str) -> Journal:
    code, name = _check_journal_fields(code, name)
    exists = (await db.execute(select(Journal.id).where(Journal.company_id == company_id, Journal.code == code))).first()
    if exists:
        raise JournalError(f"O diário {code} já existe")
    journal = Journal(company_id=company_id, code=code, name=name, is_active=True)
    db.add(journal)
    await db.commit()
    await db.refresh(journal)
    return journal


async def update_journal(db: AsyncSession, company_id: uuid.UUID, journal_id: uuid.UUID, name: str, is_active: bool) -> Journal:
    """Renames or (de)activates a journal - its code never changes. An inactive journal takes no new entry."""
    journal = await _journal(db, company_id, journal_id)
    _, journal.name = _check_journal_fields(journal.code, name)
    journal.is_active = is_active
    await db.commit()
    await db.refresh(journal)
    return journal


async def delete_journal(db: AsyncSession, company_id: uuid.UUID, journal_id: uuid.UUID) -> None:
    journal = await _journal(db, company_id, journal_id)
    used = (await db.execute(select(func.count(JournalEntry.id)).where(JournalEntry.journal_id == journal.id))).scalar_one()
    if used:
        raise JournalError(f"O diário {journal.code} tem lançamentos - não pode ser apagado (pode desativá-lo)")
    await db.delete(journal)
    await db.commit()


# ---------- the checks of an entry ----------

async def check_entry_date(db: AsyncSession, company_id: uuid.UUID, entry_date: date) -> None:
    """The date must fall in a period that takes entries: its year not closed, its month opened and not FECHADO."""
    label = f"{MONTH_NAMES_PT[entry_date.month]} de {entry_date.year}"
    year = (await db.execute(select(FiscalYear).where(
        FiscalYear.company_id == company_id, FiscalYear.year == entry_date.year))).scalar_one_or_none()
    if year is None:
        raise JournalError(f"O ano fiscal {entry_date.year} não existe - não aceita lançamentos")
    if year.status == FECHADO:
        raise JournalError(f"O ano fiscal {entry_date.year} está fechado definitivamente - não aceita lançamentos")
    period = (await db.execute(select(FiscalPeriod).where(
        FiscalPeriod.fiscal_year_id == year.id, FiscalPeriod.month == entry_date.month))).scalar_one_or_none()
    if period is None:
        raise JournalError(f"O período de {label} ainda não foi aberto - não aceita lançamentos")
    if period.status == FECHADO:
        raise JournalError(f"O período de {label} está fechado definitivamente - não aceita lançamentos")


def _amount(raw, where: str) -> Decimal:
    try:
        value = Decimal(str(raw if raw not in (None, "") else 0))
    except (InvalidOperation, ValueError):
        raise JournalError(f"{where}: valor inválido")
    if value < 0:
        raise JournalError(f"{where}: o valor não pode ser negativo")
    if value != value.quantize(CENT, rounding=ROUND_HALF_UP):
        raise JournalError(f"{where}: no máximo 2 casas decimais")
    return value.quantize(CENT)


async def _check_lines(db: AsyncSession, company_id: uuid.UUID, lines: list[dict], posting: bool) -> list[dict]:
    """The lines, checked and cleaned: [{account_id, description, debit, credit}]. Each one: an account of the chart,
    last-level (no sub-accounts) and active; a debit OR a credit, above zero. Posting: two lines at least, balanced."""
    if len(lines) > MAX_LINES:
        raise JournalError(f"No máximo {MAX_LINES} linhas por lançamento")
    ids = {_uuid(line.get("account_id")) for line in lines} - {None}
    accounts = {a.id: a for a in (await db.execute(select(Account).where(
        Account.company_id == company_id, Account.id.in_(ids)))).scalars().all()} if ids else {}
    parents = set((await db.execute(select(Account.parent_id).where(
        Account.company_id == company_id, Account.parent_id.in_(ids)))).scalars().all()) if ids else set()
    out = []
    for i, line in enumerate(lines, start=1):
        where = f"Linha {i}"
        account = accounts.get(_uuid(line.get("account_id")))
        if account is None:
            raise JournalError(f"{where}: escolha a conta")
        if account.id in parents:
            raise JournalError(f"{where}: a conta {account.code} tem subcontas - lance numa conta de último nível")
        if not account.is_active:
            raise JournalError(f"{where}: a conta {account.code} está inativa")
        debit, credit = _amount(line.get("debit"), where), _amount(line.get("credit"), where)
        if debit and credit:
            raise JournalError(f"{where}: indique o débito ou o crédito, não os dois")
        if not debit and not credit:
            raise JournalError(f"{where}: indique o valor a débito ou a crédito")
        description = (line.get("description") or "").strip()[:200] or None
        out.append({"account_id": account.id, "description": description, "debit": debit, "credit": credit})
    if posting:
        if len(out) < 2:
            raise JournalError("Um lançamento tem pelo menos duas linhas")
        debit, credit = sum(l["debit"] for l in out), sum(l["credit"] for l in out)
        if debit != credit:
            raise JournalError(f"O lançamento não está equilibrado: débito {_fmt(debit)} ≠ crédito {_fmt(credit)} "
                               f"(diferença {_fmt(abs(debit - credit))})")
    return out


def _uuid(raw) -> uuid.UUID | None:
    if isinstance(raw, uuid.UUID) or raw is None:
        return raw
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        return None


def _fmt(value: Decimal) -> str:
    """1234567.5 -> 1 234 567,50 (the PT-PT way)."""
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


# ---------- the entries ----------

async def _entry(db: AsyncSession, company_id: uuid.UUID, entry_id: uuid.UUID) -> JournalEntry:
    entry = (await db.execute(select(JournalEntry).where(
        JournalEntry.id == entry_id, JournalEntry.company_id == company_id))).scalar_one_or_none()
    if entry is None:
        raise EntryNotFoundError("Lançamento não encontrado")
    return entry


async def save_entry(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, *, entry_id: uuid.UUID | None,
                     journal_id: uuid.UUID, entry_date: date, description: str, document_ref: str | None,
                     lines: list[dict], post: bool = False, reversal_of_id: uuid.UUID | None = None,
                     source: tuple[str, uuid.UUID] | None = None) -> JournalEntry:
    """Creates a draft (entry_id None) or changes one; post=True posts it in the same step - all or nothing: a refused
    posting saves nothing. Every check runs before anything is changed (a refusal leaves the session as it was)."""
    if entry_id is None:
        entry = JournalEntry(company_id=company_id, status="RASCUNHO", created_by=user_id, reversal_of_id=reversal_of_id,
                             source_kind=source[0] if source else None, source_id=source[1] if source else None)
    else:
        entry = await _entry(db, company_id, entry_id)
        if entry.status != "RASCUNHO":
            raise JournalError("Um lançamento já lançado não pode ser alterado - faça o estorno")
    journal = await _journal(db, company_id, journal_id)
    if not journal.is_active:
        raise JournalError(f"O diário {journal.code} está inativo")
    description = (description or "").strip()
    if not description:
        raise JournalError("Indique a descrição do lançamento")
    await check_entry_date(db, company_id, entry_date)
    checked = await _check_lines(db, company_id, lines, posting=post)
    try:
        entry.journal_id, entry.entry_date = journal.id, entry_date
        entry.description, entry.document_ref = description[:200], (document_ref or "").strip()[:60] or None
        db.add(entry)
        await db.flush()
        if entry_id is not None:
            for old in (await db.execute(select(JournalEntryLine).where(JournalEntryLine.entry_id == entry.id))).scalars().all():
                await db.delete(old)
            await db.flush()
        for position, line in enumerate(checked, start=1):
            db.add(JournalEntryLine(entry_id=entry.id, position=position, **line))
        await db.flush()
        if post:
            await _post(db, company_id, user_id, entry)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(entry)
    return entry


async def _post(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, entry: JournalEntry) -> None:
    """Gives the entry the next number of its journal for its year (the journal row locked meanwhile). Flush only."""
    journal = await _journal(db, company_id, entry.journal_id, lock=True)
    last = (await db.execute(select(func.max(JournalEntry.number)).where(
        JournalEntry.journal_id == journal.id, JournalEntry.year == entry.entry_date.year))).scalar_one()
    entry.status, entry.year, entry.number = "LANCADO", entry.entry_date.year, (last or 0) + 1
    entry.posted_by, entry.posted_at = user_id, datetime.now(timezone.utc)
    await db.flush()


async def _lines_of(db: AsyncSession, entry_id: uuid.UUID) -> list[dict]:
    lines = (await db.execute(select(JournalEntryLine).where(JournalEntryLine.entry_id == entry_id)
                              .order_by(JournalEntryLine.position))).scalars().all()
    return [{"account_id": l.account_id, "description": l.description, "debit": l.debit, "credit": l.credit} for l in lines]


async def post_entry(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, entry_id: uuid.UUID) -> JournalEntry:
    """Posts a saved draft, as it is (every check run again: the chart or the periods may have changed since)."""
    entry = await _entry(db, company_id, entry_id)
    if entry.status != "RASCUNHO":
        raise JournalError("Este lançamento já foi lançado")
    return await save_entry(db, company_id, user_id, entry_id=entry.id, journal_id=entry.journal_id,
                            entry_date=entry.entry_date, description=entry.description, document_ref=entry.document_ref,
                            lines=await _lines_of(db, entry.id), post=True)


async def delete_entry(db: AsyncSession, company_id: uuid.UUID, entry_id: uuid.UUID) -> None:
    entry = await _entry(db, company_id, entry_id)
    if entry.status != "RASCUNHO":
        raise JournalError("Um lançamento já lançado não pode ser apagado - faça o estorno")
    await db.delete(entry)
    await db.commit()


# the entries cancelled from their own screen only - their estorno keeps their kind (the Demonstração de resultados
# leaves the apuramento and the abertura out, estornos included): kind -> where they are cancelled
PROTECTED_SOURCES = {
    "CLOSING": "Demonstrações financeiras › Fecho do exercício",  # the apuramento (year_closing_service)
    "OPENING": "Demonstrações financeiras › Fecho do exercício",  # the abertura of the next year
    "OPENING_BALANCES": "Lançamentos › Saldos iniciais",  # the imported opening balances (opening_balances_service)
}


async def reverse_entry(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, entry_id: uuid.UUID,
                        entry_date: date, system: bool = False) -> JournalEntry:
    """The estorno of a posted entry: posted at once, in the same journal, the debits and credits swapped.
    A protected entry (PROTECTED_SOURCES) is cancelled from its own screen only (system)."""
    entry = await _entry(db, company_id, entry_id)
    if entry.source_kind in PROTECTED_SOURCES and not system:
        raise JournalError(f"Este lançamento anula-se em {PROTECTED_SOURCES[entry.source_kind]}")
    if entry.status != "LANCADO":
        raise JournalError("Só um lançamento lançado tem estorno - um rascunho apaga-se")
    if entry.reversal_of_id is not None:
        raise JournalError("Este lançamento é um estorno - não pode ser estornado")
    done = (await db.execute(select(JournalEntry).where(JournalEntry.reversal_of_id == entry.id))).scalar_one_or_none()
    if done is not None:
        raise JournalError(f"Este lançamento já foi estornado ({await _label(db, done)})")
    if entry_date < entry.entry_date:
        raise JournalError("A data do estorno não pode ser anterior à do lançamento")
    lines = [{**l, "debit": l["credit"], "credit": l["debit"]} for l in await _lines_of(db, entry.id)]
    reversal = await save_entry(db, company_id, user_id, entry_id=None, journal_id=entry.journal_id,
                                entry_date=entry_date, description=f"Estorno de {await _label(db, entry)}",
                                document_ref=entry.document_ref, lines=lines, post=True, reversal_of_id=entry.id,
                                source=(entry.source_kind, uuid.uuid4()) if entry.source_kind in PROTECTED_SOURCES else None)
    return reversal


async def _label(db: AsyncSession, entry: JournalEntry) -> str:
    code = (await db.execute(select(Journal.code).where(Journal.id == entry.journal_id))).scalar_one()
    return label_of(code, entry.year, entry.number)


def label_of(code: str, year: int | None, number: int | None) -> str:
    """«OD 2026/0001», or «OD (rascunho)» before posting."""
    return f"{code} {year}/{number:04d}" if number else f"{code} (rascunho)"


# ---------- reading ----------

async def list_entries(db: AsyncSession, company_id: uuid.UUID, *, journal_id: uuid.UUID | None = None,
                       status: str | None = None, date_from: date | None = None, date_to: date | None = None,
                       search: str | None = None, limit: int = 200) -> list[dict]:
    """The entries, the latest first, with their totals and their estorno links."""
    totals = (select(JournalEntryLine.entry_id, func.sum(JournalEntryLine.debit).label("debit"),
                     func.sum(JournalEntryLine.credit).label("credit"), func.count(JournalEntryLine.id).label("lines"))
              .group_by(JournalEntryLine.entry_id).subquery())
    query = (select(JournalEntry, Journal.code, totals.c.debit, totals.c.credit, totals.c.lines)
             .join(Journal, Journal.id == JournalEntry.journal_id)
             .outerjoin(totals, totals.c.entry_id == JournalEntry.id)
             .where(JournalEntry.company_id == company_id))
    if journal_id:
        query = query.where(JournalEntry.journal_id == journal_id)
    if status:
        query = query.where(JournalEntry.status == status)
    if date_from:
        query = query.where(JournalEntry.entry_date >= date_from)
    if date_to:
        query = query.where(JournalEntry.entry_date <= date_to)
    if search and search.strip():
        q = f"%{search.strip()}%"
        query = query.where(or_(JournalEntry.description.ilike(q), JournalEntry.document_ref.ilike(q)))
    rows = (await db.execute(query.order_by(JournalEntry.entry_date.desc(), JournalEntry.number.desc().nullsfirst(),
                                            JournalEntry.created_at.desc()).limit(limit))).all()
    ids = [r[0].id for r in rows]
    reversed_by = {}
    if ids:
        for rev, code in (await db.execute(select(JournalEntry, Journal.code).join(Journal, Journal.id == JournalEntry.journal_id)
                                           .where(JournalEntry.reversal_of_id.in_(ids)))).all():
            reversed_by[rev.reversal_of_id] = label_of(code, rev.year, rev.number)
    originals = {r[0].reversal_of_id for r in rows if r[0].reversal_of_id}
    original_label = {}
    if originals:
        for orig, code in (await db.execute(select(JournalEntry, Journal.code).join(Journal, Journal.id == JournalEntry.journal_id)
                                            .where(JournalEntry.id.in_(originals)))).all():
            original_label[orig.id] = label_of(code, orig.year, orig.number)
    return [{
        "id": e.id, "journal_id": e.journal_id, "journal_code": code, "label": label_of(code, e.year, e.number),
        "entry_date": e.entry_date, "description": e.description, "document_ref": e.document_ref, "status": e.status,
        "debit": debit or Decimal("0"), "credit": credit or Decimal("0"), "lines": lines or 0,
        "reversal_of": original_label.get(e.reversal_of_id), "reversed_by": reversed_by.get(e.id),
        "automatic": e.source_kind is not None,
    } for e, code, debit, credit, lines in rows]


async def get_entry(db: AsyncSession, company_id: uuid.UUID, entry_id: uuid.UUID) -> dict:
    entry = await _entry(db, company_id, entry_id)
    code = (await db.execute(select(Journal.code).where(Journal.id == entry.journal_id))).scalar_one()
    rows = (await db.execute(select(JournalEntryLine, Account.code, Account.name).join(Account, Account.id == JournalEntryLine.account_id)
                             .where(JournalEntryLine.entry_id == entry.id).order_by(JournalEntryLine.position))).all()
    listed = [e for e in await list_entries(db, company_id, journal_id=entry.journal_id, date_from=entry.entry_date,
                                            date_to=entry.entry_date, limit=10000) if e["id"] == entry.id][0]
    return {**listed, "lines": [{
        "account_id": l.account_id, "account_code": acode, "account_name": aname, "description": l.description,
        "debit": l.debit, "credit": l.credit,
    } for l, acode, aname in rows], "line_count": len(rows), "posted_at": entry.posted_at}
