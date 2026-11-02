"""
Catálogo inicial: loads into an EXISTING company (created by the SUPER_ADMIN in Empresas, its period open) the base of a
new client from a JSON file, so the training shows the screens on a company already alive - and creates only ONE
example of each kind in front of the owners. Everything goes through the same services as the screens.

    python -m app.tools.catalogo_inicial 5003112330 instalador/catalogos/meldarocha_padaria.json --verificar   (reads only)
    python -m app.tools.catalogo_inicial 5003112330 instalador/catalogos/meldarocha_padaria.json

What it loads, in this order (every key optional): categorias, fornecedores, materias_primas, produtos, servicos,
receitas, clientes, compras (purchase invoices with their stock entry: the stock comes in as in real life), and a
"hotel" block - room types with their rates ("tarifas": the night without "duracao_min", the timed ones with it) and rooms, hotel services - loaded only when the company has the Hotel
module (run it again after granting it). It may be run again: what already exists (same code, name or document) is
left as it is and listed - never duplicated, never overwritten. Refused for a company with real (non-training)
sales documents.

Units (KG, L...) come from the platform's catalog: a missing one is named before anything is created.
"""
import asyncio
import json
import sys
from datetime import date, time, timedelta
from pathlib import Path

from sqlalchemy import select


def say(text: str) -> None:
    print(text, flush=True)


class CatalogError(Exception):
    """The catalog cannot be loaded - the message says why (PT-PT)."""


def _time(value: str | None, field: str) -> time | None:
    if not value:
        return None
    try:
        hours, minutes = value.split(":")
        return time(int(hours), int(minutes))
    except (ValueError, TypeError):
        raise CatalogError(f"Hora inválida em «{field}»: {value} (formato HH:MM)")


