"""Tests for Context Management feature."""
import pytest
from llm.context_manager import ContextManager


@pytest.fixture
def context_manager(user_path):
    """Create a ContextManager instance."""
    db_path = user_path / "test_context.db"
    return ContextManager(db_path=db_path)


def test_set_limit(context_manager):
    """Test setting token limit."""
    success = context_manager.set_limit("conv-123", 8192)
    assert success is True


def test_set_strategy(context_manager):
    """Test setting context strategy."""
    success = context_manager.set_strategy("conv-123", "sliding_window")
    assert success is True


def test_set_invalid_strategy(context_manager):
    """Test setting invalid strategy."""
    with pytest.raises(ValueError):
        context_manager.set_strategy("conv-123", "invalid_strategy")


def test_get_status(context_manager):
    """Test getting context status."""
    context_manager.set_limit("conv-123", 4096)
    context_manager.set_strategy("conv-123", "summarize_old")

    status = context_manager.get_status("conv-123")

    assert status["conversation_id"] == "conv-123"
    assert status["max_tokens"] == 4096
    assert status["strategy"] == "summarize_old"
    assert "estimated_tokens" in status
    assert "percentage_used" in status


def test_get_status_defaults(context_manager):
    """Test getting status with defaults."""
    status = context_manager.get_status("new-conv")

    assert status["max_tokens"] == 4096  # Default
    assert status["strategy"] == "sliding_window"  # Default


def test_clear(context_manager):
    """Test clearing context."""
    cleared = context_manager.clear("conv-123", keep_recent=5)
    assert isinstance(cleared, int)
