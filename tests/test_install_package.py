"""
The Docker installation package (docker/cliente, made by instalador/fabricar_pacote_docker.ps1): the client's server runs
ready images - never the source code, never a build, never git. These checks keep it that way.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "docker" / "cliente"
SCRIPTS = ["instalar.ps1", "instalar.sh", "atualizar.ps1", "atualizar.sh"]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def test_the_compose_runs_the_package_images_only():
    compose = _text(KIT / "docker-compose.yml")
    assert not re.search(r"^\s+build:", compose, re.M)  # nothing is built on the client's server
    assert "../" not in compose  # nothing taken from the repository
    assert compose.count("image: rmsoft-backend:${APP_VERSION}") == 2  # backend and worker
    assert "image: rmsoft-web:${APP_VERSION}" in compose
    assert "./backup.sh:/backup.sh" in compose  # shipped in the package


def test_the_scripts_load_the_images_and_never_build_nor_use_git():
    for name in SCRIPTS:
        script = _text(KIT / name)
        assert "--build" not in script, name
        assert not re.search(r"\bgit\b", script), name
        assert "docker load -i" in script, name
        assert "VERSAO" in script, name


def test_the_client_image_holds_no_source_in_any_layer():
    dockerfile = _text(ROOT / "docker" / "saas" / "Dockerfile.backend")
    compile_stage, final_stage = dockerfile.split("\nFROM python:3.11.9-slim\n")
    assert "ARG SOURCELESS=false" in compile_stage  # the SaaS image keeps its sources (default)
    assert 'find app alembic -name "*.py" -delete' in compile_stage
    assert "sourceless = true" in compile_stage  # alembic finds the compiled migrations
    # the final image takes the code from the compile stage only - never COPY app from the build context
    assert "COPY --from=code /src/app ./app" in final_stage
    assert not re.search(r"^COPY (app|alembic) ", final_stage, re.M)


def test_the_maker_checks_the_image_and_ships_only_the_kit():
    maker = _text(ROOT / "instalador" / "fabricar_pacote_docker.ps1")
    assert "SOURCELESS=true" in maker
    assert "-name '*.py' | wc -l" in maker  # refuses an image that still holds a .py
    for name in SCRIPTS + ["docker-compose.yml", "Caddyfile", ".env.example"]:
        assert f'"{name}"' in maker, name
        assert (KIT / name).exists(), name
    assert '"app"' not in maker and "Copy-Item (Join-Path $Raiz \"app" not in maker


def test_alembic_ini_has_the_line_the_compile_stage_switches():
    assert "# sourceless = false" in (ROOT / "alembic.ini").read_text(encoding="utf-8")
