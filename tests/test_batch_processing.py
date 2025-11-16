"""Tests for Batch Processing feature."""
import pytest
import json
import csv
from pathlib import Path
from unittest.mock import Mock, patch
from llm.batch_processing import BatchProcessor


@pytest.fixture
def processor(user_path):
    """Create a BatchProcessor instance with test database."""
    db_path = user_path / "test_batch.db"
    return BatchProcessor(db_path=db_path)


@pytest.fixture
def csv_file(tmp_path):
    """Create a test CSV file."""
    csv_path = tmp_path / "test.csv"
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["name", "age", "city"])
        writer.writeheader()
        writer.writerow({"name": "Alice", "age": "30", "city": "NYC"})
        writer.writerow({"name": "Bob", "age": "25", "city": "SF"})
    return csv_path


@pytest.fixture
def json_file(tmp_path):
    """Create a test JSON file."""
    json_path = tmp_path / "test.json"
    data = [
        {"name": "Alice", "task": "Review code"},
        {"name": "Bob", "task": "Write tests"},
    ]
    with open(json_path, 'w') as f:
        json.dump(data, f)
    return json_path


@pytest.fixture
def jsonl_file(tmp_path):
    """Create a test JSONL file."""
    jsonl_path = tmp_path / "test.jsonl"
    with open(jsonl_path, 'w') as f:
        f.write(json.dumps({"prompt": "First prompt"}) + "\n")
        f.write(json.dumps({"prompt": "Second prompt"}) + "\n")
    return jsonl_path


@pytest.fixture
def text_file(tmp_path):
    """Create a test text file."""
    text_path = tmp_path / "test.txt"
    with open(text_path, 'w') as f:
        f.write("First prompt\n")
        f.write("Second prompt\n")
        f.write("Third prompt\n")
    return text_path


def test_load_from_csv(processor, csv_file):
    """Test loading prompts from CSV file."""
    prompts = list(processor.load_prompts_from_file(csv_file))

    assert len(prompts) == 2
    assert prompts[0]["data"]["name"] == "Alice"
    assert prompts[1]["data"]["name"] == "Bob"


def test_load_from_csv_with_template(processor, csv_file):
    """Test loading from CSV with template substitution."""
    template = "Name: {name}, Age: {age}, City: {city}"
    prompts = list(processor.load_prompts_from_file(csv_file, template=template))

    assert len(prompts) == 2
    assert prompts[0]["prompt"] == "Name: Alice, Age: 30, City: NYC"
    assert prompts[1]["prompt"] == "Name: Bob, Age: 25, City: SF"


def test_load_from_json(processor, json_file):
    """Test loading prompts from JSON file."""
    prompts = list(processor.load_prompts_from_file(json_file))

    assert len(prompts) == 2
    assert prompts[0]["data"]["name"] == "Alice"
    assert prompts[1]["data"]["task"] == "Write tests"


def test_load_from_json_with_template(processor, json_file):
    """Test loading from JSON with template."""
    template = "{name} should {task}"
    prompts = list(processor.load_prompts_from_file(json_file, template=template))

    assert prompts[0]["prompt"] == "Alice should Review code"
    assert prompts[1]["prompt"] == "Bob should Write tests"


def test_load_from_jsonl(processor, jsonl_file):
    """Test loading prompts from JSONL file."""
    prompts = list(processor.load_prompts_from_file(jsonl_file))

    assert len(prompts) == 2


def test_load_from_text(processor, text_file):
    """Test loading prompts from text file."""
    prompts = list(processor.load_prompts_from_file(text_file))

    assert len(prompts) == 3
    assert prompts[0]["prompt"] == "First prompt"
    assert prompts[1]["prompt"] == "Second prompt"
    assert prompts[2]["prompt"] == "Third prompt"


def test_load_from_text_skips_empty_lines(processor, tmp_path):
    """Test that text loader skips empty lines."""
    text_path = tmp_path / "test.txt"
    with open(text_path, 'w') as f:
        f.write("First\n")
        f.write("\n")  # Empty line
        f.write("Second\n")
        f.write("\n")  # Empty line

    prompts = list(processor.load_prompts_from_file(text_path))

    assert len(prompts) == 2
    assert prompts[0]["prompt"] == "First"
    assert prompts[1]["prompt"] == "Second"


