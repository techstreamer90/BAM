"""Claude LLM provider using the Anthropic SDK."""

import logging
import os
from typing import List, Optional

from .provider import LLMMessage, LLMProvider, LLMResponse

logger = logging.getLogger("bam.llm.claude")

DEFAULT_MODEL = "claude-sonnet-4-20250514"


class ClaudeProvider(LLMProvider):
    """LLM provider backed by the Anthropic Claude API."""

    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "The 'anthropic' package is required for the Claude provider. "
                    "Install it with: pip install bam-model[llm]"
                )
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def complete(self, messages: List[LLMMessage], system_prompt: str = "",
                 max_tokens: int = 4096, temperature: float = 0.0) -> LLMResponse:
        client = self._get_client()

        api_messages = [{"role": m.role, "content": m.content} for m in messages]

        kwargs = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": api_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = client.messages.create(**kwargs)

        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        return LLMResponse(
            content=content,
            model=response.model,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            raw=response,
        )

    def is_available(self) -> bool:
        return bool(self._api_key)
