"""
The PGC - Plano Geral de Contabilidade de Angola (Decreto n.º 82/01) - as the system loads it when a company chooses
«PGC» for its chart of accounts (app.services.chart_of_accounts_service.start_chart).

TO COMPLETE: only the classes are here for now (confirmed by the decree). When the official list of accounts is
available, add its accounts below, in the same form - (code, name), codes with points under the 2-digit accounts
(«45», «45.1», «45.1.1») - and every company that chooses the PGC from then on gets them; a company that already
loaded it gets the new ones by loading it again (the existing accounts are kept, never renamed).
"""

PGC_ACCOUNTS: tuple[tuple[str, str], ...] = (
    ("1", "Meios fixos e investimentos"),
    ("2", "Existências"),
    ("3", "Terceiros"),
    ("4", "Meios monetários"),
    ("5", "Capital e reservas"),
    ("6", "Proveitos e ganhos por natureza"),
    ("7", "Custos e perdas por natureza"),
    ("8", "Resultados"),
)
