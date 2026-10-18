"""
Service layer for the dynamic permission system (Permission + RolePermission).

Rules:
- PERMISSION_CATALOG is the single source of truth for which permissions
  exist and which roles get them BY DEFAULT (reproducing the old hardcoded
  require_role(...) tuples, so migrating a route changes nothing at first).
- GESTOR is the company's owner role: always allowed, never stored in
  role_permissions, and its column is locked in the admin matrix (a GESTOR
  can never lock themselves out; there is no company-level rescue account).
- Defaults are distributed ONCE per (company, permission) - tracked in
  CompanyPermissionSeed - so a grant removed in the matrix survives restarts,
  while a permission added to the catalog later is distributed once to all
  companies at the next boot.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import CORE, capability_of_permission
from app.core.config import get_settings

from app.models.company_permission_seed import CompanyPermissionSeed
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.models.user import UserRole

ALWAYS_ALLOWED_ROLE = "GESTOR"
EDITABLE_ROLES = ("CAIXA", "ATENDENTE", "COZINHA", "ARMAZENISTA", "CONTABILISTA")

# (code, label, category, default_roles) - GESTOR is implicit, never listed.
PERMISSION_CATALOG: list[tuple[str, str, str, list[str]]] = [
    ("consumption_reasons:view", "Ver motivos de consumo interno", "Consumo Interno", ["ARMAZENISTA"]),
    ("consumption_reasons:manage", "Criar/editar motivos de consumo interno", "Consumo Interno", []),
    ("internal_consumption:view", "Ver histórico de consumo interno", "Consumo Interno", ["ARMAZENISTA"]),
    ("internal_consumption:record", "Registar consumo interno", "Consumo Interno", ["ARMAZENISTA"]),
    ("stock:view", "Ver níveis, movimentos e resumo de stock", "Stock", ["ARMAZENISTA"]),
    ("stock:receive", "Registar receção de stock", "Stock", ["ARMAZENISTA"]),
    ("stock:transfer", "Transferir stock entre armazens", "Stock", ["ARMAZENISTA"]),
    ("stock:loss", "Registar perdas de stock", "Stock", ["ARMAZENISTA"]),
    ("stock:adjust", "Ajustar stock (inventário)", "Stock", []),
    ("stock:locations", "Gerir localizações dos armazéns e arrumar os produtos", "Stock", ["ARMAZENISTA"]),
    ("warehouses:view", "Ver armazens", "Armazens", ["ARMAZENISTA"]),
    ("warehouses:create", "Criar armazens", "Armazens", ["ARMAZENISTA"]),
    ("warehouses:manage", "Editar, ativar e desativar armazens", "Armazens", []),
    ("production:view", "Ver estimativa e histórico de produção", "Produção", ["ARMAZENISTA"]),
    ("production:produce", "Registar produção", "Produção", ["ARMAZENISTA"]),
    ("movements:view", "Ver documentos de movimento de stock", "Movimentos de Stock", ["CAIXA"]),
    ("suppliers:view", "Ver fornecedores", "Fornecedores", ["ARMAZENISTA", "CONTABILISTA"]),
    ("suppliers:manage", "Criar e editar fornecedores", "Fornecedores", []),
    ("purchases:view", "Ver as faturas de compra", "Fornecedores", ["CONTABILISTA"]),
    ("purchases:manage", "Registar e anular faturas de compra", "Fornecedores", []),
    ("purchases:pay", "Pagar fornecedores e anular pagamentos", "Fornecedores", []),
    ("guias:view", "Ver as guias de remessa, transporte e devolução", "Guias", ["ARMAZENISTA", "CONTABILISTA"]),
    ("guias:manage", "Emitir e anular guias de remessa, transporte e devolução", "Guias", ["ARMAZENISTA"]),
    ("guias:invoice", "Faturar guias de remessa (uma fatura para as guias de um cliente)", "Guias", []),
    ("products:view", "Ver produtos", "Produtos", ["CAIXA", "ARMAZENISTA", "ATENDENTE"]),
    ("products:manage", "Criar e editar produtos e imagens", "Produtos", []),
    ("recipes:list", "Ver produtos com receita (produção)", "Produtos", ["ARMAZENISTA"]),
    ("recipes:view", "Ver a receita de um produto", "Produtos", []),
    ("recipes:manage", "Editar receitas", "Produtos", []),
    ("pos:view", "Ver caixa: sessões, saldos e stock disponível", "Caixa (POS)", ["CAIXA"]),
    ("pos:open_session", "Abrir sessão de caixa", "Caixa (POS)", ["CAIXA"]),
    ("pos:close_session", "Fechar sessão de caixa", "Caixa (POS)", ["CAIXA"]),
    ("pos:checkout", "Registar venda (checkout)", "Caixa (POS)", ["CAIXA"]),
    ("pos:checkout_ft", "Faturar (FT) na caixa - documento a pagar mais tarde", "Caixa (POS)", ["CAIXA"]),
    ("pos:proforma", "Emitir fatura pro-forma na caixa", "Caixa (POS)", ["CAIXA"]),
    ("pos:liquidate", "Liquidar (regularizar) na caixa", "Caixa (POS)", ["CAIXA"]),
    ("invoices:view", "Ver faturas, PDF e períodos disponíveis", "Faturação", ["CAIXA"]),
    ("invoices:issue", "Emitir faturas", "Faturação", ["CAIXA"]),
    ("invoices:credit_note", "Emitir notas de crédito", "Faturação", []),
    ("invoices:debit_note", "Emitir notas de débito", "Faturação", []),
    ("invoices:receipt", "Emitir recibos", "Faturação", ["CAIXA"]),
    ("invoices:proforma", "Emitir faturas pro-forma", "Faturação", ["CAIXA"]),
    ("invoices:proforma_convert", "Converter pro-forma ou orçamento em fatura", "Faturação", ["CAIXA"]),
    ("invoices:quote", "Emitir orçamentos", "Faturação", []),
    ("invoices:resubmit", "Reenviar fatura (submissão AGT)", "Faturação", ["CAIXA"]),
    ("open_accounts:view", "Ver contas abertas e respetivas linhas", "Contas Abertas", ["CAIXA", "ATENDENTE"]),
    ("open_accounts:open", "Abrir contas", "Contas Abertas", ["CAIXA", "ATENDENTE"]),
    ("open_accounts:edit_lines", "Adicionar, alterar e remover linhas de conta", "Contas Abertas", ["CAIXA", "ATENDENTE"]),
    ("open_accounts:close", "Fechar contas", "Contas Abertas", ["CAIXA"]),
    ("moedeiro:view", "Ver denominações e última contagem do moedeiro", "Moedeiro", ["CAIXA"]),
    ("moedeiro:record", "Registar contagem do moedeiro", "Moedeiro", ["CAIXA"]),
    ("customers:view", "Ver clientes", "Clientes", ["CAIXA"]),
    ("customers:create", "Criar clientes", "Clientes", ["CAIXA"]),
    ("customers:manage", "Editar clientes, sugerir código, ativar/desativar e ligações bancárias", "Clientes", []),
    ("resource_types:view", "Ver tipos de recurso", "Recursos e Reservas", ["CAIXA", "ATENDENTE"]),
    ("resource_types:manage", "Criar, editar e ativar/desativar tipos de recurso", "Recursos e Reservas", []),
    ("resources:view", "Ver recursos (quartos, mesas, ...)", "Recursos e Reservas", ["CAIXA", "ARMAZENISTA", "ATENDENTE"]),
    ("resources:manage", "Criar, editar e ativar/desativar recursos", "Recursos e Reservas", []),
    ("resources:history", "Ver o histórico dos recursos (utilizações, receita, ausências)", "Recursos e Reservas", []),
    ("bookings:view", "Ver reservas", "Recursos e Reservas", ["CAIXA"]),
    ("bookings:create", "Criar reservas", "Recursos e Reservas", ["CAIXA"]),
    ("bookings:update", "Alterar estado e reagendar reservas", "Recursos e Reservas", ["CAIXA"]),
    ("bookings:charge", "Cobrar marcações na caixa", "Recursos e Reservas", ["CAIXA"]),
    ("hotel:checkin", "Fazer check-in", "Hotel", ["CAIXA"]),
    ("hotel:checkout", "Fazer check-out", "Hotel", ["CAIXA"]),
    ("activities:view", "Ver atividades", "Atividades", ["CAIXA", "ARMAZENISTA", "ATENDENTE", "COZINHA"]),
    ("activities:manage", "Criar, editar e ativar/desativar atividades", "Atividades", []),
    ("pos_terminals:view", "Ver pontos de venda de uma atividade", "Atividades", ["CAIXA", "ATENDENTE"]),
    ("pos_terminals:manage", "Criar, editar e ativar/desativar pontos de venda", "Atividades", []),
    ("product_categories:view", "Ver categorias de produtos", "Catálogos da Empresa", ["CAIXA"]),
    ("product_categories:manage", "Criar, editar e ativar/desativar categorias de produtos", "Catálogos da Empresa", []),
    ("service_types:view", "Ver tipos de serviço", "Catálogos da Empresa", ["CAIXA"]),
    ("service_types:manage", "Criar, editar e ativar/desativar tipos de serviço", "Catálogos da Empresa", []),
    ("services:view", "Ver serviços", "Catálogos da Empresa", ["CAIXA", "ATENDENTE"]),
    ("services:manage", "Criar, editar e ativar/desativar serviços", "Catálogos da Empresa", []),
    ("tesouraria:reasons_view", "Ver motivos de movimento de caixa", "Tesouraria", ["CAIXA"]),
    ("tesouraria:reasons_manage", "Criar, editar e ativar/desativar motivos de movimento de caixa", "Tesouraria", []),
    ("tesouraria:view", "Ver movimentos de tesouraria e pendentes", "Tesouraria", ["CAIXA"]),
    ("tesouraria:overview", "Ver a vista da tesouraria (posição, movimentos e fechos de todas as caixas)", "Tesouraria", []),
    ("tesouraria:record", "Registar movimentos de tesouraria", "Tesouraria", ["CAIXA"]),
    ("tesouraria:receive", "Receber movimentos de tesouraria pendentes", "Tesouraria", ["CAIXA"]),
    ("tesouraria:cancel_movement", "Cancelar movimentos de tesouraria", "Tesouraria", ["CAIXA"]),
    ("tesouraria:daily_report", "Ver relatório diário de tesouraria", "Tesouraria", ["CAIXA"]),
    ("tesouraria:my_association", "Ver a minha associação a caixa", "Tesouraria", ["CAIXA", "ARMAZENISTA", "CONTABILISTA", "ATENDENTE", "COZINHA"]),
    ("tesouraria:associations_manage", "Associar utilizadores as caixas (pontos de venda)", "Atividades", []),
    ("tesouraria:payment_prefs_view", "Ver métodos de pagamento da empresa", "Tesouraria", ["CAIXA"]),
    ("tesouraria:payment_prefs_manage", "Configurar métodos de pagamento da empresa", "Tesouraria", []),
    ("documents:payment_term_prefs_view", "Ver exceções de condição de pagamento obrigatória da empresa", "Documentos", ["CAIXA"]),
    ("documents:payment_term_prefs_manage", "Configurar exceções de condição de pagamento obrigatória da empresa", "Documentos", []),
    ("fiscal_periods:view", "Ver exercicios e períodos fiscais", "Contabilidade", []),
    ("fiscal_periods:manage", "Abrir exercicios e períodos fiscais", "Contabilidade", []),
    ("fiscal_periods:close", "Fechar exercicios e períodos fiscais", "Contabilidade", []),
    ("fiscal_periods:current", "Ver o período fiscal corrente", "Contabilidade", ["CAIXA", "ARMAZENISTA", "CONTABILISTA", "ATENDENTE", "COZINHA"]),
    ("saf_t:export", "Exportar SAF-T", "Contabilidade", []),
    ("company:view", "Ver dados da empresa", "Empresa", []),
    ("company:manage", "Editar dados e logotipo da empresa", "Empresa", []),
    ("company_bank_accounts:view", "Ver contas bancárias da empresa", "Empresa", ["CAIXA"]),
    ("company_bank_accounts:manage", "Criar, editar e ativar/desativar contas bancárias da empresa", "Empresa", []),
    ("dashboard:view", "Ver painel de resumo", "Painel", ["ARMAZENISTA", "CONTABILISTA"]),
    ("vat:view", "Ver taxas de IVA da empresa", "IVA", ["CAIXA"]),
    ("vat:return", "Ver o apuramento do IVA (liquidado, dedutível, a pagar)", "IVA", ["CONTABILISTA"]),
    ("document_series:view", "Ver series de documentos", "Faturação", []),
    ("document_series:manage", "Criar, editar e ativar/desativar series de documentos", "Faturação", []),
    ("establishments:view", "Ver estabelecimentos", "Empresa", []),
    ("establishments:manage", "Criar, editar e ativar/desativar estabelecimentos", "Empresa", []),
    ("catalogs:view_reference", "Ver catálogos de referência (paises, moedas, bancos, IVA, unidades, tipos de documento...)", "Catálogos de Referência", []),
    ("catalogs:view_billing", "Ver métodos e condições de pagamento, retenções e denominações", "Catálogos de Referência", ["CAIXA"]),
    ("open_accounts:transfer", "Transferir e dividir linhas entre contas", "Contas Abertas", ["CAIXA", "ATENDENTE"]),
    ("kitchen:view", "Ver os pedidos da cozinha", "Cozinha", ["COZINHA"]),
    ("kitchen:update", "Fazer avancar ou recusar pratos na cozinha", "Cozinha", ["COZINHA"]),
    ("kitchen:history", "Ver o histórico da cozinha", "Cozinha", []),
]


class ProtectedRoleError(Exception):
    """Raised when someone tries to edit the grants of a role that is not editable."""


async def _ensure_catalog(db: AsyncSession) -> dict[str, Permission]:
    """Inserts (flush only, no commit) any catalog entry missing from the
    platform-wide Permission table, aligns the label and category of the existing ones with the catalog,
    and returns every permission by code."""
    result = await db.execute(select(Permission))
    by_code = {p.code: p for p in result.scalars().all()}
    for code, label, category, _ in PERMISSION_CATALOG:
        if code not in by_code:
            permission = Permission(code=code, label=label, category=category)
            db.add(permission)
            by_code[code] = permission
        else:
            # a permission can be renamed or moved: keep the label and the category in line with the catalog
            existing = by_code[code]
            if existing.label != label or existing.category != category:
                existing.label = label
                existing.category = category
    await db.flush()
    return by_code


async def grant_default_role_permissions(db: AsyncSession, company_id: uuid.UUID) -> None:
    """Flush-only variant (no commit) - lets create_company keep its single
    transaction. Grants each catalog permission's default roles to the company
    ONLY for permissions never seeded for it before."""
    by_code = await _ensure_catalog(db)

    seeded_result = await db.execute(
        select(CompanyPermissionSeed.permission_id).where(CompanyPermissionSeed.company_id == company_id)
    )
    seeded_ids = {row[0] for row in seeded_result.all()}

    grants_result = await db.execute(
        select(RolePermission.role, RolePermission.permission_id).where(RolePermission.company_id == company_id)
    )
    existing_grants = {(row[0].value, row[1]) for row in grants_result.all()}

    for code, _, _, default_roles in PERMISSION_CATALOG:
        permission = by_code[code]
        if permission.id in seeded_ids:
            continue
        for role in default_roles:
            if (role, permission.id) not in existing_grants:
                db.add(RolePermission(company_id=company_id, role=UserRole(role), permission_id=permission.id))
        db.add(CompanyPermissionSeed(company_id=company_id, permission_id=permission.id))
    await db.flush()


async def seed_permission_catalog(db: AsyncSession) -> None:
    """Idempotent - makes the platform-wide catalog match PERMISSION_CATALOG."""
    await _ensure_catalog(db)
    await db.commit()


async def seed_default_role_permissions(db: AsyncSession, company_id: uuid.UUID) -> None:
    """Idempotent, safe on every boot: distributes defaults only for
    permissions this company never received (see grant_default_role_permissions)."""
    await grant_default_role_permissions(db, company_id)
    await db.commit()


async def has_permission(db: AsyncSession, company_id: uuid.UUID, role: str, code: str) -> bool:
    # The sector separation comes first and applies to every role, GESTOR included: a permission
    # whose capability the company does not have is refused (no-op while ENFORCE_CAPABILITIES is off).
    if not await capability_allows(db, company_id, code):
        return False
    if role == ALWAYS_ALLOWED_ROLE:
        return True
    result = await db.execute(
        select(RolePermission)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(RolePermission.company_id == company_id, RolePermission.role == UserRole(role), Permission.code == code)
    )
    return result.scalar_one_or_none() is not None


async def get_permission_matrix(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """Every catalog permission with the roles currently granted for this
    company - what the admin screen renders as a checkbox matrix. GESTOR is
    always listed as granted (locked column)."""
    permissions_result = await db.execute(select(Permission).order_by(Permission.category, Permission.label))
    permissions = list(permissions_result.scalars().all())
    active_capabilities = await _active_capabilities_or_none(db, company_id)
    permissions = [p for p in permissions if _is_allowed(active_capabilities, p.code)]

    grants_result = await db.execute(select(RolePermission).where(RolePermission.company_id == company_id))
    granted_roles_by_permission: dict[uuid.UUID, set[str]] = {}
    for grant in grants_result.scalars().all():
        granted_roles_by_permission.setdefault(grant.permission_id, set()).add(grant.role.value)

    return [
        {
            "id": p.id,
            "code": p.code,
            "label": p.label,
            "category": p.category,
            "granted_roles": sorted(granted_roles_by_permission.get(p.id, set()) | {ALWAYS_ALLOWED_ROLE}),
        }
        for p in permissions
    ]


async def set_role_permission(db: AsyncSession, company_id: uuid.UUID, role: str, permission_id: uuid.UUID, granted: bool) -> None:
    if role == ALWAYS_ALLOWED_ROLE:
        raise ProtectedRoleError("O perfil Gestor tem sempre todas as permissões e não pode ser alterado")
    if role not in EDITABLE_ROLES:
        raise ProtectedRoleError("Perfil inválido para configuração de permissões")

    existing_result = await db.execute(
        select(RolePermission).where(RolePermission.company_id == company_id, RolePermission.role == UserRole(role), RolePermission.permission_id == permission_id)
    )
    existing = existing_result.scalar_one_or_none()

    if granted and existing is None:
        db.add(RolePermission(company_id=company_id, role=UserRole(role), permission_id=permission_id))
    elif not granted and existing is not None:
        await db.delete(existing)
    await db.commit()


async def _list_my_permissions_unfiltered(db: AsyncSession, company_id: uuid.UUID, role: str) -> list[str]:
    """Permission codes granted to this role in this company - what a logged-in
    user calls to show/hide buttons and menu items. GESTOR gets every code."""
    if role == ALWAYS_ALLOWED_ROLE:
        result = await db.execute(select(Permission.code).order_by(Permission.code))
        return [row[0] for row in result.all()]

    result = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.company_id == company_id, RolePermission.role == UserRole(role))
    )
    return [row[0] for row in result.all()]


# ---------- Sector separation (see app.core.capabilities) ----------

def _capability_of(code: str) -> str:
    """CORE or the capability that owns this permission. A prefix nobody classified is treated
    as core rather than raising: tests/test_sectors.py guarantees every catalog permission is
    classified, so this only protects a request from a 500."""
    try:
        return capability_of_permission(code)
    except KeyError:
        return CORE


async def _active_capabilities_or_none(db: AsyncSession, company_id: uuid.UUID):
    """None while ENFORCE_CAPABILITIES is off (everything is allowed), otherwise the set of
    capability codes the company's granted, enabled, active modules give."""
    if not get_settings().ENFORCE_CAPABILITIES:
        return None
    from app.services.sector_service import get_company_capabilities  # lazy: sector_service imports this module
    return await get_company_capabilities(db, company_id)


def _is_allowed(active, code: str) -> bool:
    if active is None:
        return True
    capability = _capability_of(code)
    return capability == CORE or capability in active


async def capability_allows(db: AsyncSession, company_id: uuid.UUID, code: str) -> bool:
    """False when the permission belongs to a capability the company does not have. Core
    permissions never cost a query."""
    if not get_settings().ENFORCE_CAPABILITIES:
        return True
    if _capability_of(code) == CORE:
        return True
    return _is_allowed(await _active_capabilities_or_none(db, company_id), code)


async def list_my_permissions(db: AsyncSession, company_id: uuid.UUID, role: str) -> list[str]:
    """Permission codes the role holds in this company AND that the company can use: the role's
    grants (GESTOR: every code) minus what the company's sectors do not give. This is the list
    the frontend builds the menu, the route guards and the buttons from."""
    codes = await _list_my_permissions_unfiltered(db, company_id, role)
    active = await _active_capabilities_or_none(db, company_id)
    return [c for c in codes if _is_allowed(active, c)]
