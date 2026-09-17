"""
Command-line utility to bootstrap the platform.
Run once to create the very first SUPER_ADMIN account, since no one else
can create it (SUPER_ADMIN creation is not exposed via any API route).
Usage: python -m app.cli create-superadmin
"""
import asyncio
import sys

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole


async def create_superadmin(full_name: str, phone_number: str, password: str):
    async with AsyncSessionLocal() as db:
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
        print(f"SUPER_ADMIN created: {user.full_name} ({user.phone_number}) - id={user.id}")


def main():
    if len(sys.argv) < 2 or sys.argv[1] != "create-superadmin":
        print("Usage: python -m app.cli create-superadmin")
        sys.exit(1)

    full_name = input("Full name: ").strip()
    phone_number = input("Phone number (E.164, ex. +244900000000): ").strip()
    password = input("Password: ").strip()

    asyncio.run(create_superadmin(full_name, phone_number, password))


if __name__ == "__main__":
    main()
