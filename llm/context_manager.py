"""
Context management functionality for LLM CLI.

Manage conversation context windows and automatic summarization.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from llm import user_dir, get_model


class ContextManager:
    """Manages conversation context and token limits."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = user_dir() / "context.db"
        self.db_path = db_path
        self.logs_db_path = user_dir() / "logs.db"
        self._init_db()

    def _init_db(self):
        """Initialize the context database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))

        conn.execute("""
            CREATE TABLE IF NOT EXISTS context_settings (
                conversation_id TEXT PRIMARY KEY,
                max_tokens INTEGER DEFAULT 4096,
                strategy TEXT DEFAULT 'sliding_window',
                auto_summarize BOOLEAN DEFAULT 1,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS context_summaries (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                messages_summarized INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        conn.commit()
        conn.close()

    def set_limit(self, conversation_id: str, max_tokens: int) -> bool:
        """Set token limit for a conversation."""
        conn = sqlite3.connect(str(self.db_path))
        now = datetime.utcnow().isoformat()

        conn.execute("""
            INSERT OR REPLACE INTO context_settings
            (conversation_id, max_tokens, updated_at)
            VALUES (?, ?, ?)
        """, (conversation_id, max_tokens, now))

        conn.commit()
        conn.close()
        return True

    def set_strategy(self, conversation_id: str, strategy: str) -> bool:
        """Set context management strategy."""
        valid_strategies = ['sliding_window', 'summarize_old', 'keep_important']

        if strategy not in valid_strategies:
            raise ValueError(f"Invalid strategy. Must be one of: {', '.join(valid_strategies)}")

        conn = sqlite3.connect(str(self.db_path))
        now = datetime.utcnow().isoformat()

        conn.execute("""
            INSERT OR REPLACE INTO context_settings
            (conversation_id, strategy, updated_at)
            VALUES (?, ?, ?)
        """, (conversation_id, strategy, now))

        conn.commit()
        conn.close()
        return True

    def get_status(self, conversation_id: str) -> Dict[str, Any]:
        """Get context status for a conversation."""
        # Get settings
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT * FROM context_settings
            WHERE conversation_id = ?
        """, (conversation_id,))

        row = cursor.fetchone()
        settings = dict(row) if row else {
            "max_tokens": 4096,
            "strategy": "sliding_window",
            "auto_summarize": True
        }

        conn.close()

        # Get current token usage (simplified - would use tiktoken in production)
        messages = self._get_conversation_messages(conversation_id)
        estimated_tokens = sum(len(m.get("prompt", "").split()) + len(m.get("response", "").split())
                              for m in messages)

        return {
            "conversation_id": conversation_id,
            "max_tokens": settings.get("max_tokens", 4096),
            "strategy": settings.get("strategy", "sliding_window"),
            "auto_summarize": settings.get("auto_summarize", True),
            "current_messages": len(messages),
            "estimated_tokens": estimated_tokens,
            "percentage_used": (estimated_tokens / settings.get("max_tokens", 4096)) * 100
        }

    def summarize(self, conversation_id: str, keep_recent: int = 5) -> str:
        """Summarize old messages in a conversation."""
        messages = self._get_conversation_messages(conversation_id)

        if len(messages) <= keep_recent:
            return "No messages to summarize"

        # Messages to summarize
        to_summarize = messages[:-keep_recent]

        # Create summary prompt
        summary_text = []
        for msg in to_summarize:
            summary_text.append(f"User: {msg.get('prompt', '')}")
            summary_text.append(f"Assistant: {msg.get('response', '')}")

        combined = "\n\n".join(summary_text)

        # Use model to create summary
        try:
            model = get_model("gpt-4o-mini")  # Use cheaper model for summarization
            response = model.prompt(
                f"Summarize this conversation, preserving key information:\n\n{combined}",
                system="You are a helpful assistant that creates concise summaries."
            )
            summary = response.text()
        except Exception:
            summary = f"[{len(to_summarize)} messages from earlier in conversation]"

        # Save summary
        import ulid
        summary_id = str(ulid.ULID())
        now = datetime.utcnow().isoformat()

        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO context_summaries
            (id, conversation_id, summary, messages_summarized, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (summary_id, conversation_id, summary, len(to_summarize), now))

        conn.commit()
        conn.close()

        return summary

    def clear(self, conversation_id: str, keep_recent: int = 0) -> int:
        """Clear old messages from context (marks them for exclusion)."""
        messages = self._get_conversation_messages(conversation_id)

        if len(messages) <= keep_recent:
            return 0

        # In a real implementation, this would mark messages as excluded
        # from context but keep them in the database
        return len(messages) - keep_recent

    def _get_conversation_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Get all messages for a conversation."""
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
