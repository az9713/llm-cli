"""
Model comparison functionality for LLM CLI.

Compare responses from multiple models side-by-side.
"""

import json
import sqlite3
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from llm import get_model, user_dir


class ModelComparison:
    """Manages model comparisons."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = user_dir() / "comparisons.db"
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the comparisons database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))

        conn.execute("""
            CREATE TABLE IF NOT EXISTS comparisons (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                prompt TEXT NOT NULL,
                system_prompt TEXT,
                models TEXT NOT NULL,
                responses JSON NOT NULL,
                metrics JSON NOT NULL,
                notes TEXT
            )
        """)

        conn.commit()
        conn.close()

    def compare(
        self,
        prompt: str,
        models: List[str],
        system: Optional[str] = None,
        save: bool = True
    ) -> Dict[str, Any]:
        """Compare the same prompt across multiple models."""
        import ulid

        comparison_id = str(ulid.ULID())
        created_at = datetime.utcnow().isoformat()

        responses = []
        metrics = {}

        for model_name in models:
            try:
                model = get_model(model_name)

                start_time = time.time()
                response = model.prompt(prompt, system=system)
                end_time = time.time()

                response_time = end_time - start_time
                response_text = response.text()

                # Get token usage if available
                input_tokens = getattr(response, 'input_tokens', 0) if hasattr(response, 'input_tokens') else 0
                output_tokens = getattr(response, 'output_tokens', 0) if hasattr(response, 'output_tokens') else 0

                # Calculate cost if we have token info
                cost = 0.0
                if hasattr(response, 'input_tokens') and hasattr(response, 'output_tokens'):
                    from llm.cost_tracking import CostTracker
                    tracker = CostTracker()
                    cost = tracker.calculate_cost(model_name, input_tokens, output_tokens)

                response_data = {
                    'model': model_name,
                    'text': response_text,
                    'time': response_time,
                    'tokens': {
                        'input': input_tokens,
                        'output': output_tokens,
                        'total': input_tokens + output_tokens
                    },
                    'cost': cost,
                    'success': True,
                    'error': None
                }

                responses.append(response_data)

                metrics[model_name] = {
                    'time': response_time,
                    'tokens': input_tokens + output_tokens,
                    'cost': cost,
                    'length': len(response_text)
                }

            except Exception as e:
                response_data = {
                    'model': model_name,
                    'text': None,
                    'time': 0,
                    'tokens': {'input': 0, 'output': 0, 'total': 0},
                    'cost': 0,
                    'success': False,
                    'error': str(e)
                }
                responses.append(response_data)

                metrics[model_name] = {
                    'time': 0,
                    'tokens': 0,
                    'cost': 0,
                    'length': 0,
                    'error': str(e)
                }

        comparison = {
            'id': comparison_id,
            'created_at': created_at,
            'prompt': prompt,
            'system_prompt': system,
            'models': models,
            'responses': responses,
            'metrics': metrics
        }

        if save:
            self._save_comparison(comparison)

        return comparison

    def _save_comparison(self, comparison: Dict[str, Any]):
        """Save a comparison to the database."""
        conn = sqlite3.connect(str(self.db_path))

        conn.execute("""
            INSERT INTO comparisons (
                id, created_at, prompt, system_prompt, models, responses, metrics
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            comparison['id'],
            comparison['created_at'],
            comparison['prompt'],
            comparison['system_prompt'],
            json.dumps(comparison['models']),
            json.dumps(comparison['responses']),
            json.dumps(comparison['metrics'])
        ))

        conn.commit()
        conn.close()

    def get_comparison(self, comparison_id: str) -> Optional[Dict[str, Any]]:
        """Get a saved comparison by ID."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute(
            "SELECT * FROM comparisons WHERE id = ?", (comparison_id,)
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

    def list_comparisons(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent comparisons."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute(
            "SELECT * FROM comparisons ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        comparisons = []
        for row in cursor.fetchall():
            comp = dict(row)
            comp['models'] = json.loads(comp['models'])
            comp['responses'] = json.loads(comp['responses'])
            comp['metrics'] = json.loads(comp['metrics'])
            comparisons.append(comp)

        conn.close()
        return comparisons

    def get_best_model(self, comparison: Dict[str, Any], criteria: str = "cost") -> str:
        """Get the best model from a comparison based on criteria."""
        successful_responses = [r for r in comparison['responses'] if r['success']]

        if not successful_responses:
            return None

        if criteria == "cost":
            best = min(successful_responses, key=lambda r: r['cost'])
        elif criteria == "time":
            best = min(successful_responses, key=lambda r: r['time'])
        elif criteria == "length":
            best = max(successful_responses, key=lambda r: len(r['text'] or ''))
        else:
            best = successful_responses[0]

        return best['model']

    def format_comparison_text(self, comparison: Dict[str, Any], show_metrics: bool = True) -> str:
        """Format comparison as text for display."""
        output = []

        output.append("=" * 70)
        output.append("MODEL COMPARISON")
        output.append("=" * 70)
        output.append(f"Prompt: {comparison['prompt']}")
        output.append(f"Models: {', '.join(comparison['models'])}")
        output.append(f"Time: {comparison['created_at']}")
        output.append("")

        for response in comparison['responses']:
            output.append("─" * 70)
            output.append(f"MODEL: {response['model']}")

            if show_metrics:
                if response['success']:
                    output.append(f"Time: {response['time']:.2f}s | "
                                  f"Tokens: {response['tokens']['total']} | "
                                  f"Cost: ${response['cost']:.4f}")
                else:
                    output.append(f"ERROR: {response['error']}")

            output.append("─" * 70)

            if response['success']:
                output.append(response['text'] or '')
            else:
                output.append(f"[Failed: {response['error']}]")

            output.append("")

        if show_metrics:
            output.append("=" * 70)
            output.append("SUMMARY")
            output.append("=" * 70)

            successful = [r for r in comparison['responses'] if r['success']]
            if successful:
                fastest = min(successful, key=lambda r: r['time'])
                cheapest = min(successful, key=lambda r: r['cost'])
                longest = max(successful, key=lambda r: len(r['text'] or ''))

                output.append(f"Fastest: {fastest['model']} ({fastest['time']:.2f}s)")
                output.append(f"Cheapest: {cheapest['model']} (${cheapest['cost']:.4f})")
                output.append(f"Longest response: {longest['model']} ({len(longest['text'])} chars)")

        return "\n".join(output)
