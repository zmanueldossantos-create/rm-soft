"""
Plans catalog - what a plan can limit and what it can switch on. The PLANS themselves (names, prices, the numbers, the
options ticked) live in the database and are edited by the SUPER_ADMIN (plan_service); only the list of what CAN be
limited or switched lives here, in code, because each entry is enforced somewhere in the code.

Two axes, kept apart on purpose:
  the sector modules (app.core.capabilities) say WHAT business the company runs (Bar, Padaria, Farmácia...);
  the plan says HOW FAR it goes (how many users, modules, shops, tills, warehouses; the options below).

What the law requires is never an option: invoicing, SAF-T, the AGT submission, VAT, periods, the Caixa - every plan
has them, the trial included.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Limit:
    code: str
    label: str      # PT, shown in the plan editor and in the refusals
    noun_one: str   # "1 utilizador"
    noun_many: str  # "3 utilizadores"


@dataclass(frozen=True)
class Option:
    code: str
    label: str
    description: str
    # the permissions this option owns (exact codes, or "prefix:*"): refused, and hidden from the menus, without it
    permissions: tuple[str, ...] = ()


LIMITS: dict[str, Limit] = {
    lim.code: lim
    for lim in (
        Limit("max_users", "Utilizadores", "utilizador ativo", "utilizadores ativos"),
        Limit("max_modules", "Módulos (setores)", "módulo", "módulos"),
        Limit("max_establishments", "Lojas / estabelecimentos", "estabelecimento ativo", "estabelecimentos ativos"),
        Limit("max_pos", "Caixas (pontos de venda)", "caixa ativa", "caixas ativas"),
        Limit("max_warehouses", "Armazéns", "armazém ativo", "armazéns ativos"),
    )
}

OPTIONS: dict[str, Option] = {
    opt.code: opt
    for opt in (
        Option("FORNECEDORES_COMPRAS", "Fornecedores, compras e pagamentos",
               "Fichas de fornecedores, faturas de compra e pagamentos a fornecedores",
               ("suppliers:*", "purchases:*")),
        Option("GUIAS", "Guias de remessa e de transporte", "Emissão de guias e a sua faturação", ("guias:*",)),
        Option("APURAMENTO_IVA", "Apuramento e mapa de IVA", "O apuramento do IVA do período", ("vat:return",)),
        Option("COPIAS_AUTOMATICAS", "Cópias de segurança automáticas", "Até 3 cópias por dia, às horas escolhidas"),
        Option("PERMISSOES_PERSONALIZADAS", "Permissões personalizadas por perfil",
               "O gestor muda o que cada perfil pode fazer"),
        Option("ASSISTENTE_IA", "Assistente IA", "O assistente no sistema", ("assistant:use",)),
        Option("IA_CANAIS", "IA por WhatsApp e Telegram", "O assistente nas conversas do WhatsApp e do Telegram"),
    )
}

# How a contract is paid, and how long one period lasts (months; None: no end - the lifetime licence)
BILLING_TYPES: dict[str, tuple[str, int | None]] = {
    "TESTE": ("Teste gratuito", 0),  # 15 days, see TRIAL_DAYS
    "MENSAL": ("Mensal", 1),
    "TRIMESTRAL": ("Trimestral", 3),
    "SEMESTRAL": ("Semestral", 6),
    "ANUAL": ("Anual", 12),
    "VITALICIA": ("Vitalícia", None),
}
TRIAL_DAYS = 15
WARN_DAYS = 15   # the gestor is told this many days before the end
GRACE_DAYS = 7   # after the end, everything still works this many days; then read only
DEPLOYMENT_MODES = {"SAAS": "SaaS (servidor RM SOFT)", "LOCAL": "Local (servidor do cliente)"}


def option_of_permission(code: str) -> str | None:
    """The option that owns this permission, None when no plan option is involved (most permissions)."""
    prefix = code.split(":", 1)[0] + ":*"
    for option in OPTIONS.values():
        if code in option.permissions or prefix in option.permissions:
            return option.code
    return None