def _positive(value, what: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise CatalogError(f"Valor inválido para {what}: {value}")
    if number <= 0:
        raise CatalogError(f"{what}: o valor tem de ser maior que zero")
    return number


async def load(db, nif: str, data: dict, dry_run: bool = False) -> dict:
    """Loads the file into the company with this NIF. Returns the report: what was created, what already existed."""
    from app.models.activity import Activity
    from app.models.company import Company
    from app.models.company_module import CompanyModule
    from app.models.customer import Customer
    from app.models.fiscal_regime import FiscalRegime
    from app.models.invoice import Invoice
    from app.models.legal_vat_rate import LegalVatRate
    from app.models.module import Module
    from app.models.product import Product
    from app.models.product_category import ProductCategory
    from app.models.purchase_invoice import PurchaseInvoice
    from app.models.recipe_ingredient import RecipeIngredient
    from app.models.resource import Resource
    from app.models.resource_type_catalog import ResourceTypeCatalog
    from app.models.service import Service
    from app.models.supplier import Supplier
    from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
    from app.models.user import User, UserRole
    from app.models.vat import VAT
    from app.services.activity_service import create_activity
    from app.services.customer_service import create_customer
    from app.services.product_category_service import create_product_category
    from app.services.product_service import create_product
    from app.services.purchase_invoice_service import register_purchase_invoice
    from app.services.recipe_service import set_recipe
    from app.services.resource_service import create_resource
    from app.services.resource_type_service import create_resource_type
    from app.services.service_service import create_service
    from app.services.supplier_service import create_supplier

    company = (await db.execute(select(Company).where(Company.nif == nif))).scalar_one_or_none()
    if company is None:
        raise CatalogError(f"Nenhuma empresa com o NIF {nif} - crie-a primeiro em Empresas")
    cid = company.id
    if (await db.execute(select(Invoice.id).where(
            Invoice.company_id == cid, Invoice.issuance_mode != "FORMACAO").limit(1))).first() is not None:
        raise CatalogError("A empresa já tem documentos reais - o catálogo inicial é só para uma empresa a começar")

    report = {"criados": [], "existentes": [], "ignorados": []}
    created, existed, skipped = report["criados"].append, report["existentes"].append, report["ignorados"].append

    # ---------------------------------------------------------------- what the platform and the company must have
    units = {u.code: u for u in (await db.execute(select(UnitOfMeasureCatalog))).scalars().all()}
    needed = {"UN"} | {item.get("unidade") or "UN" for key in ("materias_primas", "produtos", "servicos")
                       for item in data.get(key, [])}
    missing = sorted(code for code in needed if code not in units)
    if missing:
        raise CatalogError("Faltam unidades no catálogo da plataforma (SUPER_ADMIN: Configurações → Catálogos → "
                           "Unidades): " + ", ".join(missing))
    vats = {v.tax_category: v for v in (await db.execute(
        select(VAT).where(VAT.company_id == cid, VAT.is_active.is_(True)))).scalars().all()}
    regime = await db.get(FiscalRegime, company.fiscal_regime_id) if company.fiscal_regime_id else None
    legal = {}
    for rate in (await db.execute(select(LegalVatRate))).scalars().all():
        legal.setdefault(rate.tax_category, rate)
    gestor = (await db.execute(select(User).where(User.company_id == cid, User.role == UserRole.GESTOR))).scalars().first()

    def vat_for(code: str | None, what: str):
        allowed = [c for c in ("NOR", "RED", "ISE") if regime is None or getattr(regime, "allows_" + c.lower(), False)]
        category = code or ("NOR" if "NOR" in allowed else "ISE")
        if category not in allowed:
            raise CatalogError(f"{what}: a taxa {category} não é permitida pelo regime {regime.name}")
        if category not in vats:
            raise CatalogError(f"{what}: a empresa não tem a taxa de IVA {category} (Empresas → Taxas de IVA)")
        return vats[category]

    if data.get("compras"):
        from app.services.fiscal_period_service import PeriodClosedError, resolve_posting_period
        try:
            await resolve_posting_period(db, cid, None)
        except PeriodClosedError:
            raise CatalogError("As compras precisam de um período aberto: o gestor abre primeiro o exercício e o mês "
                               "em Finanças → Períodos/Exercício, depois corra de novo")

    granted = {m.name: m for m in (await db.execute(
        select(Module).join(CompanyModule, CompanyModule.module_id == Module.id)
        .where(CompanyModule.company_id == cid, CompanyModule.is_enabled.is_(True)))).scalars().all()}
    activities = {a.name: a for a in (await db.execute(select(Activity).where(Activity.company_id == cid))).scalars().all()}

    async def activity(name: str, module_name: str):
        if name in activities:
            return activities[name]
        if module_name not in granted:
            raise CatalogError(f"A empresa não tem o módulo {module_name} (Empresas → Módulos)")
        # the module's activity already made by the gestor, whatever its name: never a second one with its own till
        same_module = [a for a in activities.values() if a is not None and a.module_id == granted[module_name].id]
        if same_module:
            activities[name] = same_module[0]
            existed(f"Atividade {same_module[0].name} (módulo {module_name})")
            return same_module[0]
        activities[name] = None if dry_run else await create_activity(db, cid, granted[module_name].id, name)
        created(f"Atividade {name} (com a sua caixa)")
        return activities[name]

    # ------------------------------------------------------------------------------------------------ categories
    categories = {c.name: c for c in (await db.execute(
        select(ProductCategory).where(ProductCategory.company_id == cid))).scalars().all()}
    for name in data.get("categorias", []):
        if name in categories:
            existed(f"Categoria {name}")
            continue
        categories[name] = None if dry_run else await create_product_category(db, cid, name)
        created(f"Categoria {name}")

    def category_id(name: str | None, what: str):
        if not name:
            return None
        if name not in categories:
            raise CatalogError(f"{what}: categoria «{name}» desconhecida - acrescente-a em «categorias»")
        return categories[name].id if categories[name] is not None else None

    # ------------------------------------------------------------------------------------------------- suppliers
    suppliers = {s.name: s for s in (await db.execute(select(Supplier).where(Supplier.company_id == cid))).scalars().all()}
    for item in data.get("fornecedores", []):
        name = item["nome"]
        if name in suppliers:
            existed(f"Fornecedor {name}")
            continue
        suppliers[name] = None if dry_run else await create_supplier(
            db, cid, name, nif=item.get("nif"), phone_number=item.get("telefone"), email=item.get("email"),
            address=item.get("morada"), payment_terms=item.get("condicoes"))
        created(f"Fornecedor {name} (NIF {item.get('nif') or '-'})")

    # ------------------------------------------------------------------------ raw materials and finished articles
    products = {p.code: p for p in (await db.execute(select(Product).where(Product.company_id == cid))).scalars().all()}

    async def article(item: dict, raw: bool) -> None:
        code, name = item["codigo"], item["nome"]
        what = f"{'Matéria-prima' if raw else 'Artigo'} {code} {name}"
        if code in products:
            existed(what)
            return
        price = 0.0 if raw else _positive(item.get("preco"), what)
        vat = None if raw else vat_for(item.get("iva"), what)
        stocked = True if raw else bool(item.get("stock", True))
        if dry_run:
            products[code] = None
            created(what)
            return
        products[code] = await create_product(
            db, cid, code=code, name=name, barcode=item.get("codigo_barras"), vat_id=vat.id if vat else None,
            price=price, min_stock_threshold=float(item.get("stock_minimo") or 0) if stocked else 0,
            unit_of_measure_id=units[item.get("unidade") or "UN"].id,
            category_id=category_id(item.get("categoria"), what), purchase_price=item.get("custo"),
            is_raw_material=raw, managed_by_stock=stocked, managed_by_expiry=bool(item.get("validade")),
            not_available_pos=raw,
        )
        created(what)

    for item in data.get("materias_primas", []):
        await article(item, raw=True)
    for item in data.get("produtos", []):
        await article(item, raw=False)

    # -------------------------------------------------------------------------------------------------- services
    services = {s.code: s for s in (await db.execute(select(Service).where(Service.company_id == cid))).scalars().all()}

    async def service(item: dict, resource_type=None) -> None:
        code, name = item["codigo"], item["nome"]
        what = f"Serviço {code} {name}"
        if code in services:
            existed(what)
            return
        price = _positive(item.get("preco"), what)
        vat = vat_for(item.get("iva"), what)
        duration = item.get("duracao_min")  # a timed room rate (1 hora = 60): charged per started slice
        if duration is not None and (not isinstance(duration, int) or duration <= 0):
            raise CatalogError(f"{what}: duração inválida ({duration}) - minutos inteiros, maiores que zero")
        if not dry_run:
            services[code] = await create_service(
                db, cid, code=code, name=name, vat_id=vat.id, unit_of_measure_id=units[item.get("unidade") or "UN"].id,
                price=price, resource_type_id=resource_type.id if resource_type else None, duration_minutes=duration)
        created(what + (f" ({duration} min)" if duration else ""))

    for item in data.get("servicos", []):
        await service(item)

    # --------------------------------------------------------------------------------------------------- recipes
    with_recipe = set((await db.execute(select(RecipeIngredient.finished_product_id).where(
        RecipeIngredient.company_id == cid))).scalars().all())
    for item in data.get("receitas", []):
        code = item["produto"]
        what = f"Receita de {code}"
        if code not in products:
            raise CatalogError(f"{what}: o artigo {code} não existe")
        if products[code] is not None and products[code].id in with_recipe:
            existed(what)
            continue
        ingredients = []
        for ing in item.get("ingredientes", []):
            if ing["codigo"] not in products:
                raise CatalogError(f"{what}: o ingrediente {ing['codigo']} não existe")
            ingredients.append((ing["codigo"], _positive(ing.get("quantidade"), f"{what}, {ing['codigo']}")))
        batch_yield = _positive(item.get("rendimento"), f"{what}: rendimento")
        if not dry_run:
            await set_recipe(db, cid, products[code].id, batch_yield, [
                {"ingredient_product_id": products[c].id, "quantity_per_batch": q} for c, q in ingredients])
        created(f"{what} (lote de {batch_yield:g}, {len(ingredients)} ingredientes)")

    # ------------------------------------------------------------------------------------------------- customers
    customers = {c.name: c for c in (await db.execute(select(Customer).where(Customer.company_id == cid))).scalars().all()}
    for item in data.get("clientes", []):
        name = item["nome"]
        if name in customers:
            existed(f"Cliente {name}")
            continue
        if not dry_run:
            customers[name] = await create_customer(
                db, cid, name, item.get("nif") or "999999999", email=item.get("email"),
                phone_number=item.get("telefone"), address=item.get("morada"),
                legal_person_type=item.get("tipo") or "JURIDICA")
        created(f"Cliente {name}")

    # ------------------------------------------------------------------------- purchases: the stock comes in
    known = set((await db.execute(select(PurchaseInvoice.supplier_document).where(
        PurchaseInvoice.company_id == cid))).scalars().all())
    today = date.today()
    for item in data.get("compras", []):
        supplier_name, document = item["fornecedor"], item["documento"]
        what = f"Fatura de compra {document} ({supplier_name})"
        if document in known:
            existed(what)
            continue
        if supplier_name not in suppliers:
            raise CatalogError(f"{what}: fornecedor desconhecido")
        if "NOR" not in legal:
            raise CatalogError("Falta a taxa legal de IVA NOR no catálogo da plataforma")
        lines = []
        for line in item.get("linhas", []):
            code = line["codigo"]
            if code not in products:
                raise CatalogError(f"{what}: o artigo {code} não existe")
            rate = legal.get(line.get("iva") or "NOR")
            if rate is None:
                raise CatalogError(f"{what}: taxa legal {line.get('iva')} desconhecida")
            lines.append({
                "product_id": products[code].id if products[code] is not None else None,
                "description": code, "quantity": _positive(line.get("quantidade"), f"{what}, {code}"),
                "unit_price": float(line.get("preco") or 0), "legal_vat_rate_id": rate.id,
                "expiry_date": today + timedelta(days=int(line["validade_dias"])) if line.get("validade_dias") else None,
            })
        stock_activity = await activity(item.get("atividade") or "Padaria", item.get("modulo") or "Padaria")
        if not dry_run:
            await register_purchase_invoice(
                db, cid, gestor.id, suppliers[supplier_name].id, document, today, lines,
                due_date=today + timedelta(days=int(item["vencimento_dias"])) if item.get("vencimento_dias") else None,
                stock_entry=True, warehouse_id=stock_activity.warehouse_id,
            )
        created(f"{what}: {len(lines)} linhas, entrada em stock")

    # ------------------------------------------------------------------------------- hotel (with its module only)
    hotel = data.get("hotel")
    if hotel:
        if "Hotel" not in granted:
            skipped("Hotel: o módulo Hotel ainda não está ativo - corra de novo depois de o ativar")
        else:
            hotel_activity = await activity(hotel.get("atividade") or "Hotel", "Hotel")
            types = {t.name: t for t in (await db.execute(
                select(ResourceTypeCatalog).where(ResourceTypeCatalog.company_id == cid))).scalars().all()}
            rooms = {(r.resource_type_id, r.name) for r in (await db.execute(
                select(Resource).where(Resource.company_id == cid))).scalars().all()}
            for item in hotel.get("tipos_quarto", []):
                name = item["nome"]
                resource_type = types.get(name)
                if resource_type is None:
                    if not dry_run:
                        resource_type = await create_resource_type(
                            db, cid, name, requires_service=True, default_start_time=_time(item.get("entrada"), "entrada"),
                            default_end_time=_time(item.get("saida"), "saida"))
                        types[name] = resource_type
                    created(f"Tipo de quarto {name}")
                else:
                    existed(f"Tipo de quarto {name}")
                # the type's rates: the night (no duration) and the timed ones (1 hora, 2 horas, day use)
                for rate in ([item["diaria"]] if item.get("diaria") else []) + item.get("tarifas", []):
                    await service(rate, resource_type)
                for room in item.get("quartos", []):
                    key = (resource_type.id if resource_type else None, room["nome"])
                    if key in rooms:
                        existed(f"Quarto {room['nome']} ({name})")
                        continue
                    if not dry_run:
                        await create_resource(db, cid, hotel_activity.id, resource_type.id, room["nome"],
                                              capacity=room.get("capacidade"))
                        rooms.add(key)
                    created(f"Quarto {room['nome']} ({name})")
            for item in hotel.get("servicos", []):
                await service(item)

    return report


async def main() -> None:
    from app.core.database import AsyncSessionLocal, engine
    engine.echo = False  # DEBUG prints every SQL query: the report alone is what the person reads
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        say("Uso: python -m app.tools.catalogo_inicial <NIF> <ficheiro.json> [--verificar]")
        sys.exit(1)
    nif, path = args[0], Path(args[1])
    dry_run = "--verificar" in sys.argv
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        say(f"ERRO: o ficheiro {path} não existe")
        sys.exit(1)
    except json.JSONDecodeError as e:
        say(f"ERRO: o ficheiro não é um JSON válido (linha {e.lineno}): {e.msg}")
        sys.exit(1)
    async with AsyncSessionLocal() as db:
        try:
            report = await load(db, nif, data, dry_run=dry_run)
        except Exception as e:  # CatalogError, or a service's own refusal (a plan limit...): its message, no trace
            say(f"ERRO: {e}")
            sys.exit(1)
    say("VERIFICAÇÃO - nada foi alterado" if dry_run else "Catálogo carregado")
    say(f"\n{'A criar' if dry_run else 'Criado'} ({len(report['criados'])}):")
    for line in report["criados"]:
        say(f"  + {line}")
    if report["existentes"]:
        say(f"\nJá existia, deixado como está ({len(report['existentes'])}):")
        for line in report["existentes"]:
            say(f"  = {line}")
    for line in report["ignorados"]:
        say(f"\n  ! {line}")


if __name__ == "__main__":
    asyncio.run(main())
