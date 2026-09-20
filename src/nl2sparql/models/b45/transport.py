"""Async completion seam for B4/B5 local and remote adapters."""

from __future__ import annotations

from typing import Protocol

from nl2sparql.models.b12.contracts import ChatMessage
from nl2sparql.models.b45.contracts import LargeLLMConfig, RemoteCompletion


class CompletionTransport(Protocol):
    """Complete one ordered chat prompt through a local or remote adapter."""

    async def complete(
        self,
        messages: tuple[ChatMessage, ...],
        config: LargeLLMConfig,
        *,
        request_id: str,
    ) -> RemoteCompletion:
        """Return validated response and accounting evidence."""
