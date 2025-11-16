"""
Batch processing functionality for LLM CLI.

Process multiple prompts from files efficiently.
"""

import csv
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterator
import re

from llm import get_model, user_dir


class BatchProcessor:
    """Manages batch processing of prompts."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = user_dir() / "batch.db"
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the batch processing database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))

        conn.execute("""
            CREATE TABLE IF NOT EXISTS batch_runs (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                input_file TEXT NOT NULL,
                output_file TEXT,
                model TEXT NOT NULL,
                total_prompts INTEGER DEFAULT 0,
                completed_prompts INTEGER DEFAULT 0,
                failed_prompts INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                config JSON,
                started_at TEXT,
                completed_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS batch_results (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                prompt_index INTEGER NOT NULL,
                prompt TEXT NOT NULL,
                response TEXT,
                success BOOLEAN DEFAULT 1,
                error TEXT,
                tokens_used INTEGER DEFAULT 0,
                cost REAL DEFAULT 0,
                processed_at TEXT,
                FOREIGN KEY (batch_id) REFERENCES batch_runs(id)
            )
        """)

        conn.commit()
        conn.close()

    def load_prompts_from_file(
        self,
        file_path: Path,
        template: Optional[str] = None
    ) -> Iterator[Dict[str, Any]]:
        """Load prompts from various file formats."""
        file_path = Path(file_path)

        if file_path.suffix == '.csv':
            yield from self._load_from_csv(file_path, template)
        elif file_path.suffix in ['.json', '.jsonl']:
            yield from self._load_from_json(file_path, template)
        else:
            # Treat as plain text file with one prompt per line
            yield from self._load_from_text(file_path)

    def _load_from_csv(self, file_path: Path, template: Optional[str]) -> Iterator[Dict[str, Any]]:
        """Load prompts from CSV file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                if template:
                    # Substitute variables in template
                    prompt = template
                    for key, value in row.items():
                        prompt = prompt.replace(f"{{{key}}}", str(value))
                    yield {'index': idx, 'prompt': prompt, 'data': row}
                else:
                    # Use first column as prompt
                    first_col = list(row.values())[0]
                    yield {'index': idx, 'prompt': first_col, 'data': row}

    def _load_from_json(self, file_path: Path, template: Optional[str]) -> Iterator[Dict[str, Any]]:
        """Load prompts from JSON or JSONL file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            if file_path.suffix == '.jsonl':
                # JSON Lines format
                for idx, line in enumerate(f):
                    data = json.loads(line)
                    prompt = self._apply_template(template, data) if template else str(data)
                    yield {'index': idx, 'prompt': prompt, 'data': data}
            else:
                # Regular JSON
                data_list = json.load(f)
                if isinstance(data_list, list):
                    for idx, data in enumerate(data_list):
                        prompt = self._apply_template(template, data) if template else str(data)
                        yield {'index': idx, 'prompt': prompt, 'data': data}
                else:
                    prompt = self._apply_template(template, data_list) if template else str(data_list)
                    yield {'index': 0, 'prompt': prompt, 'data': data_list}

    def _load_from_text(self, file_path: Path) -> Iterator[Dict[str, Any]]:
        """Load prompts from plain text file (one per line)."""
        with open(file_path, 'r', encoding='utf-8') as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if line:  # Skip empty lines
                    yield {'index': idx, 'prompt': line, 'data': {}}

    def _apply_template(self, template: str, data: Dict[str, Any]) -> str:
        """Apply template with variable substitution."""
        if not template:
            return str(data)

        prompt = template
        for key, value in data.items():
            prompt = prompt.replace(f"{{{key}}}", str(value))
        return prompt

    def process_batch(
        self,
        input_file: Path,
        model_name: str,
        template: Optional[str] = None,
        system: Optional[str] = None,
        output_file: Optional[Path] = None,
        rate_limit: Optional[int] = None,
        max_prompts: Optional[int] = None
    ) -> str:
        """Process a batch of prompts."""
        import ulid

        batch_id = str(ulid.ULID())
        created_at = datetime.utcnow().isoformat()

        # Load prompts
        prompts = list(self.load_prompts_from_file(input_file, template))
        total_prompts = len(prompts)

        if max_prompts:
            prompts = prompts[:max_prompts]
            total_prompts = len(prompts)

        # Create batch run record
        config = {
            'template': template,
            'system': system,
            'rate_limit': rate_limit,
            'max_prompts': max_prompts
        }

        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO batch_runs (
                id, created_at, input_file, output_file, model,
                total_prompts, status, config, started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            batch_id, created_at, str(input_file), str(output_file) if output_file else None,
            model_name, total_prompts, 'running', json.dumps(config), datetime.utcnow().isoformat()
        ))
        conn.commit()
        conn.close()

        # Process prompts
        model = get_model(model_name)
        results = []
        completed = 0
        failed = 0

        for prompt_data in prompts:
            try:
                # Rate limiting
                if rate_limit and completed > 0:
                    time.sleep(60 / rate_limit)  # Sleep to maintain rate limit

                response = model.prompt(prompt_data['prompt'], system=system)
                response_text = response.text()

                # Get token usage if available
                tokens_used = 0
                if hasattr(response, 'input_tokens') and hasattr(response, 'output_tokens'):
                    tokens_used = response.input_tokens + response.output_tokens

                # Calculate cost
                cost = 0.0
                if hasattr(response, 'input_tokens') and hasattr(response, 'output_tokens'):
                    from llm.cost_tracking import CostTracker
                    tracker = CostTracker()
                    cost = tracker.calculate_cost(model_name, response.input_tokens, response.output_tokens)

                result = {
                    'index': prompt_data['index'],
                    'prompt': prompt_data['prompt'],
                    'response': response_text,
                    'success': True,
                    'error': None,
                    'tokens': tokens_used,
                    'cost': cost,
                    'data': prompt_data.get('data', {})
                }

                results.append(result)
                completed += 1

                # Save result to database
                self._save_result(batch_id, result)

                # Update progress
                self._update_progress(batch_id, completed, failed)

            except Exception as e:
                result = {
                    'index': prompt_data['index'],
                    'prompt': prompt_data['prompt'],
                    'response': None,
                    'success': False,
                    'error': str(e),
                    'tokens': 0,
                    'cost': 0,
                    'data': prompt_data.get('data', {})
                }

                results.append(result)
                failed += 1

                self._save_result(batch_id, result)
                self._update_progress(batch_id, completed, failed)

        # Mark batch as completed
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            UPDATE batch_runs
            SET status = ?, completed_at = ?
            WHERE id = ?
        """, ('completed', datetime.utcnow().isoformat(), batch_id))
        conn.commit()
        conn.close()

        # Save results to output file if specified
        if output_file:
            self._save_output_file(output_file, results, input_file)

        return batch_id

    def _save_result(self, batch_id: str, result: Dict[str, Any]):
        """Save a batch result to database."""
        import ulid

        result_id = str(ulid.ULID())

        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO batch_results (
                id, batch_id, prompt_index, prompt, response,
                success, error, tokens_used, cost, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result_id, batch_id, result['index'], result['prompt'],
            result['response'], result['success'], result['error'],
            result['tokens'], result['cost'], datetime.utcnow().isoformat()
        ))
        conn.commit()
        conn.close()

    def _update_progress(self, batch_id: str, completed: int, failed: int):
        """Update batch progress."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            UPDATE batch_runs
            SET completed_prompts = ?, failed_prompts = ?
            WHERE id = ?
        """, (completed, failed, batch_id))
        conn.commit()
        conn.close()

    def _save_output_file(self, output_file: Path, results: List[Dict[str, Any]], input_file: Path):
        """Save results to output file."""
        output_file = Path(output_file)

        if output_file.suffix == '.csv':
            self._save_to_csv(output_file, results, input_file)
        elif output_file.suffix == '.json':
            self._save_to_json(output_file, results)
        elif output_file.suffix == '.jsonl':
            self._save_to_jsonl(output_file, results)
        else:
            # Plain text
            with open(output_file, 'w', encoding='utf-8') as f:
                for result in results:
                    if result['success']:
                        f.write(f"{result['response']}\n\n")

    def _save_to_csv(self, output_file: Path, results: List[Dict[str, Any]], input_file: Path):
        """Save results to CSV file."""
        # Try to preserve input columns
        if results and results[0].get('data'):
            fieldnames = list(results[0]['data'].keys()) + ['response', 'success', 'error']
        else:
            fieldnames = ['prompt', 'response', 'success', 'error']

        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for result in results:
                row = result.get('data', {}).copy()
                row.update({
                    'response': result.get('response', ''),
                    'success': result['success'],
                    'error': result.get('error', '')
                })
                if not result.get('data'):
                    row['prompt'] = result['prompt']
                writer.writerow(row)

    def _save_to_json(self, output_file: Path, results: List[Dict[str, Any]]):
        """Save results to JSON file."""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)

    def _save_to_jsonl(self, output_file: Path, results: List[Dict[str, Any]]):
        """Save results to JSONL file."""
        with open(output_file, 'w', encoding='utf-8') as f:
            for result in results:
                f.write(json.dumps(result) + '\n')

    def get_batch_status(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a batch run."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute(
            "SELECT * FROM batch_runs WHERE id = ?", (batch_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        batch = dict(row)
        if batch['config']:
            batch['config'] = json.loads(batch['config'])

        return batch

    def list_batches(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent batch runs."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute(
            "SELECT * FROM batch_runs ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        batches = []
        for row in cursor.fetchall():
            batch = dict(row)
            if batch['config']:
                batch['config'] = json.loads(batch['config'])
            batches.append(batch)

        conn.close()
        return batches
