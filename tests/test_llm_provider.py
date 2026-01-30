"""Tests for the LLM provider package."""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from bam.llm.provider import LLMMessage, LLMProvider, LLMResponse
from bam.llm.claude_provider import ClaudeProvider


class TestLLMMessage(unittest.TestCase):
    def test_create(self):
        msg = LLMMessage(role="user", content="hello")
        self.assertEqual(msg.role, "user")
        self.assertEqual(msg.content, "hello")


class TestLLMResponse(unittest.TestCase):
    def test_create(self):
        resp = LLMResponse(content="hi", model="test-model")
        self.assertEqual(resp.content, "hi")
        self.assertEqual(resp.model, "test-model")
        self.assertEqual(resp.usage, {})
        self.assertIsNone(resp.raw)


class TestClaudeProvider(unittest.TestCase):
    def test_init_with_api_key(self):
        provider = ClaudeProvider(api_key="sk-test-123")
        self.assertTrue(provider.is_available())

    def test_init_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove ANTHROPIC_API_KEY if set
            env = dict(os.environ)
            env.pop("ANTHROPIC_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                provider = ClaudeProvider(api_key="")
                self.assertFalse(provider.is_available())

    def test_is_available_with_env_var(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            provider = ClaudeProvider()
            self.assertTrue(provider.is_available())

    def test_complete_with_mock(self):
        provider = ClaudeProvider(api_key="sk-test")

        # Mock the anthropic client
        mock_client = MagicMock()
        mock_block = MagicMock()
        mock_block.text = '{"result": "ok"}'
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_response.model = "claude-sonnet-4-20250514"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_client.messages.create.return_value = mock_response

        provider._client = mock_client

        messages = [LLMMessage(role="user", content="test")]
        response = provider.complete(messages, system_prompt="sys")

        self.assertEqual(response.content, '{"result": "ok"}')
        self.assertEqual(response.model, "claude-sonnet-4-20250514")
        self.assertEqual(response.usage["input_tokens"], 10)
        self.assertEqual(response.usage["output_tokens"], 5)

        # Verify API was called correctly
        call_kwargs = mock_client.messages.create.call_args[1]
        self.assertEqual(call_kwargs["system"], "sys")
        self.assertEqual(call_kwargs["messages"], [{"role": "user", "content": "test"}])


class TestProviderFactory(unittest.TestCase):
    @patch("bam.llm.factory.load_global_config")
    def test_get_claude_from_config(self, mock_config):
        mock_config.return_value = {
            "llm": {
                "provider": "claude",
                "api_key": "sk-test-config",
                "model": "claude-sonnet-4-20250514",
            }
        }
        from bam.llm.factory import get_llm_provider
        provider = get_llm_provider()
        self.assertIsInstance(provider, ClaudeProvider)
        self.assertTrue(provider.is_available())

    @patch("bam.llm.factory.load_global_config")
    def test_get_claude_from_env(self, mock_config):
        mock_config.return_value = {}
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env-test"}):
            from bam.llm.factory import get_llm_provider
            provider = get_llm_provider()
            self.assertIsInstance(provider, ClaudeProvider)

    @patch("bam.llm.factory.load_global_config")
    def test_unknown_provider_raises(self, mock_config):
        mock_config.return_value = {"llm": {"provider": "unknown"}}
        from bam.llm.factory import get_llm_provider
        with self.assertRaises(ValueError):
            get_llm_provider()

    @patch("bam.llm.factory.load_global_config")
    def test_explicit_provider_name(self, mock_config):
        mock_config.return_value = {}
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            from bam.llm.factory import get_llm_provider
            provider = get_llm_provider(provider_name="claude")
            self.assertIsInstance(provider, ClaudeProvider)


class TestMockProvider(unittest.TestCase):
    def test_is_always_available(self):
        from bam.llm.mock_provider import MockProvider
        provider = MockProvider()
        self.assertTrue(provider.is_available())

    def test_complete_returns_response(self):
        from bam.llm.mock_provider import MockProvider
        provider = MockProvider()
        messages = [LLMMessage(role="user", content="test")]
        response = provider.complete(messages)
        self.assertIsInstance(response, LLMResponse)
        self.assertEqual(response.model, "mock-v1")

    def test_responds_ok_to_test_prompt(self):
        from bam.llm.mock_provider import MockProvider
        provider = MockProvider()
        messages = [LLMMessage(role="user", content="Respond with exactly: OK")]
        response = provider.complete(messages)
        self.assertEqual(response.content, "OK")

    def test_generates_transform_plan(self):
        from bam.llm.mock_provider import MockProvider
        import json
        provider = MockProvider()
        messages = [LLMMessage(
            role="user",
            content="Source ID: test-source\n=== Current Sketch Summary ===\nTotal nodes: 0"
        )]
        response = provider.complete(messages)
        data = json.loads(response.content)
        self.assertIn("transformPlan", data)
        self.assertEqual(data["transformPlan"]["sourceId"], "test-source")

    def test_test_connection(self):
        from bam.llm.mock_provider import MockProvider
        provider = MockProvider()
        result = provider.test_connection()
        self.assertTrue(result.success)
        self.assertIn("successful", result.message)


class TestCopilotProvider(unittest.TestCase):
    def test_check_sdk_not_installed(self):
        from bam.llm.copilot_provider import CopilotProvider
        provider = CopilotProvider()
        # SDK likely not installed in test environment
        # Just verify it doesn't crash
        available = provider.is_available()
        self.assertIsInstance(available, bool)

    def test_test_connection_without_cli(self):
        from bam.llm.copilot_provider import CopilotProvider, check_copilot_cli_installed
        provider = CopilotProvider()
        result = provider.test_connection()
        # Should fail gracefully with helpful message
        if not check_copilot_cli_installed():
            self.assertFalse(result.success)
            self.assertIn("Copilot CLI", result.message)


class TestTestResult(unittest.TestCase):
    def test_create(self):
        from bam.llm.provider import TestResult
        result = TestResult(success=True, message="OK", provider="test")
        self.assertTrue(result.success)
        self.assertEqual(result.message, "OK")
        self.assertEqual(result.provider, "test")


class TestProviderFactoryExtended(unittest.TestCase):
    @patch("bam.llm.factory.load_global_config")
    def test_get_mock_provider(self, mock_config):
        mock_config.return_value = {"llm": {"provider": "mock"}}
        from bam.llm.factory import get_llm_provider
        from bam.llm.mock_provider import MockProvider
        provider = get_llm_provider()
        self.assertIsInstance(provider, MockProvider)

    @patch("bam.llm.factory.load_global_config")
    def test_get_copilot_provider(self, mock_config):
        mock_config.return_value = {"llm": {"provider": "copilot"}}
        from bam.llm.factory import get_llm_provider
        from bam.llm.copilot_provider import CopilotProvider
        provider = get_llm_provider()
        self.assertIsInstance(provider, CopilotProvider)

    @patch("bam.llm.factory.load_global_config")
    def test_defaults_to_mock_when_unconfigured(self, mock_config):
        mock_config.return_value = {}
        with patch.dict(os.environ, {}, clear=True):
            env = dict(os.environ)
            env.pop("ANTHROPIC_API_KEY", None)
            with patch.dict(os.environ, env, clear=True):
                from bam.llm.factory import get_llm_provider
                from bam.llm.mock_provider import MockProvider
                provider = get_llm_provider()
                self.assertIsInstance(provider, MockProvider)

    def test_list_providers(self):
        from bam.llm.factory import list_providers
        providers = list_providers()
        self.assertIn("claude", providers)
        self.assertIn("copilot", providers)
        self.assertIn("mock", providers)


if __name__ == "__main__":
    unittest.main()
