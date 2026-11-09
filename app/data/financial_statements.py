"""
Contabilidade - the lines of the financial statements of the PGC de Angola (Decreto n.º 82/01): the Balanço and the
Demonstração de resultados por natureza, each line with the accounts it adds up. One place to adjust the presentation
(the accountant's choice) - see app.services.financial_statements_service.

An account is given by its code and covers its sub-accounts («31» = 31, 31.1, 31.1.2.1...). How a line reads them:
  - "net": the balance of the accounts as it is (debit - credit), whatever its side;
  - "debit": only the accounts (each last-level account on its own) whose balance is devedor - a customer that owes;
  - "credit": only those whose balance is credor - a customer that paid in advance goes to the liabilities.
The asset lines show debit - credit, the equity and liability lines credit - debit; on the Demonstração de
resultados the proveitos show credit - debit and the custos debit - credit, as negatives.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Line:
    key: str
    label: str
    accounts: tuple[tuple[str, str], ...] = ()  # (code, net | debit | credit)
    kind: str = "line"  # line, section (a title), total (the sum of the lines named in sums)
    sums: tuple[str, ...] = field(default_factory=tuple)  # total: the keys added (a "-" prefix subtracts)


def _net(*codes: str) -> tuple[tuple[str, str], ...]:
    return tuple((c, "net") for c in codes)


THIRD_PARTIES = ("31", "32", "34", "35", "36", "37")

BALANCE_SHEET_ASSETS: tuple[Line, ...] = (
    Line("ANC", "Activos não correntes", kind="section"),
    Line("A_IMOB_CORP", "Imobilizações corpóreas", _net("11", "14", "18.1")),
    Line("A_IMOB_INC", "Imobilizações incorpóreas", _net("12", "18.2")),
    Line("A_SUBSID", "Investimentos em subsidiárias e associadas", _net("13.1", "13.2", "19.1", "19.2")),
    Line("A_FIN", "Outros activos financeiros", _net("13.3", "13.4", "13.5", "13.9", "18.3", "19.3", "19.4", "19.9")),
    Line("A_ONC", "Outros activos não correntes"),
    Line("T_ANC", "Total dos activos não correntes", kind="total", sums=("A_IMOB_CORP", "A_IMOB_INC", "A_SUBSID", "A_FIN", "A_ONC")),
    Line("AC", "Activos correntes", kind="section"),
    Line("A_EXIST", "Existências", _net("21", "22", "23", "24", "25", "26", "27", "28", "29")),
    Line("A_RECEBER", "Contas a receber", tuple((c, "debit") for c in THIRD_PARTIES) + _net("38")),
    Line("A_DISP", "Disponibilidades", _net("41", "42", "44", "45", "48", "49") + (("43", "debit"),)),
    Line("A_OAC", "Outros activos correntes"),
    Line("T_AC", "Total dos activos correntes", kind="total", sums=("A_EXIST", "A_RECEBER", "A_DISP", "A_OAC")),
    Line("T_ACTIVO", "Total do activo", kind="total", sums=("T_ANC", "T_AC")),
)

BALANCE_SHEET_EQUITY_LIABILITIES: tuple[Line, ...] = (
    Line("CP", "Capital próprio", kind="section"),
    Line("C_CAPITAL", "Capital", _net("51", "52")),
    Line("C_RESERVAS", "Reservas", _net("53", "54", "55", "56", "57", "58")),
    Line("C_TRANSITADOS", "Resultados transitados", _net("81", "89")),
    # before the closing, the result is still in the classes 6 and 7; after it, in 82 to 88
    Line("C_RESULTADO", "Resultado líquido do exercício", _net("6", "7", "82", "83", "84", "85", "86", "87", "88")),
    Line("T_CP", "Total do capital próprio", kind="total", sums=("C_CAPITAL", "C_RESERVAS", "C_TRANSITADOS", "C_RESULTADO")),
    Line("PNC", "Passivo não corrente", kind="section"),
    Line("P_EMPRESTIMOS_MLP", "Empréstimos de médio e longo prazos", _net("33")),
    Line("P_PROVISOES", "Provisões para outros riscos e encargos", _net("39")),
    Line("P_OPNC", "Outros passivos não correntes"),
    Line("T_PNC", "Total do passivo não corrente", kind="total", sums=("P_EMPRESTIMOS_MLP", "P_PROVISOES", "P_OPNC")),
    Line("PC", "Passivo corrente", kind="section"),
    Line("P_PAGAR", "Contas a pagar", tuple((c, "credit") for c in THIRD_PARTIES)),
    Line("P_EMPRESTIMOS_CP", "Empréstimos de curto prazo", (("43", "credit"),)),  # a bank account overdrawn
    Line("P_OPC", "Outros passivos correntes"),
    Line("T_PC", "Total do passivo corrente", kind="total", sums=("P_PAGAR", "P_EMPRESTIMOS_CP", "P_OPC")),
    Line("T_PASSIVO", "Total do passivo", kind="total", sums=("T_PNC", "T_PC")),
    Line("T_CP_PASSIVO", "Total do capital próprio e passivo", kind="total", sums=("T_CP", "T_PASSIVO")),
)

# proveitos: credit - debit; custos: shown as negatives (credit - debit too)
INCOME_STATEMENT: tuple[Line, ...] = (
    Line("R_VENDAS", "Vendas", _net("61")),
    Line("R_SERVICOS", "Prestações de serviços", _net("62")),
    Line("R_OUTROS_PROV", "Outros proveitos operacionais", _net("63")),
    Line("R_VAR_INV", "Variação nos inventários de produtos acabados e de produção em curso", _net("64")),
    Line("R_TRAB_PROPRIOS", "Trabalhos para a própria empresa", _net("65")),
    Line("R_CMV", "Custo das mercadorias vendidas e das matérias-primas e subsidiárias consumidas", _net("71")),
    Line("R_PESSOAL", "Custos com o pessoal", _net("72")),
    Line("R_AMORT", "Amortizações", _net("73")),
    Line("R_OUTROS_CUSTOS", "Outros custos e perdas operacionais", _net("75")),
    Line("T_OPERACIONAIS", "Resultados operacionais", kind="total", sums=(
        "R_VENDAS", "R_SERVICOS", "R_OUTROS_PROV", "R_VAR_INV", "R_TRAB_PROPRIOS", "R_CMV", "R_PESSOAL", "R_AMORT",
        "R_OUTROS_CUSTOS")),
    Line("R_FINANCEIROS", "Resultados financeiros", _net("66", "76")),
    Line("R_FILIAIS", "Resultados de filiais e associadas", _net("67", "77")),
    Line("R_NAO_OPER", "Resultados não operacionais", _net("68", "78")),
    Line("T_ANTES_IMPOSTOS", "Resultados antes de impostos", kind="total", sums=(
        "T_OPERACIONAIS", "R_FINANCEIROS", "R_FILIAIS", "R_NAO_OPER")),
    Line("R_IMPOSTO", "Imposto sobre o rendimento", _net("87.1")),
    Line("T_CORRENTES", "Resultados líquidos das actividades correntes", kind="total", sums=("T_ANTES_IMPOSTOS", "R_IMPOSTO")),
    Line("R_EXTRA", "Resultados extraordinários", _net("69", "79")),
    Line("R_IMPOSTO_EXTRA", "Imposto sobre o rendimento (resultados extraordinários)", _net("87.2")),
    Line("T_LIQUIDO", "Resultado líquido do exercício", kind="total", sums=("T_CORRENTES", "R_EXTRA", "R_IMPOSTO_EXTRA")),
)
