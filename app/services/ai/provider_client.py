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
