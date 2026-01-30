"""LLM provider factory and global configuration."""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from .provider import LLMProvider

logger = logging.getLogger("bam.llm.factory")

GLOBAL_CONFIG_PATH = Path.home() / ".bam" / "config.json"

# Supported providers and their descriptions
SUPPORTED_PROVIDERS = {
    "claude": "Anthropic Claude API (requires ANTHROPIC_API_KEY)",
    "copilot": "GitHub Copilot SDK (requires Copilot CLI + subscription)",
    "spawnie": "Spawnie router (routes to CLI agents - no API costs)",
    "mock": "Mock provider for testing (no API calls)",
}


def load_global_config() -> dict:
    """Load the global BAM configuration from ~/.bam/config.json."""
    if GLOBAL_CONFIG_PATH.exists():
        with open(GLOBAL_CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}


def save_global_config(config: dict):
    """Save the global BAM configuration to ~/.bam/config.json."""
    GLOBAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GLOBAL_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def get_llm_provider(
    provider_name: Optional[str] = None,
    task_type: Optional[str] = None,
    source_type: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> LLMProvider:
    """Get a configured LLM provider.

    Supported providers:
    - claude: Anthropic Claude API (default if ANTHROPIC_API_KEY is set)
    - copilot: GitHub Copilot SDK (requires Copilot CLI)
    - mock: Mock provider for testing without API calls

    Resolution order for provider:
    1. Explicit provider_name argument
    2. Project control.json (if project_dir provided)
    3. Global config (~/.bam/config.json)
    4. Environment variable fallback (ANTHROPIC_API_KEY -> claude)

    Resolution order for model:
    1. Source-specific model (if source_type and project_dir provided)
    2. Task-specific model (if task_type and project_dir provided)
    3. Global config model
    4. Provider default

    Args:
        provider_name: Explicit provider to use.
        task_type: Task type for model selection (e.g., "agent-review").
        source_type: Source type for model selection (e.g., "jama", "codebase").
        project_dir: Project directory to load control.json from.

    Returns:
        Configured LLMProvider instance.

    Raises:
        ValueError: If the provider is unknown or not configured.
    """
    config = load_global_config()
    llm_config = config.get("llm", {})

    name = provider_name or llm_config.get("provider", "")
    api_key = llm_config.get("api_key", "")
    model = llm_config.get("model", "")

    # Try to load project control.json for per-task/per-source model selection
    control_manager = None
    if project_dir:
        try:
            from ..control import ControlManager
            control_manager = ControlManager(project_dir)
            if control_manager.exists():
                control_config = control_manager.load()
                # Use project provider if not explicitly specified
                if not provider_name:
                    name = control_config.llm.provider or name
                # Get model for task/source
                if task_type or source_type:
                    model_config = control_manager.get_model_for_task(
                        task_type or "agent-review",
                        source_type=source_type,
                    )
                    if model_config.model:
                        model = model_config.model
        except Exception as e:
            logger.debug("Could not load control.json: %s", e)

    # Fallback: if no provider configured but ANTHROPIC_API_KEY exists, use claude
    if not name and os.environ.get("ANTHROPIC_API_KEY"):
        name = "claude"

    # Default to mock if nothing else is configured (for testing)
    if not name:
        name = "mock"
        logger.warning("No LLM provider configured, using mock provider")

    if name == "claude":
        from .claude_provider import ClaudeProvider
        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        if model:
            kwargs["model"] = model
        return ClaudeProvider(**kwargs)

    if name == "copilot":
        from .copilot_provider import CopilotProvider
        kwargs = {}
        if model:
            kwargs["model"] = model
        return CopilotProvider(**kwargs)

    if name == "mock":
        from .mock_provider import MockProvider
        kwargs = {}
        if model:
            kwargs["model"] = model
        return MockProvider(**kwargs)

    if name == "spawnie":
        from .spawnie_provider import SpawnieProvider
        kwargs = {}
        if model:
            kwargs["model"] = model
        # Get spawnie-specific config from control.json if available
        if control_manager and control_manager.exists():
            try:
                control_config = control_manager.load()
                spawnie_config = control_config.get("spawnie", {})
                if spawnie_config.get("mode"):
                    kwargs["mode"] = spawnie_config["mode"]
                if spawnie_config.get("timeout"):
                    kwargs["timeout"] = spawnie_config["timeout"]
            except Exception:
                pass
        return SpawnieProvider(**kwargs)

    providers_list = ", ".join(SUPPORTED_PROVIDERS.keys())
    raise ValueError(
        f"Unknown LLM provider: {name!r}. "
        f"Supported providers: {providers_list}. "
        "Configure with: bam setup llm --provider <name>"
    )


def list_providers() -> dict:
    """Return a dict of supported providers and their descriptions."""
    return dict(SUPPORTED_PROVIDERS)
