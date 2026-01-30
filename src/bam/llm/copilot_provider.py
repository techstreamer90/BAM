"""GitHub Copilot LLM provider using the Copilot SDK.

Requires:
- GitHub Copilot subscription
- Copilot CLI installed: https://github.com/features/copilot/cli
- Python SDK: pip install github-copilot-sdk
"""

import logging
import shutil
import subprocess
from typing import List, Optional

from .provider import LLMMessage, LLMProvider, LLMResponse, TestResult

logger = logging.getLogger("bam.llm.copilot")


def check_copilot_cli_installed() -> bool:
    """Check if the GitHub Copilot CLI is installed and accessible."""
    # Check for 'gh' CLI with copilot extension or standalone copilot CLI
    if shutil.which("copilot"):
        return True
    # Also check if gh CLI has copilot extension
    if shutil.which("gh"):
        try:
            result = subprocess.run(
                ["gh", "extension", "list"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if "copilot" in result.stdout.lower():
                return True
        except Exception:
            pass
    return False


class CopilotProvider(LLMProvider):
    """LLM provider backed by GitHub Copilot SDK.

    This provider uses the GitHub Copilot SDK to communicate with
    the Copilot CLI, which handles authentication and model routing.

    Prerequisites:
    1. GitHub Copilot subscription
    2. Copilot CLI installed (gh extension or standalone)
    3. Python SDK: pip install github-copilot-sdk
    """

    def __init__(self, model: str = ""):
        """Initialize the Copilot provider.

        Args:
            model: Optional model override. If not specified, Copilot
                   routes to the appropriate model automatically.
        """
        self._model = model
        self._client = None
        self._session = None
        self._sdk_available = None

    def _check_sdk(self) -> bool:
        """Check if the Copilot SDK is available."""
        if self._sdk_available is None:
            try:
                import github_copilot_sdk
                self._sdk_available = True
            except ImportError:
                self._sdk_available = False
        return self._sdk_available

    def _get_client(self):
        """Get or create the Copilot SDK client."""
        if self._client is None:
            if not self._check_sdk():
                raise ImportError(
                    "The 'github-copilot-sdk' package is required for the Copilot provider. "
                    "Install it with: pip install github-copilot-sdk\n"
                    "Also ensure the Copilot CLI is installed."
                )

            import github_copilot_sdk as copilot

            # Create client - SDK manages CLI process lifecycle
            self._client = copilot.Client()

        return self._client

    def _get_session(self):
        """Get or create a Copilot session for multi-turn conversations."""
        if self._session is None:
            client = self._get_client()
            self._session = client.create_session()
        return self._session

    def complete(self, messages: List[LLMMessage], system_prompt: str = "",
                 max_tokens: int = 4096, temperature: float = 0.0) -> LLMResponse:
        """Send messages to Copilot and get a response.

        Uses the Copilot SDK's conversation API for multi-turn support.
        """
        if not self._check_sdk():
            raise ImportError(
                "The 'github-copilot-sdk' package is required. "
                "Install with: pip install github-copilot-sdk"
            )

        import github_copilot_sdk as copilot

        try:
            session = self._get_session()

            # Build the conversation
            # Copilot SDK uses a different message format
            conversation_messages = []

            if system_prompt:
                conversation_messages.append({
                    "role": "system",
                    "content": system_prompt,
                })

            for msg in messages:
                conversation_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

            # Send to Copilot
            response = session.send(
                messages=conversation_messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            # Extract content from response
            content = response.content if hasattr(response, 'content') else str(response)
            model = response.model if hasattr(response, 'model') else "copilot"

            usage = {}
            if hasattr(response, 'usage'):
                usage = {
                    "input_tokens": getattr(response.usage, 'input_tokens', 0),
                    "output_tokens": getattr(response.usage, 'output_tokens', 0),
                }

            return LLMResponse(
                content=content,
                model=model,
                usage=usage,
                raw=response,
            )

        except Exception as e:
            logger.error("Copilot API call failed: %s", e)
            raise

    def is_available(self) -> bool:
        """Check if Copilot is configured and available.

        Checks:
        1. Copilot CLI is installed
        2. Python SDK is installed
        """
        if not check_copilot_cli_installed():
            return False
        return self._check_sdk()

    def test_connection(self) -> TestResult:
        """Test the Copilot connection.

        Overrides base to provide Copilot-specific error messages.
        """
        # Check CLI first
        if not check_copilot_cli_installed():
            return TestResult(
                success=False,
                message="GitHub Copilot CLI not found. Install from: https://github.com/features/copilot/cli",
                provider="CopilotProvider",
            )

        # Check SDK
        if not self._check_sdk():
            return TestResult(
                success=False,
                message="GitHub Copilot SDK not installed. Run: pip install github-copilot-sdk",
                provider="CopilotProvider",
            )

        # Use base class test
        return super().test_connection()

    def close(self):
        """Clean up resources."""
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None

        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def __del__(self):
        self.close()
