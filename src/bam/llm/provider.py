"""Abstract LLM provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LLMMessage:
    """A message in an LLM conversation."""
    role: str  # "user" | "assistant"
    content: str


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    content: str
    model: str
    usage: Dict[str, int] = field(default_factory=dict)
    raw: Any = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def complete(self, messages: List[LLMMessage], system_prompt: str = "",
                 max_tokens: int = 4096, temperature: float = 0.0) -> LLMResponse:
        """Send messages to the LLM and get a response."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is configured and available."""
        ...

    def test_connection(self) -> "TestResult":
        """Test the LLM connection with a simple prompt.

        Returns a TestResult with success status and details.
        """
        if not self.is_available():
            return TestResult(
                success=False,
                message="Provider not configured (missing API key or credentials)",
                provider=self.__class__.__name__,
            )

        try:
            response = self.complete(
                messages=[LLMMessage(role="user", content="Respond with exactly: OK")],
                system_prompt="You are a test assistant. Respond only with what is asked.",
                max_tokens=10,
                temperature=0.0,
            )
            # Check if response contains "OK"
            if "OK" in response.content.upper():
                return TestResult(
                    success=True,
                    message=f"Connection successful (model: {response.model})",
                    provider=self.__class__.__name__,
                    model=response.model,
                    usage=response.usage,
                )
            else:
                return TestResult(
                    success=True,  # API worked, just unexpected response
                    message=f"Connection successful but unexpected response: {response.content[:50]}",
                    provider=self.__class__.__name__,
                    model=response.model,
                    usage=response.usage,
                )
        except Exception as e:
            return TestResult(
                success=False,
                message=f"Connection failed: {e}",
                provider=self.__class__.__name__,
            )


@dataclass
class TestResult:
    """Result of an LLM connection test."""
    success: bool
    message: str
    provider: str
    model: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
