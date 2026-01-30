"""Spawnie LLM provider - routes to CLI agents via Spawnie.

Spawnie is a model router that sends prompts to CLI agents (Claude CLI,
GitHub Copilot CLI) instead of making direct API calls. This saves API
costs by leveraging existing CLI subscriptions.

Configuration:
    In control.json:
    {
        "llm": {
            "provider": "spawnie",
            "spawnie": {
                "model": "claude-sonnet",    // Model to request from Spawnie
                "mode": "blocking",          // "blocking", "async", or "output"
                "timeout": 300               // Timeout in seconds
            }
        }
    }

    Or globally in ~/.bam/config.json:
    {
        "llm": {
            "provider": "spawnie",
            "model": "claude-sonnet"
        }
    }

Spawnie handles the routing - it will find the best available provider
(CLI subscription, API key fallback, etc.) for the requested model.
"""

import logging
from typing import List, Optional

from .provider import LLMMessage, LLMProvider, LLMResponse, TestResult

logger = logging.getLogger("bam.llm.spawnie")

# Check if spawnie is available
try:
    import spawnie
    SPAWNIE_AVAILABLE = True
except ImportError:
    SPAWNIE_AVAILABLE = False
    spawnie = None


class SpawnieProvider(LLMProvider):
    """LLM provider that routes through Spawnie to CLI agents.

    Spawnie routes model requests to the best available provider:
    1. Claude CLI (if installed and logged in)
    2. Copilot CLI (if installed and logged in)
    3. API fallback (if API key configured)

    This allows using existing CLI subscriptions to avoid API costs.
    """

    def __init__(
        self,
        model: str = "claude-sonnet",
        mode: str = "blocking",
        timeout: int = 300,
    ):
        """Initialize the Spawnie provider.

        Args:
            model: Model name to request from Spawnie (e.g., "claude-sonnet",
                   "claude-opus", "claude-haiku"). Spawnie will route to the
                   best available provider for this model.
            mode: Execution mode - "blocking" (wait for result), "async"
                  (return task ID), or "output" (write to directory).
            timeout: Timeout in seconds for blocking mode.
        """
        if not SPAWNIE_AVAILABLE:
            raise ImportError(
                "Spawnie package not installed. Install with: pip install spawnie\n"
                "Or from local source: pip install -e C:/spawnie"
            )

        self._model = model
        self._mode = mode
        self._timeout = timeout
        self._registry = spawnie.get_registry()

    def complete(
        self,
        messages: List[LLMMessage],
        system_prompt: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """Send messages to LLM via Spawnie routing.

        Spawnie will route to the best available provider for the configured
        model. The prompt is constructed from the messages and system prompt.
        """
        # Build the prompt from messages
        prompt_parts = []

        if system_prompt:
            prompt_parts.append(f"<system>\n{system_prompt}\n</system>\n")

        for msg in messages:
            if msg.role == "user":
                prompt_parts.append(f"<user>\n{msg.content}\n</user>")
            elif msg.role == "assistant":
                prompt_parts.append(f"<assistant>\n{msg.content}\n</assistant>")

        full_prompt = "\n".join(prompt_parts)

        # Add generation parameters as metadata
        metadata = {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "source": "bam",
        }

        # Run through Spawnie
        result = spawnie.run(
            full_prompt,
            model=self._model,
            mode=self._mode,
            timeout=self._timeout,
            metadata=metadata,
        )

        # Handle async mode (returns task_id string)
        if isinstance(result, str):
            # Wait for the result
            result = spawnie.wait_for_result(result, timeout=self._timeout)

        # Check for errors
        if not result.succeeded:
            error_msg = result.error or "Unknown error from Spawnie"
            raise RuntimeError(f"Spawnie execution failed: {error_msg}")

        # Get the actual model used (from Spawnie's routing)
        actual_model = self._model
        if hasattr(result, "metadata") and result.metadata:
            actual_model = result.metadata.get("model", self._model)

        # Estimate token usage (Spawnie doesn't track this directly)
        input_tokens = len(full_prompt) // 4
        output_tokens = len(result.output or "") // 4

        return LLMResponse(
            content=result.output or "",
            model=f"spawnie:{actual_model}",
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
            raw=result,
        )

    def is_available(self) -> bool:
        """Check if Spawnie has an available route for the configured model."""
        if not SPAWNIE_AVAILABLE:
            return False

        try:
            route = self._registry.get_best_route(self._model)
            return route is not None
        except Exception as e:
            logger.debug("Spawnie availability check failed: %s", e)
            return False

    def test_connection(self) -> TestResult:
        """Test the Spawnie connection."""
        if not SPAWNIE_AVAILABLE:
            return TestResult(
                success=False,
                message="Spawnie package not installed",
                provider="SpawnieProvider",
            )

        # Check if model is available
        route = self._registry.get_best_route(self._model)
        if not route:
            available_models = [
                m["name"] for m in spawnie.list_models() if m["available"]
            ]
            return TestResult(
                success=False,
                message=(
                    f"No route available for model '{self._model}'. "
                    f"Available models: {', '.join(available_models) or 'none'}"
                ),
                provider="SpawnieProvider",
            )

        route_info, provider_config = route

        # Run a test prompt
        try:
            result = spawnie.run(
                "Respond with exactly: OK",
                model=self._model,
                mode="blocking",
                timeout=30,
            )

            if result.succeeded and "OK" in (result.output or "").upper():
                return TestResult(
                    success=True,
                    message=f"Connected via {provider_config.type}:{route_info.provider}",
                    provider="SpawnieProvider",
                    model=f"spawnie:{self._model}",
                    usage={"input_tokens": 5, "output_tokens": 1},
                )
            elif result.succeeded:
                return TestResult(
                    success=True,
                    message=f"Connected (unexpected response: {(result.output or '')[:30]})",
                    provider="SpawnieProvider",
                    model=f"spawnie:{self._model}",
                )
            else:
                return TestResult(
                    success=False,
                    message=f"Spawnie returned error: {result.error}",
                    provider="SpawnieProvider",
                )
        except Exception as e:
            return TestResult(
                success=False,
                message=f"Spawnie test failed: {e}",
                provider="SpawnieProvider",
            )

    def get_tracker_status(self) -> dict:
        """Get current status from Spawnie's tracker.

        This is useful for monitoring active workflows and tasks.
        Returns status dict with workflow/task counts and active items.
        """
        if not SPAWNIE_AVAILABLE:
            return {"error": "Spawnie not available"}

        return spawnie.workflow_status()

    def list_available_models(self) -> list:
        """List all models available through Spawnie.

        Returns list of dicts with name, available, route info.
        """
        if not SPAWNIE_AVAILABLE:
            return []

        return spawnie.list_models()
