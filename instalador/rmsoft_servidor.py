"""Entry point of rmsoft-servidor.exe (PyInstaller, see fabricar_setup.ps1): the commands of app/tools/server.py."""
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from app.tools.server import main
    main()
