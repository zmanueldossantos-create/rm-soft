"""
The formulas of the payroll items (rubricas), typed as text and kept as a tree - never run with eval.

    SB * 10%                              10 % of the base salary
    VH * 1,5 * HE50                       overtime at 50 %
    SE(ANTIGUIDADE >= 5; SB * 5%; 0)      a bonus after 5 years
    MIN(SUB_TRANSP; 30000)                another rubrica's amount, capped

Numbers take a comma or a point for the decimals; «;» separates the arguments of a function. Variables are the
built-in ones (salary, hours, days, seniority...) and the codes of the other rubricas. Functions: SE(cond; then; else),
MIN, MAX, ARRED(x) (2 decimals) / ARRED(x; n). Comparisons: > < >= <= = <>.

The tree has the shape of HR System's formula engine (literal, variable, binary_op, comparison, condition) plus
«function»; it is stored with the text, so a payslip is computed without parsing anything.
"""
import re
from decimal import ROUND_HALF_UP, Decimal


class FormulaError(Exception):
    """A formula that cannot be read or computed - the message says where (PT-PT)."""


_TOKEN = re.compile(r"\s*(?:(\d+(?:[.,]\d+)?)|([A-Za-z_][A-Za-z0-9_]*)|(>=|<=|<>|!=|==|[-+*/()%;<>=]))")
FUNCTIONS = {"SE": 3, "MIN": 2, "MAX": 2, "ARRED": (1, 2)}


def _tokens(text: str) -> list[tuple[str, str]]:
    out, pos, text = [], 0, text.strip()
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if match is None or match.end() == pos:
            raise FormulaError(f"Carácter inesperado na posição {pos + 1}: «{text[pos:].strip()[:10]}»")
        number, name, op = match.groups()
        if number is not None:
            out.append(("num", number.replace(",", ".")))
        elif name is not None:
            out.append(("name", name.upper()))
        else:
            out.append(("op", {"!=": "<>", "==": "="}.get(op, op)))
        pos = match.end()
        while pos < len(text) and text[pos].isspace():
            pos += 1
    return out


class _Parser:
    def __init__(self, tokens):
        self.tokens, self.i = tokens, 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None)

    def take(self, value=None):
        kind, val = self.peek()
        if kind is None:
            raise FormulaError("A fórmula está incompleta")
        if value is not None and val != value:
            raise FormulaError(f"Esperava «{value}» e encontrou «{val}»")
        self.i += 1
        return kind, val

    def comparison(self):
        left = self.expression()
        kind, val = self.peek()
        if kind == "op" and val in (">", "<", ">=", "<=", "=", "<>"):
            self.take()
            return {"type": "comparison", "operator": {"=": "==", "<>": "!="}.get(val, val), "left": left,
                    "right": self.expression()}
        return left

    def expression(self):
        node = self.term()
        while self.peek() in (("op", "+"), ("op", "-")):
            _, op = self.take()
            node = {"type": "binary_op", "operator": op, "left": node, "right": self.term()}
        return node

    def term(self):
        node = self.factor()
        while self.peek() in (("op", "*"), ("op", "/")):
            _, op = self.take()
            node = {"type": "binary_op", "operator": op, "left": node, "right": self.factor()}
        return node

    def factor(self):
        kind, val = self.peek()
        if (kind, val) == ("op", "-"):
            self.take()
            return {"type": "binary_op", "operator": "-", "left": {"type": "literal", "value": 0}, "right": self.factor()}
        if (kind, val) == ("op", "+"):
            self.take()
            return self.factor()
        node = self.atom()
        if self.peek() == ("op", "%"):  # 10% = 0,10
            self.take()
            node = {"type": "binary_op", "operator": "/", "left": node, "right": {"type": "literal", "value": 100}}
        return node

    def atom(self):
        kind, val = self.take()
        if kind == "num":
            return {"type": "literal", "value": float(val)}
        if (kind, val) == ("op", "("):
            node = self.comparison()
            self.take(")")
            return node
        if kind == "name":
            if self.peek() == ("op", "("):
                if val not in FUNCTIONS:
                    raise FormulaError(f"Função desconhecida: {val} (use SE, MIN, MAX ou ARRED)")
                self.take("(")
                args = [self.comparison()]
                while self.peek() == ("op", ";"):
                    self.take()
                    args.append(self.comparison())
                self.take(")")
                expected = FUNCTIONS[val]
                if (isinstance(expected, tuple) and len(args) not in expected) or (isinstance(expected, int) and len(args) != expected):
                    count = " ou ".join(map(str, expected)) if isinstance(expected, tuple) else str(expected)
                    raise FormulaError(f"{val} leva {count} argumento(s), separados por «;»")
                if val == "SE":
                    return {"type": "condition", "condition": args[0], "then": args[1], "else": args[2]}
                return {"type": "function", "name": val, "args": args}
            return {"type": "variable", "code": val}
        raise FormulaError(f"Esperava um número, uma variável ou «(» e encontrou «{val}»")


def parse(text: str) -> dict:
    """The tree of a formula - FormulaError with what is wrong."""
    if not (text or "").strip():
        raise FormulaError("Escreva a fórmula")
    tokens = _tokens(text)
    parser = _Parser(tokens)
    node = parser.comparison()
    if parser.i != len(tokens):
        raise FormulaError(f"Sobra «{parser.tokens[parser.i][1]}» no fim da fórmula")
    return node


def variables(node: dict) -> set[str]:
    kind = node.get("type")
    if kind == "variable":
        return {node["code"]}
    if kind in ("binary_op", "comparison"):
        return variables(node["left"]) | variables(node["right"])
    if kind == "condition":
        return variables(node["condition"]) | variables(node["then"]) | variables(node["else"])
    if kind == "function":
        return set().union(*(variables(a) for a in node["args"]))
    return set()


def _round(value: float, places: int = 2) -> float:
    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def evaluate(node: dict, context: dict[str, float]) -> float:
    kind = node.get("type")
    if kind == "literal":
        return float(node["value"])
    if kind == "variable":
        if node["code"] not in context:
            raise FormulaError(f"Variável desconhecida: {node['code']}")
        return float(context[node["code"]])
    if kind == "binary_op":
        left, right = evaluate(node["left"], context), evaluate(node["right"], context)
        op = node["operator"]
        if op == "/" and right == 0:
            return 0.0  # a payslip never breaks on a division by zero (no hours this month): the amount is 0
        return {"+": left + right, "-": left - right, "*": left * right, "/": left / right if right else 0.0}[op]
    if kind == "comparison":
        left, right = evaluate(node["left"], context), evaluate(node["right"], context)
        return float({">": left > right, "<": left < right, ">=": left >= right, "<=": left <= right,
                      "==": left == right, "!=": left != right}[node["operator"]])
    if kind == "condition":
        return evaluate(node["then"] if evaluate(node["condition"], context) else node["else"], context)
    if kind == "function":
        args = [evaluate(a, context) for a in node["args"]]
        if node["name"] == "MIN":
            return min(args)
        if node["name"] == "MAX":
            return max(args)
        if node["name"] == "ARRED":
            return _round(args[0], int(args[1]) if len(args) > 1 else 2)
    raise FormulaError("Fórmula inválida")
