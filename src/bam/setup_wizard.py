"""
BAM Setup Wizard

Interactive setup wizard for first-time users to configure LLM providers,
credentials, and model preferences.
"""

import os
import sys
from pathlib import Path
from typing import Optional

from .llm.factory import (
    GLOBAL_CONFIG_PATH,
    SUPPORTED_PROVIDERS,
    load_global_config,
    save_global_config,
    get_llm_provider,
)
from .control import (
    ControlConfig,
    ControlManager,
    CredentialConfig,
    LLMControlConfig,
    ModelConfig,
    TASK_TYPES,
    DEFAULT_MODELS,
    create_env_example,
)


# ANSI colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

    @classmethod
    def disable(cls):
        """Disable colors (e.g., for non-TTY output)."""
        cls.HEADER = cls.BLUE = cls.CYAN = cls.GREEN = ''
        cls.YELLOW = cls.RED = cls.ENDC = cls.BOLD = ''


# Disable colors if not a TTY
if not sys.stdout.isatty():
    Colors.disable()


def print_header(text: str):
    """Print a header line."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}=== {text} ==={Colors.ENDC}\n")


def print_success(text: str):
    """Print a success message."""
    print(f"{Colors.GREEN}  ✓ {text}{Colors.ENDC}")


def print_error(text: str):
    """Print an error message."""
    print(f"{Colors.RED}  ✗ {text}{Colors.ENDC}")


def print_warning(text: str):
    """Print a warning message."""
    print(f"{Colors.YELLOW}  ! {text}{Colors.ENDC}")


def print_info(text: str):
    """Print an info message."""
    print(f"{Colors.BLUE}  → {text}{Colors.ENDC}")


def prompt_choice(prompt: str, options: list, default: int = 1) -> int:
    """Prompt user to choose from a list of options.

    Returns the 1-based index of the chosen option.
    """
    print(prompt)
    for i, opt in enumerate(options, 1):
        marker = "(default)" if i == default else ""
        print(f"  [{i}] {opt} {marker}")

    while True:
        try:
            choice = input(f"\n> ").strip()
            if not choice:
                return default
            idx = int(choice)
            if 1 <= idx <= len(options):
                return idx
            print(f"Please enter a number between 1 and {len(options)}")
        except ValueError:
            print("Please enter a number")


def prompt_string(prompt: str, default: str = "") -> str:
    """Prompt user for a string input."""
    default_display = f" [{default}]" if default else ""
    result = input(f"{prompt}{default_display}: ").strip()
    return result if result else default


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    """Prompt user for a yes/no answer."""
    default_str = "Y/n" if default else "y/N"
    while True:
        result = input(f"{prompt} ({default_str}): ").strip().lower()
        if not result:
            return default
        if result in ("y", "yes"):
            return True
        if result in ("n", "no"):
            return False
        print("Please enter 'y' or 'n'")


def is_first_time_user() -> bool:
    """Check if this is a first-time user (no global config exists)."""
    return not GLOBAL_CONFIG_PATH.exists()


def run_wizard(project_dir: Optional[str] = None, force: bool = False) -> bool:
    """Run the interactive setup wizard.

    Args:
        project_dir: If provided, also creates control.json for this project.
        force: If True, run even if already configured.

    Returns:
        True if setup completed successfully.
    """
    print_header("BAM Setup Wizard")

    # Check if already configured
    if not force and not is_first_time_user():
        print("BAM is already configured.")
        if not prompt_yes_no("Would you like to reconfigure?", default=False):
            return False

    # Step 1: Choose provider
    print_header("Step 1: Choose LLM Provider")

    provider_options = [
        f"Claude (Anthropic) - {SUPPORTED_PROVIDERS['claude']}",
        f"GitHub Copilot - {SUPPORTED_PROVIDERS['copilot']}",
        f"Mock - {SUPPORTED_PROVIDERS['mock']}",
    ]
    provider_choice = prompt_choice(
        "Which LLM provider would you like to use?",
        provider_options,
        default=1,
    )
    provider = ["claude", "copilot", "mock"][provider_choice - 1]
    print_info(f"Selected: {provider}")

    # Step 2: Configure credentials
    print_header("Step 2: Configure Credentials")

    env_var = ""
    if provider == "claude":
        print("Claude requires an API key from Anthropic.")
        print_info("Get your key at: https://console.anthropic.com/")
        print()

        cred_options = [
            "Environment variable (Recommended - most secure)",
            "Enter API key now (will be saved to config - less secure)",
        ]
        cred_choice = prompt_choice(
            "How should BAM access your API key?",
            cred_options,
            default=1,
        )

        if cred_choice == 1:
            env_var = prompt_string(
                "Environment variable name",
                default="ANTHROPIC_API_KEY",
            )
            print()
            print_info(f"Set your API key in your shell:")
            print(f"    export {env_var}=sk-ant-api03-your-key-here")
            print()

            # Check if it's already set
            if os.environ.get(env_var):
                print_success(f"{env_var} is already set in your environment")
            else:
                print_warning(f"{env_var} is not currently set")
                print_info("Set it now or before running BAM")
        else:
            api_key = prompt_string("Enter your Anthropic API key")
            env_var = "ANTHROPIC_API_KEY"
            # Will be saved to config below

    elif provider == "copilot":
        print("GitHub Copilot uses the Copilot CLI for authentication.")
        print_info("Ensure you have:")
        print("    1. A GitHub Copilot subscription")
        print("    2. The Copilot CLI installed")
        print("    3. Run: pip install github-copilot-sdk")
        print()
        env_var = ""

    elif provider == "mock":
        print_success("Mock provider requires no credentials.")
        env_var = ""

    # Step 3: Test connection
    print_header("Step 3: Test Connection")

    if prompt_yes_no("Would you like to test the connection now?", default=True):
        print("Testing connection...")
        try:
            # Save config temporarily for testing
            config = load_global_config()
            config["llm"] = {"provider": provider}
            if provider == "claude" and cred_choice == 2 and api_key:
                config["llm"]["api_key"] = api_key
            save_global_config(config)

            p = get_llm_provider(provider)
            if p.is_available():
                result = p.test_connection()
                if result.success:
                    print_success(result.message)
                else:
                    print_error(result.message)
            else:
                print_warning("Provider not available (credentials not configured)")
        except Exception as e:
            print_error(f"Connection test failed: {e}")
    else:
        print_info("Skipping connection test")

    # Step 4: Model selection
    print_header("Step 4: Model Configuration")

    models_by_task = {}

    model_options = [
        "Use default models for all tasks (simpler)",
        "Configure different models per task (cost optimization)",
    ]
    model_choice = prompt_choice(
        "Would you like to customize model selection?",
        model_options,
        default=1,
    )

    if model_choice == 2:
        defaults = DEFAULT_MODELS.get(provider, DEFAULT_MODELS["mock"])

        for task in TASK_TYPES:
            print()
            print(f"Model for {Colors.BOLD}{task}{Colors.ENDC}:")

            if provider == "claude":
                task_options = [
                    "claude-opus-4-20250514 (most capable, highest cost)",
                    "claude-sonnet-4-20250514 (balanced)",
                    "claude-haiku-4-20250514 (fastest, lowest cost)",
                ]
                # Set sensible defaults per task
                if task == "agent-review":
                    default_idx = 2  # sonnet
                else:
                    default_idx = 3  # haiku

                choice = prompt_choice("", task_options, default=default_idx)
                model = [
                    "claude-opus-4-20250514",
                    "claude-sonnet-4-20250514",
                    "claude-haiku-4-20250514",
                ][choice - 1]
            else:
                model = prompt_string(
                    "  Model name",
                    default=defaults.get(task, ""),
                )

            models_by_task[task] = model
    else:
        # Use defaults
        defaults = DEFAULT_MODELS.get(provider, DEFAULT_MODELS["mock"])
        for task in TASK_TYPES:
            models_by_task[task] = defaults.get(task, "")

    # Step 5: Save configuration
    print_header("Step 5: Save Configuration")

    # Save global config
    config = load_global_config()
    config["llm"] = {
        "provider": provider,
        "env_var": env_var,
    }
    if provider == "claude" and cred_choice == 2 and api_key:
        config["llm"]["api_key"] = api_key
        print_warning("API key saved to config file. Consider using environment variable instead.")

    save_global_config(config)
    print_success(f"Global config saved to {GLOBAL_CONFIG_PATH}")

    # Save project control.json if project_dir provided
    if project_dir:
        control_mgr = ControlManager(project_dir)

        # Build control config
        llm_config = LLMControlConfig(
            provider=provider,
            credentials=CredentialConfig(source="env", env_var=env_var),
            models_by_task={
                task: ModelConfig(model=model)
                for task, model in models_by_task.items()
            },
        )
        control_config = ControlConfig(llm=llm_config)
        control_mgr.save(control_config)
        print_success(f"Project config saved to {control_mgr.control_path}")

        # Create .env.example
        env_path = create_env_example(project_dir, provider)
        print_success(f"Created {env_path}")

    # Done!
    print_header("Setup Complete!")

    print("Next steps:")
    if provider == "claude" and not os.environ.get(env_var or "ANTHROPIC_API_KEY"):
        print(f"  1. Set your API key: export {env_var or 'ANTHROPIC_API_KEY'}=sk-ant-...")
        print("  2. Run: python -m bam setup llm --test")
    elif provider == "copilot":
        print("  1. Install Copilot CLI and SDK")
        print("  2. Run: python -m bam setup llm --test")
    else:
        print("  Run: python -m bam setup llm --test")

    if project_dir:
        print(f"  Then: python -m bam --project {project_dir} stats")

    return True


def run_quick_setup(provider: str = "claude") -> bool:
    """Run a non-interactive quick setup with defaults.

    Useful for CI/CD or scripted setups.
    """
    print_info(f"Running quick setup with provider: {provider}")

    config = load_global_config()
    config["llm"] = {"provider": provider}

    if provider == "claude":
        config["llm"]["env_var"] = "ANTHROPIC_API_KEY"
    elif provider == "copilot":
        config["llm"]["env_var"] = ""

    save_global_config(config)
    print_success(f"Configured {provider} provider")

    # Test if available
    try:
        p = get_llm_provider(provider)
        if p.is_available():
            print_success("Provider is available")
            return True
        else:
            print_warning("Provider configured but credentials not found")
            return False
    except Exception as e:
        print_error(f"Setup error: {e}")
        return False


def check_first_time_and_prompt() -> bool:
    """Check if first-time user and prompt to run wizard.

    Returns True if setup is needed, False if already configured.
    """
    if not is_first_time_user():
        return False

    print()
    print(f"{Colors.BOLD}Welcome to BAM!{Colors.ENDC}")
    print()
    print("It looks like this is your first time using BAM.")
    print("BAM needs an LLM provider configured for agent-driven ingestion.")
    print()

    if prompt_yes_no("Would you like to run the setup wizard now?", default=True):
        run_wizard()
        return True
    else:
        print()
        print_info("You can run the wizard later with:")
        print("    python -m bam setup wizard")
        print()
        print_info("Or configure manually with:")
        print("    python -m bam setup llm --provider claude")
        print()
        return True


if __name__ == "__main__":
    run_wizard()
