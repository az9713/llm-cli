"""Tests for Prompt Library feature."""
import pytest
import json
from pathlib import Path
from llm.prompt_library import PromptLibrary


@pytest.fixture
def library(user_path):
    """Create a PromptLibrary instance with test database."""
    db_path = user_path / "test_prompts.db"
    return PromptLibrary(db_path=db_path)


def test_add_prompt_basic(library):
    """Test adding a basic prompt."""
    prompt_id = library.add_prompt(
        name="test-prompt",
        prompt="Hello {name}",
        description="A test prompt"
    )

    assert prompt_id is not None

    # Verify prompt was saved
    prompt = library.get_prompt("test-prompt")
    assert prompt is not None
    assert prompt["name"] == "test-prompt"
    assert prompt["prompt"] == "Hello {name}"
    assert prompt["description"] == "A test prompt"


def test_add_prompt_with_system(library):
    """Test adding a prompt with system prompt."""
    library.add_prompt(
        name="assistant",
        prompt="Help me with {task}",
        system_prompt="You are a helpful assistant",
        category="helpers"
    )

    prompt = library.get_prompt("assistant")
    assert prompt["system_prompt"] == "You are a helpful assistant"
    assert prompt["category"] == "helpers"


def test_add_prompt_with_tags(library):
    """Test adding a prompt with tags."""
    library.add_prompt(
        name="tagged",
        prompt="Test prompt",
        tags=["test", "example", "demo"]
    )

    prompt = library.get_prompt("tagged")
    assert prompt["tags"] == ["test", "example", "demo"]


def test_add_duplicate_prompt_fails(library):
    """Test that adding duplicate prompts raises error."""
    library.add_prompt(name="dup", prompt="First")

    with pytest.raises(Exception):  # Should raise unique constraint error
        library.add_prompt(name="dup", prompt="Second")


def test_list_prompts_empty(library):
    """Test listing prompts when library is empty."""
    prompts = library.list_prompts()
    assert prompts == []


def test_list_prompts(library):
    """Test listing prompts."""
    library.add_prompt(name="p1", prompt="Prompt 1")
    library.add_prompt(name="p2", prompt="Prompt 2")
    library.add_prompt(name="p3", prompt="Prompt 3")

    prompts = library.list_prompts()
    assert len(prompts) == 3
    assert any(p["name"] == "p1" for p in prompts)
    assert any(p["name"] == "p2" for p in prompts)


def test_list_prompts_by_category(library):
    """Test filtering prompts by category."""
    library.add_prompt(name="p1", prompt="P1", category="cat1")
    library.add_prompt(name="p2", prompt="P2", category="cat2")
    library.add_prompt(name="p3", prompt="P3", category="cat1")

    cat1_prompts = library.list_prompts(category="cat1")
    assert len(cat1_prompts) == 2
    assert all(p["category"] == "cat1" for p in cat1_prompts)


def test_search_prompts(library):
    """Test searching prompts."""
    library.add_prompt(
        name="python-help",
        prompt="Help with Python",
        description="Python programming assistance"
    )
    library.add_prompt(
        name="js-help",
        prompt="Help with JavaScript",
        description="JS programming assistance"
    )

    # Search for Python
    results = library.search_prompts("Python")
    assert len(results) == 1
    assert results[0]["name"] == "python-help"

    # Search for "programming" (in description)
    results = library.search_prompts("programming")
    assert len(results) == 2


def test_update_prompt(library):
    """Test updating a prompt."""
    library.add_prompt(name="test", prompt="Original")

    library.update_prompt(
        name="test",
        prompt="Updated",
        description="New description"
    )

    prompt = library.get_prompt("test")
    assert prompt["prompt"] == "Updated"
    assert prompt["description"] == "New description"


def test_delete_prompt(library):
    """Test deleting a prompt."""
    library.add_prompt(name="to-delete", prompt="Delete me")

    # Verify it exists
    assert library.get_prompt("to-delete") is not None

    # Delete it
    deleted = library.delete_prompt("to-delete")
    assert deleted is True

    # Verify it's gone
    assert library.get_prompt("to-delete") is None


def test_delete_nonexistent_prompt(library):
    """Test deleting a prompt that doesn't exist."""
    deleted = library.delete_prompt("nonexistent")
    assert deleted is False


def test_increment_usage(library):
    """Test incrementing usage count."""
    library.add_prompt(name="test", prompt="Test")

    # Initial usage should be 0
    prompt = library.get_prompt("test")
    assert prompt["usage_count"] == 0

    # Increment
    library.increment_usage("test")
    prompt = library.get_prompt("test")
    assert prompt["usage_count"] == 1

    # Increment again
    library.increment_usage("test")
    prompt = library.get_prompt("test")
    assert prompt["usage_count"] == 2


def test_export_prompts(library, tmp_path):
    """Test exporting prompts to JSON."""
    library.add_prompt(name="p1", prompt="Prompt 1", tags=["tag1"])
    library.add_prompt(name="p2", prompt="Prompt 2", category="cat1")

    export_file = tmp_path / "export.json"
    library.export_prompts(str(export_file))

    # Verify file was created
    assert export_file.exists()

    # Verify content
    with open(export_file) as f:
        data = json.load(f)

    assert len(data) == 2
    assert any(p["name"] == "p1" for p in data)


def test_import_prompts(library, tmp_path):
    """Test importing prompts from JSON."""
    # Create export file
    prompts_data = [
        {
            "name": "imported1",
            "prompt": "Imported prompt 1",
            "description": "Test import",
            "tags": ["import"]
        },
        {
            "name": "imported2",
            "prompt": "Imported prompt 2",
            "category": "imports"
        }
    ]

    import_file = tmp_path / "import.json"
    with open(import_file, 'w') as f:
        json.dump(prompts_data, f)

    # Import
    imported = library.import_prompts(str(import_file))
    assert imported == 2

    # Verify prompts were imported
    p1 = library.get_prompt("imported1")
    assert p1 is not None
    assert p1["description"] == "Test import"

    p2 = library.get_prompt("imported2")
    assert p2 is not None
    assert p2["category"] == "imports"


def test_get_nonexistent_prompt(library):
    """Test getting a prompt that doesn't exist."""
    prompt = library.get_prompt("nonexistent")
    assert prompt is None


def test_apply_variables(library):
    """Test variable substitution in prompts."""
    library.add_prompt(
        name="greeting",
        prompt="Hello {name}, welcome to {place}!"
    )

    result = library.apply_variables("greeting", {"name": "Alice", "place": "Wonderland"})
    assert result == "Hello Alice, welcome to Wonderland!"


def test_apply_variables_missing_var(library):
    """Test variable substitution with missing variable."""
    library.add_prompt(
        name="test",
        prompt="Hello {name}, you are {age} years old"
    )

    # Should leave unreplaced variables as-is
    result = library.apply_variables("test", {"name": "Bob"})
    assert "Bob" in result
    assert "{age}" in result


def test_list_prompts_limit(library):
    """Test limiting number of results."""
    for i in range(20):
        library.add_prompt(name=f"p{i}", prompt=f"Prompt {i}")

    prompts = library.list_prompts(limit=5)
    assert len(prompts) == 5


def test_prompt_metadata(library):
    """Test that metadata is properly stored."""
    library.add_prompt(
        name="meta",
        prompt="Test",
        metadata={"key1": "value1", "key2": 123}
    )

    prompt = library.get_prompt("meta")
    assert prompt["metadata"]["key1"] == "value1"
    assert prompt["metadata"]["key2"] == 123
