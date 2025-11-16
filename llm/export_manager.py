"""
Export functionality for LLM CLI.

Export conversations, comparisons, and batch results to various formats.
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from llm import user_dir


class ExportManager:
    """Manages exporting LLM data to various formats."""

    def __init__(self):
        self.logs_db_path = user_dir() / "logs.db"
        self.comparisons_db_path = user_dir() / "comparisons.db"
        self.batch_db_path = user_dir() / "batch.db"

    def export_conversation(
        self,
        conversation_id: str,
        output_format: str,
        output_file: Optional[Path] = None,
        template: Optional[str] = None,
        include_system: bool = True
    ) -> str:
        """Export a conversation to specified format."""
        # Get conversation data
        conversation_data = self._get_conversation_data(conversation_id)

        if not conversation_data:
            raise ValueError(f"Conversation {conversation_id} not found")

        # Export based on format
        if output_format == "html":
            from llm.exporters.html import HTMLExporter
            exporter = HTMLExporter(template=template)
            content = exporter.export_conversation(conversation_data, include_system=include_system)
        elif output_format == "markdown":
            from llm.exporters.markdown import MarkdownExporter
            exporter = MarkdownExporter()
            content = exporter.export_conversation(conversation_data, include_system=include_system)
        elif output_format == "json":
            content = json.dumps(conversation_data, indent=2)
        elif output_format == "text":
            content = self._format_conversation_text(conversation_data, include_system=include_system)
        else:
            raise ValueError(f"Unsupported format: {output_format}")

        # Write to file if specified
        if output_file:
            output_file = Path(output_file)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            return str(output_file)

        return content

    def export_comparison(
        self,
        comparison_id: str,
        output_format: str,
        output_file: Optional[Path] = None,
        template: Optional[str] = None
    ) -> str:
        """Export a model comparison to specified format."""
        # Get comparison data
        comparison_data = self._get_comparison_data(comparison_id)

        if not comparison_data:
            raise ValueError(f"Comparison {comparison_id} not found")

        # Export based on format
        if output_format == "html":
            from llm.exporters.html import HTMLExporter
            exporter = HTMLExporter(template=template)
            content = exporter.export_comparison(comparison_data)
        elif output_format == "markdown":
            from llm.exporters.markdown import MarkdownExporter
            exporter = MarkdownExporter()
            content = exporter.export_comparison(comparison_data)
        elif output_format == "json":
            content = json.dumps(comparison_data, indent=2)
        else:
            raise ValueError(f"Unsupported format: {output_format}")

        # Write to file if specified
        if output_file:
            output_file = Path(output_file)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            return str(output_file)

        return content

    def export_batch(
        self,
        batch_id: str,
        output_format: str,
        output_file: Optional[Path] = None
    ) -> str:
        """Export batch results to specified format."""
        # Get batch data
        batch_data = self._get_batch_data(batch_id)

        if not batch_data:
            raise ValueError(f"Batch {batch_id} not found")

        # Export based on format
        if output_format == "csv":
            import csv
            output_file = Path(output_file) if output_file else Path(f"batch_{batch_id}.csv")

            results = batch_data.get("results", [])
            fieldnames = ["index", "prompt", "response", "success", "error", "tokens", "cost"]

            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for result in results:
                    writer.writerow({
                        "index": result.get("prompt_index", ""),
                        "prompt": result.get("prompt", ""),
                        "response": result.get("response", ""),
                        "success": result.get("success", False),
                        "error": result.get("error", ""),
                        "tokens": result.get("tokens_used", 0),
                        "cost": result.get("cost", 0)
                    })

            return str(output_file)
        elif output_format == "json":
            content = json.dumps(batch_data, indent=2)
        else:
            raise ValueError(f"Unsupported format: {output_format}")

        # Write to file if specified
        if output_file:
            output_file = Path(output_file)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(content)
            return str(output_file)

        return content

    def _get_conversation_data(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation data from logs database."""
        if not self.logs_db_path.exists():
            return None

        conn = sqlite3.connect(str(self.logs_db_path))
        conn.row_factory = sqlite3.Row

        # Get conversation info
        cursor = conn.execute(
            "SELECT * FROM conversations WHERE id = ?",
            (conversation_id,)
        )
        conversation = cursor.fetchone()

        if not conversation:
            conn.close()
            return None

        # Get messages
        cursor = conn.execute(
            """
            SELECT * FROM responses
            WHERE conversation_id = ?
            ORDER BY datetime_utc ASC
            """,
            (conversation_id,)
        )
        messages = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return {
            "id": conversation_id,
            "name": conversation["name"] if conversation else None,
            "model": conversation["model"] if conversation else None,
            "messages": messages
        }

    def _get_comparison_data(self, comparison_id: str) -> Optional[Dict[str, Any]]:
        """Get comparison data from comparisons database."""
        if not self.comparisons_db_path.exists():
            return None

        conn = sqlite3.connect(str(self.comparisons_db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute(
            "SELECT * FROM comparisons WHERE id = ?",
            (comparison_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        comparison = dict(row)
        comparison['models'] = json.loads(comparison['models'])
        comparison['responses'] = json.loads(comparison['responses'])
        comparison['metrics'] = json.loads(comparison['metrics'])

        return comparison

    def _get_batch_data(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Get batch data from batch database."""
        if not self.batch_db_path.exists():
            return None

        conn = sqlite3.connect(str(self.batch_db_path))
        conn.row_factory = sqlite3.Row

        # Get batch run info
        cursor = conn.execute(
            "SELECT * FROM batch_runs WHERE id = ?",
            (batch_id,)
        )
        batch_run = cursor.fetchone()

        if not batch_run:
            conn.close()
            return None

        # Get results
        cursor = conn.execute(
            "SELECT * FROM batch_results WHERE batch_id = ? ORDER BY prompt_index",
            (batch_id,)
        )
        results = [dict(row) for row in cursor.fetchall()]

        conn.close()

        batch_data = dict(batch_run)
        if batch_data.get('config'):
            batch_data['config'] = json.loads(batch_data['config'])
        batch_data['results'] = results

        return batch_data

    def _format_conversation_text(
        self,
        conversation_data: Dict[str, Any],
        include_system: bool = True
    ) -> str:
        """Format conversation as plain text."""
        output = []

        output.append("=" * 70)
        output.append(f"CONVERSATION: {conversation_data.get('name', 'Untitled')}")
        output.append(f"Model: {conversation_data.get('model', 'Unknown')}")
        output.append("=" * 70)
        output.append("")

        for msg in conversation_data.get("messages", []):
            system = msg.get("system")
            prompt = msg.get("prompt", "")
            response = msg.get("response", "")

            if include_system and system:
                output.append("-" * 70)
                output.append("SYSTEM:")
                output.append(system)

            output.append("-" * 70)
            output.append("USER:")
            output.append(prompt)
            output.append("")
            output.append("ASSISTANT:")
            output.append(response)
            output.append("")

        return "\n".join(output)
