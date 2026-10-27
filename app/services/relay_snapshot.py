"""
The relay's photo (P4 step 5): what the client's server sends to the platform every few minutes, so that the site still
reads the catalogue and the availability while the server is off.

build_snapshot runs on the client's server (the agent); answer runs on the platform, from the last photo - with the
same filters and the same shape as the live API (app.api.public_v1), so the site cannot tell, but by the headers
X-RM-Offline and X-RM-Snapshot-At.
"""
import uuid
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

BUSY_DAYS = 400  # the bookings sent ahead (the availability a site can ask)
MAX_ITEMS = 5000


# --------------------------------------------------------------------------------------- built on the client's server

async def build_snapshot(db: AsyncSession, company_id: uuid.UUID) -> dict:
    from app.models.booking import Booking, BookingStatus
    from app.models.resource import Resource
    from app.services import public_api_service as public
    from app.services import public_bookings_service as bookings
    from app.services import public_documents_service as documents

    async def every(lister) -> list:
        items, page = [], 1
        while len(items) < MAX_ITEMS:
            got = await lister(page)
            items += got["items"]
            if page * got["page_size"] >= got["total"]:
                return items
            page += 1
        return items

    now = datetime.now(timezone.utc)
    types = await bookings._types(db, company_id)
    resources, rates = [], {}
    for resource_type in types:
        resources += [{"id": str(r.id), "name": r.name, "capacity": r.capacity, "type_id": str(resource_type.id)}
                      for r in await bookings._resources(db, company_id, resource_type.id)]
        services, vat = await bookings._rates(db, company_id, resource_type.id)
        rates[str(resource_type.id)] = [{"service_id": str(s.id), "name": s.name, "price": public._money(s.price),
                                         "vat_rate": vat[s.id], "price_with_vat": public._with_vat(s.price, vat[s.id])}
                                        for s in services]
    busy: dict[str, list] = {}
    rows = (await db.execute(select(Booking.resource_id, Booking.starts_at, Booking.ends_at).where(
        Booking.company_id == company_id, Booking.ends_at > now, Booking.starts_at < now + timedelta(days=BUSY_DAYS),
        or_(Booking.status.in_((BookingStatus.PENDENTE, BookingStatus.CONFIRMADA, BookingStatus.EM_CURSO)),
            and_(Booking.status == BookingStatus.CONCLUIDA, Booking.invoice_id.is_not(None),
                 Booking.checked_out_at.is_(None)))))).all()
    for resource_id, start, end in rows:
        busy.setdefault(str(resource_id), []).append([start.isoformat(), end.isoformat()])

    from fastapi.encoders import jsonable_encoder
    return jsonable_encoder({
        "taken_at": now,
        "activities": await documents.list_activities(db, company_id),
        "catalog": {
            "products": await every(lambda page: public.list_products(db, company_id, page=page, page_size=200)),
            "services": await every(lambda page: public.list_services(db, company_id, page=page, page_size=200)),
            "categories": await public.list_categories(db, company_id),
        },
        "bookings": {
            "types": [{"id": str(t.id), "name": t.name,
                       "default_start_time": t.default_start_time.isoformat() if t.default_start_time else None,
                       "default_end_time": t.default_end_time.isoformat() if t.default_end_time else None}
                      for t in types],
            "resources": resources, "rates": rates, "busy": busy,
        },
    })


# ------------------------------------------------------------------------------------------- answered on the platform

