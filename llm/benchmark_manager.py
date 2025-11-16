"""
Model benchmarking functionality for LLM CLI.

Run standardized benchmarks to evaluate model performance.
"""

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from llm import user_dir, get_model


class BenchmarkManager:
    """Manages model benchmarks."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = user_dir() / "benchmarks.db"
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the benchmarks database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))

        conn.execute("""
            CREATE TABLE IF NOT EXISTS benchmarks (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                test_cases JSON NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS benchmark_runs (
                id TEXT PRIMARY KEY,
                benchmark_id TEXT NOT NULL,
                models TEXT NOT NULL,
                results JSON NOT NULL,
                scores JSON NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (benchmark_id) REFERENCES benchmarks(id)
            )
        """)

        conn.commit()
        conn.close()

    def create_benchmark(
        self,
        name: str,
        test_cases: List[Dict[str, Any]],
        description: Optional[str] = None
    ) -> str:
        """Create a new benchmark."""
        import ulid

        benchmark_id = str(ulid.ULID())
        created_at = datetime.utcnow().isoformat()

        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO benchmarks (id, name, description, test_cases, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (benchmark_id, name, description, json.dumps(test_cases), created_at))

        conn.commit()
        conn.close()

        return benchmark_id

    def run_benchmark(
        self,
        benchmark_name: str,
        models: List[str]
    ) -> str:
        """Run a benchmark across multiple models."""
        import ulid

        # Get benchmark
        benchmark = self._get_benchmark(benchmark_name)
        if not benchmark:
            raise ValueError(f"Benchmark '{benchmark_name}' not found")

        test_cases = json.loads(benchmark["test_cases"])

        run_id = str(ulid.ULID())
        created_at = datetime.utcnow().isoformat()

        results = {}
        scores = {}

        for model_name in models:
            try:
                model = get_model(model_name)
                model_results = []

                for test in test_cases:
                    prompt = test.get("prompt", "")
                    expected = test.get("expected", "")

                    start_time = time.time()
                    response = model.prompt(prompt)
                    end_time = time.time()

                    response_text = response.text()

                    # Simple scoring (would be more sophisticated in production)
                    score = 1.0 if expected.lower() in response_text.lower() else 0.0

                    model_results.append({
                        "prompt": prompt,
                        "response": response_text,
                        "expected": expected,
                        "score": score,
                        "time": end_time - start_time
                    })

                # Calculate aggregate score
                avg_score = sum(r["score"] for r in model_results) / len(model_results) if model_results else 0
                avg_time = sum(r["time"] for r in model_results) / len(model_results) if model_results else 0

                results[model_name] = model_results
                scores[model_name] = {
                    "accuracy": avg_score,
                    "avg_time": avg_time,
                    "total_tests": len(model_results)
                }

            except Exception as e:
                results[model_name] = []
                scores[model_name] = {"error": str(e)}

        # Save run
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO benchmark_runs (id, benchmark_id, models, results, scores, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            benchmark["id"],
            json.dumps(models),
            json.dumps(results),
            json.dumps(scores),
            created_at
        ))

        conn.commit()
        conn.close()

        return run_id

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get benchmark run results."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT * FROM benchmark_runs WHERE id = ?
        """, (run_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        run = dict(row)
        run["models"] = json.loads(run["models"])
        run["results"] = json.loads(run["results"])
        run["scores"] = json.loads(run["scores"])

        return run

    def list_benchmarks(self) -> List[Dict[str, Any]]:
        """List all available benchmarks."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("SELECT id, name, description, created_at FROM benchmarks")
        benchmarks = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return benchmarks

    def _get_benchmark(self, name: str) -> Optional[Dict[str, Any]]:
        """Get benchmark by name."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("SELECT * FROM benchmarks WHERE name = ?", (name,))
        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else None
