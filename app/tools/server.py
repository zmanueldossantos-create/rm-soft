"""
The RM SOFT server in one command - what the Windows service runs (RMSOFT-Setup.exe), and usable by hand:

    python -m app.tools.server                     brings the database up to date, then serves (= "servir")
    python -m app.tools.server atualizar-base      only brings the database up to date (alembic upgrade head)
    python -m app.tools.server cli <command>       app/cli.py (create-superadmin, installation-code)

Packaged by PyInstaller as rmsoft-servidor.exe (instalador/): the same three commands.

Serves the API - and the screens when FRONTEND_DIR is set - on RMSOFT_PORT (80 by default), for the whole shop's
network. One process: on the Windows installation the AGT queue (AGT_QUEUE=base) and the automatic copies run inside it.
Run from the folder that holds .env (the Windows service: C:\\ProgramData\\RMSOFT): its values also fill RMSOFT_PORT.
"""
import os
import sys
from pathlib import Path


def _root() -> Path:
    """Where alembic/ and alembic.ini are: next to the code, or inside the packaged program (PyInstaller)."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent))


def _load_env() -> None:
    """The .env of the current folder into the environment (RMSOFT_PORT, RMSOFT_HOST); what is already set wins."""
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env", override=False, encoding="utf-8")


def upgrade_database() -> None:
    from alembic import command
    from alembic.config import Config
    root = _root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(config, "head")


def serve() -> None:
    import uvicorn
    upgrade_database()
    from app.main import app  # the object, not "app.main:app": nothing to look up inside the packaged program
    uvicorn.run(app, host=os.getenv("RMSOFT_HOST", "0.0.0.0"), port=int(os.getenv("RMSOFT_PORT", "80")),
                workers=1, log_level="info")


def main() -> None:
    _load_env()
    args = sys.argv[1:]
    command = args[0] if args else "servir"
    if command == "servir":
        try:
            serve()
        except KeyboardInterrupt:  # Ctrl+C, or the Windows service stopping: a normal end, no traceback
            pass
    elif command == "atualizar-base":
        upgrade_database()
        print("Base de dados atualizada.")
    elif command == "cli":
        from app import cli
        sys.argv = [sys.argv[0]] + args[1:]
        cli.main()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
