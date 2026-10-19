"""
The call to the AI provider chosen by the SUPER_ADMIN - OpenAI, Anthropic or OpenRouter - behind one function, so the
rest of the assistant never depends on the provider. OpenAI and OpenRouter share the same format.
"""
import httpx

PROVIDERS = {
    "OPENAI": "OpenAI",
    "ANTHROPIC": "Anthropic",
    "OPENROUTER": "OpenRouter",
}
_OPENAI_LIKE_URLS = {
    "OPENAI": "https://api.openai.com/v1/chat/completions",
    "OPENROUTER": "https://openrouter.ai/api/v1/chat/completions",
}
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


class AiProviderError(Exception):
    """The provider could not answer - the message is shown as it is (PT-PT)."""


async def complete(provider: str, model: str, api_key: str, system: str, messages: list[dict],
                   max_tokens: int = 1024, timeout: float = 60) -> str:
    """The provider's text answer. messages: [{"role": "user" | "assistant", "content": str}]."""
    if provider not in PROVIDERS:
        raise AiProviderError("Fornecedor de IA desconhecido")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if provider == "ANTHROPIC":
                response = await client.post(
                    _ANTHROPIC_URL,
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                    json={"model": model, "max_tokens": max_tokens, "system": system, "messages": messages},
                )
            else:
                response = await client.post(
                    _OPENAI_LIKE_URLS[provider],
                    headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
                    json={"model": model, "max_tokens": max_tokens,
                          "messages": [{"role": "system", "content": system}, *messages]},
                )
    except httpx.TimeoutException:
        raise AiProviderError("O fornecedor de IA não respondeu a tempo")
    except httpx.HTTPError:
        raise AiProviderError("Sem ligação ao fornecedor de IA - verifique a ligação à internet")
    if response.status_code in (401, 403):
        raise AiProviderError("Chave de acesso recusada pelo fornecedor de IA")
    if response.status_code == 404:
        raise AiProviderError(f"Modelo «{model}» não encontrado neste fornecedor")
    if response.status_code == 429:
        raise AiProviderError("Limite ou crédito do fornecedor de IA esgotado - tente mais tarde")
    if response.status_code >= 400:
        raise AiProviderError(f"O fornecedor de IA recusou o pedido (erro {response.status_code}): {_error_text(response)}")
    data = response.json()
    try:
        if provider == "ANTHROPIC":
            return "".join(block.get("text", "") for block in data["content"] if block.get("type") == "text").strip()
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        raise AiProviderError("Resposta do fornecedor de IA incompreensível")


def _error_text(response: httpx.Response) -> str:
    try:
        data = response.json()
        error = data.get("error")
        if isinstance(error, dict):
            return str(error.get("message", ""))[:200]
        return str(error or data)[:200]
    except ValueError:
        return response.text[:200]


# ---------- Conversation with tools
#
# A neutral transcript, turned into each provider's format here:
#   {"role": "user", "content": str}
#   {"role": "assistant", "content": str, "tool_calls": [{"id", "name", "arguments": dict}], "extra": dict}
#   {"role": "tool", "tool_call_id": str, "name": str, "content": str}
# "extra" carries what a provider asks to be sent back as it came (OpenRouter's reasoning_details for Gemini).
# Tools: [{"name", "description", "parameters": JSON schema}].

class ProviderReply:
    """The provider's answer: its text, and the tools it asks to run (empty when it has answered)."""

    def __init__(self, text: str, tool_calls: list[dict], extra: dict | None = None):
        self.text, self.tool_calls, self.extra = text, tool_calls, extra or {}


def _openai_messages(system: str, transcript: list[dict]) -> list[dict]:
    import json
    out = [{"role": "system", "content": system}]
    for item in transcript:
        if item["role"] == "assistant" and item.get("tool_calls"):
            out.append({
                "role": "assistant", "content": item.get("content") or None,
                "tool_calls": [{"id": c["id"], "type": "function",
                                "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)}}
                               for c in item["tool_calls"]],
                **(item.get("extra") or {}),
            })
        elif item["role"] == "tool":
            out.append({"role": "tool", "tool_call_id": item["tool_call_id"], "content": item["content"]})
        else:
            out.append({"role": item["role"], "content": item["content"]})
    return out


def _anthropic_messages(transcript: list[dict]) -> list[dict]:
    out: list[dict] = []
    for item in transcript:
        if item["role"] == "assistant":
            blocks = [{"type": "text", "text": item["content"]}] if item.get("content") else []
            blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["arguments"]}
                       for c in item.get("tool_calls") or []]
            out.append({"role": "assistant", "content": blocks or item.get("content", "")})
        elif item["role"] == "tool":
            result = {"type": "tool_result", "tool_use_id": item["tool_call_id"], "content": item["content"]}
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(result)  # the results of one turn go together
            else:
                out.append({"role": "user", "content": [result]})
        else:
            out.append({"role": "user", "content": item["content"]})
    return out


async def chat(provider: str, model: str, api_key: str, system: str, transcript: list[dict], tools: list[dict],
               max_tokens: int = 2000, timeout: float = 90) -> ProviderReply:
    """One turn of the conversation: the provider answers or asks for tools."""
    import json
    if provider not in PROVIDERS:
        raise AiProviderError("Fornecedor de IA desconhecido")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if provider == "ANTHROPIC":
                body = {"model": model, "max_tokens": max_tokens, "system": system,
                        "messages": _anthropic_messages(transcript)}
                if tools:
                    body["tools"] = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                                     for t in tools]
                response = await client.post(
                    _ANTHROPIC_URL, json=body,
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                )
            else:
                body = {"model": model, "max_tokens": max_tokens, "messages": _openai_messages(system, transcript)}
                if tools:
                    body["tools"] = [{"type": "function", "function": t} for t in tools]
                response = await client.post(
                    _OPENAI_LIKE_URLS[provider], json=body,
                    headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
                )
    except httpx.TimeoutException:
        raise AiProviderError("O fornecedor de IA não respondeu a tempo")
    except httpx.HTTPError:
        raise AiProviderError("Sem ligação ao fornecedor de IA - verifique a ligação à internet")
    if response.status_code in (401, 403):
        raise AiProviderError("Chave de acesso recusada pelo fornecedor de IA")
    if response.status_code == 404:
        raise AiProviderError(f"Modelo «{model}» não encontrado neste fornecedor")
    if response.status_code == 429:
        raise AiProviderError("Limite ou crédito do fornecedor de IA esgotado - tente mais tarde")
    if response.status_code >= 400:
        raise AiProviderError(f"O fornecedor de IA recusou o pedido (erro {response.status_code}): {_error_text(response)}")
    data = response.json()
    try:
        if provider == "ANTHROPIC":
            text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text").strip()
            calls = [{"id": b["id"], "name": b["name"], "arguments": b.get("input") or {}}
                     for b in data["content"] if b.get("type") == "tool_use"]
            return ProviderReply(text, calls)
        message = data["choices"][0]["message"]
        calls = []
        for c in message.get("tool_calls") or []:
            raw = c["function"].get("arguments") or "{}"
            try:
                arguments = json.loads(raw) if isinstance(raw, str) else raw
            except ValueError:
                arguments = {}
            calls.append({"id": c.get("id") or c["function"]["name"], "name": c["function"]["name"],
                          "arguments": arguments if isinstance(arguments, dict) else {}})
        extra = {"reasoning_details": message["reasoning_details"]} if message.get("reasoning_details") else {}
        return ProviderReply((message.get("content") or "").strip(), calls, extra)
    except (KeyError, IndexError, TypeError):
        raise AiProviderError("Resposta do fornecedor de IA incompreensível")
