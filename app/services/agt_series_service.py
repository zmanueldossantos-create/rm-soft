"""
The AGT's numbering series (Faturação Eletrónica): asked with solicitarSerie - one per document type, year,
establishment and indicator (N normal, C contingência) - and read back with listarSeries («Sincronizar com a AGT»):
the AGT is the reference, a series it knows and this server does not (another installation, a reinstall) is added
here with its last number used, so the numbering goes on without a gap or a double.

In Homologação a company sending as an AGT test NIF asks under that NIF, with the establishment «SEDE» (the sandbox's
default - the test NIF has none of the company's establishments).
"""
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.document_series import ContingencyIndicator, DocumentSeries
from app.models.document_type import DocumentType
from app.models.establishment import Establishment
from app.services import agt_client
from app.services.document_series_service import (SeriesAlreadyExistsError, new_series_row, same_scope)

LUANDA = timezone(timedelta(hours=1))
INT_MAX = 2_147_483_647  # number_end is an INTEGER; the AGT authorises up to 999999999999


class AgtSeriesError(Exception):
    """Refused - the message is shown as it is."""


def _int(value, default: int | None = None) -> int | None:
    """A number the AGT sends as text ("1", "999999999999") or inside a document number ("FT FT26SEDEN/57")."""
    match = re.search(r"(\d+)\s*$", str(value or "").strip())
    return min(int(match.group(1)), INT_MAX) if match else default


def _when(value) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except ValueError:
        return None
    if moment is not None and moment.tzinfo is None:
        moment = moment.replace(tzinfo=LUANDA)  # the AGT writes Angola's time without its offset
    return moment


def establishment_number(ctx: agt_client.AgtContext, company: Company, establishment: Establishment | None) -> str:
    if ctx.nif != company.nif.strip() or establishment is None:
        return "SEDE"
    return establishment.code


async def _refuse_errors(answer) -> None:
    errors = agt_client.error_list(answer)
    if errors:
        raise agt_client.AgtRefused(200, answer, agt_client.describe(errors))


async def request_series(db: AsyncSession, company: Company, doc_type: DocumentType, year: int,
                         establishment_id: uuid.UUID | None, contingency: bool, description: str | None,
                         is_predefined: bool) -> DocumentSeries:
    """solicitarSerie, then the series saved with the AGT's code and range. AgtConfigError / AgtUnavailable /
    AgtRefused go up as they are (the route turns them into messages)."""
    if establishment_id is None:
        raise AgtSeriesError("Escolha o estabelecimento que emite com esta série")
    establishment = await db.get(Establishment, establishment_id)
    if establishment is None or establishment.company_id != company.id:
        raise AgtSeriesError("Estabelecimento não encontrado")
    indicator = "CONTINGENCIA" if contingency else "NORMAL"
    if (await db.execute(same_scope(company, doc_type, year, establishment_id, indicator))).scalars().first():
        raise SeriesAlreadyExistsError(f"Já existe uma série {'de contingência' if contingency else 'normal'} para "
                                       f"{doc_type.code} {year} neste estabelecimento")

    ctx = await agt_client.context_for(db, company)
    answer = await agt_client.solicitar_serie(ctx, year, doc_type.code, establishment_number(ctx, company, establishment),
                                              "C" if contingency else "N")
    await _refuse_errors(answer)
    result = (answer or {}).get("seriesFEResult") if isinstance(answer, dict) else None
    code = str((result or {}).get("seriesCode") or "").strip()
    if not code:
        raise AgtSeriesError("A AGT não devolveu o código da série")

    series = new_series_row(company, doc_type, year, establishment_id, code[:30], description, indicator, is_predefined)
    first = _int(result.get("firstDocumentNo"), 1)
    series.number_start, series.number_end = first, _int(result.get("lastDocumentNo"), INT_MAX)
    series.current_number = first - 1
    series.agt_status, series.agt_synced_at = "A", datetime.now(timezone.utc)
    db.add(series)
    await db.commit()
    await db.refresh(series)
    return series


async def sync_series(db: AsyncSession, company: Company) -> dict:
    """listarSeries for each active establishment: the AGT's status, range and period of every series; a series the
    AGT knows and this server does not is added (with its last number used)."""
    ctx = await agt_client.context_for(db, company)
    establishments = (await db.execute(select(Establishment).where(
        Establishment.company_id == company.id, Establishment.is_active.is_(True))
        .order_by(Establishment.created_at))).scalars().all()
    if not establishments:
        raise AgtSeriesError("Nenhum estabelecimento ativo - crie pelo menos um (ex: SEDE)")
    types = {t.code: t for t in (await db.execute(select(DocumentType))).scalars().all()}
    now = datetime.now(timezone.utc)
    updated, added, unknown = 0, 0, []
    asked: set[str] = set()
    for establishment in establishments:
        number = establishment_number(ctx, company, establishment)
        if number in asked:  # a test NIF: «SEDE» for every establishment - asked once
            continue
        asked.add(number)
        answer = await agt_client.listar_series(ctx, establishmentNumber=number)
        await _refuse_errors(answer)
        # the AGT's example writes «seriresInfo»: both spellings read
        infos = (answer.get("seriesInfo") or answer.get("seriresInfo") or []) if isinstance(answer, dict) else []
        for info in infos:
            if not isinstance(info, dict) or not info.get("seriesCode"):
                continue
            code = str(info["seriesCode"]).strip()[:30]
            row = (await db.execute(select(DocumentSeries).where(
                DocumentSeries.company_id == company.id, DocumentSeries.series_code == code))).scalar_one_or_none()
            if row is None:
                doc_type = types.get(str(info.get("documentType") or "").strip())
                year = _int(info.get("seriesYear"))
                if doc_type is None or year is None:
                    unknown.append(code)
                    continue
                indicator = "CONTINGENCIA" if info.get("seriesContingencyIndicator") == "C" else "NORMAL"
                if (await db.execute(same_scope(company, doc_type, year, establishment.id, indicator))).scalars().first():
                    unknown.append(code)  # this server already has another series in that place
                    continue
                row = new_series_row(company, doc_type, year, establishment.id, code, "Importada da AGT", indicator,
                                     True)
                db.add(row)
                added += 1
            else:
                updated += 1
            row.agt_status = str(info.get("seriesStatus") or "").strip()[:1] or row.agt_status
            first = _int(info.get("firstDocumentApproved"))
            last = _int(info.get("lastDocumentApproved"))
            if first is not None:
                row.number_start = first
            if last is not None:
                row.number_end = last
            used = _int(info.get("lastDocumentCreated"))
            if used is not None and used > row.current_number:
                row.current_number = used  # never backwards: a number given here is never given again
            row.series_start_ts = _when(info.get("seriesStartTS")) or row.series_start_ts
            row.series_end_ts = _when(info.get("seriesEndTS")) or row.series_end_ts
            if row.contingency_indicator is None:
                row.contingency_indicator = ContingencyIndicator(
                    "CONTINGENCIA" if info.get("seriesContingencyIndicator") == "C" else "NORMAL")
            row.agt_synced_at = now
    await db.commit()
    return {"updated": updated, "added": added, "unknown": unknown}
