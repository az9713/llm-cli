"""Tests for Conversation Branching feature."""
import pytest
from unittest.mock import Mock, patch
from llm.branch_manager import BranchManager


@pytest.fixture
def branch_manager(user_path):
    """Create a BranchManager instance."""
    db_path = user_path / "test_branches.db"
    return BranchManager(db_path=db_path)


def test_create_branch(branch_manager):
    """Test creating a branch."""
    with patch.object(branch_manager, '_get_conversation_messages') as mock_get:
        mock_get.return_value = [
            {"id": "msg1", "prompt": "Q1", "response": "A1"},
            {"id": "msg2", "prompt": "Q2", "response": "A2"}
        ]

        branch_id = branch_manager.create_branch(
            conversation_id="conv-123",
            branch_name="test-branch",
            description="Test branch"
        )

        assert branch_id is not None
        assert len(branch_id) > 0


def test_get_branch(branch_manager):
    """Test getting branch details."""
    with patch.object(branch_manager, '_get_conversation_messages') as mock_get:
        mock_get.return_value = [
            {"id": "msg1", "prompt": "Q1", "response": "A1"}
        ]

        branch_id = branch_manager.create_branch("conv-123", "test-branch")
        branch = branch_manager.get_branch("conv-123", "test-branch")

        assert branch is not None
        assert branch["branch_name"] == "test-branch"
        assert branch["conversation_id"] == "conv-123"


def test_list_branches(branch_manager):
    """Test listing branches."""
    with patch.object(branch_manager, '_get_conversation_messages') as mock_get:
        mock_get.return_value = [{"id": "msg1", "prompt": "Q", "response": "A"}]

        branch_manager.create_branch("conv-123", "branch1")
        branch_manager.create_branch("conv-123", "branch2")

        branches = branch_manager.list_branches("conv-123")

        assert len(branches) == 2
        assert any(b["branch_name"] == "branch1" for b in branches)
        assert any(b["branch_name"] == "branch2" for b in branches)


def test_rename_branch(branch_manager):
    """Test renaming a branch."""
    with patch.object(branch_manager, '_get_conversation_messages') as mock_get:
        mock_get.return_value = [{"id": "msg1", "prompt": "Q", "response": "A"}]

        branch_manager.create_branch("conv-123", "old-name")
        success = branch_manager.rename_branch("conv-123", "old-name", "new-name")

        assert success is True

        branch = branch_manager.get_branch("conv-123", "new-name")
        assert branch is not None


def test_delete_branch(branch_manager):
    """Test deleting a branch."""
    with patch.object(branch_manager, '_get_conversation_messages') as mock_get:
        mock_get.return_value = [{"id": "msg1", "prompt": "Q", "response": "A"}]

        branch_manager.create_branch("conv-123", "to-delete")
        success = branch_manager.delete_branch("conv-123", "to-delete")

        assert success is True

        branch = branch_manager.get_branch("conv-123", "to-delete")
        assert branch is None


def test_create_branch_from_message(branch_manager):
    """Test creating branch from specific message."""
    with patch.object(branch_manager, '_get_conversation_messages') as mock_get:
        mock_get.return_value = [
            {"id": "msg1", "prompt": "Q1", "response": "A1"},
            {"id": "msg2", "prompt": "Q2", "response": "A2"},
            {"id": "msg3", "prompt": "Q3", "response": "A3"}
        ]

        branch_id = branch_manager.create_branch(
            "conv-123",
            "partial-branch",
            from_message=2
        )

        assert branch_id is not None


def test_archive_branch(branch_manager):
    """Test archiving a branch."""
    with patch.object(branch_manager, '_get_conversation_messages') as mock_get:
        mock_get.return_value = [{"id": "msg1", "prompt": "Q", "response": "A"}]

        branch_manager.create_branch("conv-123", "to-archive")
        success = branch_manager.archive_branch("conv-123", "to-archive")

        assert success is True

        # Should not appear in active list
        branches = branch_manager.list_branches("conv-123", include_inactive=False)
        assert not any(b["branch_name"] == "to-archive" for b in branches)

        # Should appear in full list
        all_branches = branch_manager.list_branches("conv-123", include_inactive=True)
        assert any(b["branch_name"] == "to-archive" for b in all_branches)
