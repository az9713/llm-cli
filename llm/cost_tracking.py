"""
Cost tracking and budget management for LLM CLI.

Tracks API spending, manages budgets, and provides cost analytics.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

from llm import user_dir


# Model pricing (per 1K tokens) - as of Nov 2024
MODEL_PRICING = {
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002},
    "claude-opus-3": {"input": 0.015, "output": 0.075},
    "claude-sonnet-3.5": {"input": 0.003, "output": 0.015},
    "claude-haiku-3": {"input": 0.00025, "output": 0.00125},
    "gemini-pro": {"input": 0.000125, "output": 0.000375},
}


class CostTracker:
    """Manages cost tracking and budgets."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = user_dir() / "costs.db"
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the costs database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))

        # Costs table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS costs (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                log_id TEXT,
                model TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                input_cost REAL DEFAULT 0,
                output_cost REAL DEFAULT 0,
                total_cost REAL DEFAULT 0,
                project TEXT,
                tags TEXT
            )
        """)

        # Budgets table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                amount REAL NOT NULL,
                period TEXT NOT NULL,
                category TEXT DEFAULT 'global',
                category_value TEXT,
                alert_threshold REAL DEFAULT 0.8,
                hard_limit BOOLEAN DEFAULT 0,
                created_at TEXT NOT NULL,
                active BOOLEAN DEFAULT 1
            )
        """)

        # Budget alerts table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS budget_alerts (
                id TEXT PRIMARY KEY,
                budget_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                spent REAL NOT NULL,
                budget_amount REAL NOT NULL,
                percentage REAL NOT NULL,
                alert_type TEXT NOT NULL,
                FOREIGN KEY (budget_id) REFERENCES budgets(id)
            )
        """)

        # Pricing table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pricing (
                model TEXT PRIMARY KEY,
                input_cost_per_1k REAL NOT NULL,
                output_cost_per_1k REAL NOT NULL,
                last_updated TEXT NOT NULL,
                source TEXT DEFAULT 'default'
            )
        """)

        # Initialize default pricing
        for model, prices in MODEL_PRICING.items():
            conn.execute("""
                INSERT OR IGNORE INTO pricing (model, input_cost_per_1k, output_cost_per_1k, last_updated)
                VALUES (?, ?, ?, ?)
            """, (model, prices["input"], prices["output"], datetime.utcnow().isoformat()))

        conn.commit()
        conn.close()

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for a model call."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute(
            "SELECT input_cost_per_1k, output_cost_per_1k FROM pricing WHERE model = ?",
            (model,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            input_cost_per_1k, output_cost_per_1k = row
        else:
            # Default pricing if model not found
            input_cost_per_1k = 0.001
            output_cost_per_1k = 0.002

        input_cost = (input_tokens / 1000) * input_cost_per_1k
        output_cost = (output_tokens / 1000) * output_cost_per_1k
        return input_cost + output_cost

    def log_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        log_id: Optional[str] = None,
        project: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """Log a cost entry."""
        import ulid

        cost_id = str(ulid.ULID())
        timestamp = datetime.utcnow().isoformat()

        total_cost = self.calculate_cost(model, input_tokens, output_tokens)
        input_cost = (input_tokens / 1000) * self._get_input_cost(model)
        output_cost = (output_tokens / 1000) * self._get_output_cost(model)

        tags_json = json.dumps(tags) if tags else None

        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO costs (
                id, timestamp, log_id, model, input_tokens, output_tokens,
                input_cost, output_cost, total_cost, project, tags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cost_id, timestamp, log_id, model, input_tokens, output_tokens,
            input_cost, output_cost, total_cost, project, tags_json
        ))
        conn.commit()
        conn.close()

        # Check budgets
        self._check_budgets(model, project)

        return cost_id

    def _get_input_cost(self, model: str) -> float:
        """Get input cost per 1K tokens for a model."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute(
            "SELECT input_cost_per_1k FROM pricing WHERE model = ?", (model,)
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0.001

    def _get_output_cost(self, model: str) -> float:
        """Get output cost per 1K tokens for a model."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute(
            "SELECT output_cost_per_1k FROM pricing WHERE model = ?", (model,)
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0.002

    def get_spending(
        self,
        period: str = "month",
        project: Optional[str] = None,
        model: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get spending summary for a period."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        # Determine date range
        now = datetime.utcnow()
        if from_date and to_date:
            start_date = from_date
            end_date = to_date
        elif period == "today":
            start_date = now.replace(hour=0, minute=0, second=0).isoformat()
            end_date = now.isoformat()
        elif period == "week":
            start_date = (now - timedelta(days=7)).isoformat()
            end_date = now.isoformat()
        elif period == "month":
            start_date = now.replace(day=1, hour=0, minute=0, second=0).isoformat()
            end_date = now.isoformat()
        elif period == "year":
            start_date = now.replace(month=1, day=1, hour=0, minute=0, second=0).isoformat()
            end_date = now.isoformat()
        else:  # all
            start_date = "2000-01-01"
            end_date = now.isoformat()

        # Build query
        query = "SELECT * FROM costs WHERE timestamp >= ? AND timestamp <= ?"
        params = [start_date, end_date]

        if project:
            query += " AND project = ?"
            params.append(project)
        if model:
            query += " AND model = ?"
            params.append(model)

        cursor = conn.execute(query, params)
        costs = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Calculate summary
        total_cost = sum(c['total_cost'] for c in costs)
        total_prompts = len(costs)
        total_tokens = sum(c['input_tokens'] + c['output_tokens'] for c in costs)

        # Group by model
        by_model = {}
        for cost in costs:
            model_name = cost['model']
            if model_name not in by_model:
                by_model[model_name] = {'cost': 0, 'prompts': 0, 'tokens': 0}
            by_model[model_name]['cost'] += cost['total_cost']
            by_model[model_name]['prompts'] += 1
            by_model[model_name]['tokens'] += cost['input_tokens'] + cost['output_tokens']

        return {
            'total_cost': total_cost,
            'total_prompts': total_prompts,
            'total_tokens': total_tokens,
            'avg_cost_per_prompt': total_cost / total_prompts if total_prompts > 0 else 0,
            'by_model': by_model,
            'period': period,
            'start_date': start_date,
            'end_date': end_date
        }

    def set_budget(
        self,
        name: str,
        amount: float,
        period: str = "monthly",
        category: str = "global",
        category_value: Optional[str] = None,
        alert_threshold: float = 0.8,
        hard_limit: bool = False
    ) -> str:
        """Set a budget."""
        import ulid

        budget_id = str(ulid.ULID())
        now = datetime.utcnow().isoformat()

        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                INSERT INTO budgets (
                    id, name, amount, period, category, category_value,
                    alert_threshold, hard_limit, created_at, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                budget_id, name, amount, period, category, category_value,
                alert_threshold, hard_limit, now, True
            ))
            conn.commit()
        finally:
            conn.close()

        return budget_id

    def get_budgets(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all budgets."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        query = "SELECT * FROM budgets"
        if active_only:
            query += " WHERE active = 1"

        cursor = conn.execute(query)
        budgets = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return budgets

    def check_budget_status(self, budget_name: str) -> Dict[str, Any]:
        """Check status of a specific budget."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute(
            "SELECT * FROM budgets WHERE name = ? AND active = 1", (budget_name,)
        )
        budget = cursor.fetchone()
        conn.close()

        if not budget:
            return None

        budget = dict(budget)

        # Get spending for this budget's period
        spending = self.get_spending(
            period=budget['period'],
            project=budget['category_value'] if budget['category'] == 'project' else None,
            model=budget['category_value'] if budget['category'] == 'model' else None
        )

        spent = spending['total_cost']
        remaining = budget['amount'] - spent
        percentage = (spent / budget['amount']) * 100 if budget['amount'] > 0 else 0

        return {
            'budget_name': budget['name'],
            'amount': budget['amount'],
            'spent': spent,
            'remaining': remaining,
            'percentage': percentage,
            'period': budget['period'],
            'status': self._get_budget_status(percentage, budget['hard_limit']),
            'hard_limit': budget['hard_limit']
        }

    def _get_budget_status(self, percentage: float, hard_limit: bool) -> str:
        """Determine budget status based on percentage."""
        if percentage >= 100:
            return "exceeded" if hard_limit else "over_budget"
        elif percentage >= 90:
            return "critical"
        elif percentage >= 80:
            return "warning"
        else:
            return "ok"

    def _check_budgets(self, model: Optional[str] = None, project: Optional[str] = None):
        """Check all budgets and send alerts if needed."""
        budgets = self.get_budgets(active_only=True)

        for budget in budgets:
            # Filter budgets based on category
            if budget['category'] == 'model' and budget['category_value'] != model:
                continue
            if budget['category'] == 'project' and budget['category_value'] != project:
                continue

            status = self.check_budget_status(budget['name'])
            if not status:
                continue

            # Check if alert is needed
            if status['percentage'] >= (budget['alert_threshold'] * 100):
                self._create_alert(budget, status)

    def _create_alert(self, budget: Dict[str, Any], status: Dict[str, Any]):
        """Create a budget alert."""
        import ulid

        alert_id = str(ulid.ULID())
        now = datetime.utcnow().isoformat()

        alert_type = "warning" if status['percentage'] < 100 else "limit_reached"

        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO budget_alerts (
                id, budget_id, timestamp, spent, budget_amount, percentage, alert_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            alert_id, budget['id'], now, status['spent'],
            budget['amount'], status['percentage'], alert_type
        ))
        conn.commit()
        conn.close()

        # In a real implementation, this would send notifications
        # For now, just store the alert

    def delete_budget(self, name: str) -> bool:
        """Delete a budget."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute("DELETE FROM budgets WHERE name = ?", (name,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted
