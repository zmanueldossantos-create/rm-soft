"""
Business logic for DocumentSeries - the numbering series behind every
invoice's InvoiceNo (SAF-T XSD format "{DocType} {series_code}/{number}",
space required). See Video 4/8 and the Kiami reference-system walkthrough:

- MANUAL mode: GESTOR can target one specific document type, or "Todos"
  (document_type_id=None) - which, rather than storing a single row with
  a null type, transparently creates ONE row per eligible document type
  (filtered by the Facturacao/Tesouraria/Compras toggles), all sharing
  the same series_code/description/dates. This keeps every document type
  its own independent counter (current_number) even under one "Todos"
  action, while avoiding a nullable document_type_id and its associated
  uniqueness/counting complications.
- ELETRONICA mode: no "Todos" - a specific, AGT-electronic-eligible
  document type must be chosen; the 3 area toggles are then auto-derived
  from that type's own area (read-only, single flag on) rather than
  freely chosen. A type sent to the AGT gets its code FROM the AGT
  (solicitarSerie - app.services.agt_series_service), per establishment,
  normal (N) or contingência (C); a working document never sent to the
  AGT (pro-forma, guias...) gets a local "{TIPO}{ANO}" code.
- Area flags (is_facturacao/is_tesouraria/is_compras) are always
  auto-derived from the doc type's own `area` for a specific-type series;
  they are only meaningfully user-chosen when picking "Todos" in MANUAL
  mode, where they decide which document types get included.
"""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_series import DocumentSeries, ContingencyIndicator
from app.models.company import Company
from app.models.document_type import DocumentType
from app.models.establishment import Establishment
from app.services.ownership import ensure_owned


class SeriesNotFoundError(Exception):
    pass


class SeriesAlreadyExistsError(Exception):
    """Raised when a specific-type series creation collides with an existing (company, doc type, year) row."""
    pass


class ManualSeriesCodeRequiredError(Exception):
    """Raised when the company has 'auto_series_year' off and no free-typed series_code was given."""
    pass


class ElectronicTypeNotEligibleError(Exception):
    """Raised when the chosen document type is not part of the AGT electronic-invoicing subset."""
    pass


class TodosNotAllowedInElectronicError(Exception):
    """Raised when "Todos" (document_type_id=None) is requested while the company is in ELETRONICA mode."""
    pass


class SeriesYearNotAllowedError(Exception):
    """A series asked for a year the AGT does not allow yet (or any more)."""


def allowed_series_years(today: date | None = None) -> list[int]:
    """
    THE AGT rule (field seriesYear of solicitarSerie): from 1 January to 15 December a series can only be created for
    the current year; after 15 December, also for the next one. Applied in both issuance modes, so a manual series
    is never prepared for a year the AGT would refuse.
    """
    today = today or date.today()
    years = [today.year]
    if (today.month, today.day) > (12, 15):
        years.append(today.year + 1)
    return years


def _current_year() -> int:
    return date.today().year


async def list_series(db: AsyncSession, company_id: uuid.UUID, year: int | None = None) -> list[DocumentSeries]:
    query = select(DocumentSeries).where(DocumentSeries.company_id == company_id)
    if year is not None:
        query = query.where(DocumentSeries.year == year)
    result = await db.execute(query.order_by(DocumentSeries.year.desc(), DocumentSeries.series_code))
    return list(result.scalars().all())


async def get_series_or_raise(db: AsyncSession, company_id: uuid.UUID, series_id: uuid.UUID) -> DocumentSeries:
    result = await db.execute(select(DocumentSeries).where(DocumentSeries.id == series_id, DocumentSeries.company_id == company_id))
    series = result.scalar_one_or_none()
    if series is None:
        raise SeriesNotFoundError("Serie não encontrada")
    return series


def _area_flags_for(doc_type: DocumentType) -> tuple[bool, bool, bool]:
    """Auto-derives the (Facturacao, Tesouraria, Compras) toggle values from a document type's own area."""
    return (
        doc_type.area == "FACTURACAO",
        doc_type.area == "TESOURARIA",
        doc_type.area == "COMPRAS",
    )


def same_scope(company: Company, doc_type: DocumentType, year: int, establishment_id: uuid.UUID | None,
               contingency_indicator: str | None):
    """The rows a new series would collide with (see the unique index uq_series_scope). A working document never sent
    to the AGT (pro-forma, guias...) keeps ONE series per year whatever the mode: a second one would repeat its
    numbers («FP FP2026/1» twice)."""
    if not doc_type.sent_to_agt:
        return select(DocumentSeries).where(DocumentSeries.company_id == company.id,
                                            DocumentSeries.document_type_id == doc_type.id, DocumentSeries.year == year)
    contingency = contingency_indicator or "NORMAL"
    query = select(DocumentSeries).where(
        DocumentSeries.company_id == company.id,
        DocumentSeries.document_type_id == doc_type.id,
        DocumentSeries.year == year,
        DocumentSeries.issuance_mode == company.issuance_mode,
        DocumentSeries.establishment_id.is_(None) if establishment_id is None
        else DocumentSeries.establishment_id == establishment_id,
    )
    if contingency == "CONTINGENCIA":
        return query.where(DocumentSeries.contingency_indicator == ContingencyIndicator.CONTINGENCIA)
    return query.where((DocumentSeries.contingency_indicator.is_(None))
                       | (DocumentSeries.contingency_indicator == ContingencyIndicator.NORMAL))


def new_series_row(company: Company, doc_type: DocumentType, year: int, establishment_id: uuid.UUID | None,
                   series_code: str, description: str | None, contingency_indicator: str | None,
                   is_predefined: bool) -> DocumentSeries:
    is_fact, is_tes, is_comp = _area_flags_for(doc_type)
    return DocumentSeries(
        company_id=company.id,
        establishment_id=establishment_id,
        document_type_id=doc_type.id,
        year=year,
        issuance_mode=company.issuance_mode,
        series_code=series_code,
        description=description,
        date_start=date(year, 1, 1),
        date_end=date(year, 12, 31),
        contingency_indicator=ContingencyIndicator(contingency_indicator) if contingency_indicator else None,
        is_predefined=is_predefined,
        is_facturacao=is_fact,
        is_tesouraria=is_tes,
        is_compras=is_comp,
        number_start=1,
        number_end=999999999,
        current_number=0,
    )


async def _create_one_series(
    db: AsyncSession, company: Company, doc_type: DocumentType, year: int,
    establishment_id: uuid.UUID | None, series_code: str | None, description: str | None,
    contingency_indicator: str | None, is_predefined: bool,
) -> DocumentSeries:
    """A series made here (MANUAL mode, or a working document never sent to the AGT) - the AGT's own series are
    requested in app.services.agt_series_service."""
    if company.issuance_mode == "ELETRONICA":
        contingency_indicator = contingency_indicator or "NORMAL"
    if (await db.execute(same_scope(company, doc_type, year, establishment_id, contingency_indicator))).scalars().first():
        raise SeriesAlreadyExistsError(f"Já existe uma serie para {doc_type.code} neste ano neste modo")

    if company.issuance_mode == "ELETRONICA" or company.auto_series_year:
        # SAF-T XSD rule: the series identifier must stay unique per document type,
        # so the bare year alone is not enough here.
        final_series_code = f"{doc_type.code}{year}"
        if company.issuance_mode == "ELETRONICA" and contingency_indicator == "CONTINGENCIA":
            final_series_code += "C"
    else:
        if not series_code:
            raise ManualSeriesCodeRequiredError("Código de serie obrigatório quando a serie automática por ano esta desativada")
        final_series_code = series_code

    series = new_series_row(company, doc_type, year, establishment_id, final_series_code, description,
                            contingency_indicator, is_predefined)
    db.add(series)
    return series


