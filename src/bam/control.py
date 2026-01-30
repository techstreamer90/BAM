"""
BAM Control Manager

Manages per-project control.json files that configure LLM providers,
model selection per task/source, and operational settings.
"""

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bam.control")

CONTROL_FILENAME = "control.json"

# Default model configurations
DEFAULT_MODELS = {
    "claude": {
        "agent-review": "claude-sonnet-4-20250514",
        "transform-fallback": "claude-haiku-4-20250514",
        "verification": "claude-haiku-4-20250514",
    },
    "copilot": {
        "agent-review": "",  # Copilot auto-routes
        "transform-fallback": "",
        "verification": "",
    },
    "spawnie": {
        "agent-review": "claude-sonnet",      # Spawnie routes to best available
        "transform-fallback": "claude-haiku", # Cost-effective for fallback
        "verification": "claude-haiku",       # Cost-effective for verification
    },
    "mock": {
        "agent-review": "mock-v1",
        "transform-fallback": "mock-v1",
        "verification": "mock-v1",
    },
}

# Task types that can have different models
TASK_TYPES = [
    "agent-review",       # Schema analysis and transform planning
    "transform-fallback", # Fallback for unmatched items
    "verification",       # Consistency checks
]


@dataclass
class ModelConfig:
    """Configuration for a specific model assignment."""
    model: str
    temperature: float = 0.0
    max_tokens: int = 4096
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ModelConfig":
        return cls(
            model=d.get("model", ""),
            temperature=d.get("temperature", 0.0),
            max_tokens=d.get("max_tokens", 4096),
            description=d.get("description", ""),
        )


@dataclass
class CredentialConfig:
    """Configuration for how to access credentials."""
    source: str = "env"  # "env" or "keyring" (future)
    env_var: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CredentialConfig":
        return cls(
            source=d.get("source", "env"),
            env_var=d.get("env_var", ""),
        )


