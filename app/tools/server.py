"""
The RM SOFT server in one command - what the Windows service runs (RMSOFT-Setup.exe), and usable by hand:

    python -m app.tools.server

Brings the database to the code's version (alembic upgrade head), then serves the API - and the screens when
FRONTEND_DIR is set - on RMSOFT_PORT (80 by default), for the whole shop's network. One process: on the Windows
installation the AGT queue (AGT_QUEUE=base) and the automatic copies run inside it.
"""
import os
import sys
from pathlib import Path


def _root() -> Path:
    """Where alembic/ and alembic.ini are: next to the code, or inside the packaged program (PyInstaller)."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent.parent))


def upgrade_database() -> None:
    from alembic import command
    from alembic.config import Config
    root = _root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(config, "head")


def main() -> None:
    import uvicorn
    upgrade_database()
    uvicorn.run("app.main:app", host=os.getenv("RMSOFT_HOST", "0.0.0.0"), port=int(os.getenv("RMSOFT_PORT", "80")),
                workers=1, log_level="info")


if __name__ == "__main__":
    main()
