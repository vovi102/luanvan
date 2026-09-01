"""Generation seam shared by local test adapters and real model inference."""

from __future__ import annotations

from typing import Protocol

from nl2sparql.models.b12.contracts import ChatMessage, Completion, GenerationConfig


class GenerationBackend(Protocol):
    """Generate one completion from validated ordered chat messages."""

    def generate(
        self,
        messages: tuple[ChatMessage, ...],
        config: GenerationConfig,
    ) -> Completion:
        """Return raw text and accounting for one batch-one generation."""
