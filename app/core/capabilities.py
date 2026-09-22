"""
Sector / capability catalog - the single source of truth for what a "module" unlocks.

Three layers, by design:
  CORE        - what every company always has (invoicing, cash desk, customers, catalogs...).
  CAPABILITY  - an optional block of features (stock, production, resources, bookings, open
                accounts, hotel stay). Defined here, in code, with its dependencies, the
                permission prefixes it owns and the screens it opens.
  SECTOR      - a named set of capabilities sold to a company (Hotel, Bar, Padaria...). The
                SUPER_ADMIN ticks which capabilities each module gives; the defaults below
                are only the starting point (see sector_service.seed_sector_catalog).

Every permission belongs to CORE or to exactly one capability (capability_of_permission and
tests/test_sectors.py): a new permission whose prefix is not classified here fails the tests,
so the separation cannot silently rot.
"""
from dataclasses import dataclass

CORE = "CORE"


@dataclass(frozen=True)
class Capability:
    code: str
    label: str
    description: str
    requires: tuple[str, ...]
    prefixes: tuple[str, ...]
    screens: tuple[str, ...]


CAPABILITIES: dict[str, Capability] = {
    c.code: c
    for c in (
        Capability(
            "STOCK", "Stock", "Armazens, movimentos de stock, fornecedores e consumo interno", (),
            ("stock", "warehouses", "movements", "suppliers", "consumption_reasons", "internal_consumption"),
            ("/stock", "/stock/dashboard", "/stock-movements", "/fornecedores", "/consumo-interno"),
        ),
        Capability(
            "PRODUCTION", "Producao", "Receitas e producao (a partir do stock)", ("STOCK",),
            ("production", "recipes"), ("/producao", "/producao/historico"),
        ),
        Capability(
            "RESOURCES", "Recursos", "Quartos, mesas, praticantes e outros recursos reservaveis", (),
            ("resource_types", "resources"), ("/recursos",),
        ),
        Capability(
            "BOOKINGS", "Reservas", "Reservas e agenda dos recursos", ("RESOURCES",),
            ("bookings",), ("/reservas",),
        ),
        Capability(
            "OPEN_ACCOUNTS", "Contas abertas", "Contas em curso, transferencia e divisao, plano de mesas", (),
            ("open_accounts",), ("/contas-abertas",),
        ),
        Capability(
            "HOTEL_STAY", "Estadia de hotel", "Check-in, check-out e ocupacao", ("BOOKINGS", "OPEN_ACCOUNTS"),
            ("hotel",), ("/ocupacao",),
        ),
    )
}

# Permission prefixes that belong to the core (always available to every company).
CORE_PREFIXES: frozenset[str] = frozenset({
    "pos", "moedeiro", "tesouraria", "invoices", "documents", "document_series", "customers", "products", "services",
    "service_types", "product_categories", "catalogs", "fiscal_periods", "saf_t", "company",
    "company_bank_accounts", "establishments", "dashboard", "vat", "activities", "pos_terminals",
})


def capability_of_permission(code: str) -> str:
    """CORE or the capability code that owns this permission. Raises KeyError for an
    unclassified prefix - classify it here (that is the point)."""
    prefix = code.split(":", 1)[0]
    for capability in CAPABILITIES.values():
        if prefix in capability.prefixes:
            return capability.code
    if prefix in CORE_PREFIXES:
        return CORE
    raise KeyError("Permission prefix not classified in app.core.capabilities: " + prefix)


def expand_dependencies(codes) -> set[str]:
    """The given capability codes plus everything they require, transitively."""
    result: set[str] = set()
    pending = list(codes)
    while pending:
        code = pending.pop()
        if code in result:
            continue
        result.add(code)
        pending.extend(CAPABILITIES[code].requires)
    return result


@dataclass(frozen=True)
class Sector:
    code: str
    name: str
    description: str
    capabilities: tuple[str, ...]
    ready: bool = True
    ready_note: str = ""


SECTORS: tuple[Sector, ...] = (
    Sector("HOTEL", "Hotel", "Alojamento: quartos, reservas, estadias e extras", ("STOCK", "RESOURCES", "BOOKINGS", "OPEN_ACCOUNTS", "HOTEL_STAY")),
    Sector("RESTAURANTE", "Restaurante", "Mesas, contas abertas, divisao e transferencia", ("STOCK", "RESOURCES", "BOOKINGS", "OPEN_ACCOUNTS")),
    Sector("BAR", "Bar", "Venda ao balcao e contas abertas", ("STOCK", "OPEN_ACCOUNTS")),
    Sector("PADARIA", "Padaria", "Venda ao balcao, stock e producao", ("STOCK", "PRODUCTION")),
    Sector("SPA_SALAO", "Spa / Salao / Consultorio", "Marcacoes por praticante, duracao dos servicos e agenda", ("RESOURCES", "BOOKINGS")),
    Sector("COMERCIO", "Comercio geral", "Venda ao balcao e stock", ("STOCK",)),
    Sector("SERVICOS", "Prestacao de servicos", "Faturacao de servicos", ()),
    Sector("FARMACIA", "Farmacia", "Venda e stock de medicamentos", ("STOCK",), False, "Em desenvolvimento: falta o controlo de lotes e validades"),
    Sector("RH", "Recursos Humanos", "Gestao de colaboradores e salarios", (), False, "Em desenvolvimento"),
    Sector("HOSPITAL", "Hospital", "Pacientes, consultas e faturacao", (), False, "Em desenvolvimento"),
    Sector("ESCOLA", "Escola", "Alunos, matriculas e propinas", (), False, "Em desenvolvimento"),
)

SECTORS_BY_CODE: dict[str, Sector] = {s.code: s for s in SECTORS}