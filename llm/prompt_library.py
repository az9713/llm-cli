"""
Prompt library management for LLM CLI.

Provides functionality to save, organize, search, and reuse prompts.
"""

import json
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any
import click
from pathlib import Path
import yaml

from llm import user_dir


class PromptLibrary:
    """Manages a library of reusable prompts."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = user_dir() / "prompts.db"
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the prompts database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prompt_library (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                prompt TEXT NOT NULL,
                system_prompt TEXT,
                description TEXT,
                category TEXT,
                tags TEXT,
                author TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                model TEXT,
                parameters JSON,
                metadata JSON,
                usage_count INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 1.0,
                avg_cost REAL DEFAULT 0.0,
                source TEXT DEFAULT 'personal',
                parent_id TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS prompt_usage (
                id TEXT PRIMARY KEY,
                prompt_id TEXT NOT NULL,
                used_at TEXT NOT NULL,
                log_id TEXT,
                success BOOLEAN DEFAULT 1,
                cost REAL DEFAULT 0.0,
                rating INTEGER,
                FOREIGN KEY (prompt_id) REFERENCES prompt_library(id)
            )
        """)

        conn.commit()
        conn.close()

    def add_prompt(
        self,
        name: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        author: Optional[str] = None,
        model: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Add a new prompt to the library."""
        import ulid

        prompt_id = str(ulid.ULID())
        now = datetime.utcnow().isoformat()

        tags_json = json.dumps(tags) if tags else None
        parameters_json = json.dumps(parameters) if parameters else None
        metadata_json = json.dumps(metadata) if metadata else None

        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                INSERT INTO prompt_library (
                    id, name, prompt, system_prompt, description, category,
                    tags, author, created_at, updated_at, model, parameters, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                prompt_id, name, prompt, system_prompt, description, category,
                tags_json, author, now, now, model, parameters_json, metadata_json
            ))
            conn.commit()
        finally:
            conn.close()

        return prompt_id

    def get_prompt(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a prompt by name."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.execute(
                "SELECT * FROM prompt_library WHERE name = ?", (name,)
            )
            row = cursor.fetchone()

            if row is None:
                return None

            prompt = dict(row)
            # Parse JSON fields
            if prompt['tags']:
                prompt['tags'] = json.loads(prompt['tags'])
            if prompt['parameters']:
                prompt['parameters'] = json.loads(prompt['parameters'])
            if prompt['metadata']:
                prompt['metadata'] = json.loads(prompt['metadata'])

            return prompt
        finally:
            conn.close()

    def list_prompts(
        self,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        author: Optional[str] = None,
        source: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """List prompts with optional filters."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        query = "SELECT * FROM prompt_library WHERE 1=1"
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)
        if author:
            query += " AND author = ?"
            params.append(author)
        if source:
            query += " AND source = ?"
            params.append(source)
        if tag:
            query += " AND tags LIKE ?"
            params.append(f'%{tag}%')

        query += " ORDER BY created_at DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        try:
            cursor = conn.execute(query, params)
            prompts = []
            for row in cursor.fetchall():
                prompt = dict(row)
                if prompt['tags']:
                    prompt['tags'] = json.loads(prompt['tags'])
                prompts.append(prompt)
            return prompts
        finally:
            conn.close()

    def search_prompts(self, query: str) -> List[Dict[str, Any]]:
        """Search prompts by name or description."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.execute("""
                SELECT * FROM prompt_library
                WHERE name LIKE ? OR description LIKE ? OR prompt LIKE ?
                ORDER BY usage_count DESC
            """, (f'%{query}%', f'%{query}%', f'%{query}%'))

            prompts = []
            for row in cursor.fetchall():
                prompt = dict(row)
                if prompt['tags']:
                    prompt['tags'] = json.loads(prompt['tags'])
                prompts.append(prompt)
            return prompts
        finally:
            conn.close()

    def update_prompt(
        self,
        name: str,
        prompt: Optional[str] = None,
        system_prompt: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        create_version: bool = False
    ) -> bool:
        """Update an existing prompt."""
        existing = self.get_prompt(name)
        if not existing:
            return False

        now = datetime.utcnow().isoformat()
        updates = []
        params = []

        if prompt is not None:
            updates.append("prompt = ?")
            params.append(prompt)
        if system_prompt is not None:
            updates.append("system_prompt = ?")
            params.append(system_prompt)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if category is not None:
            updates.append("category = ?")
            params.append(category)
        if tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(tags))

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(now)

        if create_version:
            updates.append("version = version + 1")

        params.append(name)

        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                f"UPDATE prompt_library SET {', '.join(updates)} WHERE name = ?",
                params
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def delete_prompt(self, name: str) -> bool:
        """Delete a prompt from the library."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.execute(
                "DELETE FROM prompt_library WHERE name = ?", (name,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def increment_usage(self, name: str, cost: float = 0.0, success: bool = True):
        """Track prompt usage."""
        import ulid

        prompt = self.get_prompt(name)
        if not prompt:
            return

        usage_id = str(ulid.ULID())
        now = datetime.utcnow().isoformat()

        conn = sqlite3.connect(str(self.db_path))
        try:
            # Record usage
            conn.execute("""
                INSERT INTO prompt_usage (id, prompt_id, used_at, success, cost)
                VALUES (?, ?, ?, ?, ?)
            """, (usage_id, prompt['id'], now, success, cost))

            # Update aggregate stats
            conn.execute("""
                UPDATE prompt_library
                SET usage_count = usage_count + 1,
                    avg_cost = (avg_cost * usage_count + ?) / (usage_count + 1)
                WHERE id = ?
            """, (cost, prompt['id']))

            conn.commit()
        finally:
            conn.close()

    def export_prompt(self, name: str, format: str = 'yaml') -> Optional[str]:
        """Export a prompt to YAML or JSON."""
        prompt = self.get_prompt(name)
        if not prompt:
            return None

        # Remove internal fields
        export_data = {
            'name': prompt['name'],
            'prompt': prompt['prompt'],
            'system_prompt': prompt['system_prompt'],
            'description': prompt['description'],
            'category': prompt['category'],
            'tags': prompt['tags'],
            'model': prompt['model'],
        }

        if format == 'yaml':
            return yaml.dump(export_data, default_flow_style=False)
        else:
            return json.dumps(export_data, indent=2)

    def import_prompt(self, data: str, format: str = 'yaml', overwrite: bool = False) -> Optional[str]:
        """Import a prompt from YAML or JSON."""
        try:
            if format == 'yaml':
                prompt_data = yaml.safe_load(data)
            else:
                prompt_data = json.loads(data)

            name = prompt_data.get('name')
            if not name:
                raise ValueError("Prompt name is required")

            # Check if exists
            existing = self.get_prompt(name)
            if existing and not overwrite:
                raise ValueError(f"Prompt '{name}' already exists. Use --overwrite to replace.")

            if existing:
                # Update existing
                self.update_prompt(
                    name=name,
                    prompt=prompt_data.get('prompt'),
                    system_prompt=prompt_data.get('system_prompt'),
                    description=prompt_data.get('description'),
                    category=prompt_data.get('category'),
                    tags=prompt_data.get('tags')
                )
                return name
            else:
                # Add new
                return self.add_prompt(
                    name=name,
                    prompt=prompt_data['prompt'],
                    system_prompt=prompt_data.get('system_prompt'),
                    description=prompt_data.get('description'),
                    category=prompt_data.get('category'),
                    tags=prompt_data.get('tags'),
                    model=prompt_data.get('model')
                )
        except Exception as e:
            raise ValueError(f"Failed to import prompt: {e}")