class SnapshotRefusal(Exception):
    """A request the photo answers with an error (422 / 404), as the live API would."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code


def _params(query: str | None) -> dict:
    return {k: v[-1] for k, v in parse_qs(query or "", keep_blank_values=False).items()}


def _int(params: dict, name: str, default: int, top: int | None = None) -> int:
    try:
        value = int(params.get(name, default))
    except ValueError:
        raise SnapshotRefusal(422, f"{name}: número inteiro")
    if value < 1 or (top is not None and value > top):
        raise SnapshotRefusal(422, f"{name}: entre 1 e {top}" if top else f"{name}: pelo menos 1")
    return value


def _when(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SnapshotRefusal(422, f"Data inválida: {value}")
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone(timedelta(hours=1)))


def _page_of(items: list, params: dict) -> dict:
    page, size = _int(params, "page", 1), _int(params, "page_size", 50, 200)
    since = _when(params.get("updated_since"))
    if since is not None:
        items = [i for i in items if i.get("updated_at") and _when(i["updated_at"]) >= since]
    return {"items": items[(page - 1) * size: page * size], "page": page, "page_size": size, "total": len(items)}


def _contains(item: dict, fields: tuple, text: str) -> bool:
    text = text.strip().casefold()
    return any(text in str(item.get(f) or "").casefold() for f in fields)


def _products(snapshot: dict, params: dict) -> dict:
    items = snapshot["catalog"]["products"]
    if params.get("search"):
        items = [p for p in items if _contains(p, ("name", "code", "brand"), params["search"])]
    if params.get("category"):
        items = [p for p in items if (p.get("category") or "").casefold() == params["category"].strip().casefold()]
    if params.get("barcode"):
        code = params["barcode"].strip()
        items = [p for p in items if p.get("barcode") == code or any(u.get("barcode") == code
                                                                      for u in p.get("sale_units") or [])]
    return _page_of(items, params)


def _one(items: list, item_id: str, what: str) -> dict:
    for item in items:
        if item["id"] == item_id:
            return item
    raise SnapshotRefusal(404, f"{what} não encontrado")


def _availability(snapshot: dict, params: dict) -> list:
    from app.services.public_api_service import PublicApiError, _with_vat
    from app.services.public_bookings_service import period

    def day(name):
        from datetime import date
        try:
            return date.fromisoformat(params[name]) if params.get(name) else None
        except ValueError:
            raise SnapshotRefusal(422, f"{name}: data inválida (AAAA-MM-DD)")
    check_in, check_out = day("check_in"), day("check_out")
    starts_at, ends_at = _when(params.get("starts_at")), _when(params.get("ends_at"))
    party = _int(params, "party_size", 1) if params.get("party_size") else None
    wanted = params.get("resource_type_id")
    data = snapshot["bookings"]
    out = []
    for t in data["types"]:
        if wanted and t["id"] != wanted:
            continue
        resources = [r for r in data["resources"] if r["type_id"] == t["id"]]
        if not resources:
            continue
        shape = SimpleNamespace(
            default_start_time=time.fromisoformat(t["default_start_time"]) if t["default_start_time"] else None,
            default_end_time=time.fromisoformat(t["default_end_time"]) if t["default_end_time"] else None)
        try:
            start, end, nights = period(shape, check_in, check_out, starts_at, ends_at)
        except PublicApiError as e:
            raise SnapshotRefusal(422, str(e))
        if party:
            resources = [r for r in resources if r["capacity"] is None or r["capacity"] >= party]
        free = [r for r in resources if not any(
            _when(s) < end and _when(e) > start for s, e in data["busy"].get(r["id"], []))]
        out.append({
            "resource_type_id": t["id"], "resource_type": t["name"], "starts_at": start.isoformat(),
            "ends_at": end.isoformat(), "nights": nights, "available": len(free), "total": len(resources),
            "resources": [{"id": r["id"], "name": r["name"], "capacity": r["capacity"]} for r in free],
            "rates": [{**rate, "stay_total_with_vat": _with_vat((rate["price"] or 0) * (nights or 1), rate["vat_rate"])}
                      for rate in data["rates"].get(t["id"], [])],
        })
    if wanted and not out:
        raise SnapshotRefusal(404, "Tipo de recurso não encontrado ou sem recursos")
    return out


def answer(snapshot: dict, path: str, query: str | None):
    """The answer of a read from the photo - None: this read needs the server (documents, customers, bookings...)."""
    params = _params(query)
    parts = [p for p in path.strip("/").split("/") if p]
    catalog = snapshot["catalog"]
    if parts == ["activities"]:
        return snapshot["activities"]
    if parts == ["catalog", "categories"]:
        return catalog["categories"]
    if parts == ["catalog", "products"]:
        return _products(snapshot, params)
    if len(parts) == 3 and parts[:2] == ["catalog", "products"]:
        return _one(catalog["products"], parts[2], "Produto")
    if parts == ["catalog", "services"]:
        items = catalog["services"]
        if params.get("search"):
            items = [s for s in items if _contains(s, ("name", "code"), params["search"])]
        return _page_of(items, params)
    if len(parts) == 3 and parts[:2] == ["catalog", "services"]:
        return _one(catalog["services"], parts[2], "Serviço")
    if parts == ["bookings", "availability"]:
        return _availability(snapshot, params)
    return None
