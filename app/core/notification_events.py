"""
The events that can send a notification (Definições da Empresa → Notificações). Each one is switched on per recipient
by the gestor; it is offered only to a company whose sectors have it (capability: None = every company).

by_others: sent only when the action is done by someone else than the gestor (the cashier, the receptionist...) - unless
the company switched on «also what the gestor does». Stock baixo is always sent: nobody "did" it.
"""
from dataclasses import dataclass


# not a sector's capability: the company issues in Faturação Eletrónica (its AGT events)
ELECTRONIC = "FATURACAO_ELETRONICA"


@dataclass(frozen=True)
class Event:
    code: str
    label: str
    description: str
    capability: str | None = None
    by_others: bool = True


EVENTS: dict[str, Event] = {e.code: e for e in (
    Event("CHECK_IN", "Quarto ocupado", "Check-in ou walk-in: o quarto, o hóspede, as noites", "HOTEL_STAY"),
    Event("CHECK_OUT", "Quarto libertado", "Check-out: o quarto, o hóspede, o total", "HOTEL_STAY"),
    Event("RESERVA_ONLINE", "Nova reserva online", "Uma reserva chegada do site (API): o recurso, o hóspede, as datas - "
          "a confirmar na receção", "BOOKINGS", by_others=False),
    Event("MESA_ABERTA", "Mesa aberta", "Uma conta de mesa aberta: a mesa, quem a abriu", "OPEN_ACCOUNTS"),
    Event("MESA_FECHADA", "Mesa fechada", "Uma conta de mesa fechada: a mesa, o total, o documento", "OPEN_ACCOUNTS"),
    Event("VENDA", "Venda", "Cada venda (ou só acima do montante mínimo escolhido): o documento, o total, a caixa"),
    Event("PRECO_ALTERADO", "Preço alterado", "Uma venda com um preço livre (diferente do catálogo): o artigo, o "
          "preço do catálogo e o aplicado, a caixa, quem vendeu"),
    Event("CAIXA_FECHADA", "Caixa fechada", "O fecho de uma caixa: esperado, contado e a diferença"),
    Event("STOCK_BAIXO", "Stock baixo", "Um produto abaixo do seu stock mínimo", "STOCK", by_others=False),
    Event("AGT_CONTINGENCIA", "AGT: contingência", "A AGT deixou de responder (entrada em contingência) ou voltou "
          "(saída) - Faturação Eletrónica", ELECTRONIC, by_others=False),
    Event("AGT_ATRASO", "AGT: documentos em atraso", "Documentos ainda não validados pela AGT 18 h depois de emitidos "
          "(a AGT penaliza a partir das 24 h) - Faturação Eletrónica", ELECTRONIC, by_others=False),
)}

CHANNELS = {"EMAIL": "Email", "TELEGRAM": "Telegram", "WHATSAPP": "WhatsApp"}
