"""
The informative line a hotel stay leaves on its invoice (Observações): who stayed, in which room, from when to when.
The fiscal customer of the invoice stays the one who pays (a company, the guest, or Consumidor final) - this line
never replaces it, it only tells the reception and the guest what the document is for.
"""
from datetime import datetime, timedelta, timezone

LUANDA = timezone(timedelta(hours=1))


def stay_observation(room_name: str, starts_at: datetime, ends_at: datetime,
                     guest_name: str | None = None, party_size: int | None = None, person_label: str = "Hóspede") -> str:
    """'Hóspede: Família Teste (2 pax) - Quarto 101 - 11/10/2026 14:00 a 13/10/2026 12:00' (Luanda time).
    person_label: who the name is - the guest of a room, the client of a marcação ("Cliente")."""
    def moment(value: datetime) -> str:
        if value.tzinfo is None:  # a naive time is already Luanda wall-clock time
            value = value.replace(tzinfo=LUANDA)
        return value.astimezone(LUANDA).strftime("%d/%m/%Y %H:%M")

    parts = []
    if guest_name:
        parts.append(person_label + ": " + guest_name + (f" ({party_size} pax)" if party_size else ""))
    parts.append(room_name)
    parts.append(f"{moment(starts_at)} a {moment(ends_at)}")
    return " - ".join(parts)[:500]
