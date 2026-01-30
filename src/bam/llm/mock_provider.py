"""Mock LLM provider for testing without API calls."""

import json
import logging
import re
from typing import List

from .provider import LLMMessage, LLMProvider, LLMResponse

logger = logging.getLogger("bam.llm.mock")


class MockProvider(LLMProvider):
    """Mock LLM provider that returns predictable responses.

    Useful for testing and development without consuming API credits.
    The mock provider attempts to generate sensible responses based on
    the input, particularly for BAM's agent-review prompts.
    """

    def __init__(self, model: str = "mock-v1"):
        self._model = model

    def complete(self, messages: List[LLMMessage], system_prompt: str = "",
                 max_tokens: int = 4096, temperature: float = 0.0) -> LLMResponse:
        # Get the last user message
        user_content = ""
        for msg in reversed(messages):
            if msg.role == "user":
                user_content = msg.content
                break

        # Generate response based on content
        response_content = self._generate_response(user_content, system_prompt)

        return LLMResponse(
            content=response_content,
            model=self._model,
            usage={"input_tokens": len(user_content) // 4, "output_tokens": len(response_content) // 4},
            raw=None,
        )

    def _generate_response(self, user_content: str, system_prompt: str) -> str:
        """Generate a mock response based on the input."""

        # Handle test connection requests
        if "respond with" in user_content.lower() and "ok" in user_content.lower():
            return "OK"

        # Handle BAM agent-review prompts (detect by looking for sketch summary)
        if "=== Current Sketch Summary ===" in user_content or "Source ID:" in user_content:
            return self._generate_transform_plan(user_content)

        # Handle LLM fallback for unmatched items
        if "did not match any mapping" in user_content.lower():
            return self._generate_fallback_nodes(user_content)

        # Default response
        return json.dumps({"status": "ok", "message": "Mock response"})

    def _generate_transform_plan(self, content: str) -> str:
        """Generate a mock transform plan for agent-review stage."""
        # Extract source ID if present
        source_id = "mock-source"
        match = re.search(r"Source ID:\s*(\S+)", content)
        if match:
            source_id = match.group(1)

        # Create a basic transform plan
        plan = {
            "transformPlan": {
                "sourceId": source_id,
                "nodeMappings": [
                    {
                        "sourceField": "items",
                        "nodeType": "Item",
                        "idPattern": "{source_id}-{item.id}",
                        "labelField": "name",
                        "propertyFields": ["status", "description"]
                    }
                ],
                "edgeMappings": [
                    {
                        "sourceField": "items[*].relationships",
                        "edgeType": "RELATES_TO",
                        "sourceNodePattern": "{source_id}-{item.id}",
                        "targetNodePattern": "{source_id}-{rel.targetId}"
                    }
                ],
                "filters": [],
                "metadata": {"mock": True}
            },
            "sketchChanges": None
        }
        return json.dumps(plan, indent=2)

    def _generate_fallback_nodes(self, content: str) -> str:
        """Generate mock nodes for LLM fallback."""
        # Return an empty list - in real use, items would be processed
        return json.dumps([])

    def is_available(self) -> bool:
        """Mock provider is always available."""
        return True
