"""
The Ajuda guides: every link and screen exists, every permission is a real one, a user sees only the guides of his
screens (a cashier the Caixa's, nobody the Farmácia's without the sector), the search finds by words without accents,
and the assistant reads the same guides.
"""
import json
import re
from pathlib import Path

from app.services.ai.tools import run_tool, tools_for
from app.services.help_guides import MODULES, PAGES, PLATFORM_MODULES, PLATFORM_PAGES, search_guides, visible_guides
from app.services.permission_service import PERMISSION_CATALOG

APP_JSX = (Path(__file__).resolve().parent.parent / "frontend" / "src" / "App.jsx").read_text(encoding="utf-8")
ROUTES = set(re.findall(r'<Route\s+path="([^"]+)"', APP_JSX)) | set(re.findall(r'path="(/admin/[^"]+)"', APP_JSX))
CATALOG = {entry[0] for entry in PERMISSION_CATALOG}


def test_links_screens_and_permissions_exist():
    every = MODULES + PLATFORM_MODULES + PAGES + PLATFORM_PAGES
    ids = [g["id"] for g in every]
    assert len(ids) == len(set(ids)), "duplicate guide ids"
    module_ids = {m["id"] for m in MODULES + PLATFORM_MODULES}
    for guide in every:
        assert set(guide.get("perms", [])) | set(guide.get("requires", [])) <= CATALOG, guide["id"]
        assert guide.get("perms") or guide.get("roles"), f"{guide['id']} is shown to everybody"
        if "path" in guide:
            assert guide["path"] in ROUTES, guide["path"]
        if guide.get("module"):
            assert guide["module"] in module_ids, guide["id"]
        for step in guide["steps"]:
            if isinstance(step, dict) and step.get("link"):
                assert step["link"].split("?")[0] in ROUTES, (guide["id"], step["link"])


def test_each_user_sees_the_guides_of_his_screens():
    cashier = visible_guides({"pos:view", "pos:checkout"}, "CAIXA")
    assert {g["id"] for g in cashier} == {"caixa-tesouraria", "caixa"}
    circuit = next(g for g in cashier if g["id"] == "caixa-tesouraria")
    assert [s["link"] for s in circuit["steps"]][:2] == [None, "/caixa"]  # no «Ir» to the gestor's Empresa screen

    # a pharmacy (stock, no production): no Matéria-prima nor Produção, as in its menu
    pharmacy = {g["id"] for g in visible_guides({p for p in CATALOG if not p.startswith(("recipes", "production"))}, "GESTOR")}
    assert "materia-prima" not in pharmacy and "producao" not in pharmacy and "produtos" in pharmacy

    # the screens kept for the gestor's role, whatever the permissions
    assert "utilizadores" not in {g["id"] for g in visible_guides(CATALOG, "CAIXA")}
    gestor = visible_guides(CATALOG - {"pharmacy:registers"}, "GESTOR")
    ids = [g["id"] for g in gestor]
    assert "utilizadores" in ids and "farmacia" not in ids and "receitas" not in ids
    assert gestor[0]["kind"] == "module" and gestor[-1]["kind"] == "page"  # the circuits first
    caixa = next(g for g in gestor if g["id"] == "caixa")
    assert caixa["module"] == "caixa-tesouraria" and caixa["steps"][0]["link"] is None

    # a page's circuit the user cannot see is not pointed to
    alone = visible_guides({"pos:view"}, "CAIXA") + visible_guides({"vat:return"}, "CONTABILISTA")
    assert next(g for g in alone if g["id"] == "apuramento-iva")["module"] == "fim-do-mes"
    # the platform has its own guides, and only them
    platform = visible_guides(set(), "SUPER_ADMIN")
    assert {g["id"] for g in platform} == {"novo-cliente", "manter-clientes", "empresas", "catalogo-referencia", "configuracoes", "visao-global"}
    assert next(g for g in platform if g["id"] == "empresas")["module"] == "novo-cliente"
    assert not {"empresas", "novo-cliente"} & {g["id"] for g in visible_guides(CATALOG, "GESTOR")}


def test_search_ignores_accents_and_ranks_the_title():
    guides = visible_guides(CATALOG, "GESTOR")
    found = [g["id"] for g in search_guides(guides, "Como faço para fechar o periodo?")]
    assert found[0] in ("periodos", "fim-do-mes") and len(found) == 3
    assert [g["id"] for g in search_guides(guides, "pagar fornecedor")][0] == "compras"
    assert search_guides(guides, "xyz") == []


async def test_the_assistant_reads_the_guides():
    permissions = {"assistant:use", "purchases:view", "suppliers:manage"}
    assert "consultar_ajuda" in [t["name"] for t in tools_for(permissions)]
    answer = json.loads(await run_tool(None, None, permissions, "consultar_ajuda", {"pergunta": "pagar um fornecedor"},
                                       role="GESTOR"))
    assert answer["guias"][0].startswith("Como funciona: Compras e fornecedores")
    assert "«Pagar»" in answer["guias"][0]
    nothing = json.loads(await run_tool(None, None, permissions, "consultar_ajuda", {"pergunta": "quartos"}, role="GESTOR"))
    assert "erro" in nothing  # the Reservas guides are not his
