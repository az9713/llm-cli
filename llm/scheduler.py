"""
Scheduled prompts functionality for LLM CLI.

Schedule prompts to run at specific times or on recurring schedules.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from llm import user_dir


class Scheduler:
    """Manages scheduled prompt execution."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = user_dir() / "scheduler.db"
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the scheduler database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))

        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                id TEXT PRIMARY KEY,
                name TEXT,
                prompt TEXT NOT NULL,
                model TEXT NOT NULL,
                schedule_type TEXT NOT NULL,
                schedule_value TEXT NOT NULL,
                system_prompt TEXT,
                active BOOLEAN DEFAULT 1,
                last_run TEXT,
                next_run TEXT,
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS job_runs (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                executed_at TEXT NOT NULL,
                response TEXT,
                success BOOLEAN DEFAULT 1,
                error TEXT,
                FOREIGN KEY (job_id) REFERENCES scheduled_jobs(id)
            )
        """)

        conn.commit()
        conn.close()

    def add_job(
        self,
        prompt: str,
        model: str,
        schedule_type: str,  # 'once', 'cron'
        schedule_value: str,  # datetime or cron expression
        name: Optional[str] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """Add a scheduled job."""
        import ulid

        job_id = str(ulid.ULID())
        created_at = datetime.utcnow().isoformat()

        # Calculate next run time
        next_run = self._calculate_next_run(schedule_type, schedule_value)

        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO scheduled_jobs (
                id, name, prompt, model, schedule_type, schedule_value,
                system_prompt, active, next_run, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, name, prompt, model, schedule_type, schedule_value,
            system_prompt, True, next_run, created_at
        ))

        conn.commit()
        conn.close()

        return job_id

    def list_jobs(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """List all scheduled jobs."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        query = "SELECT * FROM scheduled_jobs"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY created_at DESC"

        cursor = conn.execute(query)
        jobs = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return jobs

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job details."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("SELECT * FROM scheduled_jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()

        conn.close()
        return dict(row) if row else None

    def delete_job(self, job_id: str) -> bool:
        """Delete a scheduled job."""
        conn = sqlite3.connect(str(self.db_path))

        cursor = conn.execute("DELETE FROM scheduled_jobs WHERE id = ?", (job_id,))
        conn.commit()
        deleted = cursor.rowcount > 0

        conn.close()
        return deleted

    def run_job_now(self, job_id: str) -> str:
        """Execute a job immediately."""
        job = self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        return self._execute_job(job)

    def _execute_job(self, job: Dict[str, Any]) -> str:
        """Execute a job and record the result."""
        import ulid
        from llm import get_model

        run_id = str(ulid.ULID())
        executed_at = datetime.utcnow().isoformat()

        try:
            model = get_model(job["model"])
            response = model.prompt(
                job["prompt"],
                system=job.get("system_prompt")
            )

            response_text = response.text()
            success = True
            error = None

        except Exception as e:
            response_text = None
            success = False
            error = str(e)

        # Record run
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO job_runs (id, job_id, executed_at, response, success, error)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (run_id, job["id"], executed_at, response_text, success, error))

        # Update job last_run
        conn.execute("""
            UPDATE scheduled_jobs
            SET last_run = ?
            WHERE id = ?
        """, (executed_at, job["id"]))

        conn.commit()
        conn.close()

        return run_id

    def get_job_runs(self, job_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get execution history for a job."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row

        cursor = conn.execute("""
            SELECT * FROM job_runs
            WHERE job_id = ?
            ORDER BY executed_at DESC
            LIMIT ?
        """, (job_id, limit))

        runs = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return runs

    def _calculate_next_run(self, schedule_type: str, schedule_value: str) -> str:
        """Calculate next run time."""
        if schedule_type == "once":
            return schedule_value
        elif schedule_type == "cron":
            # Simplified - would use croniter in production
            return datetime.utcnow().isoformat()
        else:
            return datetime.utcnow().isoformat()
