"""Tests for Spawnie LLM provider integration."""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestSpawnieProviderImport:
    """Tests for SpawnieProvider import behavior."""

    def test_import_fails_gracefully_without_spawnie(self):
        """SpawnieProvider raises ImportError if spawnie not installed."""
        # This test verifies the behavior when spawnie is not available
        with patch.dict("sys.modules", {"spawnie": None}):
            # Force reimport
            import importlib
            from bam.llm import spawnie_provider

            # Reset the module-level flag
            original_available = spawnie_provider.SPAWNIE_AVAILABLE
            spawnie_provider.SPAWNIE_AVAILABLE = False

            try:
                with pytest.raises(ImportError, match="Spawnie package not installed"):
                    spawnie_provider.SpawnieProvider()
            finally:
                spawnie_provider.SPAWNIE_AVAILABLE = original_available


class TestSpawnieProviderWithMock:
    """Tests for SpawnieProvider using mocked spawnie."""

    @pytest.fixture
    def mock_spawnie(self):
        """Create a mock spawnie module."""
        mock = MagicMock()

        # Mock registry
        mock_registry = MagicMock()
        mock_registry.get_best_route.return_value = (
            MagicMock(provider="mock"),
            MagicMock(type="mock"),
        )
        mock.get_registry.return_value = mock_registry

        # Mock run result
        mock_result = MagicMock()
        mock_result.succeeded = True
        mock_result.output = "Test response"
        mock_result.error = None
        mock.run.return_value = mock_result

        # Mock list_models
        mock.list_models.return_value = [
            {"name": "claude-sonnet", "available": True, "route": "mock"},
            {"name": "claude-opus", "available": True, "route": "mock"},
        ]

        return mock

    @pytest.fixture
    def provider(self, mock_spawnie):
        """Create a SpawnieProvider with mocked spawnie."""
        with patch.dict("sys.modules", {"spawnie": mock_spawnie}):
            from bam.llm import spawnie_provider

            # Patch the module-level spawnie reference
            original_spawnie = spawnie_provider.spawnie
            original_available = spawnie_provider.SPAWNIE_AVAILABLE
            spawnie_provider.spawnie = mock_spawnie
            spawnie_provider.SPAWNIE_AVAILABLE = True

            provider = spawnie_provider.SpawnieProvider(model="claude-sonnet")

            yield provider, mock_spawnie

            # Restore
            spawnie_provider.spawnie = original_spawnie
            spawnie_provider.SPAWNIE_AVAILABLE = original_available

    def test_provider_init(self, provider):
        """SpawnieProvider initializes with correct defaults."""
        prov, mock = provider
        assert prov._model == "claude-sonnet"
        assert prov._mode == "blocking"
        assert prov._timeout == 300

    def test_is_available_with_route(self, provider):
        """is_available returns True when route exists."""
        prov, mock = provider
        assert prov.is_available() is True

    def test_is_available_without_route(self, provider):
        """is_available returns False when no route exists."""
        prov, mock = provider
        mock.get_registry().get_best_route.return_value = None
        assert prov.is_available() is False

    def test_complete_sends_prompt(self, provider):
        """complete() sends prompt through spawnie.run()."""
        from bam.llm.provider import LLMMessage

        prov, mock = provider

        messages = [LLMMessage(role="user", content="Hello, world!")]
        response = prov.complete(messages, system_prompt="You are helpful")

        # Verify spawnie.run was called
        mock.run.assert_called_once()
        call_args = mock.run.call_args

        # Check prompt construction
        prompt = call_args[0][0]
        assert "<system>" in prompt
        assert "You are helpful" in prompt
        assert "<user>" in prompt
        assert "Hello, world!" in prompt

        # Check model was passed
        assert call_args[1]["model"] == "claude-sonnet"

    def test_complete_returns_response(self, provider):
        """complete() returns properly formatted LLMResponse."""
        from bam.llm.provider import LLMMessage

        prov, mock = provider

        mock_result = MagicMock()
        mock_result.succeeded = True
        mock_result.output = "Response content"
        mock_result.error = None
        mock.run.return_value = mock_result

        messages = [LLMMessage(role="user", content="Test")]
        response = prov.complete(messages)

        assert response.content == "Response content"
        assert "spawnie:" in response.model
        assert "input_tokens" in response.usage
        assert "output_tokens" in response.usage

    def test_complete_handles_multi_turn(self, provider):
        """complete() handles multi-turn conversations."""
        from bam.llm.provider import LLMMessage

        prov, mock = provider

        messages = [
            LLMMessage(role="user", content="Question 1"),
            LLMMessage(role="assistant", content="Answer 1"),
            LLMMessage(role="user", content="Question 2"),
        ]
        prov.complete(messages)

        prompt = mock.run.call_args[0][0]
        assert "Question 1" in prompt
        assert "Answer 1" in prompt
        assert "Question 2" in prompt
        assert "<assistant>" in prompt

    def test_complete_raises_on_failure(self, provider):
        """complete() raises RuntimeError on spawnie failure."""
        from bam.llm.provider import LLMMessage

        prov, mock = provider

        mock_result = MagicMock()
        mock_result.succeeded = False
        mock_result.output = None
        mock_result.error = "Connection failed"
        mock.run.return_value = mock_result

        messages = [LLMMessage(role="user", content="Test")]

        with pytest.raises(RuntimeError, match="Spawnie execution failed"):
            prov.complete(messages)

    def test_test_connection_success(self, provider):
        """test_connection() returns success when spawnie works."""
        prov, mock = provider

        mock_result = MagicMock()
        mock_result.succeeded = True
        mock_result.output = "OK"
        mock.run.return_value = mock_result

        result = prov.test_connection()

        assert result.success is True
        assert "Connected" in result.message
        assert result.provider == "SpawnieProvider"

    def test_test_connection_no_route(self, provider):
        """test_connection() returns failure when no route available."""
        prov, mock = provider

        mock.get_registry().get_best_route.return_value = None
        mock.list_models.return_value = []

        result = prov.test_connection()

        assert result.success is False
        assert "No route available" in result.message

    def test_list_available_models(self, provider):
        """list_available_models() returns model list from spawnie."""
        prov, mock = provider

        models = prov.list_available_models()

        assert len(models) == 2
        assert models[0]["name"] == "claude-sonnet"
        assert models[0]["available"] is True

    def test_get_tracker_status(self, provider):
        """get_tracker_status() returns spawnie tracker status."""
        prov, mock = provider

        mock.workflow_status.return_value = {
            "workflows": {"running": 1, "queued": 0},
            "tasks": {"running": 2, "queued": 1},
        }

        status = prov.get_tracker_status()

        assert status["workflows"]["running"] == 1
        assert status["tasks"]["running"] == 2


class TestSpawnieProviderFactory:
    """Tests for SpawnieProvider factory integration."""

    def test_factory_creates_spawnie_provider(self):
        """get_llm_provider creates SpawnieProvider for 'spawnie'."""
        # This test requires spawnie to be installed
        pytest.importorskip("spawnie")

        from bam.llm.factory import get_llm_provider

        provider = get_llm_provider(provider_name="spawnie")

        assert provider.__class__.__name__ == "SpawnieProvider"

    def test_factory_lists_spawnie(self):
        """list_providers includes spawnie."""
        from bam.llm.factory import list_providers

        providers = list_providers()

        assert "spawnie" in providers
        assert "routes to cli agents" in providers["spawnie"].lower()