def test_process_batch_basic(processor, text_file):
    """Test basic batch processing."""
    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response"
        mock_response.input_tokens = 10
        mock_response.output_tokens = 5
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        batch_id = processor.process_batch(
            input_file=text_file,
            model_name="test-model",
            output_file=None
        )

        assert batch_id is not None
        assert len(batch_id) > 0


def test_process_batch_with_output(processor, text_file, tmp_path):
    """Test batch processing with output file."""
    output_file = tmp_path / "output.txt"

    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response"
        mock_response.input_tokens = 10
        mock_response.output_tokens = 5
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        processor.process_batch(
            input_file=text_file,
            model_name="test-model",
            output_file=output_file
        )

        # Verify output file was created
        assert output_file.exists()


def test_process_batch_with_max_prompts(processor, text_file):
    """Test batch processing with max_prompts limit."""
    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response"
        mock_response.input_tokens = 10
        mock_response.output_tokens = 5
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        batch_id = processor.process_batch(
            input_file=text_file,
            model_name="test-model",
            max_prompts=2  # Limit to 2 prompts
        )

        # Check batch status
        status = processor.get_batch_status(batch_id)
        assert status["total_prompts"] == 2  # Should only process 2


def test_process_batch_handles_errors(processor, text_file):
    """Test that batch processing handles errors gracefully."""
    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        # First call succeeds, second fails, third succeeds
        responses = [
            Mock(text=lambda: "Success 1", input_tokens=10, output_tokens=5),
            None,  # This will cause an exception
            Mock(text=lambda: "Success 3", input_tokens=10, output_tokens=5),
        ]
        mock_model.prompt.side_effect = [
            responses[0],
            Exception("Model error"),
            responses[2],
        ]
        mock_get_model.return_value = mock_model

        batch_id = processor.process_batch(
            input_file=text_file,
            model_name="test-model"
        )

        status = processor.get_batch_status(batch_id)
        assert status["completed_prompts"] == 2  # 2 succeeded
        assert status["failed_prompts"] == 1  # 1 failed


def test_get_batch_status(processor, text_file):
    """Test getting batch status."""
    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response"
        mock_response.input_tokens = 10
        mock_response.output_tokens = 5
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        batch_id = processor.process_batch(
            input_file=text_file,
            model_name="test-model"
        )

        status = processor.get_batch_status(batch_id)

        assert status is not None
        assert status["id"] == batch_id
        assert status["status"] == "completed"
        assert status["total_prompts"] == 3


def test_get_nonexistent_batch_status(processor):
    """Test getting status of non-existent batch."""
    status = processor.get_batch_status("nonexistent-id")
    assert status is None


def test_list_batches(processor, text_file):
    """Test listing batch runs."""
    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response"
        mock_response.input_tokens = 10
        mock_response.output_tokens = 5
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        # Create two batches
        processor.process_batch(text_file, "model1")
        processor.process_batch(text_file, "model2")

        batches = processor.list_batches()

        assert len(batches) == 2


def test_list_batches_limit(processor, text_file):
    """Test limiting number of batches returned."""
    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response"
        mock_response.input_tokens = 10
        mock_response.output_tokens = 5
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        # Create 5 batches
        for i in range(5):
            processor.process_batch(text_file, f"model{i}")

        batches = processor.list_batches(limit=3)

        assert len(batches) == 3


def test_save_to_csv_output(processor, csv_file, tmp_path):
    """Test saving batch results to CSV."""
    output_file = tmp_path / "output.csv"

    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Test response"
        mock_response.input_tokens = 10
        mock_response.output_tokens = 5
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        template = "Summarize info about {name}"
        processor.process_batch(
            input_file=csv_file,
            model_name="test-model",
            template=template,
            output_file=output_file
        )

        # Verify CSV was created and has correct structure
        assert output_file.exists()
        with open(output_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 2
            assert "response" in rows[0]
            assert "name" in rows[0]


def test_save_to_json_output(processor, text_file, tmp_path):
    """Test saving batch results to JSON."""
    output_file = tmp_path / "output.json"

    with patch('llm.get_model') as mock_get_model:
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text.return_value = "Response"
        mock_response.input_tokens = 10
        mock_response.output_tokens = 5
        mock_model.prompt.return_value = mock_response
        mock_get_model.return_value = mock_model

        processor.process_batch(
            input_file=text_file,
            model_name="test-model",
            output_file=output_file
        )

        # Verify JSON was created
        assert output_file.exists()
        with open(output_file, 'r') as f:
            data = json.load(f)
            assert isinstance(data, list)
            assert len(data) == 3