async def create_series(
    db: AsyncSession,
    company: Company,
    document_type_id: uuid.UUID | None,
    year: int | None = None,
    establishment_id: uuid.UUID | None = None,
    series_code: str | None = None,
    description: str | None = None,
    contingency_indicator: str | None = None,
    is_predefined: bool = True,
    todos_facturacao: bool = False,
    todos_tesouraria: bool = False,
    todos_compras: bool = False,
) -> list[DocumentSeries]:
    """
    document_type_id=None means "Todos" (MANUAL mode only) - creates one row per
    active document type matching the todos_* area toggles, all sharing the same
    series_code/description/dates. Returns the list of series rows created.
    """
    year = year or _current_year()
    await ensure_owned(db, company.id, Establishment, establishment_id, "Estabelecimento não encontrado")

    allowed = allowed_series_years()
    if year not in allowed:
        raise SeriesYearNotAllowedError("So é possível criar series para " + " ou ".join(str(y) for y in allowed))

    if document_type_id is None:
        if company.issuance_mode == "ELETRONICA":
            raise TodosNotAllowedInElectronicError('"Todos" só esta disponível em modo Manual')

        wanted_areas = []
        if todos_facturacao:
            wanted_areas.append("FACTURACAO")
        if todos_tesouraria:
            wanted_areas.append("TESOURARIA")
        if todos_compras:
            wanted_areas.append("COMPRAS")

        query = select(DocumentType).where(DocumentType.is_active == True)  # noqa: E712
        if wanted_areas:
            query = query.where(DocumentType.area.in_(wanted_areas))
        doc_types_result = await db.execute(query)
        doc_types = list(doc_types_result.scalars().all())

        created = []
        for doc_type in doc_types:
            existing = await db.execute(select(DocumentSeries).where(
                DocumentSeries.company_id == company.id,
                DocumentSeries.document_type_id == doc_type.id,
                DocumentSeries.year == year,
            ))
            if existing.scalar_one_or_none() is not None:
                continue  # already has a series this year - skip rather than fail the whole batch
            created.append(await _create_one_series(
                db, company, doc_type, year, establishment_id, series_code, description,
                contingency_indicator, is_predefined,
            ))
        await db.commit()
        for s in created:
            await db.refresh(s)
        return created

    doc_type_result = await db.execute(select(DocumentType).where(DocumentType.id == document_type_id))
    doc_type = doc_type_result.scalar_one()

    # Non-fiscal working documents (Pro-forma, Guias, Orcamento...) are never submitted
    # to AGT regardless of the company's issuance mode, so they're exempt from this
    # restriction - only fiscal document types must match the AGT electronic-submission
    # subset. See DocumentType.is_fiscal / electronic_eligible field docstrings, and the
    # matching frontend fix in CompanySettings.jsx's eligibleTypes filter.
    if company.issuance_mode == "ELETRONICA" and not doc_type.electronic_eligible and doc_type.is_fiscal:
        raise ElectronicTypeNotEligibleError(f"{doc_type.code} não está disponível para facturação eletrónica")
    if company.issuance_mode == "ELETRONICA" and not doc_type.sent_to_agt:
        # its series goes on across the mode switch, or is made at its first document (get_or_create_current_series)
        raise ElectronicTypeNotEligibleError(f"{doc_type.code} não é enviado à AGT: a sua série é criada automaticamente "
                                             "no primeiro documento (ou continua a da emissão manual)")

    if company.issuance_mode == "ELETRONICA" and doc_type.sent_to_agt:
        # the AGT gives the code: solicitarSerie for this establishment, N or C
        from app.services.agt_series_service import request_series
        return [await request_series(db, company, doc_type, year, establishment_id,
                                     (contingency_indicator or "NORMAL") == "CONTINGENCIA", description, is_predefined)]

    series = await _create_one_series(
        db, company, doc_type, year, establishment_id, series_code, description,
        contingency_indicator, is_predefined,
    )
    await db.commit()
    await db.refresh(series)
    return [series]


