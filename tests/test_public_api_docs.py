"""
API pública, step 6: the documentation in Portuguese - one self-contained page (no CDN, no script: it opens on a
client's server without internet), the guide and every operation of the API, made from the API itself.
"""
import re

import httpx

from app.main import app
from app.api.public_v1.routes import public_spec

API = "/api/public/v1"


async def _get(path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path)


async def test_the_page_stands_alone_and_documents_every_operation():
    page = await _get(API + "/docs")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    html = page.text
    # nothing from outside: no external script, stylesheet or font
    assert "<script" not in html.lower()
    assert not re.search(r'(src|href)="https?://', html), "an external file in the page"
    # the guide
    for section in ("Autenticação e segurança", "Idempotência", "Instalação local: o relé", "X-RM-Signature",
                    "Nunca ponha a chave no código de uma página web", "X-RM-Offline", "/requests/"):
        assert section in html, section
    # every operation of the API, from its own description
    for path, methods in public_spec()["paths"].items():
        for method in methods:
            assert f'<span class="m {"get" if method == "get" else method}">{method.upper()}</span><code>{path}</code>' \
                in html, (method, path)
    assert 'id="model-Rate"' in html and "stay_total_with_vat" in html


async def test_the_interactive_page_and_the_description_stay():
    assert (await _get(API + "/openapi.json")).json()["info"]["title"] == "RM SOFT - API pública"
    swagger = await _get(API + "/docs/experimentar")
    assert swagger.status_code == 200 and "swagger" in swagger.text.lower()
