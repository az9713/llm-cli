"""Tests for Export Manager feature."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from llm.export_manager import ExportManager


@pytest.fixture
def export_manager(user_path):
    """Create an ExportManager instance."""
    return ExportManager()


def test_export_conversation_html(export_manager, tmp_path):
    """Test exporting conversation to HTML."""
    with patch.object(export_manager, '_get_conversation_data') as mock_get:
        mock_get.return_value = {
            "id": "test-123",
            "name": "Test Conversation",
            "model": "gpt-4o",
            "messages": [
                {
                    "id": "1",
                    "prompt": "Hello",
                    "response": "Hi there!",
                    "system": None,
                    "datetime_utc": "2024-01-01T00:00:00"
                }
            ]
        }

        output_file = tmp_path / "test.html"
        result = export_manager.export_conversation(
            "test-123",
            "html",
            output_file=output_file
        )

        assert output_file.exists()
        content = output_file.read_text()
        assert "Test Conversation" in content
        assert "Hello" in content
        assert "Hi there!" in content


def test_export_conversation_markdown(export_manager):
    """Test exporting conversation to Markdown."""
    with patch.object(export_manager, '_get_conversation_data') as mock_get:
        mock_get.return_value = {
            "id": "test-123",
            "name": "Test",
            "model": "gpt-4o",
            "messages": [{"id": "1", "prompt": "Test", "response": "Response"}]
        }

        result = export_manager.export_conversation("test-123", "markdown")

        assert isinstance(result, str)
        assert "Test" in result
        assert "Response" in result


def test_export_nonexistent_conversation(export_manager):
    """Test exporting non-existent conversation."""
    with patch.object(export_manager, '_get_conversation_data') as mock_get:
        mock_get.return_value = None

        with pytest.raises(ValueError, match="not found"):
            export_manager.export_conversation("nonexistent", "html")


def test_export_comparison_html(export_manager):
    """Test exporting comparison to HTML."""
    with patch.object(export_manager, '_get_comparison_data') as mock_get:
        mock_get.return_value = {
            "id": "comp-123",
            "prompt": "Test prompt",
            "models": ["model1", "model2"],
            "responses": [
                {"model": "model1", "text": "Response 1", "success": True, "time": 1.0, "tokens": {"total": 10}, "cost": 0.01},
                {"model": "model2", "text": "Response 2", "success": True, "time": 2.0, "tokens": {"total": 20}, "cost": 0.02}
            ],
            "created_at": "2024-01-01"
        }

        result = export_manager.export_comparison("comp-123", "html")

        assert isinstance(result, str)
        assert "model1" in result
        assert "model2" in result


def test_export_batch_csv(export_manager, tmp_path):
    """Test exporting batch results to CSV."""
    with patch.object(export_manager, '_get_batch_data') as mock_get:
        mock_get.return_value = {
            "id": "batch-123",
            "results": [
                {"prompt_index": 0, "prompt": "P1", "response": "R1", "success": True, "tokens_used": 10, "cost": 0.01},
                {"prompt_index": 1, "prompt": "P2", "response": "R2", "success": True, "tokens_used": 20, "cost": 0.02}
            ]
        }

        output_file = tmp_path / "batch.csv"
        result = export_manager.export_batch("batch-123", "csv", output_file=output_file)

        assert Path(result).exists()
        content = Path(result).read_text()
        assert "P1" in content
        assert "R1" in content
