"""Groq LLM adapter for low-latency JSON schema completion."""

import json
from typing import Any

import httpx
from app.voice.interfaces import LLMClient


class GroqLLMAdapter(LLMClient):
    """Groq LLM adapter running small models at temperature 0 with JSON object format."""

    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient | None = None,
        base_url: str = "https://api.groq.com/openai/v1",
        model: str = "qwen/qwen3.8-27b",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None

    async def complete_json(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
            "max_tokens": 256,
        }

        response = await self._client.post(url, headers=headers, json=body)
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        result: dict[str, Any] = json.loads(content)
        return result

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
