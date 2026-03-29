"""
Anthropic API wrapper with async streaming support.

Uses AsyncAnthropic so streaming never blocks the Textual event loop —
tokens arrive and render immediately without freezing the UI.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import anthropic

if TYPE_CHECKING:
    from devflow.config import Config


class DevflowClient:
    def __init__(self, config: "Config"):
        self._client = anthropic.AsyncAnthropic(api_key=config.api_key)
        self.model = config.model

    async def stream(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 8096,
    ) -> AsyncIterator[str]:
        """
        Async-yield text tokens as they arrive from the API.
        Non-blocking — the Textual event loop stays responsive during streaming.
        """
        kwargs: dict = dict(
            model=self.model,
            max_tokens=max_tokens,
            messages=messages,
        )
        if system:
            kwargs["system"] = system

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    async def complete(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 8096,
    ) -> str:
        """Non-streaming completion. Returns the full response text."""
        parts = []
        async for token in self.stream(messages, system=system, max_tokens=max_tokens):
            parts.append(token)
        return "".join(parts)
