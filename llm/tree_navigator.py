"""
Tree navigation functionality for conversation branches.

Navigate and visualize conversation branch trees.
"""

from typing import Dict, Any, List, Optional, Tuple
import sqlite3
from pathlib import Path

from llm import user_dir


class TreeNavigator:
    """Navigate conversation branch trees."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = user_dir() / "branches.db"
        self.db_path = db_path

    def build_tree(self, conversation_id: str) -> Dict[str, Any]:
        """Build a tree structure of all branches for a conversation."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        # Get all branches
        cursor = conn.execute("""
            SELECT * FROM conversation_branches
            WHERE conversation_id = ?
            ORDER BY created_at ASC
        """, (conversation_id,))

        branches = [dict(row) for row in cursor.fetchall()]
        conn.close()

        if not branches:
            return {
                "conversation_id": conversation_id,
                "branches": [],
                "tree": None
            }

        # Build tree structure
        id_to_branch = {b["id"]: b for b in branches}
        root_branches = []

        for branch in branches:
            branch["children"] = []
            branch["message_count"] = self._get_message_count(branch["id"])

            parent_id = branch["parent_branch_id"]
            if parent_id and parent_id in id_to_branch:
                id_to_branch[parent_id]["children"].append(branch)
            else:
                root_branches.append(branch)

        return {
            "conversation_id": conversation_id,
            "branches": branches,
            "tree": root_branches
        }

    def visualize_tree(self, conversation_id: str, format: str = "ascii") -> str:
        """Visualize conversation tree as text."""
        tree_data = self.build_tree(conversation_id)

        if not tree_data["branches"]:
            return f"No branches found for conversation {conversation_id}"

        if format == "ascii":
            return self._format_ascii_tree(tree_data)
        elif format == "json":
            import json
            return json.dumps(tree_data, indent=2)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def compare_branches(
        self,
        conversation_id: str,
        branch1_name: str,
        branch2_name: str
    ) -> Dict[str, Any]:
        """Compare two branches."""
        from llm.branch_manager import BranchManager

        manager = BranchManager(self.db_path)

        # Get branches
        branch1 = manager.get_branch(conversation_id, branch1_name)
        branch2 = manager.get_branch(conversation_id, branch2_name)

        if not branch1:
            raise ValueError(f"Branch '{branch1_name}' not found")
        if not branch2:
            raise ValueError(f"Branch '{branch2_name}' not found")

        # Get messages for each branch
        messages1 = manager.get_branch_messages(branch1["id"])
        messages2 = manager.get_branch_messages(branch2["id"])

        # Find common ancestor
        common_ancestor = self._find_common_ancestor(branch1, branch2)

        # Find divergence point
        divergence_index = 0
        for i in range(min(len(messages1), len(messages2))):
            if messages1[i]["id"] != messages2[i]["id"]:
                divergence_index = i
                break
        else:
            divergence_index = min(len(messages1), len(messages2))

        common_messages = messages1[:divergence_index]
        branch1_unique = messages1[divergence_index:]
        branch2_unique = messages2[divergence_index:]

        return {
            "branch1": {
                "name": branch1_name,
                "total_messages": len(messages1),
                "unique_messages": len(branch1_unique),
                "messages": branch1_unique
            },
            "branch2": {
                "name": branch2_name,
                "total_messages": len(messages2),
                "unique_messages": len(branch2_unique),
                "messages": branch2_unique
            },
            "common": {
                "messages": len(common_messages),
                "divergence_point": divergence_index
            },
            "common_ancestor": common_ancestor
        }

    def get_branch_path(self, conversation_id: str, branch_name: str) -> List[str]:
        """Get the path from root to a branch."""
        from llm.branch_manager import BranchManager

        manager = BranchManager(self.db_path)
        branch = manager.get_branch(conversation_id, branch_name)

        if not branch:
            raise ValueError(f"Branch '{branch_name}' not found")

        path = [branch_name]
        current_branch = branch

        # Traverse up to root
        while current_branch["parent_branch_id"]:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row

            cursor = conn.execute("""
                SELECT branch_name FROM conversation_branches
                WHERE id = ?
            """, (current_branch["parent_branch_id"],))

            parent = cursor.fetchone()
            conn.close()

            if parent:
                path.insert(0, parent["branch_name"])
                current_branch = manager.get_branch(conversation_id, parent["branch_name"])
            else:
                break

        return path

    def _format_ascii_tree(self, tree_data: Dict[str, Any]) -> str:
        """Format tree as ASCII art."""
        output = []

        output.append("Conversation Branch Tree")
        output.append("=" * 70)
        output.append(f"Conversation ID: {tree_data['conversation_id']}")
        output.append(f"Total branches: {len(tree_data['branches'])}")
        output.append("")

        # Display tree
        for root_branch in tree_data["tree"]:
            self._format_branch_node(root_branch, output, prefix="", is_last=True)

        return "\n".join(output)

    def _format_branch_node(
        self,
        branch: Dict[str, Any],
        output: List[str],
        prefix: str = "",
        is_last: bool = True
    ):
        """Format a single branch node with its children."""
        # Determine connector
        connector = "└─ " if is_last else "├─ "

        # Format branch info
        branch_info = f"{branch['branch_name']} ({branch['message_count']} messages)"
        if branch.get("description"):
            branch_info += f" - {branch['description']}"

        output.append(f"{prefix}{connector}{branch_info}")

        # Prepare prefix for children
        child_prefix = prefix + ("   " if is_last else "│  ")

        # Recursively format children
        children = branch.get("children", [])
        for i, child in enumerate(children):
            is_last_child = (i == len(children) - 1)
            self._format_branch_node(child, output, child_prefix, is_last_child)

    def _get_message_count(self, branch_id: str) -> int:
        """Get count of messages in a branch."""
        conn = sqlite3.connect(str(self.db_path))

        cursor = conn.execute("""
            SELECT COUNT(*) as count FROM branch_messages
            WHERE branch_id = ?
        """, (branch_id,))

        count = cursor.fetchone()[0]
        conn.close()

        return count

    def _find_common_ancestor(
        self,
        branch1: Dict[str, Any],
        branch2: Dict[str, Any]
    ) -> Optional[str]:
        """Find the common ancestor of two branches."""
        # Get all ancestors of branch1
        ancestors1 = set()
        current = branch1
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        while current["parent_branch_id"]:
            ancestors1.add(current["parent_branch_id"])
            cursor = conn.execute("""
                SELECT * FROM conversation_branches WHERE id = ?
            """, (current["parent_branch_id"],))
            row = cursor.fetchone()
            if not row:
                break
            current = dict(row)

        # Traverse branch2's ancestors until we find one in ancestors1
        current = branch2
        while current["parent_branch_id"]:
            if current["parent_branch_id"] in ancestors1:
                # Found common ancestor
                cursor = conn.execute("""
                    SELECT branch_name FROM conversation_branches WHERE id = ?
                """, (current["parent_branch_id"],))
                row = cursor.fetchone()
                conn.close()
                return row["branch_name"] if row else None

            cursor = conn.execute("""
                SELECT * FROM conversation_branches WHERE id = ?
            """, (current["parent_branch_id"],))
            row = cursor.fetchone()
            if not row:
                break
            current = dict(row)

        conn.close()
        return None