async def get_or_create_current_series(db: AsyncSession, company: Company, document_type_id: uuid.UUID,
                                       contingency: bool | None = None) -> DocumentSeries:
    """
    Used by invoice creation - returns this year's series for the given
    document type, auto-creating it only when the company is in MANUAL
    mode with auto_series_year on (the year-based code needs no human
    input). Any other case (manual+free code, or electronic) must already
    have been explicitly created - see create_series.

    Only considers a series matching the company's CURRENT issuance_mode - a
    series created before a mode switch (e.g. a MANUAL-era "FT2026") must not
    keep being reused after the company moves to ELETRONICA, or vice versa.

    ELETRONICA mode: a series is uniquely keyed by establishment too (see AGT
    "Solicitar Serie" spec - taxRegistrationNumber + establishmentNumber +
    seriesYear + documentType). With a single active establishment (the
    common "SEDE" case for a contribuinte with one location, or one NIF
    covering several activities like bar/hotel/resto under the same fiscal
    point) it is resolved automatically; with 0 or 2+ establishments the
    caller must be told explicitly rather than silently picking the wrong one.

    Contingência (ELETRONICA, a type sent to the AGT): while the AGT cannot be reached the document takes the
    establishment's C series (within its emission period when the AGT gave one) - the N series when there is no valid
    one. contingency None: the company's current state (app.services.agt_contingency).
    """
    year = _current_year()

    doc_type = await db.get(DocumentType, document_type_id)
    if doc_type is not None and not doc_type.sent_to_agt:
        # a working document never sent to the AGT: ONE series a year whatever the mode (it goes on after a switch to
        # ELETRONICA - a new one would repeat its numbers), made at its first document when there is none
        series = (await db.execute(select(DocumentSeries).where(
            DocumentSeries.company_id == company.id, DocumentSeries.document_type_id == document_type_id,
            DocumentSeries.year == year, DocumentSeries.is_active == True)  # noqa: E712
            .order_by(DocumentSeries.current_number.desc(), DocumentSeries.created_at))).scalars().first()
        if series is not None:
            return series
        if company.issuance_mode == "ELETRONICA" or company.auto_series_year:
            series = await _create_one_series(db, company, doc_type, year, None, None, None, None, True)
            await db.commit()
            await db.refresh(series)
            return series
        raise SeriesNotFoundError("Nenhuma serie configurada para este tipo de documento neste ano - configure-a em Configurações")

    establishment_id = None
    if company.issuance_mode == "ELETRONICA":
        est_result = await db.execute(select(Establishment).where(
            Establishment.company_id == company.id, Establishment.is_active == True,  # noqa: E712
        ))
        establishments = list(est_result.scalars().all())
        if len(establishments) == 0:
            raise SeriesNotFoundError(
                "Nenhum estabelecimento ativo configurado - crie pelo menos um (ex: SEDE) antes de faturar em modo eletrónico"
            )
        if len(establishments) > 1:
            raise SeriesNotFoundError(
                "Existem varios estabelecimentos ativos - a factura deve indicar explicitamente qual deles a emite"
            )
        establishment_id = establishments[0].id

    query = select(DocumentSeries).where(
        DocumentSeries.company_id == company.id,
        DocumentSeries.document_type_id == document_type_id,
        DocumentSeries.year == year,
        DocumentSeries.issuance_mode == company.issuance_mode,
        DocumentSeries.is_active == True,  # noqa: E712
    )
    if establishment_id is not None:
        query = query.where(DocumentSeries.establishment_id == establishment_id)

    if company.issuance_mode == "ELETRONICA":
        query = query.where((DocumentSeries.agt_status.is_(None)) | (DocumentSeries.agt_status != "F"))  # not closed
        if doc_type is not None and doc_type.sent_to_agt:
            if contingency is None:
                from app.services.agt_contingency import in_contingency
                contingency = await in_contingency(db, company.id)
            if contingency:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                rows = (await db.execute(query.where(
                    DocumentSeries.contingency_indicator == ContingencyIndicator.CONTINGENCIA))).scalars().all()
                usable = [r for r in rows if (r.series_start_ts is None or r.series_start_ts <= now)
                          and (r.series_end_ts is None or now <= r.series_end_ts)]
                if usable:
                    return usable[0]
                # no valid C series: the N series (a sale is never refused for it) - the document waits in the queue
                # all the same; the screen says that a C series is missing (agt_contingency.status)
        query = query.where((DocumentSeries.contingency_indicator.is_(None))
                            | (DocumentSeries.contingency_indicator == ContingencyIndicator.NORMAL))

    result = await db.execute(query)
    series = result.scalars().first()
    if series is not None:
        return series

    if company.issuance_mode == "MANUAL" and company.auto_series_year:
        try:
            created = await create_series(db, company, document_type_id, year=year)
            return created[0]
        except SeriesAlreadyExistsError:
            # A row already exists for (doctype, year) in a DIFFERENT mode - the unique
            # constraint includes issuance_mode, so this should be rare, but surface a clear
            # message instead of letting the raw IntegrityError-derived error leak as a 500.
            raise SeriesNotFoundError(
                "Não foi possível criar automaticamente a serie para este modo - configure-a manualmente em Configurações"
            )

    raise SeriesNotFoundError("Nenhuma serie configurada para este tipo de documento neste ano - configure-a em Configurações")


async def get_next_number(db: AsyncSession, series: DocumentSeries) -> int:
    """Increments and returns the series' running counter - one call per issued document.
    Uses flush (not commit) so this stays inside the caller's own transaction: if invoice
    creation later rolls back (e.g. insufficient stock), the number is never actually
    consumed - a committed gap in the sequence would violate SAF-T continuity."""
    if series.current_number + 1 > series.number_end:
        raise SeriesNotFoundError(f"Série {series.series_code} esgotada (último número autorizado: {series.number_end}) "
                                  "- peça uma nova série à AGT")
    series.current_number += 1
    await db.flush()
    return series.current_number


async def update_series(
    db: AsyncSession, company_id: uuid.UUID, series_id: uuid.UUID,
    description: str | None = None, is_predefined: bool | None = None,
) -> DocumentSeries:
    """Only description and is_predefined are editable after creation (the N/C indicator is the AGT's) -
    everything else (year, document type, series_code, number range, dates, area flags) stays fixed
    once issued, since already-emitted invoices reference the series exactly as it was."""
    series = await get_series_or_raise(db, company_id, series_id)
    series.description = description
    if is_predefined is not None:
        series.is_predefined = is_predefined
    await db.commit()
    await db.refresh(series)
    return series


async def toggle_series(db: AsyncSession, company_id: uuid.UUID, series_id: uuid.UUID) -> DocumentSeries:
    series = await get_series_or_raise(db, company_id, series_id)
    series.is_active = not series.is_active
    await db.commit()
    await db.refresh(series)
    return series