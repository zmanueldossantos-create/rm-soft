"""
Command-line utility to bootstrap an installation.

    python -m app.cli create-superadmin            the first SUPER_ADMIN account (no API route creates one)
    python -m app.cli create-superadmin --if-none  the same, skipped when the installation already has one
    python -m app.cli installation-code            this server's code, for its licence (app/core/license.py)

The installation kit (docker/cliente) runs them inside the backend container.
"""
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole


async def superadmin_exists() -> bool:
    async with AsyncSessionLocal() as db:
        found = (await db.execute(select(User.id).where(User.role == UserRole.SUPER_ADMIN).limit(1))).first()
        return found is not None


async def create_superadmin(full_name: str, phone_number: str, password: str):
    async with AsyncSessionLocal() as db:
        taken = (await db.execute(select(User.id).where(User.company_id.is_(None), User.phone_number == phone_number))).first()
        if taken:
            print(f"Já existe uma conta da plataforma com o número {phone_number} - nada foi criado.")
            return
        user = User(
            company_id=None,
            full_name=full_name,
            phone_number=phone_number,
            password_hash=hash_password(password),
            role=UserRole.SUPER_ADMIN,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"SUPER_ADMIN criado: {user.full_name} ({user.phone_number})")


def _ask_superadmin() -> tuple[str, str, str]:
    full_name = input("Nome completo: ").strip()
    phone_number = input("Telefone (ex.: +244923000000): ").strip().replace(" ", "")
    while True:
        password = getpass.getpass("Palavra-passe (mínimo 8, não aparece): ")
        if len(password) < 8:
            print("Mínimo 8 caracteres.")
        elif password != getpass.getpass("Repetir a palavra-passe: "):
            print("As duas palavras-passe não coincidem.")
        else:
            return full_name, phone_number, password


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "create-superadmin":
        if "--if-none" in sys.argv and asyncio.run(superadmin_exists()):
            print("Esta instalação já tem uma conta SUPER_ADMIN - nada a fazer.")
            return
        asyncio.run(create_superadmin(*_ask_superadmin()))
    elif command == "installation-code":
        from app.core.license import installation_code
        print(installation_code())
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
