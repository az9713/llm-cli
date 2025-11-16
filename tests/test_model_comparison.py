"""Tests for Model Comparison feature."""
import pytest
from unittest.mock import Mock, patch
from llm.model_comparison import ModelComparison


@pytest.fixture
def comparison(user_path):
    """Create a ModelComparison instance with test database."""
    db_path = user_path / "test_comparisons.db"
    return ModelComparison(db_path=db_path)


@pytest.fixture
def mock_response():
    """Create a mock model response."""
    response = Mock()
    response.text.return_value = "This is a test response"
    response.input_tokens = 10
    response.output_tokens = 5
    return response


def test_compare_models_basic(comparison):
    """Test basic model comparison."""
    with patch('llm.get_model') as mock_get_model:
        # Setup mocks
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Test response"
        mock_response.input_tokens = 10
        mock_response.output_tokens = 5
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        result = comparison.compare(
            prompt="Test prompt",
            models=["model1", "model2"],
            save=False
        )

        assert result is not None
        assert "id" in result
        assert "prompt" in result
        assert "responses" in result
        assert len(result["responses"]) == 2


def test_compare_with_system_prompt(comparison):
    """Test comparison with system prompt."""
    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response"
        mock_response.input_tokens = 10
        mock_response.output_tokens = 5
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        result = comparison.compare(
            prompt="Test",
            models=["model1"],
            system="You are a helpful assistant",
            save=False
        )

        assert result["system_prompt"] == "You are a helpful assistant"


def test_compare_tracks_metrics(comparison):
    """Test that comparison tracks time, tokens, and cost."""
    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response"
        mock_response.input_tokens = 100
        mock_response.output_tokens = 50
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        result = comparison.compare(
            prompt="Test",
            models=["model1"],
            save=False
        )

        response_data = result["responses"][0]
        assert "time" in response_data
        assert response_data["time"] >= 0
        assert response_data["tokens"]["input"] == 100
        assert response_data["tokens"]["output"] == 50
        assert response_data["tokens"]["total"] == 150


def test_compare_handles_errors(comparison):
    """Test that comparison handles model errors gracefully."""
    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        mock_model.prompt.side_effect = Exception("Model error")
        mock_get_model.return_value = mock_model

        result = comparison.compare(
            prompt="Test",
            models=["model1"],
            save=False
        )

        response_data = result["responses"][0]
        assert response_data["success"] is False
        assert "Model error" in response_data["error"]


def test_save_comparison(comparison):
    """Test saving a comparison to database."""
    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response"
        mock_response.input_tokens = 10
        mock_response.output_tokens = 5
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        result = comparison.compare(
            prompt="Test",
            models=["model1"],
            save=True  # Save to database
        )

        # Retrieve it
        comparison_id = result["id"]
        retrieved = comparison.get_comparison(comparison_id)

        assert retrieved is not None
        assert retrieved["prompt"] == "Test"


def test_get_nonexistent_comparison(comparison):
    """Test getting a comparison that doesn't exist."""
    result = comparison.get_comparison("nonexistent-id")
    assert result is None


def test_list_comparisons(comparison):
    """Test listing comparisons."""
    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response"
        mock_response.input_tokens = 10
        mock_response.output_tokens = 5
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        # Create two comparisons
        comparison.compare("Prompt 1", ["model1"], save=True)
        comparison.compare("Prompt 2", ["model1"], save=True)

        comparisons = comparison.list_comparisons()
        assert len(comparisons) == 2


def test_list_comparisons_limit(comparison):
    """Test limiting number of comparisons returned."""
    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response"
        mock_response.input_tokens = 10
        mock_response.output_tokens = 5
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        # Create 5 comparisons
        for i in range(5):
            comparison.compare(f"Prompt {i}", ["model1"], save=True)

        comparisons = comparison.list_comparisons(limit=3)
        assert len(comparisons) == 3


