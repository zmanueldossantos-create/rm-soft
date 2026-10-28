"""
The public API's documentation (P4 step 6), in Portuguese, at /api/public/v1/docs: ONE self-contained page - no CDN,
no script, nothing fetched - so it opens on a client's server without internet too.

The guide (keys, security, errors, idempotency, documents, bookings, the relay) is written here; the reference of the
operations is made from the API's own description (OpenAPI), so it never drifts from the code. The interactive page
(Swagger, which needs internet for its files) stays at /api/public/v1/docs/experimentar.
"""
import html

PREFIX = "/api/public/v1"
TAG_ORDER = ["Chave", "Catálogo", "Clientes", "Documentos", "Reservas"]
METHOD_CLASS = {"get": "get", "post": "post", "put": "put", "delete": "delete", "patch": "put"}


def _e(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def _code(text: str) -> str:
    return f"<pre><code>{_e(text.strip())}</code></pre>"



# the examples (kept apart: a backslash cannot sit inside an f-string expression before Python 3.12)
PING_EXAMPLE = _code("""curl https://ENDERECO/api/public/v1/ping \\
  -H "Authorization: Bearer rmk_A_SUA_CHAVE\"""")
DOCUMENT_EXAMPLE = _code("""curl -X POST https://ENDERECO/api/public/v1/documents \\
  -H "Authorization: Bearer rmk_A_SUA_CHAVE" \\
  -H "Idempotency-Key: ENC-2026-001234" \\
  -H "Content-Type: application/json" \\
  -d '{"type": "FR", "payment_method": "MB", "document_reference": "ENC-2026-001234",
       "lines": [{"product_id": "…", "quantity": 2}]}'""")
WEBHOOK_PHP = _code("""// PHP
$body = file_get_contents('php://input');
$secret = hash('sha256', getenv('RMSOFT_API_KEY'));          // o SHA-256 da chave rmk_...
$expected = hash_hmac('sha256', $body, $secret);
if (!hash_equals($expected, $_SERVER['HTTP_X_RM_SIGNATURE'] ?? '')) { http_response_code(401); exit; }
$event = json_decode($body, true);   // request_id, status, response.status_code, response.body""")
WEBHOOK_NODE = _code("""// Node.js
const crypto = require('crypto');
const secret = crypto.createHash('sha256').update(process.env.RMSOFT_API_KEY).digest('hex');
const expected = crypto.createHmac('sha256', secret).update(rawBody).digest('hex');
const ok = crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(req.headers['x-rm-signature'] || ''));""")
SYNC_PHP = _code("""<?php // PHP - os produtos alterados desde a última sincronização
$ch = curl_init('https://ENDERECO/api/public/v1/catalog/products?updated_since=' . urlencode($ultima));
curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true,
  CURLOPT_HTTPHEADER => ['Authorization: Bearer ' . getenv('RMSOFT_API_KEY')]]);
$res = json_decode(curl_exec($ch), true);
foreach ($res['items'] as $p) { /* $p['name'], $p['price_with_vat'], $p['stock'] */ }""")
BOOKING_NODE = _code("""// Node.js (18+) - criar uma reserva
const res = await fetch('https://ENDERECO/api/public/v1/bookings', {
  method: 'POST',
  headers: { 'Authorization': 'Bearer ' + process.env.RMSOFT_API_KEY, 'Content-Type': 'application/json',
             'Idempotency-Key': 'WEB-' + reserva.id },
  body: JSON.stringify({ resource_type_id, service_id, check_in: '2026-12-20', check_out: '2026-12-23',
                         guest_name: 'Maria Domingos', party_size: 2, external_reference: 'WEB-' + reserva.id }),
});
if (res.status === 202) { /* servidor da empresa desligado: guardar request_id e consultar depois */ }""")

# ------------------------------------------------------------------------------------------------------- the guide

GUIDE = [
    ("comecar", "Começar", f"""
<p>A API pública liga outros programas da empresa ao RM SOFT: o site, a loja online, um motor de reservas, uma
ferramenta de relatórios. Responde em JSON, com os nomes dos campos em inglês e as mensagens em português.</p>
<ol>
<li>O gestor cria uma <b>chave de acesso</b> em <i>Definições da Empresa → Integração API → Nova chave</i>, só com as
permissões de que o programa precisa. A chave (<code>rmk_…</code>) só é mostrada <b>uma vez</b>.</li>
<li>O <b>endereço da API</b> aparece no mesmo ecrã. Numa instalação local ligada ao relé da RM SOFT, o site usa o
endereço do relé (ver <a href="#rele">Instalação local: o relé</a>).</li>
<li>Teste a chave: <code>GET {PREFIX}/ping</code> devolve a empresa e as permissões da chave.</li>
</ol>
{PING_EXAMPLE}
"""),
    ("autenticacao", "Autenticação e segurança", """
<p>Cada pedido leva a chave, de uma destas duas formas:</p>
<ul><li><code>Authorization: Bearer rmk_…</code></li><li><code>X-API-Key: rmk_…</code></li></ul>
<div class="warn"><b>Nunca ponha a chave no código de uma página web</b> (JavaScript no navegador): qualquer visitante
a veria e usaria. O pedido parte sempre do <b>servidor</b> do site (PHP, Node, Python…), que guarda a chave numa
variável de ambiente, nunca no código publicado.</div>
<ul>
<li><b>Permissões</b> - cada chave tem as suas: <i>Catálogo</i>, <i>Clientes</i>, <i>Documentos</i>, <i>Reservas</i>.
Sem a permissão: <code>403</code>.</li>
<li><b>Limite</b> - 60 pedidos por minuto por chave. Acima: <code>429</code> com <code>Retry-After: 60</code>.</li>
<li><b>Revogar</b> - uma chave perdida ou que já não se usa revoga-se no mesmo ecrã: deixa de funcionar logo
(<code>401</code>). Cada pedido fica no registo do gestor (90 dias).</li>
<li><b>Contrato terminado</b> - a empresa fica só de leitura: as leituras continuam, as escritas respondem
<code>423</code>.</li>
</ul>
"""),
    ("erros", "Respostas e erros", """
<table>
<tr><th>Código</th><th>Quando</th></tr>
<tr><td><code>200</code> / <code>201</code></td><td>Feito (201: criado).</td></tr>
<tr><td><code>202</code></td><td>Só pelo relé: o servidor da empresa está desligado - o pedido foi guardado (ver o relé).</td></tr>
<tr><td><code>401</code></td><td>Chave em falta, errada ou revogada.</td></tr>
<tr><td><code>403</code></td><td>A chave não tem esta permissão, ou a Integração API não está no plano da empresa.</td></tr>
<tr><td><code>404</code></td><td>Não encontrado (ou de outra empresa: nunca se vê o que não é da empresa da chave).</td></tr>
<tr><td><code>409</code></td><td>Conflito: cliente já existente (com o seu <code>id</code>), stock insuficiente, período fechado, sem quarto livre.</td></tr>
<tr><td><code>422</code></td><td>Dado inválido: <code>detail</code> é uma mensagem, ou a lista dos campos (<code>loc</code>, <code>msg</code>).</td></tr>
<tr><td><code>423</code></td><td>Empresa só de leitura (contrato terminado).</td></tr>
<tr><td><code>429</code></td><td>Limite de pedidos por minuto atingido.</td></tr>
<tr><td><code>503</code> / <code>504</code></td><td>Só pelo relé: servidor da empresa desligado, ou não respondeu a tempo - tente mais tarde.</td></tr>
</table>
<p>O corpo de um erro é sempre <code>{"detail": …}</code>, em português, para mostrar tal como está.</p>
"""),
    ("listas", "Listas, sincronização e preços", """
<ul>
<li>As listas são paginadas: <code>page</code> (a partir de 1) e <code>page_size</code> (até 200); a resposta traz
<code>items</code> e <code>total</code>.</li>
<li>Para manter o site sincronizado sem descarregar tudo: guarde a hora do último pedido e peça só o que mudou com
<code>updated_since</code> (ISO 8601, ex. <code>2026-10-27T10:00:00Z</code>).</li>
<li><code>price</code> é o preço <b>sem IVA</b>; <code>price_with_vat</code> o que o cliente paga (IVA de 0, 5 ou
14 %). Os preços são sempre os do RM SOFT: um documento emitido pela API usa os preços do catálogo.</li>
<li><code>stock</code>: a quantidade em todos os armazéns. <b>0 ou menos: indisponível</b> (o stock pode ficar negativo
quando a empresa o permite). <code>null</code>: artigo sem controlo de stock (sempre disponível).</li>
<li>Os artigos de uso interno, sem preço, inativos ou de uma categoria fechada à venda nunca aparecem.</li>
</ul>
"""),
    ("idempotencia", "Idempotência: nunca duas vezes", f"""
<p>Emitir um documento e criar uma reserva exigem o cabeçalho <code>Idempotency-Key</code>: um identificador único
por pedido (8 a 100 caracteres - um UUID, ou o n.º da encomenda no site).</p>
<ul>
<li>Se o mesmo pedido for enviado de novo com a mesma chave (a rede caiu antes da resposta…), a resposta é
<b>a mesma</b> (com <code>Idempotent-Replayed: true</code>) e <b>nada é criado duas vezes</b>.</li>
<li>A mesma chave com um pedido diferente: <code>422</code>. Use uma chave nova por pedido novo.</li>
<li>As respostas ficam guardadas 30 dias.</li>
</ul>
<p>Um cliente não precisa da chave: um NIF já registado responde <code>409</code> com o <code>id</code> do cliente
existente - use esse.</p>
{DOCUMENT_EXAMPLE}
"""),
    ("documentos", "Documentos e a AGT", """
<ul>
<li><b>FT</b> Fatura (paga depois), <b>FR</b> Fatura/Recibo (paga ao emitir), <b>FP</b> Fatura Pro-forma (orçamento,
não fiscal). Mesmas séries, numeração, IVA, stock e períodos que nos ecrãs do RM SOFT.</li>
<li>Uma FR exige <code>payment_method</code>: MB (Multicaixa), TB (transferência), CC/CD (cartão), DE (dinheiro
eletrónico). <b>Numerário não</b>: só é recebido na caixa.</li>
<li><code>document_reference</code>: o n.º da encomenda no site - impresso no documento e pesquisável.</li>
<li>Faturação Eletrónica: uma FT/FR segue logo para a AGT; <code>agt.status</code> passa de <code>PENDENTE</code> a
<code>ENVIADA</code> (ou <code>ERRO</code>, a empresa reenvia). Consulte <code>GET /documents/{id}</code> ou siga com
<code>updated_since</code>. Empresa em modo manual, ou documento não fiscal (FP): <code>agt</code> é
<code>null</code>.</li>
<li>O PDF (o mesmo do RM SOFT, com QR code): <code>GET /documents/{id}/pdf</code> (<code>?format=a4</code> ou
<code>thermal</code>).</li>
</ul>
"""),
    ("reservas", "Reservas", """
<ol>
<li><code>GET /bookings/availability?check_in=2026-12-20&amp;check_out=2026-12-23</code> - por tipo de quarto: quantos
estão livres, as tarifas e o total da estadia com IVA. Um hotel pede por dias (as horas de entrada e saída são as do
tipo, ex. 14:00 → 12:00); uma mesa ou uma marcação pede com horas exatas (<code>starts_at</code>,
<code>ends_at</code>).</li>
<li><code>POST /bookings</code> com o tipo (<code>resource_type_id</code>), a tarifa (<code>service_id</code>), as datas e
o hóspede: o RM SOFT escolhe um quarto livre. Sem quarto livre: <code>409</code>.</li>
<li>A reserva chega <b>PENDENTE</b>: a receção confirma-a (<b>CONFIRMADA</b>). Siga-a com
<code>GET /bookings/{id}</code>, <code>GET /bookings?external_reference=…</code> ou <code>updated_since</code>.</li>
<li><code>POST /bookings/{id}/cancel</code> - só as reservas feitas pela API, e só antes do check-in.</li>
</ol>
<p>O site só vê as reservas que ele próprio fez: as do balcão (e os seus hóspedes) nunca aparecem.</p>
"""),
    ("rele", "Instalação local: o relé", f"""
<p>Quando o RM SOFT está instalado num servidor da empresa (na loja, no hotel), o site, na internet, não o consegue
chamar. O <b>relé da RM SOFT</b> liga-os: o site chama a plataforma da RM SOFT <b>com a mesma chave e os mesmos
caminhos</b>, e o servidor da empresa vai lá buscar os pedidos (nenhuma porta é aberta na empresa).</p>
<ul>
<li><b>Servidor ligado</b>: a resposta é a do servidor, em 1 ou 2 segundos - igual a uma ligação direta
(cabeçalho <code>X-RM-Relay: true</code>).</li>
<li><b>Servidor desligado, escrita</b> (documento, reserva, cliente): <code>202</code> com
<code>{{"request_id", "status": "PENDENTE", "status_url"}}</code>. O pedido é tratado logo que o servidor volte.
Consulte <code>GET {PREFIX}/requests/{{request_id}}</code>: <code>status</code> passa a <code>FEITO</code> e
<code>response</code> traz a resposta (<code>status_code</code> e <code>body</code>). Reenviar o mesmo pedido com a
mesma <code>Idempotency-Key</code> devolve o mesmo pedido, e depois a mesma resposta.</li>
<li><b>Servidor desligado, leitura</b> do catálogo ou da disponibilidade: a resposta vem da última <b>foto</b> enviada
pelo servidor (de 5 em 5 minutos), com <code>X-RM-Offline: true</code> e <code>X-RM-Snapshot-At</code> (a hora da
foto). Uma reserva feita sobre uma foto antiga chega PENDENTE: a receção confirma-a ou recusa-a.</li>
<li><b>Outras leituras</b> com o servidor desligado: <code>503</code> - tente mais tarde.</li>
</ul>
<h4>Webhook: ser avisado em vez de perguntar</h4>
<p>Junte a uma escrita o cabeçalho <code>X-Callback-Url: https://o-seu-site/rm-soft</code>: quando o pedido é tratado,
a plataforma envia para lá (POST) o mesmo JSON que <code>GET /requests/{{id}}</code>, assinado no cabeçalho
<code>X-RM-Signature</code>: HMAC-SHA256 do corpo, com a chave = o SHA-256 (hexadecimal) da sua chave de acesso.
Verifique sempre a assinatura antes de confiar no conteúdo.</p>
{WEBHOOK_PHP}
{WEBHOOK_NODE}
<p>O endereço do webhook tem de ser público (https). A plataforma tenta 3 vezes.</p>
"""),
    ("exemplos", "Exemplos (do servidor do site)", f"""
{SYNC_PHP}
{BOOKING_NODE}
"""),
]


# --------------------------------------------------------------------------------------------- the reference (OpenAPI)

def _resolve(spec: dict, schema: dict | None) -> dict:
    seen = 0
    while schema and "$ref" in schema and seen < 10:
        schema = spec["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
        seen += 1
    return schema or {}


def _type(spec: dict, schema: dict) -> str:
    if not schema:
        return ""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if "anyOf" in schema:
        return " | ".join(t for t in (_type(spec, s) for s in schema["anyOf"]) if t and t != "null") + \
            (" | null" if any(s.get("type") == "null" for s in schema["anyOf"]) else "")
    if schema.get("type") == "array":
        return "lista de " + _type(spec, schema.get("items", {}))
    if "enum" in schema:
        return " | ".join(str(v) for v in schema["enum"])
    if "const" in schema:
        return str(schema["const"])
    kind = schema.get("type", "")
    return f"{kind} ({schema['format']})" if schema.get("format") and kind == "string" else kind


def _fields(spec: dict, schema: dict) -> str:
    schema = _resolve(spec, schema)
    props = schema.get("properties") or {}
    if not props:
        return ""
    required = set(schema.get("required") or [])
    rows = "".join(
        f"<tr><td><code>{_e(name)}</code>{' <span class=req>obrigatório</span>' if name in required else ''}</td>"
        f"<td class=type>{_e(_type(spec, prop))}</td><td>{_e(prop.get('description', ''))}</td></tr>"
        for name, prop in props.items())
    return f"<table class=fields><tr><th>Campo</th><th>Tipo</th><th>Descrição</th></tr>{rows}</table>"


def _operation(spec: dict, path: str, method: str, op: dict) -> str:
    anchor = (method + path).replace("/", "-").replace("{", "").replace("}", "")
    parts = [f'<div class=op id="{_e(anchor)}"><h4><span class="m {METHOD_CLASS.get(method, "get")}">{method.upper()}</span>'
             f'<code>{_e(path)}</code> <span class=sum>{_e(op.get("summary", ""))}</span></h4>']
    if op.get("description"):
        parts.append(f"<p>{_e(op['description'])}</p>")
    params = [p for p in op.get("parameters", [])]
    if params:
        rows = "".join(
            f"<tr><td><code>{_e(p['name'])}</code>{' <span class=req>obrigatório</span>' if p.get('required') else ''}"
            f"</td><td>{_e({'query': 'URL (?)', 'path': 'caminho', 'header': 'cabeçalho'}.get(p['in'], p['in']))}</td>"
            f"<td class=type>{_e(_type(spec, p.get('schema', {})))}</td><td>{_e(p.get('description', ''))}</td></tr>"
            for p in params)
        parts.append(f"<table class=fields><tr><th>Parâmetro</th><th>Onde</th><th>Tipo</th><th>Descrição</th></tr>{rows}</table>")
    body = (op.get("requestBody") or {}).get("content", {}).get("application/json", {}).get("schema")
    if body:
        parts.append("<p class=label>Corpo (JSON)</p>" + _fields(spec, body))
    responses = op.get("responses") or {}
    ok = next((c for c in ("201", "200") if c in responses), None)
    if ok:
        schema = responses[ok].get("content", {}).get("application/json", {}).get("schema")
        if schema and schema.get("type") == "array":
            parts.append(f"<p class=label>Resposta {ok}: lista de</p>" + _fields(spec, schema.get("items")))
        elif schema:
            parts.append(f"<p class=label>Resposta {ok}</p>" + _fields(spec, schema))
    others = [f"<code>{_e(c)}</code> {_e(r.get('description', ''))}" for c, r in responses.items()
              if c not in ("200", "201", "422") and r.get("description")]
    if others:
        parts.append("<p class=other>" + " · ".join(others) + "</p>")
    parts.append("</div>")
    return "".join(parts)


def render(spec: dict) -> str:
    by_tag: dict[str, list] = {}
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            tag = (op.get("tags") or ["API pública"])[-1]
            by_tag.setdefault(tag, []).append((path, method, op))
    tags = [t for t in TAG_ORDER if t in by_tag] + sorted(t for t in by_tag if t not in TAG_ORDER)

    nav = "".join(f'<a href="#{key}">{_e(title)}</a>' for key, title, _ in GUIDE)
    nav += '<span class=navtitle>Referência</span>' + "".join(
        f'<a href="#ref-{_e(t.lower())}">{_e(t)}</a>' for t in tags)
    guide = "".join(f'<section id="{key}"><h2>{_e(title)}</h2>{body}</section>' for key, title, body in GUIDE)
    # the nested shapes (a rate, a line, a customer...): what «lista de Rate» means
    models = {name: schema for name, schema in sorted(spec.get("components", {}).get("schemas", {}).items())
              if schema.get("properties") and name not in ("HTTPValidationError", "ValidationError")}
    nav += '<a href="#modelos">Modelos</a>' if models else ""
    models_html = ('<section id="modelos"><h2>Modelos</h2><p>As estruturas que aparecem dentro das respostas e dos '
                   'pedidos (ex.: «lista de Rate»).</p>' + "".join(
                       f'<div class=op id="model-{_e(name)}"><h4><code>{_e(name)}</code></h4>{_fields(spec, schema)}</div>'
                       for name, schema in models.items()) + "</section>") if models else ""
    reference = "".join(
        f'<section id="ref-{_e(t.lower())}"><h2>{_e(t)}</h2>'
        + "".join(_operation(spec, p, m, op) for p, m, op in by_tag[t]) + "</section>" for t in tags)
    return f"""<!doctype html>
<html lang="pt"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>RM SOFT - API pública</title>
<style>
:root{{--bg:#fff;--fg:#1d2430;--muted:#5b6575;--line:#e2e6ec;--inset:#f5f7fa;--accent:#2f6fe4;--warn:#fff6e5;--warnl:#f0c36d}}
@media (prefers-color-scheme:dark){{:root{{--bg:#15191f;--fg:#e6e9ee;--muted:#9aa3b2;--line:#2a313b;--inset:#1c222a;--accent:#5b93f5;--warn:#2e2614;--warnl:#7a5c1e}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
nav{{position:fixed;top:0;bottom:0;left:0;width:240px;overflow:auto;padding:20px 16px;border-right:1px solid var(--line);background:var(--inset)}}
nav a{{display:block;color:var(--fg);text-decoration:none;padding:4px 8px;border-radius:6px;font-size:14px}}nav a:hover{{background:var(--line)}}
.navtitle{{display:block;margin:16px 8px 4px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}
main{{margin-left:240px;padding:28px 40px 80px;max-width:1040px}}
h1{{margin:0 0 4px;font-size:26px}}h2{{margin:40px 0 12px;font-size:21px;border-bottom:1px solid var(--line);padding-bottom:6px}}h4{{margin:18px 0 6px}}
a{{color:var(--accent)}}code{{font:13px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--inset);padding:1px 5px;border-radius:4px}}
pre{{background:var(--inset);border:1px solid var(--line);border-radius:8px;padding:12px 14px;overflow:auto}}pre code{{background:none;padding:0}}
table{{border-collapse:collapse;width:100%;margin:8px 0 12px;font-size:14px}}th,td{{border:1px solid var(--line);padding:6px 9px;text-align:left;vertical-align:top}}th{{background:var(--inset)}}
.warn{{background:var(--warn);border:1px solid var(--warnl);border-radius:8px;padding:10px 14px;margin:12px 0}}
.op{{border:1px solid var(--line);border-radius:10px;padding:4px 16px 8px;margin:14px 0}}.op h4{{display:flex;flex-wrap:wrap;align-items:center;gap:8px}}
.m{{font:700 12px ui-monospace,monospace;padding:3px 8px;border-radius:5px;color:#fff}}.m.get{{background:#2f6fe4}}.m.post{{background:#1f9d55}}.m.put{{background:#c98a12}}.m.delete{{background:#d64545}}
.sum{{font-weight:400;color:var(--muted)}}.label{{margin:10px 0 0;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}}
.req{{font-size:11px;color:#d64545}}.type{{font:12px ui-monospace,monospace;color:var(--muted)}}.other{{font-size:13px;color:var(--muted)}}
.top{{color:var(--muted);margin:0 0 20px}}
@media (max-width:820px){{nav{{position:static;width:auto;border-right:0;border-bottom:1px solid var(--line)}}main{{margin:0;padding:20px 16px 60px}}}}
</style></head><body>
<nav><b>RM SOFT · API pública</b><span class=navtitle>Guia</span>{nav}
<span class=navtitle>Outros</span><a href="{PREFIX}/openapi.json">openapi.json</a><a href="{PREFIX}/docs/experimentar">Experimentar (precisa de internet)</a></nav>
<main><h1>RM SOFT - API pública</h1>
<p class=top>Versão {_e(spec.get("info", {}).get("version", "1.0"))} · endereço base <code>{PREFIX}</code> · esta página funciona sem internet.</p>
{guide}
<h2 style="margin-top:56px">Referência</h2>
<p>Todas as operações, geradas a partir da própria API. Os caminhos começam por <code>{PREFIX}</code>.</p>
{reference}
{models_html}
</main></body></html>"""

