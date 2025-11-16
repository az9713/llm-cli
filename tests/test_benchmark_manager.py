"""Tests for Model Benchmarking feature."""
import pytest
from unittest.mock import Mock, patch
from llm.benchmark_manager import BenchmarkManager


@pytest.fixture
def benchmark_manager(user_path):
    """Create a BenchmarkManager instance."""
    db_path = user_path / "test_benchmarks.db"
    return BenchmarkManager(db_path=db_path)


def test_create_benchmark(benchmark_manager):
    """Test creating a benchmark."""
    test_cases = [
        {"prompt": "What is 2+2?", "expected": "4"},
        {"prompt": "What is the capital of France?", "expected": "Paris"}
    ]

    benchmark_id = benchmark_manager.create_benchmark(
        name="math-test",
        test_cases=test_cases,
        description="Basic math test"
    )

    assert benchmark_id is not None


def test_list_benchmarks(benchmark_manager):
    """Test listing benchmarks."""
    test_cases = [{"prompt": "Test", "expected": "Answer"}]

    benchmark_manager.create_benchmark("benchmark1", test_cases)
    benchmark_manager.create_benchmark("benchmark2", test_cases)

    benchmarks = benchmark_manager.list_benchmarks()

    assert len(benchmarks) == 2
    assert any(b["name"] == "benchmark1" for b in benchmarks)


def test_run_benchmark(benchmark_manager):
    """Test running a benchmark."""
    test_cases = [{"prompt": "Test", "expected": "answer"}]

    benchmark_manager.create_benchmark("test-bench", test_cases)

    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "This contains the answer"
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        run_id = benchmark_manager.run_benchmark("test-bench", ["model1"])

        assert run_id is not None


def test_get_run(benchmark_manager):
    """Test getting benchmark run results."""
    test_cases = [{"prompt": "Test", "expected": "answer"}]

    benchmark_manager.create_benchmark("test-bench", test_cases)

    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "answer"
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        run_id = benchmark_manager.run_benchmark("test-bench", ["model1"])
        run = benchmark_manager.get_run(run_id)

        assert run is not None
        assert "results" in run
        assert "scores" in run