def test_get_best_model_by_cost(comparison):
    """Test finding best model by cost."""
    result = {
        "responses": [
            {"model": "expensive", "cost": 0.05, "success": True},
            {"model": "cheap", "cost": 0.01, "success": True},
            {"model": "medium", "cost": 0.03, "success": True},
        ]
    }

    best = comparison.get_best_model(result, criteria="cost")
    assert best == "cheap"


def test_get_best_model_by_time(comparison):
    """Test finding best model by response time."""
    result = {
        "responses": [
            {"model": "slow", "time": 5.0, "success": True},
            {"model": "fast", "time": 1.0, "success": True},
            {"model": "medium", "time": 3.0, "success": True},
        ]
    }

    best = comparison.get_best_model(result, criteria="time")
    assert best == "fast"


def test_get_best_model_by_length(comparison):
    """Test finding best model by response length."""
    result = {
        "responses": [
            {"model": "short", "text": "Short", "success": True},
            {"model": "long", "text": "This is a much longer response", "success": True},
            {"model": "medium", "text": "Medium length", "success": True},
        ]
    }

    best = comparison.get_best_model(result, criteria="length")
    assert best == "long"


def test_get_best_model_ignores_failed(comparison):
    """Test that best model selection ignores failed responses."""
    result = {
        "responses": [
            {"model": "failed-cheap", "cost": 0.001, "success": False, "error": "Error"},
            {"model": "success-expensive", "cost": 0.05, "success": True},
        ]
    }

    best = comparison.get_best_model(result, criteria="cost")
    assert best == "success-expensive"


def test_get_best_model_all_failed(comparison):
    """Test best model when all responses failed."""
    result = {
        "responses": [
            {"model": "model1", "success": False, "error": "Error 1"},
            {"model": "model2", "success": False, "error": "Error 2"},
        ]
    }

    best = comparison.get_best_model(result, criteria="cost")
    assert best is None


def test_format_comparison_text(comparison):
    """Test formatting comparison as text."""
    test_comparison = {
        "id": "test-123",
        "prompt": "Test prompt",
        "models": ["model1", "model2"],
        "created_at": "2024-01-01T00:00:00",
        "responses": [
            {
                "model": "model1",
                "text": "Response from model 1",
                "time": 1.5,
                "tokens": {"input": 10, "output": 20, "total": 30},
                "cost": 0.001,
                "success": True,
            },
            {
                "model": "model2",
                "text": "Response from model 2",
                "time": 2.0,
                "tokens": {"input": 10, "output": 25, "total": 35},
                "cost": 0.002,
                "success": True,
            },
        ],
    }

    text = comparison.format_comparison_text(test_comparison, show_metrics=True)

    assert "MODEL COMPARISON" in text
    assert "Test prompt" in text
    assert "model1" in text
    assert "model2" in text
    assert "Response from model 1" in text
    assert "Response from model 2" in text


def test_format_comparison_without_metrics(comparison):
    """Test formatting comparison without metrics."""
    test_comparison = {
        "prompt": "Test",
        "models": ["model1"],
        "created_at": "2024-01-01T00:00:00",
        "responses": [
            {
                "model": "model1",
                "text": "Response",
                "success": True,
            },
        ],
    }

    text = comparison.format_comparison_text(test_comparison, show_metrics=False)

    assert "Response" in text
    # Should not contain cost/time info
    assert "Cost:" not in text
    assert "Time:" not in text


def test_format_comparison_with_errors(comparison):
    """Test formatting comparison that includes errors."""
    test_comparison = {
        "prompt": "Test",
        "models": ["model1", "model2"],
        "created_at": "2024-01-01T00:00:00",
        "responses": [
            {
                "model": "model1",
                "text": "Success response",
                "success": True,
                "time": 1.0,
                "tokens": {"total": 10},
                "cost": 0.001,
            },
            {
                "model": "model2",
                "text": None,
                "success": False,
                "error": "Connection timeout",
            },
        ],
    }

    text = comparison.format_comparison_text(test_comparison, show_metrics=True)

    assert "Success response" in text
    assert "ERROR" in text
    assert "Connection timeout" in text
