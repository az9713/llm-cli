"""
Conversation branching functionality for LLM CLI.

Create and manage conversation branches to explore different paths.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from llm import user_dir


class BranchManager:
    """Manages conversation branches."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = user_dir() / "branches.db"
        self.db_path = db_path
        self.logs_db_path = user_dir() / "logs.db"
        self._init_db()

    def _init_db(self):
        """Initialize the branches database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))

        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_branches (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                branch_name TEXT NOT NULL,
                parent_branch_id TEXT,
                branch_point_log_id TEXT,
                created_at TEXT NOT NULL,
                description TEXT,
                active BOOLEAN DEFAULT 1,
                UNIQUE(conversation_id, branch_name),
                FOREIGN KEY (parent_branch_id) REFERENCES conversation_branches(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS branch_messages (
                id TEXT PRIMARY KEY,
                branch_id TEXT NOT NULL,
                log_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                FOREIGN KEY (branch_id) REFERENCES conversation_branches(id)
            )
        """)

        # Create indices
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_branches_conversation
            ON conversation_branches(conversation_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_branch_messages_branch
            ON branch_messages(branch_id, sequence)
        """)

        conn.commit()
        conn.close()

    def create_branch(
        self,
        conversation_id: str,
        branch_name: str,
        from_message: Optional[int] = None,
        description: Optional[str] = None,
        parent_branch: Optional[str] = None
    ) -> str:
        """Create a new conversation branch."""
        import ulid

        branch_id = str(ulid.ULID())
        created_at = datetime.utcnow().isoformat()

        # Get conversation messages
        messages = self._get_conversation_messages(conversation_id)
        if not messages:
            raise ValueError(f"Conversation {conversation_id} not found or empty")

        # Determine branch point
        if from_message is not None:
            if from_message < 1 or from_message > len(messages):
                raise ValueError(f"Invalid message number: {from_message}")
            branch_point_log_id = messages[from_message - 1]["id"]
            branch_messages = messages[:from_message]
        else:
            # Branch from current state (all messages)
            branch_point_log_id = messages[-1]["id"] if messages else None
            branch_messages = messages

        # Get parent branch ID if specified
        parent_branch_id = None
        if parent_branch:
            parent_branch_id = self._get_branch_id(conversation_id, parent_branch)
            if not parent_branch_id:
                raise ValueError(f"Parent branch '{parent_branch}' not found")

        # Create branch
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                INSERT INTO conversation_branches (
                    id, conversation_id, branch_name, parent_branch_id,
                    branch_point_log_id, created_at, description, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                branch_id, conversation_id, branch_name, parent_branch_id,
                branch_point_log_id, created_at, description, True
            ))

            # Add messages to branch
            for i, msg in enumerate(branch_messages):
                msg_id = str(ulid.ULID())
                conn.execute("""
                    INSERT INTO branch_messages (id, branch_id, log_id, sequence)
                    VALUES (?, ?, ?, ?)
                """, (msg_id, branch_id, msg["id"], i))

            conn.commit()
        finally:
            conn.close()

        return branch_id

    def get_branch(self, conversation_id: str, branch_name: str) -> Optional[Dict[str, Any]]:
        """Get branch details."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT * FROM conversation_branches
            WHERE conversation_id = ? AND branch_name = ?
        """, (conversation_id, branch_name))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        branch = dict(row)

        # Get message count
        branch["message_count"] = self._get_branch_message_count(branch["id"])

        return branch

    def list_branches(self, conversation_id: str, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """List all branches for a conversation."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        query = """
            SELECT * FROM conversation_branches
            WHERE conversation_id = ?
        """
        params = [conversation_id]

        if not include_inactive:
            query += " AND active = 1"

        query += " ORDER BY created_at DESC"

        cursor = conn.execute(query, params)
        branches = []

        for row in cursor.fetchall():
            branch = dict(row)
            branch["message_count"] = self._get_branch_message_count(branch["id"])
            branches.append(branch)

        conn.close()

        return branches

    def get_branch_messages(self, branch_id: str) -> List[Dict[str, Any]]:
        """Get all messages in a branch."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT log_id FROM branch_messages
            WHERE branch_id = ?
            ORDER BY sequence ASC
        """, (branch_id,))

        log_ids = [row["log_id"] for row in cursor.fetchall()]
        conn.close()

        # Get actual messages from logs database
        if not log_ids:
            return []

        return self._get_messages_by_ids(log_ids)

    def rename_branch(self, conversation_id: str, old_name: str, new_name: str) -> bool:
        """Rename a branch."""
        conn = sqlite3.connect(str(self.db_path))

        try:
            cursor = conn.execute("""
                UPDATE conversation_branches
                SET branch_name = ?
                WHERE conversation_id = ? AND branch_name = ?
            """, (new_name, conversation_id, old_name))

            conn.commit()
            updated = cursor.rowcount > 0
        except sqlite3.IntegrityError:
            # Branch with new name already exists
            updated = False
        finally:
            conn.close()

        return updated

    def delete_branch(self, conversation_id: str, branch_name: str, force: bool = False) -> bool:
        """Delete a branch."""
        # Get branch
        branch = self.get_branch(conversation_id, branch_name)
        if not branch:
            return False

        # Check if it has children
        if not force and self._has_child_branches(branch["id"]):
            raise ValueError(
                f"Branch '{branch_name}' has child branches. "
                "Use --force to delete it and all children."
            )

        conn = sqlite3.connect(str(self.db_path))

        try:
            # Delete child branches recursively if force
            if force:
                self._delete_child_branches(conn, branch["id"])

            # Delete branch messages
            conn.execute("""
                DELETE FROM branch_messages WHERE branch_id = ?
            """, (branch["id"],))

            # Delete branch
            conn.execute("""
                DELETE FROM conversation_branches WHERE id = ?
            """, (branch["id"],))

            conn.commit()
            deleted = True
        finally:
            conn.close()

        return deleted

    def archive_branch(self, conversation_id: str, branch_name: str) -> bool:
        """Archive a branch (set active=0)."""
        conn = sqlite3.connect(str(self.db_path))

        cursor = conn.execute("""
            UPDATE conversation_branches
            SET active = 0
            WHERE conversation_id = ? AND branch_name = ?
        """, (conversation_id, branch_name))

        conn.commit()
        updated = cursor.rowcount > 0
        conn.close()

        return updated

    def get_current_branch(self, conversation_id: str) -> Optional[str]:
        """Get the currently active branch for a conversation."""
        # This would need integration with conversation tracking
        # For now, return None (main branch)
        return None

    def _get_conversation_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a conversation from logs database."""
        if not self.logs_db_path.exists():
            return []

        conn = sqlite3.connect(str(self.logs_db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT * FROM responses
            WHERE conversation_id = ?
            ORDER BY datetime_utc ASC
        """, (conversation_id,))

        messages = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return messages

    def _get_messages_by_ids(self, log_ids: List[str]) -> List[Dict[str, Any]]:
        """Get messages by their log IDs."""
        if not self.logs_db_path.exists():
            return []

        conn = sqlite3.connect(str(self.logs_db_path))
        conn.row_factory = sqlite3.Row

        # Create placeholders for IN clause
        placeholders = ','.join('?' * len(log_ids))

        cursor = conn.execute(f"""
            SELECT * FROM responses
            WHERE id IN ({placeholders})
        """, log_ids)

        messages = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Sort by the order of log_ids
        id_to_msg = {msg["id"]: msg for msg in messages}
        return [id_to_msg[log_id] for log_id in log_ids if log_id in id_to_msg]

    def _get_branch_id(self, conversation_id: str, branch_name: str) -> Optional[str]:
        """Get branch ID by name."""
        branch = self.get_branch(conversation_id, branch_name)
        return branch["id"] if branch else None

    def _get_branch_message_count(self, branch_id: str) -> int:
        """Get count of messages in a branch."""
        conn = sqlite3.connect(str(self.db_path))

        cursor = conn.execute("""
            SELECT COUNT(*) as count FROM branch_messages
            WHERE branch_id = ?
        """, (branch_id,))

        count = cursor.fetchone()[0]
        conn.close()

        return count

    def _has_child_branches(self, branch_id: str) -> bool:
        """Check if a branch has children."""
        conn = sqlite3.connect(str(self.db_path))

        cursor = conn.execute("""
            SELECT COUNT(*) FROM conversation_branches
            WHERE parent_branch_id = ?
        """, (branch_id,))

        count = cursor.fetchone()[0]
        conn.close()

        return count > 0

    def _delete_child_branches(self, conn: sqlite3.Connection, branch_id: str):
        """Recursively delete child branches."""
        # Get children
        cursor = conn.execute("""
            SELECT id FROM conversation_branches
            WHERE parent_branch_id = ?
        """, (branch_id,))

        child_ids = [row[0] for row in cursor.fetchall()]

        # Recursively delete their children
        for child_id in child_ids:
            self._delete_child_branches(conn, child_id)

        # Delete children messages
        for child_id in child_ids:
            conn.execute("""
                DELETE FROM branch_messages WHERE branch_id = ?
            """, (child_id,))

        # Delete children
        conn.execute("""
            DELETE FROM conversation_branches
            WHERE parent_branch_id = ?
        """, (branch_id,))