@dataclass
class LLMControlConfig:
    """LLM configuration section of control.json."""
    provider: str = "claude"
    credentials: CredentialConfig = field(default_factory=CredentialConfig)
    models_by_task: Dict[str, ModelConfig] = field(default_factory=dict)
    models_by_source: Dict[str, Dict[str, ModelConfig]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "credentials": self.credentials.to_dict(),
            "models_by_task": {k: v.to_dict() for k, v in self.models_by_task.items()},
            "models_by_source": {
                src: {task: cfg.to_dict() for task, cfg in tasks.items()}
                for src, tasks in self.models_by_source.items()
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LLMControlConfig":
        models_by_task = {}
        for task, cfg in d.get("models_by_task", {}).items():
            models_by_task[task] = ModelConfig.from_dict(cfg)

        models_by_source = {}
        for src, tasks in d.get("models_by_source", {}).items():
            models_by_source[src] = {}
            for task, cfg in tasks.items():
                models_by_source[src][task] = ModelConfig.from_dict(cfg)

        return cls(
            provider=d.get("provider", "claude"),
            credentials=CredentialConfig.from_dict(d.get("credentials", {})),
            models_by_task=models_by_task,
            models_by_source=models_by_source,
        )


@dataclass
class ControlConfig:
    """Full control.json configuration."""
    version: str = "1.0.0"
    llm: LLMControlConfig = field(default_factory=LLMControlConfig)
    security: Dict[str, Any] = field(default_factory=lambda: {
        "allow_key_in_file": False,
        "require_env_var": True,
    })
    defaults: Dict[str, Any] = field(default_factory=lambda: {
        "pipeline": "agent-driven",
        "snapshot_before_ingest": True,
    })

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "llm": self.llm.to_dict(),
            "security": self.security,
            "defaults": self.defaults,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ControlConfig":
        return cls(
            version=d.get("version", "1.0.0"),
            llm=LLMControlConfig.from_dict(d.get("llm", {})),
            security=d.get("security", {"allow_key_in_file": False, "require_env_var": True}),
            defaults=d.get("defaults", {"pipeline": "agent-driven", "snapshot_before_ingest": True}),
        )


class ControlManager:
    """Manages per-project control.json files."""

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self._control_path = self.project_dir / CONTROL_FILENAME
        self._config: Optional[ControlConfig] = None

    @property
    def control_path(self) -> Path:
        return self._control_path

    def exists(self) -> bool:
        """Check if control.json exists for this project."""
        return self._control_path.exists()

    def load(self) -> ControlConfig:
        """Load control.json, creating default if not exists."""
        if self._config is not None:
            return self._config

        if self._control_path.exists():
            with open(self._control_path, "r") as f:
                data = json.load(f)
            self._config = ControlConfig.from_dict(data)
        else:
            self._config = self._create_default()

        return self._config

    def save(self, config: Optional[ControlConfig] = None):
        """Save control.json."""
        if config is not None:
            self._config = config

        if self._config is None:
            self._config = self._create_default()

        with open(self._control_path, "w") as f:
            json.dump(self._config.to_dict(), f, indent=2)

        logger.info("Saved control.json to %s", self._control_path)

    def _create_default(self) -> ControlConfig:
        """Create default control configuration."""
        # Try to detect provider from global config or environment
        provider = self._detect_provider()

        # Set up default models for the provider
        models_by_task = {}
        defaults = DEFAULT_MODELS.get(provider, DEFAULT_MODELS["mock"])

        for task in TASK_TYPES:
            model = defaults.get(task, "")
            models_by_task[task] = ModelConfig(
                model=model,
                description=self._task_description(task),
            )

        # Set up credentials
        credentials = CredentialConfig(
            source="env",
            env_var=self._default_env_var(provider),
        )

        llm_config = LLMControlConfig(
            provider=provider,
            credentials=credentials,
            models_by_task=models_by_task,
            models_by_source={},
        )

        return ControlConfig(llm=llm_config)

    def _detect_provider(self) -> str:
        """Detect which provider to use based on global config or environment."""
        # Check global config
        from .llm.factory import load_global_config
        global_config = load_global_config()
        if global_config.get("llm", {}).get("provider"):
            return global_config["llm"]["provider"]

        # Check environment variables
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "claude"

        # Default to mock for safety
        return "mock"

    def _default_env_var(self, provider: str) -> str:
        """Get the default environment variable for a provider."""
        return {
            "claude": "ANTHROPIC_API_KEY",
            "copilot": "GITHUB_TOKEN",
            "spawnie": "",  # Spawnie routes to CLIs, no direct API key needed
            "mock": "",
        }.get(provider, "")

    def _task_description(self, task: str) -> str:
        """Get description for a task type."""
        return {
            "agent-review": "Schema analysis and transform planning",
            "transform-fallback": "Fallback for unmatched items (cost-effective)",
            "verification": "Consistency and validation checks",
        }.get(task, "")

    def get_model_for_task(
        self,
        task_type: str,
        source_type: Optional[str] = None,
    ) -> ModelConfig:
        """Get the model configuration for a specific task.

        Resolution order:
        1. Source-specific model (if source_type provided)
        2. Task-specific model
        3. Default model for provider
        """
        config = self.load()

        # Check source-specific override
        if source_type and source_type in config.llm.models_by_source:
            source_models = config.llm.models_by_source[source_type]
            if task_type in source_models:
                return source_models[task_type]

        # Check task-specific model
        if task_type in config.llm.models_by_task:
            return config.llm.models_by_task[task_type]

        # Fall back to provider default
        provider = config.llm.provider
        defaults = DEFAULT_MODELS.get(provider, DEFAULT_MODELS["mock"])
        model = defaults.get(task_type, defaults.get("agent-review", ""))

        return ModelConfig(model=model)

    def set_model_for_task(
        self,
        task_type: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        source_type: Optional[str] = None,
    ):
        """Set the model for a specific task (optionally per-source)."""
        config = self.load()

        model_config = ModelConfig(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            description=self._task_description(task_type),
        )

        if source_type:
            if source_type not in config.llm.models_by_source:
                config.llm.models_by_source[source_type] = {}
            config.llm.models_by_source[source_type][task_type] = model_config
        else:
            config.llm.models_by_task[task_type] = model_config

        self.save(config)

    def get_credential(self) -> Optional[str]:
        """Get the API credential based on configuration."""
        config = self.load()
        creds = config.llm.credentials

        if creds.source == "env":
            if creds.env_var:
                return os.environ.get(creds.env_var)
            # Try default env var for provider
            default_var = self._default_env_var(config.llm.provider)
            return os.environ.get(default_var)

        # Future: support keyring
        return None

    def validate(self) -> Dict[str, Any]:
        """Validate the control configuration.

        Returns a dict with 'valid' bool and 'errors'/'warnings' lists.
        """
        config = self.load()
        errors = []
        warnings = []

        # Check provider is valid
        valid_providers = ["claude", "copilot", "spawnie", "mock"]
        if config.llm.provider not in valid_providers:
            errors.append(f"Unknown provider: {config.llm.provider}")

        # Check credentials
        if config.llm.provider != "mock":
            cred = self.get_credential()
            if not cred:
                env_var = config.llm.credentials.env_var or self._default_env_var(config.llm.provider)
                errors.append(f"Credential not found. Set {env_var} environment variable.")

        # Check models are specified
        for task in TASK_TYPES:
            model_cfg = self.get_model_for_task(task)
            if not model_cfg.model and config.llm.provider != "copilot":
                warnings.append(f"No model specified for task '{task}'")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def show(self) -> str:
        """Return a human-readable view of the control configuration."""
        config = self.load()
        validation = self.validate()

        lines = [
            "=== Project Control Configuration ===",
            f"Version: {config.version}",
            "",
            "LLM Provider:",
            f"  Provider: {config.llm.provider}",
            f"  Credentials: {config.llm.credentials.source} ({config.llm.credentials.env_var or 'default'})",
            "",
            "Models by Task:",
        ]

        for task in TASK_TYPES:
            model_cfg = self.get_model_for_task(task)
            lines.append(f"  {task}: {model_cfg.model or '(not set)'}")

        if config.llm.models_by_source:
            lines.append("")
            lines.append("Models by Source:")
            for src, tasks in config.llm.models_by_source.items():
                lines.append(f"  {src}:")
                for task, cfg in tasks.items():
                    lines.append(f"    {task}: {cfg.model}")

        lines.append("")
        lines.append("Defaults:")
        for key, value in config.defaults.items():
            lines.append(f"  {key}: {value}")

        if not validation["valid"]:
            lines.append("")
            lines.append("Errors:")
            for err in validation["errors"]:
                lines.append(f"  [!] {err}")

        if validation["warnings"]:
            lines.append("")
            lines.append("Warnings:")
            for warn in validation["warnings"]:
                lines.append(f"  [?] {warn}")

        return "\n".join(lines)


def create_env_example(project_dir: str, provider: str = "claude") -> Path:
    """Create a .env.example file showing required environment variables."""
    env_vars = {
        "claude": "ANTHROPIC_API_KEY=sk-ant-api03-your-key-here",
        "copilot": "# GitHub Copilot uses gh CLI authentication\n# Ensure you're logged in: gh auth login",
        "spawnie": "# Spawnie routes to CLI agents - no direct API key needed\n# Ensure Claude CLI or Copilot CLI is installed and authenticated\n# Run 'spawnie models' to see available routes",
        "mock": "# No credentials required for mock provider",
    }

    content = f"""# BAM Environment Variables
# Copy this file to .env and fill in your values
# NEVER commit .env to version control!

# LLM Provider Credentials
{env_vars.get(provider, env_vars["claude"])}

# Optional: Override default models
# BAM_MODEL_AGENT_REVIEW=claude-sonnet-4-20250514
# BAM_MODEL_TRANSFORM=claude-haiku-4-20250514
"""

    env_path = Path(project_dir) / ".env.example"
    env_path.write_text(content)

    # Also create/update .gitignore to exclude .env
    gitignore_path = Path(project_dir) / ".gitignore"
    gitignore_content = ""
    if gitignore_path.exists():
        gitignore_content = gitignore_path.read_text()

    if ".env" not in gitignore_content:
        with open(gitignore_path, "a") as f:
            f.write("\n# Environment files with secrets\n.env\n.env.local\n")

    return env_path
