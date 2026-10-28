"""
Calls the AGT by hand (Faturação Eletrónica) - to check the access, the signatures and the keys, from a machine that
reaches the AGT (the platform's settings are used: environment, access, software signature):

    python -m app.tools.agt_teste --nif 5000413178 series [--estab SEDE]
    python -m app.tools.agt_teste --nif 5000413178 solicitar-serie --tipo FT [--ano 2026] [--estab SEDE] [--indicador N]
    python -m app.tools.agt_teste --nif 5000413178 estado <requestID>
    python -m app.tools.agt_teste --nif 5000413178 consultar "<documentNo>"

--nif: a company of this installation (its key is used), an AGT test NIF imported in Configurações → Faturação
Eletrónica → NIFs de teste (its key is used), or any NIF with --chave <ficheiro.pem> (the file stays on this machine,
its content is never printed). The AGT's answer is printed as it came, and
the call is written in the journal (agt_calls).
"""
import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

import app.models  # noqa: F401 - every model registered
from app.core.database import AsyncSessionLocal
from app.core.secret_box import decrypt_secret
from app.models.agt_test_taxpayer import AgtTestTaxpayer
from app.models.company import Company
from app.services import agt_client


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.tools.agt_teste", description="Chamadas à AGT (teste)")
    parser.add_argument("--nif", required=True, help="NIF do contribuinte emissor")
    parser.add_argument("--chave", help="ficheiro .pem da chave privada (sem empresa com este NIF)")
    commands = parser.add_subparsers(dest="command", required=True)
    series = commands.add_parser("series", help="listarSeries")
    series.add_argument("--estab", default="SEDE")
    ask = commands.add_parser("solicitar-serie", help="solicitarSerie")
    ask.add_argument("--tipo", required=True, help="FT, FR, NC, ND, RC...")
    ask.add_argument("--ano", type=int, default=date.today().year)
    ask.add_argument("--estab", default="SEDE")
    ask.add_argument("--indicador", default="N", choices=["N", "C"])
    state = commands.add_parser("estado", help="obterEstado")
    state.add_argument("request_id")
    document = commands.add_parser("consultar", help="consultarFactura")
    document.add_argument("document_no")
    return parser


async def run(args) -> int:
    key = Path(args.chave).read_text(encoding="utf-8") if args.chave else None
    async with AsyncSessionLocal() as db:
        company = (await db.execute(select(Company).where(Company.nif == args.nif))).scalar_one_or_none()
        if company is None:
            if not key:
                test = (await db.execute(select(AgtTestTaxpayer).where(AgtTestTaxpayer.nif == args.nif))).scalar_one_or_none()
                key = decrypt_secret(test.private_key_encrypted) if test else None
            if not key:
                print(f"NIF {args.nif}: nem empresa nem NIF de teste importado - indique --chave <ficheiro.pem>")
                return 2
            company = SimpleNamespace(id=None, nif=args.nif)
        try:
            ctx = await agt_client.context_for(db, company, private_key=key)
        except agt_client.AgtConfigError as e:
            print(str(e))
            return 2
    print(f"AGT {ctx.environment} - {ctx.base_url} - NIF {ctx.nif}")
    try:
        if args.command == "series":
            answer = await agt_client.listar_series(ctx, establishmentNumber=args.estab)
        elif args.command == "solicitar-serie":
            answer = await agt_client.solicitar_serie(ctx, args.ano, args.tipo, args.estab, args.indicador)
        elif args.command == "estado":
            answer = await agt_client.obter_estado(ctx, args.request_id)
        else:
            answer = await agt_client.consultar_factura(ctx, args.document_no)
    except agt_client.AgtRefused as e:
        print(f"RECUSADO ({e.status_code}): {e}")
        print(json.dumps(e.body, ensure_ascii=False, indent=2) if isinstance(e.body, (dict, list)) else e.body)
        return 1
    except agt_client.AgtUnavailable as e:
        print(f"SEM RESPOSTA: {e}")
        return 1
    print("OK")
    print(json.dumps(answer, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str]) -> int:
    return asyncio.run(run(_parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
