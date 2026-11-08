"""
Contabilidade - «Contas por operação»: which account of the company's chart each kind of operation goes to. The company
(or its accountant) sets each one; the suggestion below is the PGC account, filled in by itself when the chart has it
(app.services.account_mapping_service.apply_suggestions). An empty suggestion: the accountant decides.

kind «parent»: the account under which the system creates one sub-account per bank account, till, customer or
supplier (app.services.account_mapping_service.sync_subaccounts); kind «account»: the account itself.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Operation:
    key: str
    group: str
    label: str
    suggestion: str  # the PGC code, "" when the accountant decides
    kind: str = "account"  # "account" or "parent"


OPERATIONS: tuple[Operation, ...] = (
    # sub-accounts made by the system, one per entity
    Operation("PARENT_BANKS_NATIONAL", "Subcontas criadas pelo sistema", "Bancos - contas em moeda nacional", "43.1", "parent"),
    Operation("PARENT_BANKS_FOREIGN", "Subcontas criadas pelo sistema", "Bancos - contas em moeda estrangeira", "43.2", "parent"),
    Operation("PARENT_TILLS", "Subcontas criadas pelo sistema", "Caixas e cofre", "45.1", "parent"),
    Operation("PARENT_CUSTOMERS_NATIONAL", "Subcontas criadas pelo sistema", "Clientes nacionais", "31.1.2.1", "parent"),
    Operation("PARENT_CUSTOMERS_FOREIGN", "Subcontas criadas pelo sistema", "Clientes estrangeiros", "31.1.2.2", "parent"),
    Operation("PARENT_SUPPLIERS", "Subcontas criadas pelo sistema", "Fornecedores", "32.1.2", "parent"),
    # sales
    Operation("CUSTOMERS_GENERIC", "Vendas", "Consumidor final e vendas sem cliente (subconta criada pelo sistema)", ""),
    Operation("SALES_GOODS", "Vendas", "Vendas de mercadorias", "61.3.1"),
    Operation("SALES_PRODUCTS", "Vendas", "Vendas de produtos fabricados (produção própria)", "61.1.1"),
    Operation("SALES_SERVICES", "Vendas", "Prestações de serviços", "62.1.1"),
    Operation("SALES_RETURNS", "Vendas", "Devoluções (notas de crédito)", "61.7.1"),
    Operation("SALES_DISCOUNTS", "Vendas", "Descontos e abatimentos concedidos", "61.8.1"),
    # VAT
    Operation("VAT_OUTPUT", "IVA", "IVA liquidado (vendas)", "34.5.3"),
    Operation("VAT_DEDUCTIBLE", "IVA", "IVA dedutível (compras)", "34.5.2"),
    Operation("VAT_SUPPORTED", "IVA", "IVA suportado", "34.5.1"),
    # purchases and stock
    Operation("PURCHASES_GOODS", "Compras e existências", "Compras de mercadorias", "21.2"),
    Operation("PURCHASES_MATERIALS", "Compras e existências", "Compras de matérias-primas e de consumo", "21.1"),
    Operation("PURCHASES_SERVICES", "Compras e existências", "Fornecimentos e serviços de terceiros (serviços, consumíveis)", "75.2"),
    Operation("PURCHASES_FIXED_ASSETS", "Compras e existências", "Compras de imobilizado (meios fixos)", ""),
    Operation("STOCK_GOODS", "Compras e existências", "Existências - mercadorias", "26"),
    Operation("STOCK_MATERIALS", "Compras e existências", "Existências - matérias-primas", "22.1"),
    Operation("STOCK_PRODUCTS", "Compras e existências", "Existências - produtos acabados", "24.1"),
    Operation("COST_OF_SALES", "Compras e existências", "Custo das existências vendidas", "71"),
    Operation("STOCK_INTERNAL_USE", "Compras e existências", "Consumo interno de existências", ""),
    Operation("STOCK_LOSSES", "Compras e existências", "Quebras de existências", "78.4.1"),
    Operation("STOCK_GAINS", "Compras e existências", "Sobras de existências", "68.4.1"),
    # treasury
    Operation("BANK_TRANSIT", "Tesouraria", "Transferências bancárias em trânsito", "48"),
    Operation("BANK_FEES", "Tesouraria", "Comissões e serviços bancários", "76.7"),
    Operation("OTHER_MEANS", "Tesouraria", "Outros meios de pagamento (nem numerário nem banco: vales, cheques por depositar...)", ""),
    Operation("CASH_SHORTAGE", "Tesouraria", "Falta de caixa (diferença no fecho)", ""),
    Operation("CASH_SURPLUS", "Tesouraria", "Sobra de caixa (diferença no fecho)", ""),
    Operation("CUSTOMER_ADVANCES", "Tesouraria", "Adiantamentos de clientes", "31.9.1"),
    Operation("SUPPLIER_ADVANCES", "Tesouraria", "Adiantamentos a fornecedores", "32.9.1"),
    # taxes
    Operation("WITHHOLDING_SUFFERED", "Impostos", "Retenção na fonte sofrida (clientes)", ""),
)

OPERATIONS_BY_KEY: dict[str, Operation] = {o.key: o for o in OPERATIONS}
